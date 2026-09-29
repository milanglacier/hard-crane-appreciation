"""book.yaml + chapters/*.md loading, and the three-level TTS config merge.

Config precedence: defaults < book.yaml `tts:` < chapter frontmatter < CLI flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import audio as A
from .segmenter import Segment, segment_markdown, strip_frontmatter

DEFAULT_PAUSE_MS: dict[str, int] = {
    "paragraph": 550,
    "heading": 900,
    "line": 250,
    "rule": 1500,
}

DEFAULT_TTS: dict[str, Any] = {
    "provider": "azure",
    "speed": 1.0,
    "format": "mp3",
    "loudnorm": True,
    "concurrency": 4,
    "sample_rate": 24000,
    "pause_ms": dict(DEFAULT_PAUSE_MS),
}

# keys the CLI may pass as None meaning "not overridden"
_TTS_SCALARS = (
    "provider", "model", "voice", "speed", "instructions", "style", "lang",
    "max_chars", "sample_rate", "format", "loudnorm", "bitrate_kbps", "concurrency",
)


@dataclass
class Chapter:
    id: str
    path: Path
    frontmatter: dict[str, Any]
    title: str
    body: str

    def segments(self, pronunciations: dict[str, str] | None = None) -> list[Segment]:
        return segment_markdown(self.body, pronunciations)


@dataclass
class Book:
    dir: Path
    title: str
    language: str
    subtitle: str = ""
    author: str = ""
    description: str = ""
    depth: str = ""
    tts: dict[str, Any] = field(default_factory=dict)
    pronunciations: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def chapters_dir(self) -> Path:
        return self.dir / "chapters"

    @property
    def audio_dir(self) -> Path:
        return self.dir / "audio"

    @property
    def cache_dir(self) -> Path:
        return self.dir / ".cache" / "tts"

    @property
    def silence_dir(self) -> Path:
        """One WAV per distinct pause length, shared by every chapter."""
        return self.dir / ".cache" / "silence"

    @property
    def concat_dir(self) -> Path:
        """The concat-demuxer list handed to ffmpeg, one per chapter."""
        return self.dir / ".cache" / "concat"

    @property
    def chapters(self) -> list[Chapter]:
        out: list[Chapter] = []
        for path in sorted(self.chapters_dir.glob("*.md")):
            out.append(load_chapter(path))
        return out

    def find_chapters(self, selectors: list[str] | None) -> list[Chapter]:
        """Match by exact id or by prefix (`--chapter 03`)."""
        chapters = self.chapters
        if not selectors:
            return chapters
        picked: list[Chapter] = []
        for sel in selectors:
            hits = [c for c in chapters if c.id == sel] or [
                c for c in chapters if c.id.startswith(sel)
            ]
            if not hits:
                known = ", ".join(c.id for c in chapters) or "(none)"
                raise SystemExit(f"no chapter matches {sel!r}; available: {known}")
            for c in hits:
                if c not in picked:
                    picked.append(c)
        return picked


def _first_h1(body: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return ""


def load_chapter(path: Path) -> Chapter:
    text = path.read_text(encoding="utf-8")
    fm_text, body = strip_frontmatter(text)
    fm = yaml.safe_load(fm_text) if fm_text.strip() else {}
    if not isinstance(fm, dict):
        fm = {}
    cid = path.stem
    title = str(fm.get("title") or _first_h1(body) or cid)
    return Chapter(id=cid, path=path, frontmatter=fm, title=title, body=body)


def load_book(book_dir: str | Path) -> Book:
    book_dir = Path(book_dir).expanduser().resolve()
    yaml_path = book_dir / "book.yaml"
    if not yaml_path.exists():
        raise SystemExit(f"{yaml_path} not found — is {book_dir} a book directory?")
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{yaml_path}: expected a mapping at the top level")
    missing = [k for k in ("title", "language") if not data.get(k)]
    if missing:
        raise SystemExit(f"{yaml_path}: missing required key(s): {', '.join(missing)}")
    tts = data.get("tts") or {}
    if not isinstance(tts, dict):
        raise SystemExit(f"{yaml_path}: `tts` must be a mapping")
    pron = data.get("pronunciations") or {}
    if not isinstance(pron, dict):
        raise SystemExit(f"{yaml_path}: `pronunciations` must be a mapping")
    return Book(
        dir=book_dir,
        title=str(data["title"]),
        language=str(data["language"]),
        subtitle=str(data.get("subtitle") or ""),
        author=str(data.get("author") or ""),
        description=str(data.get("description") or ""),
        depth=str(data.get("depth") or ""),
        tts=tts,
        pronunciations={str(k): str(v) for k, v in pron.items()},
        raw=data,
    )


_CHAPTER_TTS_KEYS = set(_TTS_SCALARS) | {"pause_ms", "extra"}


def effective_tts(
    book: Book, chapter: Chapter | None = None, cli: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Merge defaults < book.yaml < chapter frontmatter < CLI. `pause_ms` merges per key."""
    cfg: dict[str, Any] = dict(DEFAULT_TTS)
    cfg["pause_ms"] = dict(DEFAULT_PAUSE_MS)
    cfg["language"] = book.language

    def apply(src: dict[str, Any]) -> None:
        for k, v in src.items():
            if v is None:
                continue
            if k == "pause_ms" and isinstance(v, dict):
                cfg["pause_ms"].update({str(kk): int(vv) for kk, vv in v.items()})
            elif k == "extra" and isinstance(v, dict):
                cfg.setdefault("extra", {}).update(v)
            else:
                cfg[k] = v

    apply(book.tts)
    if chapter:
        # a chapter frontmatter may carry tts keys either flat or under `tts:`
        apply({k: v for k, v in chapter.frontmatter.items() if k in _CHAPTER_TTS_KEYS})
        nested = chapter.frontmatter.get("tts")
        if isinstance(nested, dict):
            apply(nested)
    if cli:
        apply(cli)

    cfg["speed"] = float(cfg.get("speed", 1.0))
    cfg["sample_rate"] = int(cfg.get("sample_rate", 24000))
    cfg["format"] = str(cfg.get("format") or "mp3").lower()
    if cfg["format"] not in A.FORMATS:
        raise SystemExit(
            f"unknown tts format {cfg['format']!r}; "
            f"known formats: {', '.join(sorted(A.FORMATS))}"
        )
    cfg["loudnorm"] = bool(cfg.get("loudnorm", True))
    # the sensible bitrate depends on the codec (opus says the same at half of it)
    cfg["bitrate_kbps"] = int(cfg.get("bitrate_kbps") or A.FORMATS[cfg["format"]]["bitrate"])
    cfg["concurrency"] = max(1, int(cfg.get("concurrency", 4)))
    return cfg


def pause_for(kind: str, pause_ms: dict[str, int]) -> int:
    """Silence inserted *after* a segment of this kind (transcript-format.md)."""
    return {
        "heading": pause_ms.get("heading", DEFAULT_PAUSE_MS["heading"]),
        "para": pause_ms.get("paragraph", DEFAULT_PAUSE_MS["paragraph"]),
        "item": pause_ms.get("paragraph", DEFAULT_PAUSE_MS["paragraph"]),
        "line": pause_ms.get("line", DEFAULT_PAUSE_MS["line"]),
        "rule": pause_ms.get("rule", DEFAULT_PAUSE_MS["rule"]),
        "display": 0,
    }.get(kind, 0)
