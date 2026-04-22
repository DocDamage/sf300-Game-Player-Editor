from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Sequence

from sf3000.app_constants import (
    APP_STATE_FILE,
    MAX_HASH_CACHE_ENTRIES,
    METADATA_CACHE_DIR,
    METADATA_CACHE_TTL_SECONDS,
)
from sf3000.layout import file_sha1, safe_stat


class SF3000StateMixin:
    def _load_settings(self) -> Dict[str, object]:
        try:
            return json.loads(APP_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self):
        data = {
            "sd_path": self._sd_path.get().strip(),
            "copy_mode": self._copy_mode.get(),
            "delete_to_recycle": bool(self._delete_to_recycle.get()),
            "read_only_mode": bool(self._read_only_mode.get()),
            "game_filter": self._game_filter_var.get(),
            "emu_filter": self._emu_filter_var.get(),
            "tab_index": self._notebook.index(self._notebook.select()),
            "system_selection": self._current_system_selection_key(),
            "emu_selection": self._current_emu_selection_key(),
            "geometry": self.geometry(),
        }
        try:
            APP_STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _queue_ui(self, callback, *args, **kwargs):
        if self._ui_state.is_closing:
            return
        try:
            self.after(0, lambda: callback(*args, **kwargs))
        except Exception:
            pass

    def _run_background_task(
        self,
        worker: Callable[[], object],
        *,
        on_success: Callable[[object], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_finally: Callable[[], None] | None = None,
    ):
        def runner():
            try:
                result = worker()
            except Exception as exc:
                if on_error is not None:
                    self._queue_ui(on_error, exc)
            else:
                if on_success is not None:
                    self._queue_ui(on_success, result)
            finally:
                if on_finally is not None:
                    self._queue_ui(on_finally)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        return thread

    def _prune_old_metadata_cache(self):
        try:
            if not METADATA_CACHE_DIR.exists():
                return
            cutoff = time.time() - METADATA_CACHE_TTL_SECONDS
            for path in METADATA_CACHE_DIR.iterdir():
                try:
                    if path.is_file() and path.stat().st_mtime < cutoff:
                        path.unlink()
                except OSError:
                    continue
        except Exception:
            pass

    def _invalidate_hash_cache(self, paths: Sequence[Path]):
        cache = self._session_state.file_hash_cache
        for path in paths:
            key = str(path.resolve(strict=False)).casefold()
            cache.pop(key, None)

    def _cached_file_hash(self, path: Path) -> str:
        stat = safe_stat(path)
        key = str(path.resolve(strict=False)).casefold()
        cache = self._session_state.file_hash_cache
        if stat is not None:
            cached = cache.get(key)
            if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
                return cached[2]
            digest = file_sha1(path)
            cache[key] = (stat.st_mtime, stat.st_size, digest)
            if len(cache) > MAX_HASH_CACHE_ENTRIES:
                oldest = next(iter(cache))
                cache.pop(oldest, None)
            return digest
        return file_sha1(path)
