"""Core helpers for File Sorter: Win32, hotkeys, clipboard, config, moving."""

from __future__ import annotations

import configparser
import ctypes
import logging
import logging.handlers
import os
import shutil
import sys
import threading
import time
import xml.etree.ElementTree as ET
from ctypes import wintypes
from pathlib import Path

APP_NAME = "File Sorter"
APP_VERSION = "1.3.0"
APP_ID = "FileSorter"

BG = "#0d1117"
CARD = "#161c24"
CARD_2 = "#1f2935"
BORDER = "#2b3542"
TEXT = "#e6edf3"
MUTED = "#8b98a8"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
SUCCESS = "#22c55e"
WARN = "#f59e0b"
DANGER = "#ef4444"
FONT = "Segoe UI"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".jpe",
    ".jfif",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
    ".ico",
    ".heic",
    ".heif",
    ".avif",
}


def default_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_ID


DATA_DIR = Path(os.environ.get("FILESORTER_DATA_DIR") or default_data_dir())
ACTIVE_FILE = DATA_DIR / "commands.ini"
HISTORY_FILE = DATA_DIR / "history.ini"
GAMEPAD_FILE = DATA_DIR / "gamepad.ini"
LOG_FILE = DATA_DIR / "errors.log"
DEFAULT_GAMEPAD_PROFILE = r"E:\file mover\keypad.gamecontroller.amgp"


def setup_logging() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=256 * 1024, backupCount=1, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
    except Exception:
        pass


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


# ---------------------------------------------------------------------------
# Win32 setup
# ---------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except Exception:
    dwmapi = None

LRESULT = ctypes.c_ssize_t

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]

shell32.DragQueryFileW.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,
    wintypes.LPWSTR,
    wintypes.UINT,
]
shell32.DragQueryFileW.restype = wintypes.UINT


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    ctypes.c_void_p,
    wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallNextHookEx.restype = LRESULT
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostThreadMessageW.restype = wintypes.BOOL


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [
    wintypes.UINT,
    ctypes.POINTER(INPUT),
    ctypes.c_int,
]
user32.SendInput.restype = wintypes.UINT

try:
    dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
except Exception:
    pass

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

MODIFIER_VKS = {
    0x10: "shift",
    0xA0: "shift",
    0xA1: "shift",
    0x11: "ctrl",
    0xA2: "ctrl",
    0xA3: "ctrl",
    0x12: "alt",
    0xA4: "alt",
    0xA5: "alt",
    0x5B: "win",
    0x5C: "win",
}
MODIFIER_WORDS = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "win": "win",
    "windows": "win",
    "lwin": "win",
    "rwin": "win",
    "meta": "win",
    "super": "win",
}
ALL_MODIFIER_VKS = (0x10, 0xA0, 0xA1, 0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5, 0x5B, 0x5C)

KEY_NAME_TO_VK = {
    "backspace": 0x08,
    "bksp": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "pause": 0x13,
    "break": 0x13,
    "capslock": 0x14,
    "caps": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "spacebar": 0x20,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "snapshot": 0x2C,
    "insert": 0x2D,
    "ins": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "apps": 0x5D,
    "appskey": 0x5D,
    "sleep": 0x5F,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "semicolon": 0xBA,
    ";": 0xBA,
    "equals": 0xBB,
    "=": 0xBB,
    "comma": 0xBC,
    ",": 0xBC,
    "minus": 0xBD,
    "-": 0xBD,
    "period": 0xBE,
    ".": 0xBE,
    "slash": 0xBF,
    "/": 0xBF,
    "backtick": 0xC0,
    "grave": 0xC0,
    "`": 0xC0,
    "leftbracket": 0xDB,
    "[": 0xDB,
    "backslash": 0xDC,
    "rightbracket": 0xDD,
    "]": 0xDD,
    "quote": 0xDE,
    "'": 0xDE,
    "multiply": 0x6A,
    "add": 0x6B,
    "separator": 0x6C,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
    "volumemute": 0xAD,
    "volumedown": 0xAE,
    "volumeup": 0xAF,
    "medianext": 0xB0,
    "mediaprev": 0xB1,
    "mediastop": 0xB2,
    "mediaplaypause": 0xB3,
    "launchmail": 0xB4,
    "launchmedia": 0xB5,
    "launchapp1": 0xB6,
    "launchapp2": 0xB7,
}
for _i in range(1, 25):
    KEY_NAME_TO_VK["f" + str(_i)] = 0x6F + _i
for _i in range(10):
    KEY_NAME_TO_VK["numpad" + str(_i)] = 0x60 + _i


# ---------------------------------------------------------------------------
# Hotkey parsing
# ---------------------------------------------------------------------------


def _clean_key_token(token: str) -> str:
    token = token.strip()
    if len(token) == 1:
        return token.lower()
    return token.lower().replace(" ", "").replace("_", "").replace("-", "")


def _unwrap_braces(token: str) -> str:
    token = token.strip()
    if (
        token.startswith("{")
        and token.endswith("}")
        and token.count("{") == 1
        and token.count("}") == 1
    ):
        return token[1:-1].strip()
    return token


def parse_hotkey(hotkey: str):
    """Convert a friendly/AHK-style hotkey into (modifiers, virtual key code)."""
    raw = (hotkey or "").strip()
    if not raw:
        raise ValueError("Hotkey is empty.")
    while raw and raw[0] in "~$*":
        raw = raw[1:]
    raw = raw.strip()
    if not raw:
        raise ValueError("Hotkey is empty.")

    lower = raw.lower()
    textual_mods = (
        "ctrl",
        "control",
        "shift",
        "alt",
        "win",
        "windows",
        "meta",
        "super",
    )
    has_textual_mod = any(word in lower for word in textual_mods)
    mods = set()
    key_token = None

    if has_textual_mod and "+" in raw:
        for part in raw.split("+"):
            if not part.strip():
                if key_token is not None:
                    raise ValueError("Use only one key in a hotkey.")
                key_token = "+"
                continue
            token = _unwrap_braces(part)
            word = token.lower()
            if word in MODIFIER_WORDS:
                mods.add(MODIFIER_WORDS[word])
            else:
                if key_token is not None:
                    raise ValueError("Use only one key in a hotkey.")
                key_token = token
        if key_token is None:
            raise ValueError("Add a key to the hotkey (for example: ctrl+shift+m).")
    else:
        while raw:
            ch = raw[0]
            if ch in "<>":
                raw = raw[1:]
                continue
            if ch in "^!+#":
                mods.add({"^": "ctrl", "!": "alt", "+": "shift", "#": "win"}[ch])
                raw = raw[1:]
            else:
                break
        key_token = _unwrap_braces(raw)
        if not key_token:
            raise ValueError("Add a key to the hotkey (for example: ctrl+shift+m).")

    if key_token.lower() in MODIFIER_WORDS:
        raise ValueError(
            "Modifier-only hotkeys are not supported. Add a key (for example: ctrl+m)."
        )

    clean = _clean_key_token(key_token)
    vk = None
    if clean in KEY_NAME_TO_VK:
        vk = KEY_NAME_TO_VK[clean]
    elif len(key_token) == 1:
        ch = key_token.lower()
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            vk = ord(ch.upper())
        else:
            result = user32.VkKeyScanW(key_token)
            if result == -1:
                raise ValueError("Unknown key: " + repr(key_token))
            vk = result & 0xFF
            shift_state = (result >> 8) & 0xFF
            if shift_state & 1:
                mods.add("shift")
            if shift_state & 2:
                mods.add("ctrl")
            if shift_state & 4:
                mods.add("alt")
    else:
        raise ValueError("Unknown key: " + repr(key_token))

    if vk in MODIFIER_VKS:
        raise ValueError(
            "Modifier-only hotkeys are not supported. Add a key (for example: ctrl+m)."
        )

    return frozenset(mods), int(vk)


KEYSYM_TO_VK = {
    "escape": 0x1B,
    "return": 0x0D,
    "tab": 0x09,
    "backspace": 0x08,
    "space": 0x20,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "prior": 0x21,
    "next": 0x22,
    "caps_lock": 0x14,
    "num_lock": 0x90,
    "scroll_lock": 0x91,
    "pause": 0x13,
    "print": 0x2C,
    "sys_req": 0x2C,
    "comma": 0xBC,
    "period": 0xBE,
    "slash": 0xBF,
    "semicolon": 0xBA,
    "equal": 0xBB,
    "minus": 0xBD,
    "grave": 0xC0,
    "quoteleft": 0xC0,
    "bracketleft": 0xDB,
    "backslash": 0xDC,
    "bracketright": 0xDD,
    "apostrophe": 0xDE,
    "quoteright": 0xDE,
    "multiply": 0x6A,
    "add": 0x6B,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
}
for _i in range(1, 25):
    KEYSYM_TO_VK["f" + str(_i)] = 0x6F + _i
for _i in range(10):
    KEYSYM_TO_VK["kp_" + str(_i)] = 0x60 + _i


def keysym_to_vk(keysym: str):
    """Best-effort conversion of a Tk keysym into a Windows virtual key code."""
    name = (keysym or "").lower()
    if not name:
        return None
    if name in KEYSYM_TO_VK:
        return KEYSYM_TO_VK[name]
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    return None


def vk_from_char(character: str):
    """Return the virtual key code for a typed character, if available."""
    if not character or len(character) != 1:
        return None
    try:
        result = user32.VkKeyScanW(character)
    except Exception:
        return None
    if result == -1:
        return None
    return int(result & 0xFF)


# ---------------------------------------------------------------------------
# Clipboard / file helpers
# ---------------------------------------------------------------------------


def clipboard_sequence() -> int:
    return int(user32.GetClipboardSequenceNumber())


def get_clipboard_files() -> list[str]:
    files = []
    if not user32.OpenClipboard(None):
        return files
    try:
        handle = user32.GetClipboardData(15)  # CF_HDROP
        if not handle:
            return files
        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        for index in range(count):
            length = shell32.DragQueryFileW(handle, index, None, 0)
            buffer = ctypes.create_unicode_buffer(length + 1)
            if shell32.DragQueryFileW(handle, index, buffer, length + 1):
                files.append(buffer.value)
    finally:
        user32.CloseClipboard()
    return files


def get_clipboard_text() -> str:
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def send_ctrl_c() -> bool:
    inputs = (INPUT * 4)()
    sequence = ((0x11, 0), (0x43, 0), (0x43, KEYEVENTF_KEYUP), (0x11, KEYEVENTF_KEYUP))
    for index, (vk, flags) in enumerate(sequence):
        inputs[index].type = INPUT_KEYBOARD
        inputs[index].ki = KEYBDINPUT(
            wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0
        )
    return user32.SendInput(4, inputs, ctypes.sizeof(INPUT)) == 4


def text_to_paths(text: str) -> list[str]:
    paths = []
    for line in (text or "").splitlines():
        candidate = line.strip().strip('"').strip("'")
        if candidate and os.path.exists(candidate):
            paths.append(candidate)
    return paths


def copy_selection_and_read() -> list[str]:
    before = clipboard_sequence()
    if not send_ctrl_c():
        return []
    deadline = time.time() + 1.5
    while time.time() < deadline:
        if clipboard_sequence() != before:
            break
        time.sleep(0.03)
    files = get_clipboard_files()
    if files:
        return files
    return text_to_paths(get_clipboard_text())


def wait_for_modifiers_released(timeout: float = 1.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in ALL_MODIFIER_VKS):
            return True
        time.sleep(0.02)
    return False


EXPLORER_WINDOW_CLASSES = {"CabinetWClass", "ExploreWClass", "Progman", "WorkerW"}


def is_explorer_foreground() -> bool:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    buffer = ctypes.create_unicode_buffer(128)
    if user32.GetClassNameW(hwnd, buffer, 128):
        return buffer.value in EXPLORER_WINDOW_CLASSES
    return False


def unique_target(folder: Path, name: str) -> Path:
    target = folder / name
    if not target.exists():
        return target
    source = Path(name)
    stem = source.stem
    suffix = source.suffix
    counter = 1
    while True:
        candidate = folder / (stem + " (" + str(counter) + ")" + suffix)
        if not candidate.exists():
            return candidate
        counter += 1


def is_image_file(path: str) -> bool:
    try:
        return Path(path).suffix.lower() in IMAGE_EXTENSIONS
    except Exception:
        return False


def natural_sort_key(value):
    import re

    return [
        int(chunk) if chunk.isdigit() else chunk.lower()
        for chunk in re.split(r"(\d+)", str(value))
    ]


def collect_image_files(paths) -> list[str]:
    """Expand files/folders into a de-duplicated list of image files."""
    found = []
    seen = set()

    def add(candidate: Path) -> None:
        try:
            resolved = candidate.resolve()
            key = os.path.normcase(str(resolved))
        except Exception:
            key = os.path.normcase(str(candidate))
        if key in seen:
            return
        if candidate.is_file() and is_image_file(str(candidate)):
            seen.add(key)
            found.append(str(candidate))

    for raw in paths or []:
        candidate = Path(str(raw).strip().strip('"'))
        try:
            if candidate.is_dir():
                for entry in sorted(candidate.iterdir(), key=natural_sort_key):
                    add(entry)
            else:
                add(candidate)
        except Exception:
            continue
    return found


def move_single_file(source: str, destination: str):
    """Move one file and return (ok, new_path_or_error)."""
    src = Path(source)
    dest = Path(destination)
    if not src.exists():
        return False, "File no longer exists."
    if not src.is_file():
        return False, "Only files can be moved here."
    if not dest.is_dir():
        return False, "Destination folder was not found."
    try:
        if src.resolve().parent == dest.resolve():
            return False, "That file is already in this folder."
        target = unique_target(dest, src.name)
        shutil.move(str(src), str(target))
        return True, str(target)
    except Exception as exc:
        return False, str(exc)


def restore_moved_file(moved_path: str, original_path: str):
    """Undo a move, returning (ok, restored_path_or_error)."""
    moved = Path(moved_path)
    original = Path(original_path)
    if not moved.exists():
        return False, "The moved file is no longer there."
    folder = original.parent
    if not folder.is_dir():
        return False, "The original folder no longer exists."
    try:
        target = unique_target(folder, original.name) if original.exists() else original
        shutil.move(str(moved), str(target))
        return True, str(target)
    except Exception as exc:
        return False, str(exc)


def format_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return (str(int(value)) + " " + unit) if unit == "B" else (
                "{:.1f} {}".format(value, unit)
            )
        value /= 1024
    return str(size) + " B"


def move_items(files: list[str], destination: str):
    dest = Path(destination)
    moved = 0
    failed = 0
    skipped = 0
    errors = []
    if not dest.is_dir():
        return 0, len(files), 0, ["Destination not found: " + str(dest)]

    for raw in files:
        source = Path(raw)
        if not source.exists():
            skipped += 1
            continue
        try:
            source_resolved = source.resolve()
            dest_resolved = dest.resolve()
            if (
                source_resolved == dest_resolved
                or source_resolved in dest_resolved.parents
            ):
                skipped += 1
                continue
            target = unique_target(dest, source.name)
            shutil.move(str(source), str(target))
            moved += 1
        except Exception as exc:
            failed += 1
            if len(errors) < 3:
                errors.append(source.name + ": " + str(exc))
    return moved, failed, skipped, errors


def short_path(path: str, parts: int = 2) -> str:
    try:
        p = Path(os.path.normpath(path))
        chunks = p.parts
        if len(chunks) > parts:
            return os.path.join("...", *chunks[-parts:])
        return str(p)
    except Exception:
        return str(path)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def load_commands(path: Path) -> list[dict[str, str]]:
    commands = []
    try:
        if not path.exists():
            return commands
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            hotkey, folder = line.split("|", 1)
            hotkey = hotkey.strip()
            folder = folder.strip()
            if hotkey and folder:
                commands.append({"hotkey": hotkey, "folder": folder})
    except Exception:
        logging.exception("Failed to read %s", path)
    return commands


def save_commands(path: Path, commands: list[dict[str, str]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with open(temp, "w", encoding="utf-8", newline="\n") as handle:
            for command in commands:
                hotkey = str(command.get("hotkey", "")).replace("|", "/").replace("\n", "")
                folder = str(command.get("folder", "")).replace("|", "/").replace("\n", "")
                handle.write(hotkey + "|" + folder + "\n")
        os.replace(temp, path)
    except Exception:
        logging.exception("Failed to write %s", path)


def command_signature(command: dict[str, str]):
    try:
        mods, vk = parse_hotkey(command["hotkey"])
        hotkey_sig = (tuple(sorted(mods)), vk)
    except Exception:
        hotkey_sig = command["hotkey"].strip().lower()
    folder_sig = os.path.normcase(os.path.normpath(command["folder"]))
    return hotkey_sig, folder_sig


def migrate_legacy_config() -> None:
    if ACTIVE_FILE.exists() or HISTORY_FILE.exists():
        return
    candidates = [
        Path.cwd() / "commands.ini",
        Path(sys.executable).resolve().parent / "commands.ini",
        Path(sys.executable).resolve().parent.parent / "commands.ini",
        Path(__file__).resolve().parent / "commands.ini",
        Path(__file__).resolve().parent.parent / "commands.ini",
    ]
    seen = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        if not candidate.exists():
            continue
        commands = load_commands(candidate)
        if commands:
            save_commands(ACTIVE_FILE, commands)
            save_commands(HISTORY_FILE, commands)
            logging.info("Imported legacy commands from %s", candidate)
            return


# ---------------------------------------------------------------------------
# Native global hotkey engine
# ---------------------------------------------------------------------------


class GlobalHotkeyEngine:
    def __init__(self, callback):
        self._callback = callback
        self._entries = {}
        self._lock = threading.RLock()
        self._pressed_mods = set()
        self._triggered_vks = set()
        self._enabled = True
        self._suspended = False
        self._thread = None
        self._thread_id = 0
        self._hook = None
        self._ready = threading.Event()
        self._error = None
        self._hook_proc = HOOKPROC(self._hook_callback)

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name="file-sorter-hotkeys", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self._hook is not None, self._error

    def _run(self):
        try:
            self._thread_id = int(kernel32.GetCurrentThreadId())
            module = kernel32.GetModuleHandleW(None)
            self._hook = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._hook_proc, module, 0
            )
            if not self._hook:
                error_code = ctypes.get_last_error()
                self._error = "SetWindowsHookEx failed (error " + str(error_code) + ")"
                logging.error(self._error)
                self._ready.set()
                return
            logging.info("Global hotkey hook started.")
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:
            self._error = str(exc)
            logging.exception("Hotkey hook thread failed")
            self._ready.set()
        finally:
            if self._hook:
                try:
                    user32.UnhookWindowsHookEx(self._hook)
                except Exception:
                    pass
                self._hook = None

    def stop(self):
        if self._thread_id:
            try:
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)

    def set_suspended(self, suspended: bool):
        self._suspended = bool(suspended)
        if suspended:
            self._pressed_mods.clear()
            self._triggered_vks.clear()

    def set_hotkeys(self, commands):
        entries = {}
        errors = []
        for command in commands:
            try:
                mods, vk = parse_hotkey(command["hotkey"])
            except Exception as exc:
                errors.append((command["hotkey"], str(exc)))
                continue
            key = (mods, vk)
            if key in entries:
                errors.append((command["hotkey"], "Hotkey is used more than once."))
                continue
            entries[key] = dict(command)
        with self._lock:
            self._entries = entries
        return errors

    def _hook_callback(self, n_code, w_param, l_param):
        try:
            if n_code < 0:
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if info.flags & LLKHF_INJECTED:
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            vk = int(info.vkCode)
            modifier = MODIFIER_VKS.get(vk)
            if modifier:
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    self._pressed_mods.add(modifier)
                elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                    self._pressed_mods.discard(modifier)
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if vk in self._triggered_vks:
                    return 1
                if not self._enabled or self._suspended:
                    return user32.CallNextHookEx(None, n_code, w_param, l_param)
                combo = (frozenset(self._pressed_mods), vk)
                with self._lock:
                    command = self._entries.get(combo)
                if command is not None and is_explorer_foreground():
                    self._triggered_vks.add(vk)
                    try:
                        self._callback(dict(command))
                    except Exception:
                        logging.exception("Hotkey callback failed")
                    return 1
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            if w_param in (WM_KEYUP, WM_SYSKEYUP):
                if vk in self._triggered_vks:
                    self._triggered_vks.discard(vk)
                    return 1
                return user32.CallNextHookEx(None, n_code, w_param, l_param)
        except Exception:
            logging.exception("Low-level keyboard hook error")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def apply_dark_titlebar(window) -> None:
    if dwmapi is None:
        return
    try:
        window.update_idletasks()
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), 20, ctypes.byref(value), ctypes.sizeof(value)
        )
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), 19, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


def apply_icon(window) -> None:
    try:
        icon = resource_path("icon.ico")
        if icon.exists():
            window.iconbitmap(str(icon))
    except Exception:
        pass


def acquire_single_instance():
    handle = kernel32.CreateMutexW(None, False, "FileSorter_SingleInstance_Mutex")
    if not handle:
        return None
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def focus_existing_window() -> None:
    hwnd = user32.FindWindowW(None, APP_NAME)
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
