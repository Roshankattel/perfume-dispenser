// Perfume Dispenser Arduino Sketch
// Arduino Uno Circuit Configuration

#include <Bounce2.h>
#include <EEPROM.h>

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
// IMPORTANT: This variable controls the operating mode:
//   - ledFlashingEnabled = true  → NORMAL MODE: LEDs flash, buttons dispense perfume
//   - ledFlashingEnabled = false → RESET MODE: Hold button for 30s to reset counter
bool ledFlashingEnabled = true; // Variable to control LED flashing and operating mode
unsigned long lastFlashTime = 0;
bool ledFlashState = false;
const unsigned long FLASH_INTERVAL = 500; // Flash every 500ms

// State control
bool dispensing = false; // Flag to indicate if system is currently dispensing

// Button press limit tracking
const int MAX_BUTTON_PRESSES = 100;                                         // Maximum presses allowed per button (changeable)
int buttonPressCount[NUM_BUTTONS] = {0, 0, 0, 0, 0};                        // Current press count for each button
bool buttonLimitReached[NUM_BUTTONS] = {false, false, false, false, false}; // Track if limit reached

// EEPROM addresses for storing button press counts (each int takes 2 bytes)
const int EEPROM_BUTTON_0 = 0;
const int EEPROM_BUTTON_1 = 2;
const int EEPROM_BUTTON_2 = 4;
const int EEPROM_BUTTON_3 = 6;
const int EEPROM_BUTTON_4 = 8;
const int EEPROM_ADDRESSES[NUM_BUTTONS] = {EEPROM_BUTTON_0, EEPROM_BUTTON_1, EEPROM_BUTTON_2, EEPROM_BUTTON_3, EEPROM_BUTTON_4};

// Button hold tracking for reset functionality (30 seconds)
unsigned long buttonHoldStartTime[NUM_BUTTONS] = {0, 0, 0, 0, 0};
bool buttonBeingHeld[NUM_BUTTONS] = {false, false, false, false, false};
const unsigned long RESET_HOLD_DURATION = 30000; // 30 seconds in milliseconds

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

    // Load button press counts from EEPROM
    loadButtonPressCountsFromEEPROM();

    // Startup animation - Flash all LEDs
    flashAllLEDs();

    Serial.println("Setup complete - System ready!");
    printButtonStatus();
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

            // Toggle only LEDs that haven't reached their limit
            for (int i = 0; i < NUM_LEDS; i++)
            {
                if (!buttonLimitReached[i])
                {
                    digitalWrite(ledPins[i], ledFlashState ? HIGH : LOW);
                }
                else
                {
                    // Keep LED OFF if limit reached
                    digitalWrite(ledPins[i], LOW);
                }
            }
        }
    }

    // Update all button states
    for (int i = 0; i < NUM_BUTTONS; i++)
    {
        buttons[i].update();
    }

    // Check for button hold (30 seconds) to reset counter
    // ONLY WORKS when ledFlashingEnabled is DISABLED (false)
    // When ledFlashingEnabled is true, buttons work normally for dispensing
    if (!ledFlashingEnabled)
    {
        for (int i = 0; i < NUM_BUTTONS; i++)
        {
            if (buttons[i].read() == LOW) // Button is being held
            {
                if (!buttonBeingHeld[i])
                {
                    // Button just started being held
                    buttonBeingHeld[i] = true;
                    buttonHoldStartTime[i] = millis();

                    // Turn on LED to show hold is detected
                    digitalWrite(ledPins[i], HIGH);

                    Serial.print("Button ");
                    Serial.print(i + 1);
                    Serial.println(" hold detected - Hold for 30 seconds to reset...");
                }
                else
                {
                    // Show progress and blink LED while holding
                    unsigned long holdDuration = millis() - buttonHoldStartTime[i];

                    // Blink the LED to show progress (faster blink as time goes on)
                    if ((holdDuration / 250) % 2 == 0) // Blink every 250ms
                    {
                        digitalWrite(ledPins[i], HIGH);
                    }
                    else
                    {
                        digitalWrite(ledPins[i], LOW);
                    }

                    // Check if held for 30 seconds
                    if (holdDuration >= RESET_HOLD_DURATION)
                    {
                        resetButtonCounter(i);
                        buttonBeingHeld[i] = false; // Prevent multiple resets
                    }
                    else if (holdDuration % 5000 < 50) // Print every 5 seconds (with small tolerance)
                    {
                        Serial.print("Button ");
                        Serial.print(i + 1);
                        Serial.print(" held for ");
                        Serial.print(holdDuration / 1000);
                        Serial.print("/30 seconds...");
                        Serial.print(" (");
                        Serial.print((holdDuration * 100) / RESET_HOLD_DURATION);
                        Serial.println("%)");
                    }
                }
            }
            else
            {
                // Button released
                if (buttonBeingHeld[i])
                {
                    unsigned long holdDuration = millis() - buttonHoldStartTime[i];
                    Serial.print("Button ");
                    Serial.print(i + 1);
                    Serial.print(" released after ");
                    Serial.print(holdDuration / 1000);
                    Serial.println(" seconds (need 30s for reset)");

                    // Turn off LED
                    digitalWrite(ledPins[i], LOW);
                }
                buttonBeingHeld[i] = false;
            }
        }
    }
    else
    {
        // When ledFlashingEnabled is true, clear any hold states
        for (int i = 0; i < NUM_BUTTONS; i++)
        {
            buttonBeingHeld[i] = false;
        }
    }

    // Only process button presses if not currently dispensing
    // AND ledFlashingEnabled is true (normal dispensing mode)
    if (!dispensing && ledFlashingEnabled)
    {
        // Count how many buttons are currently pressed
        int pressedCount = 0;
        int pressedIndex = -1;

        for (int i = 0; i < NUM_BUTTONS; i++)
        {
            // Count pressed buttons
            if (buttons[i].read() == LOW)
            {
                pressedCount++;
                pressedIndex = i;
            }
        }

        // Only activate if exactly one button is pressed
        if (pressedCount == 1 && pressedIndex >= 0)
        {
            // Check for falling edge (button just pressed) and not reached limit
            if (buttons[pressedIndex].fell() && !buttonLimitReached[pressedIndex])
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
    // Only activate if not already active and limit not reached
    if (!relayActive[index] && !buttonLimitReached[index])
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

        // Increment and save button press count
        buttonPressCount[index]++;
        saveButtonPressCountToEEPROM(index);

        // Check if limit reached
        if (buttonPressCount[index] >= MAX_BUTTON_PRESSES)
        {
            buttonLimitReached[index] = true;
            Serial.print("Button ");
            Serial.print(index + 1);
            Serial.println(" has reached its press limit!");
        }

        Serial.print("Dispenser ");
        Serial.print(index + 1);
        Serial.print(" activated (Press count: ");
        Serial.print(buttonPressCount[index]);
        Serial.print("/");
        Serial.print(MAX_BUTTON_PRESSES);
        Serial.println(")");
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

// Load button press counts from EEPROM
void loadButtonPressCountsFromEEPROM()
{
    Serial.println("Loading button press counts from EEPROM...");

    for (int i = 0; i < NUM_BUTTONS; i++)
    {
        // Read int from EEPROM (2 bytes per int)
        int value;
        EEPROM.get(EEPROM_ADDRESSES[i], value);

        // Validate the value (EEPROM might contain garbage on first use)
        if (value < 0 || value > MAX_BUTTON_PRESSES)
        {
            value = 0;
            // Save the initialized value
            EEPROM.put(EEPROM_ADDRESSES[i], value);
        }

        buttonPressCount[i] = value;

        // Check if limit already reached
        if (buttonPressCount[i] >= MAX_BUTTON_PRESSES)
        {
            buttonLimitReached[i] = true;
        }

        Serial.print("Button ");
        Serial.print(i + 1);
        Serial.print(": ");
        Serial.print(buttonPressCount[i]);
        Serial.print("/");
        Serial.print(MAX_BUTTON_PRESSES);
        if (buttonLimitReached[i])
        {
            Serial.print(" [LIMIT REACHED]");
        }
        Serial.println();
    }
}

// Save button press count to EEPROM
void saveButtonPressCountToEEPROM(int index)
{
    EEPROM.put(EEPROM_ADDRESSES[index], buttonPressCount[index]);
}

// Reset button counter (called when button held for 30 seconds)
void resetButtonCounter(int index)
{
    buttonPressCount[index] = 0;
    buttonLimitReached[index] = false;
    saveButtonPressCountToEEPROM(index);

    Serial.println("\n*** RESET SUCCESSFUL ***");
    Serial.print("Button ");
    Serial.print(index + 1);
    Serial.println(" counter has been RESET to 0!");
    Serial.println("LED flashing restored and button is now active.");
    Serial.println("************************\n");

    // Visual feedback: Flash the specific LED rapidly 10 times
    for (int i = 0; i < 10; i++)
    {
        digitalWrite(ledPins[index], HIGH);
        delay(100);
        digitalWrite(ledPins[index], LOW);
        delay(100);
    }

    // Print updated status
    printButtonStatus();
}

// Print current status of all buttons
void printButtonStatus()
{
    Serial.println("\n=== Button Status ===");
    for (int i = 0; i < NUM_BUTTONS; i++)
    {
        Serial.print("Button ");
        Serial.print(i + 1);
        Serial.print(": ");
        Serial.print(buttonPressCount[i]);
        Serial.print("/");
        Serial.print(MAX_BUTTON_PRESSES);
        if (buttonLimitReached[i])
        {
            Serial.print(" [DISABLED]");
        }
        else
        {
            Serial.print(" [ACTIVE]");
        }
        Serial.println();
    }
    Serial.println("====================\n");
}
