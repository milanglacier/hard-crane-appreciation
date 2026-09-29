"""Length, pace and lint report for a book's transcripts.

    audiobook-stats BOOK_DIR [--chapter 03] [--json]

No network, no audio dependencies: this is the loop you run while still writing.
Always exits 0 — the warnings are advice, not failures.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

from audiobook_lib.book import DEFAULT_PAUSE_MS, effective_tts, load_book, pause_for
from audiobook_lib.segmenter import (
    Segment,
    count_cjk,
    count_latin_words,
    estimate_seconds,
)

MAX_CJK_PER_PARA = 200
MAX_WORDS_PER_PARA = 120
SHORT_CHAPTER_MIN = 3.0
LONG_CHAPTER_MIN = 25.0


def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s: str, n: int) -> str:
    return s + " " * max(0, n - _width(s))


def _trunc(s: str, n: int = 40) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def lint(segments: list[Segment], has_h1: bool, minutes: float) -> list[tuple[int, str, str]]:
    """(segment index, message, excerpt). Index -1 = whole chapter."""
    out: list[tuple[int, str, str]] = []
    if not has_h1:
        out.append((-1, "chapter has no H1 heading", ""))
    if minutes < SHORT_CHAPTER_MIN:
        out.append((-1, f"chapter is only {minutes:.1f} min (info)", ""))
    elif minutes > LONG_CHAPTER_MIN:
        out.append((-1, f"chapter is {minutes:.1f} min, over {LONG_CHAPTER_MIN:.0f} (info)", ""))

    for seg in segments:
        excerpt = _trunc(seg.spoken or seg.html)
        for w in seg.warnings:
            out.append((seg.i, w, excerpt))
        if seg.kind in ("para", "item") and seg.spoken:
            cjk, words = count_cjk(seg.spoken), count_latin_words(seg.spoken)
            if cjk > MAX_CJK_PER_PARA:
                out.append((seg.i, f"paragraph is {cjk} 汉字 (over {MAX_CJK_PER_PARA})", excerpt))
            elif words > MAX_WORDS_PER_PARA:
                out.append((seg.i, f"paragraph is {words} words (over {MAX_WORDS_PER_PARA})", excerpt))
        if seg.kind == "display" and seg.html.startswith('<div class="math"'):
            near = [s for s in segments[max(0, seg.i - 2) : seg.i] if s.spoken]
            if not near:
                out.append((seg.i, "$$ block has no spoken segment within 2 segments before it", excerpt))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", action="append", help="chapter id or prefix; repeatable")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    book = load_book(args.book_dir)
    chapters = book.find_chapters(args.chapter)
    if not chapters:
        print(f"no chapters found in {book.chapters_dir}")
        return 0

    rows = []
    for ch in chapters:
        cfg = effective_tts(book, ch)
        pauses = cfg.get("pause_ms", DEFAULT_PAUSE_MS)
        segs = ch.segments(book.pronunciations)
        spoken = [s for s in segs if s.spoken]
        cjk = sum(count_cjk(s.spoken or "") for s in spoken)
        words = sum(count_latin_words(s.spoken or "") for s in spoken)
        seconds = sum(estimate_seconds(s.spoken or "", pause_for(s.kind, pauses)) for s in segs)
        minutes = seconds / 60.0
        has_h1 = any(s.kind == "heading" and s.level == 1 for s in segs)
        rows.append(
            {
                "id": ch.id,
                "title": ch.title,
                "segments": len(segs),
                "spoken_segments": len(spoken),
                "cjk": cjk,
                "words": words,
                "est_minutes": round(minutes, 1),
                "warnings": [
                    {"segment": i, "message": m, "excerpt": e}
                    for i, m, e in lint(segs, has_h1, minutes)
                ],
            }
        )

    if args.as_json:
        print(json.dumps({"book": book.title, "chapters": rows}, ensure_ascii=False, indent=2))
        return 0

    headers = ("chapter", "title", "seg", "汉字", "words", "est min", "warn")
    widths = [
        max(_width(headers[0]), *(_width(r["id"]) for r in rows)),
        max(_width(headers[1]), *(_width(_trunc(r["title"], 32)) for r in rows)),
        7, 7, 7, 8, 5,
    ]
    print("  ".join(_pad(h, w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join([
            _pad(r["id"], widths[0]),
            _pad(_trunc(r["title"], 32), widths[1]),
            _pad(str(r["segments"]), widths[2]),
            _pad(str(r["cjk"]), widths[3]),
            _pad(str(r["words"]), widths[4]),
            _pad(f"{r['est_minutes']:.1f}", widths[5]),
            _pad(str(len(r["warnings"])) if r["warnings"] else "", widths[6]),
        ]))
    total_min = sum(r["est_minutes"] for r in rows)
    print("  ".join("-" * w for w in widths))
    print("  ".join([
        _pad(f"{len(rows)} ch", widths[0]),
        _pad("total", widths[1]),
        _pad(str(sum(r["segments"] for r in rows)), widths[2]),
        _pad(str(sum(r["cjk"] for r in rows)), widths[3]),
        _pad(str(sum(r["words"] for r in rows)), widths[4]),
        _pad(f"{total_min:.1f}", widths[5]),
        _pad(str(sum(len(r["warnings"]) for r in rows)), widths[6]),
    ]))
    print(f"\ntotal ≈ {total_min:.1f} min ({total_min / 60:.1f} h) at the default pace")

    flagged = [r for r in rows if r["warnings"]]
    if not flagged:
        print("\nno warnings")
        return 0
    print("\nwarnings")
    for r in flagged:
        print(f"\n  {r['id']}  {r['title']}")
        for w in r["warnings"]:
            where = "chapter" if w["segment"] < 0 else f"seg {w['segment']:>3}"
            excerpt = f"   « {w['excerpt']} »" if w["excerpt"] else ""
            print(f"    {where}  {w['message']}{excerpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
