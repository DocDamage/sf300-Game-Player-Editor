from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import string
import struct
import tempfile
import tkinter as tk
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Sequence, Tuple

from .models import CoreCatalog, CoreDefinition, DeviceLayout, FileCoreOverride, FileRecord


SYSTEM_EXTENSIONS = {
    "3DO": [".iso", ".bin", ".cue"],
    "Amstrad CPC": [".dsk", ".cpr", ".zip"],
    "Arcade / MAME": [".zip", ".7z"],
    "Atari 2600": [".a26"],
    "Atari 5200": [".a52"],
    "Atari 7800": [".a78"],
    "Atari 800/XL/XE": [".atr", ".xex", ".xfd", ".cas"],
    "Atari Jaguar": [".j64", ".jag"],
    "Atari Lynx": [".lnx"],
    "Atari ST": [".st", ".msa", ".stx"],
    "Amiga": [".adf", ".hdf"],
    "BBC Micro": [".ssd", ".dsd", ".uef"],
    "Commodore 64": [".d64", ".t64", ".prg", ".crt"],
    "ColecoVision": [".col"],
    "DOS": [".exe", ".com"],
    "Dreamcast": [".cdi", ".gdi", ".chd"],
    "FDS": [".fds"],
    "Game & Watch": [".mgw"],
    "Game Boy": [".gb", ".gbc"],
    "GBA": [".gba"],
    "Game Gear": [".gg"],
    "GameCube": [".iso", ".gcm"],
    "Intellivision": [".int"],
    "Mega Duck": [".bin"],
    "MSX": [".rom", ".mx1", ".mx2"],
    "N64": [".n64", ".z64", ".v64"],
    "NDS": [".nds"],
    "NES": [".nes"],
    "Neo Geo": [".zip"],
    "Neo Geo Pocket": [".ngp", ".ngc"],
    "Odyssey2 / Videopac": [".bin"],
    "PC Engine": [".pce", ".ccd"],
    "PC Engine CD": [".cue", ".iso", ".chd"],
    "PICO-8": [".p8", ".png"],
    "Pokemon Mini": [".min"],
    "PSP": [".iso", ".cso", ".pbp"],
    "PlayStation": [".bin", ".cue", ".img", ".iso", ".pbp", ".chd"],
    "PlayStation 2": [".iso", ".bin", ".chd"],
    "Saturn": [".cue", ".bin", ".iso", ".chd", ".mdf"],
    "ScummVM": [".scummvm"],
    "Sega 32X": [".32x"],
    "Sega CD": [".bin", ".cue", ".chd", ".iso"],
    "Sega Genesis": [".md", ".gen"],
    "Sega Master System": [".sms"],
    "Sega Naomi": [".zip", ".7z"],
    "Sega Pico": [".md", ".bin"],
    "SG-1000": [".sg", ".sc"],
    "SNES": [".smc", ".sfc", ".fig"],
    "Supervision": [".sv"],
    "TurboGrafx-16": [".pce"],
    "Vectrex": [".vec", ".bin"],
    "Virtual Boy": [".vb"],
    "Wii": [".iso", ".wbfs"],
    "Wonderswan": [".ws", ".wsc"],
    "ZX Spectrum": [".z80", ".tap", ".tzx", ".sna"],
    "ZX81": [".p", ".tzx"],
}

SYSTEM_FOLDER_ALIASES = {
    "arcade": "Arcade / MAME",
    "mame": "Arcade / MAME",
    "atari800": "Atari 800/XL/XE",
    "atari xl xe": "Atari 800/XL/XE",
    "gb": "Game Boy",
    "gbc": "Game Boy",
    "megadrive": "Sega Genesis",
    "mega drive": "Sega Genesis",
    "genesis": "Sega Genesis",
    "mastersystem": "Sega Master System",
    "master system": "Sega Master System",
    "sms": "Sega Master System",
    "tg16": "TurboGrafx-16",
    "turbografx16": "TurboGrafx-16",
    "turbografx": "TurboGrafx-16",
    "pce": "PC Engine",
    "pcengine": "PC Engine",
    "pcenginecd": "PC Engine CD",
    "segacd": "Sega CD",
    "psx": "PlayStation",
    "ps1": "PlayStation",
    "ps2": "PlayStation 2",
    "videopac": "Odyssey2 / Videopac",
    "odyssey2": "Odyssey2 / Videopac",
}

COMMON_SYSTEM_FOLDERS = [
    "Arcade",
    "NES",
    "SNES",
    "Game Boy",
    "GBA",
    "Genesis",
    "Game Gear",
    "N64",
    "PlayStation",
    "Neo Geo",
]

ROMS_FOLDER_CANDIDATES = ("Roms", "roms", "ROMS", "ROMs")
EMU_ROOT_CREATE_OPTIONS = ("cubegm/cores", "Emulators", "cores", "retroarch/cores")
EMULATOR_EXTENSIONS = [".so", ".sh", ".elf", ".bin", ".pak"]
EMULATOR_FOLDER_CANDIDATES = (
    "cubegm/cores",
    "cubegm/Cores",
    "CUBEGM/CORES",
    "Emulators",
    "emulators",
    "EMULATORS",
    "cores",
    "Cores",
    "CORES",
    "retroarch/cores",
    "RetroArch/cores",
)
SF3000_RESERVED_ROOT_DIRS = {
    "rootfs",
    "cubegm",
    "emulators",
    "cores",
    "retroarch",
}
SF3000_EXPECTED_CORE_SUPPORT_FILES = {"config.xml", "filelist.xml"}
SF3000_EXPECTED_LAUNCHER_FILES = {"icube", "icube.sh", "icube_start.sh", "icubemp_start.sh"}
STOCK_CUBEGM_DIRS = ("cores", "language", "lib", "saves", "states", "usr")
STOCK_CUBEGM_FILES = ("icube", "icube.sh", "icube_start.sh", "setting.xml")
DEV_REPO_CANDIDATE_DIRS = ("_sf3000_700zx1_dev", "sf3000-dev")
DEV_REPO_REQUIRED_FILES = ("Dockerfile", "Makefile.sf3000", "buildRun.sh")


def _system_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


SYSTEM_EXTENSION_LOOKUP: Dict[str, Tuple[str, ...]] = {}
for system_name, extensions in SYSTEM_EXTENSIONS.items():
    SYSTEM_EXTENSION_LOOKUP[_system_key(system_name)] = tuple(ext.lower() for ext in extensions)
for alias, system_name in SYSTEM_FOLDER_ALIASES.items():
    SYSTEM_EXTENSION_LOOKUP[_system_key(alias)] = tuple(
        ext.lower() for ext in SYSTEM_EXTENSIONS[system_name]
    )

ALL_ROM_EXTENSIONS = tuple(sorted({ext.lower() for exts in SYSTEM_EXTENSIONS.values() for ext in exts}))
ALL_ROM_EXTENSION_SET = set(ALL_ROM_EXTENSIONS)
EMULATOR_EXTENSION_SET = {ext.lower() for ext in EMULATOR_EXTENSIONS}


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding, errors="replace")
        except OSError:
            raise
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def iter_files_recursive(folder: Path) -> List[Path]:
    try:
        files = [path for path in folder.rglob("*") if path.is_file()]
    except Exception:
        return []
    return sorted(files, key=lambda path: str(path).casefold())


def safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def safe_stat(path: Path) -> Optional[os.stat_result]:
    try:
        return path.stat()
    except OSError:
        return None


def list_child_dirs(folder: Path) -> List[Path]:
    try:
        return sorted([d for d in folder.iterdir() if d.is_dir()], key=lambda p: p.name.lower())
    except Exception:
        return []


def list_child_files(folder: Path) -> List[Path]:
    try:
        return sorted([f for f in folder.iterdir() if f.is_file()], key=lambda p: p.name.lower())
    except Exception:
        return []


def parse_cue_references(path: Path) -> List[Path]:
    refs = []
    try:
        content = read_text_file(path)
    except OSError:
        return refs

    for line in content.splitlines():
        match = re.match(r'^\s*FILE\s+"([^"]+)"', line, re.IGNORECASE)
        if not match:
            match = re.match(r"^\s*FILE\s+(\S+)", line, re.IGNORECASE)
        if not match:
            continue
        candidate = (path.parent / match.group(1)).resolve(strict=False)
        if safe_exists(candidate):
            refs.append(candidate)
    return refs


def parse_m3u_references(path: Path) -> List[Path]:
    refs = []
    try:
        content = read_text_file(path)
    except OSError:
        return refs

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        candidate = (path.parent / line).resolve(strict=False)
        if safe_exists(candidate):
            refs.append(candidate)
    return refs


def parse_gdi_references(path: Path) -> List[Path]:
    refs = []
    try:
        content = read_text_file(path)
    except OSError:
        return refs

    for line in content.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        filename = parts[4].strip('"')
        candidate = (path.parent / filename).resolve(strict=False)
        if safe_exists(candidate):
            refs.append(candidate)
    return refs


def related_disc_files(path: Path) -> List[Path]:
    suffix = path.suffix.casefold()
    if suffix == ".cue":
        return parse_cue_references(path)
    if suffix == ".m3u":
        return parse_m3u_references(path)
    if suffix == ".gdi":
        return parse_gdi_references(path)
    if suffix == ".ccd":
        return [candidate for ext in (".img", ".sub") if safe_exists(candidate := path.with_suffix(ext))]
    if suffix == ".mds":
        return [candidate for ext in (".mdf",) if safe_exists(candidate := path.with_suffix(ext))]
    return []


def expand_game_import_files(files: Sequence[str]) -> Tuple[List[str], List[str]]:
    pending = [Path(file_name) for file_name in files]
    initial = {str(Path(file_name).resolve(strict=False)).casefold() for file_name in files}
    seen = set()
    result: List[str] = []
    auto_added: List[str] = []

    while pending:
        path = pending.pop(0)
        if not safe_exists(path) or not path.is_file():
            continue
        key = str(path.resolve(strict=False)).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(str(path))
        if key not in initial:
            auto_added.append(path.name)
        for related in related_disc_files(path):
            related_key = str(related.resolve(strict=False)).casefold()
            if related_key not in seen:
                pending.append(related)

    return result, auto_added


def sanitize_zip_member(name: str) -> Optional[Path]:
    if not name or name.endswith("/"):
        return None
    try:
        pure_path = PurePosixPath(name)
    except Exception:
        return None
    if pure_path.is_absolute() or ".." in pure_path.parts:
        return None
    parts = [part for part in pure_path.parts if part not in ("", ".")]
    if not parts:
        return None
    return Path(*parts)


def slugify_filename(text: str, default: str = "item") -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return safe or default


def clean_filename(name: str) -> str:
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
    return title or clean_filename(stem)


def file_sha1(path: Path, chunk_size: int = 1024 * 1024) -> str:
    import hashlib

    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def http_get_json(url: str, timeout: int = 12) -> Dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "SF3000GameManager/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def download_binary_file(url: str, destination: Path, timeout: int = 20):
    request = urllib.request.Request(url, headers={"User-Agent": "SF3000GameManager/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        destination.write_bytes(response.read())


def get_windows_drives() -> List[str]:
    drives: List[str] = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:\\"
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                if drive_type in (2, 3):
                    drives.append(drive)
            bitmask >>= 1
    except Exception:
        pass
    return drives


def normalize_sf3000_root(root: Path) -> Path:
    name = root.name.casefold()
    parent = root.parent
    parent_name = parent.name.casefold() if parent != root else ""

    if name in {candidate.casefold() for candidate in ROMS_FOLDER_CANDIDATES} | {"rootfs", "cubegm"}:
        return parent

    if name == "cores" and parent_name in {"cubegm", "retroarch"}:
        return parent.parent if parent.parent != parent else parent

    return root


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except Exception:
        return str(left).casefold() == str(right).casefold()


def same_drive(left: Path, right: Path) -> bool:
    return left.anchor.casefold() == right.anchor.casefold()


def files_are_identical(left: Path, right: Path, chunk_size: int = 1024 * 1024) -> bool:
    left_stat = safe_stat(left)
    right_stat = safe_stat(right)
    if left_stat is None or right_stat is None:
        return False
    if left_stat.st_size != right_stat.st_size:
        return False

    try:
        with left.open("rb") as left_file, right.open("rb") as right_file:
            while True:
                left_chunk = left_file.read(chunk_size)
                right_chunk = right_file.read(chunk_size)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    except OSError:
        return False


def create_temp_destination(dest_folder: Path, suffix: str = "") -> Path:
    fd, temp_name = tempfile.mkstemp(
        prefix=".__sf3000_tmp_",
        suffix=suffix,
        dir=str(dest_folder),
    )
    os.close(fd)
    return Path(temp_name)


def _safe_destroy(widget):
    try:
        widget.destroy()
    except Exception:
        pass


def _first_existing_dir(root: Path, candidates: Sequence[str]) -> Optional[Path]:
    for candidate in candidates:
        folder = root / candidate
        if safe_is_dir(folder):
            return folder
    return None


def inspect_device_layout(root: Path) -> DeviceLayout:
    normalized_root = normalize_sf3000_root(root)
    cubegm_root = normalized_root / "cubegm"
    if not safe_is_dir(cubegm_root):
        cubegm_root = None

    rootfs_root = normalized_root / "rootfs"
    if not safe_is_dir(rootfs_root):
        rootfs_root = None

    roms_root = _first_existing_dir(normalized_root, ROMS_FOLDER_CANDIDATES) or normalized_root
    emu_root = _first_existing_dir(normalized_root, EMULATOR_FOLDER_CANDIDATES)

    launcher_path = cubegm_root / "icube" if cubegm_root and safe_exists(cubegm_root / "icube") else None
    launcher_start_path = (
        cubegm_root / "icube_start.sh"
        if cubegm_root and safe_exists(cubegm_root / "icube_start.sh")
        else None
    )

    core_config_path = None
    core_filelist_path = None
    if emu_root is not None:
        config_candidate = emu_root / "config.xml"
        filelist_candidate = emu_root / "filelist.xml"
        if safe_exists(config_candidate):
            core_config_path = config_candidate
        if safe_exists(filelist_candidate):
            core_filelist_path = filelist_candidate

    matched_signals = []
    if rootfs_root is not None:
        matched_signals.append("rootfs/")
    if cubegm_root is not None:
        matched_signals.append("cubegm/")
    if launcher_path is not None:
        matched_signals.append("cubegm/icube")
    if emu_root is not None and emu_root.name.casefold() == "cores":
        try:
            if same_path(emu_root.parent, cubegm_root) if cubegm_root else False:
                matched_signals.append("cubegm/cores")
            else:
                matched_signals.append(str(emu_root.relative_to(normalized_root)))
        except Exception:
            matched_signals.append(str(emu_root))
    if core_config_path is not None:
        matched_signals.append("cores/config.xml")
    if core_filelist_path is not None:
        matched_signals.append("cores/filelist.xml")

    probable_sf3000 = len(matched_signals) >= 2 or bool(
        cubegm_root and launcher_path and emu_root and emu_root.name.casefold() == "cores"
    )

    return DeviceLayout(
        root=normalized_root,
        roms_root=roms_root,
        emu_root=emu_root,
        cubegm_root=cubegm_root,
        rootfs_root=rootfs_root,
        launcher_path=launcher_path,
        launcher_start_path=launcher_start_path,
        core_config_path=core_config_path,
        core_filelist_path=core_filelist_path,
        probable_sf3000=probable_sf3000,
        using_root_fallback=same_path(roms_root, normalized_root),
        matched_signals=tuple(matched_signals),
    )


def _read_text_loose(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return path.read_text(encoding="latin-1", errors="ignore")
    except Exception:
        return ""


def _parse_fragment_xml(path: Path, expected_tag: str) -> Optional[ET.Element]:
    if not path or not safe_exists(path):
        return None
    text = _read_text_loose(path).strip()
    if not text:
        return None

    text = re.sub(r"<\?xml[^>]*\?>", "", text, flags=re.IGNORECASE).strip()
    wrapped = f"<root>\n{text}\n</root>"
    root = ET.fromstring(wrapped)
    return root if root.findall(expected_tag) else None


def _normalize_supported_extension(value: str) -> str:
    text = str(value or "").strip().lstrip(".").casefold()
    return f".{text}" if text else ""


def _normalize_override_path(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    return "/".join(parts).casefold()


def load_core_catalog(layout: Optional[DeviceLayout]) -> Optional[CoreCatalog]:
    if layout is None or layout.emu_root is None:
        return None

    catalog = CoreCatalog(
        config_path=layout.core_config_path,
        filelist_path=layout.core_filelist_path,
    )

    if layout.core_config_path is not None:
        try:
            root = _parse_fragment_xml(layout.core_config_path, "core")
            if root is None:
                catalog.parse_errors.append("config.xml could not be parsed as expected core fragments.")
            else:
                for core_node in root.findall("core"):
                    emucore = core_node.find("emucore")
                    if emucore is None:
                        continue
                    file_name = Path(str(emucore.get("file") or emucore.get("name") or "").strip()).name
                    display_name = str(emucore.get("name") or file_name or "Unknown Core").strip()
                    extensions = []
                    seen_extensions = set()
                    for ext_node in core_node.findall("supported_extensions"):
                        normalized = _normalize_supported_extension(ext_node.text or "")
                        if not normalized or normalized in seen_extensions:
                            continue
                        seen_extensions.add(normalized)
                        extensions.append(normalized)
                        if file_name:
                            catalog.extensions_to_cores.setdefault(normalized, []).append(file_name)
                    if file_name:
                        catalog.definitions.append(
                            CoreDefinition(
                                display_name=display_name,
                                file_name=file_name,
                                extensions=tuple(extensions),
                            )
                        )
                        catalog.core_names_by_file[file_name.casefold()] = display_name
        except Exception as exc:
            catalog.parse_errors.append(f"config.xml parse error: {exc}")

    if layout.core_filelist_path is not None:
        try:
            root = _parse_fragment_xml(layout.core_filelist_path, "file")
            if root is None:
                catalog.parse_errors.append("filelist.xml could not be parsed as expected file fragments.")
            else:
                for file_node in root.findall("file"):
                    relative_path = _normalize_override_path(file_node.get("name") or "")
                    core_file = Path(str(file_node.get("core") or "").strip()).name
                    if relative_path and core_file:
                        catalog.overrides.append(
                            FileCoreOverride(relative_path=relative_path, core_file=core_file)
                        )
                        catalog.override_core_by_relpath.setdefault(relative_path, core_file)
        except Exception as exc:
            catalog.parse_errors.append(f"filelist.xml parse error: {exc}")

    return catalog


def catalog_supports_extension(catalog: Optional[CoreCatalog], suffix: str) -> bool:
    normalized = _normalize_supported_extension(suffix)
    return bool(normalized and catalog and catalog.extensions_to_cores.get(normalized))


def catalog_override_for_relpath(catalog: Optional[CoreCatalog], relative_path: str) -> str:
    normalized = _normalize_override_path(relative_path)
    if not normalized or catalog is None:
        return ""
    return catalog.override_core_by_relpath.get(normalized, "")


def get_stock_cubegm_reference_issues(layout: Optional[DeviceLayout]) -> List[str]:
    if layout is None or layout.cubegm_root is None or not layout.probable_sf3000:
        return []

    issues = []
    for folder_name in STOCK_CUBEGM_DIRS:
        if not safe_is_dir(layout.cubegm_root / folder_name):
            issues.append(f"Missing stock cubegm folder '{folder_name}/'.")
    for file_name in STOCK_CUBEGM_FILES:
        if not safe_exists(layout.cubegm_root / file_name):
            issues.append(f"Missing stock cubegm file '{file_name}'.")
    return issues


def find_dev_reference_repo() -> Optional[Path]:
    script_root = Path(__file__).resolve().parent.parent
    candidates = [script_root.parent / name for name in DEV_REPO_CANDIDATE_DIRS]
    candidates.extend(Path.home() / "dev" / name for name in DEV_REPO_CANDIDATE_DIRS)

    for candidate in candidates:
        if not safe_is_dir(candidate):
            continue
        if all(safe_exists(candidate / filename) for filename in DEV_REPO_REQUIRED_FILES):
            return candidate
    return None


def looks_like_cubegm_subtree_reference(layout: Optional[DeviceLayout]) -> bool:
    if layout is None or layout.cubegm_root is None or layout.rootfs_root is not None:
        return False
    child_dirs = {
        folder.name.casefold()
        for folder in list_child_dirs(layout.root)
        if not folder.name.startswith(".")
    }
    return child_dirs == {"cubegm"}


def describe_sf3000_core_name_issue(path: Path) -> str:
    name = path.name.casefold()
    if path.suffix.casefold() == ".sh" and name not in SF3000_EXPECTED_LAUNCHER_FILES:
        return "Shell scripts are unusual here; SF3000 custom cores are usually .so files"
    if "libretro" in name and not name.endswith("_libretro_sf3000.so"):
        return "Libretro core name does not target SF3000 (_libretro_sf3000.so expected)"
    return ""


def describe_elf_shared_object_issue(path: Path) -> str:
    if path.suffix.casefold() != ".so":
        return ""
    try:
        with path.open("rb") as handle:
            header = handle.read(32)
    except Exception as exc:
        return f"Could not read shared library header: {exc}"

    if len(header) < 20:
        return "Shared library is too small to contain a valid ELF header"
    if header[:4] != b"\x7fELF":
        return "Shared library is not an ELF binary"

    elf_class = header[4]
    elf_data = header[5]
    if elf_class != 1:
        return "Shared library is not ELF32"
    if elf_data != 1:
        return "Shared library is not little-endian"

    endian = "<"
    try:
        elf_type = struct.unpack(endian + "H", header[16:18])[0]
        machine = struct.unpack(endian + "H", header[18:20])[0]
    except struct.error:
        return "Shared library has an incomplete ELF header"

    if elf_type != 3:
        return "ELF binary is not a shared library"
    if machine != 8:
        return "ELF binary is not built for MIPS"
    return ""


def get_core_catalog_issues(layout: Optional[DeviceLayout], catalog: Optional[CoreCatalog]) -> List[str]:
    if layout is None or catalog is None or layout.emu_root is None:
        return []

    issues = list(catalog.parse_errors)
    seen_core_files = set()
    duplicate_core_files = set()

    for definition in catalog.definitions:
        key = definition.file_name.casefold()
        if key in seen_core_files:
            duplicate_core_files.add(definition.file_name)
        seen_core_files.add(key)
        if not safe_exists(layout.emu_root / definition.file_name):
            issues.append(f"config.xml references missing core '{definition.file_name}'.")

    override_seen = set()
    duplicate_override_paths = set()
    for override in catalog.overrides:
        if override.relative_path in override_seen:
            duplicate_override_paths.add(override.relative_path)
        override_seen.add(override.relative_path)
        if override.core_file.casefold() not in catalog.core_names_by_file:
            issues.append(
                f"filelist.xml override '{override.relative_path}' points to unknown core '{override.core_file}'."
            )

    for name in sorted(duplicate_core_files):
        issues.append(f"config.xml declares '{name}' more than once.")
    for name in sorted(duplicate_override_paths):
        issues.append(f"filelist.xml declares '{name}' more than once.")

    for file_path in list_child_files(layout.emu_root):
        if file_path.suffix.casefold() != ".so":
            continue
        if file_path.name.casefold() not in catalog.core_names_by_file:
            backup_match = layout.emu_root / "backup" / file_path.name
            if safe_exists(backup_match):
                continue
            issues.append(f"'{file_path.name}' exists in cores but is not referenced in config.xml.")

    vice_cores = [
        file_path.name
        for file_path in list_child_files(layout.emu_root)
        if re.match(r"^vice_.*_libretro_sf3000\.so$", file_path.name, re.IGNORECASE)
    ]
    if vice_cores and not safe_is_dir(layout.root / "system" / "vice"):
        issues.append(
            "VICE-style libretro cores were found, but the expected support folder 'system/vice/' is missing."
        )

    return issues


def get_layout_issues(layout: Optional[DeviceLayout]) -> List[str]:
    if layout is None or not layout.probable_sf3000:
        return []

    issues = []
    if layout.rootfs_root is None and not looks_like_cubegm_subtree_reference(layout):
        issues.append("Missing expected 'rootfs/' system directory.")
    if layout.cubegm_root is None:
        issues.append("Missing expected 'cubegm/' launcher directory.")
    if layout.cubegm_root is not None and layout.launcher_path is None:
        issues.append("Missing expected launcher file 'cubegm/icube'.")
    if layout.cubegm_root is not None and layout.emu_root is None:
        issues.append("Missing expected emulator core folder 'cubegm/cores'.")
    if layout.emu_root is not None and layout.core_config_path is None:
        issues.append("Missing expected core mapping file 'config.xml'.")
    if layout.emu_root is not None and layout.core_filelist_path is None:
        issues.append("Missing expected launcher file list 'filelist.xml'.")
    return issues


def iter_game_folders(
    roms_root: Path,
    layout: Optional[DeviceLayout] = None,
    catalog: Optional[CoreCatalog] = None,
) -> List[Path]:
    folders = list_child_dirs(roms_root)
    if layout is None or not same_path(roms_root, layout.root):
        return folders

    filtered = []
    for folder in folders:
        name_key = folder.name.casefold()
        if name_key in SF3000_RESERVED_ROOT_DIRS:
            continue
        if get_system_extensions(folder.name) is not None:
            filtered.append(folder)
            continue
        files = list_child_files(folder)
        if any(is_rom_file(path) or catalog_supports_extension(catalog, path.suffix) for path in files):
            filtered.append(folder)
    return filtered


def find_roms_root(root: Path) -> Path:
    return inspect_device_layout(root).roms_root


def find_emulators_root(root: Path) -> Optional[Path]:
    return inspect_device_layout(root).emu_root


def get_system_extensions(system_name: str) -> Optional[Tuple[str, ...]]:
    return SYSTEM_EXTENSION_LOOKUP.get(_system_key(system_name))


def is_rom_file(path: Path) -> bool:
    return path.suffix.casefold() in ALL_ROM_EXTENSION_SET


def is_emulator_file(path: Path) -> bool:
    return path.suffix.casefold() in EMULATOR_EXTENSION_SET


def build_file_record(
    path: Path,
    display_name: str,
    parent_name: str,
    warning: str = "",
) -> FileRecord:
    stat = safe_stat(path)
    size = stat.st_size if stat else 0
    modified_ts = stat.st_mtime if stat else 0.0
    modified_text = (
        datetime.fromtimestamp(modified_ts).strftime("%Y-%m-%d  %H:%M")
        if modified_ts
        else ""
    )
    return FileRecord(
        path=path,
        display_name=display_name,
        raw_name=path.name,
        size=size,
        modified_text=modified_text,
        modified_ts=modified_ts,
        file_type=path.suffix.lstrip(".").upper() or "--",
        parent_name=parent_name,
        warning=warning,
    )


def build_game_warning(
    path: Path,
    system_name: str,
    catalog: Optional[CoreCatalog] = None,
    relative_path: str = "",
) -> str:
    suffix = path.suffix.casefold()
    override_core = catalog_override_for_relpath(catalog, relative_path)
    if override_core:
        return ""
    allowed = get_system_extensions(system_name)
    if allowed is None:
        if catalog_supports_extension(catalog, suffix):
            return "Supported by core config; folder alias unknown"
        if suffix in ALL_ROM_EXTENSION_SET:
            return "Unknown system folder"
        return "Unsupported ROM file"
    if suffix in allowed:
        return ""
    if catalog_supports_extension(catalog, suffix):
        return f"Supported by core config, not typical for {system_name}"
    if suffix in ALL_ROM_EXTENSION_SET:
        return f"Not typical for {system_name}"
    return "Unsupported ROM file"


def build_emulator_warning(path: Path, catalog: Optional[CoreCatalog] = None) -> str:
    if path.name.casefold() in SF3000_EXPECTED_CORE_SUPPORT_FILES | SF3000_EXPECTED_LAUNCHER_FILES:
        return ""
    name_issue = describe_sf3000_core_name_issue(path)
    if name_issue:
        return name_issue
    if is_emulator_file(path):
        elf_issue = describe_elf_shared_object_issue(path)
        if elf_issue:
            return elf_issue
        if (
            catalog is not None
            and path.suffix.casefold() == ".so"
            and catalog.core_names_by_file
            and path.name.casefold() not in catalog.core_names_by_file
        ):
            return "Core is not referenced in config.xml"
        return ""
    return "Unsupported emulator file"


def fuzzy_contains(text: str, query: str) -> bool:
    haystack = text.casefold()
    needle = query.casefold()
    if not needle:
        return True
    if needle in haystack:
        return True
    it = iter(haystack)
    return all(char in it for char in needle)


def record_matches_query(record: FileRecord, query: str) -> bool:
    if not query:
        return True

    search_text = " ".join(
        [
            record.display_name,
            record.raw_name,
            record.file_type,
            record.parent_name,
            record.warning,
            str(record.path),
        ]
    )

    tokens = [token for token in query.split() if token]
    for token in tokens:
        token_cf = token.casefold()
        if token_cf.startswith("."):
            if record.path.suffix.casefold() != token_cf:
                return False
            continue
        if not fuzzy_contains(search_text, token_cf):
            return False
    return True


def sanitize_windows_name(name: str) -> str:
    safe_name = "".join(char for char in name if char not in r'\/:*?"<>|')
    return safe_name.strip().rstrip(".")


def format_name_list(names: Sequence[str], limit: int = 10) -> str:
    body = "\n".join(names[:limit])
    if len(names) > limit:
        body += f"\n...and {len(names) - limit} more"
    return body
