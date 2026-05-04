import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class StrategyConfig:
    # 종목 선정
    screen_top_n: int = 30
    min_change_pct: float = 7.0

    # 진입 조건
    volume_multiplier: float = 2.0
    breakout_lookback: int = 10

    # D+1 진입 완화
    d1_volume_multiplier: float = 1.8  # 기본 2.0 대비 10% 하향

    # 청산 조건
    profit_1st_pct: float = 3.0
    profit_1st_qty_ratio: float = 0.5
    trailing_start_pct: float = 5.0
    trailing_gap_pct: float = 1.5
    stop_loss_pct: float = 2.5
    market_close_time: str = "1515"

    # 갭 제어
    gap_hold_minutes: int = 15

    # D+1 가점
    d1_score_bonus: int = 15
    d1_theme_continue_bonus: int = 5
    d1_master_stock_threshold: int = 500_000_000_000  # 5000억


@dataclass
class Config:
    app_key: str = field(default_factory=lambda: os.getenv("KIS_APP_KEY", ""))
    app_secret: str = field(default_factory=lambda: os.getenv("KIS_APP_SECRET", ""))
    account_no: str = field(default_factory=lambda: os.getenv("KIS_ACCOUNT_NO", ""))
    is_real: bool = field(default_factory=lambda: os.getenv("IS_REAL_TRADING", "false").lower() == "true")

    tg_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    tg_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    max_positions: int = field(default_factory=lambda: int(os.getenv("MAX_POSITIONS", "3")))
    total_capital: float = field(default_factory=lambda: float(os.getenv("TOTAL_CAPITAL", "10000000")))

    strategy: StrategyConfig = field(default_factory=StrategyConfig)

    @property
    def base_url(self) -> str:
        if self.is_real:
            return "https://openapi.koreainvestment.com:9443"
        return "https://openapivts.koreainvestment.com:9443"

    @property
    def ws_url(self) -> str:
        if self.is_real:
            return "ws://ops.koreainvestment.com:21000"
        return "ws://ops.koreainvestment.com:31000"


cfg = Config()
