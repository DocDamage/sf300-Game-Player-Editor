from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from sf3000.app_constants import APP_CACHE_DIR
from sf3000.archive_utils import inspect_restore_archive
from sf3000.device_mount import (
    choose_auto_mount_candidate,
    discover_mount_candidates,
    eject_drive_letter,
    extract_drive_letter,
    run_elevated_wsl_unmount,
)
from sf3000.layout import (
    create_temp_destination,
    iter_files_recursive,
    safe_exists,
    _safe_destroy,
)
from sf3000.models import TransferHistoryItem, TransferHistoryPayload
from sf3000.ui_common import ProgressDialog


class SF3000DeviceToolsMixin:
    def _pyinstaller_available(self) -> bool:
        return importlib.util.find_spec("PyInstaller") is not None

    def _finish_windows_build(self, ok: bool, output_path: str, log_path: str, detail: str):
        self._set_scanning(False)
        if ok:
            self._show_toast(
                f"Windows build created at '{Path(output_path).name}'.",
                kind="success",
                duration_ms=4200,
            )
            self._log_event("build", "Built Windows package.", detail)
            self._record_history_entry("build", "Built Windows package.", detail)
            if messagebox.askyesno(
                "Build Complete",
                f"The Windows package was created successfully.\n\nOutput:\n{output_path}\n\nOpen the output folder?",
            ):
                self._reveal_path_in_explorer(Path(output_path))
            return

        self._show_toast("Windows build failed.", kind="error", duration_ms=4200)
        self._log_event("error", "Windows build failed.", detail)
        messagebox.showerror(
            "Build Failed",
            f"PyInstaller could not finish building the Windows package.\n\nLog:\n{log_path}\n\n{detail}",
        )

    def _build_windows_exe(self):
        choice = messagebox.askyesnocancel(
            "Build Windows EXE",
            "Build a single-file executable?\n\nYes: Single EXE\nNo: Portable folder build\nCancel: Do nothing",
        )
        if choice is None:
            return
        onefile = bool(choice)
        install_needed = not self._pyinstaller_available()

        if install_needed and not messagebox.askyesno(
            "Install PyInstaller",
            "PyInstaller is not installed for this Python. Install it automatically now?",
        ):
            return

        mode_text = "single-file EXE" if onefile else "portable folder build"
        self._set_scanning(True, f"Building {mode_text}...", action_text="Building...")

        def worker():
            log_lines = []
            log_path = APP_CACHE_DIR / "last-build.log"
            project_dir = Path(__file__).resolve().parent.parent
            entry_script = project_dir / "sf3000_manager.py"
            output_dir = project_dir / "dist"
            output_dir.mkdir(parents=True, exist_ok=True)
            build_dir = project_dir / "build" / "pyinstaller"
            spec_dir = project_dir / "build" / "spec"
            build_dir.mkdir(parents=True, exist_ok=True)
            spec_dir.mkdir(parents=True, exist_ok=True)

            try:
                if not entry_script.exists():
                    raise FileNotFoundError(f"Entry script not found: {entry_script}")

                if install_needed:
                    install_cmd = [sys.executable, "-m", "pip", "install", "pyinstaller"]
                    install_proc = subprocess.run(
                        install_cmd,
                        cwd=str(project_dir),
                        capture_output=True,
                        text=True,
                        timeout=1800,
                    )
                    log_lines.append("$ " + " ".join(install_cmd))
                    log_lines.append(install_proc.stdout)
                    log_lines.append(install_proc.stderr)
                    if install_proc.returncode != 0:
                        raise RuntimeError("PyInstaller installation failed.")

                cmd = [
                    sys.executable,
                    "-m",
                    "PyInstaller",
                    "--noconfirm",
                    "--clean",
                    "--windowed",
                    "--name",
                    "SF3000 Game Manager",
                    "--distpath",
                    str(output_dir),
                    "--workpath",
                    str(build_dir),
                    "--specpath",
                    str(spec_dir),
                ]
                if onefile:
                    cmd.append("--onefile")
                if importlib.util.find_spec("tkinterdnd2") is not None:
                    cmd.extend(["--collect-all", "tkinterdnd2"])
                cmd.append(str(entry_script))

                proc = subprocess.run(
                    cmd,
                    cwd=str(project_dir),
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
                log_lines.append("$ " + " ".join(cmd))
                log_lines.append(proc.stdout)
                log_lines.append(proc.stderr)
                log_path.write_text("\n".join(log_lines), encoding="utf-8")
                if proc.returncode != 0:
                    raise RuntimeError("PyInstaller returned a non-zero exit code.")

                output_path = output_dir / (
                    "SF3000 Game Manager.exe" if onefile else "SF3000 Game Manager"
                )
                detail = f"Mode: {mode_text}\nOutput: {output_path}\nLog: {log_path}"
                return True, str(output_path), str(log_path), detail
            except Exception as exc:
                try:
                    log_path.write_text("\n".join(log_lines), encoding="utf-8")
                except Exception:
                    pass
                detail = f"{exc}\n\nMode: {mode_text}"
                return False, "", str(log_path), detail

        self._run_background_task(
            worker,
            on_success=lambda result: self._finish_windows_build(*result),
            on_error=lambda exc: self._finish_windows_build(
                False,
                "",
                str(APP_CACHE_DIR / "last-build.log"),
                str(exc),
            ),
        )

    def _show_device_health(self):
        self._show_text_viewer(
            title="Device Health",
            heading="Device Health And Diagnostics",
            text_provider=self._diagnostics_text,
            export_title="Export Diagnostics",
            export_name=f"sf3000-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
            async_text_provider=self._request_diagnostics_text,
        )

    def _export_diagnostics(self):
        self._request_diagnostics_text(
            lambda value: self._export_text_content(
                "Export Diagnostics",
                f"sf3000-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
                value,
            ),
            force_refresh=True,
        )

    def _reset_device_views(self):
        state = self._browser_state
        state.roms_root = None
        state.emu_root = None
        state.device_layout = None
        state.core_catalog = None
        state.game_records_by_key.clear()
        state.emu_records_by_key.clear()
        state.game_visible_map.clear()
        state.emu_visible_map.clear()
        state.current_game_key = "__all__"
        state.current_emu_key = "__emu_all__"
        state.current_game_records = []
        state.current_emu_records = []
        state.current_game_label = ""
        state.current_emu_label = ""
        self._sys_tree.delete(*self._sys_tree.get_children())
        self._game_tree.delete(*self._game_tree.get_children())
        self._emu_folder_tree.delete(*self._emu_folder_tree.get_children())
        self._emu_tree.delete(*self._emu_tree.get_children())
        self._emu_path_label.config(text="Emulators folder: (not found)", foreground="gray")
        self._storage_bar["value"] = 0
        self._storage_label.config(text="")

    def _safe_eject_device(self):
        raw = self._sd_path.get().strip()
        if not raw:
            messagebox.showinfo("Safe Eject", "Select or mount a device first.")
            return

        candidate = None
        try:
            candidate = choose_auto_mount_candidate(discover_mount_candidates(raw), raw)
        except Exception:
            candidate = None

        drive_letter = candidate.drive_letter if candidate else extract_drive_letter(raw)
        if candidate is None and not drive_letter:
            messagebox.showinfo(
                "Safe Eject / Unmount",
                "The current path is a regular folder, so there is no removable device to eject.",
            )
            return
        summary = [f"Current path: {raw}"]
        if candidate is not None:
            summary.append(
                f"Target: Disk {candidate.disk_number} / Partition {candidate.partition_number} ({candidate.friendly_name})"
            )
        elif drive_letter:
            summary.append(f"Target drive: {drive_letter}:\\")
        else:
            summary.append("Target: current mounted path")

        if not messagebox.askyesno(
            "Safe Eject / Unmount",
            "The app will close its view of the current device, unmount any WSL-backed disk, "
            "and try to eject a removable drive when possible.\n\n"
            + "\n".join(summary)
            + "\n\nContinue?",
            icon="warning",
        ):
            return

        self._log_event("device", "Starting safe eject / unmount.", raw)
        self._set_scanning(True, "Safely ejecting the current device...", action_text="Working...")

        def worker():
            details = []
            ok = True

            if candidate is not None:
                ok, message = run_elevated_wsl_unmount(candidate.physical_drive)
                if not ok:
                    return False, message
                details.append(
                    f"Unmounted WSL disk {candidate.disk_number} / partition {candidate.partition_number}."
                )

            if drive_letter:
                eject_ok, eject_message = eject_drive_letter(drive_letter)
                if eject_ok:
                    details.append(f"Ejected {drive_letter}:\\ safely.")
                else:
                    details.append(f"Could not fully eject {drive_letter}:\\ ({eject_message}).")

            return ok, "\n".join(details).strip()

        self._run_background_task(
            worker,
            on_success=lambda result: self._handle_safe_eject_result(*result),
            on_error=lambda exc: self._handle_safe_eject_result(False, str(exc)),
        )

    def _handle_safe_eject_result(self, ok: bool, detail: str):
        self._set_scanning(False)
        if ok:
            self._reset_device_views()
            self._sd_path.set("")
            self._refresh_drive_choices()
            self._set_status(
                "The current device has been unmounted and can be removed when Windows says it is safe."
            )
            self._show_toast("The current device has been unmounted.", kind="success")
            self._log_event("device", "Safe eject / unmount completed.", detail)
            if detail:
                messagebox.showinfo("Safe Eject / Unmount", detail)
            return

        self._set_status("Safe eject / unmount failed.")
        self._show_toast("Safe eject / unmount failed.", kind="error")
        self._log_event("error", "Safe eject / unmount failed.", detail)
        messagebox.showerror(
            "Safe Eject / Unmount",
            detail or "Could not safely eject the current device.",
        )

    def _backup_device(self):
        raw = self._sd_path.get().strip()
        if not raw or not safe_exists(Path(raw)):
            messagebox.showwarning("Backup Device", "Select or mount a device first.")
            return

        root = Path(raw)
        files = iter_files_recursive(root)
        if not files:
            messagebox.showinfo(
                "Backup Device",
                "No files were found to back up in the current device.",
            )
            return

        suggested = f"sf3000-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        archive_path = filedialog.asksaveasfilename(
            title="Create Device Backup",
            defaultextension=".zip",
            initialfile=suggested,
            filetypes=[("ZIP Archive", "*.zip"), ("All Files", "*.*")],
        )
        if not archive_path:
            return

        if not messagebox.askyesno(
            "Create Device Backup",
            f"Create a ZIP backup of {len(files)} file(s) from:\n{root}\n\nArchive:\n{archive_path}\n\nContinue?",
        ):
            return

        dialog = ProgressDialog(self, "Creating Backup")
        self._set_scanning(
            True,
            f"Creating backup '{Path(archive_path).name}'...",
            action_text="Backing Up...",
        )

        def worker():
            errors = []
            processed = 0
            cancelled = False
            archive = Path(archive_path)

            try:
                with zipfile.ZipFile(
                    archive,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    allowZip64=True,
                ) as bundle:
                    for index, path in enumerate(files, start=1):
                        if dialog.cancelled:
                            cancelled = True
                            break
                        self._queue_ui(
                            dialog.update_progress,
                            index,
                            len(files),
                            str(path),
                            "Backing Up",
                        )
                        try:
                            bundle.write(path, arcname=path.relative_to(root).as_posix())
                            processed += 1
                        except Exception as exc:
                            errors.append(f"{path.name}: {exc}")
            except Exception as exc:
                errors.append(str(exc))

            if cancelled and safe_exists(Path(archive_path)):
                try:
                    Path(archive_path).unlink()
                except OSError:
                    pass

            return archive_path, processed, errors, cancelled

        def finish(result):
            _safe_destroy(dialog)
            self._finish_backup_operation(*result)

        def fail(exc: Exception):
            _safe_destroy(dialog)
            self._finish_backup_operation(archive_path, 0, [str(exc)], False)

        self._run_background_task(worker, on_success=finish, on_error=fail)

    def _finish_backup_operation(
        self,
        archive_path: str,
        processed: int,
        errors: list[str],
        cancelled: bool,
    ):
        self._set_scanning(False)
        if errors:
            messagebox.showerror("Backup Errors", "\n".join(errors[:20]))
        if cancelled:
            self._set_status("Backup canceled.")
            self._show_toast("Backup canceled.", kind="warning")
            self._log_event("backup", "Backup canceled.", f"Archive: {archive_path}")
            return
        self._set_status(
            f"Created backup '{Path(archive_path).name}' with {processed} file(s)."
        )
        self._show_toast(
            f"Created backup '{Path(archive_path).name}'.",
            kind="success",
        )
        self._log_event(
            "backup",
            f"Created backup '{Path(archive_path).name}'.",
            f"Files: {processed}",
        )
        self._record_history_entry(
            "backup",
            f"Created backup '{Path(archive_path).name}'.",
            f"Files: {processed}",
        )

    def _restore_backup(self):
        if not self._ensure_writable("Restore Backup"):
            return

        raw = self._sd_path.get().strip()
        if not raw or not safe_exists(Path(raw)):
            messagebox.showwarning("Restore Backup", "Select or mount a device first.")
            return

        archive_path = filedialog.askopenfilename(
            title="Select Backup ZIP",
            filetypes=[("ZIP Archive", "*.zip"), ("All Files", "*.*")],
        )
        if not archive_path:
            return

        root = Path(raw)
        try:
            with zipfile.ZipFile(archive_path, "r") as bundle:
                inspection = inspect_restore_archive(bundle)
        except Exception as exc:
            messagebox.showerror("Restore Backup", str(exc))
            self._log_event("error", "Restore inspection failed.", str(exc))
            return

        valid_members = inspection.valid_members
        skipped_members = inspection.skipped_members
        if not valid_members:
            messagebox.showwarning(
                "Restore Backup",
                "The selected ZIP file does not contain any restorable files.",
            )
            return

        summary = [
            f"Backup archive: {archive_path}",
            f"Destination: {root}",
            f"Files to restore: {len(valid_members)}",
        ]
        if skipped_members:
            summary.append(f"Unsafe or invalid paths skipped: {len(skipped_members)}")

        if not messagebox.askyesno(
            "Restore Backup",
            "Restoring will overwrite files with matching paths on the current device.\n\n"
            + "\n".join(summary)
            + "\n\nContinue?",
            icon="warning",
        ):
            return

        dialog = ProgressDialog(self, "Restoring Backup")
        self._set_scanning(
            True,
            f"Restoring backup '{Path(archive_path).name}'...",
            action_text="Restoring...",
        )
        action_id, action_dir = self._begin_history_action("restore")

        def worker():
            errors = []
            restored = 0
            cancelled = False
            history_items = []
            touched_paths: list[Path] = []

            try:
                with zipfile.ZipFile(archive_path, "r") as bundle:
                    for index, (info, rel_path) in enumerate(valid_members, start=1):
                        if dialog.cancelled:
                            cancelled = True
                            break
                        destination = root / rel_path
                        self._queue_ui(
                            dialog.update_progress,
                            index,
                            len(valid_members),
                            str(destination),
                            "Restoring",
                        )
                        try:
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            created = not safe_exists(destination)
                            backup_path = ""
                            if not created:
                                backup_path = str(
                                    self._stash_file_copy(destination, action_dir, index)
                                )
                            temp_path = create_temp_destination(
                                destination.parent,
                                destination.suffix,
                            )
                            try:
                                with bundle.open(info, "r") as source, temp_path.open("wb") as target:
                                    shutil.copyfileobj(source, target, length=1024 * 1024)
                                self._replace_destination_with_temp(temp_path, destination)
                            except Exception:
                                if safe_exists(temp_path):
                                    try:
                                        temp_path.unlink()
                                    except OSError:
                                        pass
                                raise
                            history_items.append(
                                TransferHistoryItem(
                                    destination=destination,
                                    created=created,
                                    backup=Path(backup_path) if backup_path else None,
                                    source_origin=None,
                                )
                            )
                            touched_paths.append(destination)
                            restored += 1
                        except Exception as exc:
                            errors.append(f"{info.filename}: {exc}")
            except Exception as exc:
                errors.append(str(exc))

            return archive_path, restored, errors, cancelled, history_items, touched_paths

        def finish(result):
            (
                result_archive_path,
                restored,
                errors,
                cancelled,
                history_items,
                touched_paths,
            ) = result
            _safe_destroy(dialog)
            if history_items:
                self._record_history_entry(
                    "change",
                    f"Restored {restored} file(s) from '{Path(result_archive_path).name}'.",
                    f"Files: {restored} | Errors: {len(errors)}",
                    entry_id=action_id,
                    undoable=True,
                    undo_type="transfer_files",
                    payload=TransferHistoryPayload(
                        workspace=action_dir,
                        mode="restore",
                        items=history_items,
                    ),
                )
            else:
                shutil.rmtree(action_dir, ignore_errors=True)
            self._invalidate_hash_cache(touched_paths)
            self._finish_restore_operation(result_archive_path, restored, errors, cancelled)

        def fail(exc: Exception):
            _safe_destroy(dialog)
            shutil.rmtree(action_dir, ignore_errors=True)
            self._finish_restore_operation(archive_path, 0, [str(exc)], False)

        self._run_background_task(worker, on_success=finish, on_error=fail)

    def _finish_restore_operation(
        self,
        archive_path: str,
        restored: int,
        errors: list[str],
        cancelled: bool,
    ):
        self._set_scanning(False)
        if errors:
            messagebox.showerror("Restore Errors", "\n".join(errors[:20]))
        if cancelled:
            self._set_status("Restore canceled.")
            self._show_toast("Restore canceled.", kind="warning")
            self._log_event("restore", "Restore canceled.", f"Archive: {archive_path}")
            return
        self._browser_state.next_status_message = (
            f"Restored {restored} file(s) from '{Path(archive_path).name}'."
        )
        self._log_event(
            "restore",
            f"Restored '{Path(archive_path).name}'.",
            f"Files: {restored}",
        )
        self._scan_all()

    def _sync_games_from_folder(self):
        if not self._ensure_writable("Sync Games"):
            return

        selection = self._sys_tree.selection()
        if not selection or selection[0] == "__all__":
            messagebox.showinfo(
                "Select a System",
                "Select a specific system folder first, then use Sync Folder.",
            )
            return

        source_folder = filedialog.askdirectory(
            title="Select PC Folder To Sync Into This System"
        )
        if not source_folder:
            return

        files = [str(path) for path in iter_files_recursive(Path(source_folder))]
        if not files:
            messagebox.showinfo(
                "Sync Games",
                "No files were found in the selected source folder.",
            )
            return

        self._log_event(
            "sync",
            f"Syncing games from '{Path(source_folder).name}' into '{Path(selection[0]).name}'.",
            f"Source files scanned: {len(files)}",
        )
        self._import_game_files(files, Path(selection[0]))

    def _sync_emulators_from_folder(self):
        if not self._ensure_writable("Sync Emulators"):
            return

        if self._browser_state.emu_root is None:
            messagebox.showinfo(
                "No Emulators Folder",
                "No Emulators folder was found on the current device.",
            )
            return

        selection = self._emu_folder_tree.selection()
        if selection and selection[0] not in ("__emu_all__", "__emu_root__"):
            dest_folder = Path(selection[0])
        else:
            dest_folder = self._browser_state.emu_root

        source_folder = filedialog.askdirectory(
            title="Select PC Folder To Sync Into This Emulator Folder"
        )
        if not source_folder:
            return

        files = [str(path) for path in iter_files_recursive(Path(source_folder))]
        if not files:
            messagebox.showinfo(
                "Sync Emulators",
                "No files were found in the selected source folder.",
            )
            return

        self._log_event(
            "sync",
            f"Syncing emulators from '{Path(source_folder).name}' into '{dest_folder.name}'.",
            f"Source files scanned: {len(files)}",
        )
        self._import_emulator_files(files, dest_folder)
