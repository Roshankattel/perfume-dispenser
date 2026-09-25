#!/usr/bin/env python3
"""
Generate a Wi-Fi QR code for the perfume dispenser hotspot.

SSID and password match the hotspot in config.py / hotspot_manager.py:
  SSID     = Dispenser-<last 8 hex digits of the Pi serial>
  Password = 12345678  (WPA2-PSK; not derived from the serial)
  Security = WPA       (nmcli wifi-sec.key-mgmt = wpa-psk)

With no --serial argument (including a double-clicked .exe), a GUI opens.
The PNG is written next to the exe/script. The window stays open so you
can generate another code without restarting.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Must match config.py. Password is a configured constant, not generated.
SSID_PREFIX = "Dispenser-"
HOTSPOT_PASSWORD = "432FACC99AD"
WIFI_AUTH_TYPE = "WPA"

_SERIAL_RE = re.compile(r"^[0-9a-f]+$")
_WIFI_ESCAPE = str.maketrans(
    {
        "\\": r"\\",
        ";": r"\;",
        ",": r"\,",
        ":": r"\:",
        '"': r"\"",
    }
)


class InvalidSerialError(ValueError):
    """Raised when the Raspberry Pi serial number is missing or malformed."""


@dataclass(frozen=True)
class GenerateResult:
    serial: str
    ssid: str
    path: Path


def normalize_serial(raw: str | None) -> str:
    """
    Validate and normalize a Raspberry Pi CPU serial number.

    Matches config._get_pi_serial(): hex digits, last 8 used in the SSID.
    Accepts the 16-digit value from /proc/cpuinfo (and the 8-digit suffix).
    """
    if raw is None:
        raise InvalidSerialError("Serial number is missing.")

    serial = raw.strip()
    if not serial:
        raise InvalidSerialError("Serial number is missing.")

    if serial.lower().startswith("0x"):
        serial = serial[2:]

    serial = serial.lower()
    if not _SERIAL_RE.fullmatch(serial):
        raise InvalidSerialError(
            f"Invalid serial number {raw!r}: must be hexadecimal digits."
        )
    if not 8 <= len(serial) <= 16:
        raise InvalidSerialError(
            f"Invalid serial number {raw!r}: expected 8–16 hex digits "
            "(Raspberry Pi serial numbers are typically 16)."
        )
    return serial


def ssid_from_serial(serial: str) -> str:
    """SSID used by the hotspot: Dispenser- plus the last 8 hex digits."""
    return f"{SSID_PREFIX}{normalize_serial(serial)[-8:]}"


def password_from_serial(serial: str) -> str:
    """
    Hotspot PSK. Serial is validated so a bad serial is rejected, but the
    password itself is the configured constant in config.HOTSPOT_PASSWORD.
    """
    normalize_serial(serial)
    return HOTSPOT_PASSWORD


def escape_wifi_field(value: str) -> str:
    """Escape \\, ;, ,, :, and \" per the WIFI: QR / MeCard rules."""
    return value.translate(_WIFI_ESCAPE)


def wifi_qr_payload(ssid: str, password: str, hidden: bool = False) -> str:
    """Build a standards-compliant WIFI: QR payload (WPA/WPA2-PSK)."""
    hidden_flag = "true" if hidden else "false"
    return (
        f"WIFI:T:{WIFI_AUTH_TYPE};"
        f"S:{escape_wifi_field(ssid)};"
        f"P:{escape_wifi_field(password)};"
        f"H:{hidden_flag};;"
    )


def payload_for_serial(serial: str) -> str:
    ssid = ssid_from_serial(serial)
    password = password_from_serial(serial)
    return wifi_qr_payload(ssid, password, hidden=False)


def application_dir() -> Path:
    """Folder containing the .exe (frozen) or this script (source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_output_path(serial: str, directory: Path | None = None) -> Path:
    base = directory if directory is not None else application_dir()
    return base / f"wifi-qr-{normalize_serial(serial)}.png"


def resolve_output_path(serial: str, output: str | None) -> Path:
    if not output:
        return default_output_path(serial)
    path = Path(output)
    if not path.is_absolute():
        path = application_dir() / path
    return path


def write_qr_png(payload: str, output_path: Path) -> None:
    try:
        import segno
    except ImportError as exc:
        raise RuntimeError(
            "the 'segno' package is required. "
            "Install it with: pip install -r requirements.txt"
        ) from exc

    qr = segno.make(payload, error="m")
    qr.save(str(output_path), kind="png", scale=8, border=4)


def generate_for_serial(raw_serial: str, output: str | None = None) -> GenerateResult:
    """Validate the serial, write the QR PNG, and return the result."""
    serial = normalize_serial(raw_serial)
    ssid = ssid_from_serial(serial)
    payload = wifi_qr_payload(ssid, password_from_serial(serial), hidden=False)
    output_path = resolve_output_path(serial, output)
    write_qr_png(payload, output_path)
    return GenerateResult(serial=serial, ssid=ssid, path=output_path)


def run_gui() -> int:
    import tkinter as tk

    root = tk.Tk()
    root.title("Dispenser Wi-Fi QR")
    root.minsize(420, 360)
    WifiQrWindow(root)
    root.mainloop()
    return 0


class WifiQrWindow:
    """Simple window: serial box, Generate, stays open for the next unit."""

    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self._photo = None
        self._last_result: GenerateResult | None = None

        pad = {"padx": 16, "pady": 6}
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Enter a Raspberry Pi serial number and click Generate.\n"
            "The QR is saved next to this program. Leave the window open "
            "to generate another.",
            wraplength=400,
            justify="left",
        ).pack(anchor="w", **pad)

        ttk.Label(frame, text="Serial number").pack(anchor="w", padx=16)
        self.serial_var = tk.StringVar()
        self.entry = ttk.Entry(frame, textvariable=self.serial_var, width=36)
        self.entry.pack(fill="x", padx=16, pady=(0, 8))
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda _e: self.on_generate())

        ttk.Button(frame, text="Generate QR", command=self.on_generate).pack(
            anchor="w", padx=16, pady=(0, 8)
        )

        self.show_password = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Show password",
            variable=self.show_password,
            command=self._refresh_status,
        ).pack(anchor="w", padx=16)

        self.status = ttk.Label(frame, text="", wraplength=400, justify="left")
        self.status.pack(anchor="w", **pad)

        self.preview = ttk.Label(frame)
        self.preview.pack(pady=8)

    def on_generate(self) -> None:
        try:
            result = generate_for_serial(self.serial_var.get())
        except InvalidSerialError as exc:
            self._last_result = None
            self._set_status(str(exc), error=True)
            self.preview.configure(image="")
            self._photo = None
            return
        except Exception as exc:
            self._last_result = None
            self._set_status(f"Could not write QR: {exc}", error=True)
            return

        self._last_result = result
        self.serial_var.set(result.serial)
        self.entry.selection_range(0, "end")
        self.entry.focus_set()
        self._refresh_status()
        self._show_preview(result.path)

    def _refresh_status(self) -> None:
        result = self._last_result
        if result is None:
            return
        lines = [f"Saved {result.path.name}", f"SSID: {result.ssid}"]
        if self.show_password.get():
            lines.append(f"Password: {HOTSPOT_PASSWORD}")
        self._set_status("\n".join(lines), error=False)

    def _set_status(self, text: str, error: bool) -> None:
        self.status.configure(text=text, foreground="#b00020" if error else "#1a7f37")

    def _show_preview(self, path: Path) -> None:
        from tkinter import PhotoImage

        try:
            photo = PhotoImage(file=str(path))
        except Exception:
            self.preview.configure(image="")
            self._photo = None
            return
        # Shrink large codes so the window stays compact.
        while photo.width() > 240 or photo.height() > 240:
            photo = photo.subsample(2, 2)
        self._photo = photo
        self.preview.configure(image=photo)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Wi-Fi QR code for a perfume dispenser hotspot. "
            "SSID and password match config.py / hotspot_manager.py. "
            "If --serial is omitted, a GUI is shown."
        )
    )
    parser.add_argument(
        "--serial",
        help="Raspberry Pi CPU serial number (hex, typically 16 digits)",
    )
    parser.add_argument(
        "--output",
        help="PNG path (default: wifi-qr-<serial-number>.png next to this program)",
    )
    parser.add_argument(
        "--show-credentials",
        action="store_true",
        help="Print the SSID and password to the terminal (CLI only)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = _parse_args(argv)

    if args.serial is None:
        return run_gui()

    try:
        result = generate_for_serial(args.serial, args.output)
    except InvalidSerialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {result.path}")
    print(f"SSID: {result.ssid}")
    if args.show_credentials:
        print(f"Password: {HOTSPOT_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
