#!/usr/bin/env python3
"""Tests for hotspot credential derivation and Wi-Fi QR payload formatting."""

from __future__ import annotations

import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from generate_wifi_qr import (
    HOTSPOT_PASSWORD,
    InvalidSerialError,
    application_dir,
    default_output_path,
    escape_wifi_field,
    generate_for_serial,
    main,
    normalize_serial,
    password_from_serial,
    payload_for_serial,
    resolve_output_path,
    ssid_from_serial,
    wifi_qr_payload,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402


class SerialValidationTests(unittest.TestCase):
    def test_typical_16_digit_serial(self):
        self.assertEqual(
            normalize_serial("10000000abcdef12"),
            "10000000abcdef12",
        )

    def test_strips_whitespace_and_lowercases(self):
        self.assertEqual(
            normalize_serial("  10000000ABCDEF12  "),
            "10000000abcdef12",
        )

    def test_accepts_0x_prefix(self):
        self.assertEqual(
            normalize_serial("0x10000000abcdef12"),
            "10000000abcdef12",
        )

    def test_accepts_8_digit_suffix(self):
        self.assertEqual(normalize_serial("a7c7e8a5"), "a7c7e8a5")

    def test_missing_none(self):
        with self.assertRaises(InvalidSerialError) as ctx:
            normalize_serial(None)
        self.assertIn("missing", str(ctx.exception).lower())

    def test_missing_empty(self):
        with self.assertRaises(InvalidSerialError) as ctx:
            normalize_serial("   ")
        self.assertIn("missing", str(ctx.exception).lower())

    def test_non_hex_rejected(self):
        with self.assertRaises(InvalidSerialError) as ctx:
            normalize_serial("10000000gggggggg")
        self.assertIn("hexadecimal", str(ctx.exception).lower())

    def test_too_short_rejected(self):
        with self.assertRaises(InvalidSerialError) as ctx:
            normalize_serial("abc")
        self.assertIn("8", str(ctx.exception))

    def test_too_long_rejected(self):
        with self.assertRaises(InvalidSerialError):
            normalize_serial("10000000abcdef123")

    def test_cli_prints_clear_error_for_invalid_serial(self):
        stderr = StringIO()
        with patch("sys.stderr", stderr):
            code = main(["--serial", "not-a-serial"])
        self.assertEqual(code, 1)
        self.assertIn("error:", stderr.getvalue())
        self.assertIn("hexadecimal", stderr.getvalue().lower())

    def test_cli_hides_password_unless_requested(self):
        stdout = StringIO()
        with patch("generate_wifi_qr.write_qr_png"), patch("sys.stdout", stdout):
            code = main(["--serial", "10000000abcdef12", "--output", "out.png"])
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("SSID: Dispenser-abcdef12", output)
        self.assertNotIn("12345678", output)
        self.assertNotIn("Password:", output)

        stdout = StringIO()
        with patch("generate_wifi_qr.write_qr_png"), patch("sys.stdout", stdout):
            code = main(
                [
                    "--serial",
                    "10000000abcdef12",
                    "--output",
                    "out.png",
                    "--show-credentials",
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("Password: 12345678", stdout.getvalue())

    def test_opens_gui_when_serial_omitted(self):
        with patch("generate_wifi_qr.run_gui", return_value=0) as gui:
            code = main([])
        self.assertEqual(code, 0)
        gui.assert_called_once()

    def test_generate_for_serial_writes_default_png(self):
        with patch("generate_wifi_qr.write_qr_png") as write:
            result = generate_for_serial("10000000ABCDEF12")
        self.assertEqual(result.serial, "10000000abcdef12")
        self.assertEqual(result.ssid, "Dispenser-abcdef12")
        self.assertEqual(result.path.name, "wifi-qr-10000000abcdef12.png")
        write.assert_called_once()

    def test_generate_for_serial_rejects_invalid(self):
        with self.assertRaises(InvalidSerialError):
            generate_for_serial("not-a-serial")

    def test_default_png_goes_next_to_program(self):
        folder = Path("/apps/dispenser-qr")
        with patch("generate_wifi_qr.application_dir", return_value=folder):
            self.assertEqual(
                default_output_path("10000000abcdef12"),
                folder / "wifi-qr-10000000abcdef12.png",
            )
            self.assertEqual(
                resolve_output_path("10000000abcdef12", None),
                folder / "wifi-qr-10000000abcdef12.png",
            )
            self.assertEqual(
                resolve_output_path("10000000abcdef12", "custom.png"),
                folder / "custom.png",
            )

    def test_application_dir_uses_exe_when_frozen(self):
        exe = Path("/apps/generate_wifi_qr.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(exe)),
        ):
            self.assertEqual(application_dir(), exe.resolve().parent)


class SsidGenerationTests(unittest.TestCase):
    def test_uses_last_eight_hex_digits(self):
        self.assertEqual(
            ssid_from_serial("10000000abcdef12"),
            "Dispenser-abcdef12",
        )

    def test_matches_config_formula(self):
        serial = "10000000a7c7e8a5"
        expected = f"Dispenser-{serial[-8:]}"
        self.assertEqual(ssid_from_serial(serial), expected)
        self.assertTrue(config.HOTSPOT_SSID.startswith("Dispenser-"))

    def test_example_from_config_comment(self):
        self.assertEqual(
            ssid_from_serial("10000000a7c7e8a5"),
            "Dispenser-a7c7e8a5",
        )


class PasswordGenerationTests(unittest.TestCase):
    def test_password_is_configured_constant(self):
        self.assertEqual(
            password_from_serial("10000000abcdef12"),
            "12345678",
        )

    def test_password_does_not_depend_on_serial(self):
        self.assertEqual(
            password_from_serial("10000000abcdef12"),
            password_from_serial("ffffffffffff0001"),
        )

    def test_password_matches_dispenser_config(self):
        self.assertEqual(HOTSPOT_PASSWORD, config.HOTSPOT_PASSWORD)
        self.assertEqual(
            password_from_serial("10000000abcdef12"),
            config.HOTSPOT_PASSWORD,
        )

    def test_invalid_serial_still_rejected(self):
        with self.assertRaises(InvalidSerialError):
            password_from_serial("not-a-serial")


class EscapeTests(unittest.TestCase):
    def test_backslash(self):
        self.assertEqual(escape_wifi_field(r"a\b"), r"a\\b")

    def test_semicolon(self):
        self.assertEqual(escape_wifi_field("a;b"), r"a\;b")

    def test_comma(self):
        self.assertEqual(escape_wifi_field("a,b"), r"a\,b")

    def test_colon(self):
        self.assertEqual(escape_wifi_field("a:b"), r"a\:b")

    def test_double_quote(self):
        self.assertEqual(escape_wifi_field('a"b'), r"a\"b")

    def test_combined_and_backslash_first(self):
        self.assertEqual(escape_wifi_field(r'sid\;:"x'), r"sid\\\;\:\"x")

    def test_plain_text_unchanged(self):
        self.assertEqual(escape_wifi_field("Dispenser-abcdef12"), "Dispenser-abcdef12")


class PayloadFormattingTests(unittest.TestCase):
    def test_standard_payload(self):
        self.assertEqual(
            payload_for_serial("10000000abcdef12"),
            "WIFI:T:WPA;S:Dispenser-abcdef12;P:12345678;H:false;;",
        )

    def test_hidden_flag_true(self):
        self.assertEqual(
            wifi_qr_payload("net", "secret", hidden=True),
            "WIFI:T:WPA;S:net;P:secret;H:true;;",
        )

    def test_payload_escapes_ssid_and_password(self):
        payload = wifi_qr_payload("sid;one", 'pass:word,"x"')
        self.assertEqual(
            payload,
            'WIFI:T:WPA;S:sid\\;one;P:pass\\:word\\,\\"x\\";H:false;;',
        )


if __name__ == "__main__":
    unittest.main()
