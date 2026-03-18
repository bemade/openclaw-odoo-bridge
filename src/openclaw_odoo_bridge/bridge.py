from __future__ import annotations

import asyncio
import collections
import logging
from typing import Any

from .config import Config
from .odoo_client import OdooClient
from .openclaw_client import OpenClawClient

_logger = logging.getLogger(__name__)


class Bridge:
    """Main orchestrator: Odoo bus → OpenClaw hooks."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._odoo = OdooClient(config)
        self._openclaw = OpenClawClient(config)
        # OrderedDict used as an ordered set — values are unused
        self._processed_message_ids: collections.OrderedDict[int, None] = (
            collections.OrderedDict()
        )
        # Cap the size to avoid unbounded growth
        self._max_processed = 10_000

    async def run(self) -> None:
        """Main loop with automatic reconnection."""
        await self._openclaw.connect()
        while True:
            try:
                await self._odoo.connect()
                try:
                    await self._catch_up()
                    await self._listen()
                finally:
                    await self._odoo.close()
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.warning(
                    "Connection error, reconnecting in %ss",
                    self._config.reconnect_delay,
                    exc_info=True,
                )
            await asyncio.sleep(self._config.reconnect_delay)

    async def shutdown(self) -> None:
        """Cleanly close connections."""
        await self._odoo.close()
        await self._openclaw.close()
        _logger.info("Shutdown complete")

    async def _catch_up(self) -> None:
        """Process any unread notifications from while we were disconnected."""
        _logger.info("Catching up on unread notifications...")
        messages, notif_ids = await self._odoo.get_unread_notifications()
        for msg in messages:
            await self._forward_message(msg)
        if messages:
            _logger.info("Caught up on %d unread messages", len(messages))
            await self._odoo.mark_notifications_read(notif_ids)

    async def _listen(self) -> None:
        """Listen via WebSocket and poll concurrently."""
        ws_task = asyncio.create_task(self._listen_ws())
        poll_task = asyncio.create_task(self._poll_loop())
        try:
            # If either task fails, cancel the other
            done, pending = await asyncio.wait(
                [ws_task, poll_task],
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()  # re-raise any exception
        except asyncio.CancelledError:
            ws_task.cancel()
            poll_task.cancel()
            raise

    async def _listen_ws(self) -> None:
        """Listen to Odoo WebSocket bus and forward relevant notifications."""
        async for batch in self._odoo.listen_bus():
            for notif in batch:
                await self._process_notification(notif)

    async def _poll_loop(self) -> None:
        """Periodically poll for unread notifications as a fallback."""
        while True:
            await asyncio.sleep(self._config.poll_interval)
            try:
                messages, notif_ids = (
                    await self._odoo.get_unread_notifications()
                )
                for msg in messages:
                    await self._forward_message(msg)
                if messages:
                    _logger.debug("Poll found %d new messages", len(messages))
                    await self._odoo.mark_notifications_read(notif_ids)
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.warning("Poll error", exc_info=True)

    async def _process_notification(self, notif: dict[str, Any]) -> None:
        """Filter and forward a single bus notification."""
        message_data = notif.get("message", {})
        notif_type = message_data.get("type", "")

        # We care about new messages appearing in threads
        if notif_type != "mail.record/insert":
            return

        payload = message_data.get("payload", {})
        await self._process_mail_record_insert(payload)

    async def _process_mail_record_insert(
        self, payload: dict[str, Any]
    ) -> None:
        """Extract message data from a mail.record/insert notification."""
        # The payload structure varies — messages can be nested in Thread
        # or appear directly. We look for Message entries.
        messages = payload.get("Message", {})

        if isinstance(messages, dict):
            # Odoo sends {id: {fields...}} or [{fields...}]
            items = messages.values() if messages else []
        elif isinstance(messages, list):
            items = messages
        else:
            return

        for msg_data in items:
            if not isinstance(msg_data, dict):
                continue
            msg_id = msg_data.get("id")
            if not msg_id:
                continue

            # Skip messages we've already forwarded
            if msg_id in self._processed_message_ids:
                continue

            # Skip messages authored by the bot itself
            author = msg_data.get("author")
            if isinstance(author, dict) and author.get("id") == self._odoo.partner_id:
                continue

            # Fetch full message details via RPC since bus payload is partial
            full_messages = await self._odoo.call(
                "mail.message",
                "search_read",
                [[("id", "=", msg_id)]],
                {
                    "fields": [
                        "body",
                        "author_id",
                        "model",
                        "res_id",
                        "record_name",
                    ],
                },
            )
            if full_messages:
                await self._forward_message(full_messages[0])

    async def _forward_message(self, msg: dict[str, Any]) -> None:
        """Format and send a message to OpenClaw."""
        msg_id = msg.get("id")
        if msg_id and msg_id in self._processed_message_ids:
            return

        formatted = self._odoo.format_message(msg)
        if not formatted["message"].strip():
            return

        await self._openclaw.send(
            message=formatted["message"],
            session_key=formatted["session_key"],
            idempotency_key=formatted["idempotency_key"],
            name=formatted["name"],
        )

        if msg_id:
            self._processed_message_ids[msg_id] = None
            # Evict oldest entries if over capacity
            while len(self._processed_message_ids) > self._max_processed:
                self._processed_message_ids.popitem(last=False)
