# Perfume Dispenser System

A vending machine system for dispensing perfumes with integrated card payment support via MDB (Multi-Drop Bus) protocol. The system supports 5 different perfume selections with visual LED indicators and button-based selection interface.

**Available for:**
- **Raspberry Pi 4B** (Python implementation) - **Recommended**
- **Arduino Uno** (C++ implementation) - Legacy support

## Features

- **5-Channel Dispensing System**: Control up to 5 different perfume dispensers
- **Card Payment Integration**: Supports contactless card payments via Nayax payment gateway using MDB protocol
- **Visual Feedback**: 
  - All LEDs solid ON when idle (waiting for payment)
  - LEDs flash when payment is approved (waiting for item selection)
  - Individual LED indicates active dispenser during vending
- **Button Selection Interface**: 5 buttons for selecting perfume items (only active after payment approval)
- **Automatic Timeout Handling**: 
  - 55 seconds timeout for item selection
  - Automatic cancel vend if no selection is made
  - 15 seconds timeout for other operations
- **State Machine**: Robust state management for payment and vending flow
- **Serial Debugging**: Comprehensive serial output for monitoring MDB communication

## Hardware Requirements

### For Raspberry Pi 4B (Recommended)
- **Raspberry Pi 4B** (or compatible)
- **5x Relay Modules** (for controlling dispensers)
- **5x LEDs** (for visual indicators)
- **5x Push Buttons** (for item selection)
- **Nayax Payment Gateway** (MDB protocol compatible)
- **Resistors** (for LEDs and pull-up resistors for buttons)
- **Power Supply** (appropriate for relays and Raspberry Pi)
- **USB-to-TTL adapter** or **UART connection** for payment gateway communication

### For Arduino Uno (Legacy)
- **Arduino Uno** (or compatible)
- **5x Relay Modules** (for controlling dispensers)
- **5x LEDs** (for visual indicators)
- **5x Push Buttons** (for item selection)
- **Nayax Payment Gateway** (MDB protocol compatible)
- **Resistors** (for LEDs and pull-up resistors for buttons)
- **Power Supply** (appropriate for relays and Arduino)

## Pin Connections

### Raspberry Pi 4B Configuration (Configurable)

All pins are configurable in `config.py`. Default configuration:

#### Relay Pins (Output - GPIO/BCM numbering)
Control the dispenser pumps/valves:
- Relay 1: **GPIO 18** (Physical pin 12)
- Relay 2: **GPIO 23** (Physical pin 16)
- Relay 3: **GPIO 24** (Physical pin 18)
- Relay 4: **GPIO 25** (Physical pin 22)
- Relay 5: **GPIO 12** (Physical pin 32)

#### LED Pins (Output - GPIO/BCM numbering)
Visual indicators for each dispenser:
- LED 1: **GPIO 5** (Physical pin 29)
- LED 2: **GPIO 6** (Physical pin 31)
- LED 3: **GPIO 13** (Physical pin 33)
- LED 4: **GPIO 19** (Physical pin 35)
- LED 5: **GPIO 26** (Physical pin 37)

#### Button Pins (Input with Pull-up - GPIO/BCM numbering)
Item selection buttons (active LOW):
- Button 1: **GPIO 2** (Physical pin 3)
- Button 2: **GPIO 3** (Physical pin 5)
- Button 3: **GPIO 4** (Physical pin 7)
- Button 4: **GPIO 17** (Physical pin 11)
- Button 5: **GPIO 27** (Physical pin 13)

#### Payment Gateway Serial (TTL/UART)
MDB protocol communication:
- **UART**: `/dev/ttyAMA0` (GPIO 14 = TX, GPIO 15 = RX) - Default
- **USB-to-TTL**: `/dev/ttyUSB0` (if using USB adapter)
- Baud Rate: **9600**

**To change pin assignments**, edit `config.py`:
```python
RELAY_PINS = [18, 23, 24, 25, 12]  # Change these GPIO pin numbers
LED_PINS = [5, 6, 13, 19, 26]      # Change these GPIO pin numbers
BUTTON_PINS = [2, 3, 4, 17, 27]    # Change these GPIO pin numbers
TTL_SERIAL_PORT = '/dev/ttyAMA0'   # Change serial port if needed
```

### Arduino Uno Configuration (Legacy)

#### Relay Pins (Output)
- Relay 1: **A0**
- Relay 2: **A1**
- Relay 3: **A2**
- Relay 4: **A3**
- Relay 5: **12**

#### LED Pins (Output)
- LED 1: **3**
- LED 2: **5**
- LED 3: **7**
- LED 4: **9**
- LED 5: **11**

#### Button Pins (Input with Pull-up)
- Button 1: **2**
- Button 2: **4**
- Button 3: **6**
- Button 4: **8**
- Button 5: **10**

#### Payment Gateway Serial (SoftwareSerial)
- RX: **A5** (receives data from payment gateway)
- TX: **A4** (sends data to payment gateway)
- Baud Rate: **9600**

## Wiring Diagram

```
Arduino Uno                    External Components
-----------                    -------------------
A0  ────────────────► Relay 1
A1  ────────────────► Relay 2
A2  ────────────────► Relay 3
A3  ────────────────► Relay 4
12  ────────────────► Relay 5

3   ──────► LED 1 ───► GND
5   ──────► LED 2 ───► GND
7   ──────► LED 3 ───► GND
9   ──────► LED 4 ───► GND
11  ──────► LED 5 ───► GND

2   ──────► Button 1 ───► GND
4   ──────► Button 2 ───► GND
6   ──────► Button 3 ───► GND
8   ──────► Button 4 ───► GND
10  ──────► Button 5 ───► GND

A5  ────────────────► Payment Gateway TX
A4  ────────────────► Payment Gateway RX
GND ────────────────► Payment Gateway GND
```

**Note**: Buttons use internal pull-up resistors (INPUT_PULLUP), so they connect between the pin and GND. When pressed, the pin reads LOW.

## Software Setup

### Raspberry Pi 4B Setup (Recommended)

#### Prerequisites

1. **Raspberry Pi OS** (Raspbian) installed and updated
2. **Python 3.7+** (usually pre-installed)
3. **GPIO access** - User must be in `gpio` group (usually automatic)

#### Installation Steps

1. **Clone or download this repository** to your Raspberry Pi

2. **Install Python dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```
   
   Or install manually:
   ```bash
   pip3 install RPi.GPIO pyserial
   ```

3. **Configure GPIO pins** (if needed):
   - Edit `config.py` to change pin assignments
   - All pins use BCM/GPIO numbering (not physical pin numbers)
   - See pin configuration section above for details

4. **Enable UART** (if using hardware UART):
   ```bash
   sudo raspi-config
   # Navigate to: Interface Options → Serial Port
   # Enable serial port hardware
   # Disable serial console (if enabled)
   ```

5. **Check serial port**:
   ```bash
   ls -l /dev/ttyAMA0  # Hardware UART
   ls -l /dev/ttyUSB0  # USB-to-TTL adapter
   ```
   
   Update `TTL_SERIAL_PORT` in `config.py` if using a different port.

6. **Run the application**:
   ```bash
   sudo python3 perfume_dispenser.py
   ```
   
   **Note**: `sudo` may be required for GPIO access depending on your system configuration.

7. **Run as a service** (optional, for auto-start on boot):
   ```bash
   # Create systemd service file
   sudo nano /etc/systemd/system/perfume-dispenser.service
   ```
   
   Add the following content:
   ```ini
   [Unit]
   Description=Perfume Dispenser System
   After=network.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/path/to/arduino-perfume-dispenser
   ExecStart=/usr/bin/python3 /path/to/arduino-perfume-dispenser/perfume_dispenser.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   
   Then enable and start:
   ```bash
   sudo systemctl enable perfume-dispenser.service
   sudo systemctl start perfume-dispenser.service
   ```

#### Configuration

All settings are in `config.py`:

```python
# Pin assignments (GPIO/BCM numbering)
RELAY_PINS = [18, 23, 24, 25, 12]
LED_PINS = [5, 6, 13, 19, 26]
BUTTON_PINS = [2, 3, 4, 17, 27]

# Serial configuration
TTL_SERIAL_PORT = '/dev/ttyAMA0'  # or '/dev/ttyUSB0'
TTL_BAUD_RATE = 9600

# System constants
ITEM_PRICE = 200  # Price in cents ($2.00)
ITEM_SELECTION_TIMEOUT = 55000  # 55 seconds
RELAY_DURATION = 2500  # 2.5 seconds
POST_DISPENSE_DELAY = 2000  # 2 seconds
FLASH_INTERVAL = 500  # 500ms LED flash interval
```

### Arduino Uno Setup (Legacy)

#### Required Libraries

Install the following Arduino libraries:

1. **Bounce2** - For button debouncing
   - Install via Arduino Library Manager: `Bounce2` by Thomas O Fredericks

2. **SoftwareSerial** - Built-in Arduino library (no installation needed)

#### Configuration

Key constants in `src/main.cpp` that can be adjusted:

```cpp
const uint16_t ITEM_PRICE = 200;  // Price in cents ($2.00)
const unsigned long ITEM_SELECTION_TIMEOUT = 55000;  // 55 seconds
const unsigned long RELAY_DURATION = 2500;  // 2.5 seconds
const unsigned long POST_DISPENSE_DELAY = 2000;  // 2 seconds
const unsigned long FLASH_INTERVAL = 500;  // 500ms LED flash interval
```

#### Upload Instructions

1. Connect Arduino Uno to your computer via USB
2. Open project in PlatformIO or Arduino IDE
3. Select board: **Arduino Uno**
4. Select port: **[Your Arduino Port]**
5. Click **Upload** button

## Operation Flow

1. **Idle State**: All LEDs are solid ON, system waits for card tap
2. **Card Tap**: User taps card on payment gateway
3. **Price Sent**: System automatically sends item price ($2.00) to payment gateway
4. **Payment Approval**: 
   - If approved: LEDs start flashing, buttons become active
   - If rejected: LEDs turn off, session ends after timeout
5. **Item Selection**: User presses button (1-5) to select perfume
6. **Dispensing**: 
   - Selected relay activates for 3 seconds
   - Corresponding LED turns ON (others OFF)
   - Vend command sent to payment gateway
7. **Session End**: After dispensing completes, 2-second delay, then session ends

## MDB Protocol Commands

The system implements the following MDB commands:

### Sent to Payment Gateway:
- `13 00 00 C8 00 01` - Select Amount ($2.00 = 200 cents = 0xC8)
- `13 02 00 [item]` - Vend Item (item number 1-5)
- `13 01` - Cancel Vend (on timeout)
- `13 04` - End Session

### Received from Payment Gateway:
- `10 03` - Card Tap Event
- `10 05 00 0A` - Payment Approved (with amount)
- `10 06` - Payment Rejected
- `10 04` - Timeout
- `00` or `10 00` - ACK
- `30 30 20 0d 0a` - Cancel Vend ACK (ASCII "00 \r\n")

## Serial Monitor Output

The system provides detailed serial debugging at 9600 baud:

```
Setup complete - System ready!
Waiting for card tap...
RX: 10 03 03 E8 | State: WAIT_CARD_TAP
Card tap detected!
TX: 13 00 00 C8 00 01 | State: WAIT_APPROVAL
TX: Select Amount $2.00
RX: 10 05 00 C8 | State: WAIT_APPROVAL
Payment approved: $2.00
Waiting for item selection (timeout: 55 seconds)...
TX: 13 02 00 01 | State: WAIT_ITEM
TX: Vend Item 1
Dispenser 1 activated - Vending in progress
```

## Troubleshooting

### Raspberry Pi Specific

#### Permission Errors
- If you get "Permission denied" errors, try running with `sudo`:
  ```bash
  sudo python3 perfume_dispenser.py
  ```
- Or add your user to the `gpio` group:
  ```bash
  sudo usermod -a -G gpio $USER
  # Log out and back in for changes to take effect
  ```

#### Serial Port Not Found
- Check if UART is enabled: `sudo raspi-config` → Interface Options → Serial Port
- List available serial ports: `ls -l /dev/tty*`
- Update `TTL_SERIAL_PORT` in `config.py` to match your port
- For USB-to-TTL adapters, try `/dev/ttyUSB0` or `/dev/ttyACM0`

#### GPIO Pins Not Working
- Verify you're using BCM/GPIO pin numbers (not physical pin numbers)
- Check pin assignments in `config.py` match your wiring
- Use `gpio readall` (if installed) to check pin states
- Ensure pins aren't being used by other processes

### General Issues

#### LEDs Not Working
- Check LED polarity (anode to pin via resistor, cathode to GND)
- Verify resistor values (220Ω recommended)
- Check pin connections match configuration in `config.py`
- Verify GPIO pins are set as outputs

#### Buttons Not Responding
- Verify buttons are wired correctly (pin to button, button to GND)
- Check that buttons are only active after payment approval
- Verify pull-up resistors are enabled (handled automatically in code)
- Check button pin assignments in `config.py`
- Monitor console output for button state changes

#### Payment Gateway Not Communicating
- **Raspberry Pi**: Verify serial port in `config.py` matches your connection
- **Arduino**: Verify RX/TX connections (A5=RX, A4=TX)
- Check baud rate is 9600 (configured in `config.py`)
- Ensure common GND between Raspberry Pi/Arduino and payment gateway
- Monitor console output for MDB frame errors
- Try different serial ports if using USB-to-TTL adapter

#### Relays Not Activating
- Check relay module power supply
- Verify relay control pins are correct in `config.py`
- Test relays independently
- Check relay duration (2.5 seconds default, configurable in `config.py`)
- Ensure GPIO pins can provide enough current (may need transistor drivers)

## Safety Notes

- Ensure proper power supply for relay modules
- Use appropriate relay ratings for your dispenser pumps/valves
- Keep payment gateway connections secure
- Test thoroughly before deployment

## License

This project is provided as-is for educational and commercial use.

## File Structure

```
arduino-perfume-dispenser/
├── perfume_dispenser.py    # Main Python script for Raspberry Pi
├── config.py               # Configuration file (pins, settings)
├── requirements.txt        # Python dependencies
├── src/
│   └── main.cpp           # Arduino C++ code (legacy)
├── platformio.ini         # PlatformIO configuration for Arduino
└── README.md              # This file
```

## Migration from Arduino to Raspberry Pi

If migrating from Arduino to Raspberry Pi:

1. **Hardware Changes**:
   - Replace Arduino with Raspberry Pi 4B
   - Update wiring to use GPIO pins (see pin configuration above)
   - Use hardware UART or USB-to-TTL adapter for payment gateway

2. **Software Changes**:
   - Install Python dependencies: `pip3 install -r requirements.txt`
   - Configure pins in `config.py` to match your wiring
   - Update serial port in `config.py` if needed
   - Run: `sudo python3 perfume_dispenser.py`

3. **Pin Mapping Reference**:
   - Arduino pins → Raspberry Pi GPIO pins (configure in `config.py`)
   - Arduino SoftwareSerial → Raspberry Pi UART or USB serial

## Author

Perfume Dispenser System - Raspberry Pi & Arduino Implementation

