from __future__ import annotations

import shutil
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import List, Optional, Tuple

from sf3000.app_constants import MAX_HISTORY_ENTRIES
from sf3000.layout import safe_exists, slugify_filename
from sf3000.models import (
    CreateFoldersHistoryPayload,
    DeleteHistoryPayload,
    HistoryEntry,
    HistoryPayload,
    RenameHistoryPayload,
    TransferHistoryPayload,
    history_payload_workspace,
)


class SF3000HistoryMixin:
    def _begin_history_action(self, prefix: str) -> Tuple[int, Path]:
        session = self._session_state
        session.history_counter += 1
        action_dir = session.undo_cache_root / f"{prefix}-{session.history_counter:04d}"
        action_dir.mkdir(parents=True, exist_ok=True)
        return session.history_counter, action_dir

    def _make_stash_path(self, action_dir: Path, original: Path, index: int) -> Path:
        suffix = "".join(original.suffixes) or original.suffix
        base = slugify_filename(original.stem or original.name, default="file")
        return action_dir / f"{index:04d}-{base}{suffix}"

    def _stash_file_copy(self, source: Path, action_dir: Path, index: int) -> Path:
        stash_path = self._make_stash_path(action_dir, source, index)
        shutil.copy2(str(source), str(stash_path))
        return stash_path

    def _record_history_entry(
        self,
        category: str,
        title: str,
        detail: str = "",
        *,
        entry_id: Optional[int] = None,
        undoable: bool = False,
        undo_type: str = "",
        payload: Optional[HistoryPayload] = None,
    ) -> HistoryEntry:
        session = self._session_state
        if entry_id is None:
            session.history_counter += 1
            entry_id = session.history_counter
        entry = HistoryEntry(
            entry_id=entry_id,
            time_text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            category=category.upper(),
            title=title,
            detail=detail.strip(),
            undoable=undoable,
            undo_type=undo_type,
            payload=payload,
        )
        session.history_entries.append(entry)
        if len(session.history_entries) > MAX_HISTORY_ENTRIES:
            dropped = session.history_entries.pop(0)
            workspace = history_payload_workspace(dropped.payload)
            if workspace is not None:
                shutil.rmtree(workspace, ignore_errors=True)
        return entry

    def _history_status_text(self, entry: HistoryEntry) -> str:
        if entry.undone:
            return "Undone"
        if entry.failed:
            return "Undo Failed"
        if entry.undoable:
            return "Undo Ready"
        return "Info"

    def _latest_undoable_entry(self) -> Optional[HistoryEntry]:
        for entry in reversed(self._session_state.history_entries):
            if entry.undoable and not entry.undone:
                return entry
        return None

    def _cleanup_history_workspace(self, entry: HistoryEntry):
        workspace = history_payload_workspace(entry.payload)
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)

    def _undo_last_action(self):
        if not self._ensure_writable("Undo"):
            return
        entry = self._latest_undoable_entry()
        if entry is None:
            self._show_toast("No undoable changes are available in this session.", kind="info")
            return
        self._undo_history_entry(entry)

    def _undo_history_entry(self, entry: HistoryEntry):
        if not self._ensure_writable("Undo"):
            return
        if not entry.undoable:
            messagebox.showinfo("Undo", "That history item does not have an undo action.")
            return
        if entry.undone:
            messagebox.showinfo("Undo", "That history item has already been undone.")
            return

        errors: List[str] = []
        touched_paths: List[Path] = []
        payload = entry.payload

        if entry.undo_type == "rename_files":
            if not isinstance(payload, RenameHistoryPayload):
                errors.append("Rename history payload is missing or invalid.")
            else:
                for item in reversed(payload.pairs):
                    source = item.source
                    destination = item.destination
                    touched_paths.extend([source, destination])
                    if not safe_exists(destination):
                        errors.append(f"Missing renamed file: {destination.name}")
                        continue
                    if safe_exists(source):
                        errors.append(f"Original name already exists: {source.name}")
                        continue
                    try:
                        destination.rename(source)
                    except Exception as exc:
                        errors.append(f"{destination.name}: {exc}")

        elif entry.undo_type == "create_folders":
            if not isinstance(payload, CreateFoldersHistoryPayload):
                errors.append("Folder history payload is missing or invalid.")
            else:
                for folder in reversed(payload.paths):
                    touched_paths.append(folder)
                    if not safe_exists(folder):
                        continue
                    try:
                        folder.rmdir()
                    except Exception as exc:
                        errors.append(f"{folder.name}: {exc}")

        elif entry.undo_type == "transfer_files":
            if not isinstance(payload, TransferHistoryPayload):
                errors.append("Transfer history payload is missing or invalid.")
            else:
                mode = payload.mode
                for item in reversed(payload.items):
                    destination = item.destination
                    backup = item.backup
                    source_origin = item.source_origin
                    created = item.created
                    touched_paths.append(destination)
                    if source_origin is not None:
                        touched_paths.append(source_origin)
                    if backup is not None:
                        touched_paths.append(backup)

                    if mode == "move":
                        if source_origin is None:
                            errors.append(f"Missing original source path for {destination.name}")
                            continue
                        if safe_exists(source_origin):
                            errors.append(f"Source already exists: {source_origin}")
                            continue
                        if not safe_exists(destination):
                            errors.append(f"Imported file is missing: {destination}")
                            continue
                        try:
                            source_origin.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(destination), str(source_origin))
                        except Exception as exc:
                            errors.append(f"{destination.name}: {exc}")
                            continue
                        if backup is not None and backup.exists():
                            try:
                                backup_destination = destination
                                backup_destination.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(str(backup), str(backup_destination))
                            except Exception as exc:
                                errors.append(f"Restore backup for {destination.name}: {exc}")
                        elif not created and backup is None:
                            errors.append(f"Missing original backup for {destination.name}")
                    else:
                        if created:
                            if safe_exists(destination):
                                try:
                                    destination.unlink()
                                except Exception as exc:
                                    errors.append(f"{destination.name}: {exc}")
                        else:
                            if backup is None or not backup.exists():
                                errors.append(f"Missing original backup for {destination.name}")
                                continue
                            try:
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(str(backup), str(destination))
                            except Exception as exc:
                                errors.append(f"{destination.name}: {exc}")

        elif entry.undo_type == "delete_files":
            if not isinstance(payload, DeleteHistoryPayload):
                errors.append("Delete history payload is missing or invalid.")
            else:
                for item in reversed(payload.items):
                    path = item.path
                    backup = item.backup
                    touched_paths.extend([path, backup])
                    if safe_exists(path):
                        errors.append(f"Path already exists: {path}")
                        continue
                    if not backup.exists():
                        errors.append(f"Deleted backup is missing: {path.name}")
                        continue
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(backup), str(path))
                    except Exception as exc:
                        errors.append(f"{path.name}: {exc}")

        if errors:
            entry.failed = True
            entry.failure_detail = "\n".join(errors[:20])
            self._invalidate_hash_cache(touched_paths)
            self._log_event("error", f"Undo failed for '{entry.title}'.", entry.failure_detail)
            messagebox.showerror("Undo Failed", entry.failure_detail)
            return

        entry.undone = True
        entry.failed = False
        entry.failure_detail = ""
        self._cleanup_history_workspace(entry)
        self._invalidate_hash_cache(touched_paths)
        self._browser_state.next_status_message = f"Undid '{entry.title}'."
        self._log_event("undo", f"Undid '{entry.title}'.")
        self._scan_all()

    def _history_detail_text(self, entry: HistoryEntry) -> str:
        lines = [
            f"Time: {entry.time_text}",
            f"Category: {entry.category}",
            f"Status: {self._history_status_text(entry)}",
            f"Action: {entry.title}",
        ]
        if entry.detail:
            lines.extend(["", entry.detail])
        if entry.failure_detail:
            lines.extend(["", "Undo Failure", entry.failure_detail])
        if entry.undoable and not entry.undone:
            lines.extend(["", "This change can be undone while the app stays open."])
        return "\n".join(lines)

    def _refresh_history_tree_widget(self, tree, detail_box=None):
        previous = tree.selection()
        tree.delete(*tree.get_children(""))
        for entry in reversed(self._session_state.history_entries):
            preview = entry.detail.replace("\n", " | ") if entry.detail else ""
            tree.insert(
                "",
                "end",
                iid=str(entry.entry_id),
                values=(
                    entry.time_text,
                    entry.category,
                    self._history_status_text(entry),
                    entry.title,
                    preview[:120],
                ),
            )
        if previous:
            for iid in previous:
                if tree.exists(iid):
                    tree.selection_set(iid)
                    tree.see(iid)
                    break
        elif tree.get_children(""):
            first = tree.get_children("")[0]
            tree.selection_set(first)
            tree.focus(first)
        if detail_box is not None:
            selection = tree.selection()
            if selection:
                self._update_history_detail_box(detail_box, selection[0])

    def _update_history_detail_box(self, detail_box, entry_iid: str):
        entry = next(
            (
                item
                for item in self._session_state.history_entries
                if str(item.entry_id) == str(entry_iid)
            ),
            None,
        )
        detail_box.configure(state="normal")
        detail_box.delete("1.0", "end")
        if entry is not None:
            detail_box.insert("1.0", self._history_detail_text(entry))
        detail_box.configure(state="disabled")

    def _show_history_dialog(self):
        ui_state = self._ui_state
        if ui_state.history_dialog and ui_state.history_dialog.winfo_exists():
            ui_state.history_dialog.deiconify()
            ui_state.history_dialog.lift()
            return

        dialog = tk.Toplevel(self)
        dialog.title("History And Undo")
        dialog.geometry("880x560")
        dialog.minsize(760, 460)
        dialog.transient(self)
        ui_state.history_dialog = dialog

        ttk.Label(dialog, text="Change History", style="Title.TLabel").pack(
            anchor="w", padx=14, pady=(14, 6)
        )
        ttk.Label(
            dialog,
            text="Undo is session-based. Reversible changes stay available until the app closes.",
            style="Hint.TLabel",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        container = ttk.Frame(dialog, padding=(14, 0, 14, 12))
        container.pack(fill="both", expand=True)

        tree = ttk.Treeview(
            container,
            columns=("time", "category", "status", "action", "detail"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        for column, heading, width in (
            ("time", "Time", 150),
            ("category", "Category", 90),
            ("status", "Status", 110),
            ("action", "Action", 300),
            ("detail", "Detail", 220),
        ):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=80)
        tree.pack(fill="both", expand=True, side="top")

        scroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

        ttk.Label(container, text="Selected Entry Details", style="Title.TLabel").pack(
            anchor="w", pady=(10, 4)
        )
        detail_box = tk.Text(
            container,
            wrap="word",
            relief="solid",
            borderwidth=1,
            background="#ffffff",
            font="TkFixedFont",
            padx=8,
            pady=8,
            height=10,
        )
        detail_box.pack(fill="both", expand=False)
        detail_box.configure(state="disabled")

        def refresh():
            self._refresh_history_tree_widget(tree, detail_box)

        def undo_selected():
            selection = tree.selection()
            if not selection:
                return
            entry = next(
                (
                    item
                    for item in self._session_state.history_entries
                    if str(item.entry_id) == selection[0]
                ),
                None,
            )
            if entry is None:
                return
            self._undo_history_entry(entry)
            refresh()

        tree.bind(
            "<<TreeviewSelect>>",
            lambda _e: self._update_history_detail_box(detail_box, tree.selection()[0]) if tree.selection() else None,
        )

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(buttons, text="Undo Selected", command=undo_selected).pack(side="left")
        ttk.Button(
            buttons,
            text="Undo Last",
            command=lambda: (self._undo_last_action(), refresh()),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Refresh", command=refresh).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="right")

        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.bind("<Destroy>", lambda _e: setattr(self._ui_state, "history_dialog", None), add="+")
        refresh()
