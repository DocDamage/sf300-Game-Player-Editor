from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Sequence

from sf3000.app_constants import LOW_SPACE_WARNING_BYTES
from sf3000.layout import (
    ALL_ROM_EXTENSIONS,
    COMMON_SYSTEM_FOLDERS,
    EMULATOR_EXTENSIONS,
    EMU_ROOT_CREATE_OPTIONS,
    build_emulator_warning,
    build_game_warning,
    create_temp_destination,
    expand_game_import_files,
    files_are_identical,
    find_emulators_root,
    find_roms_root,
    format_name_list,
    get_system_extensions,
    is_emulator_file,
    safe_exists,
    safe_is_dir,
    safe_stat,
    same_drive,
    same_path,
    sanitize_windows_name,
    _safe_destroy,
)
from sf3000.models import (
    CreateFoldersHistoryPayload,
    DeleteHistoryItem,
    DeleteHistoryPayload,
    FileRecord,
    TransferHistoryItem,
    TransferHistoryPayload,
    TransferItem,
    TransferPlan,
)
from sf3000.ui_common import ProgressDialog, format_size
from sf3000.windows_fs import send_to_recycle_bin


class SF3000FileOpsMixin:
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

            items.append(
                TransferItem(
                    source=source,
                    destination=destination,
                    size=size,
                    overwrite=overwrite,
                )
            )

        return TransferPlan(
            items=items,
            skipped_identical=skipped_identical,
            skipped_same_path=skipped_same_path,
            overwrites=overwrites,
            total_bytes=total_bytes,
            required_bytes=required_bytes,
        )

    def _copy_files_to(self, files: Sequence[str], dest_folder: Path, on_done):
        state = self._browser_state
        if not self._ensure_writable("Import Files"):
            return

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
                + (
                    "move old files to Recycle Bin first"
                    if self._delete_to_recycle.get()
                    else "remove old files after replacement staging"
                )
            )
        if plan.skipped_identical:
            summary_lines.append(
                f"Content-identical files skipped: {len(plan.skipped_identical)}"
            )
        if usage is not None:
            summary_lines.append(f"Free space: {format_size(usage.free)}")
            summary_lines.append(
                f"Estimated space needed: {format_size(plan.required_bytes)}"
            )

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
        action_id, action_dir = self._begin_history_action("transfer")

        def worker():
            errors = []
            processed = 0
            history_items = []
            touched_paths: List[Path] = []

            for index, item in enumerate(plan.items, start=1):
                if dialog.cancelled:
                    break

                self._queue_ui(
                    dialog.update_progress,
                    index,
                    len(plan.items),
                    str(item.source),
                    verb,
                )
                try:
                    history_items.append(
                        self._execute_transfer_item(item, mode, action_dir, index)
                    )
                    touched_paths.extend([item.source, item.destination])
                    processed += 1
                except Exception as exc:
                    errors.append(f"{item.source.name}: {exc}")
            return {
                "errors": errors,
                "processed": processed,
                "history_items": history_items,
                "touched_paths": touched_paths,
                "cancelled": dialog.cancelled,
            }

        def finish(result):
            _safe_destroy(dialog)

            errors = result["errors"]
            processed = result["processed"]
            history_items = result["history_items"]
            touched_paths = result["touched_paths"]
            cancelled = result["cancelled"]

            if errors:
                messagebox.showerror("File Operation Errors", "\n".join(errors))

            if history_items:
                self._record_history_entry(
                    "change",
                    f"{mode.title()}ed {processed} file(s) to '{dest_folder.name}'.",
                    (
                        f"Planned: {len(plan.items)} | Overwrites: {len(plan.overwrites)} | "
                        f"Skipped identical: {len(plan.skipped_identical)} | Errors: {len(errors)}"
                    ),
                    entry_id=action_id,
                    undoable=True,
                    undo_type="transfer_files",
                    payload=TransferHistoryPayload(
                        workspace=action_dir,
                        mode=mode,
                        items=history_items,
                    ),
                )
            else:
                shutil.rmtree(action_dir, ignore_errors=True)

            self._invalidate_hash_cache(touched_paths)
            if cancelled:
                state.next_status_message = (
                    f"{mode.title()} cancelled after {processed} of {len(plan.items)} file(s)."
                )
            else:
                state.next_status_message = (
                    f"{mode.title()}ed {processed} file(s) to '{dest_folder.name}'."
                )

            self._log_event(
                "transfer",
                f"{mode.title()} {processed} file(s) to '{dest_folder.name}'.",
                (
                    f"Planned: {len(plan.items)} | Overwrites: {len(plan.overwrites)} | "
                    f"Skipped identical: {len(plan.skipped_identical)} | Errors: {len(errors)}"
                ),
            )
            on_done()

        def fail(exc: Exception):
            _safe_destroy(dialog)
            shutil.rmtree(action_dir, ignore_errors=True)
            messagebox.showerror("File Operation Errors", str(exc))

        self._run_background_task(worker, on_success=finish, on_error=fail)

    def _replace_destination_with_temp(self, temp_path: Path, destination: Path):
        if safe_exists(destination):
            if self._delete_to_recycle.get():
                send_to_recycle_bin(destination)
            else:
                destination.unlink()
        os.replace(temp_path, destination)

    def _execute_transfer_item(
        self,
        item: TransferItem,
        mode: str,
        action_dir: Path,
        index: int,
    ):
        item.destination.parent.mkdir(parents=True, exist_ok=True)
        created = not safe_exists(item.destination)
        backup_path = ""

        if item.overwrite:
            backup_path = str(self._stash_file_copy(item.destination, action_dir, index))

        if mode == "move" and not item.overwrite:
            shutil.move(str(item.source), str(item.destination))
            return TransferHistoryItem(
                destination=item.destination,
                created=created,
                backup=Path(backup_path) if backup_path else None,
                source_origin=item.source,
            )

        temp_path = create_temp_destination(item.destination.parent, item.destination.suffix)
        try:
            shutil.copy2(str(item.source), str(temp_path))
            self._replace_destination_with_temp(temp_path, item.destination)
            if mode == "move" and safe_exists(item.source):
                item.source.unlink()
            return TransferHistoryItem(
                destination=item.destination,
                created=created,
                backup=Path(backup_path) if backup_path else None,
                source_origin=item.source if mode == "move" else None,
            )
        except Exception:
            if safe_exists(temp_path):
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

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
        state = self._browser_state
        files = self._normalize_dropped_files(event.data)
        if not files:
            return
        if state.emu_root is None:
            messagebox.showinfo(
                "No Emulators Folder",
                "No Emulators folder found on the SD card.\nUse 'New Emulator Folder' to create one first.",
            )
            return
        selection = self._emu_folder_tree.selection()
        if selection and selection[0] not in ("__emu_all__", "__emu_root__"):
            dest_folder = Path(selection[0])
        else:
            dest_folder = state.emu_root
        self._import_emulator_files(files, dest_folder)

    def _import_game_files(self, files: Sequence[str], dest_folder: Path):
        state = self._browser_state
        files, auto_added = expand_game_import_files(files)
        accepted = []
        skipped = []
        warned = []
        for file_name in files:
            path = Path(file_name)
            relative_path = ""
            if state.roms_root is not None:
                try:
                    relative_path = str((dest_folder / path.name).relative_to(state.roms_root)).replace("\\", "/")
                except Exception:
                    relative_path = path.name
            warning = build_game_warning(
                path,
                dest_folder.name,
                state.core_catalog,
                relative_path,
            )
            if warning == "Unsupported ROM file":
                skipped.append(path.name)
                continue
            accepted.append(file_name)
            if warning:
                warned.append(f"{path.name}: {warning}")

        if auto_added:
            self._show_toast(
                f"Included {len(auto_added)} related disc/set file(s) automatically.",
                kind="info",
                duration_ms=3600,
            )
            self._log_event(
                "import",
                f"Expanded related game set files for '{dest_folder.name}'.",
                format_name_list(auto_added, limit=12),
            )

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
        state = self._browser_state
        accepted = []
        skipped = []
        warned = []
        for file_name in files:
            path = Path(file_name)
            warning = build_emulator_warning(path, state.core_catalog)
            if is_emulator_file(path):
                accepted.append(file_name)
                if warning:
                    warned.append(f"{path.name}: {warning}")
            else:
                skipped.append(path.name)

        if skipped:
            messagebox.showwarning(
                "Skipped Unsupported Files",
                "Only supported emulator file types were added.\n\n"
                + format_name_list(skipped),
            )

        if warned and not messagebox.askyesno(
            "Import With Warnings",
            "These emulator files can be imported, but they may not match the stock SF3000 setup cleanly:\n\n"
            + format_name_list(warned, limit=12)
            + "\n\nContinue?",
            icon="warning",
        ):
            return

        if accepted:
            self._copy_files_to(accepted, dest_folder, self._scan_all)

    def _add_games(self):
        state = self._browser_state
        selection = self._sys_tree.selection()
        if not selection or selection[0] == "__all__":
            messagebox.showinfo(
                "Select a System",
                "Please select a specific system folder in the left panel, then click Add Games.",
            )
            return

        dest_folder = Path(selection[0])
        allowed_extensions = get_system_extensions(dest_folder.name)
        if allowed_extensions:
            picker_extensions = allowed_extensions
        elif state.core_catalog and state.core_catalog.extensions_to_cores:
            picker_extensions = tuple(sorted(state.core_catalog.extensions_to_cores))
        else:
            picker_extensions = ALL_ROM_EXTENSIONS
        all_supported_extensions = tuple(
            sorted(
                set(ALL_ROM_EXTENSIONS) | set(state.core_catalog.extensions_to_cores)
                if state.core_catalog
                else set(ALL_ROM_EXTENSIONS)
            )
        )
        filetypes = [
            (
                f"{dest_folder.name} ROM Files",
                " ".join(f"*{ext}" for ext in picker_extensions),
            ),
            (
                "All Supported ROMs",
                " ".join(f"*{ext}" for ext in all_supported_extensions),
            ),
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
        state = self._browser_state
        raw = self._sd_path.get().strip()
        if not raw:
            messagebox.showwarning("No Drive", "Select the SD card drive first.")
            return

        if state.emu_root is None:
            messagebox.showinfo(
                "No Emulators Folder",
                "No Emulators folder found on the SD card.\nUse 'New Emulator Folder' to create one first.",
            )
            return

        selection = self._emu_folder_tree.selection()
        if selection and selection[0] not in ("__emu_all__", "__emu_root__"):
            dest_folder = Path(selection[0])
        else:
            dest_folder = state.emu_root

        files = filedialog.askopenfilenames(
            title=f"Select emulator file(s) to add to '{dest_folder.name}'",
            filetypes=[
                ("SF3000 Core Files", "*.so"),
                ("Emulator Files", " ".join(f"*{ext}" for ext in EMULATOR_EXTENSIONS)),
                ("All Files", "*.*"),
            ],
        )
        if not files:
            return
        self._import_emulator_files(files, dest_folder)

    def _delete_selected_games(self):
        records = self._selected_game_records()
        self._confirm_and_delete(records, "game file(s)")

    def _delete_selected_emulators(self):
        records = self._selected_emu_records()
        self._confirm_and_delete(records, "emulator file(s)")

    def _delete_records(
        self,
        records: List[FileRecord],
        label: str,
        *,
        confirm: bool = True,
        title: str = "Confirm Delete",
    ) -> bool:
        state = self._browser_state
        if not self._ensure_writable("Delete Files"):
            return False
        if not records:
            return False

        action_text = (
            "move to the Recycle Bin"
            if self._delete_to_recycle.get()
            else "permanently delete"
        )
        names = [record.raw_name for record in records]
        if confirm and not messagebox.askyesno(
            title,
            f"{action_text.title()} {len(records)} {label}?\n\n{format_name_list(names, limit=12)}",
            icon="warning",
        ):
            return False

        action_id, action_dir = self._begin_history_action("delete")
        errors = []
        history_items = []
        deleted_count = 0

        for index, record in enumerate(records, start=1):
            try:
                backup_path = self._stash_file_copy(record.path, action_dir, index)
                if self._delete_to_recycle.get():
                    send_to_recycle_bin(record.path)
                else:
                    record.path.unlink()
                history_items.append(DeleteHistoryItem(path=record.path, backup=backup_path))
                deleted_count += 1
            except Exception as exc:
                errors.append(f"{record.raw_name}: {exc}")

        if errors:
            messagebox.showerror("Delete Errors", "\n".join(errors))

        self._invalidate_hash_cache([record.path for record in records])
        if history_items:
            self._record_history_entry(
                "change",
                f"Deleted {deleted_count} {label}.",
                f"Requested: {len(records)} | Errors: {len(errors)}",
                entry_id=action_id,
                undoable=True,
                undo_type="delete_files",
                payload=DeleteHistoryPayload(workspace=action_dir, items=history_items),
            )
        else:
            shutil.rmtree(action_dir, ignore_errors=True)

        state.next_status_message = f"Deleted {deleted_count} {label}."
        self._log_event(
            "delete",
            f"Deleted {deleted_count} {label}.",
            f"Requested: {len(records)} | Errors: {len(errors)}",
        )
        self._scan_all()
        return True

    def _confirm_and_delete(self, records: List[FileRecord], label: str):
        self._delete_records(records, label, confirm=True, title="Confirm Delete")

    def _new_game_folder(self):
        if not self._ensure_writable("New System Folder"):
            return
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
        state = self._browser_state
        if not self._ensure_writable("Create Common Folders"):
            return
        raw = self._sd_path.get().strip()
        if not raw:
            messagebox.showwarning("No Drive", "Select the SD card drive first.")
            return

        roms_root = find_roms_root(Path(raw))
        missing = [
            name for name in COMMON_SYSTEM_FOLDERS if not safe_exists(roms_root / name)
        ]
        if not missing:
            self._show_toast("All common system folders already exist.", kind="info")
            return

        if not messagebox.askyesno(
            "Create Common Folders",
            "Create these folders?\n\n" + format_name_list(missing, limit=20),
        ):
            return

        errors = []
        created_paths = []
        for name in missing:
            try:
                path = roms_root / name
                path.mkdir(parents=True, exist_ok=True)
                created_paths.append(str(path))
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        if errors:
            messagebox.showerror("Folder Errors", "\n".join(errors))

        if created_paths:
            self._record_history_entry(
                "change",
                f"Created {len(created_paths)} common system folder(s).",
                undoable=True,
                undo_type="create_folders",
                payload=CreateFoldersHistoryPayload(paths=[Path(path) for path in created_paths]),
            )

        state.next_status_message = (
            f"Created {len(missing) - len(errors)} common system folder(s)."
        )
        self._log_event(
            "folder",
            f"Created {len(missing) - len(errors)} common system folder(s).",
            f"Requested: {len(missing)} | Errors: {len(errors)}",
        )
        self._scan_all()

    def _new_emu_folder(self):
        if not self._ensure_writable("New Emulator Folder"):
            return
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
        state = self._browser_state
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
            if not self._ensure_writable(title):
                return
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
                folder = parent_dir / safe_name
                existed_before = safe_exists(folder)
                folder.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror("Folder Error", str(exc), parent=dialog)
                return

            dialog.destroy()
            if not existed_before:
                self._record_history_entry(
                    "change",
                    f"Created folder '{safe_name}'.",
                    undoable=True,
                    undo_type="create_folders",
                    payload=CreateFoldersHistoryPayload(paths=[folder]),
                )
            state.next_status_message = f"Created folder '{safe_name}'."
            self._log_event(
                "folder",
                f"Created folder '{safe_name}'.",
                f"Parent: {parent_dir}",
            )
            on_created()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=12)
        ttk.Button(button_frame, text="Create", command=submit).pack(
            side="left", padx=6
        )
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=6
        )
        dialog.bind("<Return>", lambda _e: submit())

    def _prompt_emu_root_folder(self, parent_dir: Path):
        state = self._browser_state
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
            if not self._ensure_writable("Create Emulators Folder"):
                return
            try:
                folder = parent_dir / selection.get()
                existed_before = safe_exists(folder)
                folder.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                messagebox.showerror("Folder Error", str(exc), parent=dialog)
                return
            dialog.destroy()
            if not existed_before:
                self._record_history_entry(
                    "change",
                    f"Created emulator root folder '{selection.get()}'.",
                    undoable=True,
                    undo_type="create_folders",
                    payload=CreateFoldersHistoryPayload(paths=[folder]),
                )
            state.next_status_message = (
                f"Created emulator root folder '{selection.get()}'."
            )
            self._log_event(
                "folder",
                f"Created emulator root folder '{selection.get()}'.",
                f"Parent: {parent_dir}",
            )
            self._scan_all()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=12)
        ttk.Button(button_frame, text="Create", command=submit).pack(
            side="left", padx=6
        )
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=6
        )
        dialog.bind("<Return>", lambda _e: submit())
