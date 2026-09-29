# Hart Crane Appreciation

This repository contains the setup for a Chinese-language audiobook about Hart Crane's poetry. The book has no outline or chapters yet.

The source notes are kept locally in `references/` and are excluded from Git. The player is built from `hard-crane-appreciation/book.yaml`, chapter transcripts, and audio files. Vercel runs `scripts/vercel-build.sh` on Git deploys and serves the generated `hard-crane-appreciation/site/` directory.

## Local commands

Run these commands from the repository root. Add the MiniMax API key to the local `.env` file before generating audio.

```sh
export $(grep -v '^#' .env | xargs)
uv run --project .agents/skills/make-audiobook audiobook-stats hard-crane-appreciation
uv run --project .agents/skills/make-audiobook audiobook-build hard-crane-appreciation
uv run --project .agents/skills/make-audiobook audiobook-serve hard-crane-appreciation/site --host 0.0.0.0 --port 8000
```

Audio synthesis requires explicit approval under `AGENTS.md`. When approved, it also requires `ffmpeg`.
