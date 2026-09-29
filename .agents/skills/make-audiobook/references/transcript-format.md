# Transcript format

This is the contract shared by the human reviewer, the writer, and the
commands (`audiobook-stats`, `audiobook-synth`, `audiobook-build`). The transcript is written
as ordinary Markdown so it is pleasant to review, but every block falls into one
of three classes:

| class          | what it means                                    | blocks                                              |
| -------------- | ------------------------------------------------ | --------------------------------------------------- |
| spoken + shown | narrated, highlighted on screen while it plays   | headings, paragraphs, list items, blockquote lines  |
| shown only     | rendered on screen, never narrated                | fenced code, `$$ … $$` math, tables, images, raw HTML |
| neither        | notes to yourself or the reviewer                 | `<!-- HTML comments -->`, YAML frontmatter          |

The rule behind the split: **the audio must stand on its own.** A listener on a
train never sees the screen. Shown-only blocks exist so that someone who does
glance at the screen gets the exact formula, the exact code, or the exact
spelling. The surrounding prose must already have said everything that matters.

## Book layout

```
<book-dir>/
├── book.yaml            # metadata + TTS config (schema below)
├── outline.md           # the plan agreed with the user; see writing-guide.md
├── chapters/
│   ├── 01-<slug>.md     # one file per chapter, ordered by the numeric prefix
│   └── 02-<slug>.md
├── audio/               # produced by audiobook-synth: <chapter>.mp3|opus + .json
├── site/                # produced by audiobook-build; serve this directory
└── .cache/tts/          # per-segment FLAC cache keyed by content hash
```

Chapter files are picked up by sorting `chapters/*.md`. Use a two-digit prefix
and an ASCII slug (`03-borrow-checker.md`) so the order is stable and the
generated audio file names are portable.

## book.yaml

```yaml
title: 扩散模型：从加噪到生成
subtitle: 一本给通勤路上听的入门书          # optional
author: Milan Glacier                      # optional, shown on the index page
language: zh-Hans                          # BCP-47 tag; narration language and <html lang>
description: >                              # index page, and the page's meta description
  用十个章节讲清楚 diffusion model 的直觉、数学骨架和工程取舍。
depth: >                                    # the depth contract agreed in outline.md, kept
  直觉 + 主干公式（forward/reverse process, ELBO 的简化形式），不做完整推导。
tts:
  provider: openai          # see tts-providers.md for the supported values
  model: gpt-4o-mini-tts
  voice: alloy
  speed: 1.0
  format: mp3               # mp3 | opus | aac — the container synth writes
  loudnorm: true            # EBU R128 normalization to -16 LUFS
  instructions: >           # style prompt, used by providers that accept one
    沉稳、清晰、不急不缓的讲解者。中英文混读时英文单词自然带过，不要刻意加重。
  pause_ms:                 # silence inserted between segments; all optional
    paragraph: 550
    heading: 900
    line: 250               # between blockquote / poem lines
    rule: 1500              # at a --- horizontal rule
pronunciations:             # optional: spoken replacements applied to every chapter
  "$\\bar\\alpha_t$": "alpha bar t"
  "SQL": "S Q L"
  "Vec<T>": "Vec T"
```

Only `title` and `language` are required. `tts.*` can also be overridden per
chapter in the chapter's frontmatter (for example a different voice for a
chapter that is mostly poetry).

`language` takes any BCP-47 tag (`zh`, `zh-Hans`, `en`, `en-US`). It is emitted
verbatim as the page's `<html lang>`, so prefer the precise tag; a tag starting
with `zh` also selects the player's Chinese UI strings, anything else gets the
English ones.

## Chapter files

```markdown
---
title: 第三章  借用检查器在想什么        # optional; defaults to the first H1
voice: nova                               # optional per-chapter TTS overrides
---

# 第三章  借用检查器在想什么

上一章我们说，Rust 的所有权规则…
```

Everything after the frontmatter is the transcript. The first `#` heading is
the chapter title and is narrated like any other heading.

## Segments: the unit of sync

The scripts cut each chapter into **segments**. A segment is one block of
spoken text with a start and end time in the chapter audio; the web page
highlights the segment that is currently playing and lets the reader tap a
segment to seek to it.

| markdown                       | segment kind | narrated | pause after         |
| ------------------------------ | ------------ | -------- | ------------------- |
| `#`, `##`, `###` heading       | `heading`    | yes      | `pause_ms.heading`  |
| paragraph                      | `para`       | yes      | `pause_ms.paragraph`|
| `- item` / `1. item`           | `item`       | yes      | `pause_ms.paragraph`|
|   (rendered as `<p class="item" data-depth="1" data-marker="•">`, one per item, depth 2+ for nested) | | | |
| each line of a `>` blockquote  | `line`       | yes      | `pause_ms.line`     |
| fenced code, `$$…$$`, table, image, raw HTML | `display` | no | none (attached to the previous spoken segment) |
| `---`                          | `rule`       | no       | `pause_ms.rule`     |
| `<!-- … -->`                   | —            | no       | not shown either    |

Why paragraphs are the unit: paragraph-level sync needs no timing data from the
TTS provider at all (every provider works), it survives edits (only changed
paragraphs are re-synthesized thanks to the cache), and a paragraph of 60–150
汉字 is already a comfortable highlight width for following along. Keep
paragraphs short for this reason; a 400-character paragraph makes both the
prosody and the highlighting worse.

Blockquote lines are separate segments so that a poem can be read line by line
with a short breath between lines, and so the reader sees exactly which line is
being read.

## Shown-vs-spoken overrides

Sometimes the text the reader should see is not the text the narrator should
say. Wrap the two forms in double braces separated by `||`:

```
{{shown||spoken}}
```

Examples:

```markdown
于是我们得到 {{$x_t = \sqrt{\bar\alpha_t}\,x_0 + \sqrt{1-\bar\alpha_t}\,\epsilon$||x t 等于 根号 alpha bar t 乘以 x zero，加上 根号 1 减 alpha bar t 乘以 epsilon}}。

这一步会调用 {{`read_to_string`||read to string}}，把整个文件读进一个 String。

作者 {{W. B. Yeats||William Butler Yeats}} 在这里换了韵脚。
```

The shown half is rendered as Markdown (so inline `$…$` becomes math on the
page, backticks become code). The spoken half is plain text handed to the TTS
engine verbatim.

Two cheaper alternatives, in order of preference:

1. **Write it so the two forms coincide.** "x t 等于 根号 alpha bar t 乘以 x zero"
   is readable on screen as well; add the exact formula as a `$$` display block
   right after the paragraph. This is the default style for math — see
   `math-and-code.md`.
2. **Use `pronunciations` in `book.yaml`** for a symbol or term that recurs
   throughout the book. It is applied to the spoken text of every chapter before
   synthesis, so `$\bar\alpha_t$` can appear in prose many times with one
   mapping instead of many overrides.

Bare inline math (`$…$`) that has neither an override nor a pronunciation
mapping is flagged by `audiobook-stats`, because TTS engines read raw LaTeX
badly. It is still rendered on screen and spoken with the `$` stripped as a last
resort.

If you need a literal `||` inside the shown half (rare, e.g. a LaTeX norm),
write `\lVert … \rVert` instead.

## What is stripped from speech automatically

- `**bold**`, `*italic*`, `` `inline code` `` markers (the text stays)
- links: `[text](url)` → `text`
- footnote markers `[^1]`
- HTML tags inside a paragraph
- the `{{…||…}}` syntax, replaced by its spoken half

Punctuation is kept, because TTS engines use it for prosody. Prefer full Chinese
punctuation （，。？！：；） in Chinese text and put a space on both sides of
embedded English words (`这个 buffer 会被回收`); this helps both the engine and
the reader.

## The chapter manifest (`audio/<chapter>.json`)

`audiobook-synth` writes one JSON manifest per chapter next to the audio file.
`audiobook-build` consumes these; nothing else needs to. The shape, for
reference (`audio` carries the real extension — `.mp3`, `.opus` or `.m4a`):

```json
{
  "id": "03-borrow-checker",
  "title": "第三章  借用检查器在想什么",
  "audio": "03-borrow-checker.mp3",
  "duration": 612.3,
  "language": "zh",
  "segments": [
    {"i": 0, "kind": "heading", "start": 0.0,  "end": 3.1,  "html": "<h1>…</h1>", "spoken": "第三章 借用检查器在想什么"},
    {"i": 1, "kind": "para",    "start": 4.0,  "end": 21.7, "html": "<p>…</p>",   "spoken": "…"},
    {"i": 2, "kind": "display", "start": 21.7, "end": 21.7, "html": "<pre>…</pre>"},
    {"i": 3, "kind": "para",    "start": 22.3, "end": 40.0, "html": "<p>…</p>",   "spoken": "…",
     "words": [[22.3, 22.6, "所以"], [22.6, 23.0, "编译器"]]}
  ]
}
```

`words` is optional and only present when the provider returns word-level
timing; the page uses it for word-level highlighting when available and falls
back to segment-level highlighting otherwise. `display` segments carry the end
time of the preceding spoken segment so they light up together with it.
