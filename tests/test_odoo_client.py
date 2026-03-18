import pytest

from openclaw_odoo_bridge.config import Config
from openclaw_odoo_bridge.odoo_client import OdooClient, html_to_text


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
def client(config):
    c = OdooClient(config)
    c._partner_id = 42
    c._uid = 10
    return c


class TestHtmlToText:
    def test_simple_html(self):
        assert html_to_text("<p>Hello world</p>") == "Hello world"

    def test_nested_tags(self):
        assert html_to_text("<div><b>Bold</b> text</div>") == "Bold text"

    def test_empty(self):
        assert html_to_text("") == ""

    def test_plain_text(self):
        assert html_to_text("no html here") == "no html here"


class TestFormatMessage:
    def test_full_message(self, client):
        msg = {
            "id": 123,
            "body": "<p>Please review this</p>",
            "author_id": [5, "Alice"],
            "model": "project.task",
            "res_id": 42,
            "record_name": "Fix bug #99",
        }
        result = client.format_message(msg)
        assert result["message"] == (
            "[project.task: Fix bug #99]\nAlice: Please review this"
        )
        assert result["session_key"] == (
            "odoo:odoo.example.com:project.task:42"
        )
        assert result["idempotency_key"] == "123"
        assert "odoo.example.com" in result["name"]

    def test_message_without_record(self, client):
        msg = {
            "id": 456,
            "body": "<p>General note</p>",
            "author_id": [5, "Bob"],
            "model": "",
            "res_id": 0,
            "record_name": "",
        }
        result = client.format_message(msg)
        assert result["message"] == "Bob: General note"
        assert result["session_key"] == "odoo:odoo.example.com"

    def test_message_missing_author(self, client):
        msg = {
            "id": 789,
            "body": "<p>System message</p>",
            "author_id": False,
            "model": "sale.order",
            "res_id": 10,
            "record_name": "SO001",
        }
        result = client.format_message(msg)
        assert "Unknown:" in result["message"]
