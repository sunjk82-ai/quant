import time
import logging
import requests
from config import cfg

logger = logging.getLogger(__name__)

# 스팸 방지: 동일 코드 메시지 간격 (초)
SPAM_GATE = {
    "entry": 60,
    "exit": 30,
    "alert": 300,
}


class TelegramBot:
    def __init__(self):
        self._last_sent: dict[str, float] = {}
        self._base = f"https://api.telegram.org/bot{cfg.tg_token}"

    def _can_send(self, key: str, gate_type: str = "alert") -> bool:
        now = time.time()
        last = self._last_sent.get(key, 0)
        if now - last >= SPAM_GATE.get(gate_type, 60):
            self._last_sent[key] = now
            return True
        return False

    def _send(self, text: str):
        if not cfg.tg_token or not cfg.tg_chat_id:
            logger.debug(f"[TG skip - no token] {text}")
            return
        try:
            requests.post(
                f"{self._base}/sendMessage",
                json={"chat_id": cfg.tg_chat_id, "text": text, "parse_mode": "HTML"},
                timeout=5,
            )
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")

    def send_entry(self, name: str, code: str, price: float, qty: int, score: int, reason: str):
        if not self._can_send(f"entry_{code}", "entry"):
            return
        mode = "🔴실거래" if cfg.is_real else "🟡가상"
        text = (
            f"{mode} <b>매수 체결</b>\n"
            f"종목: {name} ({code})\n"
            f"가격: {price:,.0f}원 | 수량: {qty}주\n"
            f"점수: {score}점 | 사유: {reason}"
        )
        self._send(text)

    def send_exit(self, name: str, code: str, price: float, qty: int, signal: str, pnl_pct: float):
        if not self._can_send(f"exit_{code}", "exit"):
            return
        emoji = "✅" if pnl_pct >= 0 else "🔻"
        text = (
            f"{emoji} <b>매도 체결</b>\n"
            f"종목: {name} ({code})\n"
            f"가격: {price:,.0f}원 | 수량: {qty}주\n"
            f"신호: {signal} | 수익률: {pnl_pct:+.2f}%"
        )
        self._send(text)

    def send_alert(self, message: str, key: str = "general"):
        if not self._can_send(key, "alert"):
            return
        self._send(f"⚠️ {message}")

    def send_master_stock_alert(self, name: str, code: str, trade_amount: int):
        key = f"master_{code}"
        if not self._can_send(key, "alert"):
            return
        text = (
            f"🌟 <b>마스터스탁 감지</b>\n"
            f"{name} ({code})\n"
            f"거래대금: {trade_amount / 1e8:,.0f}억원"
        )
        self._send(text)

    def send_daily_summary(self, summary: str):
        self._send(f"📊 <b>일일 결산</b>\n{summary}")
