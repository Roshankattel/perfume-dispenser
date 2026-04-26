#!/usr/bin/env python3
"""
Button Hardware Test Script
Tests all 5 button GPIO pins independently of the main application.
Run this to verify wiring and pull-up/pull-down configuration.

Usage:
    python3 test_buttons.py            # Default: pull-up (buttons connect to GND)
    python3 test_buttons.py pulldown   # Pull-down mode (buttons connect to 3.3V)
    python3 test_buttons.py raw        # Show raw pin state every second (no edge detect)
"""

import RPi.GPIO as GPIO
import time
import sys

# ── Button pins from config ───────────────────────────────────────────────────
BUTTON_PINS = [13, 21, 16, 7, 24]
BUTTON_NAMES = ["Button 1 (GPIO 13)",
                "Button 2 (GPIO 21)",
                "Button 3 (GPIO 16)",
                "Button 4 (GPIO  7)",
                "Button 5 (GPIO 24)"]

DEBOUNCE_MS = 50  # milliseconds


def setup(mode: str):
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    if mode == "pulldown":
        pud = GPIO.PUD_DOWN
        trigger_state = GPIO.HIGH
        print("Mode: PULL-DOWN  (buttons should connect pin → 3.3V when pressed)")
    else:
        pud = GPIO.PUD_UP
        trigger_state = GPIO.LOW
        print("Mode: PULL-UP    (buttons should connect pin → GND when pressed)")

    for pin in BUTTON_PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=pud)

    return trigger_state


def test_edge_detection(trigger_state: int):
    """Detect button presses using edge detection callbacks."""
    print("\n─── Edge detection mode ─────────────────────────────────────────")
    print("Press any button. Press Ctrl+C to quit.\n")

    edge = GPIO.FALLING if trigger_state == GPIO.LOW else GPIO.RISING

    def make_callback(idx):
        def callback(channel):
            # Read pin again after debounce window to reject noise
            time.sleep(DEBOUNCE_MS / 1000)
            if GPIO.input(channel) == trigger_state:
                print(f"  ✓ PRESSED  → {BUTTON_NAMES[idx]}  (GPIO {channel})",
                      flush=True)
        return callback

    release_edge = GPIO.RISING if trigger_state == GPIO.LOW else GPIO.FALLING

    def make_release_callback(idx):
        def callback(channel):
            time.sleep(DEBOUNCE_MS / 1000)
            if GPIO.input(channel) != trigger_state:
                print(f"  ↑ released → {BUTTON_NAMES[idx]}  (GPIO {channel})",
                      flush=True)
        return callback

    for i, pin in enumerate(BUTTON_PINS):
        GPIO.add_event_detect(pin, edge,
                              callback=make_callback(i),
                              bouncetime=DEBOUNCE_MS)
        GPIO.add_event_detect(pin, release_edge,
                              callback=make_release_callback(i),
                              bouncetime=DEBOUNCE_MS)

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass


def test_polling(trigger_state: int):
    """Poll all pins in a tight loop and print state changes."""
    print("\n─── Polling mode ────────────────────────────────────────────────")
    print("Press any button. Press Ctrl+C to quit.\n")

    prev_states = [GPIO.input(p) for p in BUTTON_PINS]
    last_change = [0.0] * len(BUTTON_PINS)

    # Print initial state
    print("Initial pin states:")
    for i, pin in enumerate(BUTTON_PINS):
        state = GPIO.input(pin)
        label = "PRESSED" if state == trigger_state else "released"
        print(f"  {BUTTON_NAMES[i]:30s} → {state}  ({label})")
    print()

    try:
        while True:
            now = time.time()
            for i, pin in enumerate(BUTTON_PINS):
                state = GPIO.input(pin)
                if state != prev_states[i] and (now - last_change[i]) > DEBOUNCE_MS / 1000:
                    last_change[i] = now
                    if state == trigger_state:
                        print(f"  ✓ PRESSED  → {BUTTON_NAMES[i]}  (raw={state})",
                              flush=True)
                    else:
                        print(f"  ↑ released → {BUTTON_NAMES[i]}  (raw={state})",
                              flush=True)
                    prev_states[i] = state
            time.sleep(0.005)
    except KeyboardInterrupt:
        pass


def test_raw_snapshot():
    """Print a snapshot of all pin readings every second (no pull resistor assumed)."""
    print("\n─── Raw snapshot mode (prints every second) ─────────────────────")
    print("GPIO BCM | Name                           | Raw value")
    print("-" * 56)
    print("Press Ctrl+C to quit.\n")

    # Try both pull-up and pull-down and show both readings
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    try:
        while True:
            row = []
            for i, pin in enumerate(BUTTON_PINS):
                # Read with pull-up
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                val_up = GPIO.input(pin)
                # Read with pull-down
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                val_dn = GPIO.input(pin)
                row.append((pin, BUTTON_NAMES[i], val_up, val_dn))

            print(f"\n[{time.strftime('%H:%M:%S')}]")
            print(f"  {'GPIO':>5}  {'Name':<30}  PUD_UP  PUD_DOWN")
            for pin, name, vu, vd in row:
                note = ""
                if vu == 0:
                    note = "  ← likely pressed (active LOW)"
                elif vd == 1:
                    note = "  ← likely pressed (active HIGH)"
                print(f"  {pin:>5}  {name:<30}  {vu}       {vd}{note}")

            time.sleep(1)
    except KeyboardInterrupt:
        pass


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "pullup"

    print("=" * 58)
    print("  Perfume Dispenser — Button Hardware Test")
    print("=" * 58)
    print(f"Button pins (BCM): {BUTTON_PINS}")
    print()

    try:
        if mode == "raw":
            test_raw_snapshot()
        else:
            trigger_state = setup(mode)
            test_polling(trigger_state)
    finally:
        GPIO.cleanup()
        print("\nGPIO cleaned up. Bye!")


if __name__ == "__main__":
    main()
