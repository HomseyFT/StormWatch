#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Creating virtual environment..."
python3 -m venv .venv

echo "==> Installing dependencies..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

if command -v systemctl &>/dev/null && systemctl --user status &>/dev/null 2>&1; then
    echo "==> Installing systemd user service..."
    mkdir -p ~/.config/systemd/user
    cp stormwatch.service ~/.config/systemd/user/stormwatch.service
    systemctl --user daemon-reload
    echo "    Run: systemctl --user enable --now stormwatch"
else
    echo "==> Systemd not available — run manually: .venv/bin/python main.py"
fi

echo "==> Done. Edit config.toml before first run."
