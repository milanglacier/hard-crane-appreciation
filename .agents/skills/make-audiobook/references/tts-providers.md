# TTS providers

`audiobook-synth` talks to several providers through one interface; the
provider is chosen in `book.yaml: tts.provider` (or `--provider`). Whatever a
provider returns is normalized by ffmpeg into one canonical FLAC per clip on the
way into the cache, so every provider gets paragraph-level sync for free; a few
also return word timing, which the page uses for word-level highlighting when
present.

The landscape moves fast and **no neutral benchmark for Chinese/English
code-switched TTS exists** (as of September 2026, the public arenas score
English only). Treat the ranking below as a starting point and let the user's
ears decide: synthesize the same paragraph with two or three providers and
listen before committing to a whole book. (Commands are written bare here; run
them with one of the prefixes from SKILL.md — `uv run --project <skill>`,
`nix develop path:<skill> -c`, or `nix run path:<skill>#synth --`.)

```bash
audiobook-synth BOOK --preview --chapter 01 --provider azure
audiobook-synth BOOK --preview --chapter 01 --provider qwen
audiobook-synth BOOK --preview --chapter 01 --provider elevenlabs --voice <id>
```

Each writes `audio/preview.<ext>`; rename between runs to compare.

## Quick chooser

| need                                         | pick                          |
| -------------------------------------------- | ----------------------------- |
| Chinese narration with inline English terms  | `azure` (default), then A/B `qwen`, `minimax` |
| Best English literary narration              | `elevenlabs` (`eleven_v3` or `eleven_multilingual_v2`) |
| Word-level highlighting                      | `elevenlabs` (character alignment) |
| Cheapest acceptable, quick drafts            | `openai` `gpt-4o-mini-tts`, or `azure` inside its free 500k chars/month |
| Fully offline / no account                   | `mock` (tests only). For a real local engine see the note at the end. |

## Providers

| provider     | env                                   | default model / voice                     | zh + en mixed                         | timing        | approx price (per 1M chars) |
| ------------ | ------------------------------------- | ----------------------------------------- | ------------------------------------- | ------------- | --------------------------- |
| `azure`      | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | `zh-CN-XiaoxiaoMultilingualNeural` / `en-US-AvaMultilingualNeural` | documented mixed-lingual handling: English spans inside Chinese get English phonology | none via REST (segment sync only) | ~$16; 500k free/month |
| `qwen`       | `DASHSCOPE_API_KEY` (+ `DASHSCOPE_BASE_URL` for mainland) | `qwen3-tts-flash` / `Cherry`       | official docs demo a mixed sentence; community reports fluent switching | none          | ~$15 (unconfirmed)          |
| `minimax`    | `MINIMAX_API_KEY`, `MINIMAX_GROUP_ID` (+ `MINIMAX_BASE_URL`) | `speech-2.6-hd` / narrator voice | very low Chinese WER; vendor warns its subtitles misalign on mixed text | sentence subtitles (not used) | ~$100 (hd)      |
| `elevenlabs` | `ELEVENLABS_API_KEY`                  | `eleven_multilingual_v2` / any voice id   | good; occasional accent drift on long clips (we send short clips) | character-level → words | ~$100–150 depending on plan |
| `openai`     | `OPENAI_API_KEY` (+ `OPENAI_BASE_URL` for compatible servers) | `gpt-4o-mini-tts` / `alloy` | intelligible; voices tuned for English | none          | ~$0.60 input + audio ≈ $12–15/1M chars-equivalent |
| `gemini`     | `GEMINI_API_KEY`                      | `gemini-2.5-flash-preview-tts` / `Kore`   | 70+ languages; steerable by prompt; preview API | none          | ~$10–15 equivalent (preview pricing) |
| `mock`       | —                                     | —                                         | tone bursts of realistic length       | fake words    | free                        |

Account gotchas:

- **MiniMax** and **DashScope** have separate mainland and international
  consoles; keys are not interchangeable (`api.minimax.io` vs
  `api.minimaxi.com`; `dashscope-intl.aliyuncs.com` vs `dashscope.aliyuncs.com`).
- **Volcengine/Doubao** (ByteDance) is mainland-only with real-name
  verification and is not implemented.
- **Fish Audio** bills per UTF-8 byte, so Chinese costs ~3× per character;
  not implemented.
- **Hume** has no Chinese. **Cartesia** tops English arenas and returns
  word/phoneme timing but has no Chinese evidence; consider it only for
  English books (not implemented yet — easy to add given the provider ABC).

## Configuration reference (`book.yaml: tts`)

```yaml
tts:
  provider: azure
  voice: zh-CN-XiaoxiaoMultilingualNeural
  speed: 1.0              # 0.8–1.3 sensible; listeners can speed up in the player anyway
  style: narration-relaxed  # azure only (mstts:express-as), optional
  instructions: …          # openai / gemini / elevenlabs v3 style prompt; ignored by azure/qwen/minimax
  lang: zh-CN              # override the xml:lang / language_type derived from book.language
  max_chars: 3000          # per-request chunk size, provider defaults are sane
  format: mp3              # mp3 | opus (half the size) | aac (.m4a)
  loudnorm: true           # EBU R128 to -16 LUFS; `false` leaves levels alone
  bitrate_kbps: 96         # mono; the default follows the format (opus: 48)
  concurrency: 4
  pause_ms: {paragraph: 550, heading: 900, line: 250, rule: 1500}
  extra: {}                # merged into the provider request body verbatim
```

Per-chapter overrides go in the chapter's frontmatter with the same keys
(`voice: …`, `speed: …`), which is handy for a poetry chapter that wants a
slower pace or a different voice.

## Voice selection

```bash
audiobook-synth BOOK --list-voices                # for the configured provider
audiobook-synth BOOK --list-voices --provider elevenlabs
```

For Chinese narration prefer *multilingual* voices (Azure names containing
`Multilingual`, ElevenLabs multilingual models): they are the ones trained to
switch phonology mid-sentence. Preview a paragraph that contains several
English terms and at least one spoken formula before choosing.

## Style prompts (providers that accept `instructions`)

A calm educational narrator reads noticeably better than the defaults. For
`openai` / `gemini`:

```
沉稳、清晰、语速适中的讲解者，像在给朋友讲课。中英文混读时英文单词自然带过，
不要刻意加重或放慢。遇到公式时稍微放慢，逗号处明显停顿。
```

```
Calm, clear, unhurried explainer, as if teaching a friend on a walk. Read
embedded technical terms naturally without emphasis. Slow down slightly for
formulas and pause clearly at commas.
```

Azure ignores `instructions`; use `style` (e.g. `narration-relaxed`,
`newscast-casual` where the voice supports it) and `speed` instead.

## Pronunciation control

Provider markup differs, so the pipeline normalizes at the text level
instead: `{{shown||spoken}}` overrides and the `pronunciations` map in
`book.yaml` are applied to the spoken text before any provider sees it (see
`transcript-format.md`). This is also the only mechanism that survives
switching providers. Reserve provider-specific SSML (`extra`) for the rare
case where text-level rewriting cannot express what you need.

## Cost estimate

```bash
audiobook-synth BOOK --dry-run
```

prints characters per chapter, what is already cached, and a rough cost from
the table above. A ten-chapter, two-hour Chinese book is ~30k 汉字, i.e. well
inside Azure's free tier and a few dollars on ElevenLabs.

## Word-level timing

Only `elevenlabs` returns alignment through this pipeline today. Azure's
word boundaries are available through its Batch Synthesis API
(`wordBoundaryEnabled`) rather than the real-time REST endpoint the script
uses; adding that is the natural next step if word-level highlighting for
Chinese becomes important. Segment-level highlighting needs no provider
support and is what most listeners actually use.

## Local engines (not wired in)

CosyVoice 2/3 (Alibaba, designed for Mandarin–English switching), IndexTTS2
(Bilibili, non-standard licence), and Fish Speech / OpenAudio (non-commercial
licence) are the credible self-hosted options. They need a GPU and return no
timing. To add one, implement `audiobook_lib/tts/base.py`'s `Provider` against
its local HTTP server; the rest of the pipeline is unchanged.
