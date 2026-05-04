import logging
from src.api.kis_rest import KISRestClient
from src.strategy.screener import StockCandidate
from config import cfg

logger = logging.getLogger(__name__)


class SignalEngine:
    def __init__(self, rest: KISRestClient):
        self.rest = rest
        self.st = cfg.strategy

    def check_entry(self, candidate: StockCandidate) -> bool:
        """
        진입 조건:
        1. 현재 거래량 >= 이전 5봉 평균 거래량 × 2.0 (D+1이면 1.8)
        2. 현재가 > 이전 10봉 고가 최대값
        3. 현재가 > 당일 시가
        """
        try:
            candles = self.rest.get_minute_candles(candidate.code)
            if len(candles) < 11:
                return False

            # 최신봉 = index 0
            current_vol = int(candles[0].get("cntg_vol", 0))
            prev_5_avg = sum(int(c.get("cntg_vol", 0)) for c in candles[1:6]) / 5

            vol_multiplier = (
                self.st.d1_volume_multiplier if candidate.is_d1
                else self.st.volume_multiplier
            )
            if prev_5_avg == 0 or current_vol < prev_5_avg * vol_multiplier:
                logger.debug(f"{candidate.code}: volume condition failed ({current_vol:.0f} < {prev_5_avg * vol_multiplier:.0f})")
                return False

            prev_10_high = max(float(c.get("stck_hgpr", 0)) for c in candles[1:11])
            current_price = candidate.price
            today_open = self.rest.get_today_open(candidate.code)

            breakout = current_price > prev_10_high and current_price > today_open
            if not breakout:
                logger.debug(f"{candidate.code}: breakout failed (price={current_price}, high={prev_10_high}, open={today_open})")
            return breakout

        except Exception as e:
            logger.error(f"Signal check error {candidate.code}: {e}")
            return False
