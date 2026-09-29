# Deploying the player to Vercel

To put the player on the web, use a Git-based Vercel deploy: commit
`chapters/`, `audio/` and `book.yaml`, keep `site/` out of git.

The player is a static site, so any static host works. This file covers
Vercel with Git-based deploys: the repository holds the transcript and the
audio, and Vercel runs `audiobook-build` on every push to regenerate `site/`.

## Why Git-based, not `vercel deploy`

- `site/` is build output. It can be rebuilt from `chapters/`, `audio/` and
  `book.yaml` for free, so it stays out of git and Vercel rebuilds it.
- The audio makes the site large. The Vercel CLI caps its source upload
  (100 MB on Hobby, 1 GB on Pro), and a book of a dozen chapters gets close
  to that. Git-based deploys do not go through that upload path.
- `audiobook-build` needs no ffmpeg and uv fetches its own CPython, so the
  build runs in Vercel's standard build image.

## What the repository must track

Everything Vercel needs to run the build:

- the skill directory (the real directory, not a symlink to it);
- `BOOK_DIR/book.yaml`, `BOOK_DIR/chapters/`, `BOOK_DIR/audio/`.

And in `.gitignore`:

```gitignore
.env
.vercel/
BOOK_DIR/site/
BOOK_DIR/.cache/
```

`audio/` must be committed: synthesis costs money, and Vercel has no API
keys and no cache to re-create it. Commit it after every `audiobook-synth`
run, or the deployed site plays stale audio.

## The three files

Paths below assume the repository root holds both the skill (at `SKILL_DIR`,
e.g. `.agents/skills/make-audiobook`) and the book (at `BOOK_DIR`). Replace
both placeholders with real paths relative to the repository root.

### `scripts/vercel-build.sh`

```sh
#!/bin/sh
# Vercel build: regenerate BOOK_DIR/site, which is gitignored build output.
# Lives in a script because vercel.json caps buildCommand at 256 characters.
set -eu

# Vercel's build image ships a Python that uv itself manages, so `pip3 install uv`
# dies under PEP 668. Use the image's own uv when present, else install it.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# audiobook-build needs no ffmpeg, and uv fetches its own CPython.
exec uv run --python 3.12 --project SKILL_DIR audiobook-build BOOK_DIR
```

### `vercel.json`

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "buildCommand": "sh scripts/vercel-build.sh",
  "installCommand": "true",
  "outputDirectory": "BOOK_DIR/site",
  "cleanUrls": true,
  "trailingSlash": false,
  "headers": [
    {
      "source": "/audio/:file*",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    },
    {
      "source": "/chapters/:file*",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=0, must-revalidate" }
      ]
    },
    {
      "source": "/book.json",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=0, must-revalidate" }
      ]
    },
    {
      "source": "/(app.js|style.css)",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=0, must-revalidate" }
      ]
    },
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" }
      ]
    }
  ]
}
```

Audio can be cached for a year because `audiobook-build` adds a hash of each
file's contents to its URL, so a re-synthesized chapter gets a new URL.

### `.vercelignore`

```gitignore
# This applies to Git deploys too, not just `vercel deploy`. Anything listed here is
# absent from the build context.
.env
.vercel/
BOOK_DIR/.cache/
BOOK_DIR/outline.md
```

Add docs and editor directories as you like, but never the skill directory,
`chapters/`, `audio/` or `book.yaml`: the build reads all of them.

## Setting up the project on Vercel

1. Push the repository to GitHub (or GitLab, Bitbucket).
2. In Vercel, import the repository. Leave the framework preset as "Other"
   and the root directory as the repository root; `vercel.json` supplies the
   build command and the output directory.
3. Every push to the production branch deploys. Other branches get preview
   URLs.

## Pitfalls

- **`.vercelignore` applies to Git deploys.** Listing a build input there
  removes it from the build context. The typical symptom is uv reporting
  `Failed to spawn: audiobook-build` or `No pyproject.toml found`, because
  the skill directory arrived empty.
- **`buildCommand` is capped at 256 characters.** Keep it a one-liner that
  calls the script.
- **Do not `pip3 install uv`.** It fails with PEP 668
  (`externally-managed-environment`); the script's standalone installer
  avoids that.
- **Do not add a SPA rewrite to `index.html`.** The player routes with the
  URL hash (`#/`, `#/ch/<id>`), so every route already is the one real
  `index.html`. A catch-all rewrite would only hide 404s on missing audio or
  JSON.

## Checking a build before pushing

Reproduce what Vercel sees: clone the repository fresh, delete what
`.vercelignore` lists, and run the script from the clone's root.

```bash
git clone . /tmp/vercel-check && cd /tmp/vercel-check
rm -rf .env .vercel BOOK_DIR/.cache BOOK_DIR/outline.md   # match .vercelignore
sh scripts/vercel-build.sh
```

The build should report every chapter with audio, and `BOOK_DIR/site/`
should contain `index.html`, `book.json`, `chapters/` and `audio/`.
