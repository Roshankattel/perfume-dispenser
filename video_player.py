#!/usr/bin/env python3
"""
USB Video Player for Raspberry Pi
Automatically detects USB stick and plays videos in alphabetical order in fullscreen loop
"""

import os
import sys
import time
import subprocess
import glob
from pathlib import Path

# Force unbuffered output for systemd logging
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# Configuration
USB_MOUNT_POINTS = ['/media/pi', '/media', '/mnt/usb', '/mnt']
VIDEO_FOLDER_NAME = 'video'
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.m4v', '.wmv', '.flv', '.webm']
CHECK_INTERVAL = 5  # Check for USB every 5 seconds
MAX_WAIT_TIME = 300  # Maximum time to wait for USB (5 minutes)


def find_usb_mount_point():
    """Find the mount point of the USB stick"""
    for mount_base in USB_MOUNT_POINTS:
        if os.path.exists(mount_base):
            # Check all subdirectories (USB devices are usually mounted as subdirectories)
            try:
                for item in os.listdir(mount_base):
                    mount_path = os.path.join(mount_base, item)
                    if os.path.isdir(mount_path) and os.access(mount_path, os.R_OK):
                        # Check if it's likely a USB device (has video folder or is a mount point)
                        video_path = os.path.join(mount_path, VIDEO_FOLDER_NAME)
                        if os.path.exists(video_path) and os.path.isdir(video_path):
                            return mount_path
                        # Also check if it's a mount point (not a system directory)
                        if os.path.ismount(mount_path):
                            return mount_path
            except PermissionError:
                continue
    
    # Also check /dev/disk/by-label and /dev/disk/by-uuid
    try:
        # Check common USB device paths
        for device in glob.glob('/dev/sd*1'):
            # Try to find mount point using findmnt or mount command
            try:
                result = subprocess.run(['findmnt', '-n', '-o', 'TARGET', device], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    mount_path = result.stdout.strip()
                    video_path = os.path.join(mount_path, VIDEO_FOLDER_NAME)
                    if os.path.exists(video_path) and os.path.isdir(video_path):
                        return mount_path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    except Exception:
        pass
    
    return None


def find_video_files(usb_path):
    """Find all video files in the video folder on USB"""
    video_folder = os.path.join(usb_path, VIDEO_FOLDER_NAME)
    
    if not os.path.exists(video_folder):
        print(f"Video folder '{VIDEO_FOLDER_NAME}' not found in {usb_path}")
        return []
    
    if not os.path.isdir(video_folder):
        print(f"'{VIDEO_FOLDER_NAME}' exists but is not a directory")
        return []
    
    video_files = []
    for ext in VIDEO_EXTENSIONS:
        # Case-insensitive search
        pattern = os.path.join(video_folder, f'*{ext}')
        video_files.extend(glob.glob(pattern))
        pattern = os.path.join(video_folder, f'*{ext.upper()}')
        video_files.extend(glob.glob(pattern))
    
    # Sort alphabetically
    video_files.sort(key=str.lower)
    
    return video_files


def wait_for_usb():
    """Wait for USB stick to be mounted"""
    print("=" * 50, flush=True)
    print("USB Video Player - Waiting for USB stick...", flush=True)
    print("=" * 50, flush=True)
    
    start_time = time.time()
    
    while True:
        usb_path = find_usb_mount_point()
        
        if usb_path:
            print(f"USB stick detected at: {usb_path}", flush=True)
            return usb_path
        
        elapsed = time.time() - start_time
        if elapsed > MAX_WAIT_TIME:
            print(f"Timeout: USB stick not detected after {MAX_WAIT_TIME} seconds", flush=True)
            return None
        
        print(f"Waiting for USB stick... (checked for {elapsed:.0f}s)", flush=True)
        time.sleep(CHECK_INTERVAL)


def check_video_player():
    """Check if a video player is available"""
    players = ['mpv', 'omxplayer', 'vlc']
    
    for player in players:
        try:
            result = subprocess.run(['which', player], 
                                  capture_output=True, 
                                  timeout=2)
            if result.returncode == 0:
                return player
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    
    return None


def verify_videos_exist(video_files):
    """Verify that video files still exist"""
    return [v for v in video_files if os.path.exists(v)]


def play_videos(video_files, player_cmd, usb_path):
    """Play videos in loop"""
    if not video_files:
        print("No video files found!", flush=True)
        return False
    
    print(f"Found {len(video_files)} video file(s):", flush=True)
    for i, video in enumerate(video_files, 1):
        print(f"  {i}. {os.path.basename(video)}", flush=True)
    print("=" * 50, flush=True)
    
    print(f"Starting video playback with {player_cmd}...", flush=True)
    print("Press Ctrl+C to stop", flush=True)
    print("=" * 50, flush=True)
    
    try:
        if player_cmd == 'mpv':
            # mpv: play all videos as a playlist and loop infinitely
            # Use --loop-playlist=inf to loop through all videos continuously
            while True:
                # Verify videos still exist (USB might have been removed)
                valid_videos = verify_videos_exist(video_files)
                if not valid_videos:
                    print("USB removed or videos no longer accessible. Waiting for USB...", flush=True)
                    return False
                
                # Check if USB is still mounted
                if not os.path.exists(usb_path):
                    print("USB removed. Waiting for reinsertion...", flush=True)
                    return False
                
                cmd = ['mpv', '--fullscreen', '--loop-playlist=inf', '--no-audio', 
                       '--no-input-default-bindings', '--really-quiet',
                       '--osd-level=0'] + valid_videos
                print(f"Starting playlist with {len(valid_videos)} video(s)...", flush=True)
                result = subprocess.run(cmd, timeout=None)
                if result.returncode != 0:
                    print(f"Player exited with code {result.returncode}, restarting...", flush=True)
                    time.sleep(2)
        else:
            # For omxplayer and vlc: manually loop through all videos
            while True:
                # Verify videos still exist (USB might have been removed)
                valid_videos = verify_videos_exist(video_files)
                if not valid_videos:
                    print("USB removed or videos no longer accessible. Waiting for USB...", flush=True)
                    return False
                
                # Play each video in sequence
                for video in valid_videos:
                    # Check if USB is still mounted before each video
                    if not os.path.exists(usb_path):
                        print("USB removed. Waiting for reinsertion...", flush=True)
                        return False
                    
                    if not os.path.exists(video):
                        print(f"Video file no longer exists: {video}", flush=True)
                        return False
                    
                    if player_cmd == 'omxplayer':
                        cmd = ['omxplayer', '-b', '--no-osd', video]
                    elif player_cmd == 'vlc':
                        cmd = ['vlc', '--fullscreen', '--no-audio', '--intf', 'dummy', 
                               '--play-and-exit', '--no-video-title-show', video]
                    else:
                        print(f"Unknown player: {player_cmd}", flush=True)
                        return False
                    
                    print(f"Playing: {os.path.basename(video)}", flush=True)
                    result = subprocess.run(cmd, timeout=None)
                    if result.returncode != 0:
                        print(f"Error playing {video} (code: {result.returncode})", flush=True)
                        time.sleep(1)
                
                # After playing all videos, loop back to the beginning
                print("Finished playlist, looping...", flush=True)
            
    except KeyboardInterrupt:
        print("\nStopping video playback...", flush=True)
        return True
    except Exception as e:
        print(f"Error during playback: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point"""
    print("=" * 50, flush=True)
    print("USB Video Player - Starting", flush=True)
    print("=" * 50, flush=True)
    
    # Check for video player
    player_cmd = check_video_player()
    if not player_cmd:
        print("ERROR: No video player found!", flush=True)
        print("Please install one of: mpv, omxplayer, or vlc", flush=True)
        print("For Raspberry Pi, install with:", flush=True)
        print("  sudo apt-get update", flush=True)
        print("  sudo apt-get install mpv", flush=True)
        sys.exit(1)
    
    print(f"Using video player: {player_cmd}", flush=True)
    
    # Wait for USB stick
    usb_path = wait_for_usb()
    if not usb_path:
        print("Failed to detect USB stick. Exiting.", flush=True)
        sys.exit(1)
    
    # Main loop: wait for USB, find videos, play, repeat if USB removed
    while True:
        # Wait for USB stick
        usb_path = wait_for_usb()
        if not usb_path:
            print("Failed to detect USB stick. Retrying...", flush=True)
            time.sleep(CHECK_INTERVAL)
            continue
        
        # Find video files
        video_files = find_video_files(usb_path)
        
        if not video_files:
            print(f"No video files found in {os.path.join(usb_path, VIDEO_FOLDER_NAME)}", flush=True)
            print(f"Supported formats: {', '.join(VIDEO_EXTENSIONS)}", flush=True)
            print("Waiting for videos to be added or USB to be reinserted...", flush=True)
            time.sleep(10)
            continue
        
        # Play videos (returns False if USB was removed)
        playback_complete = play_videos(video_files, player_cmd, usb_path)
        
        if playback_complete:
            # User interrupted or normal exit
            break
        
        # USB was removed, wait and retry
        print("USB removed during playback. Waiting for reinsertion...", flush=True)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
