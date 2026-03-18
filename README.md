# openclaw-odoo-bridge

Python sidecar service that bridges Odoo mail notifications to an
[OpenClaw](https://github.com/nichochar/openclaw) bot gateway in real time.

## How it works

The bridge makes **outbound-only** connections to both services:

1. Authenticates with Odoo and connects to its WebSocket bus
2. Listens for mail notifications directed at the bot's partner
3. Forwards them to OpenClaw's `/hooks/agent` HTTP endpoint

Neither Odoo nor OpenClaw needs to be exposed to the internet.

## Setup

```bash
cp .env.example .env
# Edit .env with your Odoo and OpenClaw credentials

uv venv && uv pip install -e .
openclaw-odoo-bridge
```

## Configuration

All configuration is via environment variables (or `.env` file):

| Variable | Required | Description |
|----------|----------|-------------|
| `ODOO_URL` | Yes | Odoo base URL |
| `ODOO_DB` | Yes | Odoo database name |
| `ODOO_LOGIN` | Yes | Bot user login |
| `ODOO_PASSWORD` | Yes | Bot user password |
| `OPENCLAW_HOOKS_URL` | Yes | OpenClaw hooks endpoint |
| `OPENCLAW_HOOKS_TOKEN` | Yes | OpenClaw bearer token |
| `RECONNECT_DELAY` | No | Seconds between reconnects (default: 5) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |

## Development

```bash
uv pip install -e ".[dev]"
pytest
```

## License

LGPL-3.0
