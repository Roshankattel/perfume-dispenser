// Perfume Dispenser Arduino Sketch
// Arduino Uno Circuit Configuration

#include <Bounce2.h>
#include <SoftwareSerial.h>

// Important constants
const unsigned long ITEM_SELECTION_TIMEOUT = 55000; // 55 seconds
// const uint16_t ITEM_PRICE = 1000;  // this is the price of the item in cents
const uint16_t ITEM_PRICE = 200;                // this is the price of the item in cents
const unsigned long POST_DISPENSE_DELAY = 2000; // Delay in ms after dispensing before ending session
// Relay control constants
const unsigned long RELAY_DURATION = 2500; // 2.5 seconds in milliseconds

// Number of components
const int NUM_RELAYS = 5;
const int NUM_LEDS = 5;
const int NUM_BUTTONS = 5;

// Relay Pins Array
const int relayPins[NUM_RELAYS] = {A0, A1, A2, A3, 12};

// LED Pins Array
const int ledPins[NUM_LEDS] = {3, 5, 7, 9, 11};

// Button Pins Array (connected to ground when pressed)
const int buttonPins[NUM_BUTTONS] = {2, 4, 6, 8, 10};

// Payment Gateway Serial Communication (A4 = RX, A5 = TX) - MDB Protocol
SoftwareSerial paymentSerial(A5, A4); // RX, TX

// Bounce objects for debouncing
Bounce buttons[NUM_BUTTONS];

// Timer variables for relay control
unsigned long relayStartTime[NUM_RELAYS] = {0, 0, 0, 0, 0};
bool relayActive[NUM_RELAYS] = {false, false, false, false, false};

// LED Flashing control variables
bool ledFlashingEnabled = false; // Variable to control LED flashing (enabled after payment)
unsigned long lastFlashTime = 0;
bool ledFlashState = false;
const unsigned long FLASH_INTERVAL = 500; // Flash every 500ms

// State control
bool dispensing = false; // Flag to indicate if system is currently dispensing

// MDB Protocol State Machine
enum MDBState
{
    STATE_IDLE,
    STATE_WAIT_ENABLE_ACK,
    STATE_WAIT_CARD_TAP,
    STATE_WAIT_APPROVAL,
    STATE_WAIT_ITEM,
    STATE_VENDING,
    STATE_WAIT_CANCEL_ACK,
    STATE_ENDING
};

MDBState mdbState = STATE_IDLE;

// MDB Communication variables
uint8_t mdbRxBuffer[8];   // Fixed receive buffer
uint8_t mdbRxIndex = 0;   // Current buffer position
uint16_t amountCents = 0; // Selected amount in cents
uint8_t selectedItem = 0; // Selected item number (0-4)
unsigned long lastEventTime = 0;
const unsigned long NAYAX_TIMEOUT = 15000; // 15 seconds timeout for general operations
bool itemSelectionTimeout = false;         // Flag to track if item selection timed out

// ASCII hex string parsing buffer
char asciiHexBuffer[32];                 // Buffer for ASCII hex input
uint8_t asciiHexIndex = 0;               // Current position in ASCII buffer
unsigned long lastASCIIByteTime = 0;     // Time of last ASCII byte received
const unsigned long ASCII_TIMEOUT = 100; // 100ms timeout to process ASCII string

const unsigned long CARD_TAP_DELAY = 500; // Delay in ms before sending price after card tap
unsigned long cardTapTime = 0;            // Time when card was tapped
bool cardTapped = false;                  // Flag to trigger automatic price sending

// Post-dispensing delay before ending session
unsigned long dispenseCompleteTime = 0; // Time when dispensing completed
bool waitingToEndSession = false;       // Flag to indicate waiting for delay before ending session

// Cancel vend ACK handling
unsigned long cancelAckTime = 0;      // Time when cancel ACK was received
bool waitingToEndAfterCancel = false; // Flag to indicate waiting for delay after cancel ACK

void activateDispenser(int index);
void deactivateDispenser(int index);
uint8_t hexCharToNibble(char c);
void parseASCIIHexString(char *str, uint8_t len);
void handleNayax();
void printStateName(MDBState state);
uint8_t getMDBFrameLength(uint8_t cmd);
void processMDBFrame();
void sendSelectAmount(uint16_t cents);
void sendVendItem(uint8_t itemNumber, uint8_t buttonIndex);
void sendCancelVend();
void endSession();
void sendMDBFrame(uint8_t *data, uint8_t len);
void flashAllLEDs();

void setup()
{
    // Initialize serial communication for debugging
    Serial.begin(9600);

    // Initialize payment gateway serial communication (typically 9600 baud)
    paymentSerial.begin(9600);

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

    // Initialize MDB state - start waiting for card tap
    mdbState = STATE_WAIT_CARD_TAP;
    lastEventTime = millis();

    Serial.println("Setup complete - System ready!");
    Serial.println("Waiting for card tap...");
}

void loop()
{
    // Handle MDB communication with NAYAX
    handleNayax();

    // Automatic price sending after card tap delay
    if (cardTapped && mdbState == STATE_WAIT_APPROVAL)
    {
        unsigned long elapsed = millis() - cardTapTime;
        if (elapsed >= CARD_TAP_DELAY)
        {
            Serial.print("Sending price automatically: $");
            Serial.println(ITEM_PRICE / 100.0, 2);
            sendSelectAmount(ITEM_PRICE);
            cardTapped = false; // Reset flag
        }
    }

    // Handle LED flashing - ONLY when payment is approved and waiting for item selection
    // LEDs will NOT flash if payment is rejected or not approved
    if (ledFlashingEnabled && !dispensing && mdbState == STATE_WAIT_ITEM)
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
    // If in IDLE or WAIT_CARD_TAP state (before payment), turn all LEDs ON
    else if ((mdbState == STATE_IDLE || mdbState == STATE_WAIT_CARD_TAP) && !dispensing)
    {
        // Ensure all LEDs are on before payment
        for (int i = 0; i < NUM_LEDS; i++)
        {
            digitalWrite(ledPins[i], HIGH);
        }
    }
    // If LEDs should be off (payment not approved, rejected, or session ended, but not idle/card tap)
    else if (!ledFlashingEnabled && !dispensing && mdbState != STATE_IDLE && mdbState != STATE_WAIT_CARD_TAP)
    {
        // Ensure all LEDs are off
        for (int i = 0; i < NUM_LEDS; i++)
        {
            digitalWrite(ledPins[i], LOW);
        }
    }

    // Update all button states
    for (int i = 0; i < NUM_BUTTONS; i++)
    {
        buttons[i].update();
    }

    // Handle button presses - ONLY work after payment is approved
    // Buttons are IGNORED if payment is not approved or rejected
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

    // Only process if exactly one button is pressed, payment approved (WAIT_ITEM state), and not dispensing
    if (pressedCount == 1 && pressedIndex >= 0 && !dispensing && mdbState == STATE_WAIT_ITEM)
    {
        if (buttons[pressedIndex].fell())
        {
            // Payment approved, button selects item
            // Item numbers are 1-5 (button 0 = item 1, button 1 = item 2, etc.)
            uint8_t itemNumber = pressedIndex + 1;
            sendVendItem(itemNumber, pressedIndex);
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

    // Check if delay has passed after dispensing before ending session
    if (waitingToEndSession && (millis() - dispenseCompleteTime >= POST_DISPENSE_DELAY))
    {
        waitingToEndSession = false;
        endSession();
        Serial.println("Post-dispense delay complete - Session ended");
    }

    // Handle MDB timeout - use different timeouts for different states
    if (mdbState != STATE_IDLE && mdbState != STATE_VENDING && mdbState != STATE_WAIT_CANCEL_ACK)
    {
        unsigned long timeoutDuration;
        if (mdbState == STATE_WAIT_ITEM)
        {
            timeoutDuration = ITEM_SELECTION_TIMEOUT; // 1 for item selection
        }
        else
        {
            timeoutDuration = NAYAX_TIMEOUT; // 15 seconds for other operations
        }

        if (millis() - lastEventTime > timeoutDuration)
        {
            if (mdbState == STATE_WAIT_ITEM)
            {
                // Item selection timeout - send cancel vend command
                Serial.print("Item selection timeout (");
                Serial.print(timeoutDuration / 1000);
                Serial.println("s) - Sending cancel vend");
                sendCancelVend();
            }
            else
            {
                Serial.print("MDB timeout (");
                Serial.print(timeoutDuration / 1000);
                Serial.println("s) - Ending session");
                itemSelectionTimeout = true;
                endSession();
            }
        }
    }

    // Check if delay has passed after cancel ACK before ending session
    if (waitingToEndAfterCancel && (millis() - cancelAckTime >= POST_DISPENSE_DELAY))
    {
        waitingToEndAfterCancel = false;
        endSession();
        Serial.println("Post-cancel delay complete - Session ended");
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
        mdbState = STATE_VENDING;

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
        Serial.println(" activated - Vending in progress");
    }
}

// Function to deactivate a dispenser (LED + Relay)
void deactivateDispenser(int index)
{
    digitalWrite(ledPins[index], LOW);
    digitalWrite(relayPins[index], LOW);
    relayActive[index] = false;

    Serial.print("Dispenser ");
    Serial.print(index + 1);
    Serial.println(" deactivated");

    // Wait for delay before ending session
    if (mdbState == STATE_VENDING)
    {
        dispensing = false;
        waitingToEndSession = true;
        dispenseCompleteTime = millis();
        Serial.print("Vending complete - Waiting ");
        Serial.print(POST_DISPENSE_DELAY);
        Serial.println("ms before ending session");
    }
}

// ============================================================================
// MDB PROTOCOL IMPLEMENTATION
// ============================================================================

// Convert ASCII hex character to nibble (0-15)
uint8_t hexCharToNibble(char c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    return 0;
}

// Convert ASCII hex string to binary bytes
// Handles formats like "10 00", "1000", "3130203030", etc.
void parseASCIIHexString(char *str, uint8_t len)
{
    uint8_t byteValue = 0;
    bool hasFirstNibble = false;
    mdbRxIndex = 0;

    Serial.print("Parsing ASCII hex: ");
    for (uint8_t i = 0; i < len && i < 32; i++)
    {
        Serial.print(str[i]);
    }
    Serial.println();

    for (uint8_t i = 0; i < len && mdbRxIndex < 8; i++)
    {
        char c = str[i];

        // Skip spaces, newlines, carriage returns
        if (c == ' ' || c == '\n' || c == '\r' || c == '\t')
        {
            continue;
        }

        // Check if it's a hex character
        if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f'))
        {
            uint8_t nibble = hexCharToNibble(c);

            if (!hasFirstNibble)
            {
                byteValue = nibble << 4;
                hasFirstNibble = true;
            }
            else
            {
                byteValue |= nibble;
                mdbRxBuffer[mdbRxIndex++] = byteValue;
                hasFirstNibble = false;
            }
        }
    }

    // Handle trailing single nibble (shouldn't happen in valid MDB, but handle gracefully)
    if (hasFirstNibble && mdbRxIndex < 8)
    {
        mdbRxBuffer[mdbRxIndex++] = byteValue;
    }

    // Debug: Print converted bytes
    if (mdbRxIndex > 0)
    {
        Serial.print("Converted to bytes: ");
        for (uint8_t i = 0; i < mdbRxIndex; i++)
        {
            if (mdbRxBuffer[i] < 0x10)
                Serial.print("0");
            Serial.print(mdbRxBuffer[i], HEX);
            Serial.print(" ");
        }
        Serial.println();
    }

    // Handle single byte ACK (0x00) - response to amount/vend commands
    if (mdbRxIndex == 1 && mdbRxBuffer[0] == 0x00)
    {
        // Single byte ACK - create frame structure for processing
        uint8_t tempBuffer[2] = {0x10, 0x00}; // Fake frame start + ACK command
        mdbRxBuffer[0] = 0x10;
        mdbRxBuffer[1] = 0x00;
        mdbRxIndex = 2;
        processMDBFrame();
    }
    // If we have a complete frame, process it
    else if (mdbRxIndex >= 2)
    {
        uint8_t cmd = mdbRxBuffer[1];
        uint8_t frameLen = getMDBFrameLength(cmd);
        if (mdbRxIndex >= frameLen)
        {
            processMDBFrame();
        }
        else
        {
            Serial.print("Incomplete frame: got ");
            Serial.print(mdbRxIndex);
            Serial.print(" bytes, need ");
            Serial.println(frameLen);
        }
    }
    else if (mdbRxIndex > 0)
    {
        Serial.println("Frame too short");
    }
}

// Main MDB handler - called every loop iteration
void handleNayax()
{
    // Check for ASCII hex string timeout
    if (asciiHexIndex > 0 && (millis() - lastASCIIByteTime > ASCII_TIMEOUT))
    {
        // Timeout - process accumulated ASCII data
        parseASCIIHexString(asciiHexBuffer, asciiHexIndex);
        asciiHexIndex = 0; // Reset buffer
    }

    // Read incoming MDB frames
    while (paymentSerial.available() > 0)
    {
        uint8_t byte = paymentSerial.read();

        // Check if it's ASCII character (likely hex string mode)
        // Also handle control characters that might be part of hex strings
        if ((byte >= 0x20 && byte <= 0x7E) || byte == '\n' || byte == '\r' || byte == '\t' || byte == ' ')
        {
            // ASCII character - treat as hex string input
            if (byte == '\n' || byte == '\r')
            {
                // Check for cancel vend ACK: "00 \r\n" or "00\r\n"
                // Response is ASCII "00 " followed by \r\n (hex: 30 30 20 0d 0a)
                if (mdbState == STATE_WAIT_CANCEL_ACK && asciiHexIndex >= 2)
                {
                    // Check if buffer starts with "00" (may have space after)
                    if (asciiHexBuffer[0] == '0' && asciiHexBuffer[1] == '0')
                    {
                        // Cancel vend ACK received
                        Serial.println("Cancel vend ACK received (00)");
                        waitingToEndAfterCancel = true;
                        cancelAckTime = millis();
                        asciiHexIndex = 0; // Reset buffer
                    }
                    else if (asciiHexIndex > 0)
                    {
                        // End of line - process the accumulated string
                        parseASCIIHexString(asciiHexBuffer, asciiHexIndex);
                        asciiHexIndex = 0; // Reset buffer
                    }
                }
                else if (asciiHexIndex > 0)
                {
                    // End of line - process the accumulated string
                    parseASCIIHexString(asciiHexBuffer, asciiHexIndex);
                    asciiHexIndex = 0; // Reset buffer
                }
            }
            else if (asciiHexIndex < 31)
            {
                asciiHexBuffer[asciiHexIndex++] = (char)byte;
                asciiHexBuffer[asciiHexIndex] = '\0'; // Null terminate
                lastASCIIByteTime = millis();         // Update timestamp

                // Also check if buffer is full (process immediately)
                if (asciiHexIndex >= 31)
                {
                    parseASCIIHexString(asciiHexBuffer, asciiHexIndex);
                    asciiHexIndex = 0; // Reset buffer
                }
            }
        }
        else
        {
            // Binary byte mode - original MDB protocol
            // If we have accumulated ASCII data, process it first
            if (asciiHexIndex > 0)
            {
                parseASCIIHexString(asciiHexBuffer, asciiHexIndex);
                asciiHexIndex = 0; // Reset buffer
            }

            // Handle single byte ACK (0x00) - response to amount/vend commands
            if (byte == 0x00 && mdbRxIndex == 0)
            {
                // Single byte ACK - process immediately
                mdbRxBuffer[0] = 0x10; // Fake frame start for processing
                mdbRxBuffer[1] = 0x00; // ACK command
                mdbRxIndex = 2;
                processMDBFrame();
                mdbRxIndex = 0; // Reset buffer
            }
            // MDB frames start with 0x10
            else if (byte == 0x10)
            {
                mdbRxIndex = 0;
                mdbRxBuffer[mdbRxIndex++] = byte;
            }
            else if (mdbRxIndex > 0 && mdbRxIndex < 8)
            {
                // Continue building frame
                mdbRxBuffer[mdbRxIndex++] = byte;

                // Process frame based on command byte (2nd byte)
                if (mdbRxIndex >= 2)
                {
                    uint8_t cmd = mdbRxBuffer[1];

                    // Determine frame length and process if complete
                    uint8_t frameLen = getMDBFrameLength(cmd);
                    if (mdbRxIndex >= frameLen)
                    {
                        processMDBFrame();
                        mdbRxIndex = 0; // Reset buffer
                    }
                }
            }
            else
            {
                // Invalid byte, reset
                mdbRxIndex = 0;
            }
        }
    }
}

// Helper function to print state name for debugging
void printStateName(MDBState state)
{
    switch (state)
    {
    case STATE_IDLE:
        Serial.print("IDLE");
        break;
    case STATE_WAIT_ENABLE_ACK:
        Serial.print("WAIT_ENABLE_ACK");
        break;
    case STATE_WAIT_CARD_TAP:
        Serial.print("WAIT_CARD_TAP");
        break;
    case STATE_WAIT_APPROVAL:
        Serial.print("WAIT_APPROVAL");
        break;
    case STATE_WAIT_ITEM:
        Serial.print("WAIT_ITEM");
        break;
    case STATE_VENDING:
        Serial.print("VENDING");
        break;
    case STATE_WAIT_CANCEL_ACK:
        Serial.print("WAIT_CANCEL_ACK");
        break;
    case STATE_ENDING:
        Serial.print("ENDING");
        break;
    default:
        Serial.print("UNKNOWN");
        break;
    }
}

// Get expected frame length based on MDB command
uint8_t getMDBFrameLength(uint8_t cmd)
{
    switch (cmd)
    {
    case 0x00:
        return 2; // ACK: 10 00 or single byte 00
    case 0x03:
        return 4; // Card tap: 10 03 03 E8
    case 0x04:
        return 2; // Timeout: 10 04
    case 0x05:
        return 4; // Approved: 10 05 00 0A (4 bytes, amount in bytes 2-3)
    case 0x06:
        return 2; // Rejected: 10 06
    default:
        return 2; // Default minimum
    }
}

// Process complete MDB frame
void processMDBFrame()
{
    if (mdbRxIndex < 2)
        return;

    uint8_t cmd = mdbRxBuffer[1];
    lastEventTime = millis(); // Update timeout timer

    // Debug: Print received frame
    Serial.print("RX: ");
    for (uint8_t i = 0; i < mdbRxIndex; i++)
    {
        if (mdbRxBuffer[i] < 0x10)
            Serial.print("0");
        Serial.print(mdbRxBuffer[i], HEX);
        Serial.print(" ");
    }
    Serial.print(" | State: ");
    printStateName(mdbState);
    Serial.println();

    // Parse based on command and current state
    switch (cmd)
    {
    case 0x00: // ACK responses: Amount ACK, Vend Item ACK, or single byte ACK
        if (mdbState == STATE_WAIT_APPROVAL && mdbRxIndex == 2)
        {
            // ACK after sending amount - wait for approval response
            Serial.println("Amount command acknowledged - waiting for approval");
        }
        else if (mdbState == STATE_VENDING)
        {
            // ACK for vend item command
            Serial.println("Vend item acknowledged");
        }
        break;

    case 0x03: // Card tap event
        Serial.print("Card tap detected! Current state: ");
        printStateName(mdbState);
        Serial.print(", Frame length: ");
        Serial.println(mdbRxIndex);

        if (mdbRxIndex >= 4)
        {
            // Process card tap regardless of state (more flexible)
            if (mdbState == STATE_WAIT_CARD_TAP || mdbState == STATE_IDLE)
            {
                Serial.println("Card tapped - will send price automatically after delay");
                mdbState = STATE_WAIT_APPROVAL;
                cardTapped = true;
                cardTapTime = millis(); // Record time for delay
                Serial.print("cardTapped flag set, will send price in ");
                Serial.print(CARD_TAP_DELAY);
                Serial.println("ms");
            }
            else
            {
                Serial.print("Card tap ignored - wrong state: ");
                printStateName(mdbState);
                Serial.println();
            }
        }
        else
        {
            Serial.print("Card tap frame too short: ");
            Serial.println(mdbRxIndex);
        }
        break;

    case 0x05: // Payment approved
        if (mdbState == STATE_WAIT_APPROVAL && mdbRxIndex >= 4)
        {
            // Extract amount: format is 10 05 00 0A
            // Bytes 2-3 contain the amount: "00 0A" = 0x000A = 10 cents
            // Byte 2 = high byte, Byte 3 = low byte
            uint16_t approvedAmount = (mdbRxBuffer[2] << 8) | mdbRxBuffer[3];
            Serial.print("Payment approved: $");
            Serial.println(approvedAmount / 100.0, 2);

            mdbState = STATE_WAIT_ITEM;
            ledFlashingEnabled = true;    // Enable LED flashing
            cardTapped = false;           // Reset card tap flag
            itemSelectionTimeout = false; // Reset timeout flag
            lastEventTime = millis();     // Reset timeout timer for item selection
            Serial.print("Waiting for item selection (timeout: ");
            Serial.print(ITEM_SELECTION_TIMEOUT / 1000);
            Serial.println(" seconds)...");
        }
        break;

    case 0x06: // Payment rejected
        if (mdbState == STATE_WAIT_APPROVAL)
        {
            Serial.println("Payment rejected - waiting for timeout");
            cardTapped = false;         // Reset card tap flag
            ledFlashingEnabled = false; // Disable LED flashing
            // Turn off all LEDs
            for (int i = 0; i < NUM_LEDS; i++)
            {
                digitalWrite(ledPins[i], LOW);
            }
            // State remains WAIT_APPROVAL, will timeout and end session
        }
        break;

    case 0x04: // Timeout from Nayax
        Serial.println("NAYAX timeout received");
        if (mdbState == STATE_WAIT_APPROVAL)
        {
            // Timeout during approval - end session immediately
            endSession();
        }
        else if (mdbState == STATE_WAIT_ITEM)
        {
            // Timeout during item selection - set flag but keep waiting for full timeout period
            // Don't end session yet, let user have full time to select
            itemSelectionTimeout = true;
            Serial.println("Nayax timeout received - will not send vend command if item selected");
            Serial.println("Continuing to wait for full timeout period or user selection...");
            // Don't call endSession() - let the internal timeout handle it
        }
        break;
    }
}

// Send Enable Reader command: 14 01
// Send Select Amount command: 13 00 00 <amountHex> 00 01
void sendSelectAmount(uint16_t cents)
{
    amountCents = cents;
    uint8_t highByte = (uint8_t)((cents >> 8) & 0xFF);
    uint8_t lowByte = (uint8_t)(cents & 0xFF);

    // If high byte is zero, only send low byte
    if (highByte == 0)
    {
        uint8_t cmd[] = {
            0x13,
            0x00,
            0x00,
            lowByte, // Amount low byte only
            0x00,
            0x01};
        sendMDBFrame(cmd, 6);
    }
    else
    {
        uint8_t cmd[] = {
            0x13,
            0x00,
            0x00,
            highByte, // Amount high byte first
            lowByte,  // Amount low byte
            0x00,
            0x01};
        sendMDBFrame(cmd, 7);
    }
    Serial.print("TX: Select Amount $");
    Serial.println(cents / 100.0, 2);
}

// Send Vend Item command: 13 02 00 <itemNumber>
// itemNumber: 1-5 (item selection number)
// buttonIndex: 0-4 (button/relay index for hardware control)
void sendVendItem(uint8_t itemNumber, uint8_t buttonIndex)
{
    if (mdbState != STATE_WAIT_ITEM)
        return;
    if (itemNumber < 1 || itemNumber > 5)
        return;
    if (buttonIndex >= NUM_BUTTONS)
        return;

    selectedItem = itemNumber;

    // Check if Nayax timeout occurred - if so, don't send vend command but still dispense
    if (itemSelectionTimeout)
    {
        Serial.println("Nayax timeout occurred earlier - dispensing without sending vend command to Nayax");
        Serial.print("Dispensing item ");
        Serial.println(itemNumber);

        // Still activate dispenser even though Nayax timed out
        // Payment was successful, so user should get the product
        mdbState = STATE_VENDING;
        lastEventTime = millis();
        activateDispenser(buttonIndex);
        return;
    }

    // Normal flow: send vend command to Nayax and activate dispenser
    uint8_t cmd[] = {0x13, 0x02, 0x00, itemNumber};
    sendMDBFrame(cmd, 4);
    mdbState = STATE_VENDING;
    lastEventTime = millis();

    Serial.print("TX: Vend Item ");
    Serial.println(itemNumber);

    // Activate dispenser immediately (use buttonIndex for hardware)
    activateDispenser(buttonIndex);
}

// Send Cancel Vend command: 13 01
void sendCancelVend()
{
    if (mdbState != STATE_WAIT_ITEM)
        return;

    uint8_t cmd[] = {0x13, 0x01};
    sendMDBFrame(cmd, 2);
    mdbState = STATE_WAIT_CANCEL_ACK;
    lastEventTime = millis();
    ledFlashingEnabled = false; // Disable LED flashing
    // Turn off all LEDs
    for (int i = 0; i < NUM_LEDS; i++)
    {
        digitalWrite(ledPins[i], LOW);
    }
    Serial.println("TX: Cancel Vend");
}

// Send End Session command: 13 04
void endSession()
{
    uint8_t cmd[] = {0x13, 0x04};
    sendMDBFrame(cmd, 2);
    mdbState = STATE_IDLE;
    ledFlashingEnabled = false;
    amountCents = 0;
    selectedItem = 0;
    cardTapped = false;              // Reset card tap flag
    waitingToEndSession = false;     // Reset waiting flag
    waitingToEndAfterCancel = false; // Reset cancel waiting flag
    dispensing = false;              // Reset dispensing flag
    itemSelectionTimeout = false;    // Reset timeout flag
    Serial.println("TX: End Session");

    // Turn off all LEDs
    for (int i = 0; i < NUM_LEDS; i++)
    {
        digitalWrite(ledPins[i], LOW);
    }
}

// Send MDB frame to payment gateway
void sendMDBFrame(uint8_t *data, uint8_t len)
{
    // Debug: Print command being sent
    Serial.print("TX: ");
    for (uint8_t i = 0; i < len; i++)
    {
        if (data[i] < 0x10)
            Serial.print("0");
        Serial.print(data[i], HEX);
        Serial.print(" ");
    }
    Serial.print(" | State: ");
    printStateName(mdbState);
    Serial.println();

    // Send the MDB frame bytes
    for (uint8_t i = 0; i < len; i++)
    {
        paymentSerial.write(data[i]);
    }
    // Small delay to ensure transmission completes
    delayMicroseconds(500);
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
