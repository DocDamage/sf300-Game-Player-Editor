# Contributing

This repository ships a Windows Tkinter app for managing SF3000 game and emulator content, with a small `sf3000_manager.py` entrypoint and the main implementation split across the `sf3000/` package.

## Development Notes

- The app entrypoint is `sf3000_manager.py`.
- Most application behavior now lives in `sf3000/app_*.py`, `sf3000/*_service.py`, and `sf3000/models.py`.
- Keep non-UI logic in small service/helpers when possible so it can be covered without constructing the live Tk window.
- Optional drag-and-drop support uses `tkinterdnd2` when it is installed, but the app should still run cleanly without it.
- `SF3000GameManager(auto_startup=False)` is the preferred smoke-test path when you need a real app object without auto-scan side effects.

## Local Validation

Run the baseline checks before committing:

```powershell
python -m py_compile sf3000_manager.py sf3000\*.py tests\*.py
python -m unittest discover -s tests -v
```

Recommended manual smoke checks on Windows:

1. Launch the app and confirm it opens without errors.
2. Scan a real or test SD-card folder.
3. If you have a Linux or RAW SF3000 card, test the `Mount Linux SD` flow and confirm the app switches to the mounted `\\wsl$` path.
4. Test imports in both copy and move modes.
5. Verify rename, validate, delete, and Explorer actions from the current view.
6. If `tkinterdnd2` is installed, test drag-and-drop on both tabs.
7. Exercise duplicate scanning, metadata lookup, diagnostics, and backup/restore if your change touched those paths.

## Documentation

Keep `README.md` current when workflows, shortcuts, or dependencies change.
Update `CHANGELOG.md` for notable user-facing changes.
