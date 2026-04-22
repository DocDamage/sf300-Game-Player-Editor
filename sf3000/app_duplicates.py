from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Sequence

from sf3000.duplicate_service import find_duplicate_groups
from sf3000.layout import (
    build_file_record,
    safe_exists,
    safe_stat,
    same_path,
    _safe_destroy,
)
from sf3000.models import DuplicateGroup, FileRecord
from sf3000.ui_common import ProgressDialog, format_size


class SF3000DuplicateMixin:
    def _duplicate_source_records(self, scope: str) -> List[FileRecord]:
        state = self._browser_state
        if scope == "current":
            if self._notebook.index(self._notebook.select()) == 0:
                return list(state.game_visible_map.values()) or list(state.current_game_records)
            return list(state.emu_visible_map.values()) or list(state.current_emu_records)

        if scope == "tab":
            if self._notebook.index(self._notebook.select()) == 0:
                return list(state.game_records_by_key.get("__all__", []))
            return list(state.emu_records_by_key.get("__emu_all__", []))

        seen = set()
        result = []
        for record in list(state.game_records_by_key.get("__all__", [])) + list(
            state.emu_records_by_key.get("__emu_all__", [])
        ):
            key = str(record.path.resolve(strict=False)).casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(record)
        return result

    def _find_duplicate_groups(self, records: Sequence[FileRecord], progress=None, is_cancelled=None) -> List[DuplicateGroup]:
        return find_duplicate_groups(
            records,
            hash_getter=self._cached_file_hash,
            progress=progress,
            is_cancelled=is_cancelled,
        )

    def _show_duplicate_manager(self):
        ui_state = self._ui_state
        if ui_state.duplicate_dialog and ui_state.duplicate_dialog.winfo_exists():
            ui_state.duplicate_dialog.deiconify()
            ui_state.duplicate_dialog.lift()
            return

        dialog = tk.Toplevel(self)
        dialog.title("Duplicate Manager")
        dialog.geometry("980x620")
        dialog.minsize(860, 520)
        dialog.transient(self)
        ui_state.duplicate_dialog = dialog

        ttk.Label(dialog, text="Duplicate Manager", style="Title.TLabel").pack(
            anchor="w", padx=14, pady=(14, 6)
        )
        ttk.Label(
            dialog,
            text="This view hashes same-size files so duplicates are based on file contents, not names alone.",
            style="Hint.TLabel",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        controls = ttk.Frame(dialog, padding=(14, 0, 14, 8))
        controls.pack(fill="x")

        tab_name = "games" if self._notebook.index(self._notebook.select()) == 0 else "emulators"
        scope_var = tk.StringVar(value="current")
        ttk.Radiobutton(controls, text=f"Current {tab_name} view", variable=scope_var, value="current").pack(side="left")
        ttk.Radiobutton(controls, text=f"All {tab_name}", variable=scope_var, value="tab").pack(side="left", padx=(10, 0))
        ttk.Radiobutton(controls, text="Whole device", variable=scope_var, value="device").pack(side="left", padx=(10, 0))

        summary_var = tk.StringVar(value="Run a scan to find exact duplicate files.")
        ttk.Label(dialog, textvariable=summary_var, padding=(14, 0, 14, 6)).pack(anchor="w")

        pane = ttk.PanedWindow(dialog, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        group_frame = ttk.LabelFrame(pane, text="Duplicate Groups", padding=6)
        file_frame = ttk.LabelFrame(pane, text="Files In Selected Group", padding=6)
        pane.add(group_frame, weight=1)
        pane.add(file_frame, weight=2)

        group_list = tk.Listbox(group_frame, exportselection=False)
        group_list.pack(fill="both", expand=True)

        file_tree = ttk.Treeview(
            file_frame,
            columns=("name", "folder", "size", "modified", "action"),
            show="headings",
            selectmode="extended",
        )
        for column, heading, width in (
            ("name", "File", 280),
            ("folder", "Folder", 120),
            ("size", "Size", 90),
            ("modified", "Modified", 150),
            ("action", "Suggested", 110),
        ):
            file_tree.heading(column, text=heading)
            file_tree.column(column, width=width, minwidth=80)
        file_tree.pack(fill="both", expand=True)

        groups_state: Dict[str, object] = {"groups": []}

        def current_group() -> Optional[DuplicateGroup]:
            selection = group_list.curselection()
            if not selection:
                return None
            groups = groups_state.get("groups", [])
            if not isinstance(groups, list) or selection[0] >= len(groups):
                return None
            return groups[selection[0]]

        def refresh_file_tree(group: Optional[DuplicateGroup]):
            file_tree.delete(*file_tree.get_children(""))
            if group is None:
                return
            for index, path in enumerate(group.files):
                stat = safe_stat(path)
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d  %H:%M") if stat else ""
                suggestion = "Keep" if index == 0 else "Duplicate"
                file_tree.insert(
                    "",
                    "end",
                    iid=str(path),
                    values=(path.name, path.parent.name, format_size(stat.st_size if stat else 0), modified, suggestion),
                )
            select_recommended("newest")

        def refresh_groups(groups: Sequence[DuplicateGroup]):
            group_list.delete(0, "end")
            groups_state["groups"] = list(groups)
            if not groups:
                summary_var.set("No exact duplicates were found for the selected scope.")
                refresh_file_tree(None)
                return
            reclaim = sum(group.duplicate_bytes for group in groups)
            summary_var.set(
                f"Found {len(groups)} duplicate group(s). Potential reclaim space: {format_size(reclaim)}."
            )
            for group in groups:
                group_list.insert(
                    "end",
                    f"{group.label}  |  {len(group.files)} copies  |  reclaim {format_size(group.duplicate_bytes)}"
                )
            group_list.selection_set(0)
            refresh_file_tree(groups[0])

        def select_recommended(rule: str):
            group = current_group()
            if group is None:
                return
            paths = list(group.files)
            if rule == "oldest":
                paths.sort(key=lambda item: ((safe_stat(item).st_mtime if safe_stat(item) else 0), item.name.casefold()))
            elif rule == "shortest":
                paths.sort(key=lambda item: (len(item.name), item.name.casefold()))
            elif rule == "largest_name":
                paths.sort(key=lambda item: (-len(item.name), item.name.casefold()))
            file_tree.selection_remove(file_tree.selection())
            if len(paths) > 1:
                keep_path = paths[0]
                duplicates = [str(path) for path in group.files if not same_path(path, keep_path)]
                for iid in duplicates:
                    if file_tree.exists(iid):
                        file_tree.selection_add(iid)
                if duplicates:
                    file_tree.focus(duplicates[0])
                    file_tree.see(duplicates[0])

        def open_selected():
            selection = file_tree.selection()
            if not selection:
                return
            self._reveal_path_in_explorer(Path(selection[0]))

        def scan_duplicates():
            records = self._duplicate_source_records(scope_var.get())
            if not records:
                summary_var.set("No files are available in that scope.")
                refresh_groups([])
                return

            progress_dialog = ProgressDialog(dialog, "Scanning Duplicates")
            progress_dialog.transient(dialog)

            def worker():
                return self._find_duplicate_groups(
                    records,
                    progress=lambda value, maximum, path: self._queue_ui(
                        progress_dialog.update_progress,
                        value,
                        maximum,
                        path,
                        "Hashing",
                    ),
                    is_cancelled=lambda: progress_dialog.cancelled,
                )

            def finish(groups):
                _safe_destroy(progress_dialog)
                refresh_groups(groups)

            def fail(exc: Exception):
                _safe_destroy(progress_dialog)
                messagebox.showerror("Duplicate Scan Error", str(exc))

            self._run_background_task(worker, on_success=finish, on_error=fail)

        def delete_selected():
            selection = [Path(iid) for iid in file_tree.selection()]
            if not selection:
                return
            records = [build_file_record(path, path.stem, path.parent.name) for path in selection if safe_exists(path)]
            if not records:
                return
            if self._delete_records(records, "duplicate file(s)", confirm=True, title="Delete Duplicates"):
                scan_duplicates()

        group_list.bind("<<ListboxSelect>>", lambda _e: refresh_file_tree(current_group()))
        file_tree.bind("<Double-1>", lambda _e: open_selected())

        button_bar = ttk.Frame(dialog)
        button_bar.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(button_bar, text="Scan", command=scan_duplicates).pack(side="left")
        ttk.Button(button_bar, text="Keep Newest", command=lambda: select_recommended("newest")).pack(side="left", padx=(6, 0))
        ttk.Button(button_bar, text="Keep Oldest", command=lambda: select_recommended("oldest")).pack(side="left", padx=(6, 0))
        ttk.Button(button_bar, text="Keep Shortest Name", command=lambda: select_recommended("shortest")).pack(side="left", padx=(6, 0))
        ttk.Button(button_bar, text="Open Selected", command=open_selected).pack(side="left", padx=(10, 0))
        ttk.Button(button_bar, text="Delete Selected", command=delete_selected).pack(side="left", padx=(6, 0))
        ttk.Button(button_bar, text="Close", command=dialog.destroy).pack(side="right")

        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.bind("<Destroy>", lambda _e: setattr(self._ui_state, "duplicate_dialog", None), add="+")
