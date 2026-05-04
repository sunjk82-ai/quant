import csv
import logging
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).parents[2] / "logs"
LOGS_DIR.mkdir(exist_ok=True)

FIELDNAMES = [
    "datetime", "code", "name", "side", "price", "qty",
    "amount", "reason", "pnl_pct"
]


class TradeLogger:
    def __init__(self):
        self._today = date.today().strftime("%Y-%m-%d")
        self._path = LOGS_DIR / f"trade_history_{self._today}.csv"
        self._ensure_header()

    def _ensure_header(self):
        if not self._path.exists():
            with open(self._path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()

    def log(
        self,
        code: str,
        name: str,
        side: str,
        price: float,
        qty: int,
        reason: str = "",
        pnl_pct: float = 0.0,
    ):
        row = {
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "name": name,
            "side": side,
            "price": int(price),
            "qty": qty,
            "amount": int(price * qty),
            "reason": reason,
            "pnl_pct": f"{pnl_pct:.2f}",
        }
        try:
            with open(self._path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writerow(row)
        except Exception as e:
            logger.error(f"CSV log failed: {e}")

    def get_daily_summary(self) -> str:
        if not self._path.exists():
            return "거래 내역 없음"

        trades = []
        with open(self._path, newline="", encoding="utf-8-sig") as f:
            trades = list(csv.DictReader(f))

        sells = [t for t in trades if t["side"].startswith("SELL")]
        if not sells:
            return "금일 매도 없음"

        wins = [t for t in sells if float(t["pnl_pct"]) > 0]
        total_pnl = sum(float(t["pnl_pct"]) for t in sells)
        win_rate = len(wins) / len(sells) * 100

        return (
            f"총 매매: {len(sells)}건\n"
            f"승률: {win_rate:.1f}% ({len(wins)}승 {len(sells)-len(wins)}패)\n"
            f"평균 수익률: {total_pnl/len(sells):.2f}%"
        )
