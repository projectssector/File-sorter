"""In-app image viewer and sorter window."""

from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk
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
    SUCCESS,
    TEXT,
    WARN,
    apply_dark_titlebar,
    apply_icon,
    collect_image_files,
    format_size,
    keysym_to_vk,
    move_single_file,
    parse_hotkey,
    unique_target,
    restore_moved_file,
    short_path,
    vk_from_char,
)

IMAGE_FILE_TYPES = [
    (
        "Images",
        "*.jpg *.jpeg *.jpe *.jfif *.png *.gif *.bmp *.webp "
        "*.tif *.tiff *.ico *.heic *.heif *.avif",
    ),
    ("All files", "*.*"),
]

THUMB_SIZE = (78, 58)
MAX_THUMBS = 400


class ImageSorterWindow(tk.Frame):
    """A tab that lets you file images with the configured commands."""

    def __init__(self, parent, app, files=None):
        super().__init__(parent)
        self.app = app
        self.configure(bg=BG)

        self._images: list[str] = []
        self._all_images: list[str] = []
        self._moved: set[str] = set()
        self._sectors: list[list[str]] = []
        self._sector_index = 0
        self._sector_size = 2000
        self._loading_images = False
        self._index = 0
        self._photo = None
        self._placeholder = ImageTk.PhotoImage(
            Image.new("RGB", THUMB_SIZE, CARD_2), master=self
        )
        self._thumb_refs = {}
        self._thumb_cache = {}
        self._loaded_thumbs = set()
        self._image_info_cache = {}
        self._strip_labels = []
        self._strip_generation = 0
        self._thumb_job = None
        self._render_job = None
        self._current_strip_label = None
        self._destination_by_combo = {}
        self._dest_buttons = []
        self._extra_destinations = []
        self._moves = []
        self._closing = False

        self._build_ui()
        self._reload_destinations()
        if files:
            self.add_files(files)

        self.bind("<KeyPress>", self._on_key)
        self._register_dnd()

        self.after(80, self.focus_preview)
        self.after(140, self._render_preview)
        if not self._images:
            self.after(260, self._add_files_dialog)

    # -- layout ---------------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 12))
        header.grid_columnconfigure(0, weight=1)

        title_wrap = tk.Frame(header, bg=BG)
        title_wrap.grid(row=0, column=0, sticky="w")
        tk.Label(
            title_wrap,
            text="Image Sorter",
            bg=BG,
            fg=TEXT,
            font=(FONT, 22, "bold"),
            anchor="w",
        ).pack(side="left")
        self.count_label = tk.Label(
            title_wrap,
            text="0 images",
            bg=BG,
            fg=MUTED,
            font=(FONT, 10),
            anchor="w",
        )
        self.count_label.pack(side="left", padx=(12, 0), pady=(6, 0))
        tk.Label(
            header,
            text=(
                "Pick the images you want to sort, then click a destination "
                "or press its hotkey."
            ),
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        actions = tk.Frame(header, bg=BG)
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(
            actions,
            text="Add Images",
            style="Accent.TButton",
            command=self._add_files_dialog,
            takefocus=False,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Add Folder",
            style="Secondary.TButton",
            command=self._add_folder_dialog,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Open Original",
            style="Secondary.TButton",
            command=self._open_original,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Close",
            style="Ghost.TButton",
            command=self._close,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))

        body = tk.Frame(self, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 12))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=330)

        self._build_preview(body)
        self._build_sidebar(body)
        self._build_footer()

    def _build_preview(self, parent) -> None:
        card = tk.Frame(
            parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        self.preview_pane = tk.PanedWindow(
            card, orient=tk.VERTICAL, sashwidth=6, bg=BORDER, sashrelief=tk.FLAT
        )
        self.preview_pane.grid(row=0, column=0, sticky="nsew")

        top_frame = tk.Frame(self.preview_pane, bg=CARD)
        top_frame.grid_rowconfigure(0, weight=1)
        top_frame.grid_columnconfigure(0, weight=1)
        self.preview_frame = top_frame

        self.canvas = tk.Canvas(
            top_frame, bg="#090d12", highlightthickness=0, bd=0, cursor="hand2",
            takefocus=True,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._schedule_render)
        self.canvas.bind("<Button-1>", lambda _event: self._open_original())
        self.canvas.bind("<KeyPress>", self._on_key)
        self.bind("<KeyPress>", self._on_key)

        info = tk.Frame(top_frame, bg=CARD)
        info.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 4))

        strip_frame = tk.Frame(self.preview_pane, bg=CARD)
        strip_frame.grid_rowconfigure(0, weight=1)
        strip_frame.grid_columnconfigure(0, weight=1)

        self.preview_pane.add(top_frame, minsize=180, stretch="always")
        self.preview_pane.add(strip_frame, minsize=60, stretch="never")
        self.name_label = tk.Label(
            info,
            text="No image selected",
            bg=CARD,
            fg=TEXT,
            font=(FONT, 11, "bold"),
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.name_label.pack(fill="x")
        self.meta_label = tk.Label(
            info,
            text="Add images or drag and drop them onto this window.",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
            justify="left",
        )
        self.meta_label.pack(fill="x", pady=(2, 0))
        self.sector_label = tk.Label(
            info,
            text="",
            bg=CARD,
            fg=ACCENT,
            font=(FONT, 9, "bold"),
            anchor="w",
            justify="left",
        )
        self.sector_label.pack(fill="x", pady=(4, 0))

        self.loading_overlay = tk.Frame(self.preview_frame, bg=BG)
        self.loading_label = tk.Label(
            self.loading_overlay,
            text="Loading images and preparing sectors...",
            bg=BG,
            fg=TEXT,
            font=(FONT, 14, "bold"),
        )
        self.loading_label.place(relx=0.5, rely=0.42, anchor="center")
        self.loading_progress = ttk.Progressbar(
            self.loading_overlay, mode="indeterminate", length=260
        )
        self.loading_progress.place(relx=0.5, rely=0.5, anchor="center")
        self.loading_detail = tk.Label(
            self.loading_overlay,
            text="Please wait",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
        )
        self.loading_detail.place(relx=0.5, rely=0.58, anchor="center")

        strip_wrap = tk.Frame(strip_frame, bg=CARD)
        strip_wrap.grid(row=0, column=0, sticky="nsew", padx=10, pady=(4, 10))
        strip_frame.grid_rowconfigure(0, weight=1)
        strip_frame.grid_columnconfigure(0, weight=1)
        strip_wrap.grid_columnconfigure(0, weight=1)

        self.strip_canvas = tk.Canvas(
            strip_wrap,
            bg=CARD,
            height=THUMB_SIZE[1] + 10,
            highlightthickness=0,
            bd=0,
        )
        self.strip_canvas.grid(row=0, column=0, sticky="ew")
        strip_scroll = ttk.Scrollbar(
            strip_wrap,
            orient="horizontal",
            command=self.strip_canvas.xview,
            style="FileSorter.Horizontal.TScrollbar",
        )
        strip_scroll.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.strip_canvas.configure(xscrollcommand=strip_scroll.set)
        self.strip_canvas.bind("<MouseWheel>", self._scroll_strip)
        self.strip_canvas.bind("<Configure>", lambda _event: self.after(50, self._load_visible_thumbs))

        self.strip_inner = tk.Frame(self.strip_canvas, bg=CARD)
        self._strip_window = self.strip_canvas.create_window(
            (0, 0), window=self.strip_inner, anchor="nw"
        )
        self.strip_inner.bind(
            "<Configure>",
            lambda _event: None,
        )
        self.strip_canvas.bind(
            "<Configure>",
            lambda event: self.strip_canvas.itemconfigure(
                self._strip_window, height=event.height
            ),
        )

    def _build_sidebar(self, parent) -> None:
        sidebar = tk.Frame(
            parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        sidebar.grid(row=0, column=1, sticky="nsew")
        sidebar.grid_rowconfigure(1, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        heading = tk.Frame(sidebar, bg=CARD)
        heading.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        heading.grid_columnconfigure(0, weight=1)
        tk.Label(
            heading,
            text="MOVE TO",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            heading,
            text="Refresh",
            style="Ghost.TButton",
            command=self._reload_destinations,
            takefocus=False,
        ).grid(row=0, column=1, sticky="e")

        dest_wrap = tk.Frame(sidebar, bg=CARD)
        dest_wrap.grid(row=1, column=0, sticky="nsew", padx=(10, 4), pady=(0, 4))
        dest_wrap.grid_rowconfigure(0, weight=1)
        dest_wrap.grid_columnconfigure(0, weight=1)
        self.dest_canvas = tk.Canvas(
            dest_wrap, bg=CARD, highlightthickness=0, bd=0
        )
        self.dest_canvas.grid(row=0, column=0, sticky="nsew")
        dest_scroll = ttk.Scrollbar(
            dest_wrap,
            orient="vertical",
            command=self.dest_canvas.yview,
            style="FileSorter.Vertical.TScrollbar",
        )
        dest_scroll.grid(row=0, column=1, sticky="ns")
        self.dest_canvas.configure(yscrollcommand=dest_scroll.set)
        self.dest_inner = tk.Frame(self.dest_canvas, bg=CARD)
        self._dest_window = self.dest_canvas.create_window(
            (0, 0), window=self.dest_inner, anchor="nw"
        )
        self.dest_inner.bind(
            "<Configure>",
            lambda _event: self.dest_canvas.configure(
                scrollregion=self.dest_canvas.bbox("all")
            ),
        )
        self.dest_canvas.bind(
            "<Configure>",
            lambda event: self.dest_canvas.itemconfigure(
                self._dest_window, width=event.width
            ),
        )
        self.dest_canvas.bind("<MouseWheel>", self._scroll_destinations)
        self.dest_inner.bind("<MouseWheel>", self._scroll_destinations)

        footer = tk.Frame(sidebar, bg=CARD)
        footer.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(
            footer,
            text="Add Destination Folder",
            style="Secondary.TButton",
            command=self._add_destination_dialog,
            takefocus=False,
        ).pack(fill="x")
        ttk.Button(
            footer,
            text="Undo Last Move",
            style="Secondary.TButton",
            command=self._undo_last_move,
            takefocus=False,
        ).pack(fill="x", pady=(6, 0))
        self.status_label = tk.Label(
            footer,
            text="",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
            justify="left",
            wraplength=290,
        )
        self.status_label.pack(fill="x", pady=(8, 0))

    def _build_footer(self) -> None:
        footer = tk.Frame(self, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 16))
        left = tk.Frame(footer, bg=BG)
        left.pack(side="left")
        right = tk.Frame(footer, bg=BG)
        right.pack(side="right")

        ttk.Button(
            left,
            text="< Previous",
            style="Secondary.TButton",
            command=self.previous_image,
            takefocus=False,
        ).pack(side="left")
        ttk.Button(
            left,
            text="Next >",
            style="Secondary.TButton",
            command=self.next_image,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            left,
            text="Skip",
            style="Secondary.TButton",
            command=self.next_image,
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            left,
            text="<< Sector",
            style="Secondary.TButton",
            command=lambda: self._move_sector(-1),
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            left,
            text="Sector >>",
            style="Secondary.TButton",
            command=lambda: self._move_sector(1),
            takefocus=False,
        ).pack(side="left", padx=(8, 0))
        self.progress_label = tk.Label(
            right,
            text="Left/Right to browse  -  hotkeys move the current image",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
        )
        self.progress_label.pack(side="right")

    # -- destinations ---------------------------------------------------

    def _reload_destinations(self) -> None:
        for child in self.dest_inner.winfo_children():
            child.destroy()
        self._dest_buttons = []
        self._destination_by_combo = {}

        destinations = [dict(command) for command in self.app.active]
        destinations.extend(self._extra_destinations)

        if not destinations:
            tk.Label(
                self.dest_inner,
                text=(
                    "No destinations yet.\n\n"
                    "Add a move command in the main File Sorter window, then "
                    "press Refresh."
                ),
                bg=CARD,
                fg=MUTED,
                font=(FONT, 9),
                justify="left",
                wraplength=270,
                anchor="w",
            ).pack(fill="x", padx=6, pady=12)
            return

        for command in destinations:
            combo = None
            hotkey = command.get("hotkey", "")
            if hotkey:
                try:
                    combo = parse_hotkey(hotkey)
                except Exception:
                    combo = None
            if combo is not None:
                self._destination_by_combo[combo] = command
            self._dest_buttons.append(self._make_destination_card(command, combo))

    def _make_destination_card(self, command: dict, combo) -> tk.Frame:
        folder = command.get("folder", "")
        name = Path(folder).name or folder
        hotkey = command.get("hotkey", "")

        card = tk.Frame(
            self.dest_inner,
            bg=CARD_2,
            highlightbackground=BORDER,
            highlightthickness=1,
            cursor="hand2",
        )
        card.pack(fill="x", padx=4, pady=4)

        badge_text = hotkey if hotkey else "click"
        badge = tk.Label(
            card,
            text=badge_text,
            bg=ACCENT if hotkey else CARD,
            fg="#ffffff" if hotkey else MUTED,
            font=(FONT, 9, "bold"),
            padx=8,
            pady=4,
        )
        badge.pack(side="left", padx=(10, 10), pady=10)

        info = tk.Frame(card, bg=CARD_2)
        info.pack(side="left", fill="x", expand=True, pady=8)
        title = tk.Label(
            info,
            text=name + ("  \u2713" if os.path.isdir(folder) else "  \u2717"),
            bg=CARD_2,
            fg=TEXT,
            font=(FONT, 10, "bold"),
            anchor="w",
            justify="left",
        )
        title.pack(fill="x")
        path_label = tk.Label(
            info,
            text=short_path(folder, 2),
            bg=CARD_2,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
            justify="left",
        )
        path_label.pack(fill="x", pady=(2, 0))

        widgets = (card, badge, info, title, path_label)

        def on_enter(_event):
            for widget in (card, info, title, path_label):
                try:
                    widget.configure(bg="#243244")
                except Exception:
                    pass
            try:
                card.configure(highlightbackground=ACCENT)
            except Exception:
                pass

        def on_leave(_event):
            for widget in (card, info, title, path_label):
                try:
                    widget.configure(bg=CARD_2)
                except Exception:
                    pass
            try:
                card.configure(highlightbackground=BORDER)
            except Exception:
                pass

        def on_click(_event):
            self._move_current(command)

        for widget in widgets:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", on_click)

        return card

    def _add_destination_dialog(self) -> None:
        folder = filedialog.askdirectory(
            parent=self, title="Add a destination folder", mustexist=True
        )
        if not folder:
            return
        folder = os.path.normpath(folder)
        existing = {os.path.normcase(c.get("folder", "")) for c in self.app.active}
        existing.update(
            os.path.normcase(c.get("folder", "")) for c in self._extra_destinations
        )
        if os.path.normcase(folder) in existing:
            self._set_status("That folder is already a destination.")
            return
        self._extra_destinations.append({"hotkey": "", "folder": folder})
        self._reload_destinations()
        self._set_status("Added destination " + Path(folder).name + ".")

    # -- files ----------------------------------------------------------

    def add_files(self, paths) -> None:
        if self._loading_images:
            self._set_status("Already loading images...")
            return
        self._loading_images = True
        self._set_status("Loading images...")
        self._show_loading_overlay()
        self._update_sector_label()
        threading.Thread(
            target=self._load_images_worker, args=(list(paths or []),), daemon=True
        ).start()

    def _load_images_worker(self, paths) -> None:
        try:
            images = self._collect_with_no_preview(paths)
        except Exception:
            images = []
        try:
            self.app._ui(self._apply_loaded_images, images)
        except Exception:
            pass

    def _collect_with_no_preview(self, paths) -> list[str]:
        from sorter_core import collect_image_files, is_image_file, is_previewable_image

        from sorter_core import is_image_file, is_previewable_image

        for raw in paths or []:
            candidate = Path(str(raw).strip().strip('"'))
            try:
                if candidate.is_dir():
                    no_preview = candidate / "no_preview"
                    for entry in list(candidate.iterdir()):
                        if not entry.is_file() or not is_image_file(str(entry)):
                            continue
                        if is_previewable_image(str(entry)):
                            continue
                        no_preview.mkdir(exist_ok=True)
                        target = unique_target(no_preview, entry.name)
                        try:
                            shutil.move(str(entry), str(target))
                        except Exception:
                            pass
                elif candidate.is_file() and is_image_file(str(candidate)):
                    if not is_previewable_image(str(candidate)):
                        no_preview = candidate.parent / "no_preview"
                        no_preview.mkdir(exist_ok=True)
                        target = unique_target(no_preview, candidate.name)
                        try:
                            shutil.move(str(candidate), str(target))
                        except Exception:
                            pass
            except Exception:
                continue
        return collect_image_files(paths)

    def _apply_loaded_images(self, images) -> None:
        self._loading_images = False
        self._hide_loading_overlay()
        existing = {os.path.normcase(os.path.abspath(path)) for path in self._all_images}
        added = 0
        for image in images or []:
            key = os.path.normcase(os.path.abspath(image))
            if key in existing:
                continue
            existing.add(key)
            self._all_images.append(image)
            added += 1
        if not added:
            if images:
                self._set_status("Those images are already in the list.")
            else:
                self._set_status("No supported image files were found.")
            self._update_sector_label()
            self._update_info()
            if not self._images and self._all_images:
                self._load_first_nonempty_sector()
            return
        self._set_status(str(added) + " image(s) added.")
        if not self._images:
            self._sector_index = 0
            self._load_sector(0)
        else:
            self._update_sector_label()
            self._update_counts()
            self._update_info()
            self._rebuild_strip()
            self._render_preview()

    def _load_first_nonempty_sector(self) -> None:
        total = self._sector_total()
        for index in range(total):
            images = self._sector_images(index)
            if images:
                self._load_sector(index)
                return
        self._images = []
        self._render_preview()
        self._update_counts()
        self._update_sector_label()
        self._update_info()

    def _sector_total(self) -> int:
        if not self._all_images:
            return 0
        return (len(self._all_images) + self._sector_size - 1) // self._sector_size

    def _sector_images(self, index: int) -> list[str]:
        start = index * self._sector_size
        end = start + self._sector_size
        return [
            path
            for path in self._all_images[start:end]
            if os.path.normcase(os.path.abspath(path)) not in self._moved
        ]

    def _load_sector(self, index: int) -> None:
        total = self._sector_total()
        if total == 0:
            self._images = []
            self._sector_index = 0
            self._render_preview()
            self._update_counts()
            self._update_sector_label()
            self._update_info()
            return
        if index < 0:
            index = total - 1
        if index >= total:
            index = 0
        self._sector_index = index
        self._images = self._sector_images(index)
        if self._index >= len(self._images):
            self._index = 0
        self._rebuild_strip()
        self._render_preview()
        self._update_counts()
        self._update_sector_label()
        self._update_info()
        if self._images:
            self.after(0, self._show_sector_change)

    def _show_sector_change(self) -> None:
        total = self._sector_total()
        self._set_status(
            "Sector " + str(self._sector_index + 1) + " of " + str(total) + " ready."
        )

    def _show_loading_overlay(self) -> None:
        try:
            self.loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.loading_progress.start(12)
            self.loading_overlay.lift()
        except Exception:
            pass

    def _hide_loading_overlay(self) -> None:
        try:
            self.loading_progress.stop()
            self.loading_overlay.place_forget()
        except Exception:
            pass

    def _add_files_dialog(self) -> None:
        files = filedialog.askopenfilenames(
            parent=self,
            title="Select images to sort",
            filetypes=IMAGE_FILE_TYPES,
        )
        if files:
            self.add_files(files)
            self.focus_preview()

    def _add_folder_dialog(self) -> None:
        folder = filedialog.askdirectory(
            parent=self, title="Select a folder of images", mustexist=True
        )
        if folder:
            self.add_files([folder])
            self.focus_preview()

    def _register_dnd(self) -> None:
        def register(widget) -> None:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass
            try:
                children = widget.winfo_children()
            except Exception:
                return
            for child in children:
                register(child)

        try:
            register(self)
        except Exception:
            pass

    def _on_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        self.add_files(paths)
        return getattr(event, "action", "copy")

    # -- navigation / preview ------------------------------------------

    def focus_preview(self) -> None:
        try:
            self.focus_force()
            self.canvas.focus_set()
        except Exception:
            pass

    def _schedule_render(self, _event=None) -> None:
        if self._closing:
            return
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
        self._render_job = self.after(90, self._render_preview)

    def _render_preview(self) -> None:
        self._render_job = None
        if self._closing:
            return
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())

        if not self._images:
            self.canvas.create_text(
                width // 2,
                height // 2 - 16,
                text="No images selected",
                fill=TEXT,
                font=(FONT, 16, "bold"),
            )
            self.canvas.create_text(
                width // 2,
                height // 2 + 18,
                text="Click Add Images, or drag image files here.",
                fill=MUTED,
                font=(FONT, 10),
            )
            self.name_label.configure(text="No image selected")
            self.meta_label.configure(
                text="Add images or drag and drop them onto this window."
            )
            self._photo = None
            return

        path = self._images[self._index]
        try:
            with Image.open(path) as image:
                original_size = image.size
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")
                image.thumbnail((max(1, width - 36), max(1, height - 36)), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image, master=self)
        except Exception as exc:
            self.canvas.create_text(
                width // 2,
                height // 2 - 10,
                text="Preview unavailable",
                fill=DANGER,
                font=(FONT, 15, "bold"),
            )
            self.canvas.create_text(
                width // 2,
                height // 2 + 22,
                text=Path(path).name + "\n" + str(exc),
                fill=MUTED,
                font=(FONT, 9),
                width=max(200, width - 80),
            )
            self._photo = None
        else:
            self._photo = photo
            self.canvas.create_image(width // 2, height // 2, image=photo)

        self._update_info()

    def _update_info(self) -> None:
        if not self._images:
            self.name_label.configure(text="No image selected")
            self.meta_label.configure(
                text="Add images or drag and drop them onto this window."
            )
            self.progress_label.configure(
                text="Left/Right to browse  -  hotkeys move the current image"
            )
            return
        path = self._images[self._index]
        name = Path(path).name
        self.name_label.configure(text=name)
        details = (
            str(self._index + 1)
            + " of "
            + str(len(self._images))
            + "   -   "
            + short_path(str(Path(path).parent), 2)
        )
        try:
            if path in self._image_info_cache:
                width_px, height_px, size = self._image_info_cache[path]
            else:
                size = os.path.getsize(path)
                with Image.open(path) as image:
                    width_px, height_px = image.width, image.height
                self._image_info_cache[path] = (width_px, height_px, size)
            details += "   -   " + str(width_px) + " x " + str(height_px)
            details += "   -   " + format_size(size)
        except Exception:
            pass
        self.meta_label.configure(text=details)
        self.progress_label.configure(
            text="Left/Right to browse  -  hotkeys move the current image"
        )
        self._highlight_strip()

    def _update_counts(self) -> None:
        total = len(self._images)
        if total:
            text = str(self._index + 1) + " of " + str(total) + " images left"
        else:
            text = "0 images"
        self.count_label.configure(text=text)
        self._update_sector_label()

    def _update_sector_label(self) -> None:
        try:
            if not self._all_images:
                self.sector_label.configure(text="")
                return
            total_sectors = self._sector_total()
            remaining_total = len(self._all_images) - len(self._moved)
            text = (
                "Sector "
                + str(self._sector_index + 1)
                + " of "
                + str(total_sectors)
                + "  |  "
                + str(len(self._images))
                + " in this sector  |  "
                + str(remaining_total)
                + " remaining total"
            )
            if self._loading_images:
                text += "  |  Loading next images..."
            self.sector_label.configure(text=text, fg=ACCENT)
        except Exception:
            pass

    def _move_sector(self, direction: int) -> None:
        total = self._sector_total()
        if total <= 1:
            return
        new_index = self._sector_index + direction
        if new_index < 0:
            new_index = total - 1
        if new_index >= total:
            new_index = 0
        self._load_sector(new_index)
        self._index = 0
        self._render_preview()
        self._update_counts()
        self._scroll_to_current_thumb()

    def previous_image(self) -> None:
        if not self._images:
            if self._sector_index > 0:
                self._load_sector(self._sector_index - 1)
                if self._images:
                    self._index = len(self._images) - 1
                    self._render_preview()
                    self._update_counts()
                    self._scroll_to_current_thumb()
            return
        if self._index == 0 and self._sector_index > 0:
            self._load_sector(self._sector_index - 1)
            if self._images:
                self._index = len(self._images) - 1
        else:
            self._index = (self._index - 1) % len(self._images)
        self._render_preview()
        self._update_counts()
        self._scroll_to_current_thumb()

    def next_image(self) -> None:
        if not self._images:
            total = self._sector_total()
            if self._sector_index + 1 < total:
                self._load_sector(self._sector_index + 1)
                self._index = 0
                self._render_preview()
                self._update_counts()
                self._scroll_to_current_thumb()
            return
        if (
            self._index == len(self._images) - 1
            and self._sector_index + 1 < self._sector_total()
        ):
            self._load_sector(self._sector_index + 1)
            self._index = 0
        else:
            self._index = (self._index + 1) % len(self._images)
        self._render_preview()
        self._update_counts()
        self._scroll_to_current_thumb()

    def _select_index(self, index: int) -> None:
        if 0 <= index < len(self._images):
            self._index = index
            self._render_preview()
            self._update_counts()
            self._scroll_to_current_thumb()

    # -- filmstrip ------------------------------------------------------

    def _rebuild_strip(self) -> None:
        self._strip_generation += 1
        if self._thumb_job is not None:
            try:
                self.after_cancel(self._thumb_job)
            except Exception:
                pass
            self._thumb_job = None
        for child in self.strip_inner.winfo_children():
            child.destroy()
        self._strip_labels = []
        self._thumb_refs = {}
        self._current_strip_label = None

        self._strip_labels = [None] * len(self._images)
        try:
            for child in self.strip_inner.winfo_children():
                child.destroy()
        except Exception:
            pass
        self._loaded_thumbs.clear()
        thumb_width = THUMB_SIZE[0] + 10
        total_width = max(1, len(self._images) * thumb_width)
        try:
            self.strip_canvas.configure(
                scrollregion=(0, 0, total_width, THUMB_SIZE[1] + 12)
            )
        except Exception:
            pass
        self._highlight_strip()
        self.after(50, self._load_visible_thumbs)

    def _load_visible_thumbs(self) -> None:
        if self._closing or not self._strip_labels:
            return
        try:
            self.update_idletasks()
            width = max(1, self.strip_canvas.winfo_width())
            left = self.strip_canvas.canvasx(0)
            right = left + width
            thumb_width = THUMB_SIZE[0] + 10
            start = max(0, int(left // thumb_width) - 2)
            end = min(len(self._strip_labels), int(right // thumb_width) + 4)
        except Exception:
            start, end = 0, min(24, len(self._strip_labels))
        loaded_any = False
        for index in range(start, end):
            if index in self._loaded_thumbs:
                continue
            if index >= len(self._images):
                continue
            path = self._images[index]
            try:
                if path in self._thumb_cache:
                    photo = self._thumb_cache[path]
                else:
                    with Image.open(path) as image:
                        image = ImageOps.exif_transpose(image)
                        if image.mode not in ("RGB", "RGBA"):
                            image = image.convert("RGBA")
                        image.thumbnail(THUMB_SIZE, Image.LANCZOS)
                        photo = ImageTk.PhotoImage(image, master=self)
                    self._thumb_cache[path] = photo
                self._thumb_refs[index] = photo
                label = self._ensure_strip_label(index)
                if label is not None:
                    label.configure(image=photo)
                self._loaded_thumbs.add(index)
                loaded_any = True
            except Exception:
                pass
        if loaded_any and end < len(self._strip_labels):
            self.after_idle(self._load_visible_thumbs)
        self.after_idle(self._load_next_thumb_chunk, max(end, 0))

    def _load_next_thumb_chunk(self, start: int) -> None:
        if self._closing or not self._strip_labels:
            return
        chunk_size = 16
        end = min(start + chunk_size, len(self._strip_labels))
        loaded_any = False
        for index in range(start, end):
            if index in self._loaded_thumbs:
                continue
            if index >= len(self._images):
                continue
            path = self._images[index]
            try:
                if path in self._thumb_cache:
                    photo = self._thumb_cache[path]
                else:
                    with Image.open(path) as image:
                        image = ImageOps.exif_transpose(image)
                        if image.mode not in ("RGB", "RGBA"):
                            image = image.convert("RGBA")
                        image.thumbnail(THUMB_SIZE, Image.LANCZOS)
                        photo = ImageTk.PhotoImage(image, master=self)
                    self._thumb_cache[path] = photo
                self._thumb_refs[index] = photo
                label = self._ensure_strip_label(index)
                if label is not None:
                    label.configure(image=photo)
                self._loaded_thumbs.add(index)
                loaded_any = True
            except Exception:
                pass
        if end < len(self._strip_labels):
            self.after_idle(self._load_next_thumb_chunk, end)

    def _ensure_strip_label(self, index: int):
        if index < 0 or index >= len(self._strip_labels):
            return None
        label = self._strip_labels[index]
        if label is not None:
            try:
                if label.winfo_exists():
                    return label
            except Exception:
                pass
        try:
            label = tk.Label(
                self.strip_inner,
                image=self._placeholder,
                bg=CARD_2,
                bd=0,
                padx=2,
                pady=2,
                cursor="hand2",
            )
            thumb_width = THUMB_SIZE[0] + 10
            label.place(x=index * thumb_width, y=4)
            label.bind(
                "<Button-1>", lambda _event, i=index: self._select_index(i)
            )
            self._strip_labels[index] = label
            return label
        except Exception:
            return None

    def _highlight_strip(self) -> None:
        if self._current_strip_label is not None:
            try:
                if self._current_strip_label.winfo_exists():
                    self._current_strip_label.configure(
                        bg=CARD_2, highlightthickness=0
                    )
            except Exception:
                pass
            self._current_strip_label = None
        if not self._images or self._index >= len(self._strip_labels):
            return
        label = self._ensure_strip_label(self._index)
        if label is None:
            return
        try:
            label.configure(bg=ACCENT, highlightbackground=ACCENT, highlightthickness=2)
            self._current_strip_label = label
        except Exception:
            pass

    def _scroll_to_current_thumb(self) -> None:
        if self._index >= len(self._strip_labels):
            return
        label = self._ensure_strip_label(self._index)
        if label is None:
            return
        try:
            self.update_idletasks()
            width = max(1, self.strip_canvas.winfo_width())
            content_width = max(1, self.strip_inner.winfo_width())
            if content_width <= width:
                return
            left = label.winfo_x()
            right = left + label.winfo_width()
            view_left = self.strip_canvas.canvasx(0)
            view_right = view_left + width
            if left < view_left:
                self.strip_canvas.xview_moveto(left / content_width)
            elif right > view_right:
                self.strip_canvas.xview_moveto(
                    max(0.0, (right - width) / content_width)
                )
            self.after(50, self._load_visible_thumbs)
        except Exception:
            pass

    def _scroll_strip(self, event):
        try:
            self.strip_canvas.xview_scroll(int(-event.delta / 120), "units")
        except Exception:
            pass
        return "break"

    def _scroll_destinations(self, event):
        try:
            self.dest_canvas.yview_scroll(int(-event.delta / 120), "units")
        except Exception:
            pass
        return "break"

    # -- moving ---------------------------------------------------------

    def _move_current(self, command: dict) -> None:
        if not self._images:
            self._set_status("Add some images first.")
            return
        destination = command.get("folder", "")
        source = self._images[self._index]
        original_index = self._index
        ok, result = move_single_file(source, destination)
        if not ok:
            self._set_status(result)
            self.app.show_toast("Could not move file", result, "error")
            return
        self._moves.append((result, source, original_index))
        self._moved.add(os.path.normcase(os.path.abspath(source)))
        self._images.pop(original_index)
        if self._images:
            self._index = original_index % len(self._images)
        else:
            self._index = 0
        if not self._images:
            total = self._sector_total()
            if self._sector_index + 1 < total:
                self._load_sector(self._sector_index + 1)
                self._show_sector_change_toast()
        self._rebuild_strip()
        self._render_preview()
        self._update_counts()

        name = Path(source).name
        folder_name = Path(destination).name or destination
        self._set_status("Moved " + name + " to " + folder_name + ".")
        self.app.show_toast(
            "Moved " + name,
            "Filed in " + folder_name + ".",
            "success",
        )
        if not self._images:
            self._show_done()

    def _show_done(self) -> None:
        self._set_status("All images sorted. You can add more images anytime.")
        self.app.show_toast(
            "All done",
            "Every image in the list has been sorted.",
            "success",
        )

    def _undo_last_move(self) -> None:
        if not self._moves:
            self._set_status("There is no move to undo.")
            return
        moved_path, original_path, original_index = self._moves.pop()
        ok, result = restore_moved_file(moved_path, original_path)
        if not ok:
            self._set_status(result)
            self.app.show_toast("Undo failed", result, "error")
            return
        if result not in self._images:
            index = min(original_index, len(self._images))
            self._images.insert(index, result)
            self._index = index
        self._moved.discard(os.path.normcase(os.path.abspath(result)))
        self._update_sector_label()
        self._rebuild_strip()
        self._render_preview()
        self._update_counts()
        self._set_status("Move undone: " + Path(result).name)
        self.app.show_toast(
            "Move undone",
            Path(result).name + " was put back.",
            "info",
        )

    def _open_original(self) -> None:
        if not self._images:
            return
        path = self._images[self._index]
        try:
            os.startfile(path)
        except Exception as exc:
            self._set_status("Could not open image: " + str(exc))

    # -- keyboard -------------------------------------------------------

    def _event_combo(self, event):
        mods = set()
        state = int(event.state)
        if state & 0x4:
            mods.add("ctrl")
        if state & 0x1:
            mods.add("shift")
        if state & (0x8 | 0x20000):
            mods.add("alt")
        vk = vk_from_char(event.char)
        if vk is None:
            vk = keysym_to_vk(event.keysym)
            if vk is None:
                keysym = (event.keysym or "").lower()
                if keysym.startswith("kp_") and len(keysym) == 4 and keysym[3].isdigit():
                    vk = 0x30 + int(keysym[3])
        elif 0x60 <= vk <= 0x69:
            vk = 0x30 + (vk - 0x60)
        return frozenset(mods), vk

    def _on_key(self, event):
        if self._closing:
            return
        mods, vk = self._event_combo(event)

        command = self._destination_by_combo.get((mods, vk))
        if command is not None:
            self._move_current(command)
            return "break"

        keysym = (event.keysym or "").lower()
        if mods:
            if mods == frozenset({"ctrl"}) and keysym == "z":
                self._undo_last_move()
                return "break"
            return None

        if keysym == "escape":
            self._close()
            return "break"
        if keysym in ("left", "prior"):
            self.previous_image()
            return "break"
        if keysym in ("right", "next", "space"):
            self.next_image()
            return "break"
        if keysym == "home":
            self._select_index(0)
            return "break"
        if keysym == "end":
            self._select_index(len(self._images) - 1)
            return "break"
        if keysym in ("delete", "backspace"):
            self.next_image()
            return "break"
        if keysym == "o":
            self._open_original()
            return "break"
        return None

    # -- helpers --------------------------------------------------------

    def _set_status(self, text: str) -> None:
        try:
            self.status_label.configure(text=text)
        except Exception:
            pass

    def _center(self) -> None:
        try:
            self.update_idletasks()
            parent = self.app.root
            width = max(900, self.winfo_width())
            height = max(640, self.winfo_height())
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            x = max(0, min(x, screen_w - width))
            y = max(0, min(y, screen_h - height))
            self.geometry(
                str(width)
                + "x"
                + str(height)
                + "+"
                + str(x)
                + "+"
                + str(y)
            )
        except Exception:
            pass

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._thumb_job is not None:
            try:
                self.after_cancel(self._thumb_job)
            except Exception:
                pass
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
        self.app._image_sorter = None
        try:
            self.destroy()
        except Exception:
            pass
