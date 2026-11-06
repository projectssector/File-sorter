"""Tkinter dialogs and styles for File Sorter."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES

from sorter_core import (
    ACCENT,
    ACCENT_HOVER,
    APP_NAME,
    BG,
    BORDER,
    CARD,
    CARD_2,
    DANGER,
    FONT,
    MUTED,
    TEXT,
    apply_dark_titlebar,
    apply_icon,
    command_signature,
    load_commands,
    parse_hotkey,
    short_path,
)


def setup_styles(root) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", font=(FONT, 10))

    style.configure(
        "FileSorter.Treeview",
        background=CARD,
        fieldbackground=CARD,
        foreground=TEXT,
        borderwidth=0,
        rowheight=34,
        font=(FONT, 10),
    )
    style.map(
        "FileSorter.Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", "#ffffff")],
    )
    style.configure(
        "FileSorter.Treeview.Heading",
        background="#121820",
        foreground=MUTED,
        borderwidth=0,
        relief="flat",
        font=(FONT, 9, "bold"),
        padding=(10, 10),
    )
    style.map(
        "FileSorter.Treeview.Heading",
        background=[("active", "#1a232e")],
    )

    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground="#ffffff",
        borderwidth=0,
        focusthickness=0,
        relief="flat",
        padding=(14, 8),
        font=(FONT, 10, "bold"),
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_HOVER), ("pressed", "#1d4ed8")],
        foreground=[("disabled", "#d1d5db")],
    )
    style.configure(
        "Secondary.TButton",
        background=CARD_2,
        foreground=TEXT,
        borderwidth=0,
        focusthickness=0,
        relief="flat",
        padding=(12, 8),
    )
    style.map(
        "Secondary.TButton",
        background=[("active", "#2b3746"), ("pressed", "#242f3c")],
        foreground=[("disabled", MUTED)],
    )
    style.configure(
        "Danger.TButton",
        background="#2a1a1d",
        foreground="#f87171",
        borderwidth=0,
        focusthickness=0,
        relief="flat",
        padding=(12, 8),
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#3a2024"), ("pressed", "#2a1a1d")],
    )
    style.configure(
        "Ghost.TButton",
        background=BG,
        foreground=MUTED,
        borderwidth=0,
        focusthickness=0,
        relief="flat",
        padding=(10, 8),
    )
    style.map(
        "Ghost.TButton",
        background=[("active", CARD)],
        foreground=[("active", TEXT)],
    )

    style.configure(
        "FileSorter.TEntry",
        fieldbackground=CARD_2,
        foreground=TEXT,
        insertcolor=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        borderwidth=1,
        relief="flat",
        padding=8,
    )
    style.map(
        "FileSorter.TEntry",
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
        fieldbackground=[("disabled", CARD), ("readonly", CARD)],
    )

    style.configure(
        "FileSorter.Vertical.TScrollbar",
        background=CARD_2,
        troughcolor=CARD,
        bordercolor=CARD,
        arrowcolor=MUTED,
        darkcolor=CARD_2,
        lightcolor=CARD_2,
    )
    style.map(
        "FileSorter.Vertical.TScrollbar",
        background=[("active", "#2b3746")],
    )

    style.configure(
        "FileSorter.Horizontal.TScrollbar",
        background=CARD_2,
        troughcolor=CARD,
        bordercolor=CARD,
        arrowcolor=MUTED,
        darkcolor=CARD_2,
        lightcolor=CARD_2,
    )
    style.map(
        "FileSorter.Horizontal.TScrollbar",
        background=[("active", "#2b3746")],
    )

    style.configure(
        "TNotebook",
        background=BG,
        borderwidth=0,
        tabmargins=(0, 6, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=CARD,
        foreground=MUTED,
        padding=(16, 8),
        borderwidth=0,
        font=(FONT, 10, "bold"),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", ACCENT), ("active", CARD_2)],
        foreground=[("selected", "#ffffff"), ("active", TEXT)],
    )


class CommandDialog(tk.Toplevel):
    def __init__(self, app, command=None, index=None):
        super().__init__(app.root)
        self.app = app
        self.index = index
        self.command = command
        self.result = None
        self._drop_widgets = []

        self.title("Edit Command" if command else "Add Command")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app.root)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self._center()
        self._center_after_idle()
        apply_icon(self)
        apply_dark_titlebar(self)
        self.grab_set()
        self.bind("<Escape>", lambda _event: self._cancel())
        self.bind("<Return>", lambda _event: self._save())
        self.after(80, self._focus_hotkey)

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG, padx=26, pady=22)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text="Edit move command" if self.command else "Add a move command",
            bg=BG,
            fg=TEXT,
            font=(FONT, 16, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            container,
            text="Choose a hotkey and a destination folder for the files.",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).pack(fill="x", pady=(3, 14))

        tk.Label(
            container,
            text="HOTKEY",
            bg=BG,
            fg=MUTED,
            font=(FONT, 8, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        self.hotkey_var = tk.StringVar(
            value=self.command["hotkey"] if self.command else ""
        )
        self.hotkey_entry = ttk.Entry(
            container,
            textvariable=self.hotkey_var,
            style="FileSorter.TEntry",
            width=50,
        )
        self.hotkey_entry.pack(fill="x")
        tk.Label(
            container,
            text="Examples: 1, F9, ctrl+shift+m, ^+m   (hotkeys only fire while File Explorer is active)",
            bg=BG,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
        ).pack(fill="x", pady=(4, 12))

        tk.Label(
            container,
            text="DESTINATION FOLDER",
            bg=BG,
            fg=MUTED,
            font=(FONT, 8, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        row = tk.Frame(container, bg=BG)
        row.pack(fill="x")
        self.folder_var = tk.StringVar(
            value=self.command["folder"] if self.command else ""
        )
        self.folder_entry = ttk.Entry(
            row, textvariable=self.folder_var, style="FileSorter.TEntry"
        )
        self.folder_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(
            row,
            text="Browse",
            style="Secondary.TButton",
            command=self._browse,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))

        self.drop_zone = tk.Frame(
            container,
            bg=CARD_2,
            height=118,
            highlightbackground=BORDER,
            highlightthickness=2,
        )
        self.drop_zone.pack(fill="x", pady=(12, 14))
        self.drop_zone.pack_propagate(False)

        self.drop_inner = tk.Frame(self.drop_zone, bg=CARD_2)
        self.drop_inner.place(relx=0.5, rely=0.5, anchor="center")

        self.drop_canvas = tk.Canvas(
            self.drop_inner,
            width=58,
            height=44,
            bg=CARD_2,
            highlightthickness=0,
            bd=0,
        )
        self.drop_canvas.pack()
        self.drop_canvas.create_polygon(
            5, 13, 23, 13, 28, 18, 53, 18, 53, 39, 5, 39,
            fill="#1d4ed8", outline="",
        )
        self.drop_canvas.create_polygon(
            5, 18, 53, 18, 53, 39, 5, 39, fill=ACCENT, outline="",
        )
        self.drop_canvas.create_line(29, 23, 29, 32, fill="#ffffff", width=2)
        self.drop_canvas.create_line(24, 28, 29, 33, fill="#ffffff", width=2)
        self.drop_canvas.create_line(34, 28, 29, 33, fill="#ffffff", width=2)

        self.drop_title = tk.Label(
            self.drop_inner,
            text="Drag & drop a folder here",
            bg=CARD_2,
            fg=TEXT,
            font=(FONT, 10, "bold"),
        )
        self.drop_title.pack(pady=(4, 0))
        self.drop_sub = tk.Label(
            self.drop_inner,
            text="or click Browse to choose a folder",
            bg=CARD_2,
            fg=MUTED,
            font=(FONT, 8),
        )
        self.drop_sub.pack()

        for widget in (
            self.drop_zone,
            self.drop_inner,
            self.drop_canvas,
            self.drop_title,
            self.drop_sub,
        ):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _event: self._browse())
            self._register_drop(widget)

        self.error_label = tk.Label(
            container,
            text="",
            bg=BG,
            fg="#f87171",
            font=(FONT, 9),
            anchor="w",
            wraplength=500,
            justify="left",
        )
        self.error_label.pack(fill="x", pady=(0, 8))

        buttons = tk.Frame(container, bg=BG)
        buttons.pack(fill="x", pady=(2, 0))
        ttk.Button(
            buttons,
            text="Cancel",
            style="Secondary.TButton",
            command=self._cancel,
            takefocus=False,
        ).pack(side="right")
        ttk.Button(
            buttons,
            text="Update" if self.command else "Save",
            style="Accent.TButton",
            command=self._save,
            takefocus=False,
        ).pack(side="right", padx=(0, 8))

    def _register_drop(self, widget) -> None:
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.dnd_bind("<<DropEnter>>", lambda _event: self._set_drop_active(True))
            widget.dnd_bind("<<DropLeave>>", lambda _event: self._set_drop_active(False))
            self._drop_widgets.append(widget)
        except Exception:
            pass

    def _set_drop_active(self, active: bool) -> None:
        color = ACCENT if active else BORDER
        background = "#1b2a3f" if active else CARD_2
        try:
            self.drop_zone.configure(highlightbackground=color, bg=background)
            for widget in (
                self.drop_inner,
                self.drop_canvas,
                self.drop_title,
                self.drop_sub,
            ):
                widget.configure(bg=background)
        except Exception:
            pass

    def _on_drop(self, event):
        self._set_drop_active(False)
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        for raw in paths:
            path = os.path.normpath(str(raw))
            if os.path.isdir(path):
                self.folder_var.set(path)
                self._clear_error()
                return event.action
        self._show_error("Please drop a folder, not a file.")
        return event.action

    def _browse(self) -> None:
        folder = filedialog.askdirectory(
            parent=self,
            title="Select destination folder",
            mustexist=True,
        )
        if folder:
            self.folder_var.set(os.path.normpath(folder))
            self._clear_error()

    def _focus_hotkey(self) -> None:
        try:
            self.hotkey_entry.focus_set()
        except Exception:
            pass

    def _show_error(self, message: str) -> None:
        self.error_label.configure(text=message)

    def _clear_error(self) -> None:
        self.error_label.configure(text="")

    def _save(self) -> None:
        hotkey = self.hotkey_var.get().strip()
        folder = self.folder_var.get().strip().strip('"')
        if not hotkey:
            self._show_error("Enter a hotkey (for example: 1 or ctrl+shift+m).")
            return
        if not folder:
            self._show_error("Choose a destination folder.")
            return
        folder = os.path.normpath(folder)
        if not os.path.isdir(folder):
            self._show_error("That destination folder does not exist.")
            return
        try:
            mods, vk = parse_hotkey(hotkey)
        except ValueError as exc:
            self._show_error(str(exc))
            return

        for index, command in enumerate(self.app.active):
            if self.index is not None and index == self.index:
                continue
            try:
                other_mods, other_vk = parse_hotkey(command["hotkey"])
            except Exception:
                continue
            if (other_mods, other_vk) == (mods, vk):
                self._show_error(
                    "Hotkey '" + hotkey + "' is already used by another command."
                )
                return

        self.result = {"hotkey": hotkey, "folder": folder}
        self._close()

    def _cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _center(self) -> None:
        try:
            self.update_idletasks()
            width = max(580, self.winfo_reqwidth())
            height = self.winfo_reqheight()
            parent = self.app.root
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
            self.geometry(str(width) + "x" + str(height) + "+" + str(max(0, x)) + "+" + str(max(0, y)))
        except Exception:
            pass

    def _center_after_idle(self) -> None:
        self.after(10, self._center)


class MemoryWindow(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.configure(bg=BG)
        self._build()
        self._refresh()
        self.bind("<Escape>", lambda _event: self.destroy())

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG, padx=22, pady=20)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Command Memory",
            bg=BG,
            fg=TEXT,
            font=(FONT, 17, "bold"),
            anchor="w",
        ).pack(side="left")
        self.count_label = tk.Label(
            header,
            text="",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="e",
        )
        self.count_label.pack(side="right")
        tk.Label(
            container,
            text="Every command you save is kept here, even after you remove it from the main list.",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).pack(fill="x", pady=(3, 12))

        card = tk.Frame(container, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            card,
            columns=("hotkey", "folder"),
            show="headings",
            selectmode="browse",
            style="FileSorter.Treeview",
        )
        self.tree.heading("hotkey", text="HOTKEY", anchor="w")
        self.tree.heading("folder", text="DESTINATION FOLDER", anchor="w")
        self.tree.column("hotkey", width=130, minwidth=90, stretch=False, anchor="w")
        self.tree.column("folder", width=560, minwidth=260, stretch=True, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        self.tree.tag_configure("odd", background=CARD)
        self.tree.tag_configure("even", background="#1a222c")
        self.tree.bind("<Double-1>", lambda _event: self._load_selected())

        scroll = ttk.Scrollbar(
            card,
            orient="vertical",
            command=self.tree.yview,
            style="FileSorter.Vertical.TScrollbar",
        )
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=12)
        self.tree.configure(yscrollcommand=scroll.set)

        buttons = tk.Frame(container, bg=BG)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(
            buttons,
            text="Load Selected",
            style="Accent.TButton",
            command=self._load_selected,
            takefocus=False,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Delete",
            style="Danger.TButton",
            command=self._delete_selected,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            buttons,
            text="Import .ini",
            style="Secondary.TButton",
            command=self._import_file,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            buttons,
            text="Clear All",
            style="Danger.TButton",
            command=self._clear_all,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            buttons,
            text="Close",
            style="Secondary.TButton",
            command=self.destroy,
            takefocus=False,
        ).pack(side="right")

    def _refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, command in enumerate(self.app.history):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(command["hotkey"], command["folder"]),
                tags=("even" if index % 2 else "odd",),
            )
        self.count_label.configure(text=str(len(self.app.history)) + " saved")

    def _selected_index(self):
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except Exception:
            return None

    def _load_selected(self) -> None:
        index = self._selected_index()
        if index is None or index >= len(self.app.history):
            messagebox.showinfo(APP_NAME, "Select a memory entry to load.", parent=self)
            return
        command = dict(self.app.history[index])
        signature = command_signature(command)
        if any(command_signature(existing) == signature for existing in self.app.active):
            messagebox.showinfo(
                APP_NAME, "That command is already active.", parent=self
            )
            return
        try:
            mods, vk = parse_hotkey(command["hotkey"])
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                "That memory entry has an invalid hotkey:\n" + str(exc),
                parent=self,
            )
            return
        for existing in self.app.active:
            try:
                other_mods, other_vk = parse_hotkey(existing["hotkey"])
            except Exception:
                continue
            if (other_mods, other_vk) == (mods, vk):
                messagebox.showwarning(
                    APP_NAME,
                    "Hotkey '" + command["hotkey"] + "' is already used by another command.",
                    parent=self,
                )
                return
        self.app.active.append(command)
        self.app._save_active()
        self.app._refresh_list()
        self.app._sync_hotkeys()
        self.app._set_status("Loaded hotkey " + command["hotkey"] + " from memory")
        self.app.show_toast(
            "Command loaded",
            command["hotkey"] + " will move files to " + short_path(command["folder"]) + ".",
            "success",
        )

    def _delete_selected(self) -> None:
        index = self._selected_index()
        if index is None or index >= len(self.app.history):
            messagebox.showinfo(APP_NAME, "Select a memory entry to delete.", parent=self)
            return
        command = self.app.history.pop(index)
        self.app._save_history()
        self._refresh()
        self.app._set_status("Removed " + command["hotkey"] + " from memory")

    def _import_file(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
            title="Import commands",
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")],
        )
        if not filename:
            return
        commands = load_commands(Path(filename))
        if not commands:
            messagebox.showinfo(
                APP_NAME, "No valid commands were found in that file.", parent=self
            )
            return
        added_active = 0
        for command in commands:
            sig = command_signature(command)
            if not any(command_signature(item) == sig for item in self.app.history):
                self.app.history.append(dict(command))
            if not any(command_signature(item) == sig for item in self.app.active):
                self.app.active.append(dict(command))
                added_active += 1
        self.app._save_all()
        self.app._refresh_list()
        self.app._sync_hotkeys()
        self._refresh()
        messagebox.showinfo(
            APP_NAME,
            "Imported " + str(len(commands)) + " command(s).\n"
            + str(added_active) + " added to the main list.",
            parent=self,
        )

    def _clear_all(self) -> None:
        if not self.app.history:
            return
        if not messagebox.askyesno(
            APP_NAME,
            "Clear all saved commands from memory?\n\nCommands in the main list will stay active.",
            parent=self,
        ):
            return
        self.app.history.clear()
        self.app._save_history()
        self._refresh()
        self.app._set_status("Memory cleared")

    def _center(self) -> None:
        try:
            self.update_idletasks()
            parent = self.app.root
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
            self.geometry("+" + str(max(0, x)) + "+" + str(max(0, y)))
        except Exception:
            pass
