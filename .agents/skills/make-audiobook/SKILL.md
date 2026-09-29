---
name: make-audiobook
description: Turn a topic or source material into a narrated audiobook. Use when the user wants to learn or enjoy something by listening rather than reading, or wants to revise, re-synthesize, or serve an audiobook made earlier.
---

# Make an audiobook

An audiobook is a different artifact from a paper or a blog post: the listener
cannot see, cannot skim, and is probably on a train. This skill produces
three things in order, with the user reviewing between them:

1. **Transcript** — `outline.md` plus one Markdown file per chapter.
2. **Audio** — one MP3 per chapter plus a timing manifest, produced by
   `audiobook-synth` from a cloud TTS provider, cached per paragraph.
3. **Player** — a static site (`audiobook-build`) that plays chapters
   back to back, highlights the paragraph being spoken, remembers position,
   and works on a phone via `audiobook-serve`.

Resolve `<skill>` to the directory containing this file. Commands:

```bash
uv run --project <skill> audiobook-synth BOOK_DIR      # anywhere with uv + ffmpeg
nix develop path:<skill> -c audiobook-synth BOOK_DIR   # Nix: locked env incl. ffmpeg
nix run path:<skill>#synth -- BOOK_DIR                 # Nix, one-off
```

Six commands: `audiobook-stats`, `audiobook-synth`, `audiobook-build` and
`audiobook-serve` run the pipeline; `audiobook-clean` and `audiobook-cache`
keep a book tidy. Prefer the uv form; use the Nix forms when uv or ffmpeg is
missing (NixOS). The `path:` prefix matters when the directory is not tracked
by git. Synthesis needs **ffmpeg** on PATH, which the Nix forms provide; the
other commands do not. The rest of this file writes the commands bare
(`audiobook-synth BOOK_DIR …`); one of the prefixes above is always implied.

Nothing here hardcodes depth, length, or language — those are agreed with the
user in the outline.

## Phase 1 — Agree on the book

Read `references/writing-guide.md` §1 first. Then settle, with the user or from
what they already said, the *depth contract*: who is listening, what they
should take away, how much math/code/quotation, total and per-chapter
length, language, sources. Propose defaults rather than interrogating —
Chinese narration, commute-sized 8–15 minute chapters, depth level 2
("skeleton formulas") for technical topics — and ask only about what changes
the work materially.

If the user supplies material (papers, a book, notes), read all of it before
outlining.

Create the book directory (default `./<slug>-audiobook/`), write `book.yaml`
(schema in `references/transcript-format.md`; start from provider `azure`
unless the user has a preference) and `outline.md` from
`assets/outline-template.md`: the contract, a glossary of term decisions, and
a chapter plan with the 2–4 takeaways and the formulas/passages each chapter
will use.

**Checkpoint:** show the outline and wait for approval. Do not draft chapters
against an unapproved outline; re-planning after the fact wastes the user's
review effort.

## Phase 2 — Write the transcript

Read `references/writing-guide.md` in full and `references/math-and-code.md`
when the topic has any math or code. Follow the block conventions in
`references/transcript-format.md`: spoken text is ordinary paragraphs, exact
formulas and code go in `$$` / fenced blocks (shown, never narrated), poems
and quotations in blockquotes (read line by line), `{{shown||spoken}}` when the
screen and the narrator must differ, `pronunciations` in `book.yaml` for
recurring symbols and acronyms.

The things that most often go wrong, and why they matter:

- **Math read as symbol soup.** Say the meaning, then the formula as a
  sentence ("x t 等于 根号 alpha bar t 乘以 x zero …"), then show the exact
  LaTeX in a display block. Keep each spoken formula under ~15 seconds.
- **Code dictated.** Describe intent and the two identifiers that matter;
  show the snippet.
- **Terminology drift.** Chinese narration keeps practitioner terms in
  English (buffer, trait, diffusion model); translated terms get their English
  on first appearance in each chapter; every choice is recorded once in the
  outline glossary and reused verbatim.
- **Visual references.** Never "如下图所示" / "the equation above"; the audio
  must stand alone.
- **Paragraphs too long.** 60–150 汉字 per paragraph; the paragraph is the
  unit of highlighting and of TTS phrasing.

Chapters may be drafted in parallel (one writer per chapter, each given the
outline and glossary), but read the whole set afterwards for drift, repeated
openings, and missing bridges.

Then run the linter and share its table with the user:

```bash
audiobook-stats BOOK_DIR
```

It estimates minutes per chapter and flags raw inline math, over-long
paragraphs, display blocks with no narration around them, and unbalanced
overrides. Fix flags before review.

**Checkpoint:** hand the chapters to the user. Expect several rounds of
edits; they are cheap, because unchanged paragraphs are never re-synthesized.

## Phase 3 — Synthesize audio

Read `references/tts-providers.md` for the provider table, environment
variables, and voice advice. Check the key is present before anything else
(`echo ${AZURE_SPEECH_KEY:+set}` etc.) and tell the user which variable to
export if not.

Synthesis costs money and a bad voice choice is discovered only by
listening, so always go preview → estimate → confirm → run:

```bash
audiobook-synth BOOK_DIR --list-voices
audiobook-synth BOOK_DIR --preview --chapter 01  # → audio/preview.mp3, first 3 paragraphs
audiobook-synth BOOK_DIR --dry-run               # chars, cached vs new, est. cost
audiobook-synth BOOK_DIR                         # all chapters (skips unchanged)
audiobook-synth BOOK_DIR --chapter 03            # one chapter after edits
```

Preview a paragraph that contains embedded English terms and a spoken
formula — that is where providers differ most. If the user is undecided,
preview the same chapter with two providers (`--provider qwen`,
`--provider elevenlabs --voice …`) and let them listen. Point the user at
`audio/preview.mp3` (or serve it, see Phase 4) and get an explicit go-ahead
before the full run; report the estimated cost when asking.

Output: `audio/<chapter>.mp3` (or `.opus` / `.m4a` via `tts.format`) and
`audio/<chapter>.json` (segment timings). Chapters are loudness-normalized to
-16 LUFS by default so different voices and providers sit at the same level.
Per-paragraph results are cached in `.cache/tts/` as lossless FLAC, keyed by
provider, voice, speed and text, so a re-run after editing one paragraph
synthesizes only that paragraph.

## Phase 4 — Build and serve the player

```bash
audiobook-build BOOK_DIR                         # → BOOK_DIR/site/
audiobook-serve BOOK_DIR/site --host 0.0.0.0 --port 8000
```

`audiobook-build` works before audio exists too (transcript-only mode), which
is a good way to let the user review chapters on a phone. `audiobook-serve`
supports HTTP range requests (iOS Safari needs them for seeking) and prints
every LAN address it is reachable on; give the user those URLs. It runs until
Ctrl-C, so start it in the background when you need to keep working.

`site/index.html` is build output: the player comes from `assets/site/`, and
its `<head>` — title, `<html lang>`, description, `og:` tags — is filled in
from `book.yaml`. Link unfurlers and most crawlers read the page without
running the player's JS, so the book's identity has to be in the markup. The
book's metadata therefore lives in `book.yaml`; every build rewrites the copy
under `site/`.

The player is a single page: an index with the chapter list, progress and a
"continue" button; a chapter view with the transcript, the current paragraph
highlighted and kept in view, tap-to-seek, a sticky bar with play/pause,
±15/30 s, speed, sleep timer and autoplay-next; position is remembered and
lock-screen controls work through the Media Session API.

## Iterating

Edit chapter Markdown → `audiobook-stats` → `audiobook-synth` (only changed
paragraphs are re-synthesized, but the chapter MP3 is re-assembled) →
`audiobook-build` → refresh the browser. A change to `book.yaml: tts.*`
invalidates the cache for the affected chapters by design; warn the user
before switching voice on a finished book.

`audiobook-build` warns when a chapter's audio was rendered from an older
transcript; re-run `audiobook-synth` for it.

## Housekeeping

```bash
audiobook-clean BOOK_DIR [--dry-run]     # remove files in audio/ no chapter uses
audiobook-cache BOOK_DIR                 # cache size, referenced vs not
audiobook-cache BOOK_DIR gc [--yes]      # prune long-unused, unreferenced clips
```

- **`site/`** is replaced wholesale by every build, so a renamed or removed
  chapter disappears from the player by itself.
- **`audio/`** keeps files no chapter uses after a chapter is renamed or
  removed, after `tts.format` changes, and after a preview; synth and build
  point them out. `audiobook-clean` removes them; commit the deletions
  afterwards. Any of them can be re-rendered from the cache for free.
- **`.cache/tts/`** holds every clip ever synthesized, including ones the
  transcript no longer uses, so reverting a paragraph costs nothing.
  `audiobook-cache gc` lists clips that neither the transcript nor the
  manifests in `audio/` reference *and* that have gone unused for 60 days
  (`--older-than DAYS`); `--yes` deletes them. Run it only when the user asks
  for disk space back.

## Files

- `references/writing-guide.md` — writing for the ear: depth contract,
  chapter shape, sentence habits, Chinese/English term policy, literature
  chapters, pace estimation, review loop.
- `references/math-and-code.md` — how to speak formulas and code in Chinese
  and English, with tables and a worked example.
- `references/transcript-format.md` — the Markdown conventions, `book.yaml`
  schema, segment model, and the manifest the commands exchange.
- `references/tts-providers.md` — provider comparison, env vars, voices,
  style prompts, costs, gotchas.
- `references/deploy-vercel.md` — Git-based Vercel deploy: what to commit,
  build script, `vercel.json`, `.vercelignore`, pitfalls.
- `assets/outline-template.md` — skeleton for `outline.md`.
- `assets/site/` — the web player (copied into each book's `site/`).
- `src/audiobook_lib/` — the package: `cli/` (one module per command) plus
  the shared library (segmenter, providers, cache, ffmpeg assembly,
  housekeeping).
- `tests/` — pytest suite (`nix develop path:<skill> -c pytest`, or
  `uv run --project <skill> --group dev pytest <skill>/tests`).
- `pyproject.toml` / `uv.lock` — dependencies and the console scripts.
- `flake.nix` — dev shell and apps with ffmpeg, uv, python
  (`nix develop path:<skill>`, `nix run path:<skill>#synth`).
