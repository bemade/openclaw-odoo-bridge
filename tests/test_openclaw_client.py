import pytest
from aioresponses import aioresponses

from openclaw_odoo_bridge.config import Config
from openclaw_odoo_bridge.openclaw_client import OpenClawClient


@pytest.fixture
def config():
    return Config(
        odoo_url="https://odoo.example.com",
        odoo_db="testdb",
        odoo_login="bot@example.com",
        odoo_password="secret",
        openclaw_hooks_url="http://localhost:18789/hooks/agent",
        openclaw_hooks_token="tok-123",
    )


@pytest.fixture
async def client(config):
    c = OpenClawClient(config)
    await c.connect()
    yield c
    await c.close()


async def test_send_success(client):
    with aioresponses() as m:
        m.post(
            "http://localhost:18789/hooks/agent",
            payload={"ok": True, "runId": "run-abc"},
        )
        run_id = await client.send(
            message="Hello bot",
            session_key="odoo:example:res.partner:1",
            idempotency_key="msg_1",
            name="Odoo (example)",
        )
        assert run_id == "run-abc"


async def test_send_error_response(client):
    with aioresponses() as m:
        m.post(
            "http://localhost:18789/hooks/agent",
            status=400,
            payload={"ok": False, "error": "message required"},
        )
        run_id = await client.send(
            message="",
            session_key="odoo:example:res.partner:1",
            idempotency_key="msg_2",
        )
        assert run_id is None


async def test_send_network_error(client):
    with aioresponses() as m:
        m.post(
            "http://localhost:18789/hooks/agent",
            exception=ConnectionError("down"),
        )
        run_id = await client.send(
            message="test",
            session_key="odoo:example:res.partner:1",
            idempotency_key="msg_3",
        )
        assert run_id is None


async def test_send_headers(client):
    with aioresponses() as m:
        m.post(
            "http://localhost:18789/hooks/agent",
            payload={"ok": True, "runId": "run-xyz"},
        )
        await client.send(
            message="test",
            session_key="s",
            idempotency_key="k",
        )
        # Find the POST request in the captured requests
        for key, calls in m.requests.items():
            method, url = key
            if method == "POST" and "hooks/agent" in str(url):
                assert calls[0].kwargs["headers"]["Authorization"] == "Bearer tok-123"
                return
        pytest.fail("No POST request found to hooks/agent")
