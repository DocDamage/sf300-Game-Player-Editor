from __future__ import annotations

import os
import shutil
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sf3000.app_constants import MAX_LOG_ENTRIES, RUNTIME_LOG_FILE
from sf3000.device_mount import (
    choose_auto_mount_candidate,
    discover_mount_candidates,
    extract_drive_letter,
    get_drive_volume_state,
    is_wsl_path,
    list_wsl_distros,
)
from sf3000.layout import (
    find_dev_reference_repo,
    get_layout_issues,
    get_stock_cubegm_reference_issues,
    inspect_device_layout,
    list_child_files,
    safe_exists,
    same_path,
)
from sf3000.models import DiagnosticsContextSnapshot
from sf3000.runtime_env import TKDND_AVAILABLE
from sf3000.ui_common import format_size


class SF3000SupportMixin:
    def _invalidate_diagnostics_cache(self):
        session = self._session_state
        session.diagnostics_snapshot = None
        session.diagnostics_text_cache = ""
        session.diagnostics_request_token += 1

    def _log_event(self, category: str, message: str, detail: str = ""):
        session = self._session_state
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "category": category.upper(),
            "message": message,
            "detail": detail.strip(),
        }
        session.activity_log.append(entry)
        if len(session.activity_log) > MAX_LOG_ENTRIES:
            del session.activity_log[: len(session.activity_log) - MAX_LOG_ENTRIES]
        self._invalidate_diagnostics_cache()

    def _operation_log_text(self) -> str:
        lines = []
        for entry in self._session_state.activity_log:
            line = f"[{entry['time']}] {entry['category']}: {entry['message']}"
            if entry["detail"]:
                line += f"\n{entry['detail']}"
            lines.append(line)
        return "\n\n".join(lines) if lines else "No activity has been recorded yet."

    def _capture_diagnostics_context(self) -> DiagnosticsContextSnapshot:
        state = self._browser_state
        session = self._session_state
        return DiagnosticsContextSnapshot(
            generated_text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            path_text=self._sd_path.get().strip() or "(none)",
            read_only_mode=bool(self._read_only_mode.get()),
            copy_mode=self._copy_mode.get(),
            delete_to_recycle=bool(self._delete_to_recycle.get()),
            current_status=self._status.get(),
            roms_root=state.roms_root,
            emu_root=state.emu_root,
            dev_reference_repo=self._dev_reference_repo,
            device_layout=state.device_layout,
            core_catalog=state.core_catalog,
            activity_log=[dict(entry) for entry in session.activity_log],
        )

    def _operation_log_text_from_entries(self, entries) -> str:
        lines = []
        for entry in entries:
            line = f"[{entry['time']}] {entry['category']}: {entry['message']}"
            if entry["detail"]:
                line += f"\n{entry['detail']}"
            lines.append(line)
        return "\n\n".join(lines) if lines else "No activity has been recorded yet."

    def _build_diagnostics_text(self, snapshot: DiagnosticsContextSnapshot) -> str:
        path_text = snapshot.path_text
        path_kind = "WSL mount" if is_wsl_path(path_text) else ("Windows drive" if extract_drive_letter(path_text) else "Folder")
        lines = [
            "SF3000 Game Manager Diagnostics",
            f"Generated: {snapshot.generated_text}",
            "",
            f"Current path: {path_text}",
            f"Path type: {path_kind}",
            f"Read-only mode: {'On' if snapshot.read_only_mode else 'Off'}",
            f"Import mode: {snapshot.copy_mode}",
            f"Recycle deletes/overwrites: {'On' if snapshot.delete_to_recycle else 'Off'}",
            f"Current status: {snapshot.current_status}",
            f"WSL distros: {', '.join(list_wsl_distros()) or '(none detected)'}",
        ]

        layout = snapshot.device_layout
        try:
            storage_target = Path(path_text) if path_text and safe_exists(Path(path_text)) else None
        except Exception:
            storage_target = None
        if storage_target is not None:
            layout = layout or inspect_device_layout(storage_target)
            try:
                usage = shutil.disk_usage(storage_target)
            except Exception:
                usage = None
            if usage is not None:
                lines.append(
                    f"Storage: {format_size(usage.used)} used / {format_size(usage.total)} total / {format_size(usage.free)} free"
                )

        candidate = None
        try:
            candidates = discover_mount_candidates(path_text) if path_text else []
            candidate = choose_auto_mount_candidate(candidates, path_text)
        except Exception:
            candidate = None
        if candidate is not None:
            lines.extend(
                [
                    f"Disk candidate: Disk {candidate.disk_number} / Partition {candidate.partition_number}",
                    f"Candidate device: {candidate.friendly_name}",
                    f"Candidate bus: {candidate.bus_type}",
                    f"Candidate filesystem: {candidate.filesystem or 'RAW / Linux'}",
                ]
            )

        if extract_drive_letter(path_text):
            volume = get_drive_volume_state(path_text)
            if volume:
                lines.extend(
                    [
                        f"Drive health: {volume.get('HealthStatus') or 'Unknown'}",
                        f"Drive filesystem: {volume.get('FileSystem') or '(blank)'}",
                        f"Drive label: {volume.get('FileSystemLabel') or '(none)'}",
                    ]
                )

        catalog = snapshot.core_catalog
        if layout is not None:
            layout_state = "Confirmed" if layout.probable_sf3000 else "Partial / custom"
            lines.extend(
                [
                    f"SF3000 layout: {layout_state}",
                    f"Detected root: {layout.root}",
                    f"ROMs root: {layout.roms_root}",
                    f"Emulators root: {layout.emu_root or '(not found)'}",
                    f"Launcher root: {layout.cubegm_root or '(not found)'}",
                    f"Launcher file: {layout.launcher_path or '(missing)'}",
                    f"Launcher script: {layout.launcher_start_path or '(not found)'}",
                    f"Core config: {layout.core_config_path or '(missing)'}",
                    f"Core file list: {layout.core_filelist_path or '(missing)'}",
                ]
            )
            if layout.matched_signals:
                lines.append("Matched layout signals: " + ", ".join(layout.matched_signals))
            if layout.using_root_fallback:
                lines.append(
                    "ROM scan mode: using the device root because no dedicated roms/ folder was found."
                )
            layout_issues = get_layout_issues(layout)
            if layout_issues:
                lines.append("Layout issues:")
                lines.extend(f"- {issue}" for issue in layout_issues)
            stock_issues = get_stock_cubegm_reference_issues(layout)
            if stock_issues:
                lines.append("Stock cubegm reference gaps:")
                lines.extend(f"- {issue}" for issue in stock_issues[:12])
                if len(stock_issues) > 12:
                    lines.append(f"- ...and {len(stock_issues) - 12} more")

        if catalog is not None:
            extension_count = len(catalog.extensions_to_cores)
            custom_core_count = 0
            if layout and layout.emu_root:
                custom_core_count = sum(
                    1
                    for file_path in list_child_files(layout.emu_root)
                    if file_path.name.casefold().endswith("_libretro_sf3000.so")
                )
            lines.extend(
                [
                    f"Core definitions: {len(catalog.definitions)}",
                    f"Core-supported extensions: {extension_count}",
                    f"Per-game overrides: {len(catalog.overrides)}",
                    f"Custom sf3000 libretro cores: {custom_core_count}",
                ]
            )

            missing_core_binaries = []
            if layout and layout.emu_root:
                for definition in catalog.definitions:
                    if not safe_exists(layout.emu_root / definition.file_name):
                        missing_core_binaries.append(definition.file_name)

            unknown_override_cores = sorted(
                {
                    item.core_file
                    for item in catalog.overrides
                    if item.core_file.casefold() not in catalog.core_names_by_file
                }
            )

            if catalog.parse_errors:
                lines.append("Core catalog parse notes:")
                lines.extend(f"- {issue}" for issue in catalog.parse_errors)
            if missing_core_binaries:
                lines.append("Missing core binaries referenced by config.xml:")
                lines.extend(f"- {name}" for name in missing_core_binaries[:12])
                if len(missing_core_binaries) > 12:
                    lines.append(f"- ...and {len(missing_core_binaries) - 12} more")
            if unknown_override_cores:
                lines.append("Override cores not declared in config.xml:")
                lines.extend(f"- {name}" for name in unknown_override_cores[:12])
                if len(unknown_override_cores) > 12:
                    lines.append(f"- ...and {len(unknown_override_cores) - 12} more")

        if snapshot.roms_root and (layout is None or not same_path(snapshot.roms_root, layout.roms_root)):
            lines.append(f"ROMs root: {snapshot.roms_root}")
        if snapshot.emu_root and (layout is None or layout.emu_root is None or not same_path(snapshot.emu_root, layout.emu_root)):
            lines.append(f"Emulators root: {snapshot.emu_root}")
        if snapshot.dev_reference_repo:
            lines.append(f"Developer reference repo: {snapshot.dev_reference_repo}")
        lines.append("")
        lines.append("Recent Activity")
        lines.append(self._operation_log_text_from_entries(snapshot.activity_log))
        return "\n".join(lines)

    def _diagnostics_text(self) -> str:
        session = self._session_state
        if session.diagnostics_text_cache:
            return session.diagnostics_text_cache
        snapshot = self._capture_diagnostics_context()
        session.diagnostics_snapshot = snapshot
        session.diagnostics_text_cache = self._build_diagnostics_text(snapshot)
        return session.diagnostics_text_cache

    def _request_diagnostics_text(self, on_ready, *, force_refresh: bool = False):
        session = self._session_state
        if not force_refresh and session.diagnostics_text_cache:
            self._queue_ui(on_ready, session.diagnostics_text_cache)
            return

        snapshot = self._capture_diagnostics_context()
        session.diagnostics_snapshot = snapshot
        session.diagnostics_request_token += 1
        token = session.diagnostics_request_token

        def deliver(text: str):
            if self._ui_state.is_closing or token != self._session_state.diagnostics_request_token:
                return
            self._session_state.diagnostics_snapshot = snapshot
            self._session_state.diagnostics_text_cache = text
            on_ready(text)

        self._run_background_task(lambda: self._build_diagnostics_text(snapshot), on_success=deliver)

    def _export_text_content(self, title: str, suggested_name: str, content: str):
        filename = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".txt",
            initialfile=suggested_name,
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if not filename:
            return
        try:
            Path(filename).write_text(content, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))
            self._log_event("error", "Export failed.", str(exc))
            return
        self._show_toast(f"Saved '{Path(filename).name}'.", kind="success")
        self._log_event("export", f"Saved '{Path(filename).name}'.")

    def _ensure_writable(self, action_name: str) -> bool:
        if not self._read_only_mode.get():
            return True
        message = (
            f"Read-only mode is enabled, so '{action_name}' is blocked.\n\n"
            "Turn off 'Read-Only Safety Mode' in the toolbar first if you want to make changes."
        )
        messagebox.showinfo("Read-Only Mode", message)
        self._show_toast(f"Read-only mode blocked '{action_name}'.", kind="warning")
        self._log_event("blocked", f"Read-only mode blocked '{action_name}'.")
        return False

    def _update_write_controls(self):
        ui_state = self._ui_state
        write_state = "disabled" if self._read_only_mode.get() else "!disabled"
        readonly_combo_state = "disabled" if self._read_only_mode.get() else "readonly"

        if hasattr(self, "_copy_mode_combo"):
            self._copy_mode_combo.configure(state=readonly_combo_state)

        for widget in ui_state.writable_controls:
            try:
                widget.state([write_state] if write_state == "disabled" else ["!disabled"])
            except Exception:
                pass

    def _on_read_only_change(self):
        self._update_write_controls()
        state_text = "enabled" if self._read_only_mode.get() else "disabled"
        self._set_status(f"Read-only safety mode {state_text}.")
        self._show_toast(f"Read-only safety mode {state_text}.", kind="info")
        self._log_event("safety", f"Read-only safety mode {state_text}.")

    def _show_toast(self, message: str, kind: str = "info", duration_ms: int = 2800):
        ui_state = self._ui_state
        if ui_state.is_closing or not message.strip():
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

        frame = tk.Frame(
            toast,
            bg=bg_color,
            bd=1,
            relief="solid",
            highlightbackground=border_color,
            highlightcolor=border_color,
            highlightthickness=1,
        )
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

        ui_state.toast_window = toast
        ui_state.toast_after_id = self.after(duration_ms, self._hide_toast)

    def _hide_toast(self):
        ui_state = self._ui_state
        if ui_state.toast_after_id:
            try:
                self.after_cancel(ui_state.toast_after_id)
            except Exception:
                pass
            ui_state.toast_after_id = None
        if ui_state.toast_window and ui_state.toast_window.winfo_exists():
            ui_state.toast_window.destroy()
        ui_state.toast_window = None

    def _reposition_toast(self):
        toast_window = self._ui_state.toast_window
        if not toast_window or not toast_window.winfo_exists():
            return
        self.update_idletasks()
        toast_window.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() - toast_window.winfo_reqwidth() - 20
        y = self.winfo_rooty() + self.winfo_height() - toast_window.winfo_reqheight() - 48
        toast_window.geometry(f"+{max(x, 20)}+{max(y, 20)}")

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
            ("Ctrl+Z", "Undo the latest reversible session change"),
            ("Ctrl+M", "Load the SD card automatically, including WSL mount when needed"),
            ("Ctrl+J", "Open the selected game's metadata and cover panel"),
            ("Ctrl+Shift+E", "Safely unmount the current WSL device and try to eject it"),
            ("Ctrl+Shift+G", "Scan for duplicate files in the current tab or whole device"),
            ("Ctrl+Shift+H", "Open the device health panel"),
            ("Ctrl+Shift+X", "Build a Windows executable with PyInstaller"),
            ("Ctrl+Shift+Y", "Open the undo/history viewer"),
            ("Ctrl+Shift+B", "Create a ZIP backup of the current device"),
            ("Ctrl+Shift+R", "Restore a ZIP backup into the current device"),
            ("Ctrl+Shift+S", "Sync the current system or emulator folder from a PC folder"),
            ("Ctrl+Alt+L", "Open the activity log"),
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
            "- If Windows cannot read the SD card directly, use Ctrl+M or the toolbar button to let the app recover it or mount it with WSL.\n"
            "- The scanner now recognizes stock SF3000 structure such as rootfs/, cubegm/, cubegm/icube, and cubegm/cores/*.xml.\n"
            "- Tools > SF3000 Developer Notes now summarizes the 700zx1 build repo and the expected _libretro_sf3000.so workflow for custom cores.\n"
            "- Read-only safety mode blocks write actions while still letting you scan, validate, back up, and inspect the device.\n"
            "- Undo history lasts for the current app session and now covers imports, deletes, renames, restores, and created folders.\n"
            "- Sync Folder scans a PC folder recursively and imports supported files into the current target.\n"
            "- Duplicate Manager hashes matching-size files so you can delete true duplicates instead of filename lookalikes.\n"
            "- Game metadata uses filename-based lookup with a local cache, and falls back to a generated cover card when no image is available.\n"
            + (
                "- Drag files onto the lists to import them.\n"
                if TKDND_AVAILABLE
                else "- Install tkinterdnd2 to enable drag-and-drop import onto the lists.\n"
            )
            + "- Validation uses the selected rows first, then falls back to the current filtered view.\n",
        )
        shortcuts_box.configure(state="disabled")

        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 14))
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def _show_text_viewer(
        self,
        title: str,
        heading: str,
        text_provider,
        export_title: str,
        export_name: str,
        async_text_provider=None,
    ):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("760x520")
        dialog.minsize(620, 420)
        dialog.transient(self)

        ttk.Label(dialog, text=heading, style="Title.TLabel").pack(
            anchor="w", padx=14, pady=(14, 6)
        )

        content = ttk.Frame(dialog, padding=(14, 0, 14, 12))
        content.pack(fill="both", expand=True)

        box = tk.Text(
            content,
            wrap="word",
            relief="solid",
            borderwidth=1,
            background="#ffffff",
            font="TkFixedFont",
            padx=8,
            pady=8,
        )
        scroll = ttk.Scrollbar(content, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        box.pack(fill="both", expand=True)

        def set_text(value: str):
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", value)
            box.configure(state="disabled")

        def refresh():
            if async_text_provider is not None:
                set_text("Loading diagnostics...")
                async_text_provider(set_text, force_refresh=True)
                return
            set_text(text_provider())

        refresh()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(button_frame, text="Refresh", command=refresh).pack(side="left", padx=(0, 6))

        def export_current():
            if async_text_provider is not None:
                async_text_provider(
                    lambda value: self._export_text_content(export_title, export_name, value),
                    force_refresh=False,
                )
                return
            self._export_text_content(export_title, export_name, text_provider())

        ttk.Button(button_frame, text="Export", command=export_current).pack(side="left", padx=6)
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side="right")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def _show_activity_log(self):
        self._show_text_viewer(
            title="Activity Log",
            heading="Session Activity Log",
            text_provider=self._operation_log_text,
            export_title="Export Activity Log",
            export_name=f"sf3000-activity-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
        )

    def _runtime_log_text(self) -> str:
        try:
            if RUNTIME_LOG_FILE.exists():
                return RUNTIME_LOG_FILE.read_text(encoding="utf-8")
        except Exception:
            pass
        return "No runtime log has been captured yet."

    def _developer_notes_text(self) -> str:
        repo_path = self._dev_reference_repo or find_dev_reference_repo()
        layout = self._browser_state.device_layout
        catalog = self._browser_state.core_catalog
        env_lines = []
        for name in ("CC", "CXX", "AR", "STRIP"):
            env_lines.append(f"{name}: {os.environ.get(name) or '(not set)'}")

        lines = [
            "SF3000 Developer Notes",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "Reference repos in use:",
            "- 700zx1/cubegm-repo: stock cubegm layout, launcher scripts, core config.xml, filelist.xml",
            "- 700zx1/sf3000-dev: build container + Makefile for libretro sf3000 cores",
            "",
            f"Developer repo path: {repo_path or '(not found locally)'}",
        ]

        if repo_path:
            lines.extend(
                [
                    f"Dockerfile: {repo_path / 'Dockerfile'}",
                    f"Build helper: {repo_path / 'buildRun.sh'}",
                    f"Makefile: {repo_path / 'Makefile.sf3000'}",
                    "",
                    "Typical workflow:",
                    "1. Run the container helper to enter the build environment.",
                    "2. Build with the sf3000 makefile and platform=sf3000.",
                    "3. Expect an output name ending in _libretro_sf3000.so, for example vice_x64_libretro_sf3000.so.",
                    "4. Copy the resulting .so into cubegm/cores and update config.xml if needed.",
                    "",
                    "Example commands:",
                    f"  cd {repo_path}",
                    "  ./buildRun.sh",
                    "  make -f Makefile.sf3000 platform=sf3000",
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "The sf3000-dev reference repo was not found locally.",
                    "Clone it beside this app folder if you want build-environment notes inside the app.",
                ]
            )

        if layout and layout.emu_root:
            custom_core_names = [
                file_path.name
                for file_path in list_child_files(layout.emu_root)
                if file_path.name.casefold().endswith("_libretro_sf3000.so")
            ]
            lines.extend(
                [
                    "",
                    f"Current device emu root: {layout.emu_root}",
                    f"Detected custom sf3000 libretro cores: {len(custom_core_names)}",
                ]
            )
            if custom_core_names:
                lines.extend(f"- {name}" for name in custom_core_names[:12])
                if len(custom_core_names) > 12:
                    lines.append(f"- ...and {len(custom_core_names) - 12} more")
            if catalog is not None:
                lines.append(f"config.xml core definitions: {len(catalog.definitions)}")
                lines.append(f"filelist.xml overrides: {len(catalog.overrides)}")

        lines.extend(["", "Current environment variables:"])
        lines.extend(env_lines)
        return "\n".join(lines)

    def _show_runtime_log(self):
        self._show_text_viewer(
            title="Runtime Log",
            heading="Runtime Log",
            text_provider=self._runtime_log_text,
            export_title="Export Runtime Log",
            export_name=f"sf3000-runtime-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
        )

    def _show_developer_notes(self):
        self._show_text_viewer(
            title="SF3000 Developer Notes",
            heading="SF3000 Developer Notes",
            text_provider=self._developer_notes_text,
            export_title="Export Developer Notes",
            export_name=f"sf3000-developer-notes-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt",
        )
