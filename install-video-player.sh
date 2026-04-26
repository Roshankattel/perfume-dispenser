#!/bin/bash
# Installation script for USB Video Player service

set -e

echo "=========================================="
echo "USB Video Player Service Installer"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="video-player.service"
SERVICE_FILE="$SCRIPT_DIR/$SERVICE_NAME"
SYSTEMD_DIR="/etc/systemd/system"

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: Service file not found: $SERVICE_FILE"
    exit 1
fi

# Check if video_player.py exists
if [ ! -f "$SCRIPT_DIR/video_player.py" ]; then
    echo "Error: video_player.py not found in $SCRIPT_DIR"
    exit 1
fi

# Make video_player.py executable
chmod +x "$SCRIPT_DIR/video_player.py"
echo "Made video_player.py executable"

# Check if video player is installed
echo ""
echo "Checking for video player..."
if command -v mpv &> /dev/null; then
    echo "✓ mpv is installed"
    PLAYER="mpv"
elif command -v omxplayer &> /dev/null; then
    echo "✓ omxplayer is installed"
    PLAYER="omxplayer"
elif command -v vlc &> /dev/null; then
    echo "✓ vlc is installed"
    PLAYER="vlc"
else
    echo "⚠ No video player found!"
    echo ""
    echo "Please install a video player:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install mpv"
    echo ""
    read -p "Do you want to install mpv now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        apt-get update
        apt-get install -y mpv
        echo "✓ mpv installed"
    else
        echo "Warning: Video player not installed. Service may not work."
    fi
fi

# Update service file with correct path
# Replace the path in the service file
sed -i "s|/home/pi/perfume-dispenser|$SCRIPT_DIR|g" "$SERVICE_FILE"

# Copy service file to systemd directory
echo ""
echo "Installing systemd service..."
cp "$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_NAME"
echo "✓ Service file copied to $SYSTEMD_DIR/$SERVICE_NAME"

# Reload systemd
systemctl daemon-reload
echo "✓ Systemd daemon reloaded"

# Enable service
systemctl enable "$SERVICE_NAME"
echo "✓ Service enabled (will start on boot)"

# Ask if user wants to start the service now
echo ""
read -p "Do you want to start the service now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl start "$SERVICE_NAME"
    echo "✓ Service started"
    echo ""
    echo "Check status with: sudo systemctl status video-player"
    echo "View logs with: sudo journalctl -u video-player -f"
else
    echo ""
    echo "Service will start automatically on next boot"
fi

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Service: video-player.service"
echo "Status: sudo systemctl status video-player"
echo "Start:  sudo systemctl start video-player"
echo "Stop:   sudo systemctl stop video-player"
echo "Logs:   sudo journalctl -u video-player -f"
echo ""
echo "IMPORTANT:"
echo "1. Create a folder named 'video' on your USB stick"
echo "2. Place your video files (.mp4, .avi, .mov, etc.) in that folder"
echo "3. Videos will play in alphabetical order in fullscreen loop"
echo "4. Insert USB stick before booting or restart the service after inserting"
echo ""
