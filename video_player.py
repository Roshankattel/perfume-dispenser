#!/usr/bin/env python3
"""
USB Video Player for Raspberry Pi
Automatically detects USB stick and plays videos in alphabetical order in fullscreen loop
"""

import json
import os
import sys
import time
import subprocess
import glob

# Force unbuffered output for systemd logging
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# Configuration
USB_MOUNT_POINTS = ['/media/pi', '/media', '/mnt/usb', '/mnt']
AUTO_MOUNT_ROOT = '/media/usb-video'
VIDEO_FOLDER_NAME = 'video'
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.m4v', '.wmv', '.flv', '.webm']
CHECK_INTERVAL = 5       # Seconds between USB-present checks
MAX_WAIT_TIME = 300      # Max seconds to wait for USB on startup

# Set when a stick is found, so removal can be detected without touching a dead mount.
current_usb = {'mount': None, 'device': None}

# Watchdog — how long to let the player run before assuming it is frozen.
# Set to total playlist duration + this buffer. Restart is silent and seamless.
WATCHDOG_BUFFER_SECONDS = 120   # 2-minute grace period on top of expected duration
DEFAULT_VIDEO_DURATION  = 600   # Fallback if ffprobe is unavailable (10 min)


def run_as_root(args):
    """Run mount or umount. Use sudo when the service is not root."""
    if os.geteuid() != 0:
        args = ['sudo', '-n', *args]
    return subprocess.run(args, capture_output=True, text=True, timeout=20)


def has_video_folder(mount_path):
    video_path = os.path.join(mount_path, VIDEO_FOLDER_NAME)
    return os.path.isdir(video_path)


def findmnt_target(device):
    try:
        result = subprocess.run(
            ['findmnt', '-n', '-o', 'TARGET', device],
            capture_output=True, text=True, timeout=2
        )
        target = result.stdout.strip()
        if result.returncode == 0 and target:
            return target
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def device_path(node):
    path = node.get('path') or ''
    if path.startswith('/dev/'):
        return path
    name = node.get('name') or ''
    if name.startswith('/dev/'):
        return name
    if name:
        return '/dev/' + name
    return ''


def usb_partitions():
    """Partitions on USB disks. The Pi SD card (mmcblk) is ignored."""
    try:
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,PATH,TYPE,TRAN,MOUNTPOINT'],
            capture_output=True, text=True, timeout=5
        )
        devices = json.loads(result.stdout).get('blockdevices', [])
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, OSError):
        devices = []

    found = []
    for disk in devices:
        path = device_path(disk)
        tran = disk.get('tran') or ''
        if disk.get('type') != 'disk':
            continue
        if path.startswith('/dev/mmcblk'):
            continue
        if tran != 'usb' and not path.startswith('/dev/sd'):
            continue
        children = [child for child in (disk.get('children') or []) if child.get('type') == 'part']
        for child in children:
            child_path = device_path(child)
            if child_path:
                child = dict(child)
                child['path'] = child_path
                found.append(child)
        # A filesystem directly on the disk, with no partition table.
        if not children and path:
            disk = dict(disk)
            disk['path'] = path
            found.append(disk)

    if found:
        return found

    return [{'path': device, 'mountpoint': None} for device in sorted(glob.glob('/dev/sd*[0-9]'))]


def mount_partition(device):
    """Mount an unmounted USB partition under /media/usb-video."""
    existing = findmnt_target(device)
    if existing:
        return existing

    mount_path = os.path.join(AUTO_MOUNT_ROOT, os.path.basename(device))
    if not os.path.isdir(mount_path):
        try:
            if os.geteuid() == 0:
                os.makedirs(mount_path, exist_ok=True)
            else:
                made = run_as_root(['mkdir', '-p', mount_path])
                if made.returncode != 0:
                    detail = (made.stderr or made.stdout).strip()
                    print(f"Could not create {mount_path}: {detail}", flush=True)
                    return None
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"Could not create {mount_path}: {exc}", flush=True)
            return None

    if os.path.ismount(mount_path):
        return mount_path

    print(f"Mounting {device} at {mount_path}", flush=True)
    try:
        result = run_as_root(['mount', device, mount_path])
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"Could not mount {device}: {exc}", flush=True)
        return None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        print(f"Could not mount {device}: {detail}", flush=True)
        return None
    return mount_path


def remember_usb(mount_path, device):
    current_usb['mount'] = mount_path
    current_usb['device'] = device
    return mount_path


def find_usb_mount_point():
    """Find a USB stick that contains a video folder, mounting it if needed."""
    for part in usb_partitions():
        device = part.get('path')
        if not device:
            continue
        mount_path = part.get('mountpoint') or findmnt_target(device)
        if not mount_path:
            mount_path = mount_partition(device)
        if mount_path and has_video_folder(mount_path):
            return remember_usb(mount_path, device)

    # Desktop automount uses /media/<user>/<label>, two levels under /media.
    for mount_base in USB_MOUNT_POINTS:
        if not os.path.isdir(mount_base):
            continue
        try:
            candidates = [os.path.join(mount_base, item) for item in os.listdir(mount_base)]
        except PermissionError:
            continue
        deeper = []
        for mount_path in candidates:
            if has_video_folder(mount_path):
                return remember_usb(mount_path, findmnt_target_source(mount_path))
            if os.path.isdir(mount_path):
                try:
                    deeper.extend(
                        os.path.join(mount_path, item) for item in os.listdir(mount_path)
                    )
                except PermissionError:
                    continue
        for mount_path in deeper:
            if has_video_folder(mount_path):
                return remember_usb(mount_path, findmnt_target_source(mount_path))

    return None


def findmnt_target_source(mount_path):
    try:
        result = subprocess.run(
            ['findmnt', '-n', '-o', 'SOURCE', mount_path],
            capture_output=True, text=True, timeout=2
        )
        source = result.stdout.strip()
        if result.returncode == 0 and source.startswith('/dev/'):
            return source
    except (subprocess.TimeoutExpired, FileNotFoundError):
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

    # FAT volumes from macOS include AppleDouble files such as ._clip.mp4.
    unique = []
    seen = set()
    for path in video_files:
        name = os.path.basename(path)
        if name.startswith('._') or name.startswith('.'):
            continue
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)

    unique.sort(key=str.lower)
    return unique


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


def get_video_duration(video_path):
    """Return video duration in seconds via ffprobe, or DEFAULT_VIDEO_DURATION if unavailable."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', video_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return DEFAULT_VIDEO_DURATION


def get_total_playlist_duration(video_files):
    """Probe each video and return the summed duration for watchdog calculation."""
    print("Probing video durations for watchdog timer...", flush=True)
    total = 0
    for video in video_files:
        dur = get_video_duration(video)
        total += dur
        print(f"  {os.path.basename(video)}: {dur:.0f}s ({dur / 60:.1f} min)", flush=True)
    print(f"Total playlist: {total:.0f}s ({total / 60:.1f} min) — "
          f"watchdog fires at {(total + WATCHDOG_BUFFER_SECONDS):.0f}s", flush=True)
    return total


def run_with_usb_monitor(proc, usb_path, watchdog_timeout=None):
    """
    Poll a Popen process every 2 seconds.
    - USB removed  → kill player, sys.exit(0)
    - watchdog_timeout exceeded → kill player, return 'watchdog'  (caller restarts)
    - Process exits normally    → return its exit code
    """
    start = time.time()
    while True:
        ret = proc.poll()
        if ret is not None:
            return ret

        device = current_usb.get('device')
        if (device and not os.path.exists(device)) or not os.path.isdir(usb_path):
            print("USB removed - stopping video immediately.", flush=True)
            if usb_path.startswith(AUTO_MOUNT_ROOT + os.sep):
                try:
                    run_as_root(['umount', '-l', usb_path])
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            sys.exit(0)

        if watchdog_timeout is not None:
            elapsed = time.time() - start
            if elapsed > watchdog_timeout:
                print(f"Watchdog: player has been running {elapsed:.0f}s "
                      f"(limit {watchdog_timeout:.0f}s) — appears stuck, restarting...",
                      flush=True)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return 'watchdog'

        time.sleep(2)


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
    print("=" * 50, flush=True)

    try:
        if player_cmd == 'mpv':
            # Single mpv process plays the entire playlist; watchdog restarts if frozen
            total_duration = get_total_playlist_duration(video_files)
            watchdog_timeout = total_duration + WATCHDOG_BUFFER_SECONDS
            while True:
                valid_videos = verify_videos_exist(video_files)
                if not valid_videos:
                    print("Videos no longer accessible.", flush=True)
                    sys.exit(0)
                cmd = ['mpv', '--fullscreen', '--loop-playlist=inf', '--no-audio',
                       '--no-input-default-bindings', '--really-quiet',
                       '--osd-level=0'] + valid_videos
                print(f"Starting mpv playlist ({len(valid_videos)} video(s), "
                      f"watchdog: {watchdog_timeout:.0f}s)...", flush=True)
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                run_with_usb_monitor(proc, usb_path, watchdog_timeout=watchdog_timeout)
                print("Restarting mpv (exited or watchdog)...", flush=True)
                time.sleep(2)

        elif player_cmd == 'vlc':
            # Single VLC process — one window, no gaps between videos.
            # Watchdog kills and restarts VLC if it freezes on a specific video.
            total_duration = get_total_playlist_duration(video_files)
            watchdog_timeout = total_duration + WATCHDOG_BUFFER_SECONDS
            while True:
                valid_videos = verify_videos_exist(video_files)
                if not valid_videos:
                    print("Videos no longer accessible.", flush=True)
                    sys.exit(0)
                cmd = ['vlc', '--fullscreen', '--loop', '--no-audio',
                       '--no-video-title-show', '--no-osd',
                       '--no-qt-system-tray', '--no-qt-error-dialogs',
                       '--file-caching=5000',   # 5-second read buffer from USB
                       '--no-stats'] + valid_videos
                print(f"Starting VLC playlist ({len(valid_videos)} video(s), "
                      f"watchdog: {watchdog_timeout:.0f}s)...", flush=True)
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                run_with_usb_monitor(proc, usb_path, watchdog_timeout=watchdog_timeout)
                print("Restarting VLC (exited or watchdog)...", flush=True)
                time.sleep(2)

        elif player_cmd == 'omxplayer':
            # omxplayer cannot play playlists — spawn per video.
            # xsetroot paints the desktop black to hide the gap between clips.
            try:
                subprocess.run(['xsetroot', '-solid', 'black'],
                               capture_output=True, timeout=2)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            while True:
                valid_videos = verify_videos_exist(video_files)
                if not valid_videos:
                    print("Videos no longer accessible.", flush=True)
                    sys.exit(0)
                for video in valid_videos:
                    if not os.path.exists(usb_path):
                        print("USB removed - stopping.", flush=True)
                        sys.exit(0)
                    dur = get_video_duration(video)
                    watchdog_timeout = dur + WATCHDOG_BUFFER_SECONDS
                    print(f"Playing: {os.path.basename(video)} "
                          f"(watchdog: {watchdog_timeout:.0f}s)", flush=True)
                    proc = subprocess.Popen(
                        ['omxplayer', '-b', '--no-osd', video],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    run_with_usb_monitor(proc, usb_path, watchdog_timeout=watchdog_timeout)
                print("Playlist finished, looping...", flush=True)

        else:
            print(f"Unknown player: {player_cmd}", flush=True)
            return False

    except KeyboardInterrupt:
        print("\nStopping video playback...", flush=True)
        return True
    except SystemExit:
        raise
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
