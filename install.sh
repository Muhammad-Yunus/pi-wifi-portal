#!/bin/bash
# WiFi Portal Installer
# Usage: sudo ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="wifi-portal.service"
TARGET_DIR="/opt/wifi-portal"
APP_FILE="$TARGET_DIR/app.py"
BACKUP_FILE="$TARGET_DIR/app.py.bak"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

# ── Root Check ──────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "❌ Error: Please run as root (sudo $0)"
    exit 1
fi

echo "🚀 Installing WiFi Portal..."

# ── Backup existing app.py ──────────────────────────────────
if [ -f "$APP_FILE" ]; then
    cp "$APP_FILE" "$BACKUP_FILE"
    echo "✅ Backup created: $BACKUP_FILE"
else
    echo "ℹ️  No existing app.py found, skipping backup"
fi

# ── Create target directory ─────────────────────────────────
mkdir -p "$TARGET_DIR"
chown root:root "$TARGET_DIR"
echo "✅ Created $TARGET_DIR"

# ── Copy app.py from repo ───────────────────────────────────
cp "$SCRIPT_DIR/app.py" "$APP_FILE"
chown root:root "$APP_FILE"
chmod 755 "$APP_FILE"
echo "✅ Installed app.py"

# ── Install systemd service ─────────────────────────────────
if [ -f "$SERVICE_FILE" ]; then
    echo "⚠️  Service file already exists, backing up..."
    cp "$SERVICE_FILE" "${SERVICE_FILE}.bak"
fi

cp "$SCRIPT_DIR/wifi-portal.service" "$SERVICE_FILE"
systemctl daemon-reload
echo "✅ Installed systemd service"

# ── Enable & start service ──────────────────────────────────
systemctl enable wifi-portal.service
systemctl start wifi-portal.service
sleep 2

# ── Verify installation ─────────────────────────────────────
if systemctl is-active --quiet wifi-portal; then
    PORT_STATUS=$(ss -tlnp | grep -c ":3001 " || true)
    if [ "$PORT_STATUS" -gt 0 ]; then
        echo ""
        echo "🎉 Installation complete!"
        echo ""
        echo "   Status:   systemctl status wifi-portal"
        echo "   Logs:     journalctl -u wifi-portal -f"
        echo "   Port:     3001"
        echo "   Service:  enabled (starts on boot)"
        echo ""
        echo "   Hotspot SSID will be set to device hostname"
        exit 0
    else
        echo "⚠️  Service running but port 3001 not listening"
        journalctl -u wifi-portal -n 10
        exit 1
    fi
else
    echo "❌ Failed to start service"
    journalctl -u wifi-portal -n 20
    exit 1
fi
