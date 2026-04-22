# Changelog

## 2026-04-22

Initial full app implementation and polish pass.

### Added

- complete SF3000 game and emulator manager application in `sf3000_manager.py`
- background scanning with responsive UI behavior
- game and emulator validation flows
- copy and move import modes
- safer overwrite handling with staged replacement
- Recycle Bin delete support
- optional drag-and-drop import support through `tkinterdnd2`
- keyboard shortcuts, context menus, tooltips, toast notifications, and in-app help
- common system-folder creation helpers
- richer filtering, sorting, and metadata views
- automatic WSL-assisted mounting for Linux or RAW SF3000 SD cards, including candidate detection and in-app selection when needed

### Documentation

- replaced placeholder README with full setup and usage documentation
- documented optional drag-and-drop dependency
- documented keyboard shortcuts and workflow notes
- documented the built-in WSL mount flow and related requirements
