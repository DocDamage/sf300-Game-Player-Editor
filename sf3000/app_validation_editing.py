from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import List

from sf3000.layout import (
    catalog_override_for_relpath,
    clean_filename,
    format_name_list,
    get_core_catalog_issues,
    get_layout_issues,
    get_stock_cubegm_reference_issues,
    get_system_extensions,
    safe_exists,
    same_path,
    sanitize_windows_name,
)
from sf3000.models import FileRecord, RenameHistoryPair, RenameHistoryPayload


class SF3000ValidationEditingMixin:
    def _device_layout_validation_issues(
        self,
        include_games: bool = False,
        include_emulators: bool = False,
    ) -> List[str]:
        state = self._browser_state
        layout = state.device_layout
        if layout is None:
            return []

        issues = []
        if include_games and layout.probable_sf3000 and layout.using_root_fallback:
            issues.append(
                "No dedicated 'roms/' folder was found, so the app is scanning the device root and filtering out system folders."
            )

        if include_emulators:
            issues.extend(get_layout_issues(layout))
            issues.extend(get_stock_cubegm_reference_issues(layout))
            issues.extend(get_core_catalog_issues(layout, state.core_catalog))

        return issues

    def _validate_selected_games(self):
        state = self._browser_state
        records = self._selected_game_records() or list(state.game_visible_map.values())
        issues = self._device_layout_validation_issues(include_games=True)

        if state.current_game_key not in ("", "__all__"):
            folder_name = Path(state.current_game_key).name
            if get_system_extensions(folder_name) is None:
                has_override_match = False
                if state.roms_root is not None and state.core_catalog is not None:
                    for record in records:
                        try:
                            relpath = str(record.path.relative_to(state.roms_root)).replace("\\", "/")
                        except Exception:
                            relpath = record.raw_name
                        if catalog_override_for_relpath(state.core_catalog, relpath):
                            has_override_match = True
                            break
                if not has_override_match:
                    issues.append(f"Folder '{folder_name}' is not a recognized system alias.")

        for record in records:
            if record.warning:
                issues.append(f"{record.raw_name}: {record.warning}")
        issues = list(dict.fromkeys(issues))

        if not issues:
            self._show_toast(f"No issues found in '{state.current_game_label}'.", kind="success")
            self._log_event(
                "validate",
                f"Validated games in '{state.current_game_label}'.",
                "No issues found.",
            )
            return

        messagebox.showwarning(
            "Validation Results",
            f"Found {len(issues)} issue(s) in '{state.current_game_label}':\n\n"
            f"{format_name_list(issues, limit=18)}",
        )
        self._log_event(
            "validate",
            f"Validated games in '{state.current_game_label}'.",
            f"Issues found: {len(issues)}",
        )

    def _validate_selected_emulators(self):
        state = self._browser_state
        records = self._selected_emu_records() or list(state.emu_visible_map.values())
        issues = self._device_layout_validation_issues(include_emulators=True)
        issues.extend(f"{record.raw_name}: {record.warning}" for record in records if record.warning)
        issues = list(dict.fromkeys(issues))

        if not issues:
            self._show_toast(f"No issues found in '{state.current_emu_label}'.", kind="success")
            self._log_event(
                "validate",
                f"Validated emulators in '{state.current_emu_label}'.",
                "No issues found.",
            )
            return

        messagebox.showwarning(
            "Validation Results",
            f"Found {len(issues)} issue(s) in '{state.current_emu_label}':\n\n"
            f"{format_name_list(issues, limit=18)}",
        )
        self._log_event(
            "validate",
            f"Validated emulators in '{state.current_emu_label}'.",
            f"Issues found: {len(issues)}",
        )

    def _selected_game_records(self) -> List[FileRecord]:
        visible_map = self._browser_state.game_visible_map
        return [
            visible_map[iid]
            for iid in self._game_tree.selection()
            if iid in visible_map
        ]

    def _selected_emu_records(self) -> List[FileRecord]:
        visible_map = self._browser_state.emu_visible_map
        return [
            visible_map[iid]
            for iid in self._emu_tree.selection()
            if iid in visible_map
        ]

    def _rename_selected_games(self):
        records = self._selected_game_records()
        self._rename_single_record(records, "Rename Game File")

    def _rename_selected_emulators(self):
        records = self._selected_emu_records()
        self._rename_single_record(records, "Rename Emulator File")

    def _rename_single_record(self, records: List[FileRecord], title: str):
        if not self._ensure_writable(title):
            return
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
            self._record_history_entry(
                "change",
                f"Renamed '{record.raw_name}' to '{destination.name}'.",
                undoable=True,
                undo_type="rename_files",
                payload=RenameHistoryPayload(
                    pairs=[RenameHistoryPair(source=record.path, destination=destination)]
                ),
            )
            self._browser_state.next_status_message = f"Renamed '{record.raw_name}' to '{destination.name}'."
            self._log_event("rename", f"Renamed '{record.raw_name}' to '{destination.name}'.")
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
        if not self._ensure_writable("Clean Names"):
            return
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
        history_pairs = []
        for source, destination in proposed:
            try:
                source.rename(destination)
                history_pairs.append(RenameHistoryPair(source=source, destination=destination))
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")

        if errors:
            messagebox.showerror("Rename Errors", "\n".join(errors))

        if history_pairs:
            self._record_history_entry(
                "change",
                f"Cleaned names for {len(history_pairs)} file(s).",
                f"Files: {len(history_pairs)}",
                undoable=True,
                undo_type="rename_files",
                payload=RenameHistoryPayload(pairs=history_pairs),
            )

        self._browser_state.next_status_message = f"Cleaned names for {len(proposed) - len(errors)} file(s)."
        self._log_event(
            "rename",
            f"Cleaned names for {len(proposed) - len(errors)} file(s).",
            f"Planned: {len(proposed)} | Errors: {len(errors)}",
        )
        self._scan_all()
