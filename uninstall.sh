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

# Identify rules to delete
echo "🔍 Identifying hotspot iptables rules..."
RULES=$(iptables -t nat -S PREROUTING 2>/dev/null | grep -E "(to:10\.42\.0\.1:3001|to:10\.42\.0\.1:53)" || true)
RULES_POST=$(iptables -t nat -S POSTROUTING 2>/dev/null | grep -E "10\.42\.0\.0/24.*MASQUERADE" || true)

if [ -n "$RULES" ] || [ -n "$RULES_POST" ]; then
    echo "📋 Found rules to delete:"
    [ -n "$RULES" ] && echo "  PREROUTING: $RULES"
    [ -n "$RULES_POST" ] && echo "  POSTROUTING: $RULES_POST"
    
    # Delete identified rules
    echo "🗑️  Deleting identified rules..."
    DELETED=0
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            # Convert -A to -D
            DELETE_LINE=$(echo "$line" | sed 's/^-A/-D/')
            CHAIN=$(echo "$DELETE_LINE" | awk '{print $2}')
            RULE=$(echo "$DELETE_LINE" | cut -d' ' -f3-)
            iptables -t "$CHAIN" -D $RULE 2>/dev/null && echo "  ✓ Deleted: $RULE" && DELETED=$((DELETED+1)) || echo "  ✗ Failed: $RULE"
        fi
    done <<< "$RULES"
    
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            DELETE_LINE=$(echo "$line" | sed 's/^-A/-D/')
            CHAIN=$(echo "$DELETE_LINE" | awk '{print $2}')
            RULE=$(echo "$DELETE_LINE" | cut -d' ' -f3-)
            iptables -t "$CHAIN" -D $RULE 2>/dev/null && echo "  ✓ Deleted: $RULE" && DELETED=$((DELETED+1)) || echo "  ✗ Failed: $RULE"
        fi
    done <<< "$RULES_POST"
    
    # Verify cleanup
    echo "✅ Verifying cleanup..."
    REMAINING=$(iptables -t nat -S PREROUTING 2>/dev/null | grep -E "(to:10\.42\.0\.1:3001|to:10\.42\.0\.1:53)" || true)
    REMAINING_POST=$(iptables -t nat -S POSTROUTING 2>/dev/null | grep -E "10\.42\.0\.0/24.*MASQUERADE" || true)
    
    if [ -n "$REMAINING" ] || [ -n "$REMAINING_POST" ]; then
        echo "⚠️  WARNING: Some rules still remain, falling back to force flush..."
        iptables -t nat -F PREROUTING 2>/dev/null || true
        iptables -t nat -F POSTROUTING 2>/dev/null || true
        echo "✅ Force flush completed"
    else
        echo "✅ Cleanup verified: $DELETED rules removed"
    fi
else
    echo "ℹ️  No hotspot rules found"
fi

echo "✅ iptables rules cleaned"

# ── Remove hotspot connection (if exists) ──────────────────
HOTSPOT_SSID=$(hostname)
nmcli connection show "$HOTSPOT_SSID" 2>/dev/null && \
    nmcli connection delete "$HOTSPOT_SSID" 2>/dev/null && \
    echo "✅ Hotspot connection removed" || \
    echo "ℹ️  Hotspot connection not found"

echo ""
echo "🎉 Uninstallation complete!"
