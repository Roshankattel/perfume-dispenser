#!/usr/bin/env python3
"""
Perfume Dispenser System for Raspberry Pi 4B
Converts Arduino code to Python with configurable GPIO pins
"""

import RPi.GPIO as GPIO
import serial
import time
import threading
import sys
from enum import Enum
from typing import List, Optional
import config

# Force unbuffered output for systemd logging
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# MDB Protocol State Machine
class MDBState(Enum):
    STATE_IDLE = 0
    STATE_WAIT_ENABLE_ACK = 1
    STATE_WAIT_CARD_TAP = 2
    STATE_WAIT_APPROVAL = 3
    STATE_WAIT_ITEM = 4
    STATE_VENDING = 5
    STATE_WAIT_CANCEL_ACK = 6
    STATE_ENDING = 7


class PerfumeDispenser:
    def __init__(self):
        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Pin assignments from config
        self.relay_pins = config.RELAY_PINS
        self.led_pins = config.LED_PINS
        self.button_pins = config.BUTTON_PINS
        
        # Setup GPIO pins
        self._setup_gpio()
        
        # Initialize serial communication for payment gateway
        try:
            self.payment_serial = serial.Serial(
                port=config.TTL_SERIAL_PORT,
                baudrate=config.TTL_BAUD_RATE,
                timeout=0.1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
        except Exception as e:
            print(f"Error opening serial port: {e}")
            print(f"Trying alternative port...")
            try:
                self.payment_serial = serial.Serial(
                    port='/dev/ttyUSB0',
                    baudrate=config.TTL_BAUD_RATE,
                    timeout=0.1
                )
            except Exception as e2:
                print(f"Error opening alternative serial port: {e2}")
                raise
        
        # State variables
        self.mdb_state = MDBState.STATE_WAIT_CARD_TAP
        self.dispensing = False
        self.led_flashing_enabled = False
        self.led_flash_state = False
        self.item_selection_timeout = False
        self.card_tapped = False
        self.waiting_to_end_session = False
        self.waiting_to_end_after_cancel = False
        
        # Timing variables
        self.last_flash_time = 0
        self.last_event_time = time.time() * 1000
        self.card_tap_time = 0
        self.dispense_complete_time = 0
        self.cancel_ack_time = 0
        self.relay_start_time = [0] * config.NUM_RELAYS
        self.relay_active = [False] * config.NUM_RELAYS
        
        # MDB communication variables
        self.mdb_rx_buffer = bytearray(8)
        self.mdb_rx_index = 0
        self.amount_cents = 0
        self.selected_item = 0
        
        # ASCII hex string parsing
        self.ascii_hex_buffer = bytearray(32)
        self.ascii_hex_index = 0
        self.last_ascii_byte_time = 0
        
        # Button state tracking
        self.button_states = [GPIO.HIGH] * config.NUM_BUTTONS
        self.button_last_state = [GPIO.HIGH] * config.NUM_BUTTONS
        self.button_last_change_time = [0] * config.NUM_BUTTONS
        
        # Threading
        self.running = True
        self.serial_thread = None
        
        # Initial startup logs - flush immediately for systemd
        print("=" * 50, flush=True)
        print("Perfume Dispenser System - Starting Up", flush=True)
        print("=" * 50, flush=True)
        print(f"Relay pins: {self.relay_pins}", flush=True)
        print(f"LED pins: {self.led_pins}", flush=True)
        print(f"Button pins: {self.button_pins}", flush=True)
        print(f"Serial port: {config.TTL_SERIAL_PORT}", flush=True)
        print(f"Baud rate: {config.TTL_BAUD_RATE}", flush=True)
        print("=" * 50, flush=True)
    
    def _setup_gpio(self):
        """Configure all GPIO pins"""
        # Setup relay pins as outputs, set to LOW (relay off)
        for pin in self.relay_pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        
        # Setup LED pins as outputs, set to LOW (LED off)
        for pin in self.led_pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        
        # Setup button pins as inputs with pull-up resistors
        for pin in self.button_pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    def flash_all_leds(self):
        """Startup animation - Flash all LEDs 3 times"""
        for flash in range(3):
            # Turn all LEDs ON
            for pin in self.led_pins:
                GPIO.output(pin, GPIO.HIGH)
            time.sleep(0.2)
            
            # Turn all LEDs OFF
            for pin in self.led_pins:
                GPIO.output(pin, GPIO.LOW)
            time.sleep(0.2)
    
    def activate_dispenser(self, index: int):
        """Activate a dispenser (LED + Relay)"""
        if index < 0 or index >= config.NUM_RELAYS:
            return
        
        # Only activate if not already active
        if not self.relay_active[index]:
            # Stop flashing and set dispensing state
            self.dispensing = True
            self.mdb_state = MDBState.STATE_VENDING
            
            # Turn off all LEDs first
            for pin in self.led_pins:
                GPIO.output(pin, GPIO.LOW)
            
            # Activate the selected dispenser
            GPIO.output(self.led_pins[index], GPIO.HIGH)
            GPIO.output(self.relay_pins[index], GPIO.HIGH)
            self.relay_active[index] = True
            self.relay_start_time[index] = time.time() * 1000
            
            print(f"Dispenser {index + 1} activated - Vending in progress")
    
    def deactivate_dispenser(self, index: int):
        """Deactivate a dispenser (LED + Relay)"""
        if index < 0 or index >= config.NUM_RELAYS:
            return
        
        GPIO.output(self.led_pins[index], GPIO.LOW)
        GPIO.output(self.relay_pins[index], GPIO.LOW)
        self.relay_active[index] = False
        
        print(f"Dispenser {index + 1} deactivated")
        
        # Wait for delay before ending session
        if self.mdb_state == MDBState.STATE_VENDING:
            self.dispensing = False
            self.waiting_to_end_session = True
            self.dispense_complete_time = time.time() * 1000
            print(f"Vending complete - Waiting {config.POST_DISPENSE_DELAY}ms before ending session")
    
    def hex_char_to_nibble(self, c: int) -> int:
        """Convert ASCII hex character to nibble (0-15)"""
        if 48 <= c <= 57:  # '0' to '9'
            return c - 48
        if 65 <= c <= 70:  # 'A' to 'F'
            return c - 65 + 10
        if 97 <= c <= 102:  # 'a' to 'f'
            return c - 97 + 10
        return 0
    
    def parse_ascii_hex_string(self, data: bytes, length: int):
        """Convert ASCII hex string to binary bytes"""
        byte_value = 0
        has_first_nibble = False
        self.mdb_rx_index = 0
        
        print(f"Parsing ASCII hex: {data[:length].decode('ascii', errors='ignore')}")
        
        for i in range(length):
            if i >= 32 or self.mdb_rx_index >= 8:
                break
            
            c = data[i]
            
            # Skip spaces, newlines, carriage returns
            if c in (32, 10, 13, 9):  # space, newline, carriage return, tab
                continue
            
            # Check if it's a hex character
            if ((48 <= c <= 57) or   # '0' to '9'
                (65 <= c <= 70) or   # 'A' to 'F'
                (97 <= c <= 102)):   # 'a' to 'f'
                
                nibble = self.hex_char_to_nibble(c)
                
                if not has_first_nibble:
                    byte_value = nibble << 4
                    has_first_nibble = True
                else:
                    byte_value |= nibble
                    self.mdb_rx_buffer[self.mdb_rx_index] = byte_value
                    self.mdb_rx_index += 1
                    has_first_nibble = False
        
        # Handle trailing single nibble
        if has_first_nibble and self.mdb_rx_index < 8:
            self.mdb_rx_buffer[self.mdb_rx_index] = byte_value
            self.mdb_rx_index += 1
        
        # Debug: Print converted bytes
        if self.mdb_rx_index > 0:
            print("Converted to bytes: ", end="")
            for i in range(self.mdb_rx_index):
                print(f"{self.mdb_rx_buffer[i]:02X} ", end="")
            print()
        
        # Handle single byte ACK (0x00)
        if self.mdb_rx_index == 1 and self.mdb_rx_buffer[0] == 0x00:
            self.mdb_rx_buffer[0] = 0x10
            self.mdb_rx_buffer[1] = 0x00
            self.mdb_rx_index = 2
            self.process_mdb_frame()
        # If we have a complete frame, process it
        elif self.mdb_rx_index >= 2:
            cmd = self.mdb_rx_buffer[1]
            frame_len = self.get_mdb_frame_length(cmd)
            if self.mdb_rx_index >= frame_len:
                self.process_mdb_frame()
            else:
                print(f"Incomplete frame: got {self.mdb_rx_index} bytes, need {frame_len}")
        elif self.mdb_rx_index > 0:
            print("Frame too short")
    
    def get_mdb_frame_length(self, cmd: int) -> int:
        """Get expected frame length based on MDB command"""
        if cmd == 0x00:
            return 2  # ACK
        elif cmd == 0x03:
            return 4  # Card tap
        elif cmd == 0x04:
            return 2  # Timeout
        elif cmd == 0x05:
            return 4  # Approved
        elif cmd == 0x06:
            return 2  # Rejected
        else:
            return 2  # Default minimum
    
    def print_state_name(self, state: MDBState):
        """Print state name for debugging"""
        state_names = {
            MDBState.STATE_IDLE: "IDLE",
            MDBState.STATE_WAIT_ENABLE_ACK: "WAIT_ENABLE_ACK",
            MDBState.STATE_WAIT_CARD_TAP: "WAIT_CARD_TAP",
            MDBState.STATE_WAIT_APPROVAL: "WAIT_APPROVAL",
            MDBState.STATE_WAIT_ITEM: "WAIT_ITEM",
            MDBState.STATE_VENDING: "VENDING",
            MDBState.STATE_WAIT_CANCEL_ACK: "WAIT_CANCEL_ACK",
            MDBState.STATE_ENDING: "ENDING"
        }
        print(state_names.get(state, "UNKNOWN"), end="")
    
    def process_mdb_frame(self):
        """Process complete MDB frame"""
        if self.mdb_rx_index < 2:
            return
        
        cmd = self.mdb_rx_buffer[1]
        self.last_event_time = time.time() * 1000
        
        # Debug: Print received frame
        print("RX: ", end="")
        for i in range(self.mdb_rx_index):
            print(f"{self.mdb_rx_buffer[i]:02X} ", end="")
        print(f"| State: ", end="")
        self.print_state_name(self.mdb_state)
        print()
        
        # Parse based on command and current state
        if cmd == 0x00:  # ACK responses
            if self.mdb_state == MDBState.STATE_WAIT_APPROVAL and self.mdb_rx_index == 2:
                print("Amount command acknowledged - waiting for approval")
            elif self.mdb_state == MDBState.STATE_VENDING:
                print("Vend item acknowledged")
        
        elif cmd == 0x03:  # Card tap event
            print(f"Card tap detected! Current state: ", end="")
            self.print_state_name(self.mdb_state)
            print(f", Frame length: {self.mdb_rx_index}")
            
            if self.mdb_rx_index >= 4:
                if self.mdb_state in (MDBState.STATE_WAIT_CARD_TAP, MDBState.STATE_IDLE):
                    print("Card tapped - will send price automatically after delay")
                    self.mdb_state = MDBState.STATE_WAIT_APPROVAL
                    self.card_tapped = True
                    self.card_tap_time = time.time() * 1000
                    print(f"cardTapped flag set, will send price in {config.CARD_TAP_DELAY}ms")
                else:
                    print("Card tap ignored - wrong state: ", end="")
                    self.print_state_name(self.mdb_state)
                    print()
            else:
                print(f"Card tap frame too short: {self.mdb_rx_index}")
        
        elif cmd == 0x05:  # Payment approved
            if self.mdb_state == MDBState.STATE_WAIT_APPROVAL and self.mdb_rx_index >= 4:
                # Extract amount: format is 10 05 00 0A
                approved_amount = (self.mdb_rx_buffer[2] << 8) | self.mdb_rx_buffer[3]
                print(f"Payment approved: ${approved_amount / 100.0:.2f}")
                
                self.mdb_state = MDBState.STATE_WAIT_ITEM
                self.led_flashing_enabled = True
                self.card_tapped = False
                self.item_selection_timeout = False
                self.last_event_time = time.time() * 1000
                print(f"Waiting for item selection (timeout: {config.ITEM_SELECTION_TIMEOUT / 1000} seconds)...")
        
        elif cmd == 0x06:  # Payment rejected
            if self.mdb_state == MDBState.STATE_WAIT_APPROVAL:
                print("Payment rejected - waiting for timeout")
                self.card_tapped = False
                self.led_flashing_enabled = False
                # Turn off all LEDs
                for pin in self.led_pins:
                    GPIO.output(pin, GPIO.LOW)
        
        elif cmd == 0x04:  # Timeout from Nayax
            print("NAYAX timeout received")
            if self.mdb_state == MDBState.STATE_WAIT_APPROVAL:
                self.end_session()
            elif self.mdb_state == MDBState.STATE_WAIT_ITEM:
                self.item_selection_timeout = True
                print("Nayax timeout received - will not send vend command if item selected")
                print("Continuing to wait for full timeout period or user selection...")
    
    def handle_nayax(self):
        """Main MDB handler - processes serial data"""
        current_time = time.time() * 1000
        
        # Check for ASCII hex string timeout
        if self.ascii_hex_index > 0 and (current_time - self.last_ascii_byte_time > config.ASCII_TIMEOUT):
            # Timeout - process accumulated ASCII data
            self.parse_ascii_hex_string(bytes(self.ascii_hex_buffer[:self.ascii_hex_index]), self.ascii_hex_index)
            self.ascii_hex_index = 0
        
        # Read incoming MDB frames
        while self.payment_serial.in_waiting > 0:
            byte = self.payment_serial.read(1)[0]
            
            # Check if it's ASCII character (likely hex string mode)
            if (0x20 <= byte <= 0x7E) or byte in (10, 13, 9, 32):  # printable ASCII or control chars
                # ASCII character - treat as hex string input
                if byte in (10, 13):  # newline or carriage return
                    # Check for cancel vend ACK: "00 \r\n"
                    if self.mdb_state == MDBState.STATE_WAIT_CANCEL_ACK and self.ascii_hex_index >= 2:
                        if self.ascii_hex_buffer[0] == 48 and self.ascii_hex_buffer[1] == 48:  # '0' = 48
                            print("Cancel vend ACK received (00)")
                            self.waiting_to_end_after_cancel = True
                            self.cancel_ack_time = time.time() * 1000
                            self.ascii_hex_index = 0
                        elif self.ascii_hex_index > 0:
                            self.parse_ascii_hex_string(bytes(self.ascii_hex_buffer[:self.ascii_hex_index]), self.ascii_hex_index)
                            self.ascii_hex_index = 0
                    elif self.ascii_hex_index > 0:
                        self.parse_ascii_hex_string(bytes(self.ascii_hex_buffer[:self.ascii_hex_index]), self.ascii_hex_index)
                        self.ascii_hex_index = 0
                elif self.ascii_hex_index < 31:
                    self.ascii_hex_buffer[self.ascii_hex_index] = byte
                    self.ascii_hex_index += 1
                    self.last_ascii_byte_time = current_time
                    
                    if self.ascii_hex_index >= 31:
                        self.parse_ascii_hex_string(bytes(self.ascii_hex_buffer[:self.ascii_hex_index]), self.ascii_hex_index)
                        self.ascii_hex_index = 0
            else:
                # Binary byte mode - original MDB protocol
                if self.ascii_hex_index > 0:
                    self.parse_ascii_hex_string(bytes(self.ascii_hex_buffer[:self.ascii_hex_index]), self.ascii_hex_index)
                    self.ascii_hex_index = 0
                
                # Handle single byte ACK (0x00)
                if byte == 0x00 and self.mdb_rx_index == 0:
                    self.mdb_rx_buffer[0] = 0x10
                    self.mdb_rx_buffer[1] = 0x00
                    self.mdb_rx_index = 2
                    self.process_mdb_frame()
                    self.mdb_rx_index = 0
                # MDB frames start with 0x10
                elif byte == 0x10:
                    self.mdb_rx_index = 0
                    self.mdb_rx_buffer[self.mdb_rx_index] = byte
                    self.mdb_rx_index += 1
                elif self.mdb_rx_index > 0 and self.mdb_rx_index < 8:
                    self.mdb_rx_buffer[self.mdb_rx_index] = byte
                    self.mdb_rx_index += 1
                    
                    if self.mdb_rx_index >= 2:
                        cmd = self.mdb_rx_buffer[1]
                        frame_len = self.get_mdb_frame_length(cmd)
                        if self.mdb_rx_index >= frame_len:
                            self.process_mdb_frame()
                            self.mdb_rx_index = 0
                else:
                    self.mdb_rx_index = 0
    
    def send_mdb_frame(self, data: List[int]):
        """Send MDB frame to payment gateway"""
        # Debug: Print command being sent
        print("TX: ", end="")
        for byte in data:
            print(f"{byte:02X} ", end="")
        print(f"| State: ", end="")
        self.print_state_name(self.mdb_state)
        print()
        
        # Send the MDB frame bytes
        self.payment_serial.write(bytes(data))
        time.sleep(0.0005)  # Small delay to ensure transmission completes
    
    def send_select_amount(self, cents: int):
        """Send Select Amount command"""
        self.amount_cents = cents
        high_byte = (cents >> 8) & 0xFF
        low_byte = cents & 0xFF
        
        if high_byte == 0:
            cmd = [0x13, 0x00, 0x00, low_byte, 0x00, 0x01]
        else:
            cmd = [0x13, 0x00, 0x00, high_byte, low_byte, 0x00, 0x01]
        
        self.send_mdb_frame(cmd)
        print(f"TX: Select Amount ${cents / 100.0:.2f}")
    
    def send_vend_item(self, item_number: int, button_index: int):
        """Send Vend Item command"""
        if self.mdb_state != MDBState.STATE_WAIT_ITEM:
            return
        if item_number < 1 or item_number > 5:
            return
        if button_index >= config.NUM_BUTTONS:
            return
        
        self.selected_item = item_number
        
        # Check if Nayax timeout occurred
        if self.item_selection_timeout:
            print("Nayax timeout occurred earlier - dispensing without sending vend command to Nayax")
            print(f"Dispensing item {item_number}")
            self.mdb_state = MDBState.STATE_VENDING
            self.last_event_time = time.time() * 1000
            self.activate_dispenser(button_index)
            return
        
        # Normal flow: send vend command to Nayax and activate dispenser
        cmd = [0x13, 0x02, 0x00, item_number]
        self.send_mdb_frame(cmd)
        self.mdb_state = MDBState.STATE_VENDING
        self.last_event_time = time.time() * 1000
        
        print(f"TX: Vend Item {item_number}")
        
        # Activate dispenser immediately
        self.activate_dispenser(button_index)
    
    def send_cancel_vend(self):
        """Send Cancel Vend command"""
        if self.mdb_state != MDBState.STATE_WAIT_ITEM:
            return
        
        cmd = [0x13, 0x01]
        self.send_mdb_frame(cmd)
        self.mdb_state = MDBState.STATE_WAIT_CANCEL_ACK
        self.last_event_time = time.time() * 1000
        self.led_flashing_enabled = False
        
        # Turn off all LEDs
        for pin in self.led_pins:
            GPIO.output(pin, GPIO.LOW)
        
        print("TX: Cancel Vend")
    
    def end_session(self):
        """Send End Session command"""
        cmd = [0x13, 0x04]
        self.send_mdb_frame(cmd)
        self.mdb_state = MDBState.STATE_IDLE
        self.led_flashing_enabled = False
        self.amount_cents = 0
        self.selected_item = 0
        self.card_tapped = False
        self.waiting_to_end_session = False
        self.waiting_to_end_after_cancel = False
        self.dispensing = False
        self.item_selection_timeout = False
        print("TX: End Session")
        
        # Turn off all LEDs
        for pin in self.led_pins:
            GPIO.output(pin, GPIO.LOW)
    
    def update_buttons(self):
        """Update button states with debouncing"""
        current_time = time.time() * 1000
        
        for i in range(config.NUM_BUTTONS):
            pin = self.button_pins[i]
            current_state = GPIO.input(pin)
            
            # Debouncing logic
            if current_state != self.button_last_state[i]:
                self.button_last_change_time[i] = current_time
            
            if (current_time - self.button_last_change_time[i]) > config.BUTTON_DEBOUNCE_INTERVAL:
                if current_state != self.button_states[i]:
                    self.button_states[i] = current_state
            
            self.button_last_state[i] = current_state
    
    def run(self):
        """Main loop"""
        # Startup animation
        print("Running startup LED animation...", flush=True)
        self.flash_all_leds()
        
        print("=" * 50, flush=True)
        print("Setup complete - System ready!", flush=True)
        print("Waiting for card tap...", flush=True)
        print("=" * 50, flush=True)
        
        # Start serial reading thread
        self.serial_thread = threading.Thread(target=self._serial_reader_thread, daemon=True)
        self.serial_thread.start()
        
        try:
            while self.running:
                current_time = time.time() * 1000
                
                # Automatic price sending after card tap delay
                if self.card_tapped and self.mdb_state == MDBState.STATE_WAIT_APPROVAL:
                    elapsed = current_time - self.card_tap_time
                    if elapsed >= config.CARD_TAP_DELAY:
                        print(f"Sending price automatically: ${config.ITEM_PRICE / 100.0:.2f}")
                        self.send_select_amount(config.ITEM_PRICE)
                        self.card_tapped = False
                
                # Handle LED flashing
                if (self.led_flashing_enabled and not self.dispensing and 
                    self.mdb_state == MDBState.STATE_WAIT_ITEM):
                    if current_time - self.last_flash_time >= config.FLASH_INTERVAL:
                        self.led_flash_state = not self.led_flash_state
                        self.last_flash_time = current_time
                        
                        # Toggle all LEDs
                        for pin in self.led_pins:
                            GPIO.output(pin, GPIO.HIGH if self.led_flash_state else GPIO.LOW)
                # If in IDLE or WAIT_CARD_TAP state, turn all LEDs ON
                elif (self.mdb_state in (MDBState.STATE_IDLE, MDBState.STATE_WAIT_CARD_TAP) and 
                      not self.dispensing):
                    for pin in self.led_pins:
                        GPIO.output(pin, GPIO.HIGH)
                # If LEDs should be off
                elif (not self.led_flashing_enabled and not self.dispensing and 
                      self.mdb_state not in (MDBState.STATE_IDLE, MDBState.STATE_WAIT_CARD_TAP)):
                    for pin in self.led_pins:
                        GPIO.output(pin, GPIO.LOW)
                
                # Update button states
                self.update_buttons()
                
                # Handle button presses
                pressed_count = 0
                pressed_index = -1
                
                for i in range(config.NUM_BUTTONS):
                    if self.button_states[i] == GPIO.LOW:  # Button is pressed (active LOW)
                        pressed_count += 1
                        pressed_index = i
                
                # Only process if exactly one button is pressed, payment approved, and not dispensing
                if (pressed_count == 1 and pressed_index >= 0 and not self.dispensing and 
                    self.mdb_state == MDBState.STATE_WAIT_ITEM):
                    # Check for button press (falling edge)
                    if (self.button_states[pressed_index] == GPIO.LOW and 
                        self.button_last_state[pressed_index] == GPIO.HIGH):
                        item_number = pressed_index + 1
                        self.send_vend_item(item_number, pressed_index)
                
                # Check if any relay needs to be turned off after duration
                for i in range(config.NUM_RELAYS):
                    if self.relay_active[i]:
                        if current_time - self.relay_start_time[i] >= config.RELAY_DURATION:
                            self.deactivate_dispenser(i)
                
                # Check if delay has passed after dispensing before ending session
                if (self.waiting_to_end_session and 
                    (current_time - self.dispense_complete_time >= config.POST_DISPENSE_DELAY)):
                    self.waiting_to_end_session = False
                    self.end_session()
                    print("Post-dispense delay complete - Session ended")
                
                # Handle MDB timeout
                if self.mdb_state not in (MDBState.STATE_IDLE, MDBState.STATE_VENDING, 
                                         MDBState.STATE_WAIT_CANCEL_ACK):
                    timeout_duration = (config.ITEM_SELECTION_TIMEOUT 
                                      if self.mdb_state == MDBState.STATE_WAIT_ITEM 
                                      else config.NAYAX_TIMEOUT)
                    
                    if current_time - self.last_event_time > timeout_duration:
                        if self.mdb_state == MDBState.STATE_WAIT_ITEM:
                            print(f"Item selection timeout ({timeout_duration / 1000}s) - Sending cancel vend")
                            self.send_cancel_vend()
                        else:
                            print(f"MDB timeout ({timeout_duration / 1000}s) - Ending session")
                            self.item_selection_timeout = True
                            self.end_session()
                
                # Check if delay has passed after cancel ACK before ending session
                if (self.waiting_to_end_after_cancel and 
                    (current_time - self.cancel_ack_time >= config.POST_DISPENSE_DELAY)):
                    self.waiting_to_end_after_cancel = False
                    self.end_session()
                    print("Post-cancel delay complete - Session ended")
                
                time.sleep(0.01)  # Small delay to prevent CPU spinning
                
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.running = False
        finally:
            self.cleanup()
    
    def _serial_reader_thread(self):
        """Thread for reading serial data"""
        while self.running:
            try:
                self.handle_nayax()
                time.sleep(0.001)  # Small delay
            except Exception as e:
                print(f"Serial thread error: {e}")
                time.sleep(0.1)
    
    def cleanup(self):
        """Cleanup GPIO and serial on exit"""
        print("Cleaning up...")
        self.running = False
        
        # Turn off all relays and LEDs
        for pin in self.relay_pins:
            GPIO.output(pin, GPIO.LOW)
        for pin in self.led_pins:
            GPIO.output(pin, GPIO.LOW)
        
        # Close serial port
        if self.payment_serial and self.payment_serial.is_open:
            self.payment_serial.close()
        
        # Cleanup GPIO
        GPIO.cleanup()
        print("Cleanup complete", flush=True)


def main():
    """Main entry point"""
    print("=" * 50, flush=True)
    print("Perfume Dispenser System - Main Entry Point", flush=True)
    print("=" * 50, flush=True)
    
    try:
        dispenser = PerfumeDispenser()
        dispenser.run()
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt - shutting down gracefully...", flush=True)
    except Exception as e:
        print(f"Fatal error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        if 'dispenser' in locals():
            dispenser.cleanup()
    finally:
        print("Perfume Dispenser System - Exiting", flush=True)


if __name__ == "__main__":
    main()
