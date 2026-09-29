"""Synthesize chapter audio and the segment-timing manifest.

    audiobook-synth BOOK_DIR                       # everything that changed
    audiobook-synth BOOK_DIR --chapter 03          # prefix or id, repeatable
    audiobook-synth BOOK_DIR --force               # re-render even if unchanged
    audiobook-synth BOOK_DIR --dry-run             # counts + cost, no network
    audiobook-synth BOOK_DIR --format opus         # mp3 (default) | opus | aac
    audiobook-synth BOOK_DIR --no-loudnorm         # skip loudness normalization
    audiobook-synth BOOK_DIR --verbose             # print every ffmpeg command
    audiobook-synth BOOK_DIR --preview [--segments 3]
    audiobook-synth BOOK_DIR --preview-text "任意一段文字"
    audiobook-synth BOOK_DIR --list-voices

Needs ffmpeg and ffprobe on PATH (or `$FFMPEG` / `$FFPROBE`): every clip is
normalized to canonical FLAC as it enters the cache and each chapter is one
concat-demuxer call. `nix develop path:<skill-dir>` provides both.

Two levels of skipping: a chapter whose source_hash is unchanged is not touched
at all, and inside a chapter every segment is looked up in <book>/.cache/tts
first — so editing one paragraph costs one paragraph.

Nothing is ever deleted here: a renamed chapter leaves its old audio behind
(`audiobook-clean` reviews it) and replaced clips stay in the cache
(`audiobook-cache gc` prunes it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audiobook_lib import audio as A
from audiobook_lib.book import Book, Chapter, effective_tts, load_book, pause_for
from audiobook_lib.cache import Cache, cache_key
from audiobook_lib.housekeeping import orphan_hint, plan_chunks
from audiobook_lib.segmenter import Segment, chunk_text, estimate_seconds
from audiobook_lib.tts import KNOWN, TTSError, get_provider, price_per_1m
from audiobook_lib.tts.base import Provider, SynthResult

CHUNK_GAP_MS = 120  # a breath between the pieces of a chunked segment


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_hash(cfg: dict[str, Any], spoken: list[str]) -> str:
    """Everything that can change the rendered chapter, `format` and `loudnorm`
    included — those are not in the clip cache key, so this is what forces a
    re-render when the encoder settings change."""
    material = {k: v for k, v in sorted(cfg.items()) if k != "concurrency"}
    blob = json.dumps({"cfg": material, "spoken": spoken}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------


def synth_texts(
    texts: list[str], provider: Provider, cfg: dict[str, Any], cache: Cache, workers: int
) -> tuple[dict[str, A.Clip], int, int]:
    """Synthesize the distinct texts, cache-first. Returns (by_text, n_cached, chars_sent).

    Every result is normalized to canonical FLAC by `Cache.store`, so the
    returned clips all share the configured rate, channel count and format.
    """
    out: dict[str, A.Clip] = {}
    todo: list[str] = []
    n_cached = 0
    sr = int(cfg["sample_rate"])
    for text in dict.fromkeys(texts):
        hit = cache.load(cache_key(cfg, text))
        if hit is not None:
            out[text] = hit
            n_cached += 1
        else:
            todo.append(text)

    def work(text: str) -> tuple[str, SynthResult]:
        return text, provider.synthesize(text, cfg)

    if todo:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for text, result in pool.map(work, todo):
                out[text] = cache.store(cache_key(cfg, text), result, sr)
    return out, n_cached, sum(len(t) for t in todo)


def assemble(
    segments: list[Segment],
    chunks: list[list[str]],
    clips: dict[str, A.Clip],
    cfg: dict[str, Any],
    silence_dir: Path,
) -> tuple[list[Path], list[dict[str, Any]], int]:
    """Lay the clips out on a timeline with the configured silences.

    Returns the WAVs to concatenate, the manifest entries, and the total frame
    count. The cursor is counted in frames, never in floats, so the times in
    the manifest are exactly the sample offsets ffmpeg will produce.
    """
    sr = int(cfg["sample_rate"])
    pauses = cfg.get("pause_ms", {})
    parts: list[Path] = []
    entries: list[dict[str, Any]] = []
    frames = 0
    last_spoken_end = 0.0

    def at(f: int) -> float:
        return round(f / float(sr), 3)

    def pause(ms: int) -> None:
        nonlocal frames
        if ms <= 0:
            return
        sil = A.silence_clip(ms, sr, silence_dir)
        parts.append(sil.path)
        frames += sil.frames

    for seg, pieces in zip(segments, chunks):
        entry: dict[str, Any] = {"i": seg.i, "kind": seg.kind, "html": seg.html}
        if seg.level:
            entry["level"] = seg.level

        if not pieces:
            if seg.kind == "rule":
                entry["start"] = at(frames)
                pause(pause_for("rule", pauses))
                entry["end"] = at(frames)
            else:  # display: shares the end of the preceding spoken segment
                entry["start"] = entry["end"] = round(last_spoken_end, 3)
            entries.append(entry)
            continue

        start = at(frames)
        words: list[list[Any]] = []
        for n, piece in enumerate(pieces):
            clip = clips[piece]
            if n:
                pause(CHUNK_GAP_MS)
            if clip.words:
                cursor = frames / float(sr)
                words.extend([round(cursor + s, 3), round(cursor + e, 3), t] for s, e, t in clip.words)
            parts.append(clip.path)
            frames += clip.frames

        entry["start"] = start
        entry["end"] = at(frames)
        entry["spoken"] = seg.spoken
        if words:
            entry["words"] = words
        entries.append(entry)
        last_spoken_end = frames / float(sr)

        pause(pause_for(seg.kind, pauses))

    if not parts:  # a chapter with nothing spoken: ffmpeg still needs an input
        sil = A.silence_clip(100, sr, silence_dir)
        parts.append(sil.path)
        frames += sil.frames

    return parts, entries, frames


def render_chapter(
    book: Book, ch: Chapter, cfg: dict[str, Any], provider: Provider, cache: Cache, force: bool
) -> str:
    segments = ch.segments(book.pronunciations)
    spoken = [s.spoken or "" for s in segments if s.spoken]
    shash = source_hash(cfg, spoken)
    sr = int(cfg["sample_rate"])
    ext = A.format_spec(cfg["format"])["ext"]
    out_path = book.audio_dir / f"{ch.id}.{ext}"
    manifest_path = book.audio_dir / f"{ch.id}.json"

    if not force and out_path.exists() and manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text("utf-8"))
        except Exception:
            old = {}
        if old.get("source_hash") == shash:
            print(f"  {ch.id}: unchanged, skipped")
            return ""

    t0 = time.time()
    limit = provider.chunk_limit(cfg)
    chunks = plan_chunks(segments, limit)
    texts = [piece for pieces in chunks for piece in pieces]
    clips, n_cached, chars_sent = synth_texts(
        texts, provider, cfg, cache, int(cfg["concurrency"])
    )
    parts, entries, frames = assemble(segments, chunks, clips, cfg, book.silence_dir)
    duration = frames / float(sr)

    list_file = A.write_concat_list(book.concat_dir / f"{ch.id}.txt", parts)
    A.encode_concat(
        list_file, out_path,
        sample_rate=sr, fmt=cfg["format"],
        bitrate_kbps=int(cfg["bitrate_kbps"]), loudnorm=bool(cfg["loudnorm"]),
    )
    probed = A.probe_duration(out_path)
    tolerance = 0.05 + float(A.format_spec(cfg["format"])["slack"])
    if probed is not None and abs(probed - duration) > tolerance:
        print(
            f"  warning: {ch.id}: manifest says {duration:.3f}s but ffprobe reads "
            f"{probed:.3f}s ({(probed - duration) * 1000:+.0f} ms)"
        )

    manifest = {
        "id": ch.id,
        "title": ch.title,
        "audio": out_path.name,
        "duration": round(duration, 3),
        "language": book.language,
        "provider": cfg.get("provider"),
        "voice": cfg.get("voice"),
        "source_hash": shash,
        "generated_at": now_iso(),
        "segments": entries,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    n_requests = len(dict.fromkeys(texts))
    print(
        f"  {ch.id}: {len(segments)} segments, {n_cached}/{n_requests} cached, "
        f"{n_requests - n_cached} synthesized, {duration:6.1f}s audio, "
        f"{chars_sent} chars sent, {time.time() - t0:.1f}s elapsed"
    )
    return f"{chars_sent}"


# --------------------------------------------------------------------------


def do_dry_run(book: Book, chapters: list[Chapter], cli: dict[str, Any]) -> int:
    total_chars = total_min = 0.0
    total_uncached = 0
    print(f"{book.title}  —  dry run, no network\n")
    for ch in chapters:
        cfg = effective_tts(book, ch, cli)
        provider = get_provider(str(cfg["provider"]))
        cache = Cache(book.cache_dir)
        segments = ch.segments(book.pronunciations)
        chunks = plan_chunks(segments, provider.chunk_limit(cfg))
        texts = [p for pieces in chunks for p in pieces]
        chars = sum(len(t) for t in texts)
        cached = sum(len(t) for t in dict.fromkeys(texts) if cache.path(cache_key(cfg, t)).exists())
        seconds = sum(
            estimate_seconds(s.spoken or "", pause_for(s.kind, cfg.get("pause_ms", {})))
            for s in segments
        )
        total_chars += chars
        total_uncached += chars - cached
        total_min += seconds / 60.0
        print(
            f"  {ch.id}: {len(segments)} segments, {chars} chars "
            f"({cached} cached / {chars - cached} to synthesize), "
            f"≈{seconds / 60:.1f} min"
        )
    cfg = effective_tts(book, chapters[0] if chapters else None, cli)
    provider = get_provider(str(cfg["provider"]))
    price = price_per_1m(provider, cfg)
    print(f"\n  totals: {int(total_chars)} chars, ≈{total_min:.1f} min of audio")
    print(
        f"  output: {cfg['format']} @ {cfg['bitrate_kbps']} kbps, {cfg['sample_rate']} Hz mono, "
        f"loudnorm {'on' if cfg['loudnorm'] else 'off'}"
    )
    if price is None:
        print(f"  provider {provider.name}: no price on record")
    else:
        print(
            f"  provider {provider.name} ≈ ${price:.2f}/1M chars  →  "
            f"${total_uncached * price / 1e6:.2f} for the {total_uncached} uncached chars "
            f"(${total_chars * price / 1e6:.2f} if nothing were cached) — approximate"
        )
    return 0


def do_preview(book: Book, chapters: list[Chapter], cli: dict[str, Any], n: int, text: str | None) -> int:
    ch = chapters[0] if chapters else None
    cfg = effective_tts(book, ch, cli)
    provider = get_provider(str(cfg["provider"]))
    cache = Cache(book.cache_dir)
    if text:
        pieces = chunk_text(text, provider.chunk_limit(cfg))
        kinds = ["para"] * len(pieces)
    else:
        if ch is None:
            raise SystemExit("no chapters to preview; pass --preview-text instead")
        segs = [s for s in ch.segments(book.pronunciations) if s.spoken][:n]
        pieces = [s.spoken or "" for s in segs]
        kinds = [s.kind for s in segs]
    if not pieces:
        raise SystemExit("nothing to preview")

    clips, n_cached, chars = synth_texts(pieces, provider, cfg, cache, int(cfg["concurrency"]))
    sr = int(cfg["sample_rate"])
    parts: list[Path] = []
    frames = 0
    for piece, kind in zip(pieces, kinds):
        clip = clips[piece]
        parts.append(clip.path)
        frames += clip.frames
        gap = pause_for(kind, cfg.get("pause_ms", {}))
        if gap > 0:
            sil = A.silence_clip(gap, sr, book.silence_dir)
            parts.append(sil.path)
            frames += sil.frames

    ext = A.format_spec(cfg["format"])["ext"]
    out = book.audio_dir / f"preview.{ext}"
    list_file = A.write_concat_list(book.concat_dir / "preview.txt", parts)
    A.encode_concat(
        list_file, out,
        sample_rate=sr, fmt=cfg["format"],
        bitrate_kbps=int(cfg["bitrate_kbps"]), loudnorm=bool(cfg["loudnorm"]),
    )
    print(
        f"preview: {len(pieces)} segments, {n_cached} cached, {chars} chars sent, "
        f"{frames / float(sr):.1f}s → {out}"
    )
    print(f"  provider={cfg['provider']} voice={cfg.get('voice')} model={cfg.get('model')} speed={cfg['speed']}")
    return 0


def do_list_voices(book: Book, cli: dict[str, Any]) -> int:
    cfg = effective_tts(book, None, cli)
    provider = get_provider(str(cfg["provider"]))
    voices = provider.list_voices(cfg)
    if not voices:
        print(f"{provider.name}: no voice list available")
        return 0
    print(f"{provider.name} voices ({len(voices)}):")
    width = max(len(v[0]) for v in voices)
    for vid, desc in voices:
        print(f"  {vid.ljust(width)}  {desc}")
    return 0


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", action="append", help="chapter id or prefix; repeatable")
    ap.add_argument("--force", action="store_true", help="re-render even if the source is unchanged")
    ap.add_argument("--dry-run", action="store_true", help="counts and cost, no network")
    ap.add_argument("--preview", action="store_true", help="first N spoken segments -> audio/preview.<ext>")
    ap.add_argument("--preview-text", help="synthesize this text -> audio/preview.<ext>")
    ap.add_argument("--segments", type=int, default=3, help="segments for --preview (default 3)")
    ap.add_argument("--list-voices", action="store_true")
    ap.add_argument("--provider", choices=KNOWN)
    ap.add_argument("--model")
    ap.add_argument("--voice")
    ap.add_argument("--speed", type=float)
    ap.add_argument("--instructions")
    ap.add_argument("--concurrency", type=int)
    ap.add_argument(
        "--format", choices=sorted(A.FORMATS),
        help="output codec (default mp3; opus is half the size at the same quality)",
    )
    ap.add_argument("--bitrate-kbps", type=int, help="override the per-format default bitrate")
    ap.add_argument(
        "--loudnorm", action=argparse.BooleanOptionalAction, default=None,
        help="EBU R128 loudness normalization to -16 LUFS (default: on)",
    )
    ap.add_argument("--verbose", action="store_true", help="print every ffmpeg command")
    args = ap.parse_args()

    A.set_verbose(args.verbose)
    cli = {
        k: v
        for k, v in {
            "provider": args.provider,
            "model": args.model,
            "voice": args.voice,
            "speed": args.speed,
            "instructions": args.instructions,
            "concurrency": args.concurrency,
            "format": args.format,
            "bitrate_kbps": args.bitrate_kbps,
            "loudnorm": args.loudnorm,
        }.items()
        if v is not None
    }

    book = load_book(args.book_dir)
    if args.list_voices:
        return do_list_voices(book, cli)

    chapters = book.find_chapters(args.chapter)
    if not args.dry_run:
        try:  # fail before a single character is sent to a paid API
            A.require_tools()
        except A.AudioError as exc:
            print(exc, file=sys.stderr)
            return 1
    if args.preview or args.preview_text:
        return do_preview(book, chapters, cli, args.segments, args.preview_text)
    if not chapters:
        print(f"no chapters found in {book.chapters_dir}")
        return 0
    if args.dry_run:
        return do_dry_run(book, chapters, cli)

    print(f"{book.title}  —  {len(chapters)} chapter(s)")
    t0 = time.time()
    total_chars = 0
    for ch in chapters:
        cfg = effective_tts(book, ch, cli)
        provider = get_provider(str(cfg["provider"]))
        cache = Cache(book.cache_dir)
        try:
            sent = render_chapter(book, ch, cfg, provider, cache, args.force)
        except (TTSError, A.AudioError) as exc:
            print(f"  {ch.id}: FAILED: {exc}")
            return 1
        total_chars += int(sent or 0)
    print(f"done in {time.time() - t0:.1f}s; {total_chars} characters sent to the provider")
    if hint := orphan_hint(book):
        print(hint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
