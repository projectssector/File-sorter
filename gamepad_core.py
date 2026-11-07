"""XInput gamepad detection, polling and mapping storage."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
import xml.etree.ElementTree as ET
from ctypes import wintypes
from pathlib import Path

from sorter_core import GAMEPAD_FILE

BUTTON_ORDER = [
    "A",
    "B",
    "X",
    "Y",
    "LB",
    "RB",
    "LT",
    "RT",
    "Back",
    "Start",
    "LS",
    "RS",
    "DPadUp",
    "DPadRight",
    "DPadDown",
    "DPadLeft",
]

BUTTON_LABELS = {
    "A": "A",
    "B": "B",
    "X": "X",
    "Y": "Y",
    "LB": "Left bumper",
    "RB": "Right bumper",
    "LT": "Left trigger",
    "RT": "Right trigger",
    "Back": "Back / View",
    "Start": "Start / Menu",
    "LS": "Left stick click",
    "RS": "Right stick click",
    "DPadUp": "D-pad up",
    "DPadRight": "D-pad right",
    "DPadDown": "D-pad down",
    "DPadLeft": "D-pad left",
}

BUTTON_MASKS = {
    "DPadUp": 0x0001,
    "DPadDown": 0x0002,
    "DPadLeft": 0x0004,
    "DPadRight": 0x0008,
    "Start": 0x0010,
    "Back": 0x0020,
    "LS": 0x0040,
    "RS": 0x0080,
    "LB": 0x0100,
    "RB": 0x0200,
    "A": 0x1000,
    "B": 0x2000,
    "X": 0x4000,
    "Y": 0x8000,
}

TRIGGER_THRESHOLD = 60
HOLD_DELAY = 0.35
HOLD_REPEAT = 0.07
DEFAULT_MAPPING = {"Y": "1", "LB": "2", "X": "3"}

AMGP_BUTTON_NAMES = {
    0: "A",
    1: "B",
    2: "X",
    3: "Y",
    4: "LB",
    5: "RB",
    6: "Back",
    7: "Start",
    9: "LS",
    10: "RS",
    11: "DPadUp",
    12: "DPadDown",
    13: "DPadLeft",
    14: "DPadRight",
}


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


def _load_xinput():
    for name in ("XInput1_4.dll", "XInput1_3.dll", "xinput9_1_0.dll"):
        try:
            library = ctypes.WinDLL(name)
            library.XInputGetState.argtypes = [
                wintypes.DWORD,
                ctypes.POINTER(XINPUT_STATE),
            ]
            library.XInputGetState.restype = wintypes.DWORD
            return library
        except Exception:
            continue
    return None


xinput = _load_xinput()


def _read_state(slot: int):
    if xinput is None:
        return None
    try:
        state = XINPUT_STATE()
        result = xinput.XInputGetState(slot, ctypes.byref(state))
        if result == 0:
            return state
    except Exception:
        return None
    return None


def _buttons_from_state(state) -> set[str]:
    buttons = set()
    for name, mask in BUTTON_MASKS.items():
        if state.Gamepad.wButtons & mask:
            buttons.add(name)
    if state.Gamepad.bLeftTrigger >= TRIGGER_THRESHOLD:
        buttons.add("LT")
    if state.Gamepad.bRightTrigger >= TRIGGER_THRESHOLD:
        buttons.add("RT")
    return buttons


class GamepadManager:
    """Poll XInput slots in the background and report button presses."""

    def __init__(self, on_button=None, on_connection_change=None, on_button_hold=None):
        self._on_button = on_button
        self._on_connection_change = on_connection_change
        self._on_button_hold = on_button_hold
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._connected: list[dict] = []
        self._last_buttons: dict[int, set[str]] = {}
        self._held_since: dict[tuple[int, str], float] = {}
        self._next_repeat: dict[tuple[int, str], float] = {}
        self._error = None

    @property
    def available(self) -> bool:
        return xinput is not None

    @property
    def error(self):
        return self._error

    def detect_now(self) -> list[dict]:
        connected = []
        for slot in range(4):
            if _read_state(slot) is not None:
                connected.append(self._controller_info(slot))
        return connected

    @property
    def connected(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._connected]

    @staticmethod
    def _controller_info(slot: int) -> dict:
        return {"slot": slot, "name": "Xbox Controller " + str(slot + 1)}

    def start(self):
        if xinput is None:
            self._error = (
                "XInput is not available on this PC. Connect an Xbox-compatible "
                "controller and make sure the XInput driver is installed."
            )
            return False, self._error
        if self._thread is not None and self._thread.is_alive():
            return True, None
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="file-sorter-gamepad", daemon=True
        )
        self._thread.start()
        return True, None

    def stop(self):
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self):
        try:
            while not self._stop.is_set():
                self._poll_once()
                time.sleep(0.016)
        except Exception:
            logging.exception("Gamepad polling thread failed")
        finally:
            self._thread = None

    def _poll_once(self):
        states = {}
        connected = []
        for slot in range(4):
            state = _read_state(slot)
            if state is not None:
                states[slot] = state
                connected.append(self._controller_info(slot))

        if connected != self._connected:
            with self._lock:
                self._connected = connected
            if self._on_connection_change is not None:
                try:
                    self._on_connection_change([dict(item) for item in connected])
                except Exception:
                    logging.exception("Gamepad connection callback failed")

        now = time.monotonic()
        for slot, state in states.items():
            buttons = _buttons_from_state(state)
            previous = self._last_buttons.get(slot, set())
            presses = buttons - previous
            self._last_buttons[slot] = buttons

            for button in BUTTON_ORDER:
                if button in presses:
                    key = (slot, button)
                    self._held_since[key] = now
                    self._next_repeat[key] = now + HOLD_DELAY

            if presses and self._on_button is not None:
                for button in BUTTON_ORDER:
                    if button in presses:
                        try:
                            self._on_button(button, slot)
                        except Exception:
                            logging.exception("Gamepad button callback failed")

            if self._on_button_hold is None:
                continue
            for button in BUTTON_ORDER:
                key = (slot, button)
                if button not in buttons:
                    self._held_since.pop(key, None)
                    self._next_repeat.pop(key, None)
                    continue
                if button in presses:
                    continue
                held_since = self._held_since.get(key)
                if held_since is None:
                    self._held_since[key] = now
                    self._next_repeat[key] = now + HOLD_DELAY
                    continue
                due = self._next_repeat.get(key)
                if due is None:
                    due = held_since + HOLD_DELAY
                if now >= due:
                    self._next_repeat[key] = now + HOLD_REPEAT
                    try:
                        self._on_button_hold(button, slot)
                    except Exception:
                        logging.exception("Gamepad hold callback failed")

        for slot in list(self._last_buttons):
            if slot not in states:
                self._last_buttons.pop(slot, None)
                for key in [k for k in self._held_since if k[0] == slot]:
                    self._held_since.pop(key, None)
                    self._next_repeat.pop(key, None)


def load_gamepad_mapping(path: Path = GAMEPAD_FILE) -> dict[str, str]:
    mapping = {}
    try:
        if not path.exists():
            return mapping
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            button, hotkey = line.split("=", 1)
            button = button.strip()
            hotkey = hotkey.strip()
            if button in BUTTON_ORDER and hotkey:
                mapping[button] = hotkey
    except Exception:
        logging.exception("Failed to read gamepad mapping %s", path)
    return mapping


def save_gamepad_mapping(mapping: dict[str, str], path: Path = GAMEPAD_FILE) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with open(temp, "w", encoding="utf-8", newline="\n") as handle:
            for button in BUTTON_ORDER:
                hotkey = str(mapping.get(button, "")).replace("\n", "").strip()
                if hotkey:
                    handle.write(button + "=" + hotkey + "\n")
        os.replace(temp, path)
    except Exception:
        logging.exception("Failed to write gamepad mapping %s", path)


def _code_to_hotkey(code_text: str):
    text = (code_text or "").strip().lower()
    if not text:
        return None
    try:
        value = int(text, 0)
    except Exception:
        return None
    if value > 0xFFFF:
        return None
    if 0x30 <= value <= 0x39:
        return chr(value)
    if 0x41 <= value <= 0x5A:
        return chr(value).lower()
    if 0x61 <= value <= 0x7A:
        return chr(value)
    names = {
        0x08: "Backspace",
        0x09: "Tab",
        0x0D: "Enter",
        0x1B: "Esc",
        0x20: "Space",
        0x25: "Left",
        0x26: "Up",
        0x27: "Right",
        0x28: "Down",
        0x2D: "Insert",
        0x2E: "Delete",
        0x24: "Home",
        0x23: "End",
        0x21: "PageUp",
        0x22: "PageDown",
    }
    if value in names:
        return names[value]
    if 0x70 <= value <= 0x87:
        return "F" + str(value - 0x6F)
    return None


def parse_amgp_mapping(path) -> tuple[dict[str, str], str]:
    """Read button mappings from a Steam controller config (.amgp)."""
    mapping = {}
    try:
        tree = ET.parse(str(path))
    except Exception as exc:
        return mapping, str(exc)
    root = tree.getroot()
    for set_element in root.findall("./sets/set"):
        for button in set_element.findall("./button"):
            try:
                index = int(button.get("index", "-1"))
            except Exception:
                continue
            name = AMGP_BUTTON_NAMES.get(index)
            if name is None or name not in BUTTON_ORDER:
                continue
            slot = button.find("./slots/slot")
            if slot is None:
                continue
            mode = slot.findtext("mode", default="keyboard").strip().lower()
            if mode not in ("keyboard", ""):
                continue
            hotkey = _code_to_hotkey(slot.findtext("code", default=""))
            if hotkey:
                mapping[name] = hotkey
        if mapping:
            break
    return mapping, ""


def find_amgp_files() -> list[Path]:
    candidates = []
    seen = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except Exception:
            return
        key = str(resolved).lower()
        if key in seen or not resolved.is_file():
            return
        seen.add(key)
        candidates.append(resolved)

    bases = [Path.cwd(), Path(getattr(sys, "_MEIPASS", Path.cwd()))]
    try:
        bases.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    try:
        bases.append(Path(__file__).resolve().parent)
    except Exception:
        pass

    for base in bases:
        try:
            folders = [base] + list(base.parents)[:3]
        except Exception:
            folders = [base]
        for folder in folders:
            try:
                for path in folder.glob("*.amgp"):
                    add(path)
            except Exception:
                pass

    desktop = Path.home() / "Desktop"
    for path in (
        desktop / "file mover" / "keypad.gamecontroller.amgp",
        desktop / "file mover" / "keypad.amgp",
    ):
        add(path)
    return candidates


def load_or_seed_mapping() -> dict[str, str]:
    if GAMEPAD_FILE.exists():
        return load_gamepad_mapping(GAMEPAD_FILE)

    for path in find_amgp_files():
        mapping, _error = parse_amgp_mapping(path)
        if mapping:
            save_gamepad_mapping(mapping, GAMEPAD_FILE)
            logging.info("Imported gamepad mapping from %s", path)
            return mapping

    mapping = dict(DEFAULT_MAPPING)
    save_gamepad_mapping(mapping, GAMEPAD_FILE)
    return mapping
