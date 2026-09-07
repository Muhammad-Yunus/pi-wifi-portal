#!/bin/bash
# WiFi Portal Uninstaller
# Usage: sudo ./uninstall.sh

set -e

SERVICE_NAME="wifi-portal.service"
TARGET_DIR="/opt/wifi-portal"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

# ── Root Check ──────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "❌ Error: Please run as root (sudo $0)"
    exit 1
fi

echo "🗑️  Uninstalling WiFi Portal..."

# ── Stop & disable service ──────────────────────────────────
if systemctl is-active --quiet wifi-portal 2>/dev/null; then
    systemctl stop wifi-portal.service
    echo "✅ Service stopped"
else
    echo "ℹ️  Service not running"
fi

systemctl disable wifi-portal.service 2>/dev/null || true
echo "✅ Service disabled"

# ── Remove service file ─────────────────────────────────────
if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    echo "✅ Service file removed"
else
    echo "ℹ️  Service file not found"
fi

# ── Remove app directory ────────────────────────────────────
if [ -d "$TARGET_DIR" ]; then
    # Preserve backup if exists
    if [ -f "$TARGET_DIR/app.py.bak" ]; then
        echo "ℹ️  Backup found: $TARGET_DIR/app.py.bak"
    fi
    rm -rf "$TARGET_DIR"
    echo "✅ $TARGET_DIR removed"
fi

# ── Clean iptables rules ────────────────────────────────────
echo "🧹 Cleaning iptables rules..."
iptables -t nat -D PREROUTING -p tcp --dport 80 -j DNAT --to-destination 10.42.0.1:3001 2>/dev/null || true
iptables -t nat -D PREROUTING -p tcp --dport 53 -j DNAT --to-destination 10.42.0.1:53 2>/dev/null || true
iptables -t nat -D PREROUTING -p udp --dport 53 -j DNAT --to-destination 10.42.0.1:53 2>/dev/null || true
iptables -t nat -D POSTROUTING -s 10.42.0.0/24 -j MASQUERADE 2>/dev/null || true
echo "✅ iptables rules cleaned"

# ── Remove hotspot connection (if exists) ──────────────────
HOTSPOT_SSID=$(hostname)
nmcli connection show "$HOTSPOT_SSID" 2>/dev/null && \
    nmcli connection delete "$HOTSPOT_SSID" 2>/dev/null && \
    echo "✅ Hotspot connection removed" || \
    echo "ℹ️  Hotspot connection not found"

echo ""
echo "🎉 Uninstallation complete!"
