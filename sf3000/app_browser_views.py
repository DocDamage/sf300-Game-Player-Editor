from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from sf3000.layout import record_matches_query
from sf3000.models import FileRecord, FolderSummaryRow, StorageUsageSnapshot
from sf3000.ui_common import format_size


class SF3000BrowserViewsMixin:
    def _populate_system_tree(self, rows: Sequence[FolderSummaryRow], roms_root: Path):
        self._sys_tree.delete(*self._sys_tree.get_children())
        self._sys_tree.insert("", "end", iid="__all__", text="All Systems", values=[str(roms_root)])
        for row in rows:
            text = f"  {row.name}  ({row.count})"
            if row.issues:
                text += f"  [{row.issues} issues]"
            self._sys_tree.insert("", "end", iid=row.path, text=text, values=[row.path])

    def _populate_emu_tree(
        self,
        rows: Sequence[FolderSummaryRow],
        emu_root: Optional[Path],
        root_count: int,
    ):
        state = self._browser_state
        self._emu_folder_tree.delete(*self._emu_folder_tree.get_children())
        if emu_root is None:
            self._emu_path_label.config(
                text="Emulators folder: (not found -- create one with 'New Emulator Folder')",
                foreground="gray",
            )
            return

        self._emu_path_label.config(text=f"Emulators folder: {emu_root}", foreground="black")
        total_count = len(state.emu_records_by_key.get("__emu_all__", []))
        self._emu_folder_tree.insert(
            "",
            "end",
            iid="__emu_all__",
            text=f"All Emulators  ({total_count})",
            values=[str(emu_root)],
        )

        if root_count:
            root_issues = sum(
                1 for record in state.emu_records_by_key.get("__emu_root__", []) if record.warning
            )
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
            text = f"  {row.name}  ({row.count})"
            if row.issues:
                text += f"  [{row.issues} issues]"
            self._emu_folder_tree.insert("", "end", iid=row.path, text=text, values=[row.path])

    def _update_storage_from_usage(self, usage: Optional[StorageUsageSnapshot]):
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
        state = self._browser_state
        state.current_emu_key = "__emu_all__"
        state.current_emu_label = ""
        state.current_emu_records = []
        state.emu_visible_map.clear()
        self._emu_tree.delete(*self._emu_tree.get_children())
        if self._notebook.index(self._notebook.select()) == 1:
            self._set_status("No Emulators folder found on the selected device.")

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
            return self._browser_state.pending_system_selection
        iid = selection[0]
        return iid if iid == "__all__" else Path(iid).name

    def _current_emu_selection_key(self) -> str:
        selection = self._emu_folder_tree.selection()
        if not selection:
            return self._browser_state.pending_emu_selection
        iid = selection[0]
        return iid if iid.startswith("__") else Path(iid).name

    def _set_status(self, text: str):
        self._status.set(text)
        if hasattr(self, "_invalidate_diagnostics_cache"):
            self._invalidate_diagnostics_cache()

    def _game_status_text(self) -> str:
        state = self._browser_state
        visible_count = len(state.game_visible_map)
        issue_count = sum(1 for record in state.game_visible_map.values() if record.warning)
        suffix = ""
        if (
            state.device_layout
            and state.device_layout.probable_sf3000
            and state.device_layout.using_root_fallback
        ):
            suffix = " | root scan fallback"
        if self._game_filter_var.get().strip():
            return (
                f"Showing {visible_count} of {len(state.current_game_records)} game file(s) in "
                f"'{state.current_game_label}' | {issue_count} warning(s){suffix}."
            )
        return f"{visible_count} game file(s) in '{state.current_game_label}' | {issue_count} warning(s){suffix}."

    def _emu_status_text(self) -> str:
        state = self._browser_state
        visible_count = len(state.emu_visible_map)
        issue_count = sum(1 for record in state.emu_visible_map.values() if record.warning)
        layout_issue_count = len(self._device_layout_validation_issues(include_emulators=True))
        suffix = f" | {layout_issue_count} layout issue(s)" if layout_issue_count else ""
        if self._emu_filter_var.get().strip():
            return (
                f"Showing {visible_count} of {len(state.current_emu_records)} emulator file(s) in "
                f"'{state.current_emu_label}' | {issue_count} warning(s){suffix}."
            )
        return f"{visible_count} emulator file(s) in '{state.current_emu_label}' | {issue_count} warning(s){suffix}."

    def _refresh_active_status(self):
        state = self._browser_state
        if self._notebook.index(self._notebook.select()) == 0:
            if state.current_game_label:
                self._set_status(self._game_status_text())
            return
        if state.current_emu_label:
            self._set_status(self._emu_status_text())
        elif state.emu_root is None:
            self._set_status("No Emulators folder found on the selected device.")

    def _on_system_select(self, _event=None):
        state = self._browser_state
        selection = self._sys_tree.selection()
        if not selection:
            return

        iid = selection[0]
        state.current_game_key = iid
        state.pending_system_selection = iid if iid == "__all__" else Path(iid).name
        state.current_game_records = list(state.game_records_by_key.get(iid, []))
        state.current_game_label = "All Systems" if iid == "__all__" else Path(iid).name
        self._refresh_game_tree()

    def _on_game_filter_change(self, *_args):
        self._refresh_game_tree()

    def _refresh_game_tree(self):
        state = self._browser_state
        previous_selection = self._game_tree.selection()
        self._game_tree.delete(*self._game_tree.get_children())
        state.game_visible_map.clear()

        if not state.current_game_label:
            return

        visible_records = [
            record
            for record in state.current_game_records
            if record_matches_query(record, self._game_filter_var.get().strip())
        ]
        visible_records = self._sorted_game_records(visible_records)

        for index, record in enumerate(visible_records):
            iid = str(record.path)
            state.game_visible_map[iid] = record
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
            key=lambda record: self._record_sort_value(
                record,
                self._game_sort_column,
                game_mode=True,
            ),
            reverse=self._game_sort_reverse,
        )

    def _sort_games(self, column: str):
        if self._game_sort_column == column:
            self._game_sort_reverse = not self._game_sort_reverse
        else:
            self._game_sort_column = column
            self._game_sort_reverse = False
        self._refresh_game_tree()

    def _on_emu_folder_select(self, _event=None):
        state = self._browser_state
        selection = self._emu_folder_tree.selection()
        if not selection:
            return

        iid = selection[0]
        state.current_emu_key = iid
        state.pending_emu_selection = iid if iid.startswith("__") else Path(iid).name
        state.current_emu_records = list(state.emu_records_by_key.get(iid, []))
        if iid == "__emu_all__":
            state.current_emu_label = "All Emulators"
        elif iid == "__emu_root__":
            state.current_emu_label = "/ (root)"
        else:
            state.current_emu_label = Path(iid).name
        self._refresh_emu_tree()

    def _on_emu_filter_change(self, *_args):
        self._refresh_emu_tree()

    def _refresh_emu_tree(self):
        state = self._browser_state
        previous_selection = self._emu_tree.selection()
        self._emu_tree.delete(*self._emu_tree.get_children())
        state.emu_visible_map.clear()

        if not state.current_emu_label:
            return

        visible_records = [
            record
            for record in state.current_emu_records
            if record_matches_query(record, self._emu_filter_var.get().strip())
        ]
        visible_records = self._sorted_emu_records(visible_records)

        for index, record in enumerate(visible_records):
            iid = str(record.path)
            state.emu_visible_map[iid] = record
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
            key=lambda record: self._record_sort_value(
                record,
                self._emu_sort_column,
                game_mode=False,
            ),
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
