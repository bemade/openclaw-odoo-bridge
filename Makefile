SERVICE    := openclaw-odoo-bridge
UNIT       := $(SERVICE).service
INSTALL_DIR := /opt/openclaw-odoo-bridge

.PHONY: install uninstall start stop restart status logs build

build:
	uv build

install: build
	id -u openclaw &>/dev/null || sudo useradd -r -s /usr/sbin/nologin openclaw
	sudo mkdir -p $(INSTALL_DIR)
	sudo python3 -m venv $(INSTALL_DIR)/.venv
	sudo $(INSTALL_DIR)/.venv/bin/pip install dist/*.whl --force-reinstall
	sudo test -f $(INSTALL_DIR)/.env || sudo cp .env.example $(INSTALL_DIR)/.env
	sudo chown -R openclaw:openclaw $(INSTALL_DIR)
	sudo cp $(UNIT) /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable --now $(SERVICE)

uninstall:
	sudo systemctl disable --now $(SERVICE) || true
	sudo rm -f /etc/systemd/system/$(UNIT)
	sudo systemctl daemon-reload

start:
	sudo systemctl start $(SERVICE)

stop:
	sudo systemctl stop $(SERVICE)

restart:
	sudo systemctl restart $(SERVICE)

status:
	sudo systemctl status $(SERVICE)

logs:
	journalctl -u $(SERVICE) -f
