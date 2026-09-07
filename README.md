# 📶 Pi Wi-Fi Portal

> Ultra-lightweight captive portal for Raspberry Pi OS Bookworm — zero external dependencies, instant hotspot with Wi-Fi provisioning.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Raspberry Pi OS](https://img.shields.io/badge/Raspberry_Pi-Bookworm-green.svg)](https://www.raspberrypi.com/software/operating-systems/)
[![NetworkManager](https://img.shields.io/badge/NetworkManager-compatible-brightgreen.svg)](https://networkmanager.dev/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-success.svg)]()

---

## 📋 Description

Pi Wi-Fi Portal is a **minimal, self-contained captive portal** that runs on a Raspberry Pi and provides a simple web interface for connecting to Wi-Fi networks. When no Wi-Fi is connected, it automatically creates an open hotspot and serves a captive portal page where users can scan and connect to available networks.

### ✨ Key Features

- **Zero external dependencies** — uses only Python 3 standard library
- **Auto-hotspot** — creates open AP named after device hostname
- **Captive portal** — redirects all HTTP traffic to portal page
- **Wi-Fi provisioning** — scan & connect to any nearby network
- **Clean handoff** — shuts down portal when connection succeeds
- **Systemd integrated** — auto-starts on boot
- **Single-file HTML** — embedded UI, no build step required

---

## 🏗️ App Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Device                           │
│  (Phone/Laptop connecting to hotspot)                       │
│  └── Browser → http://10.42.0.1 (port 80)                  │
└────────────────────────┬────────────────────────────────────┘
                         │ DNAT (iptables)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Raspberry Pi                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              Systemd Service                          │ │
│  │         (wifi-portal.service)                         │ │
│  └───────────────────────┬───────────────────────────────┘ │
│                          │                                  │
│  ┌───────────────────────▼───────────────────────────────┐ │
│  │              Python Application                       │ │
│  │                  (app.py)                             │ │
│  │                                                       │ │
│  │  ┌───────────────────────────────────────────────┐   │ │
│  │  │           Network Manager Interface           │   │ │
│  │  │  ┌─────────┐  ┌──────────┐  ┌─────────────┐  │   │ │
│  │  │  │ensure   │  │  scan_   │  │ connect_to_ │  │   │ │
│  │  │  │hotspot()│  │networks()│  │network()    │  │   │ │
│  │  │  └─────────┘  └──────────┘  └─────────────┘  │   │ │
│  │  └───────────────────────────────────────────────┘   │ │
│  │                                                       │ │
│  │  ┌───────────────────────────────────────────────┐   │ │
│  │  │           HTTP Server (port 3001)             │   │ │
│  │  │  GET  /          → Portal HTML page           │   │ │
│  │  │  GET  /scan      → JSON list of networks      │   │ │
│  │  │  POST /connect   → Connect to WiFi            │   │ │
│  │  │  GET  /status    → Connection status          │   │ │
│  │  └───────────────────────────────────────────────┘   │ │
│  │                                                       │ │
│  │  ┌───────────────────────────────────────────────┐   │ │
│  │  │           iptables DNAT Rules                 │   │ │
│  │  │  port 80  → 10.42.0.1:3001 (portal)          │   │ │
│  │  │  port 53  → 10.42.0.1:53   (DNS)             │   │ │
│  │  └───────────────────────────────────────────────┘   │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Device connects to hotspot SSID
           │
           ▼
2. iptables DNAT: port 80 → 10.42.0.1:3001
           │
           ▼
3. Browser requests http://10.42.0.1
           │
           ▼
4. Python HTTP server serves portal page
           │
           ▼
5. User selects network → POST /connect
           │
           ▼
6. nmcli connects to target WiFi
           │
           ├─ Success → Shutdown portal → Exit
           │
           └─ Failed → Show error → Retry
```

---

## 📁 Project Structure

```
pi-wifi-manager/
├── app.py                    # Main application (captive portal + hotspot)
├── wifi-portal.service       # systemd service unit file
├── install.sh                # Automated installation script
├── uninstall.sh              # Automated removal script
├── .gitignore                # Git ignore patterns
└── .git/                     # Git repository
```

### Deployment Location

| File | Source | Destination |
|------|--------|-------------|
| `app.py` | Repo → `/home/pi/pi-wifi-manager/` | Deployed to `/opt/wifi-portal/` |
| `wifi-portal.service` | Repo → `/home/pi/pi-wifi-manager/` | Installed to `/etc/systemd/system/` |

---

## 🚀 How to Build

This project requires **no build step** — it's a pure Python application with a single embedded HTML file.

### Prerequisites

- Raspberry Pi (any model with WiFi)
- Raspberry Pi OS Bookworm (64-bit recommended)
- Python 3.11+
- NetworkManager
- Root access (via sudo)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/your-org/pi-wifi-manager.git
cd pi-wifi-manager

# Run installer (requires sudo)
sudo ./install.sh
```

### Manual Deploy

```bash
# Copy application to /opt
sudo mkdir -p /opt/wifi-portal
sudo cp app.py /opt/wifi-portal/app.py
sudo chown root:root /opt/wifi-portal/app.py
sudo chmod 755 /opt/wifi-portal/app.py

# Install systemd service
sudo cp wifi-portal.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start
sudo systemctl enable --now wifi-portal.service
```

---

## 📦 How to Install

### One-Command Install

```bash
# From the project directory
sudo ./install.sh
```

The install script will:
1. ✅ Create `/opt/wifi-portal/` directory
2. ✅ Backup existing `app.py` (if any)
3. ✅ Copy `app.py` from repo to `/opt/wifi-portal/`
4. ✅ Install systemd service
5. ✅ Enable service (starts on boot)
6. ✅ Start service
7. ✅ Verify installation

### Post-Install Verification

```bash
# Check service status
systemctl status wifi-portal.service

# Check port 3001 is listening
ss -tlnp | grep 3001

# View logs
journalctl -u wifi-portal -f
```

### Uninstall

```bash
sudo ./uninstall.sh
```

The uninstall script will:
1. ✅ Stop & disable service
2. ✅ Remove service file
3. ✅ Remove `/opt/wifi-portal/`
4. ✅ Clean iptables rules
5. ✅ Remove hotspot connection

---

## 🔧 Configuration

### Default Settings

| Setting | Value | Description |
|---------|-------|-------------|
| `HOST_IP` | `10.42.0.1` | Hotspot IP address |
| `_PORTAL_PORT` | `3001` | Portal HTTP port |
| `HOTSPOT_SSID` | `(hostname)` | Hotspot name = device hostname |

### Environment Variables

No environment variables required — all configuration is in `app.py`.

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Captive portal HTML page |
| `/scan` | GET | JSON list of nearby Wi-Fi networks |
| `/connect` | POST | Connect to a Wi-Fi network |
| `/status` | GET | Current connection status |

### Connect Request Body

```json
{
  "ssid": "MyNetwork",
  "password": "secret123"
}
```

### Status Response

```json
{
  "status": "success",
  "ip": "192.168.1.100"
}
```

---

## 🐛 Troubleshooting

### Service won't start

```bash
# Check logs
journalctl -u wifi-portal -n 50 --no-pager

# Check if port 3001 is free
ss -tlnp | grep 3001
```

### Hotspot not created

```bash
# Check NetworkManager status
nmcli dev status

# Check wlan0 availability
nmcli -t -f DEVICE,STATE dev show wlan0
```

### Portal not redirecting

```bash
# Check iptables rules
sudo iptables -t nat -L PREROUTING -n -v

# Flush and restart
sudo ./uninstall.sh && sudo ./install.sh
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- Built for **Raspberry Pi OS Bookworm** with NetworkManager
- No nginx dependency — pure Python HTTP server
- Single-file architecture for easy deployment
