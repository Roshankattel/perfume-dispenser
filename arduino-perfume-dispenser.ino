// Perfume Dispenser Arduino Sketch
// Arduino Uno Circuit Configuration

#include <Bounce2.h>

// Number of components
const int NUM_RELAYS = 5;
const int NUM_LEDS = 5;
const int NUM_BUTTONS = 5;

// Relay Pins Array
const int relayPins[NUM_RELAYS] = {A0, A1, A2, A3, 13};

// LED Pins Array
const int ledPins[NUM_LEDS] = {3, 5, 7, 9, 11};

// Button Pins Array (connected to ground when pressed)
const int buttonPins[NUM_BUTTONS] = {2, 4, 6, 8, 10};

// Bounce objects for debouncing
Bounce buttons[NUM_BUTTONS];

// Timer variables for relay control
unsigned long relayStartTime[NUM_RELAYS] = {0, 0, 0, 0, 0};
bool relayActive[NUM_RELAYS] = {false, false, false, false, false};
const unsigned long RELAY_DURATION = 3000; // 3 seconds in milliseconds

// LED Flashing control variables
bool ledFlashingEnabled = true; // Variable to control LED flashing
unsigned long lastFlashTime = 0;
bool ledFlashState = false;
const unsigned long FLASH_INTERVAL = 500; // Flash every 500ms

// State control
bool dispensing = false; // Flag to indicate if system is currently dispensing

void setup()
{
    // Initialize serial communication for debugging
    Serial.begin(9600);

    // Configure all relay pins as OUTPUT and turn them OFF
    for (int i = 0; i < NUM_RELAYS; i++)
    {
        pinMode(relayPins[i], OUTPUT);
        digitalWrite(relayPins[i], LOW);
    }

    // Configure all LED pins as OUTPUT and turn them OFF
    for (int i = 0; i < NUM_LEDS; i++)
    {
        pinMode(ledPins[i], OUTPUT);
        digitalWrite(ledPins[i], LOW);
    }

    // Configure all button pins with INPUT_PULLUP and attach Bounce
    for (int i = 0; i < NUM_BUTTONS; i++)
    {
        buttons[i].attach(buttonPins[i], INPUT_PULLUP);
        buttons[i].interval(25); // 25ms debounce interval
    }

    // Startup animation - Flash all LEDs
    flashAllLEDs();

    Serial.println("Setup complete - System ready!");
}

void loop()
{
    // Handle LED flashing when not dispensing
    if (ledFlashingEnabled && !dispensing)
    {
        if (millis() - lastFlashTime >= FLASH_INTERVAL)
        {
            ledFlashState = !ledFlashState;
            lastFlashTime = millis();

            // Toggle all LEDs
            for (int i = 0; i < NUM_LEDS; i++)
            {
                digitalWrite(ledPins[i], ledFlashState ? HIGH : LOW);
            }
        }
    }

    // Update all button states
    for (int i = 0; i < NUM_BUTTONS; i++)
    {
        buttons[i].update();
    }

    // Only process button presses if not currently dispensing
    if (!dispensing)
    {
        // Count how many buttons are currently pressed
        int pressedCount = 0;
        int pressedIndex = -1;

        for (int i = 0; i < NUM_BUTTONS; i++)
        {
            if (buttons[i].read() == LOW) // Button is pressed (active LOW)
            {
                pressedCount++;
                pressedIndex = i;
            }
        }

        // Only activate if exactly one button is pressed
        if (pressedCount == 1 && pressedIndex >= 0)
        {
            // Check for falling edge (button just pressed)
            if (buttons[pressedIndex].fell())
            {
                activateDispenser(pressedIndex);
            }
        }
    }

    // Check if any relay needs to be turned off after 3 seconds
    for (int i = 0; i < NUM_RELAYS; i++)
    {
        if (relayActive[i])
        {
            if (millis() - relayStartTime[i] >= RELAY_DURATION)
            {
                deactivateDispenser(i);
            }
        }
    }
}

// Function to activate a dispenser (LED + Relay)
void activateDispenser(int index)
{
    // Only activate if not already active
    if (!relayActive[index])
    {
        // Stop flashing and set dispensing state
        dispensing = true;

        // Turn off all LEDs first
        for (int i = 0; i < NUM_LEDS; i++)
        {
            digitalWrite(ledPins[i], LOW);
        }

        // Activate the selected dispenser
        digitalWrite(ledPins[index], HIGH);
        digitalWrite(relayPins[index], HIGH);
        relayActive[index] = true;
        relayStartTime[index] = millis();

        Serial.print("Dispenser ");
        Serial.print(index + 1);
        Serial.println(" activated");
    }
}

// Function to deactivate a dispenser (LED + Relay)
void deactivateDispenser(int index)
{
    digitalWrite(ledPins[index], LOW);
    digitalWrite(relayPins[index], LOW);
    relayActive[index] = false;

    // Resume flashing after dispensing is complete
    dispensing = false;
    lastFlashTime = millis(); // Reset flash timer

    Serial.print("Dispenser ");
    Serial.print(index + 1);
    Serial.println(" deactivated - Resuming LED flashing");
}

// Startup animation - Flash all LEDs
void flashAllLEDs()
{
    // Flash 3 times
    for (int flash = 0; flash < 3; flash++)
    {
        // Turn all LEDs ON
        for (int i = 0; i < NUM_LEDS; i++)
        {
            digitalWrite(ledPins[i], HIGH);
        }
        delay(200);

        // Turn all LEDs OFF
        for (int i = 0; i < NUM_LEDS; i++)
        {
            digitalWrite(ledPins[i], LOW);
        }
        delay(200);
    }
}
