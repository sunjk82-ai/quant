import json
import logging
from datetime import date
from pathlib import Path
from config import cfg

logger = logging.getLogger(__name__)

THEMES_FILE = Path(__file__).parents[2] / "themes.json"


class ThemeFilter:
    def __init__(self):
        self._data: dict = {}
        self._d1_stocks: dict[str, dict] = {}  # code -> {score, is_master}
        self._d1_themes: set[str] = set()
        self.load()

    def load(self):
        if not THEMES_FILE.exists():
            logger.warning("themes.json not found")
            return
        with open(THEMES_FILE, encoding="utf-8") as f:
            self._data = json.load(f)
        self._build_d1_map()

    def _build_d1_map(self):
        """최신 2개 날짜 추출 → D+1 후보군 설정"""
        dates = sorted(self._data.keys(), reverse=True)
        if not dates:
            return

        d0_date = dates[0]
        d0_entries = self._data[d0_date]
        d1_theme_names: set[str] = set()

        for entry in d0_entries:
            theme_name = entry.get("theme", "")
            d1_theme_names.add(theme_name)
            for stock in entry.get("stocks", []):
                code = stock["code"]
                self._d1_stocks[code] = {
                    "score": cfg.strategy.d1_score_bonus,
                    "theme": theme_name,
                    "is_master": stock.get("is_leader", False),
                }

        if len(dates) >= 2:
            d_minus1_date = dates[1]
            for entry in self._data[d_minus1_date]:
                if entry.get("theme") in d1_theme_names:
                    self._d1_themes.add(entry.get("theme"))
                    for stock in entry.get("stocks", []):
                        code = stock["code"]
                        if code in self._d1_stocks:
                            self._d1_stocks[code]["score"] += cfg.strategy.d1_theme_continue_bonus

        logger.info(f"D+1 candidates loaded: {len(self._d1_stocks)} stocks, base date={d0_date}")

    def score(self, code: str) -> tuple[int, bool]:
        """(가점, is_d1) 반환"""
        info = self._d1_stocks.get(code)
        if info is None:
            return 0, False
        return info["score"], True

    def is_master_stock(self, code: str, trade_amount: int) -> bool:
        info = self._d1_stocks.get(code)
        if info and trade_amount >= cfg.strategy.d1_master_stock_threshold:
            return True
        return False
