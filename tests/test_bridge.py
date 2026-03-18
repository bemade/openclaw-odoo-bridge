from unittest.mock import AsyncMock, patch

import pytest

from openclaw_odoo_bridge.bridge import Bridge
from openclaw_odoo_bridge.config import Config


@pytest.fixture
def config():
    return Config(
        odoo_url="https://odoo.example.com",
        odoo_db="testdb",
        odoo_login="bot@example.com",
        odoo_password="secret",
        openclaw_hooks_url="http://localhost:18789/hooks/agent",
        openclaw_hooks_token="tok-123",
        reconnect_delay=0.01,
    )


@pytest.fixture
def bridge(config):
    b = Bridge(config)
    b._odoo._partner_id = 42
    b._odoo._uid = 10
    return b


class TestProcessNotification:
    async def test_ignores_non_mail_notifications(self, bridge):
        bridge._openclaw.send = AsyncMock()
        await bridge._process_notification({
            "id": 1,
            "message": {"type": "bus.bus/im_status_updated", "payload": {}},
        })
        bridge._openclaw.send.assert_not_called()

    async def test_forwards_mail_record_insert(self, bridge):
        bridge._openclaw.send = AsyncMock(return_value="run-1")
        bridge._odoo.call = AsyncMock(return_value=[{
            "id": 100,
            "body": "<p>Hello bot</p>",
            "author_id": [5, "Alice"],
            "model": "project.task",
            "res_id": 7,
            "record_name": "Task #7",
        }])
        await bridge._process_notification({
            "id": 2,
            "message": {
                "type": "mail.record/insert",
                "payload": {
                    "Message": {"100": {"id": 100, "author": {"id": 5}}},
                },
            },
        })
        bridge._openclaw.send.assert_called_once()
        call_kwargs = bridge._openclaw.send.call_args[1]
        assert "Hello bot" in call_kwargs["message"]
        assert "project.task" in call_kwargs["session_key"]

    async def test_skips_bot_own_messages(self, bridge):
        bridge._openclaw.send = AsyncMock()
        await bridge._process_notification({
            "id": 3,
            "message": {
                "type": "mail.record/insert",
                "payload": {
                    "Message": {
                        "200": {"id": 200, "author": {"id": 42}},
                    },
                },
            },
        })
        # Bot's own message (partner_id=42) should be skipped
        bridge._openclaw.send.assert_not_called()

    async def test_dedup_same_message(self, bridge):
        bridge._openclaw.send = AsyncMock(return_value="run-1")
        bridge._odoo.call = AsyncMock(return_value=[{
            "id": 300,
            "body": "<p>Dedup test</p>",
            "author_id": [5, "Alice"],
            "model": "res.partner",
            "res_id": 1,
            "record_name": "Test",
        }])
        notif = {
            "id": 4,
            "message": {
                "type": "mail.record/insert",
                "payload": {
                    "Message": {"300": {"id": 300, "author": {"id": 5}}},
                },
            },
        }
        await bridge._process_notification(notif)
        await bridge._process_notification(notif)
        # Should only forward once
        bridge._openclaw.send.assert_called_once()


class TestCatchUp:
    async def test_catch_up_forwards_unread(self, bridge):
        bridge._odoo.get_unread_notifications = AsyncMock(return_value=[
            {
                "id": 50,
                "body": "<p>Missed message</p>",
                "author_id": [3, "Bob"],
                "model": "sale.order",
                "res_id": 5,
                "record_name": "SO005",
            },
        ])
        bridge._openclaw.send = AsyncMock(return_value="run-2")
        await bridge._catch_up()
        bridge._openclaw.send.assert_called_once()
        assert "Missed message" in bridge._openclaw.send.call_args[1]["message"]

    async def test_catch_up_empty(self, bridge):
        bridge._odoo.get_unread_notifications = AsyncMock(return_value=[])
        bridge._openclaw.send = AsyncMock()
        await bridge._catch_up()
        bridge._openclaw.send.assert_not_called()
