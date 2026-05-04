"""
Saeiti V2 — 홍인기 주도주 단타 자동화 시스템
"""
import asyncio
import logging
import sys
import time
from datetime import datetime

from config import cfg
from src.api.kis_rest import KISRestClient
from src.api.kis_ws import KISWebSocket
from src.strategy.screener import StockScreener
from src.strategy.signals import SignalEngine
from src.filter.news import NewsFilter
from src.filter.theme import ThemeFilter
from src.filter.global_market import GlobalMarketFilter
from src.execution.position import PositionManager, ExitSignal
from src.execution.order import OrderManager
from src.monitor.telegram import TelegramBot
from src.logger.csv_logger import TradeLogger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/saeiti_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


class SaeitiBot:
    def __init__(self):
        self.rest = KISRestClient()
        self.pos_mgr = PositionManager()
        self.tg = TelegramBot()
        self.trade_log = TradeLogger()
        self.order_mgr = OrderManager(self.rest, self.pos_mgr, self.tg, self.trade_log)
        self.screener = StockScreener(self.rest)
        self.signal_engine = SignalEngine(self.rest)
        self.news_filter = NewsFilter()
        self.theme_filter = ThemeFilter()
        self.global_filter = GlobalMarketFilter()
        self.ws: KISWebSocket | None = None
        self.watchlist: dict[str, object] = {}  # code -> StockCandidate
        self._tick_prices: dict[str, float] = {}
        self._gap_stocks: set[str] = set()  # 갭 유보 중인 종목

    # ──────────────────────────────────────────
    # WebSocket tick 핸들러
    # ──────────────────────────────────────────
    def _on_tick(self, tick: dict):
        code = tick["code"]
        price = float(tick["price"])
        self._tick_prices[code] = price

    # ──────────────────────────────────────────
    # 전처리: 글로벌 감성 + 스크리닝
    # ──────────────────────────────────────────
    def _premarket_setup(self):
        logger.info("=== 프리마켓 초기화 시작 ===")

        sentiment = self.global_filter.get_sentiment()
        logger.info(f"글로벌 감성: {sentiment['sentiment']} | NASDAQ {sentiment['nasdaq_chg']:+.2f}% SOX {sentiment['sox_chg']:+.2f}%")
        self.tg.send_alert(
            f"글로벌 감성: {sentiment['sentiment']}\n"
            f"나스닥 {sentiment['nasdaq_chg']:+.2f}% / S&P500 {sentiment['sp500_chg']:+.2f}% / SOX {sentiment['sox_chg']:+.2f}%",
            key="global_sentiment"
        )

        if sentiment["sentiment"] == "risk_off":
            logger.warning("Risk-Off 감지 — 필터 강화 모드 진입")

        candidates = self.screener.screen()
        for c in candidates:
            theme_score, is_d1 = self.theme_filter.score(c.code)
            c.score += theme_score
            c.is_d1 = is_d1

            if self.theme_filter.is_master_stock(c.code, c.trade_amount):
                self.tg.send_master_stock_alert(c.name, c.code, c.trade_amount)

        candidates.sort(key=lambda x: x.score, reverse=True)
        self.watchlist = {c.code: c for c in candidates}
        logger.info(f"워치리스트 확정: {len(self.watchlist)}종목")
        for c in candidates[:5]:
            logger.info(f"  [{c.score:+d}] {c.name}({c.code}) {c.change_pct:+.1f}% {'★D+1' if c.is_d1 else ''}")

    # ──────────────────────────────────────────
    # 장 중 루프
    # ──────────────────────────────────────────
    async def _market_loop(self):
        screen_interval = 300  # 5분마다 재스크리닝
        last_screen = 0.0

        while True:
            now_str = datetime.now().strftime("%H%M")

            # 장 마감
            if now_str >= cfg.strategy.market_close_time:
                await self._close_all_positions(now_str)
                break

            # 재스크리닝
            if time.time() - last_screen >= screen_interval:
                await asyncio.to_thread(self._refresh_watchlist)
                last_screen = time.time()

            # 포지션 청산 체크
            for code, pos in list(self.pos_mgr.positions.items()):
                price = self._tick_prices.get(code, pos.entry_price)
                signal = self.pos_mgr.check_exit(code, price, now_str)
                if signal != ExitSignal.NONE:
                    await asyncio.to_thread(self.order_mgr.handle_exit, code, price, signal)

            # 신규 진입 체크
            if not self.pos_mgr.is_full:
                await self._check_entries(now_str)

            await asyncio.sleep(1)

    async def _check_entries(self, now_str: str):
        gap_cutoff = cfg.strategy.gap_hold_minutes
        market_open_min = int("0900")

        for code, candidate in list(self.watchlist.items()):
            if code in self.pos_mgr.positions:
                continue

            # 갭 유보 처리 (시가 갭 방지: 장 초반 15분)
            if int(now_str) < market_open_min + gap_cutoff and code in self._gap_stocks:
                continue

            price = self._tick_prices.get(code, candidate.price)
            candidate.price = price

            ok = await asyncio.to_thread(self.signal_engine.check_entry, candidate)
            if not ok:
                continue

            # 뉴스 필터 (실제로는 뉴스 API 연동 필요 — 현재는 스킵)
            news_score, news_verdict = 0, "재료미확인"
            if news_verdict == "악재감지":
                logger.info(f"{candidate.name}: 악재 감지 — 진입 차단")
                continue

            reason_parts = []
            if candidate.is_d1:
                reason_parts.append(f"D+1(+{candidate.score})")
            reason_parts.append(f"뉴스:{news_verdict}")

            self.order_mgr.buy(
                code=code,
                name=candidate.name,
                price=price,
                score=candidate.score,
                reason=" | ".join(reason_parts) or "Pure Flow",
            )

    def _refresh_watchlist(self):
        new_candidates = self.screener.screen()
        for c in new_candidates:
            theme_score, is_d1 = self.theme_filter.score(c.code)
            c.score += theme_score
            c.is_d1 = is_d1
            if c.code not in self.watchlist:
                self.watchlist[c.code] = c
                if self.ws:
                    asyncio.run_coroutine_threadsafe(self.ws.subscribe(c.code), asyncio.get_event_loop())

    async def _close_all_positions(self, now_str: str):
        logger.info("=== 15:15 전량 청산 시작 ===")
        for code, pos in list(self.pos_mgr.positions.items()):
            price = self._tick_prices.get(code, pos.entry_price)
            self.order_mgr.handle_exit(code, price, ExitSignal.TIME_EXIT)

    # ──────────────────────────────────────────
    # 메인 실행
    # ──────────────────────────────────────────
    async def run(self):
        mode = "실거래" if cfg.is_real else "가상매매"
        logger.info(f"=== Saeiti V2 시작 [{mode}] ===")
        self.tg.send_alert(f"Saeiti V2 시작 [{mode}]", key="startup")

        # 프리마켓 초기화
        await asyncio.to_thread(self._premarket_setup)

        # WebSocket 연결
        try:
            approval_key = await asyncio.to_thread(self.rest.get_ws_approval_key)
            self.ws = KISWebSocket(approval_key, self._on_tick)
            await self.ws.connect()
            for code in self.watchlist:
                await self.ws.subscribe(code)
        except Exception as e:
            logger.warning(f"WebSocket 연결 실패 (REST 폴링 모드로 전환): {e}")

        # 장 중 루프
        await self._market_loop()

        # 일일 결산
        summary = self.trade_log.get_daily_summary()
        logger.info(f"=== 일일 결산 ===\n{summary}")
        self.tg.send_daily_summary(summary)

        if self.ws:
            await self.ws.close()


if __name__ == "__main__":
    asyncio.run(SaeitiBot().run())
