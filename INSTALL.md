# Installation

## Option 1: Installer (recommended)

1. Download `FileSorterSetup.exe`.
2. Double-click it. If Windows SmartScreen appears, choose **More info** -> **Run anyway**.
3. Follow the wizard. The app installs to `%LOCALAPPDATA%\Programs\File Sorter`.
4. Launch from the Start menu or desktop shortcut.

## Option 2: Portable executable

1. Download `FileSorter.exe`.
2. Place it anywhere.
3. Run it. Configuration is stored in `%APPDATA%\FileSorter`.

## Requirements

- Windows 10 or later (x64).
- For gamepad support: an Xbox-compatible controller with XInput drivers (built into Windows).
- For building from source: Python 3.12+, dependencies in `requirements.txt`.

## Build from source

```powershell
python -m pip install -r requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

This produces `FileSorter.exe` and `FileSorterSetup.exe`.

## Uninstall

Use Windows **Settings -> Apps -> Installed apps -> File Sorter -> Uninstall**, or run the uninstaller from the install folder. User data in `%APPDATA%\FileSorter` is left in place; delete it manually if desired.