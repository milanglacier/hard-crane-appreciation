"""Remove files in audio/ that no chapter uses any more.

    audiobook-clean BOOK_DIR             # delete them
    audiobook-clean BOOK_DIR --dry-run   # only list them

An orphan is a file in audio/ that no current chapter uses: the old audio and
manifest of a renamed or deleted chapter, the old codec after a `format`
switch, a preview. A chapter whose transcript changed is *not* an orphan — its
audio is overwritten by the next synth.

Orphans are removed without asking: a committed one comes back from git, and
any chapter re-renders from `.cache/tts/` without a paid request as long as
its transcript exists.
"""

from __future__ import annotations

import argparse

from audiobook_lib.book import load_book
from audiobook_lib.housekeeping import orphan_audio


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book_dir")
    ap.add_argument("--dry-run", action="store_true", help="list, delete nothing")
    args = ap.parse_args()

    book = load_book(args.book_dir)
    orphans = orphan_audio(book)
    if not orphans:
        print(f"{book.audio_dir}: nothing to clean")
        return 0

    verb = "would remove" if args.dry_run else "removing"
    print(f"{verb} {len(orphans)} orphaned file(s) in {book.audio_dir}:")
    width = max(len(p.name) for p in orphans)
    for path in orphans:
        print(f"  {path.name.ljust(width)}  {human(path.stat().st_size):>9}")
        if not args.dry_run:
            path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
