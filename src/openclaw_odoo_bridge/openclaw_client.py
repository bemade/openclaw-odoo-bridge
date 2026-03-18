from __future__ import annotations

import logging

import aiohttp

from .config import Config

_logger = logging.getLogger(__name__)


class OpenClawClient:
    """Async HTTP client for the OpenClaw /hooks/agent endpoint."""

    def __init__(self, config: Config) -> None:
        self._url = config.openclaw_hooks_url
        self._token = config.openclaw_hooks_token
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def send(
        self,
        message: str,
        session_key: str,
        idempotency_key: str,
        name: str = "Odoo",
    ) -> str | None:
        """POST a message to OpenClaw. Returns runId on success, None on failure."""
        assert self._session is not None
        payload = {
            "message": message,
            "name": name,
            "sessionKey": session_key,
            "idempotencyKey": idempotency_key,
        }
        try:
            async with self._session.post(
                self._url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                body = await resp.json()
                if resp.status == 200 and body.get("ok"):
                    run_id = body.get("runId")
                    _logger.info(
                        "Forwarded to OpenClaw (runId=%s, session=%s)",
                        run_id,
                        session_key,
                    )
                    return run_id
                _logger.warning(
                    "OpenClaw returned %s: %s",
                    resp.status,
                    body.get("error", body),
                )
                return None
        except Exception:
            _logger.warning(
                "Failed to POST to OpenClaw at %s",
                self._url,
                exc_info=True,
            )
            return None
