import os

import pytest

from openclaw_odoo_bridge.config import Config


@pytest.fixture
def env_vars(monkeypatch):
    """Set all required env vars."""
    values = {
        "ODOO_URL": "https://odoo.example.com",
        "ODOO_DB": "testdb",
        "ODOO_LOGIN": "bot@example.com",
        "ODOO_PASSWORD": "secret",
        "OPENCLAW_HOOKS_URL": "http://localhost:18789/hooks/agent",
        "OPENCLAW_HOOKS_TOKEN": "tok-123",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return values


def test_from_env(env_vars):
    config = Config.from_env(dotenv_path=os.devnull)
    assert config.odoo_url == "https://odoo.example.com"
    assert config.odoo_db == "testdb"
    assert config.odoo_login == "bot@example.com"
    assert config.odoo_password == "secret"
    assert config.openclaw_hooks_url == "http://localhost:18789/hooks/agent"
    assert config.openclaw_hooks_token == "tok-123"
    assert config.reconnect_delay == 5.0
    assert config.log_level == "INFO"


def test_missing_required_var(monkeypatch):
    monkeypatch.delenv("ODOO_URL", raising=False)
    with pytest.raises(ValueError, match="ODOO_URL"):
        Config.from_env(dotenv_path=os.devnull)


def test_odoo_ws_url_https(env_vars):
    config = Config.from_env(dotenv_path=os.devnull)
    assert config.odoo_ws_url == "wss://odoo.example.com/websocket"


def test_odoo_ws_url_http(env_vars, monkeypatch):
    monkeypatch.setenv("ODOO_URL", "http://localhost:8069")
    config = Config.from_env(dotenv_path=os.devnull)
    assert config.odoo_ws_url == "ws://localhost:8069/websocket"


def test_odoo_hostname(env_vars):
    config = Config.from_env(dotenv_path=os.devnull)
    assert config.odoo_hostname == "odoo.example.com"


def test_trailing_slash_stripped(env_vars, monkeypatch):
    monkeypatch.setenv("ODOO_URL", "https://odoo.example.com/")
    config = Config.from_env(dotenv_path=os.devnull)
    assert config.odoo_url == "https://odoo.example.com"
