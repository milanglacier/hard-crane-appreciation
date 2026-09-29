"""Inspect and prune the per-paragraph TTS cache.

    audiobook-cache BOOK_DIR                        # stats
    audiobook-cache BOOK_DIR gc                     # what gc would remove
    audiobook-cache BOOK_DIR gc --yes               # remove it
    audiobook-cache BOOK_DIR gc --older-than 30     # days unused (default 60)

Every clip in the cache was paid for, and one the transcript no longer uses
is what makes reverting a paragraph free, so gc removes a clip only when both
hold:

  - neither the transcript nor the manifests in audio/ reference it; and
  - it has not been used for `--older-than` days (a cache hit refreshes it).
    This also covers clips the reference scan cannot match: ones rendered
    under a since-changed model or speed, or with a one-off CLI flag.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from audiobook_lib.book import load_book
from audiobook_lib.cache import Cache
from audiobook_lib.cli.clean import human
from audiobook_lib.housekeeping import referenced_keys

DAY = 86400.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book_dir")
    ap.add_argument("action", nargs="?", choices=("stats", "gc"), default="stats")
    ap.add_argument("--older-than", type=float, default=60, metavar="DAYS",
                    help="gc: only clips unused for this many days (default 60)")
    ap.add_argument("--yes", action="store_true", help="gc: delete (default: list only)")
    args = ap.parse_args()

    book = load_book(args.book_dir)
    cache = Cache(book.cache_dir)
    entries = cache.entries()
    size = {k: sum(p.stat().st_size for p in files) for k, files in entries.items()}
    last_used = {k: max(p.stat().st_mtime for p in files) for k, files in entries.items()}

    referenced = referenced_keys(book)
    unref = [k for k in entries if k not in referenced]

    print(f"{book.cache_dir}: {len(entries)} clips, {human(sum(size.values()))}")
    print(f"  referenced:   {len(entries) - len(unref)}")
    print(f"  unreferenced: {len(unref)}, {human(sum(size[k] for k in unref))}")
    if args.action == "stats":
        if unref:
            oldest = min(last_used[k] for k in unref)
            print(f"  oldest unreferenced clip last used {(time.time() - oldest) / DAY:.0f} days ago")
        return 0

    cutoff = time.time() - args.older_than * DAY
    doomed = sorted(k for k in unref if last_used[k] < cutoff)
    # half-written files from an interrupted run, once they are clearly abandoned
    leftovers = [p for p in cache.leftovers() if p.stat().st_mtime < time.time() - 3600]
    freed = sum(size[k] for k in doomed) + sum(p.stat().st_size for p in leftovers)
    print(
        f"gc: {len(doomed)} unreferenced clip(s) unused for {args.older_than:g}+ days"
        + (f", {len(leftovers)} partial file(s)" if leftovers else "")
        + f" — {human(freed)}"
    )
    if not doomed and not leftovers:
        return 0
    if not args.yes:
        print("nothing deleted; pass --yes to remove them")
        return 0
    paths: list[Path] = [p for k in doomed for p in entries[k]] + leftovers
    for path in paths:
        path.unlink(missing_ok=True)
    print(f"removed {len(paths)} file(s), freed {human(freed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
