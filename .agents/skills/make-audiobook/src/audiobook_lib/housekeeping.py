"""What is still needed and what is not.

The bookkeeping behind `audiobook-clean` (files in `audio/` that belong to no
chapter), `audiobook-cache gc` (clips the current version does not use), and
the hints `audiobook-synth` / `audiobook-build` print. Nothing here deletes
anything; the commands do.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .book import Book, Chapter, effective_tts, voice_tts
from .cache import cache_key
from .segmenter import Segment, chunk_text
from .tts import get_provider


@dataclass
class Piece:
    """One request's worth of spoken text, with the settings of the voice that reads it."""

    key: str
    text: str
    cfg: dict[str, Any]


def plan_pieces(segments: list[Segment], cfg: dict[str, Any]) -> list[list[Piece]]:
    """Per segment, the request-sized pieces of its spoken text."""
    out: list[list[Piece]] = []
    for seg in segments:
        if not seg.spoken:
            out.append([])
            continue
        scfg = voice_tts(cfg, seg.alt_voice)
        limit = get_provider(str(scfg["provider"])).chunk_limit(scfg)
        out.append([Piece(cache_key(scfg, t), t, scfg) for t in chunk_text(seg.spoken, limit)])
    return out


def load_manifest(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# -- audio/ -----------------------------------------------------------------


def expected_audio(book: Book) -> set[str]:
    """Names in `audio/` a current chapter still uses: its manifest, and the
    audio file that manifest names (whatever the format it was rendered in)."""
    names: set[str] = set()
    for ch in book.chapters:
        names.add(f"{ch.id}.json")
        manifest = load_manifest(book.audio_dir / f"{ch.id}.json")
        if manifest and manifest.get("audio"):
            names.add(Path(str(manifest["audio"])).name)
    return names


def orphan_audio(book: Book) -> list[Path]:
    """Files in `audio/` no current chapter uses: renamed or deleted chapters,
    the old codec after a format switch, previews."""
    if not book.audio_dir.is_dir():
        return []
    keep = expected_audio(book)
    return sorted(
        p for p in book.audio_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.name not in keep
    )


def orphan_hint(book: Book) -> str | None:
    orphans = orphan_audio(book)
    if not orphans:
        return None
    shown = ", ".join(p.name for p in orphans[:4]) + (", …" if len(orphans) > 4 else "")
    return (
        f"note: {len(orphans)} file(s) in audio/ belong to no chapter ({shown}); "
        f"remove with `audiobook-clean {book.dir}`"
    )


def stale_chapters(book: Book) -> list[str]:
    """Chapters whose manifest was rendered from different spoken text, or with
    different voice markers, than the transcript now has — edited but not
    re-synthesized."""
    stale: list[str] = []
    for ch in book.chapters:
        manifest = load_manifest(book.audio_dir / f"{ch.id}.json")
        if manifest is None:
            continue
        now = [(s.spoken, s.alt_voice) for s in ch.segments(book.pronunciations) if s.spoken]
        then = [
            (e.get("spoken"), e.get("alt_voice"))
            for e in manifest.get("segments", []) if e.get("spoken")
        ]
        if now != then:
            stale.append(ch.id)
    return stale


# -- the TTS cache ----------------------------------------------------------


def _keys(cfg: dict[str, Any], segments: list[Segment]) -> set[str]:
    return {p.key for pieces in plan_pieces(segments, cfg) for p in pieces}


def chapter_keys(book: Book, ch: Chapter) -> set[str]:
    """The clips the next `audiobook-synth` of this chapter would use."""
    return _keys(effective_tts(book, ch, {}), ch.segments(book.pronunciations))


def manifest_keys(book: Book, manifest: dict[str, Any], chapters: dict[str, Chapter]) -> set[str]:
    """The clips a rendered chapter was assembled from, recomputed from its
    spoken text. The manifest records provider and voice; the rest of the
    config (model, speed, alt voice settings, …) is taken as it is now, so a
    clip rendered under a since-changed setting or a one-off CLI flag is not
    matched — the gc age threshold is what protects those."""
    ch = chapters.get(str(manifest.get("id")))
    cli = {k: manifest[k] for k in ("provider", "voice") if manifest.get(k)}
    segments = [
        Segment(n, e.get("kind", "para"), "", str(e["spoken"]), alt_voice=e.get("alt_voice"))
        for n, e in enumerate(manifest.get("segments", [])) if e.get("spoken")
    ]
    try:
        return _keys(effective_tts(book, ch, cli), segments)
    except SystemExit:  # a provider or alt voice this version no longer knows
        return set()


def referenced_keys(book: Book) -> set[str]:
    """Every cache key the current version still points at: what the
    transcript would synthesize now, and what the manifests in `audio/` were
    assembled from."""
    chapters = {ch.id: ch for ch in book.chapters}
    keys: set[str] = set()
    for ch in chapters.values():
        keys |= chapter_keys(book, ch)
    if book.audio_dir.is_dir():
        for path in sorted(book.audio_dir.glob("*.json")):
            if (manifest := load_manifest(path)) is not None:
                keys |= manifest_keys(book, manifest, chapters)
    return keys
