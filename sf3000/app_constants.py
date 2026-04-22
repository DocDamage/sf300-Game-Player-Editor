from pathlib import Path

APP_STATE_FILE = Path.home() / ".sf3000_game_manager.json"
APP_CACHE_DIR = Path.home() / ".sf3000_game_manager_cache"
METADATA_CACHE_DIR = APP_CACHE_DIR / "metadata"
RUNTIME_LOG_FILE = APP_CACHE_DIR / "runtime.log"
LOW_SPACE_WARNING_BYTES = 256 * 1024 * 1024
MAX_LOG_ENTRIES = 500
MAX_HISTORY_ENTRIES = 160
MAX_HASH_CACHE_ENTRIES = 2048
METADATA_CACHE_TTL_SECONDS = 14 * 24 * 60 * 60
TK_PHOTO_EXTENSIONS = {".png", ".gif", ".ppm", ".pgm"}
APP_WINDOW_TITLE = "SF3000 Game Manager"
