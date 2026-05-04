"""
글로벌 시장 감성 필터.
Yahoo Finance 비공식 API로 나스닥/S&P500/SOX 전일 등락률을 조회.
"""
import logging
import requests

logger = logging.getLogger(__name__)

INDICES = {
    "NASDAQ": "^IXIC",
    "SP500": "^GSPC",
    "SOX": "^SOX",
}

# Risk-On 기준: 나스닥 +1% 이상
RISK_ON_THRESHOLD = 1.0
# Risk-Off 기준: 나스닥 -1% 이하
RISK_OFF_THRESHOLD = -1.0


def _fetch_change_pct(symbol: str) -> float:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        if len(closes) >= 2 and closes[-1] and closes[-2]:
            return (closes[-1] - closes[-2]) / closes[-2] * 100
    except Exception as e:
        logger.warning(f"Global market fetch failed ({symbol}): {e}")
    return 0.0


class GlobalMarketFilter:
    def get_sentiment(self) -> dict:
        """
        Returns:
            {
                "sentiment": "risk_on" | "neutral" | "risk_off",
                "nasdaq_chg": float,
                "sp500_chg": float,
                "sox_chg": float,
            }
        """
        nasdaq = _fetch_change_pct("^IXIC")
        sp500 = _fetch_change_pct("^GSPC")
        sox = _fetch_change_pct("^SOX")

        if nasdaq >= RISK_ON_THRESHOLD:
            sentiment = "risk_on"
        elif nasdaq <= RISK_OFF_THRESHOLD:
            sentiment = "risk_off"
        else:
            sentiment = "neutral"

        result = {
            "sentiment": sentiment,
            "nasdaq_chg": round(nasdaq, 2),
            "sp500_chg": round(sp500, 2),
            "sox_chg": round(sox, 2),
        }
        logger.info(f"Global sentiment: {result}")
        return result
