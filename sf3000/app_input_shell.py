from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class SF3000InputShellMixin:
    def _bind_shortcuts(self):
        bindings = {
            "<Control-r>": self._scan_all,
            "<F5>": self._scan_all,
            "<Control-z>": self._undo_last_action,
            "<Control-m>": self._shortcut_mount_linux,
            "<Control-j>": self._show_selected_metadata,
            "<Control-Shift-e>": self._safe_eject_device,
            "<Control-Shift-g>": self._show_duplicate_manager,
            "<Control-Shift-h>": self._show_device_health,
            "<Control-Shift-x>": self._build_windows_exe,
            "<Control-Shift-y>": self._show_history_dialog,
            "<Control-Shift-b>": self._backup_device,
            "<Control-Shift-r>": self._restore_backup,
            "<Control-Shift-s>": self._sync_current_folder,
            "<Control-Alt-l>": self._show_activity_log,
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

    def _shortcuts_enabled(self) -> bool:
        grabbed = self.grab_current()
        return not self._ui_state.is_closing and grabbed in (None, self)

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

    def _shortcut_mount_linux(self):
        self._mount_linux_sd(user_initiated=True, preferred_path=self._sd_path.get().strip())

    def _sync_current_folder(self):
        if self._notebook.index(self._notebook.select()) == 0:
            self._sync_games_from_folder()
        else:
            self._sync_emulators_from_folder()

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
        toast_window = self._ui_state.toast_window
        if toast_window and toast_window.winfo_exists():
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
