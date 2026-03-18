from __future__ import annotations

import asyncio
import json
import logging
from html.parser import HTMLParser
from typing import Any, AsyncIterator

import aiohttp
import websockets
import websockets.asyncio.client

from .config import Config

_logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 50  # seconds — Odoo times out idle connections at 60s


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML-to-text converter."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def html_to_text(html: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()


class OdooClient:
    """Async Odoo JSON-RPC + WebSocket bus client."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._partner_id: int | None = None
        self._uid: int | None = None
        self._last_notif_id: int = 0

    async def connect(self) -> None:
        """Create HTTP session and authenticate."""
        self._session = aiohttp.ClientSession()
        await self._authenticate()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def _authenticate(self) -> None:
        """Authenticate via JSON-RPC and store session cookie."""
        result = await self._jsonrpc("/web/session/authenticate", {
            "db": self._config.odoo_db,
            "login": self._config.odoo_login,
            "password": self._config.odoo_password,
        })
        self._uid = result.get("uid")
        if not self._uid:
            raise RuntimeError("Odoo authentication failed — check credentials")
        self._partner_id = result.get("partner_id")
        _logger.info(
            "Authenticated as uid=%s partner_id=%s",
            self._uid,
            self._partner_id,
        )

    @property
    def partner_id(self) -> int:
        if self._partner_id is None:
            raise RuntimeError("Not authenticated")
        return self._partner_id

    async def _jsonrpc(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a JSON-RPC call to Odoo."""
        assert self._session is not None
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "id": 1,
            "params": params or {},
        }
        url = self._config.odoo_url + path
        async with self._session.post(url, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
        if "error" in data:
            err = data["error"]
            msg = err.get("data", {}).get("message", err.get("message", str(err)))
            raise RuntimeError(f"Odoo JSON-RPC error: {msg}")
        return data.get("result", {})

    async def call(
        self,
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Call an Odoo model method via JSON-RPC."""
        return await self._jsonrpc("/web/dataset/call_kw", {
            "model": model,
            "method": method,
            "args": args or [],
            "kwargs": kwargs or {},
        })

    async def get_unread_notifications(self) -> list[dict[str, Any]]:
        """Fetch unread mail.notification records for the bot's partner."""
        notif_ids = await self.call(
            "mail.notification",
            "search_read",
            [[
                ("res_partner_id", "=", self.partner_id),
                ("is_read", "=", False),
            ]],
            {"fields": ["mail_message_id"], "limit": 100},
        )
        if not notif_ids:
            return []
        message_ids = list({n["mail_message_id"][0] for n in notif_ids})
        messages = await self.call(
            "mail.message",
            "search_read",
            [[("id", "in", message_ids)]],
            {
                "fields": [
                    "body",
                    "author_id",
                    "model",
                    "res_id",
                    "record_name",
                    "date",
                ],
            },
        )
        return messages

    async def listen_bus(self) -> AsyncIterator[list[dict[str, Any]]]:
        """Connect to Odoo WebSocket bus and yield notification batches."""
        assert self._session is not None
        cookies = {
            key: morsel.value
            for key, morsel in self._session.cookie_jar.filter_cookies(
                self._config.odoo_url
            ).items()
        }
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())

        async for ws in websockets.asyncio.client.connect(
            self._config.odoo_ws_url,
            additional_headers={"Cookie": cookie_header},
        ):
            try:
                # Subscribe — Odoo auto-adds the user's partner channel
                subscribe_msg = json.dumps({
                    "event_name": "subscribe",
                    "data": {
                        "channels": [],
                        "last": self._last_notif_id,
                    },
                })
                await ws.send(subscribe_msg)
                _logger.info(
                    "WebSocket connected, subscribed (last=%d)",
                    self._last_notif_id,
                )

                # Start heartbeat task
                heartbeat_task = asyncio.create_task(
                    self._heartbeat(ws)
                )
                try:
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            # Pong or heartbeat response — ignore
                            continue
                        notifications = json.loads(raw)
                        if not isinstance(notifications, list):
                            continue
                        if notifications:
                            self._last_notif_id = max(
                                n["id"] for n in notifications
                            )
                        yield notifications
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
            except websockets.ConnectionClosed:
                _logger.warning("WebSocket connection closed, will reconnect")
                continue

    @staticmethod
    async def _heartbeat(
        ws: websockets.asyncio.client.ClientConnection,
    ) -> None:
        """Send periodic heartbeat to prevent Odoo from closing the connection."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await ws.send(b"\x00")
            except websockets.ConnectionClosed:
                return

    def format_message(self, msg: dict[str, Any]) -> dict[str, str]:
        """Format an Odoo mail.message dict into bridge payload fields."""
        body_plain = html_to_text(msg.get("body", ""))
        author = (
            msg["author_id"][1]
            if isinstance(msg.get("author_id"), (list, tuple))
            else "Unknown"
        )
        record_name = msg.get("record_name") or ""
        res_model = msg.get("model") or ""
        res_id = msg.get("res_id") or ""

        parts = []
        if record_name and res_model:
            parts.append(f"[{res_model}: {record_name}]")
        parts.append(f"{author}: {body_plain}")

        session_parts = ["odoo", self._config.odoo_hostname]
        if res_model:
            session_parts.append(res_model)
        if res_id:
            session_parts.append(str(res_id))

        return {
            "message": "\n".join(parts),
            "session_key": ":".join(session_parts),
            "idempotency_key": str(msg.get("id", "")),
            "name": f"Odoo ({self._config.odoo_hostname})",
        }
