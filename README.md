# 📶 Pi Wi-Fi Portal

> **Zero-dependency captive portal** for Raspberry Pi — auto-hotspot, web provisioning, clean handoff.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry_Pi-Bookworm-DC042D?logo=raspberry-pi)](https://www.raspberrypi.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen)]()
[![Stars](https://img.shields.io/github/stars/placeholder/pi-wifi-manager?style=social)]()

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🚀 **Zero Dependencies** | Pure Python 3 stdlib — no pip install needed |
| 📡 **Auto Hotspot** | Creates open AP named after device hostname |
| 🌐 **Captive Portal** | Redirects all HTTP traffic to provisioning page |
| 🔍 **WiFi Scanner** | Scan & connect to any nearby network |
| 🔄 **Clean Handoff** | Shuts down portal when connection succeeds |
| ⚡ **Systemd Integrated** | Auto-starts on boot via service |

---

## 🏗️ Architecture

```
┌─────────────┐     DNAT       ┌──────────────────┐
│   Client    │ ──────────▶    │  Raspberry Pi    │
│  Device     │  :80 → :3001   │  (10.42.0.1)     │
└─────────────┘                └──────────────────┘
                                  │
                     ┌────────────┼────────────┐
                     ▼            ▼            ▼
               ┌──────────┐  ┌─────────┐  ┌──────────┐
               │ Portal   │  │iptables │  │ nmcli    │
               │ Server   │  │  Rules  │  │  WiFi    │
               │ (3001)   │  │         │  │ Manager  │
               └──────────┘  └─────────┘  └──────────┘
```

### Data Flow

```
1. Device connects to hotspot SSID
        │
        ▼
2. iptables DNAT: port 80 → 10.42.0.1:3001
        │
        ▼
3. Browser → Captive Portal HTML
        │
        ▼
4. User scans networks → selects WiFi
        │
        ▼
5. POST /connect → nmcli connects
        │
        ├── Success → Shutdown portal → Done
        └── Failed  → Show error → Retry
```

---

## 📁 Project Structure

```
pi-wifi-manager/
├── app.py                  # Main application (captive portal + hotspot)
├── wifi-portal.service     # systemd service unit
├── install.sh              # One-command installer
├── uninstall.sh            # One-command remover
├── .gitignore
└── README.md
```

---

## 🚀 Quick Start

### Install

```bash
git clone https://github.com/your-org/pi-wifi-manager.git
cd pi-wifi-manager
sudo ./install.sh
```

### Uninstall

```bash
sudo ./uninstall.sh
```

---

## 🔧 Manual Install

```bash
# Deploy application
sudo mkdir -p /opt/wifi-portal
sudo cp app.py /opt/wifi-portal/app.py
sudo chown root:root /opt/wifi-portal/app.py
sudo chmod 755 /opt/wifi-portal/app.py

# Install systemd service
sudo cp wifi-portal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wifi-portal.service
```

---

## 🌐 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Captive portal page |
| `/scan` | GET | JSON list of nearby networks |
| `/connect` | POST | Connect to a network |
| `/status` | GET | Connection status |

### POST /connect Payload

```json
{
  "ssid": "MyNetwork",
  "password": "secret123"
}
```

### GET /status Response

```json
{
  "status": "success",
  "ip": "192.168.1.100"
}
```

---

## 🔌 Default Configuration

| Setting | Value |
|---------|-------|
| Hotspot IP | `10.42.0.1` |
| Portal Port | `3001` |
| Hotspot SSID | Device hostname |

---

## 🐛 Troubleshooting

```bash
# Check service status
systemctl status wifi-portal.service

# View logs
journalctl -u wifi-portal -f

# Check iptables rules
sudo iptables -t nat -L PREROUTING -n -v

# Verify port listening
ss -tlnp \| grep 3001
```

---

## 📄 License

MIT — See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

Built for **Raspberry Pi OS Bookworm** with zero external dependencies.

---

<div align="center">

**Made with ❤️ for Raspberry Pi enthusiasts**

</div>
