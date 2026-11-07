"""File Sorter - Python GUI replacement for the AutoHotkey file mover."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from gamepad_core import (
    GamepadManager,
    load_or_seed_mapping,
    save_gamepad_mapping as persist_gamepad_mapping,
)
from gamepad_ui import GamepadWindow
from image_sorter_ui import ImageSorterWindow
from sorter_core import (
    ACCENT,
    ACTIVE_FILE,
    APP_NAME,
    APP_VERSION,
    BG,
    BORDER,
    CARD,
    DANGER,
    FONT,
    HISTORY_FILE,
    MUTED,
    SUCCESS,
    TEXT,
    WARN,
    GlobalHotkeyEngine,
    acquire_single_instance,
    apply_dark_titlebar,
    apply_icon,
    collect_media_files,
    command_signature,
    copy_selection_and_read,
    enable_dpi_awareness,
    focus_existing_window,
    is_explorer_foreground,
    load_commands,
    migrate_legacy_config,
    move_items,
    save_commands,
    setup_logging,
    short_path,
    wait_for_modifiers_released,
)
from sorter_ui import CommandDialog, MemoryWindow, setup_styles


class FileSorterApp:
    def __init__(self, smoke_test: bool = False):
        self.smoke_test = smoke_test
        self.root = TkinterDnD.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("900x600")
        self.root.minsize(760, 480)
        self.root.configure(bg=BG)
        apply_icon(self.root)
        setup_styles(self.root)
        self.root.report_callback_exception = self._report_callback_exception

        self.active = []
        self.history = []
        self.paused = False
        self._move_busy = False
        self._closing = False
        self._toast = None
        self._memory_window = None
        self._image_sorter = None
        self._gamepad_window = None
        self._ui_queue = queue.Queue()
        self._hotkey_errors = []
        self._hotkeys_ok = False
        self._gamepads_ok = False
        self._gamepad_connected = []
        self.gamepad_mapping = {}
        self.gamepads = None

        self._load_config()
        self._build_ui()
        self._refresh_list()

        self.hotkeys = GlobalHotkeyEngine(self._on_hotkey)
        ok, error = self.hotkeys.start()
        self._hotkeys_ok = ok
        if ok:
            self._sync_hotkeys()
        else:
            logging.error("Hotkeys unavailable: %s", error)
            self._set_status("Global hotkeys could not start. Check errors.log.")
            self.hotkey_label.configure(text="Global hotkeys: unavailable")
            if not smoke_test:
                self.root.after(
                    350,
                    lambda: messagebox.showerror(
                        APP_NAME,
                        "Global hotkeys could not start, so commands will not fire.\n\n"
                        + str(error),
                    ),
                )

        self.gamepad_mapping = load_or_seed_mapping()
        self.gamepads = GamepadManager(
            self._on_gamepad_button,
            self._on_gamepad_connection,
            on_button_hold=self._on_gamepad_hold,
        )
        gamepad_ok, gamepad_error = self.gamepads.start()
        self._gamepads_ok = gamepad_ok
        if not gamepad_ok:
            logging.error("Gamepad unavailable: %s", gamepad_error)
        self._update_gamepad_label()

        apply_dark_titlebar(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(30, self._poll_ui_queue)
        self._set_ready_status()

        if smoke_test:
            self.root.after(1200, self._smoke_finish)

        logging.info("File Sorter %s started.", APP_VERSION)

    # -- config ---------------------------------------------------------

    def _load_config(self) -> None:
        migrate_legacy_config()
        self.active = load_commands(ACTIVE_FILE)
        self.history = load_commands(HISTORY_FILE)
        if self.active and not self.history:
            self.history = [dict(command) for command in self.active]
            self._save_history()

    def _save_active(self) -> None:
        save_commands(ACTIVE_FILE, self.active)

    def _save_history(self) -> None:
        save_commands(HISTORY_FILE, self.history)

    def _save_all(self) -> None:
        self._save_active()
        self._save_history()

    # -- UI -------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self.root, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 14))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text=APP_NAME,
            bg=BG,
            fg=TEXT,
            font=(FONT, 24, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text=(
                "Select files in Explorer and press a hotkey, or use Sort Media "
                "to view and file pictures and videos without Explorer."
            ),
            bg=BG,
            fg=MUTED,
            font=(FONT, 10),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        self.state_pill = tk.Label(
            header,
            text=" ACTIVE ",
            bg="#12321f",
            fg="#4ade80",
            font=(FONT, 9, "bold"),
            padx=6,
            pady=4,
        )
        self.state_pill.grid(row=0, column=1, rowspan=2, sticky="e")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 14))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.commands_tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.commands_tab, text="Commands")

        card = tk.Frame(
            self.commands_tab, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        card.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 0))
        self.commands_tab.grid_rowconfigure(0, weight=1)
        self.commands_tab.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            card,
            columns=("status", "hotkey", "folder"),
            show="headings",
            selectmode="browse",
            style="FileSorter.Treeview",
        )
        self.tree.heading("status", text="READY", anchor="center")
        self.tree.heading("hotkey", text="HOTKEY", anchor="w")
        self.tree.heading("folder", text="DESTINATION FOLDER", anchor="w")
        self.tree.column("status", width=70, minwidth=60, stretch=False, anchor="center")
        self.tree.column("hotkey", width=130, minwidth=90, stretch=False, anchor="w")
        self.tree.column("folder", width=600, minwidth=300, stretch=True, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        self.tree.tag_configure("missing", foreground=DANGER)
        self.tree.tag_configure("odd", background=CARD)
        self.tree.tag_configure("even", background="#1a222c")
        self.tree.bind("<Double-1>", lambda _event: self.edit_selected())
        self.tree.bind("<Delete>", lambda _event: self.delete_selected())
        self.tree.bind("<Button-3>", self._show_context_menu)

        scroll = ttk.Scrollbar(
            card,
            orient="vertical",
            command=self.tree.yview,
            style="FileSorter.Vertical.TScrollbar",
        )
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=12)
        self.tree.configure(yscrollcommand=scroll.set)

        self.empty_label = tk.Label(
            card,
            text='No commands yet.\nClick "Add Command" to create one.',
            bg=CARD,
            fg=MUTED,
            font=(FONT, 11),
            justify="center",
        )
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

        self.context_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=CARD,
            fg=TEXT,
            activebackground=ACCENT,
            activeforeground="#ffffff",
            borderwidth=0,
        )
        self.context_menu.add_command(label="Edit", command=self.edit_selected)
        self.context_menu.add_command(label="Delete", command=self.delete_selected)

        toolbar = tk.Frame(self.root, bg=BG)
        toolbar.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 14))

        left = tk.Frame(toolbar, bg=BG)
        left.pack(side="left")
        right = tk.Frame(toolbar, bg=BG)
        right.pack(side="right")

        ttk.Button(
            left,
            text="Sort Media",
            style="Accent.TButton",
            command=self.open_image_sorter,
            takefocus=False,
        ).pack(side="left")
        ttk.Button(
            left,
            text="Add Command",
            style="Secondary.TButton",
            command=self.open_add_dialog,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            left,
            text="Edit Selected",
            style="Secondary.TButton",
            command=self.edit_selected,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            left,
            text="Delete",
            style="Danger.TButton",
            command=self.delete_selected,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            right,
            text="Memory",
            style="Secondary.TButton",
            command=self.open_memory,
            takefocus=False,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            right,
            text="Gamepad",
            style="Secondary.TButton",
            command=self.open_gamepad,
            takefocus=False,
        ).pack(side="right", padx=(8, 0))
        self.pause_btn = ttk.Button(
            right,
            text="Pause",
            style="Secondary.TButton",
            command=self.toggle_pause,
            takefocus=False,
        )
        self.pause_btn.pack(side="right", padx=(8, 0))
        ttk.Button(
            right,
            text="Exit",
            style="Ghost.TButton",
            command=self.on_close,
            takefocus=False,
        ).pack(side="right", padx=(8, 0))

        footer = tk.Frame(self.root, bg=BG)
        footer.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 14))
        self.status_label = tk.Label(
            footer,
            text="Ready",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        self.status_label.pack(side="left")
        self.hotkey_label = tk.Label(
            footer,
            text="",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="e",
        )
        self.hotkey_label.pack(side="right")
        self.gamepad_label = tk.Label(
            footer,
            text="Gamepad: checking...",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="e",
        )
        self.gamepad_label.pack(side="right", padx=(0, 18))

        self._register_main_dnd()

    def _register_main_dnd(self) -> None:
        def register(widget) -> None:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_main_drop)
            except Exception:
                pass
            try:
                children = widget.winfo_children()
            except Exception:
                return
            for child in children:
                register(child)

        try:
            register(self.root)
        except Exception:
            logging.exception("Could not enable drag and drop on the main window")

    def _on_main_drop(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        media = collect_media_files(paths)
        if not media:
            self.show_toast(
                "No images or videos found",
                "Drop image or video files, or a folder that contains them.",
                "warn",
            )
        else:
            self.open_image_sorter(media)
        return getattr(event, "action", "copy")

    def _refresh_list(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, command in enumerate(self.active):
            folder = command.get("folder", "")
            status = "\u2713" if os.path.isdir(folder) else "\u2717"
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(status, command["hotkey"], folder),
                tags=(
                    ("even" if index % 2 else "odd",)
                    + (("missing",) if not os.path.isdir(folder) else ())
                ),
            )
        if self.active:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")
        self._update_hotkey_label()

    def _set_status(self, text: str) -> None:
        try:
            self.status_label.configure(text=text)
        except Exception:
            pass

    def _set_ready_status(self) -> None:
        if self.paused:
            self._set_status("Hotkeys paused.")
        else:
            self._set_status("Ready")

    def _update_hotkey_label(self) -> None:
        if not self._hotkeys_ok:
            text = "Global hotkeys: unavailable"
        elif self.paused:
            text = "Global hotkeys: paused"
        elif self._hotkey_errors:
            text = str(len(self.active)) + " hotkey(s) active (" + str(len(self._hotkey_errors)) + " issue)"
        else:
            text = str(len(self.active)) + " hotkey(s) active"
        try:
            self.hotkey_label.configure(text=text)
        except Exception:
            pass

    def _update_gamepad_label(self) -> None:
        if self.gamepads is None:
            text = "Gamepad: checking..."
        elif not self._gamepads_ok:
            text = "Gamepad: unavailable"
        elif self._gamepad_connected:
            names = ", ".join(
                item.get("name", "Controller") for item in self._gamepad_connected
            )
            text = "Gamepad: " + names
        else:
            text = "Gamepad: not connected"
        try:
            self.gamepad_label.configure(text=text)
        except Exception:
            pass

    def _poll_ui_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                function, args, kwargs = self._ui_queue.get_nowait()
                try:
                    function(*args, **kwargs)
                except Exception:
                    logging.exception("UI task failed")
        except queue.Empty:
            pass
        self.root.after(30, self._poll_ui_queue)

    def _ui(self, function, *args, **kwargs) -> None:
        if self._closing:
            return
        self._ui_queue.put((function, args, kwargs))

    def _report_callback_exception(self, exc_type, exc_value, exc_traceback) -> None:
        logging.error("Tk callback error", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            messagebox.showerror(APP_NAME, str(exc_value))
        except Exception:
            pass

    # -- actions --------------------------------------------------------

    def _selected_index(self):
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except Exception:
            return None

    def _show_context_menu(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def open_add_dialog(self) -> None:
        self._open_command_dialog(None, None)

    def edit_selected(self) -> None:
        index = self._selected_index()
        if index is None or index >= len(self.active):
            messagebox.showinfo(APP_NAME, "Select a command to edit.")
            return
        self._open_command_dialog(dict(self.active[index]), index)

    def _open_command_dialog(self, command, index) -> None:
        self.hotkeys.set_suspended(True)
        dialog = None
        try:
            dialog = CommandDialog(self, command, index)
            self.root.wait_window(dialog)
        finally:
            if not self._closing:
                self.hotkeys.set_suspended(False)
        if dialog is not None and dialog.result:
            if index is None:
                self.add_command(dialog.result)
            else:
                self.update_command(index, dialog.result)

    def add_command(self, command: dict) -> None:
        command = dict(command)
        self.active.append(command)
        signature = command_signature(command)
        if not any(command_signature(item) == signature for item in self.history):
            self.history.append(dict(command))
        self._save_all()
        self._refresh_list()
        self._sync_hotkeys()
        self._refresh_gamepad_window()
        self._set_status("Added hotkey " + command["hotkey"] + ".")
        logging.info("Added command %s -> %s", command["hotkey"], command["folder"])

    def update_command(self, index: int, command: dict) -> None:
        if index < 0 or index >= len(self.active):
            return
        old = self.active[index]
        self.active[index] = dict(command)
        old_hotkey = str(old.get("hotkey", "")).strip().lower()
        new_hotkey = str(command.get("hotkey", "")).strip()
        if old_hotkey != new_hotkey.strip().lower():
            moved_mapping = False
            for button, mapped_hotkey in list(self.gamepad_mapping.items()):
                if str(mapped_hotkey).strip().lower() == old_hotkey:
                    self.gamepad_mapping[button] = new_hotkey
                    moved_mapping = True
            if moved_mapping:
                self.save_gamepad_mapping()
        old_signature = command_signature(old)
        replaced = False
        for history_index, history_command in enumerate(self.history):
            if command_signature(history_command) == old_signature:
                self.history[history_index] = dict(command)
                replaced = True
                break
        if not replaced:
            new_signature = command_signature(command)
            if not any(command_signature(item) == new_signature for item in self.history):
                self.history.append(dict(command))
        self._save_all()
        self._refresh_list()
        self._sync_hotkeys()
        self._refresh_gamepad_window()
        self._set_status("Updated hotkey " + command["hotkey"] + ".")
        logging.info("Updated command %s -> %s", command["hotkey"], command["folder"])

    def delete_selected(self) -> None:
        index = self._selected_index()
        if index is None or index >= len(self.active):
            messagebox.showinfo(APP_NAME, "Select a command to delete.")
            return
        command = self.active.pop(index)
        self._save_active()
        self._refresh_list()
        self._sync_hotkeys()
        self._refresh_gamepad_window()
        self._set_status(
            "Removed " + command["hotkey"] + " (it is still available in Memory)."
        )
        logging.info("Removed active command %s", command["hotkey"])

    def open_image_sorter(self, files=None) -> None:
        if self._image_sorter is not None:
            try:
                if self._image_sorter.winfo_exists():
                    self.notebook.select(self._image_sorter)
                    self._image_sorter._reload_destinations()
                    if files:
                        self._image_sorter.add_files(files)
                    return
            except Exception:
                pass
            self._image_sorter = None
        self._image_sorter = ImageSorterWindow(self.notebook, self, files)
        self.notebook.add(self._image_sorter, text="Sort Media")
        self.notebook.select(self._image_sorter)

    def open_memory(self) -> None:
        if self._memory_window is not None:
            try:
                if self._memory_window.winfo_exists():
                    self.notebook.select(self._memory_window)
                    self._memory_window._refresh()
                    return
            except Exception:
                pass
            self._memory_window = None
        self._memory_window = MemoryWindow(self.notebook, self)
        self.notebook.add(self._memory_window, text="Memory")
        self.notebook.select(self._memory_window)

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.hotkeys.set_enabled(not self.paused)
        if self.paused:
            self.pause_btn.configure(text="Resume")
            self.state_pill.configure(text=" PAUSED ", bg="#3a2a12", fg="#fbbf24")
            self._set_status("Hotkeys paused.")
        else:
            self.pause_btn.configure(text="Pause")
            self.state_pill.configure(text=" ACTIVE ", bg="#12321f", fg="#4ade80")
            self._set_status("Hotkeys active.")
        self._update_hotkey_label()

    def _sync_hotkeys(self) -> None:
        if not self._hotkeys_ok:
            return
        self._hotkey_errors = self.hotkeys.set_hotkeys(self.active)
        self.hotkeys.set_enabled(not self.paused)
        self._update_hotkey_label()
        if self._hotkey_errors:
            logging.warning("Hotkey issues: %s", self._hotkey_errors)

    # -- gamepad handling -----------------------------------------------

    def open_gamepad(self) -> None:
        if self._gamepad_window is not None:
            try:
                if self._gamepad_window.winfo_exists():
                    self.notebook.select(self._gamepad_window)
                    self._gamepad_window._build_rows()
                    self._gamepad_window.refresh_status()
                    return
            except Exception:
                pass
            self._gamepad_window = None
        self._gamepad_window = GamepadWindow(self.notebook, self)
        self.notebook.add(self._gamepad_window, text="Gamepad")
        self.notebook.select(self._gamepad_window)

    def save_gamepad_mapping(self) -> None:
        persist_gamepad_mapping(self.gamepad_mapping)

    def _refresh_gamepad_window(self) -> None:
        if self._gamepad_window is not None:
            try:
                if self._gamepad_window.winfo_exists():
                    self._gamepad_window._build_rows()
            except Exception:
                pass

    def _on_gamepad_connection(self, connected) -> None:
        self._ui(self._apply_gamepad_connection, list(connected or []))

    def _apply_gamepad_connection(self, connected) -> None:
        previous = list(self._gamepad_connected)
        self._gamepad_connected = list(connected)
        self._update_gamepad_label()
        if self._gamepad_window is not None:
            try:
                if self._gamepad_window.winfo_exists():
                    self._gamepad_window.refresh_status()
            except Exception:
                pass
        if connected and not previous:
            names = ", ".join(
                item.get("name", "Controller") for item in connected
            )
            self.show_toast("Gamepad connected", names + " is ready.", "success")
            self._set_status("Gamepad connected. Press its buttons to sort files.")
        elif previous and not connected and not self._closing:
            self.show_toast(
                "Gamepad disconnected",
                "Reconnect the controller to keep using gamepad buttons.",
                "warn",
            )
            self._set_status("Gamepad disconnected.")

    def _on_gamepad_button(self, button: str, slot: int) -> None:
        self._ui(self._handle_gamepad_button, button, slot)

    def _on_gamepad_hold(self, button: str, slot: int) -> None:
        if button in ("DPadLeft", "DPadRight", "Left", "Right"):
            self._ui(self._handle_gamepad_button, button, slot, True)

    def _handle_gamepad_button(self, button: str, slot: int, repeated=False) -> None:
        if self._closing:
            return
        if repeated and button not in ("DPadLeft", "DPadRight", "Left", "Right"):
            return
        if self._gamepad_window is not None:
            try:
                if self._gamepad_window.winfo_exists():
                    if self._gamepad_window.is_listening():
                        if repeated:
                            return
                        self._gamepad_window.note_button(button)
                        self._gamepad_window.capture_button(button)
                        return
                    if not repeated:
                        self._gamepad_window.note_button(button)
            except Exception:
                pass
        if self.paused:
            return
        hotkey = self.gamepad_mapping.get(button)
        command = self._find_command_by_hotkey(hotkey) if hotkey else None

        if self._image_sorter is not None:
            try:
                if self._image_sorter.winfo_exists():
                    if command is not None:
                        if repeated:
                            return
                        self._image_sorter._move_current(command)
                        return
                    if hotkey == "__delete__":
                        if repeated:
                            return
                        self._image_sorter.next_image()
                        self.show_toast("Skipped image", "Moved to the next image.", "info")
                        return
                    if hotkey == "__undo__":
                        if repeated:
                            return
                        self._image_sorter._undo_last_move()
                        self.show_toast("Undo", "Last move undone.", "info")
                        return
                    sorter = self._image_sorter
                    if button in ("DPadLeft", "Left"):
                        sorter.previous_image()
                        return
                    if button in ("DPadRight", "Right"):
                        sorter.next_image()
                        return
                    if repeated:
                        return
                    if button in ("DPadUp", "Up"):
                        sorter._select_index(0)
                        return
                    if button in ("DPadDown", "Down"):
                        sorter._select_index(len(sorter._images) - 1)
                        return
                    if button in ("A", "Start"):
                        sorter.next_image()
                        return
                    if button == "B":
                        sorter._undo_last_move()
                        return
                    if button in ("X", "Back"):
                        sorter._open_original()
                        return
                    if button == "Y":
                        sorter._undo_last_move()
                        return
                    return
            except Exception:
                self._image_sorter = None

        if repeated:
            return
        if hotkey in ("__delete__", "__undo__"):
            self.show_toast(
                "Sort Media not open",
                "Open the Sort Media tab first.",
                "warn",
            )
            return
        if command is None:
            return
        self._on_hotkey(command)

    def _find_command_by_hotkey(self, hotkey: str):
        target = str(hotkey or "").strip().lower()
        if not target:
            return None
        for command in self.active:
            if str(command.get("hotkey", "")).strip().lower() == target:
                return dict(command)
        return None

    def _on_tab_changed(self, _event=None) -> None:
        try:
            current = self.notebook.select()
            widget = self.notebook.nametowidget(current)
        except Exception:
            return
        if widget is self._image_sorter and self._image_sorter is not None:
            try:
                self._image_sorter.focus_preview()
                self.root.bind("<Delete>", lambda _e: self._image_sorter.next_image())
                self.root.bind("<BackSpace>", lambda _e: self._image_sorter.next_image())
            except Exception:
                pass
        else:
            try:
                self.root.unbind("<Delete>")
                self.root.unbind("<BackSpace>")
            except Exception:
                pass

    # -- hotkey handling ------------------------------------------------

    def _on_hotkey(self, command: dict) -> None:
        if self._closing or self.paused:
            return
        if self._move_busy:
            return
        self._move_busy = True
        worker = threading.Thread(
            target=self._move_worker, args=(dict(command),), daemon=True
        )
        worker.start()

    def _move_worker(self, command: dict) -> None:
        try:
            destination = command.get("folder", "")
            if not os.path.isdir(destination):
                self._ui(
                    self.show_toast,
                    "Destination not found",
                    destination,
                    "error",
                )
                return
            self._ui(
                self._set_status,
                "Moving selected items to " + short_path(destination) + "...",
            )
            if not wait_for_modifiers_released(1.0):
                self._ui(
                    self.show_toast,
                    "Nothing moved",
                    "Release the hotkey keys and try again.",
                    "warn",
                )
                return
            if not is_explorer_foreground():
                self._ui(
                    self.show_toast,
                    "Nothing moved",
                    "File Explorer is not the active window. "
                    "Use Sort Media to file pictures and videos.",
                    "warn",
                )
                return
            files = copy_selection_and_read()
            if not files:
                self._ui(
                    self.show_toast,
                    "No files selected",
                    "Select files in File Explorer, then press the hotkey.",
                    "warn",
                )
                return
            moved, failed, skipped, errors = move_items(files, destination)
            self._ui(
                self._show_move_result,
                command,
                moved,
                failed,
                skipped,
                errors,
            )
        except Exception as exc:
            logging.exception("Move failed")
            self._ui(self.show_toast, "Move failed", str(exc), "error")
        finally:
            self._move_busy = False
            self._ui(self._set_ready_status)

    def _show_move_result(self, command, moved, failed, skipped, errors) -> None:
        destination = short_path(command.get("folder", ""))
        if moved and not failed:
            title = "Move complete"
            message = str(moved) + " item(s) moved to " + destination + "."
            kind = "success"
        elif moved and failed:
            title = "Move finished with errors"
            message = str(moved) + " moved, " + str(failed) + " failed."
            if errors:
                message += "\n" + errors[0]
            kind = "warn"
        elif failed:
            title = "Move failed"
            message = str(failed) + " item(s) could not be moved."
            if errors:
                message += "\n" + errors[0]
            kind = "error"
        else:
            title = "Nothing moved"
            message = "No items were moved."
            kind = "warn"
        if skipped:
            message += " " + str(skipped) + " skipped."
        self.show_toast(title, message, kind)
        self._set_status(title + ": " + message.split("\n")[0])

    # -- toast ----------------------------------------------------------

    def show_toast(self, title: str, message: str, kind: str = "info") -> None:
        if self._closing:
            return
        if self._toast is not None:
            try:
                self._toast.destroy()
            except Exception:
                pass
            self._toast = None
        colors = {
            "success": SUCCESS,
            "warn": WARN,
            "error": DANGER,
            "info": ACCENT,
        }
        accent = colors.get(kind, ACCENT)
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        wrapper = tk.Frame(
            top, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        wrapper.pack(fill="both", expand=True)
        tk.Frame(wrapper, bg=accent, width=5).pack(side="left", fill="y")
        body = tk.Frame(wrapper, bg=CARD)
        body.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        tk.Label(
            body,
            text=title,
            bg=CARD,
            fg=TEXT,
            font=(FONT, 10, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text=message,
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
            justify="left",
            wraplength=340,
        ).pack(fill="x", pady=(3, 0))
        top.update_idletasks()
        width = max(320, top.winfo_reqwidth())
        height = top.winfo_reqheight()
        screen_w = top.winfo_screenwidth()
        screen_h = top.winfo_screenheight()
        top.geometry(
            "+"
            + str(max(0, screen_w - width - 24))
            + "+"
            + str(max(0, screen_h - height - 64))
        )
        top.bind("<Button-1>", lambda _event: top.destroy())
        self._toast = top

        def close_toast():
            try:
                if top.winfo_exists():
                    top.destroy()
            except Exception:
                pass

        top.after(4000, close_toast)

    # -- shutdown / smoke test ------------------------------------------

    def on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self._save_all()
        except Exception:
            logging.exception("Failed to save config while closing")
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            if self.gamepads is not None:
                self.gamepads.stop()
        except Exception:
            pass
        if self._gamepad_window is not None:
            try:
                self._gamepad_window._close()
            except Exception:
                pass
        if self._toast is not None:
            try:
                self._toast.destroy()
            except Exception:
                pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def _smoke_finish(self) -> None:
        logging.info("Smoke test finished. Hotkeys ok: %s", self._hotkeys_ok)
        try:
            if getattr(sys, "stdout", None):
                print("SMOKE_OK" if self._hotkeys_ok else "SMOKE_OK_NO_HOTKEYS")
        except Exception:
            pass
        self.on_close()


def main() -> None:
    enable_dpi_awareness()
    setup_logging()
    smoke = "--smoke-test" in sys.argv
    if not smoke:
        if acquire_single_instance() is None:
            focus_existing_window()
            return
    app = FileSorterApp(smoke_test=smoke)
    dropped = [arg for arg in sys.argv[1:] if arg != "--smoke-test"]
    if dropped:
        app.root.after(150, lambda: app.open_image_sorter(dropped))
    app.root.mainloop()


if __name__ == "__main__":
    main()
