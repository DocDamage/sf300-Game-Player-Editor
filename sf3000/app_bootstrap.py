from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path
from typing import List, Optional

from sf3000.app_constants import APP_CACHE_DIR, METADATA_CACHE_DIR
from sf3000.layout import find_dev_reference_repo, safe_exists
from sf3000.models import (
    BrowserSessionState,
    OperationSessionState,
    UIRuntimeState,
)
from sf3000.runtime_env import (
    append_runtime_log,
    current_window_title,
    install_runtime_monitoring,
    running_frozen,
)

class SF3000BootstrapMixin:
    def __init__(self, *, auto_startup: bool = True):
        install_runtime_monitoring()
        super().__init__()
        self._ui_state = UIRuntimeState()
        self._bootstrap_window()
        self._bootstrap_load_settings()
        self._bootstrap_initialize_state()
        self._bootstrap_prepare_cache_dirs()
        self._bootstrap_build_ui()
        if auto_startup:
            self._bootstrap_finish_startup()

    def _bootstrap_window(self):
        self.title(current_window_title())
        self.geometry("1180x720")
        self.minsize(900, 560)
        self.protocol("WM_DELETE_WINDOW", self._on_close_app)
        append_runtime_log(
            "Application starting."
            + (" [frozen build]" if running_frozen() else " [source debug build]")
        )

    def _bootstrap_load_settings(self):
        self._loaded_state = self._load_settings()
        saved_geometry = self._loaded_state.get("geometry")
        if isinstance(saved_geometry, str) and saved_geometry:
            try:
                self.geometry(saved_geometry)
            except Exception:
                pass

    def _bootstrap_initialize_state(self):
        self._sd_path = tk.StringVar(value=self._loaded_state.get("sd_path", ""))
        self._status = tk.StringVar(value="Select your SF3000 SD card drive to get started.")
        self._copy_mode = tk.StringVar(value=self._loaded_state.get("copy_mode", "copy"))
        self._delete_to_recycle = tk.BooleanVar(
            value=bool(self._loaded_state.get("delete_to_recycle", True))
        )
        self._read_only_mode = tk.BooleanVar(
            value=bool(self._loaded_state.get("read_only_mode", False))
        )
        self._game_filter_var = tk.StringVar(value=self._loaded_state.get("game_filter", ""))
        self._emu_filter_var = tk.StringVar(value=self._loaded_state.get("emu_filter", ""))

        self._browser_state = BrowserSessionState(
            pending_system_selection=self._loaded_state.get("system_selection", "__all__"),
            pending_emu_selection=self._loaded_state.get("emu_selection", "__emu_all__"),
        )
        self._session_state = OperationSessionState(
            undo_cache_root=Path(tempfile.mkdtemp(prefix="sf3000-undo-"))
        )
        self._dev_reference_repo = find_dev_reference_repo()

        self._game_sort_column = "name"
        self._game_sort_reverse = False
        self._emu_sort_column = "name"
        self._emu_sort_reverse = False

        self._pending_tab_index = int(self._loaded_state.get("tab_index", 0))

    def _bootstrap_prepare_cache_dirs(self):
        try:
            APP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            METADATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _bootstrap_build_ui(self):
        self._configure_style()
        self._build_ui()
        self._build_context_menus()
        self._register_drop_targets()
        self._bind_shortcuts()
        self._install_tooltips()
        self._configure_tree_appearance()
        self._update_write_controls()

        self._game_filter_var.trace_add("write", self._on_game_filter_change)
        self._emu_filter_var.trace_add("write", self._on_emu_filter_change)
        self._read_only_mode.trace_add("write", lambda *_args: self._on_read_only_change())

    def _bootstrap_finish_startup(self):
        if self._ui_state.startup_complete:
            return

        self._ui_state.startup_complete = True
        self._refresh_drive_choices()
        self._notebook.select(min(self._pending_tab_index, self._notebook.index("end") - 1))
        self._prune_old_metadata_cache()
        self._log_event("session", "Application started.")

        selected_path = self._sd_path.get().strip()
        if selected_path and safe_exists(Path(selected_path)):
            self._scan_all()
        else:
            self._auto_detect_drive()
