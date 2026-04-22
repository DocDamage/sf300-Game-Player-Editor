from __future__ import annotations

import tkinter as tk
import webbrowser
from base64 import b64encode
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, Optional, Tuple

from sf3000.layout import normalize_game_lookup_title, slugify_filename
from sf3000.metadata_service import (
    build_local_metadata_card,
    fetch_metadata_card,
    load_cached_metadata,
    save_metadata_card,
)
from sf3000.models import FileRecord, MetadataCard
from sf3000.ui_common import format_size


class SF3000MetadataMixin:
    def _selected_metadata_record(self) -> Optional[FileRecord]:
        if self._notebook.index(self._notebook.select()) == 0:
            records = self._selected_game_records()
        else:
            records = self._selected_emu_records()
        return records[0] if records else None

    def _metadata_lookup_key(self, record: FileRecord) -> str:
        system_name = record.parent_name or (
            self._browser_state.current_game_label
            if self._notebook.index(self._notebook.select()) == 0
            else "Emulator"
        )
        return slugify_filename(f"{system_name}-{normalize_game_lookup_title(record.raw_name)}")

    def _load_cached_metadata(self, lookup_key: str) -> Optional[MetadataCard]:
        return load_cached_metadata(self._session_state.metadata_cache, lookup_key)

    def _save_metadata_card(self, card: MetadataCard):
        save_metadata_card(self._session_state.metadata_cache, card)

    def _build_local_metadata_card(self, record: FileRecord, note: str = "") -> MetadataCard:
        system_name = record.parent_name or "Unknown"
        title = normalize_game_lookup_title(record.raw_name)
        lookup_key = self._metadata_lookup_key(record)
        return build_local_metadata_card(
            record,
            lookup_key=lookup_key,
            title=title,
            system_name=system_name,
            note=note,
        )

    def _fetch_metadata_card(self, record: FileRecord, force_refresh: bool = False) -> MetadataCard:
        system_name = record.parent_name or "Unknown"
        return fetch_metadata_card(
            record,
            lookup_key=self._metadata_lookup_key(record),
            title=normalize_game_lookup_title(record.raw_name),
            system_name=system_name,
            cache=self._session_state.metadata_cache,
            force_refresh=force_refresh,
        )

    def _cover_palette(self, record: FileRecord) -> Tuple[str, str]:
        palettes = [
            ("#1d4ed8", "#dbeafe"),
            ("#047857", "#d1fae5"),
            ("#b45309", "#ffedd5"),
            ("#7c3aed", "#ede9fe"),
            ("#be123c", "#ffe4e6"),
            ("#0f766e", "#ccfbf1"),
        ]
        seed = sum(ord(char) for char in f"{record.parent_name}:{record.raw_name}")
        return palettes[seed % len(palettes)]

    def _render_cover_panel(self, canvas, record: FileRecord, card: MetadataCard):
        ui_state = self._ui_state
        canvas.delete("all")
        width = max(canvas.winfo_width(), 240)
        height = max(canvas.winfo_height(), 320)
        border, fill = self._cover_palette(record)
        canvas.create_rectangle(0, 0, width, height, fill=fill, outline=border, width=3)
        canvas.create_rectangle(18, 18, width - 18, height - 18, outline=border, width=2)

        if card.image_path and Path(card.image_path).exists():
            try:
                image_bytes = Path(card.image_path).read_bytes()
                ui_state.metadata_image = tk.PhotoImage(data=b64encode(image_bytes).decode("ascii"))
                canvas.create_image(width // 2, height // 2, image=ui_state.metadata_image)
                return
            except Exception:
                ui_state.metadata_image = None

        title_text = card.title or normalize_game_lookup_title(record.raw_name)
        canvas.create_text(
            width // 2,
            56,
            text=record.parent_name or "SF3000",
            fill=border,
            font=("Segoe UI Semibold", 11),
            width=width - 48,
        )
        canvas.create_text(
            width // 2,
            height // 2 - 12,
            text=title_text,
            fill="#0f172a",
            font=("Segoe UI Semibold", 16),
            width=width - 54,
        )
        canvas.create_text(
            width // 2,
            height - 54,
            text=card.description or "Generated cover card",
            fill=border,
            font=("Segoe UI", 10),
            width=width - 52,
        )

    def _show_selected_metadata(self):
        ui_state = self._ui_state
        record = self._selected_metadata_record()
        if record is None:
            messagebox.showinfo("Metadata / Cover", "Select a file first.")
            return

        if ui_state.metadata_dialog and ui_state.metadata_dialog.winfo_exists():
            ui_state.metadata_dialog.destroy()

        dialog = tk.Toplevel(self)
        dialog.title("Metadata / Cover")
        dialog.geometry("860x520")
        dialog.minsize(760, 460)
        dialog.transient(self)
        ui_state.metadata_dialog = dialog

        ttk.Label(dialog, text="Metadata And Cover", style="Title.TLabel").pack(
            anchor="w", padx=14, pady=(14, 6)
        )

        outer = ttk.Frame(dialog, padding=(14, 0, 14, 14))
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer)
        left.pack(side="left", fill="y")
        right = ttk.Frame(outer)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))

        cover = tk.Canvas(left, width=260, height=360, highlightthickness=0, background="#f4f7fb")
        cover.pack(fill="y", expand=False)

        title_var = tk.StringVar(value=normalize_game_lookup_title(record.raw_name))
        source_var = tk.StringVar(value="Loading local details...")
        meta_var = tk.StringVar(value=f"File: {record.raw_name}\nSystem: {record.parent_name}\nSize: {format_size(record.size)}")

        ttk.Label(right, textvariable=title_var, style="Title.TLabel").pack(anchor="w")
        ttk.Label(right, textvariable=source_var, style="Hint.TLabel").pack(anchor="w", pady=(2, 6))
        ttk.Label(right, textvariable=meta_var, justify="left").pack(anchor="w", pady=(0, 8))

        text_box = tk.Text(
            right,
            wrap="word",
            relief="solid",
            borderwidth=1,
            background="#ffffff",
            font=("Segoe UI", 10),
            padx=10,
            pady=10,
            height=18,
        )
        text_box.pack(fill="both", expand=True)
        text_box.configure(state="disabled")

        state: Dict[str, object] = {"card": self._build_local_metadata_card(record)}

        def apply_card(card: MetadataCard):
            state["card"] = card
            title_var.set(card.title or normalize_game_lookup_title(record.raw_name))
            source_line = card.source_name
            if card.page_url:
                source_line += " | Open source for more"
            source_var.set(source_line)
            meta_var.set(
                f"File: {record.raw_name}\nSystem: {record.parent_name}\nSize: {format_size(record.size)}\nModified: {record.modified_text or 'Unknown'}"
            )
            text_box.configure(state="normal")
            text_box.delete("1.0", "end")
            text_box.insert("1.0", card.summary.strip() or "No metadata summary was available.")
            text_box.configure(state="disabled")
            self._render_cover_panel(cover, record, card)

        def load_card(force_refresh: bool = False):
            apply_card(self._build_local_metadata_card(record, "Looking up online metadata..."))
            self._run_background_task(
                lambda: self._fetch_metadata_card(record, force_refresh=force_refresh),
                on_success=apply_card,
            )

        button_bar = ttk.Frame(right)
        button_bar.pack(fill="x", pady=(10, 0))
        ttk.Button(button_bar, text="Refresh Lookup", command=lambda: load_card(True)).pack(side="left")

        def open_source():
            card = state.get("card")
            if not isinstance(card, MetadataCard):
                return
            target = card.page_url or card.image_url
            if target:
                webbrowser.open_new_tab(target)

        ttk.Button(button_bar, text="Open Source", command=open_source).pack(side="left", padx=(6, 0))
        ttk.Button(button_bar, text="Reveal File", command=lambda: self._reveal_path_in_explorer(record.path)).pack(side="left", padx=(6, 0))
        ttk.Button(button_bar, text="Close", command=dialog.destroy).pack(side="right")

        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.bind("<Destroy>", lambda _e: setattr(self._ui_state, "metadata_dialog", None), add="+")
        dialog.after(20, lambda: apply_card(self._build_local_metadata_card(record)))
        dialog.after(80, load_card)
