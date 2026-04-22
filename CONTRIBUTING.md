# Contributing

This repository currently ships a single-file Windows Tkinter app for managing SF3000 game and emulator content.

## Development Notes

- The app entrypoint is `sf3000_manager.py`.
- The code is intentionally self-contained for easy distribution and simple end-user setup.
- Optional drag-and-drop support uses `tkinterdnd2` when it is installed, but the app should still run cleanly without it.

## Local Validation

Run the basic syntax check before committing:

```powershell
python -m py_compile sf3000_manager.py
```

Recommended manual smoke checks on Windows:

1. Launch the app and confirm it opens without errors.
2. Scan a real or test SD-card folder.
3. Test imports in both copy and move modes.
4. Verify rename, validate, delete, and Explorer actions from the current view.
5. If `tkinterdnd2` is installed, test drag-and-drop on both tabs.

## Documentation

Keep `README.md` current when workflows, shortcuts, or dependencies change.
Update `CHANGELOG.md` for notable user-facing changes.
