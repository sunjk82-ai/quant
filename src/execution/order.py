import math
import logging
from src.api.kis_rest import KISRestClient
from src.execution.position import Position, PositionManager, ExitSignal
from src.monitor.telegram import TelegramBot
from src.logger.csv_logger import TradeLogger
from config import cfg

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(
        self,
        rest: KISRestClient,
        pos_mgr: PositionManager,
        tg: TelegramBot,
        trade_log: TradeLogger,
    ):
        self.rest = rest
        self.pos_mgr = pos_mgr
        self.tg = tg
        self.trade_log = trade_log

    def _capital_per_slot(self) -> float:
        return cfg.total_capital / cfg.max_positions

    def buy(self, code: str, name: str, price: float, score: int, reason: str):
        if self.pos_mgr.is_full:
            logger.info(f"Position full, skip buy: {name}({code})")
            return
        if code in self.pos_mgr.positions:
            return

        capital = self._capital_per_slot()
        qty = math.floor(capital / price)
        if qty <= 0:
            logger.warning(f"Insufficient capital for {name}({code})")
            return

        mode = "실거래" if cfg.is_real else "가상"
        logger.info(f"[{mode}] BUY {name}({code}) {qty}주 @{price:,.0f} | 점수:{score} | {reason}")

        if cfg.is_real:
            try:
                result = self.rest.place_order(code, qty, int(price), "buy")
                logger.info(f"Order result: {result}")
            except Exception as e:
                logger.error(f"Buy order failed: {e}")
                return

        pos = Position(code=code, name=name, entry_price=price, qty=qty)
        self.pos_mgr.add(pos)
        self.tg.send_entry(name, code, price, qty, score, reason)
        self.trade_log.log(code, name, "BUY", price, qty, reason)

    def sell(self, code: str, price: float, signal: str, qty: int):
        pos = self.pos_mgr.positions.get(code)
        if pos is None:
            return

        mode = "실거래" if cfg.is_real else "가상"
        pnl_pct = pos.pnl_pct(price)
        logger.info(f"[{mode}] SELL {pos.name}({code}) {qty}주 @{price:,.0f} | {signal} | PnL:{pnl_pct:+.2f}%")

        if cfg.is_real:
            try:
                self.rest.place_order(code, qty, 0, "sell")  # 시장가 매도
            except Exception as e:
                logger.error(f"Sell order failed: {e}")
                return

        self.tg.send_exit(pos.name, code, price, qty, signal, pnl_pct)
        self.trade_log.log(code, pos.name, f"SELL_{signal}", price, qty, signal, pnl_pct)

        if signal == ExitSignal.PARTIAL:
            self.pos_mgr.apply_partial(code)
        else:
            self.pos_mgr.remove(code)

    def handle_exit(self, code: str, price: float, signal: str):
        pos = self.pos_mgr.positions.get(code)
        if pos is None or signal == ExitSignal.NONE:
            return

        if signal == ExitSignal.PARTIAL:
            qty = int(pos.qty * cfg.strategy.profit_1st_qty_ratio)
        else:
            qty = pos.remaining_qty

        self.sell(code, price, signal, qty)
