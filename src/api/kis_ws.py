import asyncio
import json
import logging
from typing import Callable
import websockets
from config import cfg

logger = logging.getLogger(__name__)


class KISWebSocket:
    def __init__(self, approval_key: str, on_tick: Callable[[dict], None]):
        self.approval_key = approval_key
        self.on_tick = on_tick
        self._ws = None
        self._subscribed: set[str] = set()

    async def connect(self):
        self._ws = await websockets.connect(cfg.ws_url, ping_interval=30)
        logger.info("WebSocket connected")
        asyncio.create_task(self._recv_loop())

    async def subscribe(self, code: str):
        if code in self._subscribed or self._ws is None:
            return
        payload = {
            "header": {
                "approval_key": self.approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": "H0STCNT0",  # 실시간 체결가
                    "tr_key": code,
                }
            },
        }
        await self._ws.send(json.dumps(payload))
        self._subscribed.add(code)
        logger.debug(f"Subscribed: {code}")

    async def unsubscribe(self, code: str):
        if code not in self._subscribed or self._ws is None:
            return
        payload = {
            "header": {
                "approval_key": self.approval_key,
                "custtype": "P",
                "tr_type": "2",
                "content-type": "utf-8",
            },
            "body": {
                "input": {"tr_id": "H0STCNT0", "tr_key": code}
            },
        }
        await self._ws.send(json.dumps(payload))
        self._subscribed.discard(code)

    async def _recv_loop(self):
        async for raw in self._ws:
            try:
                if raw[0] == "0":  # 실시간 데이터
                    self._parse_tick(raw)
                elif raw[0] == "{":  # JSON 응답 (구독 확인 등)
                    msg = json.loads(raw)
                    logger.debug(f"WS msg: {msg.get('header', {}).get('tr_id')}")
            except Exception as e:
                logger.error(f"WS parse error: {e}")

    def _parse_tick(self, raw: str):
        """H0STCNT0 실시간 체결 데이터 파싱"""
        # 포맷: 0|H0STCNT0|001|종목코드^시간^현재가^전일대비...
        parts = raw.split("|")
        if len(parts) < 4:
            return
        fields = parts[3].split("^")
        if len(fields) < 13:
            return
        tick = {
            "code": fields[0],
            "time": fields[1],
            "price": int(fields[2]),
            "volume": int(fields[12]),
            "cum_volume": int(fields[13]) if len(fields) > 13 else 0,
        }
        self.on_tick(tick)

    async def close(self):
        if self._ws:
            await self._ws.close()
