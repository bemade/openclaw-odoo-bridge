from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    odoo_url: str
    odoo_db: str
    odoo_login: str
    odoo_password: str
    openclaw_hooks_url: str
    openclaw_hooks_token: str
    reconnect_delay: float = 5.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = None) -> Config:
        load_dotenv(dotenv_path)

        def _require(key: str) -> str:
            value = os.environ.get(key, "").strip()
            if not value:
                raise ValueError(f"Missing required environment variable: {key}")
            return value

        return cls(
            odoo_url=_require("ODOO_URL").rstrip("/"),
            odoo_db=_require("ODOO_DB"),
            odoo_login=_require("ODOO_LOGIN"),
            odoo_password=_require("ODOO_PASSWORD"),
            openclaw_hooks_url=_require("OPENCLAW_HOOKS_URL"),
            openclaw_hooks_token=_require("OPENCLAW_HOOKS_TOKEN"),
            reconnect_delay=float(os.environ.get("RECONNECT_DELAY", "5")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )

    @property
    def odoo_hostname(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.odoo_url).hostname or self.odoo_url

    @property
    def odoo_ws_url(self) -> str:
        url = self.odoo_url
        if url.startswith("https://"):
            return "wss://" + url[8:] + "/websocket"
        if url.startswith("http://"):
            return "ws://" + url[7:] + "/websocket"
        return "wss://" + url + "/websocket"
