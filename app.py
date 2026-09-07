#!/usr/bin/env python3
"""Ultra-light Wi-Fi Captive Portal for Raspberry Pi OS Bookworm.

Zero external dependencies — uses only Python 3 standard library.
"""

import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST_IP = "10.42.0.1"
HOTSPOT_SSID = None  # set at startup from hostname
_PORTAL_PORT = 3001  # Captive portal runs on port 3001 (no port 80)

# Global server reference for handoff
_server_instance = None


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "command timed out"
    except Exception as e:
        return 1, "", str(e)


def get_hostname() -> str:
    return socket.gethostname()


def _wait_nm_ready(retries: int = 20, delay: float = 0.5) -> bool:
    """Wait until NetworkManager reports wifi device is available."""
    for _ in range(retries):
        code, out, _ = _run(["nmcli", "-t", "-f", "TYPE,STATE", "dev"], timeout=3)
        if code == 0 and "wifi" in out:
            return True
        time.sleep(delay)
    return False


def _is_wifi_connected_to_ap() -> bool:
    """Check if wlan0 is connected to an infrastructure AP (not hotspot)."""
    code, out, _ = _run(["nmcli", "-t", "-f", "NAME,DEVICE",
                          "connection", "show", "--active"], timeout=5)
    if code != 0:
        return False
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] == "wlan0" and parts[0] != HOTSPOT_SSID:
            # Check if it's AP mode (hotspot) or infrastructure (client)
            code2, out2, _ = _run(["nmcli", "-t", "-f",
                                    "802-11-wireless.mode",
                                    "connection", "show", parts[0]], timeout=5)
            if code2 == 0 and out2.strip() and out2.strip() != "ap":
                return True
    return False


def _is_hotspot_active() -> bool:
    """Check whether our hotspot connection is active on wlan0."""
    code, out, _ = _run(["nmcli", "-t", "-f", "NAME,DEVICE",
                          "connection", "show", "--active"], timeout=5)
    if code != 0:
        return False
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == HOTSPOT_SSID and parts[1] == "wlan0":
            return True
    return False


def ensure_hotspot() -> bool:
    """Create an open hotspot if wlan0 is not connected to any infrastructure AP.
    Returns True if hotspot is active (or was already active).
    """
    global HOTSPOT_SSID
    HOTSPOT_SSID = get_hostname()

    # Already running with our exact SSID?
    code, out, _ = _run(["nmcli", "-t", "-f", "NAME",
                          "connection", "show", "--active"], timeout=5)
    if code == 0:
        for line in out.splitlines():
            name = line.strip()
            if not name or name == "lo":
                continue
            # Check if this active connection has our SSID and is AP mode
            code2, out2, _ = _run(["nmcli", "-t", "-f",
                                    "802-11-wireless.ssid,802-11-wireless.mode",
                                    "connection", "show", name], timeout=5)
            if code2 == 0:
                parts = out2.strip().split(":")
                if len(parts) >= 2 and parts[0] == HOTSPOT_SSID and parts[1] == "ap":
                    print(f"[wifi-portal] Hotspot '{HOTSPOT_SSID}' already active.",
                          flush=True)
                    return True

    # Wait for NM to be ready
    if not _wait_nm_ready():
        print("[wifi-portal] ERROR: NetworkManager not ready after 10s", flush=True)
        return False

    # Kill any stale connection on wlan0 FIRST (before checking state)
    code2, out2, _ = _run(["nmcli", "-t", "-f", "NAME,DEVICE",
                            "connection", "show", "--active"], timeout=5)
    if code2 == 0:
        for line in out2.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "wlan0" and parts[0] != HOTSPOT_SSID:
                print(f"[wifi-portal] Stopping stale connection '{parts[0]}'.",
                      flush=True)
                _run(["nmcli", "connection", "down", parts[0]])
                time.sleep(1)

    # Re-check after cleanup
    time.sleep(2)
    code3, out3, _ = _run(["nmcli", "-t", "-f", "TYPE,STATE", "dev"], timeout=5)
    wifi_connected = False
    if code3 == 0:
        for line in out3.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[0] == "wifi":
                if parts[1] == "connected":
                    wifi_connected = True
                break

    if wifi_connected:
        print("[wifi-portal] WARNING: wlan0 is connected to an AP, hotspot not created.",
              flush=True)
        return False

    # --- Create OPEN hotspot (Method 2: manual connection) ---
    # Clean up any stale profile first
    _run(["nmcli", "connection", "delete", HOTSPOT_SSID])
    _run(["nmcli", "connection", "delete", "Hotspot"])
    time.sleep(1)

    code, _, err2 = _run([
        "nmcli", "connection", "add",
        "type", "wifi", "ifname", "wlan0",
        "con-name", HOTSPOT_SSID,
        "autoconnect", "no",
        "wifi.ssid", HOTSPOT_SSID,
        "wifi.mode", "ap",
        "ipv4.method", "shared",
        "ipv6.method", "ignore",
    ], timeout=10)
    if code != 0:
        print(f"[wifi-portal] ERROR creating connection: {err2.strip()}", flush=True)
        return False

    code3, _, err3 = _run([
        "nmcli", "connection", "up", HOTSPOT_SSID
    ], timeout=15)
    if code3 != 0:
        print(f"[wifi-portal] ERROR bringing up hotspot: {err3.strip()}", flush=True)
        return False

    # Patch to open (no security)
    _run(["nmcli", "connection", "modify", HOTSPOT_SSID,
          "802-11-wireless-security.key-mgmt", "none"])

    # Add iptables DNAT rules for captive portal
    print("[wifi-portal] Adding iptables DNAT rules for hotspot...", flush=True)
    _run(["iptables", "-t", "nat", "-A", "PREROUTING", "-p", "tcp",
          "--dport", "80", "-j", "DNAT", "--to-destination", f"{HOST_IP}:{_PORTAL_PORT}"])
    _run(["iptables", "-t", "nat", "-A", "PREROUTING", "-p", "tcp",
          "--dport", "53", "-j", "DNAT", "--to-destination", f"{HOST_IP}:53"])
    _run(["iptables", "-t", "nat", "-A", "PREROUTING", "-p", "udp",
          "--dport", "53", "-j", "DNAT", "--to-destination", f"{HOST_IP}:53"])
    _run(["iptables", "-t", "nat", "-A", "POSTROUTING",
          "-s", "10.42.0.0/24", "-j", "MASQUERADE"])

    # Validate: confirm key-mgmt is actually none
    time.sleep(1)
    code4, out4, _ = _run(["nmcli", "-t", "-f",
                           "802-11-wireless-security.key-mgmt",
                           "connection", "show", HOTSPOT_SSID], timeout=5)
    if code4 == 0 and "none" not in out4.lower():
        print("[wifi-portal] WARNING: hotspot still has security, re-patching…",
              flush=True)
        _run(["nmcli", "connection", "down", HOTSPOT_SSID])
        time.sleep(1)
        _run(["nmcli", "connection", "modify", HOTSPOT_SSID,
              "802-11-wireless-security.key-mgmt", "none"])
        _run(["nmcli", "connection", "up", HOTSPOT_SSID])
        time.sleep(1)

    # Wait until hotspot is confirmed active
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(1)
        if _is_hotspot_active():
            print(f"[wifi-portal] Hotspot '{HOTSPOT_SSID}' is OPEN and active.",
                  flush=True)
            return True
    print("[wifi-portal] ERROR: hotspot did not become active in time.",
          flush=True)
    return False


def scan_networks() -> list[dict]:
    """Return list of nearby Wi-Fi networks as dicts."""
    _run(["nmcli", "dev", "wifi", "rescan"])
    time.sleep(1)
    code, out, err = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY",
                            "dev", "wifi", "list"], timeout=10)
    if code != 0:
        print(f"[wifi-portal] scan error: {err.strip()}", flush=True)
        return []
    networks = []
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            ssid_raw = parts[0]
            # nmcli escapes colons in SSIDs as \:
            ssid = ssid_raw.replace("\\:", ":")
            signal = parts[1]
            security = parts[2] if parts[2] else "Open"
            networks.append({"ssid": ssid, "signal": signal, "sec": security})
    return networks


def connect_to_network(ssid: str, password: str) -> dict:
    """Attempt to connect; returns status dict. Restores hotspot on failure."""
    global HOTSPOT_SSID

    # NOTE: Don't tear down hotspot yet! Keep it running so the client
    # device stays connected to the portal while we attempt the WiFi connection.
    # Only remove hotspot AFTER successful connection.

    code, out, err = _run(["nmcli", "dev", "wifi", "connect", ssid,
                            "password", password], timeout=45)
    if code != 0:
        # Connection failed — hotspot still running, user can retry
        return {"status": "failed", "error": err.strip()[:120]}

    # Poll for IP for up to 20 seconds
    deadline = time.time() + 20
    ip = None
    while time.time() < deadline:
        time.sleep(1)
        code2, out2, _ = _run(["nmcli", "-g", "IP4.ADDRESS",
                                "device", "show", "wlan0"], timeout=5)
        if code2 == 0 and out2.strip():
            addr = out2.strip().split("/")[0]
            if addr and addr not in ("0.0.0.0", ""):
                ip = addr
                break

    if ip:
        # Success! Now tear down hotspot so wlan0 can be used for internet
        _run(["nmcli", "connection", "delete", HOTSPOT_SSID or "Hotspot"])
        return {"status": "success", "ip": ip}
    else:
        # Timeout — hotspot still running, user can retry
        return {"status": "failed", "error": "Connection timed out"}


# Shared connection state
_conn_lock = threading.Lock()
_conn_status = {"status": "idle"}   # idle | processing | success | failed


class PortalHandler(BaseHTTPRequestHandler):
    """Handles all captive-portal HTTP requests."""

    def log_message(self, fmt, *args):
        pass  # suppress default stderr logging

    def _redirect_portal(self):
        self.send_response(302)
        self.send_header("Location", f"http://{HOST_IP}/")
        self.end_headers()

    def do_GET(self):
        # Captive-portal detection endpoints (iOS/Android/Windows)
        if self.path in ("/generate_204", "/hotspot-detect.html",
                         "/redirect", "/ncsi.txt", "/canonical.html",
                         "/success.html", "/chipmunk", "/firewall",
                         "/libproxy", "/legal", "/logo", "/login",
                         "/robots.txt", "/self.php", "/start",
                         "/status-204", "/test", "/wifi/connect",
                         "/wpad.dat"):
            self._redirect_portal()
            return

        if self.path == "/":
            self._serve_index()
        elif self.path == "/scan":
            self._serve_scan()
        elif self.path == "/status":
            self._serve_status()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/connect":
            self._handle_connect()
        else:
            self.send_error(404)

    def _serve_index(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_HTML_PAGE.encode("utf-8"))

    def _serve_scan(self):
        networks = scan_networks()
        body = json.dumps(networks)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _serve_status(self):
        with _conn_lock:
            data = dict(_conn_status)
        body = json.dumps(data)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _handle_connect(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}

        ssid = payload.get("ssid", "").strip()
        password = payload.get("password", "").strip()

        if not ssid:
            self._json_response(400, {"error": "SSID is required"})
            return

        # Respond immediately so client can poll /status
        with _conn_lock:
            _conn_status["status"] = "processing"
        self._json_response(200, {"status": "processing"})

        # Background thread does the actual connection
        def _connect_job():
            result = connect_to_network(ssid, password)
            with _conn_lock:
                _conn_status.update(result)
            # Trigger handoff on success
            if result.get("status") == "success" and _server_instance:
                threading.Thread(target=_perform_handoff,
                                 args=(_server_instance,), daemon=True).start()

        threading.Thread(target=_connect_job, daemon=True).start()

    def _json_response(self, code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _flush_hotspot_iptables() -> None:
    """Remove all hotspot-related iptables DNAT/MASQUERADE rules."""
    # Remove all PREROUTING DNAT rules for port 80 and 53
    _run(["iptables", "-t", "nat", "-D", "PREROUTING",
          "-p", "tcp", "--dport", "80", "-j", "DNAT",
          "--to-destination", f"{HOST_IP}:{_PORTAL_PORT}"], timeout=3)
    _run(["iptables", "-t", "nat", "-D", "PREROUTING",
          "-p", "tcp", "--dport", "53", "-j", "DNAT",
          "--to-destination", f"{HOST_IP}:53"], timeout=3)
    _run(["iptables", "-t", "nat", "-D", "PREROUTING",
          "-p", "udp", "--dport", "53", "-j", "DNAT",
          "--to-destination", f"{HOST_IP}:53"], timeout=3)
    # Remove MASQUERADE rule
    _run(["iptables", "-t", "nat", "-D", "POSTROUTING",
          "-s", "10.42.0.0/24", "-j", "MASQUERADE"], timeout=3)


def _perform_handoff(server):
    """Shutdown portal and exit clean."""
    print("[wifi-portal] Handoff triggered.", flush=True)
    time.sleep(3)  # Wait for client redirect
    print("[wifi-portal] Stopping portal server...", flush=True)
    server.shutdown()
    print("[wifi-portal] Removing hotspot iptables rules...", flush=True)
    _flush_hotspot_iptables()
    print("[wifi-portal] Exit 0 - portal done.", flush=True)
    os._exit(0)


# ── Embedded HTML page (single-file, no external assets) ─────────────────
_HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wi-Fi Portal</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#0f172a;color:#e2e8f0;min-height:100dvh;display:flex;
     align-items:center;justify-content:center}
.card{background:#1e293b;border:1px solid #334155;border-radius:16px;
      padding:2rem;max-width:400px;width:90%;box-shadow:0 25px 50px rgba(0,0,0,.5)}
h1{font-size:1.5rem;margin-bottom:.25rem;color:#f8fafc}
p.sub{color:#94a3b8;font-size:.875rem;margin-bottom:1.5rem}
label{display:block;font-size:.75rem;color:#94a3b8;margin-bottom:.25rem;
      text-transform:uppercase;letter-spacing:.05em}
input{width:100%;padding:.625rem .75rem;border-radius:8px;border:1px solid #334155;
      background:#0f172a;color:#e2e8f0;font-size:.9375rem;margin-bottom:1rem;
      outline:none}
input:focus{border-color:#6366f1}
button{width:100%;padding:.75rem;border:none;border-radius:8px;
       background:#6366f1;color:#fff;font-size:1rem;font-weight:600;cursor:pointer;
       transition:background .2s}
button:hover{background:#4f46e5}
button:disabled{background:#334155;color:#94a3b8;cursor:not-allowed}
.status{margin-top:1rem;padding:.75rem;border-radius:8px;font-size:.875rem;text-align:center}
.status.idle{background:#1e293b;color:#94a3b8}
.status.processing{background:#1e3a5f;color:#7dd3fc}
.status.success{background:#14532d;color:#86efac}
.status.failed{background:#7f1d1d;color:#fca5a5}
.networks{margin-top:1rem}
.networks h2{font-size:1rem;margin-bottom:.75rem;color:#cbd5e1}
.net-item{display:flex;align-items:center;justify-content:space-between;
          padding:.5rem .75rem;border-radius:8px;cursor:pointer;transition:background .15s}
.net-item:hover{background:#334155}
.net-item .ssid{font-size:.9375rem}
.net-item .meta{font-size:.75rem;color:#94a3b8}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid #7dd3fc;
         border-top-color:transparent;border-radius:50%;animation:spin .6s linear infinite;
         vertical-align:middle;margin-right:.375rem}
@keyframes spin{to{transform:rotate(360deg)}}
.btn-secondary{background:#334155;margin-top:.5rem}
.btn-secondary:hover{background:#475569}
</style>
</head>
<body>
<div class="card">
  <h1>&#x1F4F1; Wi-Fi Connect</h1>
  <p class="sub">Select a network and enter the password to connect.</p>

  <div id="msg" class="status idle">Scanning networks...</div>

  <div class="networks" id="netList"></div>

  <form id="connForm" style="margin-top:1rem" onsubmit="return false;">
    <label for="ssidInput">Network Name (SSID)</label>
    <input id="ssidInput" type="text" placeholder="Choose from list above" required>
    <label for="passInput">Password</label>
    <input id="passInput" type="password" placeholder="Wi-Fi password">
    <button id="connectBtn" onclick="doConnect()">Connect</button>
  </form>

  <button class="btn-secondary" onclick="refreshScan()" style="margin-top:.5rem">Refresh List</button>
</div>

<script>
async function setStatus(type, text) {
  const el = document.getElementById('msg');
  el.className = 'status ' + type;
  el.innerHTML = text;
}

async function refreshScan() {
  setStatus('idle', '<span class="spinner"></span> Scanning…');
  try {
    const r = await fetch('/scan');
    const nets = await r.json();
    const list = document.getElementById('netList');
    list.innerHTML = '';
    if (nets.length === 0) {
      list.innerHTML = '<p style="color:#94a3b8;font-size:.875rem;padding:.5rem 0">No networks found.</p>';
    } else {
      nets.sort((a,b) => parseInt(b.signal) - parseInt(a.signal));
      nets.forEach(n => {
        const div = document.createElement('div');
        div.className = 'net-item';
        div.innerHTML = '<span class="ssid">' + esc(n.ssid||'(hidden)') + '</span>' +
                        '<span class="meta">' + n.signal + '% · ' + n.sec + '</span>';
        div.addEventListener('click', () => {
          document.getElementById('ssidInput').value = n.ssid;
          document.getElementById('passInput').focus();
        });
        list.appendChild(div);
      });
    }
    setStatus('idle', nets.length + ' network' + (nets.length!==1?'s':'') + ' available — select one.');
  } catch(e) {
    setStatus('failed', 'Scan failed — retrying…');
  }
}

async function doConnect() {
  const ssid = document.getElementById('ssidInput').value.trim();
  const pwd  = document.getElementById('passInput').value;
  if (!ssid) { setStatus('failed','Please choose a network first.'); return; }

  const btn = document.getElementById('connectBtn');
  btn.disabled = true;
  setStatus('processing','<span class="spinner"></span> Connecting to ' + esc(ssid) + '…');

  try {
    await fetch('/connect', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ssid, password: pwd})
    });
  } catch(e) {
    setStatus('failed','Request failed — try again.');
    btn.disabled = false;
    return;
  }

  // Poll /status until settled
  const poll = setInterval(async () => {
    try {
      const r = await fetch('/status');
      const data = await r.json();
      if (data.status === 'success') {
        clearInterval(poll);
        setStatus('success', 'Connected! Redirecting to ' + data.ip + '…');
        setTimeout(() => { location.href = 'http://' + data.ip; }, 3000);
      } else if (data.status === 'failed') {
        clearInterval(poll);
        setStatus('failed', (data.error||'Connection failed').slice(0,80) +
                           ' — hotspot restored, try again.');
        btn.disabled = false;
      }
    } catch(e) {}
  }, 1000);

  // Safety timeout after 25 s
  setTimeout(() => { clearInterval(poll); btn.disabled = false; }, 25000);
}

function esc(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

// Init
refreshScan();
</script>
</body>
</html>"""


def main():
    global HOTSPOT_SSID, _server_instance

    # 1. Wait for NetworkManager to be ready
    print("[wifi-portal] Waiting for NetworkManager…", flush=True)
    if not _wait_nm_ready(retries=30, delay=0.5):
        print("[wifi-portal] ERROR: NetworkManager not ready. Exiting.", flush=True)
        return

    # 2. If already connected to WiFi AP → no portal needed
    if _is_wifi_connected_to_ap():
        print("[wifi-portal] WiFi already connected, flushing stale iptables...", flush=True)
        _flush_hotspot_iptables()
        print("[wifi-portal] Exit 0 - WiFi connected, no portal needed.", flush=True)
        return

    # 3. Flush stale iptables rules
    print("[wifi-portal] Flushing stale iptables rules...", flush=True)
    _flush_hotspot_iptables()

    # 4. Create hotspot
    print("[wifi-portal] Creating hotspot...", flush=True)
    hotspot_up = ensure_hotspot()
    if not hotspot_up:
        print("[wifi-portal] ERROR: Failed to create hotspot.", flush=True)
        return

    # 5. Start server on port 3001
    _server_instance = ThreadingHTTPServer(("0.0.0.0", _PORTAL_PORT), PortalHandler)
    print(f"[wifi-portal] Listening on http://0.0.0.0:{_PORTAL_PORT}", flush=True)
    print(f"[wifi-portal] Hotspot SSID: '{HOTSPOT_SSID}' (IP: {HOST_IP})",
          flush=True)

    try:
        _server_instance.serve_forever()
    except KeyboardInterrupt:
        pass
    _server_instance.server_close()


if __name__ == "__main__":
    main()
