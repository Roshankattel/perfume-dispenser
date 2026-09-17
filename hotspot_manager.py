#!/usr/bin/env python3
"""
Hotspot and Captive Portal Manager
Enables a temporary Wi-Fi access point with an HTTP portal for configuring
RELAY_DURATION. Imported by perfume_dispenser.py; all network operations run
in a background thread so the main button loop is never blocked.

Requirements (run service as root, or grant sudoers rights for):
  nmcli, iptables, writes to /etc/NetworkManager/dnsmasq-shared.d/
"""

import os
import re
import tempfile
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import config

# ── Internal constants ───────────────────────────────────────────────────────

_CON_NAME  = "perfume-hotspot"
_DNSMASQ   = "/etc/NetworkManager/dnsmasq-shared.d/captive.conf"
_WEB_PORT  = 8080  # non-root port; iptables redirects 80 → 8080

# ── Portal HTML template ─────────────────────────────────────────────────────

_HTML = """\
<!DOCTYPE html><html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dispenser Setup</title>
<style>
  body{{font-family:sans-serif;max-width:420px;margin:40px auto;padding:0 16px;color:#222}}
  h2{{margin-bottom:4px}} p.sub{{margin-top:0;color:#666}}
  input[type=number]{{width:100%;padding:8px;font-size:1.1em;
                      box-sizing:border-box;border:1px solid #ccc;border-radius:4px}}
  button{{width:100%;padding:10px;font-size:1.1em;background:#0071e3;color:#fff;
          border:none;border-radius:6px;cursor:pointer;margin-top:8px}}
  button:active{{background:#005bb5}}
  .ok {{background:#d4edda;color:#155724;padding:8px;border-radius:4px;margin-top:8px}}
  .err{{background:#f8d7da;color:#721c24;padding:8px;border-radius:4px;margin-top:8px}}
</style></head><body>
<h2>Perfume Dispenser Setup</h2>
<p class="sub">Configure spray duration</p>
<p>Current <b>RELAY_DURATION</b>: <b>{cur} ms</b></p>
<form method="POST" action="/save">
  <label>New duration in milliseconds ({mn}–{mx}):<br>
  <input type="number" name="v" value="{cur}" min="{mn}" max="{mx}" required></label>
  <button type="submit">Save</button>
</form>
{msg}
</body></html>
"""


# ── HTTP request handler ─────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    """Minimal captive-portal handler.  manager is set by HotspotManager."""
    manager = None

    # ---- helpers ----

    def log_message(self, *_):
        pass  # suppress default access log; important events are printed elsewhere

    def _send(self, code: int, body: str):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type",   "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _page(self, msg: str = "") -> str:
        mn = getattr(config, "RELAY_DURATION_MIN", 100)
        mx = getattr(config, "RELAY_DURATION_MAX", 10_000)
        return _HTML.format(cur=config.RELAY_DURATION, mn=mn, mx=mx, msg=msg)

    # ---- GET ----

    def do_GET(self):
        path = urlparse(self.path).path
        if path not in ("/", "/save"):
            # Redirect captive-portal probes and all other paths to the portal
            self.send_response(302)
            self.send_header("Location", f"http://{config.HOTSPOT_IP}/")
            self.end_headers()
            return
        self._send(200, self._page())

    # ---- POST ----

    def do_POST(self):
        if urlparse(self.path).path != "/save":
            self._send(404, "Not Found")
            return

        n    = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode(errors="replace")
        raw  = parse_qs(body).get("v", [""])[0].strip()

        mn = getattr(config, "RELAY_DURATION_MIN", 100)
        mx = getattr(config, "RELAY_DURATION_MAX", 10_000)
        try:
            val = int(raw)
            if not (mn <= val <= mx):
                raise ValueError("out of range")
            self.manager._write_relay_duration(val)
            msg = f'<div class="ok">&#10003; Saved — RELAY_DURATION = {val} ms</div>'
            print(f"[hotspot] RELAY_DURATION updated → {val} ms", flush=True)
        except (ValueError, TypeError):
            msg = (f'<div class="err">&#10007; Invalid value. '
                   f'Enter an integer between {mn} and {mx}.</div>')
            print(f"[hotspot] Rejected invalid RELAY_DURATION submission: {raw!r}", flush=True)

        self._send(200, self._page(msg))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(args: list, check: bool = False) -> int:
    """Run a command, return its exit code.  Failures are only raised if check=True."""
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode and check:
        raise RuntimeError(f"{' '.join(str(a) for a in args[:4])}: {r.stderr.strip()}")
    return r.returncode


# ── HotspotManager ───────────────────────────────────────────────────────────

class HotspotManager:
    """
    Manages a Wi-Fi access point and captive portal in the background.

    Usage in the main application:
        hotspot = HotspotManager()
        # When the combo is detected:
        threading.Thread(target=hotspot.toggle, daemon=True).start()
        # On shutdown:
        if hotspot.is_active:
            hotspot.disable()
    """

    # Button indices (0-based) for the combo — button 1 and button 3
    BTNS = (0, 2)

    def __init__(self):
        self._active = False
        self._server: HTTPServer | None = None
        self._sthread: threading.Thread | None = None
        _Handler.manager = self

    @property
    def is_active(self) -> bool:
        return self._active

    # ---- public API ----

    def toggle(self):
        """Toggle the hotspot on or off (blocking — call from a background thread)."""
        if self._active:
            self._disable()
        else:
            self._enable()

    def disable(self):
        """Unconditionally disable the hotspot (idempotent)."""
        if self._active:
            self._disable()

    # ---- private: enable path ----

    def _enable(self):
        print("[hotspot] Enabling hotspot…", flush=True)
        try:
            self._write_dns()           # write before NM starts its dnsmasq
            self._bring_up()            # nmcli: create + start AP connection
            self._iptables("A")         # redirect port 80 → 8080
            self._start_server()        # start HTTP portal on port 8080
            self._active = True
            print(f"[hotspot] Active — SSID: {config.HOTSPOT_SSID!r} | "
                  f"portal: http://{config.HOTSPOT_IP}/", flush=True)
        except Exception as exc:
            print(f"[hotspot] Enable failed: {exc}", flush=True)
            self._net_cleanup()

    def _write_dns(self):
        """DNS hijack: redirect all queries to portal IP via NM's dnsmasq."""
        os.makedirs(os.path.dirname(_DNSMASQ), exist_ok=True)
        with open(_DNSMASQ, "w") as f:
            f.write(f"address=/#/{config.HOTSPOT_IP}\n")

    def _bring_up(self):
        _run(["nmcli", "con", "delete", _CON_NAME])     # remove stale entry if any
        pw = getattr(config, "HOTSPOT_PASSWORD", "")
        for cmd in [
            ["nmcli", "con", "add", "type", "wifi", "ifname", "wlan0",
             "con-name", _CON_NAME, "autoconnect", "no", "ssid", config.HOTSPOT_SSID],
            ["nmcli", "con", "modify", _CON_NAME,
             "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
             "ipv4.method", "shared", "ipv4.addresses", f"{config.HOTSPOT_IP}/24"],
            *(
                [["nmcli", "con", "modify", _CON_NAME,
                  "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", pw]]
                if pw else []
            ),
            ["nmcli", "con", "up", _CON_NAME],
        ]:
            _run(cmd, check=True)

    def _iptables(self, action: str):
        """Add (-A) or remove (-D) the port-80 → port-8080 redirect rule."""
        _run(["iptables", "-t", "nat", f"-{action}", "PREROUTING",
              "-i", "wlan0", "-p", "tcp", "--dport", "80",
              "-j", "REDIRECT", "--to-port", str(_WEB_PORT)])

    def _start_server(self):
        self._server  = HTTPServer(("0.0.0.0", _WEB_PORT), _Handler)
        self._sthread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="portal-http"
        )
        self._sthread.start()

    # ---- private: disable path ----

    def _disable(self):
        print("[hotspot] Disabling hotspot…", flush=True)
        self._stop_server()
        self._iptables("D")
        self._net_cleanup()
        _run(["nmcli", "device", "connect", "wlan0"])   # best-effort reconnect
        self._active = False
        print("[hotspot] Disabled — normal networking restored", flush=True)

    def _stop_server(self):
        if self._server:
            self._server.shutdown()
            self._server  = None
            self._sthread = None

    def _net_cleanup(self):
        _run(["nmcli", "con", "down",   _CON_NAME])
        _run(["nmcli", "con", "delete", _CON_NAME])
        try:
            os.remove(_DNSMASQ)
        except FileNotFoundError:
            pass

    # ---- config update ----

    def _write_relay_duration(self, value: int):
        """
        Atomically update RELAY_DURATION in config.py and apply the new value
        to the running process immediately (no restart required).
        """
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
        with open(path) as f:
            text = f.read()

        new_text = re.sub(
            r"^(RELAY_DURATION\s*=\s*)\d+",
            lambda m: f"{m.group(1)}{value}",
            text,
            flags=re.MULTILINE,
        )
        if new_text == text:
            raise RuntimeError("RELAY_DURATION assignment not found in config.py")

        # Atomic write: write to tmp then rename (never leaves a partial file)
        dir_ = os.path.dirname(path)
        with tempfile.NamedTemporaryFile(
                "w", dir=dir_, delete=False, suffix=".tmp") as tmp:
            tmp.write(new_text)
            tmp_path = tmp.name
        os.replace(tmp_path, path)          # atomic on POSIX

        config.RELAY_DURATION = value       # live update — no restart needed
