"""
Configuration file for Raspberry Pi Perfume Dispenser
All pin assignments are configurable here
"""

# GPIO Pin Configuration (BCM numbering)
# Use BCM pin numbers (not physical pin numbers)
# Example: GPIO 18 = Physical pin 12

# Relay Pins (Output) - Control dispenser pumps/valves
# Set to HIGH to activate relay
RELAY_PINS = [4, 17, 27, 22, 5]  # GPIO pins for 5 relays

# LED Pins (Output) - Visual indicators for each dispenser
# Set to HIGH to turn LED on
LED_PINS = [26, 20, 8, 25, 23]  # GPIO pins for 5 LEDs

# Button Pins (Input with Pull-up) - Item selection buttons
# Reads LOW when pressed (active LOW)
BUTTON_PINS = [13, 21, 16, 7, 24]  # GPIO pins for 5 buttons

# TTL Serial Configuration for Payment Gateway (MDB Protocol)
# Raspberry Pi UART pins: GPIO 14 (TX), GPIO 15 (RX)
# For USB-to-TTL adapter, specify the device path 
TTL_SERIAL_PORT = '/dev/serial0'  # Default UART on Raspberry Pi
TTL_BAUD_RATE = 9600  # MDB protocol baud rate

# System Constants
ITEM_PRICE = 200  # Price in cents ($2.00)
ITEM_SELECTION_TIMEOUT = 55000  # 55 seconds in milliseconds
RELAY_DURATION = 1350  # 1.35 seconds in milliseconds (Perfume dispensing time)
POST_DISPENSE_DELAY = 2000  # 2 seconds in milliseconds
FLASH_INTERVAL = 500  # 500ms LED flash interval
NAYAX_TIMEOUT = 15000  # 15 seconds timeout for general operations
CARD_TAP_DELAY = 500  # Delay in ms before sending price after card tap
ASCII_TIMEOUT = 100  # 100ms timeout to process ASCII string
BUTTON_DEBOUNCE_INTERVAL = 25  # 25ms debounce interval for buttons

# Number of components
NUM_RELAYS = len(RELAY_PINS)
NUM_LEDS = len(LED_PINS)
NUM_BUTTONS = len(BUTTON_PINS)

# Validate configuration
if NUM_RELAYS != 5 or NUM_LEDS != 5 or NUM_BUTTONS != 5:
    raise ValueError("Configuration error: Must have exactly 5 relays, 5 LEDs, and 5 buttons")
