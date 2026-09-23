# Wi-Fi Hotspot QR Code

Generate a scannable QR code that connects a phone to the same Wi-Fi hotspot the Raspberry Pi advertises.

Credentials follow the dispenser hotspot in `config.py` and `hotspot_manager.py`:

| Field | Source |
|---|---|
| **SSID** | `Dispenser-` + last 8 hex digits of the Pi CPU serial (from `/proc/cpuinfo`) |
| **Password** | `12345678` (configured WPA2 PSK; not derived from the serial) |
| **Security** | WPA/WPA2-PSK (`wifi-sec.key-mgmt` = `wpa-psk`) |

## Install

From this directory (`wifi-qr/`):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

From this directory:

```bash
python3 generate_wifi_qr.py --serial 10000000abcdef12
```

Writes `wifi-qr-10000000abcdef12.png` in the current directory. That serial produces SSID `Dispenser-abcdef12`.

Optional output path:

```bash
python3 generate_wifi_qr.py \
  --serial 10000000abcdef12 \
  --output dispenser-wifi-qr.png
```

The password is not printed unless you pass `--show-credentials`.

On the Pi, the serial is:

```bash
grep Serial /proc/cpuinfo
```

## Tests

From this directory:

```bash
python3 -m unittest test_generate_wifi_qr.py
```
