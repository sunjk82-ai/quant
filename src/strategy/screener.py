import logging
from dataclasses import dataclass, field
from src.api.kis_rest import KISRestClient
from config import cfg

logger = logging.getLogger(__name__)


@dataclass
class StockCandidate:
    code: str
    name: str
    price: float
    change_pct: float
    volume: int
    trade_amount: int  # 거래대금 (원)
    industry: str = ""
    score: int = 0
    is_d1: bool = False


class StockScreener:
    def __init__(self, rest: KISRestClient):
        self.rest = rest
        self.st = cfg.strategy

    def screen(self) -> list[StockCandidate]:
        """거래대금 상위 30 ∩ 등락률 +7% 이상 → 업종 대장주 1종목만 선별"""
        raw_kospi = self.rest.get_volume_rank(market="J", top_n=self.st.screen_top_n)
        raw_kosdaq = self.rest.get_volume_rank(market="Q", top_n=self.st.screen_top_n)

        candidates: list[StockCandidate] = []
        for item in raw_kospi + raw_kosdaq:
            try:
                change_pct = float(item.get("prdy_ctrt", 0))
                if change_pct < self.st.min_change_pct:
                    continue

                price_data = self.rest.get_current_price(item["mksc_shrn_iscd"])
                trade_amount = int(item.get("acml_tr_pbmn", 0))

                candidates.append(
                    StockCandidate(
                        code=item["mksc_shrn_iscd"],
                        name=item.get("hts_kor_isnm", ""),
                        price=float(item.get("stck_prpr", 0)),
                        change_pct=change_pct,
                        volume=int(item.get("acml_vol", 0)),
                        trade_amount=trade_amount,
                        industry=price_data.get("bstp_kor_isnm", ""),
                    )
                )
            except Exception as e:
                logger.warning(f"Screener skip {item.get('mksc_shrn_iscd')}: {e}")

        # 거래대금 기준 정렬
        candidates.sort(key=lambda x: x.trade_amount, reverse=True)
        deduped = self._deduplicate_by_industry(candidates)
        logger.info(f"Screened {len(deduped)} candidates (before: {len(candidates)})")
        return deduped

    def _deduplicate_by_industry(self, candidates: list[StockCandidate]) -> list[StockCandidate]:
        """동일 업종 내 등락률 1등주만 남김"""
        seen: dict[str, StockCandidate] = {}
        no_industry: list[StockCandidate] = []

        for c in candidates:
            if not c.industry:
                no_industry.append(c)
                continue
            existing = seen.get(c.industry)
            if existing is None or c.change_pct > existing.change_pct:
                seen[c.industry] = c

        return list(seen.values()) + no_industry
