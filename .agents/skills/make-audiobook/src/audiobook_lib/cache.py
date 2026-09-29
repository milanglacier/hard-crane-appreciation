"""Per-segment audio cache.

Keyed by everything that can change the clip, so editing one paragraph
re-synthesizes exactly that paragraph and nothing else. The cache is also the
single normalization point: whatever a provider returns is passed through
ffmpeg once on the way in and stored as canonical FLAC (mono, 16-bit, the
configured sample rate), so assembly only ever sees identical formats.

Chapter-level settings (`format`, `loudnorm`, `bitrate_kbps`) are deliberately
*not* in the key — they change how a chapter is encoded, not how a clip
sounds, and they are covered by the chapter's `source_hash` instead.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from . import audio as A
from .tts.base import SynthResult


def cache_key(cfg: dict[str, Any], text: str) -> str:
    payload = {
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "voice": cfg.get("voice"),
        "speed": cfg.get("speed"),
        "instructions": cfg.get("instructions"),
        "sample_rate": cfg.get("sample_rate"),
        "text": text,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Cache:
    """`<key>.flac` (+ `<key>.words.json` when the provider returned word timings).

    Nothing here ever deletes a clip on its own: every entry was paid for, and
    a reverted paragraph should come back for free. `audiobook-cache gc` is the
    only way out, and it keys off the mtime that `load` refreshes on each hit.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path(self, key: str) -> Path:
        return self.root / f"{key}{A.CLIP_EXT}"

    def _words_path(self, key: str) -> Path:
        return self.root / f"{key}.words.json"

    def load(self, key: str) -> A.Clip | None:
        path = self.path(key)
        if not path.exists():
            return None
        try:
            frames, rate = A.clip_info(path)
        except Exception:
            return None
        self.touch(key)
        return A.Clip(path=path, frames=frames, sample_rate=rate, words=self._words(key))

    def touch(self, key: str) -> None:
        """Mark as used now. Done by hand: atime is unreliable under
        noatime/relatime mounts, and gc needs a real "last used"."""
        for path in (self.path(key), self._words_path(key)):
            try:
                os.utime(path)
            except FileNotFoundError:
                pass

    def _words(self, key: str) -> list[tuple[float, float, str]] | None:
        wpath = self._words_path(key)
        if not wpath.exists():
            return None
        try:
            return [tuple(w) for w in json.loads(wpath.read_text("utf-8"))]
        except Exception:
            return None

    def store(self, key: str, result: SynthResult, sample_rate: int) -> A.Clip:
        """Normalize through ffmpeg and land the FLAC atomically."""
        self.root.mkdir(parents=True, exist_ok=True)
        final = self.path(key)
        tmp = self.root / f".{key}.part{A.CLIP_EXT}"
        try:
            clip = A.normalize_clip(
                result.data, result.format, tmp,
                sample_rate=sample_rate, src_rate=result.sample_rate,
            )
            os.replace(tmp, final)
        finally:
            tmp.unlink(missing_ok=True)
        clip.path = final
        clip.words = result.words
        if result.words:
            self._words_path(key).write_text(
                json.dumps([list(w) for w in result.words], ensure_ascii=False),
                encoding="utf-8",
            )
        return clip

    def entries(self) -> dict[str, list[Path]]:
        """Every key on disk with all of its files (clip, legacy clip, words)."""
        out: dict[str, list[Path]] = {}
        if not self.root.is_dir():
            return out
        for path in self.root.iterdir():
            if path.name.startswith(".") or not path.is_file():
                continue
            key = path.name.split(".", 1)[0]
            out.setdefault(key, []).append(path)
        return out

    def leftovers(self) -> list[Path]:
        """Half-written `.<key>.part.*` files from an interrupted run."""
        if not self.root.is_dir():
            return []
        return [p for p in self.root.glob(".*.part.*") if p.is_file()]
