"""Assemble the static web player.

    audiobook-build BOOK_DIR [--out DIR] [--site-assets DIR]

Works before a single second of audio exists: a chapter with no manifest is
written in transcript-only mode (null start/end, null audio) so the whole book
can be reviewed in the player before any money is spent.

The output directory is rebuilt from scratch every time — staged next to it,
then swapped in — so a renamed chapter or a format switch leaves nothing stale
behind. Audio is hardlinked, so a rebuild costs next to nothing. A directory
that does not look like an earlier build is never replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
from datetime import datetime, timezone
from importlib.resources import files as resource_files
from pathlib import Path
from typing import Any

from audiobook_lib import audio as A
from audiobook_lib.book import Book, Chapter, load_book
from audiobook_lib.housekeeping import orphan_hint, stale_chapters

# The repo checkout, for an editable install or a `uv run --project` run.
SKILL_DIR = Path(__file__).resolve().parents[3]
REPO_ASSETS = SKILL_DIR / "assets" / "site"


def default_assets() -> Path:
    """Player assets: inside the wheel first, then the repo checkout.

    A built wheel ships `assets/site` under the package (see the
    `force-include` in pyproject.toml); a checkout keeps it at the repo root.
    """
    try:
        packaged = Path(str(resource_files("audiobook_lib") / "assets" / "site"))
        if packaged.is_dir():
            return packaged
    except (ModuleNotFoundError, TypeError, OSError):
        pass
    return REPO_ASSETS


DEFAULT_ASSETS = default_assets()

PLACEHOLDER = """<!doctype html>
<html lang="{lang}">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
 body {{ font: 16px/1.7 system-ui, sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem; }}
 .note {{ background: #fffbe6; border: 1px solid #e8d98a; padding: .75rem 1rem; border-radius: .5rem; }}
 li {{ margin: .4rem 0; }}
</style>
<h1>{title}</h1>
<p>{subtitle}</p>
<p class="note">Placeholder page: <code>assets/site/</code> had no
<code>index.html</code> when this site was built. The data files below are the
real output and the player can be dropped in later.</p>
<ul>
{items}
</ul>
<p><a href="book.json">book.json</a></p>
"""


# dropped into every build, so the next build knows the directory is its to replace
MARKER = ".audiobook-site"


def is_built_site(path: Path) -> bool:
    """Ours to replace: marked, or shaped like our output (book.json + chapters/)."""
    if (path / MARKER).is_file():
        return True
    return (path / "book.json").is_file() and (path / "chapters").is_dir()


def check_out_dir(out: Path) -> None:
    if not out.exists():
        return
    if not out.is_dir():
        raise SystemExit(f"{out} exists and is not a directory")
    if any(out.iterdir()) and not is_built_site(out):
        raise SystemExit(
            f"{out} is not empty and was not built by audiobook-build (no {MARKER}); "
            "refusing to replace it — pass a new or empty --out"
        )


def swap_in(stage: Path, out: Path) -> None:
    """Replace `out` with `stage`: two renames, so a running audiobook-serve
    (which resolves every request against the path) sees the old site or the
    new one, never half of each."""
    old = out.parent / f".{out.name}.old"
    shutil.rmtree(old, ignore_errors=True)
    try:
        if out.exists():
            os.replace(out, old)
        os.replace(stage, out)
    except OSError:
        # `out` cannot be renamed (a mount point, say): empty it and move in
        out.mkdir(parents=True, exist_ok=True)
        for item in out.iterdir():
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in stage.iterdir():
            os.replace(item, out / item.name)
        stage.rmdir()
    shutil.rmtree(old, ignore_errors=True)


def copy_assets(assets: Path, out: Path) -> bool:
    """Returns True when real assets were copied."""
    if not assets.is_dir() or not any(assets.iterdir()):
        return False
    for item in assets.iterdir():
        if item.name.startswith("."):
            continue
        dest = out / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    return (out / "index.html").exists()


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_index(text: str, book: Book) -> str:
    """Bake the book's identity into <head> at build time.

    The player sets `document.title` and `<html lang>` from book.json once it
    runs, but link unfurlers (Slack, WeChat, iMessage, Telegram) and most
    crawlers never execute JS — the markup is all they ever see. Tags the asset
    already defines are left alone, so a custom `--site-assets` page keeps its
    own head.
    """
    lang = book.language or "en"
    title = book.title or "Audiobook"
    desc = " ".join((book.description or book.subtitle or "").split())

    if re.search(r"<html\b[^>]*\blang=", text, re.I):
        text = re.sub(
            r'(<html\b[^>]*\blang=")[^"]*(")',
            lambda m: m.group(1) + esc(lang) + m.group(2), text, count=1, flags=re.I,
        )
    else:
        text = re.sub(r"<html\b", lambda m: f'<html lang="{esc(lang)}"', text, count=1, flags=re.I)

    extra: list[str] = []
    if re.search(r"<title>", text, re.I):
        text = re.sub(
            r"<title>.*?</title>", lambda m: f"<title>{esc(title)}</title>",
            text, count=1, flags=re.I | re.S,
        )
    else:
        extra.append(f"<title>{esc(title)}</title>")

    taken = {m.lower() for m in re.findall(r'<meta\s+(?:name|property)="([^"]+)"', text, re.I)}
    wanted = (
        ("name", "description", desc),
        ("name", "author", book.author),
        ("property", "og:type", "website"),
        ("property", "og:title", title),
        ("property", "og:description", desc),
        ("name", "twitter:card", "summary"),
    )
    extra += [
        f'<meta {kind}="{key}" content="{esc(value)}">'
        for kind, key, value in wanted
        if value and key not in taken
    ]
    if not extra:
        return text

    block = "\n".join(extra)
    if re.search(r"</head>", text, re.I):
        return re.sub(r"</head>", lambda m: block + "\n</head>", text, count=1, flags=re.I)
    return block + "\n" + text


def link_or_copy(src: Path, dest: Path) -> None:
    """Hardlink when possible — a book is hundreds of MB of audio."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def audio_version(path: Path) -> str:
    """A short hash of the file's bytes, added to its URL as `?v=`.

    A re-synthesized chapter keeps its file name, so the hash is what gives
    new audio a new URL. That lets the host tell browsers to cache audio
    forever: a returning listener never plays an old recording against new
    timings.
    """
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()[:12]


def transcript_manifest(book: Book, ch: Chapter) -> dict[str, Any]:
    """A manifest with no timing, for chapters that have not been synthesized."""
    segments = []
    for seg in ch.segments(book.pronunciations):
        entry: dict[str, Any] = {
            "i": seg.i, "kind": seg.kind, "start": None, "end": None, "html": seg.html,
        }
        if seg.level:
            entry["level"] = seg.level
        if seg.spoken:
            entry["spoken"] = seg.spoken
        segments.append(entry)
    return {
        "id": ch.id, "title": ch.title, "audio": None, "duration": None,
        "language": book.language, "segments": segments,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book_dir")
    ap.add_argument("--out", help="output directory (default BOOK_DIR/site)")
    ap.add_argument("--site-assets", help=f"player assets (default {DEFAULT_ASSETS})")
    args = ap.parse_args()

    book = load_book(args.book_dir)
    final = Path(args.out).expanduser().resolve() if args.out else book.dir / "site"
    assets = Path(args.site_assets).expanduser().resolve() if args.site_assets else DEFAULT_ASSETS
    check_out_dir(final)
    out = final.parent / f".{final.name}.building"
    shutil.rmtree(out, ignore_errors=True)
    (out / "chapters").mkdir(parents=True)
    (out / MARKER).write_text("built by audiobook-build; replaced wholesale on every build\n")

    have_assets = copy_assets(assets, out)
    if have_assets:
        index = out / "index.html"
        index.write_text(render_index(index.read_text("utf-8"), book), encoding="utf-8")
    else:
        print(f"notice: no player assets in {assets} — writing a placeholder index.html")

    chapters_meta: list[dict[str, Any]] = []
    for ch in book.chapters:
        manifest_src = book.audio_dir / f"{ch.id}.json"
        if manifest_src.exists():
            manifest = json.loads(manifest_src.read_text("utf-8"))
        else:
            manifest = transcript_manifest(book, ch)

        # the manifest names the file, extension and all: mp3, opus or m4a
        audio_rel: str | None = None
        named = str(manifest.get("audio") or "")
        if named:
            src = book.audio_dir / Path(named).name
            if src.exists() and src.suffix.lower() in A.AUDIO_EXTS:
                audio_rel = f"audio/{src.name}?v={audio_version(src)}"
                link_or_copy(src, out / "audio" / src.name)
        manifest["audio"] = audio_rel

        (out / "chapters" / f"{ch.id}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        chapters_meta.append(
            {
                "id": ch.id,
                "title": ch.title,
                "audio": audio_rel,
                "duration": manifest.get("duration"),
                "manifest": f"chapters/{ch.id}.json",
            }
        )

    book_json = {
        "title": book.title,
        "subtitle": book.subtitle,
        "author": book.author,
        "description": book.description,
        "language": book.language,
        "depth": book.depth,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chapters": chapters_meta,
    }
    (out / "book.json").write_text(json.dumps(book_json, ensure_ascii=False, indent=1), encoding="utf-8")

    if not have_assets:
        items = "\n".join(
            f'  <li><a href="{c["manifest"]}">{c["id"]}</a> — {c["title"]}'
            + (
                f' (<a href="{c["audio"]}">{Path(c["audio"].partition("?")[0]).suffix.lstrip(".")}</a>)'
                if c["audio"] else " — no audio yet"
            )
            + "</li>"
            for c in chapters_meta
        )
        (out / "index.html").write_text(
            PLACEHOLDER.format(
                lang=book.language, title=book.title,
                subtitle=book.subtitle or book.description, items=items,
            ),
            encoding="utf-8",
        )

    swap_in(out, final)

    with_audio = sum(1 for c in chapters_meta if c["audio"])
    print(
        f"built {final}: {len(chapters_meta)} chapters, {with_audio} with audio, "
        f"{len(chapters_meta) - with_audio} transcript-only"
    )
    for cid in stale_chapters(book):
        print(
            f"  warning: {cid}: audio/{cid}.json was rendered from a different transcript "
            f"than chapters/{cid}.md — re-run audiobook-synth"
        )
    if hint := orphan_hint(book):
        print(hint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
