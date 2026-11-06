"""Gamepad detection and mapping window."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gamepad_core import (
    BUTTON_LABELS,
    BUTTON_ORDER,
    find_amgp_files,
    parse_amgp_mapping,
)
from sorter_core import (
    ACCENT,
    APP_NAME,
    BG,
    BORDER,
    CARD,
    CARD_2,
    DANGER,
    FONT,
    MUTED,
    SUCCESS,
    TEXT,
    WARN,
    apply_dark_titlebar,
    apply_icon,
    short_path,
)


class GamepadWindow(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.configure(bg=BG)
        self._listening_hotkey = None
        self._listening_name = ""
        self._closed = False

        self._build_ui()
        self._build_rows()
        self.refresh_status()
        self.bind("<Escape>", self._on_escape)

    # -- layout ---------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="Gamepad",
            bg=BG,
            fg=TEXT,
            font=(FONT, 22, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text=(
                "Gamepad buttons are used only inside File Sorter. They never "
                "send keys to other applications."
            ),
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(
            header,
            text="Close",
            style="Ghost.TButton",
            command=self._close,
            takefocus=False,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        status_card = tk.Frame(
            self, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        status_card.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 12))
        status_card.grid_columnconfigure(0, weight=1)

        self.status_label = tk.Label(
            status_card,
            text="Checking for controller...",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 10, "bold"),
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 2))
        self.last_button_label = tk.Label(
            status_card,
            text="Press any gamepad button to test the connection.",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        self.last_button_label.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))

        buttons = tk.Frame(status_card, bg=CARD)
        buttons.grid(row=0, column=1, rowspan=2, sticky="e", padx=12)
        ttk.Button(
            buttons,
            text="Detect Gamepad",
            style="Accent.TButton",
            command=self._detect_now,
            takefocus=False,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Import .amgp",
            style="Secondary.TButton",
            command=self._import_amgp,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))

        card = tk.Frame(
            self, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        card.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 12))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        card_header = tk.Frame(card, bg=CARD)
        card_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        card_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            card_header,
            text="BUTTON ASSIGNMENTS",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            card_header,
            text="Refresh",
            style="Ghost.TButton",
            command=self._refresh,
            takefocus=False,
        ).grid(row=0, column=1, sticky="e")

        self.rows_canvas = tk.Canvas(card, bg=CARD, highlightthickness=0, bd=0)
        self.rows_canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 8))
        scrollbar = ttk.Scrollbar(
            card,
            orient="vertical",
            command=self.rows_canvas.yview,
            style="FileSorter.Vertical.TScrollbar",
        )
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 8))
        self.rows_canvas.configure(yscrollcommand=scrollbar.set)
        self.rows_inner = tk.Frame(self.rows_canvas, bg=CARD)
        self._rows_window = self.rows_canvas.create_window(
            (0, 0), window=self.rows_inner, anchor="nw"
        )
        self.rows_inner.bind(
            "<Configure>",
            lambda _event: self.rows_canvas.configure(
                scrollregion=self.rows_canvas.bbox("all")
            ),
        )
        self.rows_canvas.bind(
            "<Configure>",
            lambda event: self.rows_canvas.itemconfigure(
                self._rows_window, width=event.width
            ),
        )
        self.rows_canvas.bind("<MouseWheel>", self._scroll_rows)
        self.rows_inner.bind("<MouseWheel>", self._scroll_rows)

        footer = tk.Frame(self, bg=BG)
        footer.grid(row=3, column=0, sticky="ew", padx=22, pady=(0, 16))
        self.listen_label = tk.Label(
            footer,
            text="Click Listen, then press the gamepad button you want to assign.",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        self.listen_label.pack(side="left")
        ttk.Button(
            footer,
            text="Clear All Mappings",
            style="Danger.TButton",
            command=self._clear_all,
            takefocus=False,
        ).pack(side="right")

    def _scroll_rows(self, event):
        try:
            self.rows_canvas.yview_scroll(int(-event.delta / 120), "units")
        except Exception:
            pass
        return "break"

    # -- rows -----------------------------------------------------------

    def _build_rows(self) -> None:
        for child in self.rows_inner.winfo_children():
            child.destroy()
        self._listening_hotkey = None
        self._listening_name = ""

        if not self.app.active:
            tk.Label(
                self.rows_inner,
                text=(
                    "No move commands yet.\n\n"
                    "Add commands in the main File Sorter window first, then "
                    "return here to assign gamepad buttons."
                ),
                bg=CARD,
                fg=MUTED,
                font=(FONT, 10),
                justify="left",
                anchor="w",
                wraplength=560,
            ).pack(fill="x", padx=8, pady=(20, 8))

        for command in self.app.active:
            self._make_row(command)

        tk.Label(
            self.rows_inner,
            text="SPECIAL ACTIONS",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8, "bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(12, 4))

        for label, token, description in (
            ("Delete (skip image)", "__delete__", "Skip the current image while sorting pictures."),
            ("Undo last move", "__undo__", "Undo the most recent image move."),
        ):
            self._make_special_row(label, token, description)

    def _make_row(self, command: dict) -> None:
        hotkey = command.get("hotkey", "")
        folder = command.get("folder", "")
        name = Path(folder).name or folder
        current_button = self._button_for_hotkey(hotkey)

        row = tk.Frame(
            self.rows_inner,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        row.pack(fill="x", padx=4, pady=4)

        badge = tk.Label(
            row,
            text=hotkey if hotkey else "?",
            bg=ACCENT,
            fg="#ffffff",
            font=(FONT, 9, "bold"),
            padx=8,
            pady=4,
        )
        badge.pack(side="left", padx=(10, 10), pady=10)

        info = tk.Frame(row, bg=CARD_2)
        info.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(
            info,
            text=name or "(destination)",
            bg=CARD_2,
            fg=TEXT,
            font=(FONT, 10, "bold"),
            anchor="w",
            justify="left",
        ).pack(fill="x")
        tk.Label(
            info,
            text=short_path(folder, 2),
            bg=CARD_2,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(2, 0))

        controls = tk.Frame(row, bg=CARD_2)
        controls.pack(side="right", padx=(8, 10), pady=8)

        combo = ttk.Combobox(
            controls,
            values=["None"] + BUTTON_ORDER,
            state="readonly",
            width=12,
            font=(FONT, 9),
        )
        combo.set(current_button if current_button else "None")
        combo.pack(side="left")
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event, h=hotkey, c=combo: self._on_combo_changed(h, c),
        )
        ttk.Button(
            controls,
            text="Listen",
            style="Secondary.TButton",
            command=lambda h=hotkey, n=name: self._start_listening(h, n),
            takefocus=False,
        ).pack(side="left", padx=(8, 0))

    def _make_special_row(self, label: str, token: str, description: str) -> None:
        current_button = self._button_for_value(token)

        row = tk.Frame(
            self.rows_inner,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        row.pack(fill="x", padx=4, pady=4)

        badge = tk.Label(
            row,
            text=label,
            bg="#334155",
            fg="#ffffff",
            font=(FONT, 9, "bold"),
            padx=8,
            pady=4,
        )
        badge.pack(side="left", padx=(10, 10), pady=10)

        info = tk.Frame(row, bg=CARD_2)
        info.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(
            info,
            text=label,
            bg=CARD_2,
            fg=TEXT,
            font=(FONT, 10, "bold"),
            anchor="w",
            justify="left",
        ).pack(fill="x")
        tk.Label(
            info,
            text=description,
            bg=CARD_2,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(2, 0))

        controls = tk.Frame(row, bg=CARD_2)
        controls.pack(side="right", padx=(8, 10), pady=8)

        combo = ttk.Combobox(
            controls,
            values=["None"] + BUTTON_ORDER,
            state="readonly",
            width=12,
            font=(FONT, 9),
        )
        combo.set(current_button if current_button else "None")
        combo.pack(side="left")
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event, t=token, c=combo: self._on_special_combo_changed(t, c),
        )
        ttk.Button(
            controls,
            text="Listen",
            style="Secondary.TButton",
            command=lambda t=token, lbl=label: self._start_listening(t, lbl),
            takefocus=False,
        ).pack(side="left", padx=(8, 0))

    def _button_for_value(self, value: str):
        preferred = []
        for button in BUTTON_ORDER:
            if self.app.gamepad_mapping.get(button) == value:
                preferred.append(button)
        if not preferred:
            return ""
        return preferred[0]

    def _button_for_hotkey(self, hotkey: str):
        return self._button_for_value(hotkey)

    def _on_special_combo_changed(self, token: str, combo) -> None:
        value = combo.get().strip()
        if value == "None" or not value:
            self._clear_value(token)
        else:
            self._assign_value(token, value)
        self._build_rows()

    def _assign_value(self, value: str, button: str) -> None:
        mapping = self.app.gamepad_mapping
        for existing_button, existing_value in list(mapping.items()):
            if existing_value == value or existing_button == button:
                mapping.pop(existing_button, None)
        mapping[button] = value
        self.app.save_gamepad_mapping()

    def _clear_value(self, value: str) -> None:
        mapping = self.app.gamepad_mapping
        for button, existing_value in list(mapping.items()):
            if existing_value == value:
                mapping.pop(button, None)
        self.app.save_gamepad_mapping()

    def _on_combo_changed(self, hotkey: str, combo) -> None:
        value = combo.get().strip()
        if value == "None" or not value:
            self._clear_hotkey(hotkey)
        else:
            self._assign_button(hotkey, value)
        self._build_rows()

    def _start_listening(self, hotkey: str, name: str) -> None:
        self._listening_hotkey = hotkey
        self._listening_name = name
        self.listen_label.configure(
            text='Listening for a gamepad button for "' + name + '"...'
        )
        self.app.show_toast(
            "Listening",
            "Press the gamepad button you want to use for " + name + ".",
            "info",
        )

    def is_listening(self) -> bool:
        return self._listening_hotkey is not None

    def note_button(self, button: str) -> None:
        label = BUTTON_LABELS.get(button, button)
        try:
            self.last_button_label.configure(
                text="Last button pressed: " + label, fg=TEXT
            )
        except Exception:
            pass

    def capture_button(self, button: str) -> None:
        if self._listening_hotkey is None:
            return
        hotkey = self._listening_hotkey
        name = self._listening_name
        self._listening_hotkey = None
        self._listening_name = ""
        self._assign_button(hotkey, button)
        self.listen_label.configure(
            text='Assigned "' + BUTTON_LABELS.get(button, button) + '" to ' + name + "."
        )
        self.app.show_toast(
            "Gamepad button assigned",
            BUTTON_LABELS.get(button, button) + " will move files to " + name + ".",
            "success",
        )
        self._build_rows()

    def _assign_button(self, hotkey: str, button: str) -> None:
        mapping = self.app.gamepad_mapping
        for existing_button, existing_hotkey in list(mapping.items()):
            if existing_hotkey == hotkey or existing_button == button:
                mapping.pop(existing_button, None)
        mapping[button] = hotkey
        self.app.save_gamepad_mapping()

    def _clear_hotkey(self, hotkey: str) -> None:
        mapping = self.app.gamepad_mapping
        for button, existing_hotkey in list(mapping.items()):
            if existing_hotkey == hotkey:
                mapping.pop(button, None)
        self.app.save_gamepad_mapping()

    def _clear_all(self) -> None:
        if not self.app.gamepad_mapping:
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Remove every gamepad button assignment?",
            parent=self,
        ):
            return
        self.app.gamepad_mapping.clear()
        self.app.save_gamepad_mapping()
        self._build_rows()
        self.listen_label.configure(text="All gamepad mappings cleared.")
        self.app.show_toast("Gamepad mappings cleared", "Buttons are now unassigned.", "info")

    # -- status / import ------------------------------------------------

    def refresh_status(self, announce: bool = False) -> None:
        manager = self.app.gamepads
        if manager is None or not manager.available:
            self.status_label.configure(
                text="Gamepad support unavailable", fg=DANGER
            )
            self.last_button_label.configure(
                text=manager.error if manager is not None and manager.error else
                "XInput was not found on this PC."
            )
            return
        connected = manager.detect_now()
        self.app._gamepad_connected = connected
        self.app._update_gamepad_label()
        if connected:
            names = ", ".join(item["name"] for item in connected)
            self.status_label.configure(text="Connected: " + names, fg=SUCCESS)
            self.last_button_label.configure(
                text="Press any gamepad button to test the connection.", fg=MUTED
            )
            if announce:
                self.app.show_toast(
                    "Gamepad detected", names + " is ready.", "success"
                )
        else:
            self.status_label.configure(
                text="No gamepad detected", fg=WARN
            )
            self.last_button_label.configure(
                text="Connect a controller, then press Detect Gamepad."
            )
            if announce:
                self.app.show_toast(
                    "No gamepad found",
                    "Connect an Xbox-compatible controller and try again.",
                    "warn",
                )

    def _detect_now(self) -> None:
        self.refresh_status(announce=True)

    def _refresh(self) -> None:
        self._build_rows()
        self.refresh_status()
        self.listen_label.configure(
            text="Click Listen, then press the gamepad button you want to assign."
        )
        self.app.show_toast("Refreshed", "Destinations and gamepad status updated.", "info")

    def _import_amgp(self) -> None:
        initial = ""
        candidates = find_amgp_files()
        if candidates:
            initial = str(candidates[0].parent)
        else:
            initial = str(Path.home() / "Desktop")
        filename = filedialog.askopenfilename(
            parent=self,
            title="Import Steam controller config",
            initialdir=initial,
            filetypes=[("Steam controller config", "*.amgp"), ("All files", "*.*")],
        )
        if not filename:
            return
        mapping, error = parse_amgp_mapping(filename)
        if error:
            messagebox.showerror(
                APP_NAME,
                "Could not read that config:\n" + error,
                parent=self,
            )
            return
        if not mapping:
            messagebox.showinfo(
                APP_NAME,
                "That file does not contain any keyboard button mappings "
                "that File Sorter can use.",
                parent=self,
            )
            return
        self.app.gamepad_mapping.clear()
        self.app.gamepad_mapping.update(mapping)
        self.app.save_gamepad_mapping()
        self._build_rows()
        summary = "\n".join(
            BUTTON_LABELS.get(button, button) + " -> " + hotkey
            for button, hotkey in mapping.items()
        )
        messagebox.showinfo(
            APP_NAME,
            "Imported " + str(len(mapping)) + " button mapping(s):\n\n" + summary,
            parent=self,
        )
        self.app.show_toast(
            "Config imported",
            str(len(mapping)) + " gamepad button(s) mapped.",
            "success",
        )

    # -- window ---------------------------------------------------------

    def _on_escape(self, _event=None) -> None:
        if self._listening_hotkey is not None:
            self._listening_hotkey = None
            self._listening_name = ""
            self.listen_label.configure(text="Listening cancelled.")
            return
        self._close()

    def _center(self) -> None:
        try:
            self.update_idletasks()
            parent = self.app.root
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
            self.geometry("+" + str(max(0, x)) + "+" + str(max(0, y)))
        except Exception:
            pass

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.app._gamepad_window = None
        try:
            self.destroy()
        except Exception:
            pass
