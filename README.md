# Autostart Guide - Perfume Dispenser System

This guide explains how to set up the Perfume Dispenser System and the USB Video Player to automatically start when your Raspberry Pi boots up.

- **Perfume Dispenser**: Payment and dispensing system (Methods 1–3 below)
- **Video Player**: USB video playback in fullscreen (see Video Player Service section)

## Method 1: Using systemd Service (Recommended)

The easiest way is to use the provided installation script.

### Quick Installation

1. **Navigate to the project directory**:
   ```bash
   cd ~/perfume-dispenser
   ```

2. **Run the installation script**:
   ```bash
   sudo ./install-service.sh
   ```

   The script will:
   - Detect your project directory
   - Create a systemd service file
   - Enable the service to start on boot
   - Configure it to run as your user

3. **Start the service immediately** (optional):
   ```bash
   sudo systemctl start perfume-dispenser
   ```

### Manual Installation

If you prefer to install manually:

1. **Copy the service file**:
   ```bash
   sudo cp perfume-dispenser.service /etc/systemd/system/
   ```

2. **Edit the service file** to match your setup:
   ```bash
   sudo nano /etc/systemd/system/perfume-dispenser.service
   ```
   
   Update these lines with your actual paths:
   ```ini
   User=pi                                    # Your username
   WorkingDirectory=/home/pi/perfume-dispenser  # Your project path
   ExecStart=/usr/bin/python3 /home/pi/perfume-dispenser/perfume_dispenser.py
   ```

3. **Reload systemd and enable the service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable perfume-dispenser.service
   sudo systemctl start perfume-dispenser.service
   ```

### Service Management Commands

```bash
# Check service status
sudo systemctl status perfume-dispenser

# Start the service
sudo systemctl start perfume-dispenser

# Stop the service
sudo systemctl stop perfume-dispenser

# Restart the service
sudo systemctl restart perfume-dispenser

# View live logs
sudo journalctl -u perfume-dispenser -f

# View recent logs
sudo journalctl -u perfume-dispenser -n 50

# Disable autostart (but keep service installed)
sudo systemctl disable perfume-dispenser

# Remove the service completely
sudo systemctl stop perfume-dispenser
sudo systemctl disable perfume-dispenser
sudo rm /etc/systemd/system/perfume-dispenser.service
sudo systemctl daemon-reload
```

## Method 2: Using rc.local (Alternative)

If you prefer a simpler approach without systemd:

1. **Edit rc.local**:
   ```bash
   sudo nano /etc/rc.local
   ```

2. **Add this line before `exit 0`**:
   ```bash
   su - pi -c "cd /home/pi/perfume-dispenser && /usr/bin/python3 perfume_dispenser.py &"
   ```

3. **Make sure the file ends with `exit 0`**

**Note**: This method is less robust than systemd (no automatic restart on failure, harder to manage).

## Method 3: Using crontab @reboot

1. **Edit crontab**:
   ```bash
   crontab -e
   ```

2. **Add this line**:
   ```cron
   @reboot cd /home/pi/perfume-dispenser && /usr/bin/python3 perfume_dispenser.py
   ```

**Note**: This method also doesn't provide automatic restart on failure.

---

## Video Player Service (USB Video Playback)

The video player automatically plays videos from a USB stick in fullscreen, in alphabetical order. It starts on boot, waits for the USB to be connected, and stops immediately if the USB is removed.

### Quick Installation

1. **Navigate to the project directory**:
   ```bash
   cd ~/perfume-dispenser
   ```

2. **Run the installation script**:
   ```bash
   sudo ./install-video-player.sh
   ```

   The script will:
   - Check for a video player (mpv, omxplayer, or vlc)
   - Offer to install mpv if none is found
   - Create and enable the systemd service
   - Optionally start the service immediately

3. **Prepare your USB stick**:
   - Create a folder named `video` on the USB stick
   - Place your video files (.mp4, .avi, .mov, .mkv, etc.) in that folder
   - Videos will play in **alphabetical order**

### Behavior

- **USB connected**: Detects USB, reads videos from the `video` folder, plays in alphabetical order in fullscreen loop
- **USB removed**: Stops video immediately (no resume)
- **USB reconnected**: Service restarts automatically and waits for USB; when connected, plays again

### Manual Installation

1. **Install a video player** (if not already installed):
   ```bash
   sudo apt-get update
   sudo apt-get install mpv
   ```

2. **Copy the service file**:
   ```bash
   sudo cp video-player.service /etc/systemd/system/
   ```

3. **Edit the service file** to match your setup:
   ```bash
   sudo nano /etc/systemd/system/video-player.service
   ```
   
   Update the path in `ExecStart`:
   ```ini
   ExecStart=/usr/bin/python3 -u /home/pi/perfume-dispenser/video_player.py
   ```

4. **Reload systemd and enable the service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable video-player.service
   sudo systemctl start video-player.service
   ```

### Video Player Service Commands

```bash
# Check service status
sudo systemctl status video-player

# Start the service
sudo systemctl start video-player

# Stop the service
sudo systemctl stop video-player

# Restart the service
sudo systemctl restart video-player

# View live logs
sudo journalctl -u video-player -f

# View recent logs
sudo journalctl -u video-player -n 50

# Disable autostart
sudo systemctl disable video-player
```

### Video Player Troubleshooting

- **No video player found**: Install mpv with `sudo apt-get install mpv`
- **USB not detected**: Ensure the USB has a `video` folder with video files; check mount point with `ls /media/pi/`
- **Videos not playing**: Verify video format is supported (.mp4, .avi, .mov, .mkv, etc.)
- **Display issues**: Ensure `DISPLAY=:0` is set if using a desktop environment

---

## Troubleshooting

### Service won't start

1. **Check service status**:
   ```bash
   sudo systemctl status perfume-dispenser
   ```

2. **Check logs**:
   ```bash
   sudo journalctl -u perfume-dispenser -n 50
   ```

3. **Common issues**:
   - **Permission errors**: Make sure the user in the service file has access to GPIO
   - **Path errors**: Verify the paths in the service file are correct
   - **Python not found**: Check that Python 3 is at `/usr/bin/python3`
   - **Dependencies missing**: Run `pip3 install -r requirements.txt`

### Service starts but stops immediately

1. **Check if it's a permission issue**:
   ```bash
   sudo journalctl -u perfume-dispenser -n 50
   ```

2. **Try running manually** to see the error:
   ```bash
   python3 perfume_dispenser.py
   ```

3. **Check GPIO permissions**:
   ```bash
   groups  # Should include 'gpio' group
   ```

### Service doesn't start on boot

1. **Verify service is enabled**:
   ```bash
   sudo systemctl is-enabled perfume-dispenser
   ```
   Should output: `enabled`

2. **Check if service file exists**:
   ```bash
   ls -l /etc/systemd/system/perfume-dispenser.service
   ```

3. **Reload systemd**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable perfume-dispenser
   ```

## Testing Autostart

To test if autostart works:

1. **Enable the service** (if not already):
   ```bash
   sudo systemctl enable perfume-dispenser
   ```

2. **Reboot the Raspberry Pi**:
   ```bash
   sudo reboot
   ```

3. **After reboot, check if service is running**:
   ```bash
   sudo systemctl status perfume-dispenser
   ```

   Should show: `Active: active (running)`

## Recommended: systemd Service

The systemd service method is recommended because it:
- ✅ Automatically restarts if the program crashes
- ✅ Provides better logging with `journalctl`
- ✅ Easy to start/stop/restart
- ✅ Starts after network is ready
- ✅ Standard Linux service management

## Service Configuration Details

The service file (`perfume-dispenser.service`) includes:

- **Restart=always**: Automatically restarts if the program crashes
- **RestartSec=10**: Waits 10 seconds before restarting
- **After=network.target**: Starts after network is available
- **StandardOutput=journal**: Logs output to systemd journal
- **StandardError=journal**: Logs errors to systemd journal

You can modify these settings in `/etc/systemd/system/perfume-dispenser.service` if needed.
