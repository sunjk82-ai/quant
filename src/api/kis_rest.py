import time
import requests
from typing import Optional
from config import cfg


class KISRestClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._token_expired_at: float = 0.0
        self.session = requests.Session()

    # ──────────────────────────────────────────
    # OAuth2
    # ──────────────────────────────────────────
    def _ensure_token(self):
        if self._token and time.time() < self._token_expired_at:
            return
        resp = self.session.post(
            f"{cfg.base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": cfg.app_key,
                "appsecret": cfg.app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expired_at = time.time() + int(data.get("expires_in", 86400)) - 60

    def _headers(self, tr_id: str) -> dict:
        self._ensure_token()
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self._token}",
            "appkey": cfg.app_key,
            "appsecret": cfg.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def get_ws_approval_key(self) -> str:
        resp = self.session.post(
            f"{cfg.base_url}/oauth2/Approval",
            json={
                "grant_type": "client_credentials",
                "appkey": cfg.app_key,
                "secretkey": cfg.app_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()["approval_key"]

    # ──────────────────────────────────────────
    # 시장 데이터
    # ──────────────────────────────────────────
    def get_volume_rank(self, market: str = "J", top_n: int = 30) -> list[dict]:
        """거래량 상위 종목 조회 (J=KOSPI, Q=KOSDAQ)"""
        params = {
            "FID_COND_MRKT_DIV_CODE": market,
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": "",
        }
        resp = self.session.get(
            f"{cfg.base_url}/uapi/domestic-stock/v1/quotations/volume-rank",
            headers=self._headers("FHPST01710000"),
            params=params,
        )
        resp.raise_for_status()
        return resp.json().get("output", [])[:top_n]

    def get_current_price(self, code: str) -> dict:
        """현재가 조회"""
        resp = self.session.get(
            f"{cfg.base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._headers("FHKST01010100"),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
        )
        resp.raise_for_status()
        return resp.json().get("output", {})

    def get_minute_candles(self, code: str, time_str: str = "") -> list[dict]:
        """분봉 조회 (최근 30봉)"""
        resp = self.session.get(
            f"{cfg.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            headers=self._headers("FHKST03010200"),
            params={
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_HOUR_1": time_str or "153000",
                "FID_PW_DATA_INCU_YN": "N",
            },
        )
        resp.raise_for_status()
        return resp.json().get("output2", [])

    def get_today_open(self, code: str) -> float:
        data = self.get_current_price(code)
        return float(data.get("stck_oprc", 0))

    # ──────────────────────────────────────────
    # 주문
    # ──────────────────────────────────────────
    def place_order(self, code: str, qty: int, price: int, side: str) -> dict:
        """
        side: 'buy' | 'sell'
        price=0 → 시장가
        """
        if cfg.is_real:
            tr_id = "TTTC0802U" if side == "buy" else "TTTC0801U"
        else:
            tr_id = "VTTC0802U" if side == "buy" else "VTTC0801U"

        ord_dvsn = "01" if price == 0 else "00"  # 01=시장가, 00=지정가

        body = {
            "CANO": cfg.account_no.split("-")[0],
            "ACNT_PRDT_CD": cfg.account_no.split("-")[1] if "-" in cfg.account_no else "01",
            "PDNO": code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        resp = self.session.post(
            f"{cfg.base_url}/uapi/domestic-stock/v1/trading/order-cash",
            headers=self._headers(tr_id),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    def get_balance(self) -> dict:
        """계좌 잔고 조회"""
        tr_id = "TTTC8434R" if cfg.is_real else "VTTC8434R"
        resp = self.session.get(
            f"{cfg.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=self._headers(tr_id),
            params={
                "CANO": cfg.account_no.split("-")[0],
                "ACNT_PRDT_CD": cfg.account_no.split("-")[1] if "-" in cfg.account_no else "01",
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        resp.raise_for_status()
        return resp.json()
