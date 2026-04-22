from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from sf3000.ui_common import ToolTip
from sf3000.runtime_env import DND_FILES, TKDND_AVAILABLE


class SF3000UIScaffoldMixin:
    def _configure_style(self):
        self.option_add("*tearOff", False)
        style = ttk.Style(self)
        theme_names = style.theme_names()
        if "vista" in theme_names:
            style.theme_use("vista")
        elif "clam" in theme_names:
            style.theme_use("clam")

        self.configure(background="#f4f7fb")
        style.configure(".", font=("Segoe UI", 9))
        style.configure("TFrame", background="#f4f7fb")
        style.configure("TLabelframe", background="#f4f7fb", padding=8)
        style.configure("TLabelframe.Label", font=("Segoe UI Semibold", 9), foreground="#1e293b")
        style.configure("TLabel", background="#f4f7fb", foreground="#0f172a")
        style.configure("Hint.TLabel", foreground="#64748b")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 10), foreground="#0f172a")
        style.configure("TButton", padding=(10, 5))
        style.configure("Treeview", rowheight=26, fieldbackground="#ffffff", background="#ffffff")
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))
        style.configure("TNotebook", background="#f4f7fb", tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", padding=(14, 7))
        style.map(
            "Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#0f172a")],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#ffffff")],
            foreground=[("selected", "#0f172a")],
        )

    def _configure_tree_appearance(self):
        for tree in (self._game_tree, self._emu_tree):
            tree.tag_configure("row_even", background="#ffffff")
            tree.tag_configure("row_odd", background="#f8fbff")
            tree.tag_configure("warning", foreground="#9a3412")

    def _install_tooltips(self):
        hint = (
            "Drop files here to import them."
            if TKDND_AVAILABLE
            else "Drag-and-drop is available if you install 'tkinterdnd2'."
        )

        pairs = [
            (self._drive_combo, "Choose the SD-card root or mounted path. Press Enter to scan."),
            (self._browse_button, "Browse for the SF3000 SD-card root folder."),
            (self._scan_button, "Rescan the selected device. Shortcut: Ctrl+R or F5."),
            (
                self._mount_button,
                "Load the SD card automatically. The app will either recover a Windows-readable card "
                "or mount a RAW/Linux card through WSL. Shortcut: Ctrl+M. Windows may show a UAC prompt first.",
            ),
            (self._copy_mode_combo, "Choose whether imported files are copied or moved."),
            (
                self._recycle_toggle,
                "When enabled, deletes and overwritten files are moved to the Recycle Bin first.",
            ),
            (
                self._read_only_toggle,
                "Block imports, deletes, renames, restores, and folder creation until you turn this off.",
            ),
            (self._undo_button, "Undo the most recent reversible change in this session. Shortcut: Ctrl+Z."),
            (self._open_button, "Open the current selection in Explorer. Shortcut: Ctrl+O."),
            (
                self._tools_button,
                "Open device tools for history, duplicates, metadata, backup, restore, packaging, and diagnostics.",
            ),
            (self._help_button, "Show keyboard shortcuts and workflow tips. Shortcut: F1."),
            (self._game_add_button, "Add game files to the selected system folder. Shortcut: Ctrl+I."),
            (self._game_delete_button, "Delete the selected game files. Shortcut: Delete."),
            (self._game_rename_button, "Rename the selected game file. Shortcut: F2."),
            (self._game_clean_button, "Clean selected game file names. Shortcut: Ctrl+L."),
            (
                self._game_validate_button,
                "Validate the selected rows or current filtered game view. Shortcut: Ctrl+D.",
            ),
            (
                self._game_info_button,
                "Show game metadata and cover art for the selected ROM. Shortcut: Ctrl+J.",
            ),
            (
                self._game_sync_button,
                "Sync supported game files from a PC folder into the selected system. Shortcut: Ctrl+Shift+S.",
            ),
            (self._game_new_folder_button, "Create a new system folder. Shortcut: Ctrl+Shift+N."),
            (self._game_common_button, "Create a starter set of common system folders."),
            (
                self._game_filter_entry,
                "Filter by title, filename, extension, folder, or warning. Shortcut: Ctrl+F.",
            ),
            (self._game_filter_clear_button, "Clear the Games filter. Shortcut: Escape."),
            (self._emu_add_button, "Add emulator files to the selected emulator folder. Shortcut: Ctrl+I."),
            (self._emu_delete_button, "Delete the selected emulator files. Shortcut: Delete."),
            (self._emu_rename_button, "Rename the selected emulator file. Shortcut: F2."),
            (self._emu_clean_button, "Clean selected emulator file names. Shortcut: Ctrl+L."),
            (
                self._emu_validate_button,
                "Validate the selected rows or current filtered emulator view. Shortcut: Ctrl+D.",
            ),
            (
                self._emu_sync_button,
                "Sync supported emulator files from a PC folder into the selected emulator folder. Shortcut: Ctrl+Shift+S.",
            ),
            (self._emu_new_folder_button, "Create an emulator folder or emulator root. Shortcut: Ctrl+Shift+N."),
            (
                self._emu_filter_entry,
                "Filter by filename, extension, folder, or warning. Shortcut: Ctrl+F.",
            ),
            (self._emu_filter_clear_button, "Clear the Emulators filter. Shortcut: Escape."),
            (self._sys_tree, "Pick a system folder. Press Enter to open it in Explorer."),
            (self._emu_folder_tree, "Pick an emulator folder. Press Enter to open it in Explorer."),
            (
                self._game_tree,
                f"Double-click or press Enter to reveal a file. Right-click for actions. {hint}",
            ),
            (
                self._emu_tree,
                f"Double-click or press Enter to reveal a file. Right-click for actions. {hint}",
            ),
        ]

        self._ui_state.tooltips = [ToolTip(widget, text) for widget, text in pairs]

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x", side="top")

        ttk.Label(toolbar, text="SF3000 SD Card", style="Title.TLabel").pack(
            side="left",
            padx=(0, 10),
        )
        ttk.Label(toolbar, text="Drive / Path:").pack(side="left")
        self._drive_combo = ttk.Combobox(toolbar, textvariable=self._sd_path, width=34)
        self._drive_combo.pack(side="left", padx=(4, 0))
        self._drive_combo.bind("<<ComboboxSelected>>", lambda _e: self._scan_all())
        self._drive_combo.bind("<Return>", lambda _e: self._scan_all())

        self._browse_button = ttk.Button(toolbar, text="Browse...", command=self._browse_path)
        self._browse_button.pack(side="left", padx=4)
        self._scan_button = ttk.Button(toolbar, text="Scan", command=self._scan_all)
        self._scan_button.pack(side="left", padx=2)
        self._mount_button = ttk.Button(
            toolbar,
            text="Load SD Card",
            command=lambda: self._mount_linux_sd(
                user_initiated=True,
                preferred_path=self._sd_path.get().strip(),
            ),
        )
        self._mount_button.pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(toolbar, text="Import Mode:").pack(side="left")
        self._copy_mode_combo = ttk.Combobox(
            toolbar,
            textvariable=self._copy_mode,
            values=("copy", "move"),
            state="readonly",
            width=8,
        )
        self._copy_mode_combo.pack(side="left", padx=(4, 0))
        self._recycle_toggle = ttk.Checkbutton(
            toolbar,
            text="Recycle Deletes/Overwrites",
            variable=self._delete_to_recycle,
        )
        self._recycle_toggle.pack(side="left", padx=10)
        self._read_only_toggle = ttk.Checkbutton(
            toolbar,
            text="Read-Only Safety Mode",
            variable=self._read_only_mode,
        )
        self._read_only_toggle.pack(side="left", padx=(0, 6))
        self._undo_button = ttk.Button(toolbar, text="Undo Last", command=self._undo_last_action)
        self._undo_button.pack(side="left", padx=(2, 0))

        self._help_button = ttk.Button(toolbar, text="Shortcuts", command=self._show_shortcuts_dialog)
        self._help_button.pack(side="right", padx=2)
        self._tools_button = ttk.Menubutton(toolbar, text="Tools")
        self._tools_button.pack(side="right", padx=2)
        self._open_button = ttk.Button(toolbar, text="Open in Explorer", command=self._open_in_explorer)
        self._open_button.pack(side="right", padx=2)

        self._tools_menu = tk.Menu(self, tearoff=False)
        self._tools_menu.add_command(label="Undo Last Change\tCtrl+Z", command=self._undo_last_action)
        self._tools_menu.add_command(
            label="History And Undo...\tCtrl+Shift+Y",
            command=self._show_history_dialog,
        )
        self._tools_menu.add_separator()
        self._tools_menu.add_command(
            label="Duplicate Manager...\tCtrl+Shift+G",
            command=self._show_duplicate_manager,
        )
        self._tools_menu.add_command(
            label="Game Metadata / Cover\tCtrl+J",
            command=self._show_selected_metadata,
        )
        self._tools_menu.add_separator()
        self._tools_menu.add_command(
            label="Device Health\tCtrl+Shift+H",
            command=self._show_device_health,
        )
        self._tools_menu.add_command(
            label="Safe Eject / Unmount\tCtrl+Shift+E",
            command=self._safe_eject_device,
        )
        self._tools_menu.add_separator()
        self._tools_menu.add_command(label="Backup Device...\tCtrl+Shift+B", command=self._backup_device)
        self._tools_menu.add_command(
            label="Restore Backup...\tCtrl+Shift+R",
            command=self._restore_backup,
        )
        self._tools_menu.add_command(
            label="Build Windows EXE...\tCtrl+Shift+X",
            command=self._build_windows_exe,
        )
        self._tools_menu.add_command(label="SF3000 Developer Notes", command=self._show_developer_notes)
        self._tools_menu.add_separator()
        self._tools_menu.add_command(
            label="View Activity Log\tCtrl+Alt+L",
            command=self._show_activity_log,
        )
        self._tools_menu.add_command(label="View Runtime Log", command=self._show_runtime_log)
        self._tools_menu.add_command(label="Export Diagnostics...", command=self._export_diagnostics)
        self._tools_button["menu"] = self._tools_menu

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=6, pady=(2, 0))
        self._notebook.bind("<<NotebookTabChanged>>", lambda _e: self._refresh_active_status())

        games_frame = ttk.Frame(self._notebook)
        emulators_frame = ttk.Frame(self._notebook)
        self._notebook.add(games_frame, text="  Games  ")
        self._notebook.add(emulators_frame, text="  Emulators  ")

        self._build_games_tab(games_frame)
        self._build_emulators_tab(emulators_frame)

        storage_frame = ttk.Frame(self, padding=(6, 2))
        storage_frame.pack(fill="x", side="bottom")
        self._storage_label = ttk.Label(storage_frame, text="")
        self._storage_label.pack(side="left")
        self._storage_bar = ttk.Progressbar(storage_frame, length=220, maximum=100, mode="determinate")
        self._storage_bar.pack(side="right", padx=(0, 4))
        ttk.Label(storage_frame, text="Storage:").pack(side="right")

        status_frame = ttk.Frame(self, relief="sunken", padding=(6, 2))
        status_frame.pack(fill="x", side="bottom")
        ttk.Label(status_frame, textvariable=self._status).pack(side="left")
        self._shortcut_hint_label = ttk.Label(
            status_frame,
            text=(
                "Ctrl+Z Undo  |  Ctrl+M Load SD  |  Ctrl+Shift+S Sync  |  Ctrl+I Import  |  Ctrl+J Info"
                + ("  |  Drop files to import" if TKDND_AVAILABLE else "")
            ),
            style="Hint.TLabel",
        )
        self._shortcut_hint_label.pack(side="right", padx=(0, 10))
        self._scan_progress = ttk.Progressbar(status_frame, mode="indeterminate", length=120)
        self._scan_progress.pack(side="right")

    def _build_games_tab(self, parent):
        actions = ttk.Frame(parent, padding=(4, 4))
        actions.pack(fill="x", side="top")

        self._game_add_button = ttk.Button(actions, text="+ Add Games", command=self._add_games)
        self._game_add_button.pack(side="left", padx=2)
        self._game_delete_button = ttk.Button(
            actions,
            text="Delete Selected",
            command=self._delete_selected_games,
        )
        self._game_delete_button.pack(side="left", padx=2)
        self._game_rename_button = ttk.Button(
            actions,
            text="Rename Selected",
            command=self._rename_selected_games,
        )
        self._game_rename_button.pack(side="left", padx=2)
        self._game_clean_button = ttk.Button(
            actions,
            text="Clean Names",
            command=self._clean_selected_game_names,
        )
        self._game_clean_button.pack(side="left", padx=2)
        self._game_validate_button = ttk.Button(
            actions,
            text="Validate",
            command=self._validate_selected_games,
        )
        self._game_validate_button.pack(side="left", padx=2)
        self._game_info_button = ttk.Button(
            actions,
            text="Info / Cover",
            command=self._show_selected_metadata,
        )
        self._game_info_button.pack(side="left", padx=2)
        self._game_sync_button = ttk.Button(
            actions,
            text="Sync Folder...",
            command=self._sync_games_from_folder,
        )
        self._game_sync_button.pack(side="left", padx=2)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        self._game_new_folder_button = ttk.Button(
            actions,
            text="New System Folder",
            command=self._new_game_folder,
        )
        self._game_new_folder_button.pack(side="left", padx=2)
        self._game_common_button = ttk.Button(
            actions,
            text="Create Common Folders",
            command=self._create_common_system_folders,
        )
        self._game_common_button.pack(side="left", padx=2)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(actions, text="Filter:").pack(side="left")
        self._game_filter_entry = ttk.Entry(actions, textvariable=self._game_filter_var, width=28)
        self._game_filter_entry.pack(side="left", padx=(4, 2))
        self._game_filter_clear_button = ttk.Button(
            actions,
            text="Clear",
            command=lambda: self._game_filter_var.set(""),
        )
        self._game_filter_clear_button.pack(side="left", padx=2)

        pane = ttk.PanedWindow(parent, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=4, pady=4)

        systems_frame = ttk.LabelFrame(pane, text="Systems", padding=2)
        pane.add(systems_frame, weight=1)

        self._sys_tree = ttk.Treeview(systems_frame, show="tree", selectmode="browse")
        sys_scroll = ttk.Scrollbar(systems_frame, orient="vertical", command=self._sys_tree.yview)
        self._sys_tree.configure(yscrollcommand=sys_scroll.set)
        sys_scroll.pack(side="right", fill="y")
        self._sys_tree.pack(fill="both", expand=True)
        self._sys_tree.bind("<<TreeviewSelect>>", self._on_system_select)
        self._sys_tree.bind(
            "<Button-3>",
            lambda event: self._post_tree_menu(event, self._sys_tree, self._systems_menu),
        )

        games_frame = ttk.LabelFrame(pane, text="Games", padding=2)
        pane.add(games_frame, weight=4)

        columns = ("name", "file", "size", "type", "modified", "folder", "warning")
        self._game_tree = ttk.Treeview(
            games_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self._game_tree.heading("name", text="Title", command=lambda: self._sort_games("name"))
        self._game_tree.heading("file", text="File Name", command=lambda: self._sort_games("file"))
        self._game_tree.heading("size", text="Size", command=lambda: self._sort_games("size"))
        self._game_tree.heading("type", text="Type", command=lambda: self._sort_games("type"))
        self._game_tree.heading(
            "modified",
            text="Modified",
            command=lambda: self._sort_games("modified"),
        )
        self._game_tree.heading("folder", text="Folder", command=lambda: self._sort_games("folder"))
        self._game_tree.heading("warning", text="Warning", command=lambda: self._sort_games("warning"))

        self._game_tree.column("name", width=220, minwidth=120)
        self._game_tree.column("file", width=220, minwidth=120)
        self._game_tree.column("size", width=90, anchor="e", minwidth=60)
        self._game_tree.column("type", width=70, anchor="center", minwidth=50)
        self._game_tree.column("modified", width=140, minwidth=100)
        self._game_tree.column("folder", width=110, minwidth=80)
        self._game_tree.column("warning", width=220, minwidth=100)

        game_scroll_y = ttk.Scrollbar(games_frame, orient="vertical", command=self._game_tree.yview)
        game_scroll_x = ttk.Scrollbar(games_frame, orient="horizontal", command=self._game_tree.xview)
        self._game_tree.configure(yscrollcommand=game_scroll_y.set, xscrollcommand=game_scroll_x.set)
        game_scroll_y.pack(side="right", fill="y")
        game_scroll_x.pack(side="bottom", fill="x")
        self._game_tree.pack(fill="both", expand=True)

        self._game_tree.bind("<Delete>", lambda _e: self._delete_selected_games())
        self._game_tree.bind("<Double-1>", lambda _e: self._reveal_selected_file(self._game_tree))
        self._game_tree.bind(
            "<Button-3>",
            lambda event: self._post_tree_menu(event, self._game_tree, self._games_menu),
        )

    def _build_emulators_tab(self, parent):
        actions = ttk.Frame(parent, padding=(4, 4))
        actions.pack(fill="x", side="top")

        self._emu_add_button = ttk.Button(actions, text="+ Add Emulator", command=self._add_emulators)
        self._emu_add_button.pack(side="left", padx=2)
        self._emu_delete_button = ttk.Button(
            actions,
            text="Delete Selected",
            command=self._delete_selected_emulators,
        )
        self._emu_delete_button.pack(side="left", padx=2)
        self._emu_rename_button = ttk.Button(
            actions,
            text="Rename Selected",
            command=self._rename_selected_emulators,
        )
        self._emu_rename_button.pack(side="left", padx=2)
        self._emu_clean_button = ttk.Button(
            actions,
            text="Clean Names",
            command=self._clean_selected_emulator_names,
        )
        self._emu_clean_button.pack(side="left", padx=2)
        self._emu_validate_button = ttk.Button(
            actions,
            text="Validate",
            command=self._validate_selected_emulators,
        )
        self._emu_validate_button.pack(side="left", padx=2)
        self._emu_sync_button = ttk.Button(
            actions,
            text="Sync Folder...",
            command=self._sync_emulators_from_folder,
        )
        self._emu_sync_button.pack(side="left", padx=2)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        self._emu_new_folder_button = ttk.Button(
            actions,
            text="New Emulator Folder",
            command=self._new_emu_folder,
        )
        self._emu_new_folder_button.pack(side="left", padx=2)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        self._emu_path_label = ttk.Label(
            actions,
            text="Emulators folder: (not found)",
            foreground="gray",
        )
        self._emu_path_label.pack(side="left", padx=4)
        ttk.Separator(actions, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(actions, text="Filter:").pack(side="left")
        self._emu_filter_entry = ttk.Entry(actions, textvariable=self._emu_filter_var, width=28)
        self._emu_filter_entry.pack(side="left", padx=(4, 2))
        self._emu_filter_clear_button = ttk.Button(
            actions,
            text="Clear",
            command=lambda: self._emu_filter_var.set(""),
        )
        self._emu_filter_clear_button.pack(side="left", padx=2)

        pane = ttk.PanedWindow(parent, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=4, pady=4)

        folders_frame = ttk.LabelFrame(pane, text="Emulator Folders", padding=2)
        pane.add(folders_frame, weight=1)

        self._emu_folder_tree = ttk.Treeview(folders_frame, show="tree", selectmode="browse")
        emu_scroll = ttk.Scrollbar(
            folders_frame,
            orient="vertical",
            command=self._emu_folder_tree.yview,
        )
        self._emu_folder_tree.configure(yscrollcommand=emu_scroll.set)
        emu_scroll.pack(side="right", fill="y")
        self._emu_folder_tree.pack(fill="both", expand=True)
        self._emu_folder_tree.bind("<<TreeviewSelect>>", self._on_emu_folder_select)
        self._emu_folder_tree.bind(
            "<Button-3>",
            lambda event: self._post_tree_menu(event, self._emu_folder_tree, self._emu_folders_menu),
        )

        files_frame = ttk.LabelFrame(pane, text="Emulator Files", padding=2)
        pane.add(files_frame, weight=4)

        columns = ("name", "size", "type", "modified", "folder", "warning")
        self._emu_tree = ttk.Treeview(
            files_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self._emu_tree.heading("name", text="File Name", command=lambda: self._sort_emus("name"))
        self._emu_tree.heading("size", text="Size", command=lambda: self._sort_emus("size"))
        self._emu_tree.heading("type", text="Type", command=lambda: self._sort_emus("type"))
        self._emu_tree.heading(
            "modified",
            text="Modified",
            command=lambda: self._sort_emus("modified"),
        )
        self._emu_tree.heading("folder", text="Folder", command=lambda: self._sort_emus("folder"))
        self._emu_tree.heading("warning", text="Warning", command=lambda: self._sort_emus("warning"))

        self._emu_tree.column("name", width=300, minwidth=120)
        self._emu_tree.column("size", width=90, anchor="e", minwidth=60)
        self._emu_tree.column("type", width=70, anchor="center", minwidth=50)
        self._emu_tree.column("modified", width=140, minwidth=100)
        self._emu_tree.column("folder", width=110, minwidth=80)
        self._emu_tree.column("warning", width=240, minwidth=100)

        emu_files_scroll_y = ttk.Scrollbar(files_frame, orient="vertical", command=self._emu_tree.yview)
        emu_files_scroll_x = ttk.Scrollbar(files_frame, orient="horizontal", command=self._emu_tree.xview)
        self._emu_tree.configure(
            yscrollcommand=emu_files_scroll_y.set,
            xscrollcommand=emu_files_scroll_x.set,
        )
        emu_files_scroll_y.pack(side="right", fill="y")
        emu_files_scroll_x.pack(side="bottom", fill="x")
        self._emu_tree.pack(fill="both", expand=True)

        self._emu_tree.bind("<Delete>", lambda _e: self._delete_selected_emulators())
        self._emu_tree.bind("<Double-1>", lambda _e: self._reveal_selected_file(self._emu_tree))
        self._emu_tree.bind(
            "<Button-3>",
            lambda event: self._post_tree_menu(event, self._emu_tree, self._emus_menu),
        )

        self._ui_state.writable_controls = [
            self._recycle_toggle,
            self._game_add_button,
            self._game_delete_button,
            self._game_rename_button,
            self._game_clean_button,
            self._game_sync_button,
            self._game_new_folder_button,
            self._game_common_button,
            self._undo_button,
            self._emu_add_button,
            self._emu_delete_button,
            self._emu_rename_button,
            self._emu_clean_button,
            self._emu_sync_button,
            self._emu_new_folder_button,
        ]

    def _build_context_menus(self):
        self._systems_menu = tk.Menu(self, tearoff=False)
        self._systems_menu.add_command(
            label="Open Folder\tEnter",
            command=self._open_selected_system_folder,
        )
        self._systems_menu.add_command(
            label="Validate\tCtrl+D",
            command=self._validate_selected_games,
        )
        self._systems_menu.add_command(
            label="Sync Folder...\tCtrl+Shift+S",
            command=self._sync_games_from_folder,
        )
        self._systems_menu.add_separator()
        self._systems_menu.add_command(
            label="New System Folder\tCtrl+Shift+N",
            command=self._new_game_folder,
        )
        self._systems_menu.add_command(
            label="Create Common Folders",
            command=self._create_common_system_folders,
        )
        self._systems_menu.add_separator()
        self._systems_menu.add_command(label="Refresh\tF5", command=self._scan_all)

        self._games_menu = tk.Menu(self, tearoff=False)
        self._games_menu.add_command(
            label="Reveal in Explorer\tEnter",
            command=lambda: self._reveal_selected_file(self._game_tree),
        )
        self._games_menu.add_command(
            label="Metadata / Cover\tCtrl+J",
            command=self._show_selected_metadata,
        )
        self._games_menu.add_command(label="Rename\tF2", command=self._rename_selected_games)
        self._games_menu.add_command(
            label="Clean Names\tCtrl+L",
            command=self._clean_selected_game_names,
        )
        self._games_menu.add_separator()
        self._games_menu.add_command(
            label="Duplicate Manager...\tCtrl+Shift+G",
            command=self._show_duplicate_manager,
        )
        self._games_menu.add_command(
            label="Sync Folder...\tCtrl+Shift+S",
            command=self._sync_games_from_folder,
        )
        self._games_menu.add_command(
            label="Validate\tCtrl+D",
            command=self._validate_selected_games,
        )
        self._games_menu.add_command(label="Delete\tDelete", command=self._delete_selected_games)
        self._games_menu.add_separator()
        self._games_menu.add_command(label="Refresh\tF5", command=self._scan_all)

        self._emu_folders_menu = tk.Menu(self, tearoff=False)
        self._emu_folders_menu.add_command(
            label="Open Folder\tEnter",
            command=self._open_selected_emu_folder,
        )
        self._emu_folders_menu.add_command(
            label="Validate\tCtrl+D",
            command=self._validate_selected_emulators,
        )
        self._emu_folders_menu.add_command(
            label="Sync Folder...\tCtrl+Shift+S",
            command=self._sync_emulators_from_folder,
        )
        self._emu_folders_menu.add_separator()
        self._emu_folders_menu.add_command(
            label="New Emulator Folder\tCtrl+Shift+N",
            command=self._new_emu_folder,
        )
        self._emu_folders_menu.add_separator()
        self._emu_folders_menu.add_command(label="Refresh\tF5", command=self._scan_all)

        self._emus_menu = tk.Menu(self, tearoff=False)
        self._emus_menu.add_command(
            label="Reveal in Explorer\tEnter",
            command=lambda: self._reveal_selected_file(self._emu_tree),
        )
        self._emus_menu.add_command(label="Rename\tF2", command=self._rename_selected_emulators)
        self._emus_menu.add_command(
            label="Clean Names\tCtrl+L",
            command=self._clean_selected_emulator_names,
        )
        self._emus_menu.add_separator()
        self._emus_menu.add_command(
            label="Duplicate Manager...\tCtrl+Shift+G",
            command=self._show_duplicate_manager,
        )
        self._emus_menu.add_command(
            label="Sync Folder...\tCtrl+Shift+S",
            command=self._sync_emulators_from_folder,
        )
        self._emus_menu.add_command(
            label="Validate\tCtrl+D",
            command=self._validate_selected_emulators,
        )
        self._emus_menu.add_command(label="Delete\tDelete", command=self._delete_selected_emulators)
        self._emus_menu.add_separator()
        self._emus_menu.add_command(label="Refresh\tF5", command=self._scan_all)

    def _register_drop_targets(self):
        if not TKDND_AVAILABLE:
            return

        try:
            self._game_tree.drop_target_register(DND_FILES)
            self._emu_tree.drop_target_register(DND_FILES)
            self._game_tree.dnd_bind("<<Drop>>", self._on_game_drop)
            self._emu_tree.dnd_bind("<<Drop>>", self._on_emu_drop)
        except Exception:
            pass
