# Project Rules

## Writing

Write in plain, simple language everywhere: **code, comments, docstrings,
commit messages, docs, README documentation, chapter transcripts, and
explanations to the user**.

### Code, Comments, Docstrings & Transcripts

The text in the repo must read as the final, clean version. It should carry
no trace of the back and forth it took to get there, as if it had never been
written any other way. Describe only the current state:

- No references to earlier drafts or revisions: no "in the previous version",
  no "we changed this to", no contrast with earlier behavior. Record behavior
  changes in commit messages, where readers have the relevant context.
- Chapter transcripts are the finished book, not a draft with corrections
  layered on top. If an explanation needs rework, rewrite the passage itself
  so the book reads as one consistent whole. References to earlier chapters
  are part of the finished book and are fine.

### Commit Messages & Communication

Write commit messages and explanations to the user in plain English, since the
user may not read the code. Use complete sentences, not compressed jargon or
dense noun phrases. Bad: "fix: tts cache invalidation". Good: "fix(cache):
re-synthesizing a chapter after an edit only pays again for the paragraphs that
changed". Do not coin terminology; say what the thing does instead.

Commit messages should read like a human explaining the change, not
telegraphic shorthand. The maintainer has repeatedly pushed back on terse,
abbreviated subject lines that drop the words that carry the actual intent.
Write the subject as a full, clear sentence. It may be long — that is fine —
but it must name the real outcome, not a compressed label for it.

## Appreciation depth and language

- Target depth: university literature major. Assume the listener has basic
  literary-theory vocabulary but has not studied Crane before.
- The audiobook is in Chinese (Mandarin). Crane's original poetry lines must
  be quoted in English.
- When discussing imagery during appreciation:
  - If the word or phrase is quoted directly from Crane's original text, keep
    it in English.
  - Otherwise use Chinese and provide a translation.
- For Crane's more obscure English imagery, give a brief Chinese gloss in
  parentheses on first use. If the meaning is straightforward, a direct
  translation is enough; do not over-explain.

## Serving

- When serving the audiobook site, bind to `0.0.0.0` (not `127.0.0.1`).

## TTS Provider

- Use MiniMax as the TTS provider. The MiniMax API key is stored in `.env` at the repo root.
- Load env vars with `export $(grep -v '^#' .env | xargs)` **before** running any audiobook command. `source .env` alone does not export the variables into subprocesses (e.g. `nix-shell --run`).

## Running audiobook commands

- The audiobook skill lives in `.agents/skills/make-audiobook`, with `.claude/skills/make-audiobook` as a symlink to it. Either path works for `--project`.
- The commands (`audiobook-synth`, `audiobook-build`, `audiobook-serve`, `audiobook-stats`, `audiobook-clean`, `audiobook-cache`) are run with `uv run --project .claude/skills/make-audiobook <command>` (or `.agents/skills/make-audiobook`).
- `audiobook-synth` requires `ffmpeg`. On Nix systems (NixOS or any machine with Nix installed), wrap the command with `nix-shell -p ffmpeg --run "..."` to provide ffmpeg on the fly. On non-Nix systems, install ffmpeg yourself (e.g. `apt install ffmpeg`, `brew install ffmpeg`) so it is on PATH. Example:
  ```bash
  export $(grep -v '^#' .env | xargs)
  # Nix:
  nix-shell -p ffmpeg --run "uv run --project .claude/skills/make-audiobook audiobook-synth hard-crane-appreciation"
  # Non-Nix (ffmpeg already on PATH):
  uv run --project .claude/skills/make-audiobook audiobook-synth hard-crane-appreciation
  ```
- `audiobook-build`, `audiobook-serve`, `audiobook-stats`, `audiobook-clean` and `audiobook-cache` do **not** need ffmpeg — `uv run` alone is fine.
  `build_site.py` imports `audiobook_lib.audio` only for the `AUDIO_EXTS` constant; the ffmpeg
  lookup is lazy, inside the encode helpers. This is what lets Vercel build the site (see below).
- `--list-voices` also does not need ffmpeg.

## Build pipeline

The full rebuild sequence is:

```bash
export $(grep -v '^#' .env | xargs)
nix-shell -p ffmpeg --run "uv run --project .claude/skills/make-audiobook audiobook-synth hard-crane-appreciation"
uv run --project .claude/skills/make-audiobook audiobook-build hard-crane-appreciation
uv run --project .claude/skills/make-audiobook audiobook-serve hard-crane-appreciation/site --host 0.0.0.0 --port 8000
```

## Audiobook workflow

- **STOP: Do NOT run `audiobook-synth` without explicit user approval.**
  After drafting new or revised chapter transcripts:
  1. Run `audiobook-stats` and share the results.
  2. **STOP and wait.** Do not proceed until the user explicitly says to synthesize (e.g. "go ahead", "synth it", "approved").
  3. Only then run `audiobook-synth`. Synthesis costs real money and cannot be
     undone. Skipping the review step or assuming approval is NEVER acceptable
     , not even if the stats show zero warnings, not even if the user said "do
     everything", not even if you think the chapters are obviously fine. Always
     wait for the explicit go-ahead.

## Version control

- `.env` is gitignored (contains API keys).
- `.cache/tts/` is gitignored (local paragraph-level FLAC cache, keyed by voice+text). It is what
  makes reverting a paragraph free: never delete it by hand, and run `audiobook-cache gc` only when
  asked.
- `audio/` is tracked — synthesis costs money, so the mp3s and their timing JSON are the one
  thing that must never be lost.
- `site/` is **not** tracked (gitignored): it is pure build output, regenerated from `audio/` +
  `chapters/` + `book.yaml` by `audiobook-build`, which Vercel runs on every deploy.

## Deploying to Vercel

Config is `vercel.json` + `.vercelignore` at the repo root. Things those files don't tell you:

- **Git-based deploys only.** `site/` is gitignored, so Vercel regenerates it by running
  `scripts/vercel-build.sh`. Keep the `buildCommand` in `vercel.json` a one-liner pointing at
  that script — Vercel's schema caps `buildCommand` at 256 characters.
- **`.vercelignore` applies to Git deploys, not just `vercel deploy`.** Anything listed there is
  absent from the build context.
