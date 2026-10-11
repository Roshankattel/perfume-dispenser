# Raspberry Pi OS Lite installation

This guide installs the perfume dispenser and the USB video player on a Raspberry Pi with no desktop. Follow the steps in order. A keyboard and HDMI screen are needed only to confirm video playback. All setup commands are typed over SSH.

The steps below match the installation on the controller `perfume-dispenser` (user `arvella`) on 11 October 2026.

## 1 Versions

| Item | Version |
|---|---|
| Board | Raspberry Pi 4 Model B Rev 1.4 |
| Operating system | Raspberry Pi OS Lite, 64-bit. Image reference 2026-10-06 (`pi-gen` stage2). Debian GNU/Linux 13.7 (trixie) |
| Kernel | `6.18.50+rpt-rpi-v8` (1:6.18.50-1+rpt1, 11 September 2026) |
| Software | Perfume Dispenser 1.1.0 |
| Python | 3.13.5 |
| mpv | 0.40.0-3+deb13u1 |
| python3-serial | 3.5-2 |
| python3-segno | 1.6.6-2 |
| python3-png | 0.20231004.0-4 |
| python3-rpi-lgpio | 0.6-0~rpt1+trixie (this package provides `RPi.GPIO`) |
| NetworkManager | 1.52.1-1+rpt4 |
| nftables | 1.1.3-1 |

`ffprobe` is installed together with `mpv`. The video player uses it to time the playlist.

A 2 GB Raspberry Pi 4 is the board to buy. On this Lite system the whole machine used about 400 MB while a video was playing and the dispenser was running. A 1 GB board can run this load. There is no official 3 GB Raspberry Pi.

## 2 What you need

- A Raspberry Pi 4 with a microSD card of at least 16 GB
- A computer with Raspberry Pi Imager
- The project folder from this repository
- A USB flash drive for the videos (prepared in section 8)
- The Pi on the same network as your computer, with SSH enabled

## 3 Write the operating system

1. Open Raspberry Pi Imager.
2. Choose **Raspberry Pi OS (other)** and then **Raspberry Pi OS Lite (64-bit)**. The image must be the Debian 13 (trixie) Lite image, 64-bit. Do not choose the desktop image.
3. Choose the microSD card.
4. Open the imager settings before you write the card:
   - Set a hostname, for example `perfume-dispenser`.
   - Set a username and password. This guide uses the username `arvella`. Use your own username and replace `arvella` in the later commands.
   - Enable SSH. Password authentication is enough.
   - Set the Wi-Fi network if the Pi will not use an Ethernet cable.
5. Write the card, put it in the Pi, and power the Pi on.
6. From your computer, connect:

   ```bash
   ssh arvella@perfume-dispenser.local
   ```

   If the name does not resolve, find the Pi's address in your router and use `ssh arvella@<ip-address>`.

## 4 Install the packages

On the Pi, update the package list and install the player and the Python libraries:

```bash
sudo apt update
sudo apt install -y mpv python3-serial python3-segno python3-png python3-rpi-lgpio
```

Confirm NetworkManager and nftables are present. The Lite image already includes them. If either command prints nothing, install that package.

```bash
dpkg-query -W network-manager nftables
sudo apt install -y network-manager nftables
```

Do not use `pip install` for these libraries. Debian 13 blocks system-wide pip installs. The `apt` packages above are the ones the services import.

## 5 Copy the project

On your computer, from the project folder:

```bash
rsync -a --exclude .git --exclude __pycache__ ./ arvella@perfume-dispenser.local:Documents/perfume-dispenser/
```

The files must end up in:

```text
/home/arvella/Documents/perfume-dispenser/
```

That folder must contain `perfume_dispenser.py`, `video_player.py`, `install-service.sh`, and `install-video-player.sh`.

## 6 Install the perfume dispenser service

On the Pi:

```bash
cd /home/arvella/Documents/perfume-dispenser
chmod +x install-service.sh install-video-player.sh
sudo ./install-service.sh
```

The script looks for `/home/arvella/perfume-dispenser` first. That folder does not exist, so the script asks for the project path. Type:

```text
/home/arvella/Documents/perfume-dispenser
```

The script enables `perfume-dispenser.service`. The service runs as **root**. Root is required for the Wi-Fi hotspot, the firewall, and GPIO.

Start it now:

```bash
sudo systemctl start perfume-dispenser
```

## 7 Install the video player service

On the Pi, from the same folder:

```bash
sudo ./install-video-player.sh
```

When the script asks whether to start the service now, type `y`.

The script does three things:

- It checks that `mpv` is installed.
- It sets the service user to the user who ran `sudo` (`arvella`).
- It allows that user to run only `mount`, `umount`, and `mkdir` without a password. The player needs this because Raspberry Pi OS Lite does not mount a USB stick by itself.

The rule is written to `/etc/sudoers.d/video-player-mount`.

## 8 Prepare the USB flash drive

The player only plays files from the **first partition**, and only from a folder named `video`.

1. Copy the `video` folder off the stick before you erase it.
2. On a Mac, open Disk Utility, choose **View → Show All Devices**, and select the physical USB drive.
3. Erase it. Set **Format** to **MS-DOS (FAT)** and **Scheme** to **Master Boot Record**.
4. Create a folder named `video` on the stick and copy the video files into that folder.
5. Eject the stick and plug it into the Pi.

A stick that was formatted on a Mac often has a small EFI partition first and the videos on the second partition. The player does not use that second partition. After the erase above, the stick has one partition, `sda1`.

Supported file types are `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.wmv`, `.flv`, and `.webm`. Files are played in alphabetical order, with no sound, in a loop.

When the stick is inserted, the player mounts it at `/media/usb-video/sda1` and starts `mpv`. No desktop is required. The picture goes to the HDMI screen.

## 9 Check that both services are running

```bash
sudo systemctl status perfume-dispenser video-player
```

Both units must show `active (running)` and `enabled`.

Dispenser log:

```bash
sudo journalctl -u perfume-dispenser -n 30 --no-pager
```

A healthy dispenser log ends with `Setup complete - System ready!` and `Waiting for card tap...`.

Video player log:

```bash
sudo journalctl -u video-player -n 30 --no-pager
```

With the stick inserted, the log shows `Mounting /dev/sda1` and `Starting mpv playlist`.

Other commands:

```bash
sudo systemctl restart perfume-dispenser
sudo systemctl restart video-player
sudo systemctl stop video-player
```

## 10 What is installed where

| Item | Location |
|---|---|
| Project | `/home/arvella/Documents/perfume-dispenser` |
| Dispenser service | `/etc/systemd/system/perfume-dispenser.service` (user `root`) |
| Video service | `/etc/systemd/system/video-player.service` (user `arvella`) |
| USB mount permission | `/etc/sudoers.d/video-player-mount` |
| USB mount point | `/media/usb-video/sda1` |
| Video folder on the stick | `/media/usb-video/sda1/video` |

Both services start on boot. The video service waits 15 seconds, then waits for a USB stick. If the stick is removed, playback stops. When the stick is inserted again, playback starts again.
