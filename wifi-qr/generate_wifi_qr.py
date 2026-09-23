#!/usr/bin/env python3
"""
Generate a Wi-Fi QR code for the perfume dispenser hotspot.

SSID and password match the hotspot in config.py / hotspot_manager.py:
  SSID     = Dispenser-<last 8 hex digits of the Pi serial>
  Password = 12345678  (WPA2-PSK; not derived from the serial)
  Security = WPA       (nmcli wifi-sec.key-mgmt = wpa-psk)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Must match config.py. Password is a configured constant, not generated.
SSID_PREFIX = "Dispenser-"
HOTSPOT_PASSWORD = "12345678"
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


def default_output_path(serial: str) -> Path:
    return Path(f"wifi-qr-{normalize_serial(serial)}.png")


def write_qr_png(payload: str, output_path: Path) -> None:
    try:
        import segno
    except ImportError as exc:
        raise SystemExit(
            "error: the 'segno' package is required. "
            "Install it with: pip3 install -r wifi-qr/requirements.txt"
        ) from exc

    qr = segno.make(payload, error="m")
    qr.save(str(output_path), kind="png", scale=8, border=4)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Wi-Fi QR code for a perfume dispenser hotspot. "
            "SSID and password match config.py / hotspot_manager.py."
        )
    )
    parser.add_argument(
        "--serial",
        required=True,
        help="Raspberry Pi CPU serial number (hex, typically 16 digits)",
    )
    parser.add_argument(
        "--output",
        help="PNG path (default: wifi-qr-<serial-number>.png)",
    )
    parser.add_argument(
        "--show-credentials",
        action="store_true",
        help="Print the SSID and password to the terminal",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        serial = normalize_serial(args.serial)
    except InvalidSerialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ssid = ssid_from_serial(serial)
    password = password_from_serial(serial)
    payload = wifi_qr_payload(ssid, password, hidden=False)
    output_path = Path(args.output) if args.output else default_output_path(serial)

    write_qr_png(payload, output_path)
    print(f"Wrote {output_path}")
    print(f"SSID: {ssid}")
    if args.show_credentials:
        print(f"Password: {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
