#!/usr/bin/env python3
"""
SF3000 Game Manager
Browse and manage games and emulators on your SF3000 SD card.

Requirements: Python 3.8+, no external packages needed.
Optional: Install tkinterdnd2 to enable drag-and-drop import.
Note: The SD card must be accessible as a drive letter.
      Use Ext2Fsd, WSL, or DiskInternals Linux Reader to mount ext4 first.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import string
import subprocess
import tempfile
import threading
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    TKDND_AVAILABLE = True
    TkBase = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    TKDND_AVAILABLE = False
    TkBase = tk.Tk


# ---------------------------------------------------------------------------
# ROM file extensions grouped by system
# ---------------------------------------------------------------------------
SYSTEM_EXTENSIONS = {
    "3DO": [".iso", ".bin", ".cue"],
    "Amstrad CPC": [".dsk", ".cpr", ".zip"],
    "Arcade / MAME": [".zip", ".7z"],
    "Atari 2600": [".a26"],
    "Atari 5200": [".a52"],
    "Atari 7800": [".a78"],
    "Atari 800/XL/XE": [".atr", ".xex", ".xfd", ".cas"],
    "Atari Jaguar": [".j64", ".jag"],
    "Atari Lynx": [".lnx"],
    "Atari ST": [".st", ".msa", ".stx"],
    "Amiga": [".adf", ".hdf"],
    "BBC Micro": [".ssd", ".dsd", ".uef"],
    "Commodore 64": [".d64", ".t64", ".prg", ".crt"],
    "ColecoVision": [".col"],
    "DOS": [".exe", ".com"],
    "Dreamcast": [".cdi", ".gdi", ".chd"],
    "FDS": [".fds"],
    "Game & Watch": [".mgw"],
    "Game Boy": [".gb", ".gbc"],
    "GBA": [".gba"],
    "Game Gear": [".gg"],
    "GameCube": [".iso", ".gcm"],
    "Intellivision": [".int"],
    "Mega Duck": [".bin"],
    "MSX": [".rom", ".mx1", ".mx2"],
    "N64": [".n64", ".z64", ".v64"],
    "NDS": [".nds"],
    "NES": [".nes"],
    "Neo Geo": [".zip"],
    "Neo Geo Pocket": [".ngp", ".ngc"],
    "Odyssey2 / Videopac": [".bin"],
    "PC Engine": [".pce", ".ccd"],
    "PC Engine CD": [".cue", ".iso", ".chd"],
    "PICO-8": [".p8", ".png"],
    "Pokemon Mini": [".min"],
    "PSP": [".iso", ".cso", ".pbp"],
    "PlayStation": [".bin", ".cue", ".img", ".iso", ".pbp", ".chd"],
    "PlayStation 2": [".iso", ".bin", ".chd"],
    "Saturn": [".cue", ".bin", ".iso", ".chd", ".mdf"],
    "ScummVM": [".scummvm"],
    "Sega 32X": [".32x"],
    "Sega CD": [".bin", ".cue", ".chd", ".iso"],
    "Sega Genesis": [".md", ".gen"],
    "Sega Master System": [".sms"],
    "Sega Naomi": [".zip", ".7z"],
    "Sega Pico": [".md", ".bin"],
    "SG-1000": [".sg", ".sc"],
    "SNES": [".smc", ".sfc", ".fig"],
    "Supervision": [".sv"],
    "TurboGrafx-16": [".pce"],
    "Vectrex": [".vec", ".bin"],
    "Virtual Boy": [".vb"],
    "Wii": [".iso", ".wbfs"],
    "Wonderswan": [".ws", ".wsc"],
    "ZX Spectrum": [".z80", ".tap", ".tzx", ".sna"],
    "ZX81": [".p", ".tzx"],
}

SYSTEM_FOLDER_ALIASES = {
    "arcade": "Arcade / MAME",
    "mame": "Arcade / MAME",
    "atari800": "Atari 800/XL/XE",
    "atari xl xe": "Atari 800/XL/XE",
    "gb": "Game Boy",
    "gbc": "Game Boy",
    "megadrive": "Sega Genesis",
    "mega drive": "Sega Genesis",
    "genesis": "Sega Genesis",
    "mastersystem": "Sega Master System",
    "master system": "Sega Master System",
    "sms": "Sega Master System",
    "tg16": "TurboGrafx-16",
    "turbografx16": "TurboGrafx-16",
    "turbografx": "TurboGrafx-16",
    "pce": "PC Engine",
    "pcengine": "PC Engine",
    "pcenginecd": "PC Engine CD",
    "segacd": "Sega CD",
    "psx": "PlayStation",
    "ps1": "PlayStation",
    "ps2": "PlayStation 2",
    "videopac": "Odyssey2 / Videopac",
    "odyssey2": "Odyssey2 / Videopac",
}

COMMON_SYSTEM_FOLDERS = [
    "Arcade",
    "NES",
    "SNES",
    "Game Boy",
    "GBA",
    "Genesis",
    "Game Gear",
    "N64",
    "PlayStation",
    "Neo Geo",
]

EMU_ROOT_CREATE_OPTIONS = ("Emulators", "cores", "retroarch/cores")

# Emulator file extensions the SF3000 uses
EMULATOR_EXTENSIONS = [".so", ".sh", ".elf", ".bin", ".pak"]

# Candidate folder names for emulators on the device
EMULATOR_FOLDER_CANDIDATES = (
    "Emulators",
    "emulators",
    "EMULATORS",
    "cores",
    "Cores",
    "CORES",
    "retroarch/cores",
    "RetroArch/cores",
)

APP_STATE_FILE = Path.home() / ".sf3000_game_manager.json"
LOW_SPACE_WARNING_BYTES = 256 * 1024 * 1024


def _system_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


SYSTEM_EXTENSION_LOOKUP: Dict[str, Tuple[str, ...]] = {}
for system_name, extensions in SYSTEM_EXTENSIONS.items():
    SYSTEM_EXTENSION_LOOKUP[_system_key(system_name)] = tuple(ext.lower() for ext in extensions)
for alias, system_name in SYSTEM_FOLDER_ALIASES.items():
    SYSTEM_EXTENSION_LOOKUP[_system_key(alias)] = tuple(
        ext.lower() for ext in SYSTEM_EXTENSIONS[system_name]
    )

ALL_ROM_EXTENSIONS = tuple(sorted({ext.lower() for exts in SYSTEM_EXTENSIONS.values() for ext in exts}))
ALL_ROM_EXTENSION_SET = set(ALL_ROM_EXTENSIONS)
EMULATOR_EXTENSION_SET = {ext.lower() for ext in EMULATOR_EXTENSIONS}


@dataclass
class FileRecord:
    path: Path
    display_name: str
    raw_name: str
    size: int
    modified_text: str
    modified_ts: float
    file_type: str
    parent_name: str
    warning: str = ""


@dataclass
class TransferItem:
    source: Path
    destination: Path
    size: int
    overwrite: bool


@dataclass
class TransferPlan:
    items: List[TransferItem]
    skipped_identical: List[str]
    skipped_same_path: List[str]
    overwrites: List[str]
    total_bytes: int
    required_bytes: int


# ---------------------------------------------------------------------------
# Windows recycle-bin helper
# ---------------------------------------------------------------------------
FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def send_to_recycle_bin(path: Path):
    target = str(path.resolve(strict=False)) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = target
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI

    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if result != 0 or op.fAnyOperationsAborted:
        raise OSError(f"Could not move '{path.name}' to the Recycle Bin.")


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def format_size(value: int) -> str:
    n = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def get_windows_drives() -> List[str]:
    drives: List[str] = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:\\"
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                if drive_type in (2, 3):
                    drives.append(drive)
            bitmask >>= 1
    except Exception:
        pass
    return drives


def safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def safe_stat(path: Path) -> Optional[os.stat_result]:
    try:
        return path.stat()
    except OSError:
        return None


def list_child_dirs(folder: Path) -> List[Path]:
    try:
        return sorted([d for d in folder.iterdir() if d.is_dir()], key=lambda p: p.name.lower())
    except Exception:
        return []


def list_child_files(folder: Path) -> List[Path]:
    try:
        return sorted([f for f in folder.iterdir() if f.is_file()], key=lambda p: p.name.lower())
    except Exception:
        return []


def find_roms_root(root: Path) -> Path:
    for candidate in ("Roms", "roms", "ROMS", "ROMs"):
        folder = root / candidate
        if safe_is_dir(folder):
            return folder
    return root


def find_emulators_root(root: Path) -> Optional[Path]:
    for candidate in EMULATOR_FOLDER_CANDIDATES:
        folder = root / candidate
        if safe_is_dir(folder):
            return folder
    return None


def get_system_extensions(system_name: str) -> Optional[Tuple[str, ...]]:
    return SYSTEM_EXTENSION_LOOKUP.get(_system_key(system_name))


def is_rom_file(path: Path) -> bool:
    return path.suffix.casefold() in ALL_ROM_EXTENSION_SET


def is_emulator_file(path: Path) -> bool:
    return path.suffix.casefold() in EMULATOR_EXTENSION_SET


def build_file_record(
    path: Path,
    display_name: str,
    parent_name: str,
    warning: str = "",
) -> FileRecord:
    stat = safe_stat(path)
    size = stat.st_size if stat else 0
    modified_ts = stat.st_mtime if stat else 0.0
    modified_text = (
        datetime.fromtimestamp(modified_ts).strftime("%Y-%m-%d  %H:%M")
        if modified_ts
        else ""
    )
    return FileRecord(
        path=path,
        display_name=display_name,
        raw_name=path.name,
        size=size,
        modified_text=modified_text,
        modified_ts=modified_ts,
        file_type=path.suffix.lstrip(".").upper() or "--",
        parent_name=parent_name,
        warning=warning,
    )


def build_game_warning(path: Path, system_name: str) -> str:
    suffix = path.suffix.casefold()
    allowed = get_system_extensions(system_name)
    if allowed is None:
        if suffix in ALL_ROM_EXTENSION_SET:
            return "Unknown system folder"
        return "Unsupported ROM file"
    if suffix in allowed:
        return ""
    if suffix in ALL_ROM_EXTENSION_SET:
        return f"Not typical for {system_name}"
    return "Unsupported ROM file"


def build_emulator_warning(path: Path) -> str:
    if is_emulator_file(path):
        return ""
    return "Unsupported emulator file"


def fuzzy_contains(text: str, query: str) -> bool:
    haystack = text.casefold()
    needle = query.casefold()
    if not needle:
        return True
    if needle in haystack:
        return True
    it = iter(haystack)
    return all(char in it for char in needle)


def record_matches_query(record: FileRecord, query: str) -> bool:
    if not query:
        return True

    search_text = " ".join(
        [
            record.display_name,
            record.raw_name,
            record.file_type,
            record.parent_name,
            record.warning,
            str(record.path),
        ]
    )

    tokens = [token for token in query.split() if token]
    for token in tokens:
        token_cf = token.casefold()
        if token_cf.startswith("."):
            if record.path.suffix.casefold() != token_cf:
                return False
            continue
        if not fuzzy_contains(search_text, token_cf):
            return False
    return True


def clean_filename(name: str) -> str:
    path = Path(name)
    suffix = "".join(path.suffixes) if path.suffixes else ""
    stem = name[: len(name) - len(suffix)] if suffix else name
    cleaned = stem.replace("_", " ").replace(".", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_.")
    if not cleaned:
        cleaned = stem.strip() or "Renamed File"
    return f"{cleaned}{suffix}"


def sanitize_windows_name(name: str) -> str:
    safe_name = "".join(char for char in name if char not in r'\/:*?"<>|')
    return safe_name.strip().rstrip(".")


def format_name_list(names: Sequence[str], limit: int = 10) -> str:
    body = "\n".join(names[:limit])
    if len(names) > limit:
        body += f"\n...and {len(names) - limit} more"
    return body


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except Exception:
        return str(left).casefold() == str(right).casefold()


def same_drive(left: Path, right: Path) -> bool:
    return left.anchor.casefold() == right.anchor.casefold()


def files_are_identical(left: Path, right: Path, chunk_size: int = 1024 * 1024) -> bool:
    left_stat = safe_stat(left)
    right_stat = safe_stat(right)
    if left_stat is None or right_stat is None:
        return False
    if left_stat.st_size != right_stat.st_size:
        return False

    try:
        with left.open("rb") as left_file, right.open("rb") as right_file:
            while True:
                left_chunk = left_file.read(chunk_size)
                right_chunk = right_file.read(chunk_size)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    except OSError:
        return False


def create_temp_destination(dest_folder: Path, suffix: str = "") -> Path:
    fd, temp_name = tempfile.mkstemp(
        prefix=".__sf3000_tmp_",
        suffix=suffix,
        dir=str(dest_folder),
    )
    os.close(fd)
    return Path(temp_name)


def _safe_destroy(widget):
    try:
        widget.destroy()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Progress dialog
# ---------------------------------------------------------------------------
class ProgressDialog(tk.Toplevel):
    def __init__(self, parent, title: str = "Processing Files"):
        super().__init__(parent)
        self.title(title)
        self.geometry("460x140")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cancelled = False
        self._filename_var = tk.StringVar(value="Preparing...")
        self._count_var = tk.StringVar(value="")

        ttk.Label(self, textvariable=self._filename_var, wraplength=430).pack(
            pady=(15, 4), padx=12, anchor="w"
        )
        self._bar = ttk.Progressbar(self, length=430, mode="determinate")
        self._bar.pack(pady=4, padx=12)
        ttk.Label(self, textvariable=self._count_var).pack()
        ttk.Button(self, text="Cancel", command=self._on_close).pack(pady=8)

    def update_progress(self, value: int, maximum: int, filepath: str, verb: str):
        if self.cancelled or not self.winfo_exists():
            return
        self._bar["maximum"] = maximum
        self._bar["value"] = value
        self._filename_var.set(f"{verb}: {Path(filepath).name}")
        self._count_var.set(f"{value} of {maximum}")
        self.update_idletasks()

    def _on_close(self):
        self.cancelled = True
        if self.winfo_exists():
            self.destroy()


class ToolTip:
    def __init__(self, widget, text, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _resolve_text(self) -> str:
        value = self.text() if callable(self.text) else self.text
        return value.strip() if isinstance(value, str) else ""

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        text = self._resolve_text()
        if not text or self._tip or not self.widget.winfo_exists():
            return

        self._tip = tk.Toplevel(self.widget)
        self._tip.withdraw()
        self._tip.overrideredirect(True)
        self._tip.attributes("-topmost", True)

        frame = tk.Frame(
            self._tip,
            bg="#172033",
            bd=1,
            relief="solid",
            highlightthickness=0,
        )
        frame.pack()
        tk.Label(
            frame,
            text=text,
            bg="#172033",
            fg="#f8fafc",
            justify="left",
            padx=8,
            pady=6,
            wraplength=320,
            font=("Segoe UI", 9),
        ).pack()

        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._tip.geometry(f"+{x}+{y}")
        self._tip.deiconify()

    def _hide(self, _event=None):
        self._cancel()
        if self._tip and self._tip.winfo_exists():
            self._tip.destroy()
        self._tip = None


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------
class SF3000GameManager(TkBase):
    def __init__(self):
        super().__init__()
        self.title("SF3000 Game Manager")
        self.geometry("1180x720")
        self.minsize(900, 560)
        self.protocol("WM_DELETE_WINDOW", self._on_close_app)

        self._loaded_state = self._load_settings()
        saved_geometry = self._loaded_state.get("geometry")
        if isinstance(saved_geometry, str) and saved_geometry:
            try:
                self.geometry(saved_geometry)
            except Exception:
                pass

        self._sd_path = tk.StringVar(value=self._loaded_state.get("sd_path", ""))
        self._status = tk.StringVar(value="Select your SF3000 SD card drive to get started.")
        self._copy_mode = tk.StringVar(value=self._loaded_state.get("copy_mode", "copy"))
        self._delete_to_recycle = tk.BooleanVar(
            value=bool(self._loaded_state.get("delete_to_recycle", True))
        )
        self._game_filter_var = tk.StringVar(value=self._loaded_state.get("game_filter", ""))
        self._emu_filter_var = tk.StringVar(value=self._loaded_state.get("emu_filter", ""))

        self._roms_root: Optional[Path] = None
        self._emu_root: Optional[Path] = None

        self._game_records_by_key: Dict[str, List[FileRecord]] = {}
        self._emu_records_by_key: Dict[str, List[FileRecord]] = {}
        self._game_visible_map: Dict[str, FileRecord] = {}
        self._emu_visible_map: Dict[str, FileRecord] = {}

        self._current_game_key = "__all__"
        self._current_emu_key = "__emu_all__"
        self._current_game_label = ""
        self._current_emu_label = ""
        self._current_game_records: List[FileRecord] = []
        self._current_emu_records: List[FileRecord] = []

        self._game_sort_column = "name"
        self._game_sort_reverse = False
        self._emu_sort_column = "name"
        self._emu_sort_reverse = False

        self._pending_system_selection = self._loaded_state.get("system_selection", "__all__")
        self._pending_emu_selection = self._loaded_state.get("emu_selection", "__emu_all__")
        self._pending_tab_index = int(self._loaded_state.get("tab_index", 0))
        self._pending_game_paths: List[str] = []
        self._pending_emu_paths: List[str] = []

        self._scan_generation = 0
        self._scan_in_progress = False
        self._next_status_message: Optional[str] = None
        self._is_closing = False
        self._toast_window: Optional[tk.Toplevel] = None
        self._toast_after_id = None
        self._tooltips: List[ToolTip] = []

        self._configure_style()
        self._build_ui()
        self._build_context_menus()
        self._register_drop_targets()
        self._bind_shortcuts()
        self._install_tooltips()
        self._configure_tree_appearance()

        self._game_filter_var.trace_add("write", self._on_game_filter_change)
        self._emu_filter_var.trace_add("write", self._on_emu_filter_change)

        self._refresh_drive_choices()
        self._notebook.select(min(self._pending_tab_index, self._notebook.index("end") - 1))

        if self._sd_path.get().strip() and safe_exists(Path(self._sd_path.get().strip())):
            self._scan_all()
        else:
            self._auto_detect_drive()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _configure_style(self):
        self.option_add("*tearOff", False)
        style = ttk.Style(self)
        theme_names = style.theme_names()
        if "vista" in theme_names:
            style.theme_use("vista")
        elif "clam" in theme_names:
            style.theme_use("clam")

        self.configure(background="#f4f7fb")
        style.configure(".", font=("Segoe UI", 9))
        style.configure("TFrame", background="#f4f7fb")
        style.configure("TLabelframe", background="#f4f7fb", padding=8)
        style.configure("TLabelframe.Label", font=("Segoe UI Semibold", 9), foreground="#1e293b")
        style.configure("TLabel", background="#f4f7fb", foreground="#0f172a")
        style.configure("Hint.TLabel", foreground="#64748b")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 10), foreground="#0f172a")
        style.configure("TButton", padding=(10, 5))
        style.configure("Treeview", rowheight=26, fieldbackground="#ffffff", background="#ffffff")
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))
        style.configure("TNotebook", background="#f4f7fb", tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", padding=(14, 7))
        style.map(
            "Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#0f172a")],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#ffffff")],
            foreground=[("selected", "#0f172a")],
        )

    def _configure_tree_appearance(self):
        for tree in (self._game_tree, self._emu_tree):
            tree.tag_configure("row_even", background="#ffffff")
            tree.tag_configure("row_odd", background="#f8fbff")
            tree.tag_configure("warning", foreground="#9a3412")

    def _bind_shortcuts(self):
        bindings = {
            "<Control-r>": self._scan_all,
            "<F5>": self._scan_all,
            "<Control-o>": self._open_in_explorer,
            "<Control-i>": self._shortcut_import,
            "<Control-f>": self._focus_active_filter,
            "<Escape>": self._shortcut_escape,
            "<F2>": self._shortcut_rename,
            "<Control-l>": self._shortcut_clean_names,
            "<Control-d>": self._shortcut_validate,
            "<Control-Shift-N>": self._shortcut_new_folder,
            "<F1>": self._show_shortcuts_dialog,
            "<Alt-1>": lambda: self._switch_tab(0),
            "<Alt-2>": lambda: self._switch_tab(1),
            "<Control-Key-1>": lambda: self._switch_tab(0),
            "<Control-Key-2>": lambda: self._switch_tab(1),
            "<Control-a>": self._shortcut_select_all,
        }
        for sequence, handler in bindings.items():
            self.bind_all(sequence, lambda event, fn=handler: self._run_shortcut(fn))

        self.bind("<Configure>", lambda _e: self._reposition_toast(), add="+")
        self._game_tree.bind("<Return>", lambda _e: self._reveal_selected_file(self._game_tree))
        self._emu_tree.bind("<Return>", lambda _e: self._reveal_selected_file(self._emu_tree))
        self._sys_tree.bind("<Return>", lambda _e: self._open_selected_system_folder())
        self._emu_folder_tree.bind("<Return>", lambda _e: self._open_selected_emu_folder())

    def _install_tooltips(self):
        hint = (
            "Drop files here to import them."
            if TKDND_AVAILABLE
            else "Drag-and-drop is available if you install 'tkinterdnd2'."
        )

        pairs = [
            (self._drive_combo, "Choose the SD-card root or mounted path. Press Enter to scan."),
            (self._browse_button, "Browse for the SF3000 SD-card root folder."),
            (self._scan_button, "Rescan the selected device. Shortcut: Ctrl+R or F5."),
            (self._copy_mode_combo, "Choose whether imported files are copied or moved."),
            (
                self._recycle_toggle,
                "When enabled, deletes and overwritten files are moved to the Recycle Bin first.",
            ),
            (self._open_button, "Open the current selection in Explorer. Shortcut: Ctrl+O."),
            (self._help_button, "Show keyboard shortcuts and workflow tips. Shortcut: F1."),
            (self._game_add_button, "Add game files to the selected system folder. Shortcut: Ctrl+I."),
            (self._game_delete_button, "Delete the selected game files. Shortcut: Delete."),
            (self._game_rename_button, "Rename the selected game file. Shortcut: F2."),
            (self._game_clean_button, "Clean selected game file names. Shortcut: Ctrl+L."),
            (self._game_validate_button, "Validate the selected rows or current filtered game view. Shortcut: Ctrl+D."),
            (self._game_new_folder_button, "Create a new system folder. Shortcut: Ctrl+Shift+N."),
            (self._game_common_button, "Create a starter set of common system folders."),
            (self._game_filter_entry, "Filter by title, filename, extension, folder, or warning. Shortcut: Ctrl+F."),
            (self._game_filter_clear_button, "Clear the Games filter. Shortcut: Escape."),
            (self._emu_add_button, "Add emulator files to the selected emulator folder. Shortcut: Ctrl+I."),
            (self._emu_delete_button, "Delete the selected emulator files. Shortcut: Delete."),
            (self._emu_rename_button, "Rename the selected emulator file. Shortcut: F2."),
            (self._emu_clean_button, "Clean selected emulator file names. Shortcut: Ctrl+L."),
            (self._emu_validate_button, "Validate the selected rows or current filtered emulator view. Shortcut: Ctrl+D."),
            (self._emu_new_folder_button, "Create an emulator folder or emulator root. Shortcut: Ctrl+Shift+N."),
            (self._emu_filter_entry, "Filter by filename, extension, folder, or warning. Shortcut: Ctrl+F."),
            (self._emu_filter_clear_button, "Clear the Emulators filter. Shortcut: Escape."),
            (self._sys_tree, "Pick a system folder. Press Enter to open it in Explorer."),
            (self._emu_folder_tree, "Pick an emulator folder. Press Enter to open it in Explorer."),
            (self._game_tree, f"Double-click or press Enter to reveal a file. Right-click for actions. {hint}"),
            (self._emu_tree, f"Double-click or press Enter to reveal a file. Right-click for actions. {hint}"),
        ]

        self._tooltips = [ToolTip(widget, text) for widget, text in pairs]

    def _shortcuts_enabled(self) -> bool:
        grabbed = self.grab_current()
        return not self._is_closing and grabbed in (None, self)

    def _run_shortcut(self, handler):
        if not self._shortcuts_enabled():
            return "break"
        handler()
        return "break"

    def _switch_tab(self, index: int):
        self._notebook.select(index)
        self._refresh_active_status()

    def _active_file_tree(self):
        return self._game_tree if self._notebook.index(self._notebook.select()) == 0 else self._emu_tree

    def _active_filter_entry(self):
        return self._game_filter_entry if self._notebook.index(self._notebook.select()) == 0 else self._emu_filter_entry

    def _focus_active_filter(self):
        entry = self._active_filter_entry()
        entry.focus_set()
        entry.select_range(0, "end")
        entry.icursor("end")

    def _shortcut_import(self):
        if self._notebook.index(self._notebook.select()) == 0:
            self._add_games()
        else:
            self._add_emulators()

    def _shortcut_new_folder(self):
        if self._notebook.index(self._notebook.select()) == 0:
            self._new_game_folder()
        else:
            self._new_emu_folder()

    def _shortcut_rename(self):
        if self._notebook.index(self._notebook.select()) == 0:
            self._rename_selected_games()
        else:
            self._rename_selected_emulators()

    def _shortcut_clean_names(self):
        if self._notebook.index(self._notebook.select()) == 0:
            self._clean_selected_game_names()
        else:
            self._clean_selected_emulator_names()

    def _shortcut_validate(self):
        if self._notebook.index(self._notebook.select()) == 0:
            self._validate_selected_games()
        else:
            self._validate_selected_emulators()

    def _shortcut_escape(self):
        if self._toast_window and self._toast_window.winfo_exists():
            self._hide_toast()
            return
        if self._notebook.index(self._notebook.select()) == 0 and self._game_filter_var.get():
            self._game_filter_var.set("")
            return
        if self._notebook.index(self._notebook.select()) == 1 and self._emu_filter_var.get():
            self._emu_filter_var.set("")

    def _shortcut_select_all(self):
        focus_widget = self.focus_get()
        if isinstance(focus_widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            try:
                focus_widget.select_range(0, "end")
                focus_widget.icursor("end")
            except Exception:
                pass
            return

        tree = self._active_file_tree()
        children = tree.get_children("")
        if children:
            tree.selection_set(children)
            tree.focus(children[0])
            tree.see(children[0])

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x", side="top")

        ttk.Label(toolbar, text="SF3000 SD Card", style="Title.TLabel").pack(side="left", padx=(0, 10))
        ttk.Label(toolbar, text="Drive / Path:").pack(side="left")
        self._drive_combo = ttk.Combobox(toolbar, textvariable=self._sd_path, width=18)
        self._drive_combo.pack(side="left", padx=(4, 0))
        self._drive_combo.bind("<<ComboboxSelected>>", lambda _e: self._scan_all())
        self._drive_combo.bind("<Return>", lambda _e: self._scan_all())

        self._browse_button = ttk.Button(toolbar, text="Browse...", command=self._browse_path)
        self._browse_button.pack(side="left", padx=4)
        self._scan_button = ttk.Button(toolbar, text="Scan", command=self._scan_all)
        self._scan_button.pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(toolbar, text="Import Mode:").pack(side="left")
        self._copy_mode_combo = ttk.Combobox(
            toolbar,
            textvariable=self._copy_mode,
            values=("copy", "move"),
            state="readonly",
            width=8,
        )
        self._copy_mode_combo.pack(side="left", padx=(4, 0))
        self._recycle_toggle = ttk.Checkbutton(
            toolbar,
            text="Recycle Deletes/Overwrites",
            variable=self._delete_to_recycle,
        )
        self._recycle_toggle.pack(side="left", padx=10)

        self._help_button = ttk.Button(toolbar, text="Shortcuts", command=self._show_shortcuts_dialog)
        self._help_button.pack(side="right", padx=2)
        self._open_button = ttk.Button(toolbar, text="Open in Explorer", command=self._open_in_explorer)
        self._open_button.pack(side="right", padx=2)

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=6, pady=(2, 0))
        self._notebook.bind("<<NotebookTabChanged>>", lambda _e: self._refresh_active_status())

        games_frame = ttk.Frame(self._notebook)
        emulators_frame = ttk.Frame(self._notebook)
        self._notebook.add(games_frame, text="  Games  ")
        self._notebook.add(emulators_frame, text="  Emulators  ")

        self._build_games_tab(games_frame)
        self._build_emulators_tab(emulators_frame)

        storage_frame = ttk.Frame(self, padding=(6, 2))
        storage_frame.pack(fill="x", side="bottom")
        self._storage_label = ttk.Label(storage_frame, text="")
        self._storage_label.pack(side="left")
        self._storage_bar = ttk.Progressbar(storage_frame, length=220, maximum=100, mode="determinate")
        self._storage_bar.pack(side="right", padx=(0, 4))
        ttk.Label(storage_frame, text="Storage:").pack(side="right")

        status_frame = ttk.Frame(self, relief="sunken", padding=(6, 2))
        status_frame.pack(fill="x", side="bottom")
        ttk.Label(status_frame, textvariable=self._status).pack(side="left")
        self._shortcut_hint_label = ttk.Label(
            status_frame,
            text=(
                "F1 Help  |  Ctrl+I Import  |  Ctrl+F Filter  |  F2 Rename"
                + ("  |  Drop files to import" if TKDND_AVAILABLE else "")
            ),
            style="Hint.TLabel",
        )
        self._shortcut_hint_label.pack(side="right", padx=(0, 10))
        self._scan_progress = ttk.Progressbar(status_frame, mode="indeterminate", length=120)
        self._scan_progress.pack(side="right")

    def _build_games_tab(self, parent):
        actions = ttk.Frame(parent, padding=(4, 4))
        actions.pack(fill="x", side="top")

        self._game_add_button = ttk.Button(actions, text="+ Add Games", command=self._add_games)
        self._game_add_button.pack(side="left", padx=2)
        self._game_delete_button = ttk.Button(actions, text="Delete Selected", command=self._delete_selected_games)
        self._game_delete_button.pack(
            side="left", padx=2
        )
        self._game_rename_button = ttk.Button(actions, text="Rename Selected", command=self._rename_selected_games)
        self._game_rename_button.pack(
            side="left", padx=2
        )
        self._game_clean_button = ttk.Button(actions, text="Clean Names", command=self._clean_selected_game_names)
        self._game_clean_button.pack(
            side="left", padx=2
        )
        self._game_validate_button = ttk.Button(actions, text="Validate", command=self._validate_selected_games)
        self._game_validate_button.pack(
            side="left", padx=2
        )
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        self._game_new_folder_button = ttk.Button(actions, text="New System Folder", command=self._new_game_folder)
        self._game_new_folder_button.pack(
            side="left", padx=2
        )
        self._game_common_button = ttk.Button(
            actions,
            text="Create Common Folders",
            command=self._create_common_system_folders,
        )
        self._game_common_button.pack(
            side="left", padx=2
        )
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(actions, text="Filter:").pack(side="left")
        self._game_filter_entry = ttk.Entry(actions, textvariable=self._game_filter_var, width=28)
        self._game_filter_entry.pack(
            side="left", padx=(4, 2)
        )
        self._game_filter_clear_button = ttk.Button(actions, text="Clear", command=lambda: self._game_filter_var.set(""))
        self._game_filter_clear_button.pack(
            side="left", padx=2
        )

        pane = ttk.PanedWindow(parent, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=4, pady=4)

        systems_frame = ttk.LabelFrame(pane, text="Systems", padding=2)
        pane.add(systems_frame, weight=1)

        self._sys_tree = ttk.Treeview(systems_frame, show="tree", selectmode="browse")
        sys_scroll = ttk.Scrollbar(systems_frame, orient="vertical", command=self._sys_tree.yview)
        self._sys_tree.configure(yscrollcommand=sys_scroll.set)
        sys_scroll.pack(side="right", fill="y")
        self._sys_tree.pack(fill="both", expand=True)
        self._sys_tree.bind("<<TreeviewSelect>>", self._on_system_select)
        self._sys_tree.bind(
            "<Button-3>",
            lambda event: self._post_tree_menu(event, self._sys_tree, self._systems_menu),
        )

        games_frame = ttk.LabelFrame(pane, text="Games", padding=2)
        pane.add(games_frame, weight=4)

        columns = ("name", "file", "size", "type", "modified", "folder", "warning")
        self._game_tree = ttk.Treeview(
            games_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self._game_tree.heading("name", text="Title", command=lambda: self._sort_games("name"))
        self._game_tree.heading("file", text="File Name", command=lambda: self._sort_games("file"))
        self._game_tree.heading("size", text="Size", command=lambda: self._sort_games("size"))
        self._game_tree.heading("type", text="Type", command=lambda: self._sort_games("type"))
        self._game_tree.heading("modified", text="Modified", command=lambda: self._sort_games("modified"))
        self._game_tree.heading("folder", text="Folder", command=lambda: self._sort_games("folder"))
        self._game_tree.heading("warning", text="Warning", command=lambda: self._sort_games("warning"))

        self._game_tree.column("name", width=220, minwidth=120)
        self._game_tree.column("file", width=220, minwidth=120)
        self._game_tree.column("size", width=90, anchor="e", minwidth=60)
        self._game_tree.column("type", width=70, anchor="center", minwidth=50)
        self._game_tree.column("modified", width=140, minwidth=100)
        self._game_tree.column("folder", width=110, minwidth=80)
        self._game_tree.column("warning", width=220, minwidth=100)

        game_scroll_y = ttk.Scrollbar(games_frame, orient="vertical", command=self._game_tree.yview)
        game_scroll_x = ttk.Scrollbar(games_frame, orient="horizontal", command=self._game_tree.xview)
        self._game_tree.configure(yscrollcommand=game_scroll_y.set, xscrollcommand=game_scroll_x.set)
        game_scroll_y.pack(side="right", fill="y")
        game_scroll_x.pack(side="bottom", fill="x")
        self._game_tree.pack(fill="both", expand=True)

        self._game_tree.bind("<Delete>", lambda _e: self._delete_selected_games())
        self._game_tree.bind("<Double-1>", lambda _e: self._reveal_selected_file(self._game_tree))
        self._game_tree.bind(
            "<Button-3>",
            lambda event: self._post_tree_menu(event, self._game_tree, self._games_menu),
        )

    def _build_emulators_tab(self, parent):
        actions = ttk.Frame(parent, padding=(4, 4))
        actions.pack(fill="x", side="top")

        self._emu_add_button = ttk.Button(actions, text="+ Add Emulator", command=self._add_emulators)
        self._emu_add_button.pack(
            side="left", padx=2
        )
        self._emu_delete_button = ttk.Button(actions, text="Delete Selected", command=self._delete_selected_emulators)
        self._emu_delete_button.pack(
            side="left", padx=2
        )
        self._emu_rename_button = ttk.Button(actions, text="Rename Selected", command=self._rename_selected_emulators)
        self._emu_rename_button.pack(
            side="left", padx=2
        )
        self._emu_clean_button = ttk.Button(actions, text="Clean Names", command=self._clean_selected_emulator_names)
        self._emu_clean_button.pack(
            side="left", padx=2
        )
        self._emu_validate_button = ttk.Button(actions, text="Validate", command=self._validate_selected_emulators)
        self._emu_validate_button.pack(
            side="left", padx=2
        )
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        self._emu_new_folder_button = ttk.Button(actions, text="New Emulator Folder", command=self._new_emu_folder)
        self._emu_new_folder_button.pack(
            side="left", padx=2
        )
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        self._emu_path_label = ttk.Label(actions, text="Emulators folder: (not found)", foreground="gray")
        self._emu_path_label.pack(side="left", padx=4)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(actions, text="Filter:").pack(side="left")
        self._emu_filter_entry = ttk.Entry(actions, textvariable=self._emu_filter_var, width=28)
        self._emu_filter_entry.pack(
            side="left", padx=(4, 2)
        )
        self._emu_filter_clear_button = ttk.Button(actions, text="Clear", command=lambda: self._emu_filter_var.set(""))
        self._emu_filter_clear_button.pack(
            side="left", padx=2
        )

        pane = ttk.PanedWindow(parent, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=4, pady=4)

        folders_frame = ttk.LabelFrame(pane, text="Emulator Folders", padding=2)
        pane.add(folders_frame, weight=1)

        self._emu_folder_tree = ttk.Treeview(folders_frame, show="tree", selectmode="browse")
        emu_scroll = ttk.Scrollbar(
            folders_frame, orient="vertical", command=self._emu_folder_tree.yview
        )
        self._emu_folder_tree.configure(yscrollcommand=emu_scroll.set)
        emu_scroll.pack(side="right", fill="y")
        self._emu_folder_tree.pack(fill="both", expand=True)
        self._emu_folder_tree.bind("<<TreeviewSelect>>", self._on_emu_folder_select)
        self._emu_folder_tree.bind(
            "<Button-3>",
            lambda event: self._post_tree_menu(event, self._emu_folder_tree, self._emu_folders_menu),
        )

        files_frame = ttk.LabelFrame(pane, text="Emulator Files", padding=2)
        pane.add(files_frame, weight=4)

        columns = ("name", "size", "type", "modified", "folder", "warning")
        self._emu_tree = ttk.Treeview(
            files_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self._emu_tree.heading("name", text="File Name", command=lambda: self._sort_emus("name"))
        self._emu_tree.heading("size", text="Size", command=lambda: self._sort_emus("size"))
        self._emu_tree.heading("type", text="Type", command=lambda: self._sort_emus("type"))
        self._emu_tree.heading(
            "modified",
            text="Modified",
            command=lambda: self._sort_emus("modified"),
        )
        self._emu_tree.heading("folder", text="Folder", command=lambda: self._sort_emus("folder"))
        self._emu_tree.heading("warning", text="Warning", command=lambda: self._sort_emus("warning"))

        self._emu_tree.column("name", width=300, minwidth=120)
        self._emu_tree.column("size", width=90, anchor="e", minwidth=60)
        self._emu_tree.column("type", width=70, anchor="center", minwidth=50)
        self._emu_tree.column("modified", width=140, minwidth=100)
        self._emu_tree.column("folder", width=110, minwidth=80)
        self._emu_tree.column("warning", width=240, minwidth=100)

        emu_files_scroll_y = ttk.Scrollbar(files_frame, orient="vertical", command=self._emu_tree.yview)
        emu_files_scroll_x = ttk.Scrollbar(files_frame, orient="horizontal", command=self._emu_tree.xview)
        self._emu_tree.configure(
            yscrollcommand=emu_files_scroll_y.set,
            xscrollcommand=emu_files_scroll_x.set,
        )
        emu_files_scroll_y.pack(side="right", fill="y")
        emu_files_scroll_x.pack(side="bottom", fill="x")
        self._emu_tree.pack(fill="both", expand=True)

        self._emu_tree.bind("<Delete>", lambda _e: self._delete_selected_emulators())
        self._emu_tree.bind("<Double-1>", lambda _e: self._reveal_selected_file(self._emu_tree))
        self._emu_tree.bind(
            "<Button-3>",
            lambda event: self._post_tree_menu(event, self._emu_tree, self._emus_menu),
        )

    def _build_context_menus(self):
        self._systems_menu = tk.Menu(self, tearoff=False)
        self._systems_menu.add_command(label="Open Folder\tEnter", command=self._open_selected_system_folder)
        self._systems_menu.add_command(label="Validate\tCtrl+D", command=self._validate_selected_games)
        self._systems_menu.add_separator()
        self._systems_menu.add_command(label="New System Folder\tCtrl+Shift+N", command=self._new_game_folder)
        self._systems_menu.add_command(
            label="Create Common Folders", command=self._create_common_system_folders
        )
        self._systems_menu.add_separator()
        self._systems_menu.add_command(label="Refresh\tF5", command=self._scan_all)

        self._games_menu = tk.Menu(self, tearoff=False)
        self._games_menu.add_command(label="Reveal in Explorer\tEnter", command=lambda: self._reveal_selected_file(self._game_tree))
        self._games_menu.add_command(label="Rename\tF2", command=self._rename_selected_games)
        self._games_menu.add_command(label="Clean Names\tCtrl+L", command=self._clean_selected_game_names)
        self._games_menu.add_separator()
        self._games_menu.add_command(label="Validate\tCtrl+D", command=self._validate_selected_games)
        self._games_menu.add_command(label="Delete\tDelete", command=self._delete_selected_games)
        self._games_menu.add_separator()
        self._games_menu.add_command(label="Refresh\tF5", command=self._scan_all)

        self._emu_folders_menu = tk.Menu(self, tearoff=False)
        self._emu_folders_menu.add_command(label="Open Folder\tEnter", command=self._open_selected_emu_folder)
        self._emu_folders_menu.add_command(label="Validate\tCtrl+D", command=self._validate_selected_emulators)
        self._emu_folders_menu.add_separator()
        self._emu_folders_menu.add_command(label="New Emulator Folder\tCtrl+Shift+N", command=self._new_emu_folder)
        self._emu_folders_menu.add_separator()
        self._emu_folders_menu.add_command(label="Refresh\tF5", command=self._scan_all)

        self._emus_menu = tk.Menu(self, tearoff=False)
        self._emus_menu.add_command(label="Reveal in Explorer\tEnter", command=lambda: self._reveal_selected_file(self._emu_tree))
        self._emus_menu.add_command(label="Rename\tF2", command=self._rename_selected_emulators)
        self._emus_menu.add_command(label="Clean Names\tCtrl+L", command=self._clean_selected_emulator_names)
        self._emus_menu.add_separator()
        self._emus_menu.add_command(label="Validate\tCtrl+D", command=self._validate_selected_emulators)
        self._emus_menu.add_command(label="Delete\tDelete", command=self._delete_selected_emulators)
        self._emus_menu.add_separator()
        self._emus_menu.add_command(label="Refresh\tF5", command=self._scan_all)

    def _register_drop_targets(self):
        if not TKDND_AVAILABLE:
            return

        try:
            self._game_tree.drop_target_register(DND_FILES)
            self._emu_tree.drop_target_register(DND_FILES)
            self._game_tree.dnd_bind("<<Drop>>", self._on_game_drop)
            self._emu_tree.dnd_bind("<<Drop>>", self._on_emu_drop)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Persistent state
    # ------------------------------------------------------------------
    def _load_settings(self) -> Dict[str, object]:
        try:
            return json.loads(APP_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self):
        data = {
            "sd_path": self._sd_path.get().strip(),
            "copy_mode": self._copy_mode.get(),
            "delete_to_recycle": bool(self._delete_to_recycle.get()),
            "game_filter": self._game_filter_var.get(),
            "emu_filter": self._emu_filter_var.get(),
            "tab_index": self._notebook.index(self._notebook.select()),
            "system_selection": self._current_system_selection_key(),
            "emu_selection": self._current_emu_selection_key(),
            "geometry": self.geometry(),
        }
        try:
            APP_STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _on_close_app(self):
        self._is_closing = True
        self._hide_toast()
        self._save_settings()
        self.destroy()

    def _queue_ui(self, callback, *args):
        if self._is_closing:
            return
        try:
            self.after(0, callback, *args)
        except Exception:
            pass

    def _show_toast(self, message: str, kind: str = "info", duration_ms: int = 2800):
        if self._is_closing or not message.strip():
            return

        colors = {
            "info": ("#0f172a", "#f8fafc"),
            "success": ("#14532d", "#f0fdf4"),
            "warning": ("#9a3412", "#fff7ed"),
            "error": ("#991b1b", "#fef2f2"),
        }
        border_color, bg_color = colors.get(kind, colors["info"])

        self._hide_toast()

        toast = tk.Toplevel(self)
        toast.withdraw()
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        try:
            toast.attributes("-alpha", 0.96)
        except Exception:
            pass

        frame = tk.Frame(toast, bg=bg_color, bd=1, relief="solid", highlightbackground=border_color, highlightcolor=border_color, highlightthickness=1)
        frame.pack()
        label = tk.Label(
            frame,
            text=message,
            bg=bg_color,
            fg=border_color,
            justify="left",
            padx=12,
            pady=8,
            wraplength=340,
            font=("Segoe UI", 9),
        )
        label.pack()
        frame.bind("<Button-1>", lambda _e: self._hide_toast())
        label.bind("<Button-1>", lambda _e: self._hide_toast())

        self.update_idletasks()
        toast.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() - toast.winfo_reqwidth() - 20
        y = self.winfo_rooty() + self.winfo_height() - toast.winfo_reqheight() - 48
        toast.geometry(f"+{max(x, 20)}+{max(y, 20)}")
        toast.deiconify()

        self._toast_window = toast
        self._toast_after_id = self.after(duration_ms, self._hide_toast)

    def _hide_toast(self):
        if self._toast_after_id:
            try:
                self.after_cancel(self._toast_after_id)
            except Exception:
                pass
            self._toast_after_id = None
        if self._toast_window and self._toast_window.winfo_exists():
            self._toast_window.destroy()
        self._toast_window = None

    def _reposition_toast(self):
        if not self._toast_window or not self._toast_window.winfo_exists():
            return
        self.update_idletasks()
        self._toast_window.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() - self._toast_window.winfo_reqwidth() - 20
        y = self.winfo_rooty() + self.winfo_height() - self._toast_window.winfo_reqheight() - 48
        self._toast_window.geometry(f"+{max(x, 20)}+{max(y, 20)}")

    def _show_shortcuts_dialog(self):
        if not self._shortcuts_enabled():
            return

        dialog = tk.Toplevel(self)
        dialog.title("Shortcuts and Tips")
        dialog.geometry("560x440")
        dialog.minsize(500, 360)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Keyboard Shortcuts", style="Title.TLabel").pack(
            anchor="w", padx=14, pady=(14, 6)
        )

        shortcuts = [
            ("Ctrl+R / F5", "Scan or refresh the current device"),
            ("Ctrl+I", "Import files into the current target folder"),
            ("Ctrl+O", "Open the current selection in Explorer"),
            ("Ctrl+F", "Focus the current tab's filter box"),
            ("Escape", "Clear the current filter or dismiss the toast"),
            ("F2", "Rename the selected file"),
            ("Ctrl+L", "Clean selected file names"),
            ("Ctrl+D", "Validate selected rows or the current filtered view"),
            ("Ctrl+Shift+N", "Create a new system or emulator folder"),
            ("Ctrl+A", "Select all visible rows in the current file list"),
            ("Alt+1 / Alt+2", "Switch between Games and Emulators"),
            ("Enter", "Reveal the selected row or folder in Explorer"),
            ("Delete", "Delete selected files"),
            ("F1", "Open this help window"),
        ]

        content = ttk.Frame(dialog, padding=(14, 0, 14, 14))
        content.pack(fill="both", expand=True)

        shortcuts_box = tk.Text(
            content,
            wrap="word",
            relief="flat",
            borderwidth=0,
            background="#f4f7fb",
            font="TkFixedFont",
            padx=2,
            pady=2,
            height=16,
        )
        shortcuts_box.pack(fill="both", expand=True)

        shortcuts_box.insert("end", "Shortcuts\n\n")
        for shortcut, description in shortcuts:
            shortcuts_box.insert("end", f"{shortcut:<18} {description}\n")

        shortcuts_box.insert(
            "end",
            "\nTips\n\n"
            "- Filter boxes search by name, extension, folder, and warning text.\n"
            "- Right-click any tree for context actions.\n"
            "- Double-click or press Enter on a file row to reveal it in Explorer.\n"
            + (
                "- Drag files onto the lists to import them.\n"
                if TKDND_AVAILABLE
                else "- Install tkinterdnd2 to enable drag-and-drop import onto the lists.\n"
            )
            + 
            "- Validation uses the selected rows first, then falls back to the current filtered view.\n",
        )
        shortcuts_box.configure(state="disabled")

        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 14))
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    # ------------------------------------------------------------------
    # Drive handling
    # ------------------------------------------------------------------
    def _refresh_drive_choices(self):
        drives = get_windows_drives()
        current = self._sd_path.get().strip()
        values = drives[:]
        if current and current not in values:
            values.append(current)
        self._drive_combo["values"] = values

    def _auto_detect_drive(self):
        drives = get_windows_drives()
        self._drive_combo["values"] = drives

        for drive in drives:
            if not safe_exists(Path(drive)):
                continue
            roms_root = find_roms_root(Path(drive))
            if roms_root != Path(drive):
                self._sd_path.set(drive)
                self._scan_all()
                return

        for drive in drives:
            if safe_exists(Path(drive)):
                self._sd_path.set(drive)
                return

    def _browse_path(self):
        path = filedialog.askdirectory(title="Select SF3000 SD Card Root Folder")
        if path:
            self._sd_path.set(path)
            self._scan_all()

    # ------------------------------------------------------------------
    # Background scanning
    # ------------------------------------------------------------------
    def _scan_all(self):
        raw = self._sd_path.get().strip()
        self._refresh_drive_choices()
        if not raw:
            self._set_status("Select an SD card path to scan.")
            return

        root = Path(raw)
        if not safe_exists(root):
            messagebox.showerror(
                "Not Found",
                f"Path not found:\n{raw}\n\n"
                "Make sure the SD card is inserted and mounted.\n"
                "If it shows as RAW, use Ext2Fsd, WSL, or DiskInternals Linux Reader "
                "to mount the ext4 partition first.",
            )
            return

        self._pending_system_selection = self._current_system_selection_key()
        self._pending_emu_selection = self._current_emu_selection_key()
        self._pending_game_paths = list(self._game_tree.selection())
        self._pending_emu_paths = list(self._emu_tree.selection())

        self._scan_generation += 1
        generation = self._scan_generation
        self._set_scanning(True, f"Scanning {root}...")

        def worker():
            try:
                payload = self._collect_scan_payload(root)
            except Exception as exc:
                self._queue_ui(self._handle_scan_error, generation, str(exc))
                return
            self._queue_ui(self._apply_scan_payload, generation, payload)

        threading.Thread(target=worker, daemon=True).start()

    def _collect_scan_payload(self, root: Path) -> Dict[str, object]:
        storage = None
        try:
            storage = shutil.disk_usage(root)
        except Exception:
            storage = None

        roms_root = find_roms_root(root)
        game_folders = list_child_dirs(roms_root)
        game_records_by_key: Dict[str, List[FileRecord]] = {"__all__": []}
        game_folder_rows = []

        for folder in game_folders:
            records = []
            for file_path in list_child_files(folder):
                warning = build_game_warning(file_path, folder.name)
                records.append(build_file_record(file_path, file_path.stem, folder.name, warning))
            records.sort(key=lambda record: record.raw_name.casefold())
            game_records_by_key[str(folder)] = records
            game_records_by_key["__all__"].extend(records)
            game_folder_rows.append(
                {
                    "path": str(folder),
                    "name": folder.name,
                    "count": len(records),
                    "issues": sum(1 for record in records if record.warning),
                }
            )

        game_records_by_key["__all__"].sort(
            key=lambda record: (record.parent_name.casefold(), record.raw_name.casefold())
        )

        emu_root = find_emulators_root(root)
        emu_records_by_key: Dict[str, List[FileRecord]] = {"__emu_all__": [], "__emu_root__": []}
        emu_folder_rows = []

        if emu_root is not None:
            root_records = []
            for file_path in list_child_files(emu_root):
                warning = build_emulator_warning(file_path)
                root_records.append(build_file_record(file_path, file_path.name, "/", warning))
            root_records.sort(key=lambda record: record.raw_name.casefold())
            emu_records_by_key["__emu_root__"] = root_records
            emu_records_by_key["__emu_all__"].extend(root_records)

            for folder in list_child_dirs(emu_root):
                records = []
                for file_path in list_child_files(folder):
                    warning = build_emulator_warning(file_path)
                    records.append(build_file_record(file_path, file_path.name, folder.name, warning))
                records.sort(key=lambda record: record.raw_name.casefold())
                emu_records_by_key[str(folder)] = records
                emu_records_by_key["__emu_all__"].extend(records)
                emu_folder_rows.append(
                    {
                        "path": str(folder),
                        "name": folder.name,
                        "count": len(records),
                        "issues": sum(1 for record in records if record.warning),
                    }
                )

        emu_records_by_key["__emu_all__"].sort(
            key=lambda record: (record.parent_name.casefold(), record.raw_name.casefold())
        )

        return {
            "root": root,
            "storage": storage,
            "games": {
                "roms_root": roms_root,
                "folder_rows": game_folder_rows,
                "records_by_key": game_records_by_key,
                "total_files": len(game_records_by_key["__all__"]),
                "issues": sum(1 for record in game_records_by_key["__all__"] if record.warning),
            },
            "emus": {
                "emu_root": emu_root,
                "folder_rows": emu_folder_rows,
                "records_by_key": emu_records_by_key,
                "root_count": len(emu_records_by_key["__emu_root__"]),
                "total_files": len(emu_records_by_key["__emu_all__"]),
                "issues": sum(1 for record in emu_records_by_key["__emu_all__"] if record.warning),
            },
        }

    def _handle_scan_error(self, generation: int, message: str):
        if generation != self._scan_generation:
            return
        self._set_scanning(False)
        messagebox.showerror("Scan Error", message)
        self._set_status("Scan failed.")
        self._show_toast("Scan failed. See the error dialog for details.", kind="error")

    def _apply_scan_payload(self, generation: int, payload: Dict[str, object]):
        if generation != self._scan_generation:
            return

        self._set_scanning(False)
        self._refresh_drive_choices()

        games = payload["games"]
        emus = payload["emus"]

        self._roms_root = games["roms_root"]
        self._emu_root = emus["emu_root"]
        self._game_records_by_key = games["records_by_key"]
        self._emu_records_by_key = emus["records_by_key"]

        self._populate_system_tree(games["folder_rows"], self._roms_root)
        self._populate_emu_tree(emus["folder_rows"], self._emu_root, emus["root_count"])

        self._update_storage_from_usage(payload["storage"])

        self._restore_tree_selection(self._sys_tree, self._pending_system_selection, "__all__")
        if self._emu_root is not None:
            self._restore_tree_selection(self._emu_folder_tree, self._pending_emu_selection, "__emu_all__")

        self._on_system_select()
        if self._emu_root is not None:
            self._on_emu_folder_select()
        else:
            self._clear_emu_view()

        self._restore_file_selection(self._game_tree, self._pending_game_paths)
        self._restore_file_selection(self._emu_tree, self._pending_emu_paths)

        if self._next_status_message:
            self._set_status(self._next_status_message)
            self._show_toast(
                self._next_status_message,
                kind="warning" if "cancel" in self._next_status_message.casefold() else "success",
            )
            self._next_status_message = None
        else:
            self._refresh_active_status()

    def _set_scanning(self, scanning: bool, message: str = ""):
        self._scan_in_progress = scanning
        if scanning:
            self._scan_button.state(["disabled"])
            self._scan_button.configure(text="Scanning...")
            self._scan_progress.start(12)
            self.configure(cursor="watch")
            if message:
                self._set_status(message)
        else:
            self._scan_button.state(["!disabled"])
            self._scan_button.configure(text="Scan")
            self._scan_progress.stop()
            self.configure(cursor="")

    def _populate_system_tree(self, rows: Sequence[Dict[str, object]], roms_root: Path):
        self._sys_tree.delete(*self._sys_tree.get_children())
        self._sys_tree.insert("", "end", iid="__all__", text="All Systems", values=[str(roms_root)])
        for row in rows:
            text = f"  {row['name']}  ({row['count']})"
            if row["issues"]:
                text += f"  [{row['issues']} issues]"
            self._sys_tree.insert("", "end", iid=row["path"], text=text, values=[row["path"]])

    def _populate_emu_tree(self, rows: Sequence[Dict[str, object]], emu_root: Optional[Path], root_count: int):
        self._emu_folder_tree.delete(*self._emu_folder_tree.get_children())
        if emu_root is None:
            self._emu_path_label.config(
                text="Emulators folder: (not found -- create one with 'New Emulator Folder')",
                foreground="gray",
            )
            return

        self._emu_path_label.config(text=f"Emulators folder: {emu_root}", foreground="black")
        total_count = len(self._emu_records_by_key.get("__emu_all__", []))
        self._emu_folder_tree.insert(
            "",
            "end",
            iid="__emu_all__",
            text=f"All Emulators  ({total_count})",
            values=[str(emu_root)],
        )

        if root_count:
            root_issues = sum(1 for record in self._emu_records_by_key.get("__emu_root__", []) if record.warning)
            text = f"  / (root)  ({root_count})"
            if root_issues:
                text += f"  [{root_issues} issues]"
            self._emu_folder_tree.insert(
                "",
                "end",
                iid="__emu_root__",
                text=text,
                values=[str(emu_root)],
            )

        for row in rows:
            text = f"  {row['name']}  ({row['count']})"
            if row["issues"]:
                text += f"  [{row['issues']} issues]"
            self._emu_folder_tree.insert("", "end", iid=row["path"], text=text, values=[row["path"]])

    def _update_storage_from_usage(self, usage):
        if usage is None:
            self._storage_bar["value"] = 0
            self._storage_label.config(text="")
            return

        pct = (usage.used / usage.total) * 100 if usage.total else 0
        self._storage_bar["value"] = pct
        self._storage_label.config(
            text=(
                f"{format_size(usage.used)} used / {format_size(usage.total)} total"
                f"  ({format_size(usage.free)} free)"
            )
        )

    def _clear_emu_view(self):
        self._current_emu_key = "__emu_all__"
        self._current_emu_label = ""
        self._current_emu_records = []
        self._emu_visible_map.clear()
        self._emu_tree.delete(*self._emu_tree.get_children())
        if self._notebook.index(self._notebook.select()) == 1:
            self._set_status("No Emulators folder found on the selected device.")

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------
    def _restore_tree_selection(self, tree, selection_key: str, fallback_iid: str):
        children = tree.get_children("")
        if not children:
            return

        target = None
        if selection_key in children:
            target = selection_key
        elif selection_key:
            for child in children:
                if child.startswith("__"):
                    continue
                if Path(child).name.casefold() == selection_key.casefold():
                    target = child
                    break

        if target is None:
            target = fallback_iid if fallback_iid in children else children[0]

        tree.selection_set(target)
        tree.focus(target)
        tree.see(target)

    def _restore_file_selection(self, tree, paths: Sequence[str]):
        existing = [path for path in paths if tree.exists(path)]
        if not existing:
            return
        tree.selection_set(existing)
        tree.focus(existing[0])
        tree.see(existing[0])

    def _current_system_selection_key(self) -> str:
        selection = self._sys_tree.selection()
        if not selection:
            return self._pending_system_selection
        iid = selection[0]
        return iid if iid == "__all__" else Path(iid).name

    def _current_emu_selection_key(self) -> str:
        selection = self._emu_folder_tree.selection()
        if not selection:
            return self._pending_emu_selection
        iid = selection[0]
        return iid if iid.startswith("__") else Path(iid).name

    def _set_status(self, text: str):
        self._status.set(text)

    def _game_status_text(self) -> str:
        visible_count = len(self._game_visible_map)
        issue_count = sum(1 for record in self._game_visible_map.values() if record.warning)
        if self._game_filter_var.get().strip():
            return (
                f"Showing {visible_count} of {len(self._current_game_records)} game file(s) in "
                f"'{self._current_game_label}' | {issue_count} warning(s)."
            )
        return f"{visible_count} game file(s) in '{self._current_game_label}' | {issue_count} warning(s)."

    def _emu_status_text(self) -> str:
        visible_count = len(self._emu_visible_map)
        issue_count = sum(1 for record in self._emu_visible_map.values() if record.warning)
        if self._emu_filter_var.get().strip():
            return (
                f"Showing {visible_count} of {len(self._current_emu_records)} emulator file(s) in "
                f"'{self._current_emu_label}' | {issue_count} warning(s)."
            )
        return f"{visible_count} emulator file(s) in '{self._current_emu_label}' | {issue_count} warning(s)."

    def _refresh_active_status(self):
        if self._notebook.index(self._notebook.select()) == 0:
            if self._current_game_label:
                self._set_status(self._game_status_text())
            return
        if self._current_emu_label:
            self._set_status(self._emu_status_text())
        elif self._emu_root is None:
            self._set_status("No Emulators folder found on the selected device.")

    # ------------------------------------------------------------------
    # Games list
    # ------------------------------------------------------------------
    def _on_system_select(self, _event=None):
        selection = self._sys_tree.selection()
        if not selection:
            return

        iid = selection[0]
        self._current_game_key = iid
        self._pending_system_selection = iid if iid == "__all__" else Path(iid).name
        self._current_game_records = list(self._game_records_by_key.get(iid, []))
        self._current_game_label = "All Systems" if iid == "__all__" else Path(iid).name
        self._refresh_game_tree()

    def _on_game_filter_change(self, *_args):
        self._refresh_game_tree()

    def _refresh_game_tree(self):
        previous_selection = self._game_tree.selection()
        self._game_tree.delete(*self._game_tree.get_children())
        self._game_visible_map.clear()

        if not self._current_game_label:
            return

        visible_records = [
            record
            for record in self._current_game_records
            if record_matches_query(record, self._game_filter_var.get().strip())
        ]
        visible_records = self._sorted_game_records(visible_records)

        for index, record in enumerate(visible_records):
            iid = str(record.path)
            self._game_visible_map[iid] = record
            tags = ["row_even" if index % 2 == 0 else "row_odd"]
            if record.warning:
                tags.append("warning")
            self._game_tree.insert(
                "",
                "end",
                iid=iid,
                tags=tuple(tags),
                values=(
                    record.display_name,
                    record.raw_name,
                    format_size(record.size),
                    record.file_type,
                    record.modified_text,
                    record.parent_name,
                    record.warning,
                ),
            )

        self._restore_file_selection(self._game_tree, previous_selection)
        if self._notebook.index(self._notebook.select()) == 0:
            self._set_status(self._game_status_text())

    def _sorted_game_records(self, records: List[FileRecord]) -> List[FileRecord]:
        return sorted(
            records,
            key=lambda record: self._record_sort_value(record, self._game_sort_column, game_mode=True),
            reverse=self._game_sort_reverse,
        )

    def _sort_games(self, column: str):
        if self._game_sort_column == column:
            self._game_sort_reverse = not self._game_sort_reverse
        else:
            self._game_sort_column = column
            self._game_sort_reverse = False
        self._refresh_game_tree()

    # ------------------------------------------------------------------
    # Emulators list
    # ------------------------------------------------------------------
    def _on_emu_folder_select(self, _event=None):
        selection = self._emu_folder_tree.selection()
        if not selection:
            return

        iid = selection[0]
        self._current_emu_key = iid
        self._pending_emu_selection = iid if iid.startswith("__") else Path(iid).name
        self._current_emu_records = list(self._emu_records_by_key.get(iid, []))
        if iid == "__emu_all__":
            self._current_emu_label = "All Emulators"
        elif iid == "__emu_root__":
            self._current_emu_label = "/ (root)"
        else:
            self._current_emu_label = Path(iid).name
        self._refresh_emu_tree()

    def _on_emu_filter_change(self, *_args):
        self._refresh_emu_tree()

    def _refresh_emu_tree(self):
        previous_selection = self._emu_tree.selection()
        self._emu_tree.delete(*self._emu_tree.get_children())
        self._emu_visible_map.clear()

        if not self._current_emu_label:
            return

        visible_records = [
            record
            for record in self._current_emu_records
            if record_matches_query(record, self._emu_filter_var.get().strip())
        ]
        visible_records = self._sorted_emu_records(visible_records)

        for index, record in enumerate(visible_records):
            iid = str(record.path)
            self._emu_visible_map[iid] = record
            tags = ["row_even" if index % 2 == 0 else "row_odd"]
            if record.warning:
                tags.append("warning")
            self._emu_tree.insert(
                "",
                "end",
                iid=iid,
                tags=tuple(tags),
                values=(
                    record.raw_name,
                    format_size(record.size),
                    record.file_type,
                    record.modified_text,
                    record.parent_name,
                    record.warning,
                ),
            )

        self._restore_file_selection(self._emu_tree, previous_selection)
        if self._notebook.index(self._notebook.select()) == 1:
            self._set_status(self._emu_status_text())

    def _sorted_emu_records(self, records: List[FileRecord]) -> List[FileRecord]:
        return sorted(
            records,
            key=lambda record: self._record_sort_value(record, self._emu_sort_column, game_mode=False),
            reverse=self._emu_sort_reverse,
        )

    def _sort_emus(self, column: str):
        if self._emu_sort_column == column:
            self._emu_sort_reverse = not self._emu_sort_reverse
        else:
            self._emu_sort_column = column
            self._emu_sort_reverse = False
        self._refresh_emu_tree()

    def _record_sort_value(self, record: FileRecord, column: str, game_mode: bool):
        if column == "name":
            return record.display_name.casefold() if game_mode else record.raw_name.casefold()
        if column == "file":
            return record.raw_name.casefold()
        if column == "size":
            return record.size
        if column == "type":
            return record.file_type.casefold()
        if column == "modified":
            return record.modified_ts
        if column == "folder":
            return record.parent_name.casefold()
        if column == "warning":
            return record.warning.casefold()
        return record.raw_name.casefold()

    # ------------------------------------------------------------------
    # Explorer helpers
    # ------------------------------------------------------------------
    def _post_tree_menu(self, event, tree, menu):
        row = tree.identify_row(event.y)
        if row:
            tree.selection_set(row)
            tree.focus(row)
            tree.event_generate("<<TreeviewSelect>>")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _reveal_path_in_explorer(self, path: Path):
        if not safe_exists(path):
            return
        try:
            if path.is_file():
                subprocess.Popen(["explorer", f"/select,{path}"])
            else:
                os.startfile(path)
        except Exception:
            target = path.parent if path.is_file() else path
            os.startfile(target)

    def _reveal_selected_file(self, tree):
        selection = tree.selection()
        if not selection:
            return
        self._reveal_path_in_explorer(Path(selection[0]))

    def _open_selected_system_folder(self):
        selection = self._sys_tree.selection()
        if not selection:
            return
        iid = selection[0]
        if iid == "__all__":
            if self._roms_root:
                self._reveal_path_in_explorer(self._roms_root)
            return
        self._reveal_path_in_explorer(Path(iid))

    def _open_selected_emu_folder(self):
        selection = self._emu_folder_tree.selection()
        if not selection:
            return
        iid = selection[0]
        if iid in ("__emu_all__", "__emu_root__"):
            if self._emu_root:
                self._reveal_path_in_explorer(self._emu_root)
            return
        self._reveal_path_in_explorer(Path(iid))

    def _open_in_explorer(self):
        tab_index = self._notebook.index(self._notebook.select())

        if tab_index == 0:
            file_selection = self._game_tree.selection()
            if file_selection:
                self._reveal_path_in_explorer(Path(file_selection[0]))
                return
            self._open_selected_system_folder()
            return

        file_selection = self._emu_tree.selection()
        if file_selection:
            self._reveal_path_in_explorer(Path(file_selection[0]))
            return
        self._open_selected_emu_folder()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate_selected_games(self):
        records = self._selected_game_records() or list(self._game_visible_map.values())
        issues = []

        if self._current_game_key not in ("", "__all__"):
            folder_name = Path(self._current_game_key).name
            if get_system_extensions(folder_name) is None:
                issues.append(f"Folder '{folder_name}' is not a recognized system alias.")

        for record in records:
            if record.warning:
                issues.append(f"{record.raw_name}: {record.warning}")

        if not issues:
            self._show_toast(f"No issues found in '{self._current_game_label}'.", kind="success")
            return

        messagebox.showwarning(
            "Validation Results",
            f"Found {len(issues)} issue(s) in '{self._current_game_label}':\n\n"
            f"{format_name_list(issues, limit=18)}",
        )

    def _validate_selected_emulators(self):
        records = self._selected_emu_records() or list(self._emu_visible_map.values())
        issues = [f"{record.raw_name}: {record.warning}" for record in records if record.warning]

        if not issues:
            self._show_toast(f"No issues found in '{self._current_emu_label}'.", kind="success")
            return

        messagebox.showwarning(
            "Validation Results",
            f"Found {len(issues)} issue(s) in '{self._current_emu_label}':\n\n"
            f"{format_name_list(issues, limit=18)}",
        )

    # ------------------------------------------------------------------
    # Rename helpers
    # ------------------------------------------------------------------
    def _selected_game_records(self) -> List[FileRecord]:
        return [self._game_visible_map[iid] for iid in self._game_tree.selection() if iid in self._game_visible_map]

    def _selected_emu_records(self) -> List[FileRecord]:
        return [self._emu_visible_map[iid] for iid in self._emu_tree.selection() if iid in self._emu_visible_map]

    def _rename_selected_games(self):
        records = self._selected_game_records()
        self._rename_single_record(records, "Rename Game File")

    def _rename_selected_emulators(self):
        records = self._selected_emu_records()
        self._rename_single_record(records, "Rename Emulator File")

    def _rename_single_record(self, records: List[FileRecord], title: str):
        if not records:
            return
        if len(records) != 1:
            messagebox.showinfo(title, "Select exactly one file to rename.")
            return

        record = records[0]
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("430x140")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="New file name:").pack(pady=(16, 4), padx=12, anchor="w")
        entry = ttk.Entry(dialog, width=52)
        entry.insert(0, record.raw_name)
        entry.pack(padx=12, fill="x")
        entry.select_range(0, "end")
        entry.focus()

        def submit():
            new_name = entry.get().strip()
            if not new_name:
                return
            if "." not in new_name and record.path.suffix:
                new_name += record.path.suffix

            safe_name = sanitize_windows_name(new_name)
            if safe_name != new_name:
                messagebox.showwarning(
                    "Invalid Name",
                    "File name contains invalid Windows characters.",
                    parent=dialog,
                )
                return

            destination = record.path.with_name(new_name)
            if same_path(destination, record.path):
                dialog.destroy()
                return
            if safe_exists(destination):
                messagebox.showwarning(
                    "Name Exists",
                    f"A file named '{new_name}' already exists.",
                    parent=dialog,
                )
                return

            try:
                record.path.rename(destination)
            except Exception as exc:
                messagebox.showerror("Rename Error", str(exc), parent=dialog)
                return

            dialog.destroy()
            self._next_status_message = f"Renamed '{record.raw_name}' to '{destination.name}'."
            self._scan_all()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=12)
        ttk.Button(button_frame, text="Rename", command=submit).pack(side="left", padx=6)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=6)
        dialog.bind("<Return>", lambda _e: submit())

    def _clean_selected_game_names(self):
        self._clean_selected_names(self._selected_game_records(), "game file(s)")

    def _clean_selected_emulator_names(self):
        self._clean_selected_names(self._selected_emu_records(), "emulator file(s)")

    def _clean_selected_names(self, records: List[FileRecord], label: str):
        if not records:
            return

        proposed = []
        planned_targets = set()
        for record in records:
            new_name = clean_filename(record.raw_name)
            destination = record.path.with_name(new_name)
            if same_path(destination, record.path):
                continue
            if safe_exists(destination) or str(destination).casefold() in planned_targets:
                continue
            planned_targets.add(str(destination).casefold())
            proposed.append((record.path, destination))

        if not proposed:
            self._show_toast("No selected files need cleaning.", kind="info")
            return

        preview = [f"{source.name}  ->  {destination.name}" for source, destination in proposed]
        if not messagebox.askyesno(
            "Clean Names",
            f"Rename {len(proposed)} {label}?\n\n{format_name_list(preview, limit=12)}",
        ):
            return

        errors = []
        for source, destination in proposed:
            try:
                source.rename(destination)
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")

        if errors:
            messagebox.showerror("Rename Errors", "\n".join(errors))

        self._next_status_message = f"Cleaned names for {len(proposed) - len(errors)} file(s)."
        self._scan_all()

    # ------------------------------------------------------------------
    # Copy / move helpers
    # ------------------------------------------------------------------
    def _build_transfer_plan(self, files: Sequence[str], dest_folder: Path) -> TransferPlan:
        mode = self._copy_mode.get()
        items = []
        skipped_identical = []
        skipped_same_path = []
        overwrites = []
        total_bytes = 0
        required_bytes = 0

        for file_name in files:
            source = Path(file_name)
            destination = dest_folder / source.name
            stat = safe_stat(source)
            size = stat.st_size if stat else 0

            if same_path(source, destination):
                skipped_same_path.append(source.name)
                continue

            overwrite = False
            if safe_exists(destination):
                if files_are_identical(source, destination):
                    skipped_identical.append(source.name)
                    continue
                overwrite = True
                overwrites.append(source.name)

            total_bytes += size
            if mode == "copy":
                required_bytes += size
            elif not same_drive(source, destination):
                required_bytes += size

            items.append(TransferItem(source=source, destination=destination, size=size, overwrite=overwrite))

        return TransferPlan(
            items=items,
            skipped_identical=skipped_identical,
            skipped_same_path=skipped_same_path,
            overwrites=overwrites,
            total_bytes=total_bytes,
            required_bytes=required_bytes,
        )

    def _copy_files_to(self, files: Sequence[str], dest_folder: Path, on_done):
        mode = self._copy_mode.get()
        plan = self._build_transfer_plan(files, dest_folder)

        if plan.skipped_same_path:
            messagebox.showinfo(
                "Skipped Files",
                "These files are already in the destination folder and were skipped:\n\n"
                f"{format_name_list(plan.skipped_same_path)}",
            )

        if not plan.items:
            if plan.skipped_identical:
                self._show_toast(
                    "Every selected file already exists with matching contents, so nothing was imported.",
                    kind="info",
                    duration_ms=3400,
                )
            return

        usage = None
        usage_target = dest_folder if safe_exists(dest_folder) else Path(self._sd_path.get().strip())
        try:
            usage = shutil.disk_usage(usage_target)
        except Exception:
            usage = None

        summary_lines = [
            f"Mode: {mode.title()}",
            f"Destination: {dest_folder}",
            f"Files to process: {len(plan.items)}",
            f"Transfer size: {format_size(plan.total_bytes)}",
        ]
        if plan.overwrites:
            summary_lines.append(f"Files to overwrite: {len(plan.overwrites)}")
            summary_lines.append(
                "Overwrite handling: "
                + ("move old files to Recycle Bin first" if self._delete_to_recycle.get() else "remove old files after replacement staging")
            )
        if plan.skipped_identical:
            summary_lines.append(f"Content-identical files skipped: {len(plan.skipped_identical)}")
        if usage is not None:
            summary_lines.append(f"Free space: {format_size(usage.free)}")
            summary_lines.append(f"Estimated space needed: {format_size(plan.required_bytes)}")

        if usage is not None and plan.required_bytes > usage.free:
            if not messagebox.askyesno(
                "Low Space Warning",
                "There may not be enough free space for this import.\n\n"
                + "\n".join(summary_lines)
                + "\n\nContinue anyway?",
                icon="warning",
            ):
                return
        elif usage is not None and usage.free - plan.required_bytes < LOW_SPACE_WARNING_BYTES:
            if not messagebox.askyesno(
                "Low Space Warning",
                "This import will leave very little free space on the device.\n\n"
                + "\n".join(summary_lines)
                + "\n\nContinue?",
                icon="warning",
            ):
                return
        elif not messagebox.askyesno(
            f"{mode.title()} Files",
            "\n".join(summary_lines) + "\n\nContinue?",
        ):
            return

        dialog = ProgressDialog(self, f"{mode.title()}ing Files")
        verb = "Moving" if mode == "move" else "Copying"

        def worker():
            errors = []
            processed = 0

            for index, item in enumerate(plan.items, start=1):
                if dialog.cancelled:
                    break

                self._queue_ui(dialog.update_progress, index, len(plan.items), str(item.source), verb)
                try:
                    self._execute_transfer_item(item, mode)
                    processed += 1
                except Exception as exc:
                    errors.append(f"{item.source.name}: {exc}")

            self._queue_ui(_safe_destroy, dialog)

            if errors:
                self._queue_ui(messagebox.showerror, "File Operation Errors", "\n".join(errors))

            if dialog.cancelled:
                self._next_status_message = f"{mode.title()} cancelled after {processed} of {len(plan.items)} file(s)."
            else:
                self._next_status_message = f"{mode.title()}ed {processed} file(s) to '{dest_folder.name}'."

            self._queue_ui(on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _replace_destination_with_temp(self, temp_path: Path, destination: Path):
        if safe_exists(destination):
            if self._delete_to_recycle.get():
                send_to_recycle_bin(destination)
            else:
                destination.unlink()
        os.replace(temp_path, destination)

    def _execute_transfer_item(self, item: TransferItem, mode: str):
        item.destination.parent.mkdir(parents=True, exist_ok=True)

        if mode == "move" and not item.overwrite:
            shutil.move(str(item.source), str(item.destination))
            return

        temp_path = create_temp_destination(item.destination.parent, item.destination.suffix)
        try:
            shutil.copy2(str(item.source), str(temp_path))
            self._replace_destination_with_temp(temp_path, item.destination)
            if mode == "move" and safe_exists(item.source):
                item.source.unlink()
        except Exception:
            if safe_exists(temp_path):
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    # ------------------------------------------------------------------
    # Add files
    # ------------------------------------------------------------------
    def _normalize_dropped_files(self, raw_data: str) -> List[str]:
        try:
            dropped_paths = [Path(value) for value in self.tk.splitlist(raw_data)]
        except tk.TclError:
            return []

        files = []
        skipped_dirs = []
        for path in dropped_paths:
            if safe_exists(path) and path.is_file():
                files.append(str(path))
            elif safe_is_dir(path):
                skipped_dirs.append(path.name)

        if skipped_dirs:
            messagebox.showinfo(
                "Skipped Folders",
                "Dropped folders are not imported automatically. These were skipped:\n\n"
                + format_name_list(skipped_dirs),
            )
        return files

    def _on_game_drop(self, event):
        files = self._normalize_dropped_files(event.data)
        if not files:
            return
        selection = self._sys_tree.selection()
        if not selection or selection[0] == "__all__":
            messagebox.showinfo(
                "Select a System",
                "Select a specific system folder on the left, then drop files into the games list.",
            )
            return
        self._import_game_files(files, Path(selection[0]))

    def _on_emu_drop(self, event):
        files = self._normalize_dropped_files(event.data)
        if not files:
            return
        if self._emu_root is None:
            messagebox.showinfo(
                "No Emulators Folder",
                "No Emulators folder found on the SD card.\nUse 'New Emulator Folder' to create one first.",
            )
            return
        selection = self._emu_folder_tree.selection()
        if selection and selection[0] not in ("__emu_all__", "__emu_root__"):
            dest_folder = Path(selection[0])
        else:
            dest_folder = self._emu_root
        self._import_emulator_files(files, dest_folder)

    def _import_game_files(self, files: Sequence[str], dest_folder: Path):
        accepted = []
        skipped = []
        warned = []
        for file_name in files:
            path = Path(file_name)
            warning = build_game_warning(path, dest_folder.name)
            if warning == "Unsupported ROM file":
                skipped.append(path.name)
                continue
            accepted.append(file_name)
            if warning:
                warned.append(f"{path.name}: {warning}")

        if skipped:
            messagebox.showwarning(
                "Skipped Unsupported Files",
                "These files do not look like supported ROMs and were skipped:\n\n"
                + format_name_list(skipped),
            )

        if warned and not messagebox.askyesno(
            "Import With Warnings",
            "These files can be imported, but they may not match the selected system cleanly:\n\n"
            + format_name_list(warned, limit=12)
            + "\n\nContinue?",
            icon="warning",
        ):
            return

        if accepted:
            self._copy_files_to(accepted, dest_folder, self._scan_all)

    def _import_emulator_files(self, files: Sequence[str], dest_folder: Path):
        accepted = []
        skipped = []
        for file_name in files:
            path = Path(file_name)
            if is_emulator_file(path):
                accepted.append(file_name)
            else:
                skipped.append(path.name)

        if skipped:
            messagebox.showwarning(
                "Skipped Unsupported Files",
                "Only supported emulator file types were added.\n\n" + format_name_list(skipped),
            )

        if accepted:
            self._copy_files_to(accepted, dest_folder, self._scan_all)

    def _add_games(self):
        selection = self._sys_tree.selection()
        if not selection or selection[0] == "__all__":
            messagebox.showinfo(
                "Select a System",
                "Please select a specific system folder in the left panel, then click Add Games.",
            )
            return

        dest_folder = Path(selection[0])
        allowed_extensions = get_system_extensions(dest_folder.name)
        picker_extensions = allowed_extensions or ALL_ROM_EXTENSIONS
        filetypes = [
            (f"{dest_folder.name} ROM Files", " ".join(f"*{ext}" for ext in picker_extensions)),
            ("All Supported ROMs", " ".join(f"*{ext}" for ext in ALL_ROM_EXTENSIONS)),
            ("All Files", "*.*"),
        ]
        files = filedialog.askopenfilenames(
            title=f"Select ROMs to add to '{dest_folder.name}'",
            filetypes=filetypes,
        )
        if not files:
            return
        self._import_game_files(files, dest_folder)

    def _add_emulators(self):
        raw = self._sd_path.get().strip()
        if not raw:
            messagebox.showwarning("No Drive", "Select the SD card drive first.")
            return

        if self._emu_root is None:
            messagebox.showinfo(
                "No Emulators Folder",
                "No Emulators folder found on the SD card.\nUse 'New Emulator Folder' to create one first.",
            )
            return

        selection = self._emu_folder_tree.selection()
        if selection and selection[0] not in ("__emu_all__", "__emu_root__"):
            dest_folder = Path(selection[0])
        else:
            dest_folder = self._emu_root

        files = filedialog.askopenfilenames(
            title=f"Select emulator file(s) to add to '{dest_folder.name}'",
            filetypes=[
                ("Emulator Files", " ".join(f"*{ext}" for ext in EMULATOR_EXTENSIONS)),
                ("All Files", "*.*"),
            ],
        )
        if not files:
            return
        self._import_emulator_files(files, dest_folder)

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------
    def _delete_selected_games(self):
        records = self._selected_game_records()
        self._confirm_and_delete(records, "game file(s)")

    def _delete_selected_emulators(self):
        records = self._selected_emu_records()
        self._confirm_and_delete(records, "emulator file(s)")

    def _confirm_and_delete(self, records: List[FileRecord], label: str):
        if not records:
            return

        action_text = "move to the Recycle Bin" if self._delete_to_recycle.get() else "permanently delete"
        names = [record.raw_name for record in records]
        if not messagebox.askyesno(
            "Confirm Delete",
            f"{action_text.title()} {len(records)} {label}?\n\n{format_name_list(names, limit=12)}",
            icon="warning",
        ):
            return

        errors = []
        for record in records:
            try:
                if self._delete_to_recycle.get():
                    send_to_recycle_bin(record.path)
                else:
                    record.path.unlink()
            except Exception as exc:
                errors.append(f"{record.raw_name}: {exc}")

        if errors:
            messagebox.showerror("Delete Errors", "\n".join(errors))

        self._next_status_message = f"Deleted {len(records) - len(errors)} {label}."
        self._scan_all()

    # ------------------------------------------------------------------
    # Folder creation
    # ------------------------------------------------------------------
    def _new_game_folder(self):
        raw = self._sd_path.get().strip()
        if not raw:
            messagebox.showwarning("No Drive", "Select the SD card drive first.")
            return

        self._prompt_new_folder(
            parent_dir=find_roms_root(Path(raw)),
            title="New System Folder",
            prompt="System folder name (e.g. GBA, NES, SNES):",
            on_created=self._scan_all,
        )

    def _create_common_system_folders(self):
        raw = self._sd_path.get().strip()
        if not raw:
            messagebox.showwarning("No Drive", "Select the SD card drive first.")
            return

        roms_root = find_roms_root(Path(raw))
        missing = [name for name in COMMON_SYSTEM_FOLDERS if not safe_exists(roms_root / name)]
        if not missing:
            self._show_toast("All common system folders already exist.", kind="info")
            return

        if not messagebox.askyesno(
            "Create Common Folders",
            "Create these folders?\n\n" + format_name_list(missing, limit=20),
        ):
            return

        errors = []
        for name in missing:
            try:
                (roms_root / name).mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        if errors:
            messagebox.showerror("Folder Errors", "\n".join(errors))

        self._next_status_message = f"Created {len(missing) - len(errors)} common system folder(s)."
        self._scan_all()

    def _new_emu_folder(self):
        raw = self._sd_path.get().strip()
        if not raw:
            messagebox.showwarning("No Drive", "Select the SD card drive first.")
            return

        root = Path(raw)
        emu_root = find_emulators_root(root)
        if emu_root is None:
            self._prompt_emu_root_folder(root)
            return

        self._prompt_new_folder(
            parent_dir=emu_root,
            title="New Emulator Subfolder",
            prompt="Subfolder name (e.g. SNES, GBA, MAME):",
            on_created=self._scan_all,
        )

    def _prompt_new_folder(self, parent_dir: Path, title: str, prompt: str, on_created):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("360x140")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text=prompt).pack(pady=(16, 4), padx=12, anchor="w")
        entry = ttk.Entry(dialog, width=34)
        entry.pack(padx=12, fill="x")
        entry.focus()

        def submit():
            name = entry.get().strip()
            if not name:
                return
            safe_name = sanitize_windows_name(name)
            if safe_name != name or not safe_name:
                messagebox.showwarning(
                    "Invalid Name",
                    "Folder name contains invalid characters.",
                    parent=dialog,
                )
                return
            try:
                (parent_dir / safe_name).mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror("Folder Error", str(exc), parent=dialog)
                return

            dialog.destroy()
            self._next_status_message = f"Created folder '{safe_name}'."
            on_created()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=12)
        ttk.Button(button_frame, text="Create", command=submit).pack(side="left", padx=6)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=6)
        dialog.bind("<Return>", lambda _e: submit())

    def _prompt_emu_root_folder(self, parent_dir: Path):
        dialog = tk.Toplevel(self)
        dialog.title("Create Emulators Folder")
        dialog.geometry("390x160")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="Choose the emulator root folder name:").pack(
            pady=(16, 4), padx=12, anchor="w"
        )
        selection = tk.StringVar(value=EMU_ROOT_CREATE_OPTIONS[0])
        combo = ttk.Combobox(
            dialog,
            textvariable=selection,
            values=EMU_ROOT_CREATE_OPTIONS,
            state="readonly",
        )
        combo.pack(padx=12, fill="x")
        combo.focus()

        ttk.Label(
            dialog,
            text="Use a recognized name so the scanner can rediscover it automatically.",
            wraplength=360,
        ).pack(pady=(8, 0), padx=12, anchor="w")

        def submit():
            try:
                (parent_dir / selection.get()).mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror("Folder Error", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._next_status_message = f"Created emulator root folder '{selection.get()}'."
            self._scan_all()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=12)
        ttk.Button(button_frame, text="Create", command=submit).pack(side="left", padx=6)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=6)
        dialog.bind("<Return>", lambda _e: submit())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SF3000GameManager()
    app.mainloop()
