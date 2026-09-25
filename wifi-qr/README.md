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

Writes `wifi-qr-10000000abcdef12.png` next to the script (or `.exe`). That serial produces SSID `Dispenser-abcdef12`.

If you omit `--serial`, a window opens with a serial text box. Click **Generate QR** (or press Enter). The window stays open so you can type the next serial without restarting:

```bash
python3 generate_wifi_qr.py
```

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

## Windows `.exe`

Build on a Windows machine (PyInstaller cannot produce a Windows exe from macOS):

```bat
cd wifi-qr
build_windows.bat
```

That creates `wifi-qr\dist\generate_wifi_qr.exe`. Copy the exe to any folder and double-click it. Type the Pi serial, click **Generate QR**, and `wifi-qr-<serial>.png` is saved in the **same folder as the exe**. The window stays open for the next unit.

## Tests

From this directory:

```bash
python3 -m unittest test_generate_wifi_qr.py
```
