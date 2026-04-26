#!/bin/bash
# Installation script for Perfume Dispenser Systemd Service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Perfume Dispenser System - Service Installation"
echo "=============================================="

# Get the current directory (where the script is located)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_FILE="$SCRIPT_DIR/perfume-dispenser.service"
SYSTEMD_DIR="/etc/systemd/system"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}Error: Service file not found: $SERVICE_FILE${NC}"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-$USER}
if [ "$ACTUAL_USER" == "root" ]; then
    echo -e "${YELLOW}Warning: Running as root user. Service will run as 'pi' user.${NC}"
    ACTUAL_USER="pi"
fi

# Get the actual home directory
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)
PROJECT_DIR="$ACTUAL_HOME/perfume-dispenser"

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}Warning: Project directory not found at: $PROJECT_DIR${NC}"
    echo "Please enter the full path to the project directory:"
    read -r PROJECT_DIR
    
    if [ ! -d "$PROJECT_DIR" ]; then
        echo -e "${RED}Error: Directory does not exist: $PROJECT_DIR${NC}"
        exit 1
    fi
fi

# Check if main script exists
if [ ! -f "$PROJECT_DIR/perfume_dispenser.py" ]; then
    echo -e "${RED}Error: Main script not found: $PROJECT_DIR/perfume_dispenser.py${NC}"
    exit 1
fi

# Create a temporary service file with correct paths
TEMP_SERVICE="/tmp/perfume-dispenser.service"
sed "s|/home/pi/perfume-dispenser|$PROJECT_DIR|g; s|User=pi|User=$ACTUAL_USER|g" "$SERVICE_FILE" > "$TEMP_SERVICE"

# Copy service file to systemd directory
echo "Installing service file..."
cp "$TEMP_SERVICE" "$SYSTEMD_DIR/perfume-dispenser.service"

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable service (start on boot)
echo "Enabling service to start on boot..."
systemctl enable perfume-dispenser.service

echo ""
echo -e "${GREEN}Service installed successfully!${NC}"
echo ""
echo "Service configuration:"
echo "  - User: $ACTUAL_USER"
echo "  - Working Directory: $PROJECT_DIR"
echo "  - Service file: $SYSTEMD_DIR/perfume-dispenser.service"
echo ""
echo "Useful commands:"
echo "  Start service:     sudo systemctl start perfume-dispenser"
echo "  Stop service:      sudo systemctl stop perfume-dispenser"
echo "  Restart service:   sudo systemctl restart perfume-dispenser"
echo "  Check status:      sudo systemctl status perfume-dispenser"
echo "  View logs:         sudo journalctl -u perfume-dispenser -f"
echo "  Disable service:   sudo systemctl disable perfume-dispenser"
echo ""
echo -e "${GREEN}The service will automatically start on boot.${NC}"
echo "To start it now, run: sudo systemctl start perfume-dispenser"
