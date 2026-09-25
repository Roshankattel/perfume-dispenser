@echo off
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name generate_wifi_qr ^
  --hidden-import segno ^
  --hidden-import png ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  generate_wifi_qr.py
if errorlevel 1 exit /b 1

echo.
echo Built: "%~dp0dist\generate_wifi_qr.exe"
echo Copy that file anywhere. Double-click it, type a serial, click
echo Generate. The QR PNG is saved in the same folder as the exe.
echo The window stays open so you can generate another.
echo.
pause
