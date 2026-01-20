#!/bin/bash
# Startup script for Perfume Dispenser System on Raspberry Pi

# Check if running as root (may be required for GPIO access)
if [ "$EUID" -ne 0 ]; then 
    echo "Note: Running without sudo. If you encounter permission errors, run with: sudo $0"
fi

# Change to script directory
cd "$(dirname "$0")"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check if required packages are installed
python3 -c "import RPi.GPIO" 2>/dev/null || {
    echo "Error: RPi.GPIO is not installed"
    echo "Install with: pip3 install -r requirements.txt"
    exit 1
}

python3 -c "import serial" 2>/dev/null || {
    echo "Error: pyserial is not installed"
    echo "Install with: pip3 install -r requirements.txt"
    exit 1
}

# Run the application
echo "Starting Perfume Dispenser System..."
python3 perfume_dispenser.py
