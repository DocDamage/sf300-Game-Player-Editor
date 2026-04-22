from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sf3000.metadata_service import (
    build_local_metadata_card,
    fetch_metadata_card,
    load_cached_metadata,
    save_metadata_card,
)
from sf3000.models import FileRecord, MetadataCard


def make_record(root: Path, name: str = "game.gba") -> FileRecord:
    path = root / name
    path.write_bytes(b"rom")
    stat = path.stat()
    return FileRecord(
        path=path,
        display_name=path.stem,
        raw_name=path.name,
        size=stat.st_size,
        modified_text="",
        modified_ts=stat.st_mtime,
        file_type=path.suffix.lstrip(".").upper(),
        parent_name="GBA",
        warning="",
    )


class MetadataServiceTests(unittest.TestCase):
    def test_save_and_load_cached_metadata_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cache = {}
            card = MetadataCard(
                lookup_key="gba-mario",
                title="Mario",
                system="GBA",
                summary="summary",
            )

            save_metadata_card(cache, card, cache_dir)
            cache.clear()
            loaded = load_cached_metadata(cache, "gba-mario", cache_dir)

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.title, "Mario")
            self.assertEqual(cache["gba-mario"].system, "GBA")

    def test_fetch_metadata_card_falls_back_to_local_card_on_http_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = make_record(Path(tmp))
            cache = {}

            with patch("sf3000.metadata_service.http_get_json", side_effect=RuntimeError("offline")):
                card = fetch_metadata_card(
                    record,
                    lookup_key="gba-game",
                    title="Game",
                    system_name="GBA",
                    cache=cache,
                    cache_dir=Path(tmp),
                )

            self.assertEqual(card.source_name, "Local")
            self.assertIn("offline", card.summary)

    def test_fetch_metadata_card_persists_wikipedia_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            record = make_record(cache_dir)
            cache = {}
            responses = [
                {"query": {"search": [{"title": "Mario Title"}]}},
                {
                    "title": "Mario Title",
                    "description": "Platform game",
                    "extract": "A famous game.",
                    "content_urls": {"desktop": {"page": "https://example.test/mario"}},
                    "thumbnail": {"source": "https://example.test/mario.png"},
                },
            ]

            with patch("sf3000.metadata_service.http_get_json", side_effect=responses), patch(
                "sf3000.metadata_service.download_binary_file"
            ) as download_file:
                card = fetch_metadata_card(
                    record,
                    lookup_key="gba-mario",
                    title="Mario",
                    system_name="GBA",
                    cache=cache,
                    cache_dir=cache_dir,
                )

            self.assertEqual(card.source_name, "Wikipedia")
            self.assertEqual(card.title, "Mario Title")
            self.assertEqual(card.page_url, "https://example.test/mario")
            self.assertIn("gba-mario", cache)
            download_file.assert_called_once()

    def test_build_local_metadata_card_uses_explicit_lookup_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = make_record(Path(tmp))

            card = build_local_metadata_card(
                record,
                lookup_key="gba-game",
                title="Game",
                system_name="GBA",
                note="extra note",
            )

            self.assertEqual(card.lookup_key, "gba-game")
            self.assertEqual(card.title, "Game")
            self.assertIn("extra note", card.summary)


if __name__ == "__main__":
    unittest.main()
