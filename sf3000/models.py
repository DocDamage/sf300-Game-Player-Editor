from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple, Union


def _clean_title_fallback(name: str) -> str:
    path = Path(name)
    suffix = "".join(path.suffixes) if path.suffixes else ""
    stem = name[: len(name) - len(suffix)] if suffix else name
    cleaned = stem.replace("_", " ").replace(".", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_.")
    if not cleaned:
        cleaned = stem.strip() or "Renamed File"
    return f"{cleaned}{suffix}"


def normalize_game_lookup_title(name: str) -> str:
    stem = Path(name).stem
    title = stem.replace("_", " ").replace(".", " ")
    title = re.sub(r"\[[^\]]*\]", " ", title)
    title = re.sub(r"\([^)]*\)", " ", title)
    title = re.sub(r"\b(?:disc|disk|side)\s*[0-9a-z]+\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(
        r"\b(?:usa|europe|japan|world|beta|proto|prototype|demo|sample|translated)\b",
        " ",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"\brev\s*[a-z0-9]+\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\bv\d+(?:\.\d+)*\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" -_.")
    return title or _clean_title_fallback(stem)


@dataclass
class FileRecord:
    path: Path
    display_name: str
    raw_name: str
    size: int
    modified_text: str
    modified_ts: float
    file_type: str
    parent_name: str
    warning: str = ""


@dataclass
class TransferItem:
    source: Path
    destination: Path
    size: int
    overwrite: bool


@dataclass
class TransferPlan:
    items: List[TransferItem]
    skipped_identical: List[str]
    skipped_same_path: List[str]
    overwrites: List[str]
    total_bytes: int
    required_bytes: int


@dataclass
class MountCandidate:
    disk_number: int
    partition_number: int
    physical_drive: str
    friendly_name: str
    drive_letter: str
    filesystem: str
    size: int
    bus_type: str
    mount_name: str
    partition_type: str = ""
    is_offline: bool = False
    is_read_only: bool = False
    windows_recoverable: bool = False
    score: int = 0


@dataclass
class HistoryEntry:
    entry_id: int
    time_text: str
    category: str
    title: str
    detail: str = ""
    undoable: bool = False
    undo_type: str = ""
    payload: Optional["HistoryPayload"] = None
    undone: bool = False
    failed: bool = False
    failure_detail: str = ""


@dataclass
class DuplicateGroup:
    key: str
    label: str
    files: List[Path]
    size: int
    duplicate_bytes: int


@dataclass
class MetadataCard:
    lookup_key: str
    title: str
    system: str
    description: str = ""
    summary: str = ""
    page_url: str = ""
    image_url: str = ""
    image_path: str = ""
    source_name: str = "Local"


@dataclass
class DeviceLayout:
    root: Path
    roms_root: Path
    emu_root: Optional[Path] = None
    cubegm_root: Optional[Path] = None
    rootfs_root: Optional[Path] = None
    launcher_path: Optional[Path] = None
    launcher_start_path: Optional[Path] = None
    core_config_path: Optional[Path] = None
    core_filelist_path: Optional[Path] = None
    probable_sf3000: bool = False
    using_root_fallback: bool = False
    matched_signals: Tuple[str, ...] = ()


@dataclass
class CoreDefinition:
    display_name: str
    file_name: str
    extensions: Tuple[str, ...] = ()


@dataclass
class FileCoreOverride:
    relative_path: str
    core_file: str


@dataclass
class CoreCatalog:
    config_path: Optional[Path] = None
    filelist_path: Optional[Path] = None
    definitions: List[CoreDefinition] = field(default_factory=list)
    overrides: List[FileCoreOverride] = field(default_factory=list)
    override_core_by_relpath: Dict[str, str] = field(default_factory=dict)
    extensions_to_cores: Dict[str, List[str]] = field(default_factory=dict)
    core_names_by_file: Dict[str, str] = field(default_factory=dict)
    parse_errors: List[str] = field(default_factory=list)


@dataclass
class FolderSummaryRow:
    path: str
    name: str
    count: int
    issues: int


@dataclass
class StorageUsageSnapshot:
    total: int
    used: int
    free: int

    @classmethod
    def from_usage(cls, usage) -> "StorageUsageSnapshot":
        return cls(total=int(usage.total), used=int(usage.used), free=int(usage.free))


@dataclass
class GameScanBucket:
    roms_root: Path
    folder_rows: List[FolderSummaryRow] = field(default_factory=list)
    records_by_key: Dict[str, List[FileRecord]] = field(default_factory=dict)
    total_files: int = 0
    issues: int = 0


@dataclass
class EmulatorScanBucket:
    emu_root: Optional[Path] = None
    folder_rows: List[FolderSummaryRow] = field(default_factory=list)
    records_by_key: Dict[str, List[FileRecord]] = field(default_factory=dict)
    root_count: int = 0
    total_files: int = 0
    issues: int = 0


@dataclass
class BrowserSessionState:
    roms_root: Optional[Path] = None
    emu_root: Optional[Path] = None
    device_layout: Optional[DeviceLayout] = None
    core_catalog: Optional[CoreCatalog] = None
    game_records_by_key: Dict[str, List[FileRecord]] = field(default_factory=dict)
    emu_records_by_key: Dict[str, List[FileRecord]] = field(default_factory=dict)
    game_visible_map: Dict[str, FileRecord] = field(default_factory=dict)
    emu_visible_map: Dict[str, FileRecord] = field(default_factory=dict)
    current_game_key: str = "__all__"
    current_emu_key: str = "__emu_all__"
    current_game_label: str = ""
    current_emu_label: str = ""
    current_game_records: List[FileRecord] = field(default_factory=list)
    current_emu_records: List[FileRecord] = field(default_factory=list)
    pending_system_selection: str = "__all__"
    pending_emu_selection: str = "__emu_all__"
    pending_game_paths: List[str] = field(default_factory=list)
    pending_emu_paths: List[str] = field(default_factory=list)
    scan_generation: int = 0
    scan_in_progress: bool = False
    next_status_message: Optional[str] = None


@dataclass
class OperationSessionState:
    undo_cache_root: Path
    activity_log: List[Dict[str, str]] = field(default_factory=list)
    history_entries: List["HistoryEntry"] = field(default_factory=list)
    history_counter: int = 0
    file_hash_cache: Dict[str, Tuple[float, int, str]] = field(default_factory=dict)
    metadata_cache: Dict[str, "MetadataCard"] = field(default_factory=dict)
    diagnostics_snapshot: Optional["DiagnosticsContextSnapshot"] = None
    diagnostics_text_cache: str = ""
    diagnostics_request_token: int = 0


@dataclass
class UIRuntimeState:
    startup_complete: bool = False
    is_closing: bool = False
    toast_window: object | None = None
    toast_after_id: object | None = None
    tooltips: List[object] = field(default_factory=list)
    history_dialog: object | None = None
    metadata_dialog: object | None = None
    metadata_image: object | None = None
    duplicate_dialog: object | None = None
    writable_controls: List[object] = field(default_factory=list)


@dataclass
class ScanPayload:
    root: Path
    layout: DeviceLayout
    core_catalog: Optional[CoreCatalog]
    storage: Optional[StorageUsageSnapshot]
    games: GameScanBucket
    emus: EmulatorScanBucket


@dataclass
class RenameHistoryPair:
    source: Path
    destination: Path


@dataclass
class RenameHistoryPayload:
    pairs: List[RenameHistoryPair] = field(default_factory=list)


@dataclass
class CreateFoldersHistoryPayload:
    paths: List[Path] = field(default_factory=list)


@dataclass
class TransferHistoryItem:
    destination: Path
    created: bool
    backup: Optional[Path] = None
    source_origin: Optional[Path] = None


@dataclass
class TransferHistoryPayload:
    workspace: Path
    mode: str
    items: List[TransferHistoryItem] = field(default_factory=list)


@dataclass
class DeleteHistoryItem:
    path: Path
    backup: Path


@dataclass
class DeleteHistoryPayload:
    workspace: Path
    items: List[DeleteHistoryItem] = field(default_factory=list)


@dataclass
class DiagnosticsContextSnapshot:
    generated_text: str
    path_text: str
    read_only_mode: bool
    copy_mode: str
    delete_to_recycle: bool
    current_status: str
    roms_root: Optional[Path]
    emu_root: Optional[Path]
    dev_reference_repo: Optional[Path]
    device_layout: Optional[DeviceLayout]
    core_catalog: Optional[CoreCatalog]
    activity_log: List[Dict[str, str]] = field(default_factory=list)


HistoryPayload = Union[
    RenameHistoryPayload,
    CreateFoldersHistoryPayload,
    TransferHistoryPayload,
    DeleteHistoryPayload,
]


def history_payload_workspace(payload: Optional[HistoryPayload]) -> Optional[Path]:
    if isinstance(payload, (TransferHistoryPayload, DeleteHistoryPayload)):
        return payload.workspace
    return None


__all__ = [
    "BrowserSessionState",
    "CoreCatalog",
    "CoreDefinition",
    "CreateFoldersHistoryPayload",
    "DeleteHistoryItem",
    "DeleteHistoryPayload",
    "DiagnosticsContextSnapshot",
    "DeviceLayout",
    "DuplicateGroup",
    "EmulatorScanBucket",
    "FileCoreOverride",
    "FileRecord",
    "FolderSummaryRow",
    "GameScanBucket",
    "HistoryEntry",
    "HistoryPayload",
    "MetadataCard",
    "MountCandidate",
    "OperationSessionState",
    "RenameHistoryPair",
    "RenameHistoryPayload",
    "ScanPayload",
    "StorageUsageSnapshot",
    "TransferHistoryItem",
    "TransferHistoryPayload",
    "TransferItem",
    "TransferPlan",
    "UIRuntimeState",
    "history_payload_workspace",
    "normalize_game_lookup_title",
]
