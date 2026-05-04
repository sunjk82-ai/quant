import time
import logging
from dataclasses import dataclass, field
from config import cfg

logger = logging.getLogger(__name__)


@dataclass
class Position:
    code: str
    name: str
    entry_price: float
    qty: int
    entry_time: float = field(default_factory=time.time)
    peak_price: float = 0.0
    partial_sold: bool = False  # 1차 익절 완료 여부

    def __post_init__(self):
        self.peak_price = self.entry_price

    @property
    def remaining_qty(self) -> int:
        if self.partial_sold:
            return self.qty - int(self.qty * cfg.strategy.profit_1st_qty_ratio)
        return self.qty

    def update_peak(self, price: float):
        if price > self.peak_price:
            self.peak_price = price

    def pnl_pct(self, current_price: float) -> float:
        return (current_price - self.entry_price) / self.entry_price * 100

    def peak_pnl_pct(self, current_price: float) -> float:
        return (current_price - self.peak_price) / self.peak_price * 100


class ExitSignal:
    NONE = "none"
    PARTIAL = "partial"     # 1차 익절 (50%)
    TRAILING = "trailing"   # 트레일링 스탑 전량
    STOP_LOSS = "stop_loss" # 손절 전량
    TIME_EXIT = "time_exit" # 시간 청산 전량


class PositionManager:
    def __init__(self):
        self.positions: dict[str, Position] = {}
        self.st = cfg.strategy

    def add(self, pos: Position):
        self.positions[pos.code] = pos
        logger.info(f"Position opened: {pos.name}({pos.code}) {pos.qty}주 @{pos.entry_price:,.0f}")

    def remove(self, code: str):
        self.positions.pop(code, None)

    def check_exit(self, code: str, current_price: float, current_time_str: str) -> str:
        """ExitSignal 반환"""
        pos = self.positions.get(code)
        if pos is None:
            return ExitSignal.NONE

        pos.update_peak(current_price)
        pnl = pos.pnl_pct(current_price)
        drop_from_peak = pos.peak_pnl_pct(current_price)

        # 시간 청산
        if current_time_str >= self.st.market_close_time:
            return ExitSignal.TIME_EXIT

        # 손절: 진입가 대비 -2.5%
        if pnl <= -self.st.stop_loss_pct:
            return ExitSignal.STOP_LOSS

        # 트레일링: +5% 도달 후 고점 대비 -1.5%
        if pos.peak_price >= pos.entry_price * (1 + self.st.trailing_start_pct / 100):
            if drop_from_peak <= -self.st.trailing_gap_pct:
                return ExitSignal.TRAILING

        # 1차 익절: +3% (아직 미실행)
        if not pos.partial_sold and pnl >= self.st.profit_1st_pct:
            return ExitSignal.PARTIAL

        return ExitSignal.NONE

    def apply_partial(self, code: str):
        if code in self.positions:
            self.positions[code].partial_sold = True

    @property
    def is_full(self) -> bool:
        return len(self.positions) >= cfg.max_positions
