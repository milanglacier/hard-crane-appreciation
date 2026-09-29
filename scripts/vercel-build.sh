#!/bin/sh
# Vercel build: regenerate hard-crane-appreciation/site, which is gitignored build output.
# Lives in a script because vercel.json caps buildCommand at 256 characters.
set -eu

# Vercel's build image ships a Python that uv itself manages, so `pip3 install uv`
# dies under PEP 668. Use the image's own uv when present, else install it.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# audiobook-build needs no ffmpeg, and uv fetches its own CPython.
exec uv run --python 3.12 --project .agents/skills/make-audiobook \
  audiobook-build hard-crane-appreciation
