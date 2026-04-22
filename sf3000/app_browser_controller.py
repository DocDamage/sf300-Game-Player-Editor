from __future__ import annotations

import os
import shutil
import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Sequence

from sf3000.device_mount import (
    build_wsl_unc_paths,
    choose_auto_mount_candidate,
    discover_mount_candidates,
    drive_needs_wsl_mount,
    extract_drive_letter,
    is_wsl_path,
    list_wsl_distros,
    run_elevated_windows_disk_recovery,
    run_elevated_wsl_mount,
    wake_wsl_backend,
)
from sf3000.layout import (
    build_emulator_warning,
    build_file_record,
    build_game_warning,
    get_windows_drives,
    inspect_device_layout,
    iter_game_folders,
    list_child_dirs,
    list_child_files,
    load_core_catalog,
    normalize_sf3000_root,
    safe_exists,
)
from sf3000.models import (
    EmulatorScanBucket,
    FileRecord,
    FolderSummaryRow,
    GameScanBucket,
    MountCandidate,
    ScanPayload,
    StorageUsageSnapshot,
)
from sf3000.ui_common import format_size


class SF3000BrowserControllerMixin:
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
        current = self._sd_path.get().strip()

        if current and is_wsl_path(current):
            wake_wsl_backend()
            if safe_exists(Path(current)):
                self._scan_all()
                return

        for drive in drives:
            if not safe_exists(Path(drive)):
                continue
            layout = inspect_device_layout(Path(drive))
            if layout.probable_sf3000 or not layout.using_root_fallback:
                self._sd_path.set(drive)
                self._scan_all()
                return

        if current and safe_exists(Path(current)) and not drive_needs_wsl_mount(current):
            self._sd_path.set(current)
            return

        self._mount_linux_sd(
            user_initiated=False,
            preferred_path=current,
            allow_choice=False,
            quiet_if_none=True,
        )

    def _browse_path(self):
        path = filedialog.askdirectory(title="Select SF3000 SD Card Root Folder")
        if path:
            self._sd_path.set(path)
            self._scan_all()

    def _format_mount_candidate(self, candidate: MountCandidate) -> str:
        drive_text = f"{candidate.drive_letter}:\\" if candidate.drive_letter else "No Windows letter"
        filesystem = candidate.filesystem or candidate.partition_type or "RAW / Linux"
        if candidate.is_offline:
            filesystem = f"{filesystem} | Offline"
        return (
            f"Disk {candidate.disk_number}, Partition {candidate.partition_number} | "
            f"{drive_text} | {format_size(candidate.size)} | {filesystem} | {candidate.friendly_name}"
        )

    def _prompt_mount_candidate(
        self,
        candidates: Sequence[MountCandidate],
    ) -> Optional[MountCandidate]:
        dialog = tk.Toplevel(self)
        dialog.title("Choose Linux SD Card")
        dialog.geometry("840x300")
        dialog.minsize(760, 260)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="Choose the Linux or RAW partition to mount with WSL:",
            style="Title.TLabel",
        ).pack(anchor="w", padx=14, pady=(14, 8))

        content = ttk.Frame(dialog, padding=(14, 0, 14, 12))
        content.pack(fill="both", expand=True)

        tree = ttk.Treeview(
            content,
            columns=("disk", "drive", "size", "filesystem", "device"),
            show="headings",
            selectmode="browse",
        )
        tree.heading("disk", text="Disk / Partition")
        tree.heading("drive", text="Drive")
        tree.heading("size", text="Size")
        tree.heading("filesystem", text="Windows View")
        tree.heading("device", text="Device")
        tree.column("disk", width=120, minwidth=100)
        tree.column("drive", width=90, minwidth=70, anchor="center")
        tree.column("size", width=90, minwidth=70, anchor="e")
        tree.column("filesystem", width=120, minwidth=100, anchor="center")
        tree.column("device", width=360, minwidth=220)

        scroll_y = ttk.Scrollbar(content, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        for index, candidate in enumerate(candidates):
            tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    f"Disk {candidate.disk_number} / P{candidate.partition_number}",
                    f"{candidate.drive_letter}:\\" if candidate.drive_letter else "--",
                    format_size(candidate.size),
                    candidate.filesystem or "RAW / Linux",
                    candidate.friendly_name,
                ),
            )

        if candidates:
            tree.selection_set("0")
            tree.focus("0")
            tree.see("0")

        chosen: Dict[str, Optional[MountCandidate]] = {"value": None}

        def submit():
            selection = tree.selection()
            if not selection:
                return
            chosen["value"] = candidates[int(selection[0])]
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=(0, 12))
        ttk.Button(button_frame, text="Mount", command=submit).pack(side="left", padx=6)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left", padx=6)
        tree.bind("<Double-1>", lambda _e: submit())
        dialog.bind("<Return>", lambda _e: submit())
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

        self.wait_window(dialog)
        return chosen["value"]

    def _mount_linux_sd(
        self,
        user_initiated: bool = False,
        preferred_path: str = "",
        allow_choice: bool = True,
        quiet_if_none: bool = False,
    ) -> bool:
        if self._browser_state.scan_in_progress or self._ui_state.is_closing:
            return False

        self._set_scanning(True, "Looking for Linux SD cards...", action_text="Working...")

        def worker():
            distros = list_wsl_distros()
            if not distros:
                return (
                    [],
                    "",
                    preferred_path,
                    user_initiated,
                    allow_choice,
                    quiet_if_none,
                    "WSL is not available or no Linux distribution is installed.",
                )

            candidates = discover_mount_candidates(preferred_path)
            return (
                candidates,
                distros[0],
                preferred_path,
                user_initiated,
                allow_choice,
                quiet_if_none,
                "",
            )

        self._run_background_task(
            worker,
            on_success=lambda result: self._handle_mount_discovery_result(*result),
            on_error=lambda exc: self._handle_mount_discovery_result(
                [],
                "",
                preferred_path,
                user_initiated,
                allow_choice,
                quiet_if_none,
                str(exc),
            ),
        )
        return True

    def _handle_mount_discovery_result(
        self,
        candidates: Sequence[MountCandidate],
        distro_name: str,
        preferred_path: str,
        user_initiated: bool,
        allow_choice: bool,
        quiet_if_none: bool,
        error_message: str,
    ):
        if error_message:
            self._set_scanning(False)
            self._set_status("Could not inspect Linux SD card devices.")
            self._show_toast("Could not inspect Linux SD card devices.", kind="error")
            self._log_event("error", "Linux SD card discovery failed.", error_message)
            if user_initiated or not quiet_if_none:
                messagebox.showerror("Load SD Card", error_message)
            return

        candidate = choose_auto_mount_candidate(candidates, preferred_path)
        if candidate is None and candidates and allow_choice:
            self._set_scanning(False)
            candidate = self._prompt_mount_candidate(candidates)
            if candidate is None:
                self._set_status("Linux SD mount canceled.")
                self._show_toast("Linux SD mount canceled.", kind="warning")
                self._log_event("mount", "Linux SD mount canceled.")
                return

        if candidate is None:
            self._set_scanning(False)
            if candidates and not allow_choice:
                message = "Multiple storage devices were found. Click 'Load SD Card' to choose one."
            else:
                message = "No Linux or RAW SD card candidates were found."
            self._set_status(message)
            self._show_toast(message, kind="warning")
            self._log_event("mount", message)
            if user_initiated and not quiet_if_none:
                messagebox.showinfo("Load SD Card", message)
            return

        if candidate.windows_recoverable:
            self._set_scanning(
                True,
                f"Recovering {self._format_mount_candidate(candidate)} for Windows...",
                action_text="Working...",
            )
            self._recover_windows_candidate_async(candidate)
            return

        self._set_scanning(
            True,
            f"Mounting {self._format_mount_candidate(candidate)} via WSL...",
            action_text="Working...",
        )
        self._mount_candidate_async(candidate, distro_name)

    def _recover_windows_candidate_async(self, candidate: MountCandidate):
        self._run_background_task(
            lambda: run_elevated_windows_disk_recovery(candidate),
            on_success=lambda result: self._handle_windows_recovery_success(candidate, result[1])
            if result[0]
            else self._handle_windows_recovery_failure(candidate, result[2]),
            on_error=lambda exc: self._handle_windows_recovery_failure(candidate, str(exc)),
        )

    def _handle_windows_recovery_success(self, candidate: MountCandidate, drive_path: str):
        self._set_scanning(False)
        self._sd_path.set(drive_path)
        self._refresh_drive_choices()
        self._set_status(f"Recovered {candidate.friendly_name} as {drive_path}.")
        self._show_toast(f"Recovered {candidate.friendly_name} as {drive_path}.", kind="success")
        self._log_event(
            "mount",
            f"Recovered {candidate.friendly_name} for Windows access.",
            f"Disk {candidate.disk_number} / Partition {candidate.partition_number}\n{drive_path}",
        )
        self._scan_all()

    def _handle_windows_recovery_failure(self, candidate: MountCandidate, message: str):
        self._set_scanning(False)
        self._set_status("Could not recover the SD card for Windows access.")
        self._show_toast("Could not recover the SD card automatically.", kind="error")
        self._log_event(
            "error",
            f"Automatic Windows recovery failed for disk {candidate.disk_number}.",
            message,
        )
        messagebox.showerror(
            "Load SD Card",
            message
            + "\n\nTry this next:\n"
            + "- Approve the Windows UAC prompt if it appears.\n"
            + "- Safely reinsert the SD card if Windows still keeps it offline.\n"
            + "- If Windows assigns a new drive letter after reinserting it, select that drive and scan again.",
        )

    def _mount_candidate_async(self, candidate: MountCandidate, distro_name: str):
        def worker():
            mounted_paths = build_wsl_unc_paths(distro_name, candidate.mount_name)
            wake_wsl_backend()
            mounted_path = next((path for path in mounted_paths if safe_exists(path)), None)
            path_ready = mounted_path is not None
            ok = True
            error_message = ""

            if not path_ready:
                ok, error_message = run_elevated_wsl_mount(candidate)

            deadline = time.time() + 20
            while time.time() < deadline:
                wake_wsl_backend()
                for path in mounted_paths:
                    if safe_exists(path):
                        return True, str(path)
                time.sleep(1.0)

            if not error_message:
                error_message = (
                    "WSL did not expose the mounted SD card under:\n"
                    + "\n".join(str(path) for path in mounted_paths)
                    + "\n\nafter mounting "
                    f"{self._format_mount_candidate(candidate)}."
                )
            if not ok and "canceled" in error_message.casefold():
                error_message = "The Windows elevation prompt was canceled."
            return False, error_message

        self._run_background_task(
            worker,
            on_success=lambda result: self._handle_mount_success(candidate, result[1])
            if result[0]
            else self._handle_mount_failure(result[1]),
            on_error=lambda exc: self._handle_mount_failure(str(exc)),
        )

    def _handle_mount_success(self, candidate: MountCandidate, mounted_path: str):
        self._set_scanning(False)
        self._sd_path.set(mounted_path)
        self._refresh_drive_choices()
        self._set_status(f"Mounted {candidate.friendly_name} via WSL.")
        self._show_toast(f"Mounted {candidate.friendly_name} via WSL.", kind="success")
        self._log_event(
            "mount",
            f"Mounted {candidate.friendly_name} via WSL.",
            f"Disk {candidate.disk_number} / Partition {candidate.partition_number}\n{mounted_path}",
        )
        self._scan_all()

    def _handle_mount_failure(self, message: str):
        self._set_scanning(False)
        self._set_status("Could not mount the SD card automatically.")
        self._show_toast("Could not mount the SD card automatically.", kind="error")
        self._log_event("error", "Automatic SD card mount failed.", message)
        messagebox.showerror(
            "Load SD Card",
            message
            + "\n\nTry this next:\n"
            + "- Approve the Windows UAC prompt if it appears.\n"
            + "- Reinsert the SD card if another app is holding it open.\n"
            + "- If you mount it manually in WSL, scan the mounted path again.",
        )

    def _scan_all(self):
        state = self._browser_state
        raw = self._sd_path.get().strip()
        self._refresh_drive_choices()
        if not raw:
            self._set_status("Select an SD card path to scan.")
            return

        root = normalize_sf3000_root(Path(raw))
        if str(root) != raw:
            self._sd_path.set(str(root))
            raw = str(root)
        if is_wsl_path(raw):
            wake_wsl_backend()

        if extract_drive_letter(raw) and drive_needs_wsl_mount(raw):
            if self._mount_linux_sd(
                user_initiated=False,
                preferred_path=raw,
                allow_choice=True,
                quiet_if_none=False,
            ):
                return

        if not safe_exists(root):
            if (extract_drive_letter(raw) or is_wsl_path(raw)) and self._mount_linux_sd(
                user_initiated=False,
                preferred_path=raw,
                allow_choice=True,
                quiet_if_none=False,
            ):
                return
            messagebox.showerror(
                "Not Found",
                f"Path not found:\n{raw}\n\n"
                "Make sure the SD card is inserted and mounted.",
            )
            return

        state.pending_system_selection = self._current_system_selection_key()
        state.pending_emu_selection = self._current_emu_selection_key()
        state.pending_game_paths = list(self._game_tree.selection())
        state.pending_emu_paths = list(self._emu_tree.selection())

        state.scan_generation += 1
        generation = state.scan_generation
        self._set_scanning(True, f"Scanning {root}...")

        def worker():
            return self._collect_scan_payload(root)

        self._run_background_task(
            worker,
            on_success=lambda payload: self._apply_scan_payload(generation, payload),
            on_error=lambda exc: self._handle_scan_error(generation, str(exc)),
        )

    def _collect_scan_payload(self, root: Path) -> ScanPayload:
        layout = inspect_device_layout(root)
        catalog = load_core_catalog(layout)
        root = layout.root
        storage = None
        try:
            storage = StorageUsageSnapshot.from_usage(shutil.disk_usage(root))
        except Exception:
            storage = None

        roms_root = layout.roms_root
        game_folders = iter_game_folders(roms_root, layout, catalog)
        game_records_by_key: Dict[str, List[FileRecord]] = {"__all__": []}
        game_folder_rows = []

        for folder in game_folders:
            records = []
            for file_path in list_child_files(folder):
                try:
                    relative_path = str(file_path.relative_to(roms_root)).replace("\\", "/")
                except Exception:
                    relative_path = file_path.name
                warning = build_game_warning(file_path, folder.name, catalog, relative_path)
                records.append(build_file_record(file_path, file_path.stem, folder.name, warning))
            records.sort(key=lambda record: record.raw_name.casefold())
            game_records_by_key[str(folder)] = records
            game_records_by_key["__all__"].extend(records)
            game_folder_rows.append(
                FolderSummaryRow(
                    path=str(folder),
                    name=folder.name,
                    count=len(records),
                    issues=sum(1 for record in records if record.warning),
                )
            )

        game_records_by_key["__all__"].sort(
            key=lambda record: (record.parent_name.casefold(), record.raw_name.casefold())
        )

        emu_root = layout.emu_root
        emu_records_by_key: Dict[str, List[FileRecord]] = {
            "__emu_all__": [],
            "__emu_root__": [],
        }
        emu_folder_rows = []

        if emu_root is not None:
            root_records = []
            for file_path in list_child_files(emu_root):
                warning = build_emulator_warning(file_path, catalog)
                root_records.append(build_file_record(file_path, file_path.name, "/", warning))
            root_records.sort(key=lambda record: record.raw_name.casefold())
            emu_records_by_key["__emu_root__"] = root_records
            emu_records_by_key["__emu_all__"].extend(root_records)

            for folder in list_child_dirs(emu_root):
                records = []
                for file_path in list_child_files(folder):
                    warning = build_emulator_warning(file_path, catalog)
                    records.append(build_file_record(file_path, file_path.name, folder.name, warning))
                records.sort(key=lambda record: record.raw_name.casefold())
                emu_records_by_key[str(folder)] = records
                emu_records_by_key["__emu_all__"].extend(records)
                emu_folder_rows.append(
                    FolderSummaryRow(
                        path=str(folder),
                        name=folder.name,
                        count=len(records),
                        issues=sum(1 for record in records if record.warning),
                    )
                )

        emu_records_by_key["__emu_all__"].sort(
            key=lambda record: (record.parent_name.casefold(), record.raw_name.casefold())
        )

        return ScanPayload(
            root=root,
            layout=layout,
            core_catalog=catalog,
            storage=storage,
            games=GameScanBucket(
                roms_root=roms_root,
                folder_rows=game_folder_rows,
                records_by_key=game_records_by_key,
                total_files=len(game_records_by_key["__all__"]),
                issues=sum(1 for record in game_records_by_key["__all__"] if record.warning),
            ),
            emus=EmulatorScanBucket(
                emu_root=emu_root,
                folder_rows=emu_folder_rows,
                records_by_key=emu_records_by_key,
                root_count=len(emu_records_by_key["__emu_root__"]),
                total_files=len(emu_records_by_key["__emu_all__"]),
                issues=sum(1 for record in emu_records_by_key["__emu_all__"] if record.warning),
            ),
        )

    def _handle_scan_error(self, generation: int, message: str):
        if generation != self._browser_state.scan_generation:
            return
        self._set_scanning(False)
        messagebox.showerror("Scan Error", message)
        self._set_status("Scan failed.")
        self._show_toast("Scan failed. See the error dialog for details.", kind="error")
        self._log_event("error", "Scan failed.", message)

    def _apply_scan_payload(self, generation: int, payload: ScanPayload):
        state = self._browser_state
        if generation != state.scan_generation:
            return

        self._set_scanning(False)
        self._refresh_drive_choices()

        games = payload.games
        emus = payload.emus

        state.device_layout = payload.layout
        state.core_catalog = payload.core_catalog
        state.roms_root = games.roms_root
        state.emu_root = emus.emu_root
        state.game_records_by_key = games.records_by_key
        state.emu_records_by_key = emus.records_by_key

        self._populate_system_tree(games.folder_rows, state.roms_root)
        self._populate_emu_tree(emus.folder_rows, state.emu_root, emus.root_count)

        self._update_storage_from_usage(payload.storage)

        self._restore_tree_selection(self._sys_tree, state.pending_system_selection, "__all__")
        if state.emu_root is not None:
            self._restore_tree_selection(
                self._emu_folder_tree,
                state.pending_emu_selection,
                "__emu_all__",
            )

        self._on_system_select()
        if state.emu_root is not None:
            self._on_emu_folder_select()
        else:
            self._clear_emu_view()

        self._restore_file_selection(self._game_tree, state.pending_game_paths)
        self._restore_file_selection(self._emu_tree, state.pending_emu_paths)

        if state.next_status_message:
            self._set_status(state.next_status_message)
            self._show_toast(
                state.next_status_message,
                kind="warning" if "cancel" in state.next_status_message.casefold() else "success",
            )
            state.next_status_message = None
        else:
            self._refresh_active_status()
        self._log_event(
            "scan",
            f"Scanned '{payload.root}'.",
            (
                f"Games: {games.total_files} files, {games.issues} issues\n"
                f"Emulators: {emus.total_files} files, {emus.issues} issues"
                + (
                    f"\nCore definitions: {len(state.core_catalog.definitions)} | Overrides: {len(state.core_catalog.overrides)}"
                    if state.core_catalog is not None
                    else ""
                )
                + (
                    "\nLayout: " + ", ".join(state.device_layout.matched_signals)
                    if state.device_layout and state.device_layout.matched_signals
                    else ""
                )
            ),
        )

    def _set_scanning(self, scanning: bool, message: str = "", action_text: str = "Scanning..."):
        self._browser_state.scan_in_progress = scanning
        if scanning:
            self._scan_button.state(["disabled"])
            self._mount_button.state(["disabled"])
            self._browse_button.state(["disabled"])
            self._open_button.state(["disabled"])
            self._undo_button.state(["disabled"])
            self._tools_button.state(["disabled"])
            self._read_only_toggle.state(["disabled"])
            self._drive_combo.state(["disabled"])
            self._scan_button.configure(text=action_text)
            self._scan_progress.start(12)
            self.configure(cursor="watch")
            if message:
                self._set_status(message)
        else:
            self._scan_button.state(["!disabled"])
            self._mount_button.state(["!disabled"])
            self._browse_button.state(["!disabled"])
            self._open_button.state(["!disabled"])
            if not self._read_only_mode.get():
                self._undo_button.state(["!disabled"])
            self._tools_button.state(["!disabled"])
            self._read_only_toggle.state(["!disabled"])
            self._drive_combo.state(["!disabled"])
            self._scan_button.configure(text="Scan")
            self._scan_progress.stop()
            self.configure(cursor="")

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
            if self._browser_state.roms_root:
                self._reveal_path_in_explorer(self._browser_state.roms_root)
            return
        self._reveal_path_in_explorer(Path(iid))

    def _open_selected_emu_folder(self):
        selection = self._emu_folder_tree.selection()
        if not selection:
            return
        iid = selection[0]
        if iid in ("__emu_all__", "__emu_root__"):
            if self._browser_state.emu_root:
                self._reveal_path_in_explorer(self._browser_state.emu_root)
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
