#!/usr/bin/env python3
"""
Hotspot and Captive Portal Manager
Enables a temporary Wi-Fi access point with an HTTP portal for configuring
RELAY_DURATION. Imported by perfume_dispenser.py; all network operations run
in a background thread so the main button loop is never blocked.

Requirements (run service as root, or grant sudoers rights for):
  nmcli, nft (or iptables), writes to /etc/NetworkManager/dnsmasq-shared.d/
"""

import os
import re
import shutil
import tempfile
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import config

# ── Internal constants ───────────────────────────────────────────────────────

_CON_NAME  = "perfume-hotspot"
_DNSMASQ   = "/etc/NetworkManager/dnsmasq-shared.d/captive.conf"
_WEB_PORT   = 8080  # non-root port; nft/iptables redirects 80 → 8080
_NFT_TABLE  = "perfume_hotspot"

# Resolve full paths for privileged binaries that may not be in systemd's PATH
_SEARCH_DIRS = ["/usr/sbin", "/sbin", "/usr/bin", "/bin"]

def _find(name: str) -> str | None:
    """Find a binary in the standard sbin/bin locations, or None if missing."""
    return shutil.which(name, path=":".join(_SEARCH_DIRS))

# Prefer nftables (Raspberry Pi OS / Debian default). iptables is a fallback.
_NMCLI    = _find("nmcli")
_NFT      = _find("nft")
_IPTABLES = _find("iptables")


def _wifi_iface() -> str:
    """
    Return the name of the first Wi-Fi device known to NetworkManager.
    Falls back to 'wlan0' if detection fails.
    Cached after first call so nmcli is only invoked once.
    """
    if _wifi_iface._cache:
        return _wifi_iface._cache[0]
    if not _NMCLI:
        _wifi_iface._cache.append("wlan0")
        return "wlan0"
    try:
        r = subprocess.run(
            [_NMCLI, "-t", "-f", "DEVICE,TYPE", "device"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[1].strip() == "wifi":
                iface = parts[0].strip()
                print(f"[hotspot] Detected Wi-Fi interface: {iface}", flush=True)
                _wifi_iface._cache.append(iface)
                return iface
    except Exception as exc:
        print(f"[hotspot] Interface detection failed ({exc}), falling back to wlan0", flush=True)
    _wifi_iface._cache.append("wlan0")
    return "wlan0"

_wifi_iface._cache: list = []

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
            if not _NMCLI:
                raise RuntimeError("nmcli not found; install NetworkManager")
            if not _NFT and not _IPTABLES:
                raise RuntimeError("nft or iptables not found; install nftables")
            self._write_dns()           # write before NM starts its dnsmasq
            self._bring_up()            # nmcli: create + start AP connection
            self._port_redirect(True)   # redirect port 80 → 8080
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
        _run([_NMCLI, "con", "delete", _CON_NAME])     # remove stale entry if any
        iface = _wifi_iface()
        pw = getattr(config, "HOTSPOT_PASSWORD", "")
        for cmd in [
            [_NMCLI, "con", "add", "type", "wifi", "ifname", iface,
             "con-name", _CON_NAME, "autoconnect", "no", "ssid", config.HOTSPOT_SSID],
            [_NMCLI, "con", "modify", _CON_NAME,
             "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
             "ipv4.method", "shared", "ipv4.addresses", f"{config.HOTSPOT_IP}/24"],
            *(
                [[_NMCLI, "con", "modify", _CON_NAME,
                  "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", pw]]
                if pw else []
            ),
            [_NMCLI, "con", "up", _CON_NAME],
        ]:
            _run(cmd, check=True)

    def _port_redirect(self, enable: bool):
        """Add or remove the port-80 → port-8080 redirect (nft, else iptables)."""
        iface = _wifi_iface()
        if _NFT:
            if enable:
                _run([_NFT, "delete", "table", "ip", _NFT_TABLE])
                rules = (
                    f"table ip {_NFT_TABLE} {{\n"
                    f"    chain prerouting {{\n"
                    f"        type nat hook prerouting priority dstnat;\n"
                    f"        iifname \"{iface}\" tcp dport 80 redirect to :{_WEB_PORT}\n"
                    f"    }}\n"
                    f"}}\n"
                )
                r = subprocess.run(
                    [_NFT, "-f", "-"], input=rules,
                    capture_output=True, text=True,
                )
                if r.returncode:
                    raise RuntimeError(f"nft: {r.stderr.strip()}")
            else:
                _run([_NFT, "delete", "table", "ip", _NFT_TABLE])
            return
        action = "A" if enable else "D"
        _run([_IPTABLES, "-t", "nat", f"-{action}", "PREROUTING",
              "-i", iface, "-p", "tcp", "--dport", "80",
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
        self._port_redirect(False)
        self._net_cleanup()
        if _NMCLI:
            _run([_NMCLI, "device", "connect", _wifi_iface()])   # best-effort reconnect
        self._active = False
        print("[hotspot] Disabled — normal networking restored", flush=True)

    def _stop_server(self):
        if self._server:
            self._server.shutdown()
            self._server  = None
            self._sthread = None

    def _net_cleanup(self):
        if _NMCLI:
            _run([_NMCLI, "con", "down",   _CON_NAME])
            _run([_NMCLI, "con", "delete", _CON_NAME])
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
