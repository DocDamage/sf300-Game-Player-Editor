# SF3000 Game Player Editor

Windows desktop editor for browsing, validating, organizing, and importing ROMs and emulator files on an SF3000 SD card.

## Overview

This project provides a polished Tkinter-based manager for SF3000 game libraries and emulator files. It is designed to work directly against a mounted SD card or a copied card image folder and focuses on the common maintenance tasks that are annoying to do by hand in Explorer.

The app now ships as a small entrypoint plus a modular `sf3000/` package instead of one giant source file. That keeps the Windows/Tkinter UI, device-mount logic, validation, file operations, metadata tools, duplicate analysis, and runtime services separated into smaller units that are easier to test and maintain.

The app supports:

- automatic SD-card path detection on Windows
- automatic WSL-assisted mounting for Linux or RAW SF3000 cards
- separate Games and Emulators views
- background scanning so the UI stays responsive
- file filtering, sorting, validation, rename, and cleanup tools
- copy or move import modes
- safer overwrite handling with staging
- optional Recycle Bin deletion
- optional drag-and-drop import when `tkinterdnd2` is installed
- keyboard shortcuts, tooltips, toast notifications, and built-in shortcut help
- duplicate scanning based on file contents, not filenames alone
- save/restore/backup, sync, diagnostics, and device-health tools
- an automated unit-test suite for the highest-risk workflows

## Requirements

- Windows
- Python 3.8+
- Tkinter (included with standard Python on Windows)

Optional:

- `tkinterdnd2` for drag-and-drop import support
- WSL with an installed Linux distribution if you want the app to auto-mount ext4 cards for you

Install the optional package with:

```powershell
pip install tkinterdnd2
```

## Why Windows

The app is currently tuned for Windows behavior:

- drive-letter auto-detection
- Explorer integration
- Recycle Bin support through native Windows shell APIs
- WSL-based mounting for Linux-readable SD card partitions

If your SF3000 SD card uses an ext4 partition, the app can now try to mount it through WSL for you.

## Running The App

```powershell
python sf3000_manager.py
```

You can point the app at:

- the mounted SD-card root
- a local folder containing the extracted SD-card contents

## Main Features

### Game Management

- browse system folders and ROM files
- filter by title, filename, extension, folder, path, or warning text
- validate selected rows or the current filtered view
- rename individual files
- bulk clean names
- create custom system folders
- create a starter set of common system folders

### Emulator Management

- detect supported emulator root locations
- browse root-level and subfolder-based emulator files
- validate supported and unsupported file types
- rename and clean emulator filenames
- create recognized emulator root folders and subfolders

### Import Behavior

- choose between `copy` and `move` modes
- preview destination, overwrite count, transfer size, and free-space impact
- skip content-identical files
- stage replacements before overwriting existing files
- optionally route deletes and overwritten files through the Recycle Bin

### UX Improvements

- background scanning with progress indicator
- live filter boxes on both tabs
- right-click context menus
- toast notifications for common success/info states
- built-in shortcut/help dialog
- status bar with active-view summaries
- striped tables and warning highlighting

## Common Workflows

### Initial Setup

1. Insert or mount the SF3000 SD card in Windows.
2. Launch the app with `python sf3000_manager.py`.
3. If Windows shows the card as RAW or unreadable, click `Mount Linux SD` or press `Ctrl+M` and approve the UAC prompt.
4. If auto-detection does not pick the card up, use the path picker to point at the card root or mounted `\\wsl$` path manually.

### Mounting A Linux SD Card

1. Insert the SF3000 SD card.
2. Click `Mount Linux SD` in the toolbar or press `Ctrl+M`.
3. If there is only one clear Linux or RAW candidate, the app mounts it automatically.
4. If there are multiple candidates, choose the correct disk and partition from the in-app picker.
5. After mounting, the app switches itself to the `\\wsl$` path and scans automatically.

### Importing ROMs

1. Select the destination system folder on the Games tab.
2. Choose whether the toolbar should use copy or move mode.
3. Import files through the button, the context menu, or drag-and-drop when enabled.
4. Review the preflight summary before confirming the transfer.

### Reviewing Existing Files

1. Scan or refresh the card with `Ctrl+R` or `F5`.
2. Use the filter field to narrow the current list.
3. Run validation on the selected rows or current filtered view with `Ctrl+D`.
4. Use rename, clean-name, Explorer, and delete actions from the toolbar, context menu, or shortcuts.

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+R` / `F5` | Scan or refresh the current device |
| `Ctrl+M` | Mount a Linux or RAW SD card through WSL |
| `Ctrl+I` | Import files into the current target folder |
| `Ctrl+O` | Open the current selection in Explorer |
| `Ctrl+F` | Focus the current tab filter |
| `Escape` | Clear the current filter or dismiss the toast |
| `F2` | Rename the selected file |
| `Ctrl+L` | Clean selected filenames |
| `Ctrl+D` | Validate selected rows or the current filtered view |
| `Ctrl+Shift+N` | Create a new system or emulator folder |
| `Ctrl+A` | Select all visible rows in the current file list |
| `Alt+1` / `Ctrl+1` | Switch to the Games tab |
| `Alt+2` / `Ctrl+2` | Switch to the Emulators tab |
| `Enter` | Reveal the selected file or folder in Explorer |
| `Delete` | Delete selected files |
| `F1` | Open the built-in shortcuts/help window |

## Drag And Drop

If `tkinterdnd2` is installed, you can drag files directly onto:

- the Games file list
- the Emulators file list

Dropped folders are skipped intentionally. Import validation still applies, so drag-and-drop uses the same filtering and transfer rules as the file-picker workflow.

## Project Files

- `sf3000_manager.py`: thin application entrypoint
- `sf3000/`: application package with UI mixins, services, models, and platform helpers
- `tests/`: automated regression tests for mount helpers, startup, diagnostics, transfer/undo, metadata, duplicate analysis, and typed payloads
- `build_windows_exe.ps1`: helper script for packaging a Windows executable
- `CHANGELOG.md`: session-level change summary
- `CONTRIBUTING.md`: development and validation notes
- `LICENSE`: MIT license

## Architecture

- `sf3000_manager.py` boots `SF3000GameManager` and leaves the rest to the `sf3000` package.
- `sf3000/models.py` contains the core dataclasses, including explicit browser, operation, and UI runtime state objects.
- `sf3000/app_*.py` modules hold the UI/controller mixins for scanning, views, file operations, validation, device tools, metadata, duplicates, history, and lifecycle behavior.
- `sf3000/*_service.py` modules hold extracted non-UI workflows such as metadata lookup/caching and duplicate analysis.
- `sf3000/device_mount.py`, `sf3000/layout.py`, and `sf3000/windows_fs.py` contain the Windows/WSL, SF3000-layout, and filesystem platform helpers.

## Notes

- Application state is saved locally in the user profile at `~/.sf3000_game_manager.json`.
- The app does not require third-party packages unless you want drag-and-drop support.
- The source tree is modular, but the app still launches with the same simple `python sf3000_manager.py` entrypoint.
- Deferred startup support exists for tests and smoke harnesses through `SF3000GameManager(auto_startup=False)`.

## Troubleshooting

- If auto-detect does not find the card, browse to the mounted card root manually.
- If Windows shows the card as RAW or unreadable, use `Mount Linux SD` and approve the UAC prompt so WSL can mount it.
- If the Emulators tab looks empty, create a recognized emulator root folder from the app and rescan.
- If drag-and-drop is unavailable, install `tkinterdnd2` and relaunch the app.
- If automatic Linux mounting is unavailable, verify WSL is installed and has at least one distribution configured.
- If Windows still cannot access the card contents after mounting, verify the SD card is healthy and the ext4 partition is supported by your current WSL build.

## Development

Quick validation:

```powershell
python -m py_compile sf3000_manager.py sf3000\*.py tests\*.py
python -m unittest discover -s tests -v
```

## License

MIT. See [LICENSE](LICENSE).
