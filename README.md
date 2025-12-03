# Perfume Dispenser System

An Arduino-based vending machine system for dispensing perfumes with integrated card payment support via MDB (Multi-Drop Bus) protocol. The system supports 5 different perfume selections with visual LED indicators and button-based selection interface.

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

- **Arduino Uno** (or compatible)
- **5x Relay Modules** (for controlling dispensers)
- **5x LEDs** (for visual indicators)
- **5x Push Buttons** (for item selection)
- **Nayax Payment Gateway** (MDB protocol compatible)
- **Resistors** (for LEDs and pull-up resistors for buttons)
- **Power Supply** (appropriate for relays and Arduino)

## Pin Connections

### Relay Pins (Output)
Control the dispenser pumps/valves:
- Relay 1: **A0**
- Relay 2: **A1**
- Relay 3: **A2**
- Relay 4: **A3**
- Relay 5: **12**

### LED Pins (Output)
Visual indicators for each dispenser:
- LED 1: **3**
- LED 2: **5**
- LED 3: **7**
- LED 4: **9**
- LED 5: **11**

### Button Pins (Input with Pull-up)
Item selection buttons (active LOW):
- Button 1: **2**
- Button 2: **4**
- Button 3: **6**
- Button 4: **8**
- Button 5: **10**

### Payment Gateway Serial (SoftwareSerial)
MDB protocol communication:
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

3   ───[220Ω]───► LED 1 ───► GND
5   ───[220Ω]───► LED 2 ───► GND
7   ───[220Ω]───► LED 3 ───► GND
9   ───[220Ω]───► LED 4 ───► GND
11  ───[220Ω]───► LED 5 ───► GND

2   ───[10kΩ]───► Button 1 ───► GND
4   ───[10kΩ]───► Button 2 ───► GND
6   ───[10kΩ]───► Button 3 ───► GND
8   ───[10kΩ]───► Button 4 ───► GND
10  ───[10kΩ]───► Button 5 ───► GND

A5  ────────────────► Payment Gateway TX
A4  ────────────────► Payment Gateway RX
GND ────────────────► Payment Gateway GND
```

**Note**: Buttons use internal pull-up resistors (INPUT_PULLUP), so they connect between the pin and GND. When pressed, the pin reads LOW.

## Software Setup

### Required Libraries

Install the following Arduino libraries:

1. **Bounce2** - For button debouncing
   - Install via Arduino Library Manager: `Bounce2` by Thomas O Fredericks

2. **SoftwareSerial** - Built-in Arduino library (no installation needed)

### Configuration

Key constants in the code that can be adjusted:

```cpp
const uint16_t ITEM_PRICE = 200;  // Price in cents ($2.00)
const unsigned long ITEM_SELECTION_TIMEOUT = 55000;  // 55 seconds
const unsigned long RELAY_DURATION = 3000;  // 3 seconds
const unsigned long POST_DISPENSE_DELAY = 2000;  // 2 seconds
const unsigned long FLASH_INTERVAL = 500;  // 500ms LED flash interval
```

### Upload Instructions

1. Connect Arduino Uno to your computer via USB
2. Open `perfumeDespenser.ino` in Arduino IDE
3. Select board: **Tools → Board → Arduino Uno**
4. Select port: **Tools → Port → [Your Arduino Port]**
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

### LEDs Not Working
- Check LED polarity (anode to pin via resistor, cathode to GND)
- Verify resistor values (220Ω recommended)
- Check pin connections match code

### Buttons Not Responding
- Verify buttons are wired correctly (pin to button, button to GND)
- Check that buttons are only active after payment approval
- Use serial monitor to see button state changes

### Payment Gateway Not Communicating
- Verify RX/TX connections (A5=RX, A4=TX)
- Check baud rate is 9600
- Ensure common GND between Arduino and payment gateway
- Monitor serial output for MDB frame errors

### Relays Not Activating
- Check relay module power supply
- Verify relay control pins are correct
- Test relays independently
- Check relay duration (3 seconds default)

## Safety Notes

- Ensure proper power supply for relay modules
- Use appropriate relay ratings for your dispenser pumps/valves
- Keep payment gateway connections secure
- Test thoroughly before deployment

## License

This project is provided as-is for educational and commercial use.

## Author

Perfume Dispenser System - Arduino Implementation

