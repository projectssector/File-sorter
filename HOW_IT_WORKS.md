# How File Sorter Works

## Overview

File Sorter is a Tkinter desktop application (`file_sorter.py`) with three main areas:

- **Commands tab**: list of hotkey -> destination folder commands.
- **Image Sorter tab**: preview and file images.
- **Memory tab**: retained commands that were removed from the active list.
- **Gamepad tab**: controller detection and button mapping.

## Core modules

- `sorter_core.py`: constants, paths (`%APPDATA%\FileSorter`), config load/save, hotkey parsing, file move helpers, XInput constants.
- `sorter_ui.py`: ttk styles and dialogs (`CommandDialog`, `MemoryWindow`).
- `file_sorter.py`: main app, global hotkey engine, command management, tabs.
- `image_sorter_ui.py`: image preview, filmstrip, destinations, keyboard navigation.
- `gamepad_core.py`: XInput polling, button detection, `.amgp` import, mapping load/save.
- `gamepad_ui.py`: gamepad status and mapping UI.

## Data flow

1. On startup, `FileSorterApp._load_config()` reads `commands.ini` (active) and `history.ini` (memory).
2. `GlobalHotkeyEngine` registers each active command's hotkey.
3. When a hotkey fires, `_on_hotkey()` starts a worker thread that:
   - waits for modifier keys to release,
   - verifies File Explorer is foreground,
   - reads the current Explorer selection,
   - moves items to the destination,
   - reports results via the UI queue.
4. The UI queue (`_ui`) marshals worker-thread callbacks onto the Tkinter main thread.

## Image Sorter

- Collects image files from files/folders/drag-and-drop.
- Renders the current image and a filmstrip.
- Destination buttons and keyboard digits move the current image to the matching folder.
- Navigation: Left/Right/PgUp/PgDn/Space/Home/End/Delete/Backspace/o/Ctrl+Z.
- Moves are recorded for Undo.

## Gamepad

- `GamepadManager` polls XInput slots in a background thread.
- Button presses are marshaled to the UI thread.
- If the image sorter is open, mapped buttons file the current image; unmapped buttons navigate.
- Otherwise, mapped buttons trigger the normal Explorer move worker.
- Mappings are stored in `%APPDATA%\FileSorter\gamepad.ini` and can be imported from a Steam `.amgp` file.

## Persistence

- Active commands: `%APPDATA%\FileSorter\commands.ini`
- Command memory: `%APPDATA%\FileSorter\history.ini`
- Gamepad mappings: `%APPDATA%\FileSorter\gamepad.ini`
- Errors: `%APPDATA%\FileSorter\errors.log`