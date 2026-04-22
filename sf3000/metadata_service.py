from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Dict, Optional

from sf3000.app_constants import METADATA_CACHE_DIR, TK_PHOTO_EXTENSIONS
from sf3000.layout import (
    download_binary_file,
    http_get_json,
)
from sf3000.models import FileRecord, MetadataCard
from sf3000.ui_common import format_size


def metadata_cache_path(lookup_key: str, cache_dir: Path = METADATA_CACHE_DIR) -> Path:
    return cache_dir / f"{lookup_key}.json"


def metadata_image_path(lookup_key: str, url: str, cache_dir: Path = METADATA_CACHE_DIR) -> Path:
    suffix = Path(urllib.parse.urlparse(url).path).suffix or ".img"
    return cache_dir / f"{lookup_key}{suffix}"


def load_cached_metadata(
    cache: Dict[str, MetadataCard],
    lookup_key: str,
    cache_dir: Path = METADATA_CACHE_DIR,
) -> Optional[MetadataCard]:
    if lookup_key in cache:
        return cache[lookup_key]
    cache_path = metadata_cache_path(lookup_key, cache_dir)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    card = MetadataCard(**payload)
    cache[lookup_key] = card
    return card


def save_metadata_card(
    cache: Dict[str, MetadataCard],
    card: MetadataCard,
    cache_dir: Path = METADATA_CACHE_DIR,
):
    cache[card.lookup_key] = card
    try:
        metadata_cache_path(card.lookup_key, cache_dir).write_text(
            json.dumps(card.__dict__, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def build_local_metadata_card(
    record: FileRecord,
    lookup_key: str,
    title: str,
    system_name: str,
    note: str = "",
) -> MetadataCard:
    summary_lines = [
        f"Title: {title}",
        f"System: {system_name}",
        f"Filename: {record.raw_name}",
        f"Folder: {record.parent_name}",
        f"Size: {format_size(record.size)}",
        f"Modified: {record.modified_text or 'Unknown'}",
    ]
    if record.warning:
        summary_lines.append(f"Warning: {record.warning}")
    if note:
        summary_lines.extend(["", note])
    return MetadataCard(
        lookup_key=lookup_key,
        title=title,
        system=system_name,
        description="Local file details",
        summary="\n".join(summary_lines),
        source_name="Local",
    )


def fetch_metadata_card(
    record: FileRecord,
    *,
    lookup_key: str,
    title: str,
    system_name: str,
    cache: Dict[str, MetadataCard],
    force_refresh: bool = False,
    cache_dir: Path = METADATA_CACHE_DIR,
) -> MetadataCard:
    if not force_refresh:
        cached = load_cached_metadata(cache, lookup_key, cache_dir)
        if cached is not None:
            return cached

    search_query = f"{title} {system_name} video game".strip()
    search_url = (
        "https://en.wikipedia.org/w/api.php?action=query&format=json&list=search&srlimit=5&srsearch="
        + urllib.parse.quote(search_query)
    )

    try:
        search_payload = http_get_json(search_url, timeout=12)
        results = (((search_payload.get("query") or {}).get("search")) or [])
        wiki_title = str(results[0]["title"]).strip() if results else title
        summary_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(
            wiki_title,
            safe="",
        )
        summary_payload = http_get_json(summary_url, timeout=12)
    except Exception as exc:
        return build_local_metadata_card(
            record,
            lookup_key=lookup_key,
            title=title,
            system_name=system_name,
            note=f"Online lookup was unavailable: {exc}",
        )

    page_url = ""
    content_urls = summary_payload.get("content_urls") or {}
    desktop = content_urls.get("desktop") or {}
    if desktop.get("page"):
        page_url = str(desktop.get("page"))

    image_url = ""
    image_path = ""
    thumbnail = summary_payload.get("thumbnail") or {}
    if thumbnail.get("source"):
        image_url = str(thumbnail.get("source"))
        candidate_path = metadata_image_path(lookup_key, image_url, cache_dir)
        if candidate_path.suffix.casefold() in TK_PHOTO_EXTENSIONS:
            if force_refresh or not candidate_path.exists():
                try:
                    download_binary_file(image_url, candidate_path)
                except Exception:
                    candidate_path = Path("")
            if str(candidate_path):
                image_path = str(candidate_path)

    card = MetadataCard(
        lookup_key=lookup_key,
        title=str(summary_payload.get("title") or title),
        system=system_name,
        description=str(summary_payload.get("description") or "Wikipedia summary"),
        summary=str(summary_payload.get("extract") or "").strip()
        or build_local_metadata_card(
            record,
            lookup_key=lookup_key,
            title=title,
            system_name=system_name,
        ).summary,
        page_url=page_url,
        image_url=image_url,
        image_path=image_path,
        source_name="Wikipedia",
    )
    save_metadata_card(cache, card, cache_dir)
    return card
