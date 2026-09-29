"""Markdown chapter -> ordered list of Segment.

The contract is references/transcript-format.md: some blocks are spoken and
shown, some are shown only, some are neither. Everything here exists to make
that split, and to derive a clean spoken string for the TTS engine.

Two rendering choices worth knowing about:

* a list item renders as ``<p class="item" data-depth="N">`` rather than ``<li>``
  so that each segment is a self-contained, independently highlightable block
  (the player inserts segments one by one; a bare ``<li>`` outside a list is
  awkward). Nesting survives as ``data-depth``.
* inline and display math is passed through untouched (only ``&`` / ``<`` are
  HTML-escaped) so client-side KaTeX sees the original LaTeX.
"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

from markdown_it import MarkdownIt
from markdown_it.token import Token

Kind = Literal["heading", "para", "item", "line", "display", "rule"]

CJK_PER_SEC = 4.0
LATIN_WORDS_PER_SEC = 2.5

_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002ffff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’._-]*")


@dataclass
class Segment:
    i: int
    kind: Kind
    html: str
    spoken: str | None
    level: int | None = None
    warnings: list[str] = field(default_factory=list)


def make_md() -> MarkdownIt:
    return MarkdownIt("commonmark").enable("table").enable("strikethrough")


# --------------------------------------------------------------------------
# {{shown||spoken}} overrides and inline-math / code-span protection
# --------------------------------------------------------------------------

# Private-use sentinels: markdown-it rewrites NUL to U+FFFD (CommonMark requires
# it), so a \x00-based placeholder would not survive renderInline.
_PLACEHOLDER = "\ue000{}\ue001"
_PLACEHOLDER_RE = re.compile(r"\ue000(\d+)\ue001")


def _scan_spans(text: str) -> list[tuple[int, int]]:
    """Byte ranges of inline code spans and inline ``$…$`` math.

    ``{{`` and ``||`` inside these must not be treated as syntax — a code span
    may legitimately contain ``{{`` and a LaTeX norm may contain ``||``.
    """
    spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "`":
            j = i
            while j < n and text[j] == "`":
                j += 1
            fence = text[i:j]
            close = text.find(fence, j)
            while close != -1 and close + len(fence) < n and text[close + len(fence)] == "`":
                close = text.find(fence, close + len(fence) + 1)
            if close == -1:
                i = j
                continue
            spans.append((i, close + len(fence)))
            i = close + len(fence)
            continue
        if c == "$":
            close = text.find("$", i + 1)
            # a lone `$` (a price, a shell prompt) should not open a math span
            if close != -1 and close > i + 1 and "\n" not in text[i:close]:
                spans.append((i, close + 1))
                i = close + 1
                continue
        i += 1
    return spans


def _in_spans(pos: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


@dataclass
class _Split:
    shown: str
    spoken: str
    spoken_parts: list[str]  # verbatim spoken halves, in order
    unbalanced: bool


def split_overrides(text: str) -> _Split:
    """Split ``{{shown||spoken}}`` into the shown source and the spoken source.

    The spoken half is kept verbatim (it is plain text by definition), so the
    caller can shield it from the markdown-stripping pass.
    """
    spans = _scan_spans(text)
    shown_out: list[str] = []
    spoken_out: list[str] = []
    parts: list[str] = []
    unbalanced = False
    i, n = 0, len(text)
    while i < n:
        if text.startswith("{{", i) and not _in_spans(i, spans):
            end = text.find("}}", i + 2)
            if end == -1:
                unbalanced = True
                shown_out.append(text[i:])
                spoken_out.append(text[i:])
                break
            inner = text[i + 2 : end]
            inner_spans = _scan_spans(inner)
            sep = -1
            k = 0
            while True:
                k = inner.find("||", k)
                if k == -1:
                    break
                if not _in_spans(k, inner_spans):
                    sep = k
                    break
                k += 2
            if sep == -1:
                unbalanced = True
                shown_out.append(inner)
                spoken_out.append(inner)
            else:
                shown_half = inner[:sep]
                spoken_half = inner[sep + 2 :]
                shown_out.append(shown_half)
                spoken_out.append(_PLACEHOLDER.format(len(parts)))
                parts.append(spoken_half)
            i = end + 2
            continue
        if text.startswith("}}", i) and not _in_spans(i, spans):
            unbalanced = True
        shown_out.append(text[i])
        spoken_out.append(text[i])
        i += 1
    return _Split("".join(shown_out), "".join(spoken_out), parts, unbalanced)


# --------------------------------------------------------------------------
# spoken text derivation
# --------------------------------------------------------------------------

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)")
_REF_LINK_RE = re.compile(r"\[([^\]]*)\]\[[^\]]*\]")
_FOOTNOTE_RE = re.compile(r"\[\^[^\]]*\]")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_EMPHASIS_RE = re.compile(r"(\*{1,3}|~~)")
# `_` is emphasis only when it is not inside a word (CommonMark), and an
# intra-word `_` is usually part of an identifier we want to keep.
_UNDERSCORE_RE = re.compile(r"(?<![A-Za-z0-9])_{1,3}|_{1,3}(?![A-Za-z0-9])")
_MD_ESCAPE_RE = re.compile(r"\\([^A-Za-z0-9\s])")
_INLINE_MATH_RE = re.compile(r"\$([^$\n]+)\$")
_WS_RE = re.compile(r"[ \t\r\f\v]+")


def _say_math(latex: str) -> str:
    """Last-resort reading of bare inline math: drop the LaTeX punctuation.

    `\\sigma_t` becomes "sigma t" rather than "sigmat" or "\\sigma_t". The
    author is warned either way; this only keeps the fallback intelligible.
    """
    return re.sub(r"[\\_^{}]+", " ", latex)


def apply_pronunciations(text: str, mapping: dict[str, str] | None) -> str:
    """Literal replacement, longest key first so ``$\\alpha_t$`` beats ``$\\alpha$``."""
    if not mapping:
        return text
    for key in sorted(mapping, key=len, reverse=True):
        if key:
            text = text.replace(key, str(mapping[key]))
    return text


def spoken_from_source(
    source: str, pronunciations: dict[str, str] | None = None
) -> tuple[str, list[str]]:
    """Turn the markdown source of one block into what the narrator says."""
    warnings: list[str] = []
    split = split_overrides(source)
    if split.unbalanced:
        warnings.append("unbalanced {{ }} override")

    text = split.spoken
    # Pronunciations run on the source form first (so a key may be `$\bar\alpha_t$`,
    # i.e. it can match inline math before the `$` are stripped) and once more at
    # the end (so it can also match the plain spoken form).
    text = apply_pronunciations(text, pronunciations)
    text = _HTML_COMMENT_RE.sub("", text)
    text = _IMAGE_RE.sub("", text)
    text = _FOOTNOTE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _REF_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("`", "")

    if _INLINE_MATH_RE.search(text):
        warnings.append("bare inline $…$ math spoken with the $ stripped")
        text = _INLINE_MATH_RE.sub(lambda m: _say_math(m.group(1)), text)

    text = _EMPHASIS_RE.sub("", text)
    text = _UNDERSCORE_RE.sub("", text)
    text = _MD_ESCAPE_RE.sub(r"\1", text)
    text = text.replace("\\", " ")

    # put the verbatim spoken halves back, untouched by any of the above
    def _restore(m: re.Match[str]) -> str:
        return split.spoken_parts[int(m.group(1))]

    text = _PLACEHOLDER_RE.sub(_restore, text)
    text = apply_pronunciations(text, pronunciations)

    text = text.replace("\n", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text, warnings


# --------------------------------------------------------------------------
# html rendering
# --------------------------------------------------------------------------


def _escape_math(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;")


def _render_inline(md: MarkdownIt, source: str) -> str:
    """Render inline markdown, keeping ``$…$`` math byte-for-byte."""
    spans = [(a, b) for a, b in _scan_spans(source) if source[a] == "$"]
    parts: list[str] = []
    out: list[str] = []
    last = 0
    for a, b in spans:
        out.append(source[last:a])
        out.append(_PLACEHOLDER.format(len(parts)))
        parts.append(source[a:b])
        last = b
    out.append(source[last:])
    rendered = md.renderInline("".join(out)).strip()
    rendered = _HTML_COMMENT_RE.sub("", rendered)
    return _PLACEHOLDER_RE.sub(lambda m: _escape_math(parts[int(m.group(1))]), rendered)


def _render_tokens(md: MarkdownIt, tokens: list[Token]) -> str:
    return md.renderer.render(tokens, md.options, {}).strip()


# --------------------------------------------------------------------------
# the walk
# --------------------------------------------------------------------------

_DISPLAY_MATH_RE = re.compile(r"^\$\$.*\$\$$", re.S)
_ONLY_IMAGE_RE = re.compile(r"^(?:!\[[^\]]*\]\([^)]*\)\s*)+$")


class _Builder:
    def __init__(self, md: MarkdownIt, pronunciations: dict[str, str] | None):
        self.md = md
        self.pron = pronunciations
        self.segments: list[Segment] = []

    def add(self, kind: Kind, html: str, spoken: str | None, level: int | None = None,
            warnings: list[str] | None = None) -> None:
        if spoken is not None and not spoken.strip():
            spoken = None if kind in ("display", "rule") else ""
        if kind not in ("display", "rule") and not spoken:
            return  # a block that says nothing is not a segment
        self.segments.append(
            Segment(len(self.segments), kind, html, spoken, level, list(warnings or []))
        )

    def spoken_block(self, kind: Kind, source: str, level: int | None = None) -> None:
        spoken, warns = spoken_from_source(source, self.pron)
        split = split_overrides(source)
        if kind == "heading":
            html = f"<h{level}>{_render_inline(self.md, split.shown)}</h{level}>"
        elif kind == "line":
            html = f'<p class="line">{_render_inline(self.md, split.shown)}</p>'
        else:
            html = f"<p>{_render_inline(self.md, split.shown)}</p>"
        self.add(kind, html, spoken, level, warns)

    def item_block(self, source: str, depth: int, marker: str) -> None:
        spoken, warns = spoken_from_source(source, self.pron)
        split = split_overrides(source)
        html = (
            f'<p class="item" data-depth="{depth}" data-marker="{html_mod.escape(marker, quote=True)}">'
            f"{_render_inline(self.md, split.shown)}</p>"
        )
        self.add("item", html, spoken, None, warns)


def _matching_close(tokens: list[Token], start: int) -> int:
    """Index of the token closing the container opened at `start`."""
    depth = 0
    for j in range(start, len(tokens)):
        if tokens[j].nesting == 1:
            depth += 1
        elif tokens[j].nesting == -1:
            depth -= 1
            if depth == 0:
                return j
    return len(tokens) - 1


def _walk(b: _Builder, tokens: list[Token], i: int, end: int, depth: int, in_quote: bool) -> None:
    while i < end:
        t = tokens[i]
        ty = t.type

        if ty == "heading_open":
            inline = tokens[i + 1]
            b.spoken_block("heading", inline.content, level=int(t.tag[1:]))
            i = _matching_close(tokens, i) + 1

        elif ty == "paragraph_open":
            inline = tokens[i + 1]
            src = inline.content
            stripped = src.strip()
            if _DISPLAY_MATH_RE.match(stripped):
                b.add("display", f'<div class="math">{_escape_math(stripped)}</div>', None)
            elif _ONLY_IMAGE_RE.match(stripped):
                b.add("display", f"<p>{_render_inline(b.md, stripped)}</p>", None)
            elif in_quote:
                for line in src.split("\n"):
                    if line.strip():
                        b.spoken_block("line", line)
            else:
                b.spoken_block("para", src)
            i = _matching_close(tokens, i) + 1

        elif ty == "blockquote_open":
            close = _matching_close(tokens, i)
            _walk(b, tokens, i + 1, close, depth, True)
            i = close + 1

        elif ty in ("bullet_list_open", "ordered_list_open"):
            close = _matching_close(tokens, i)
            ordered = ty == "ordered_list_open"
            n = int(t.attrGet("start") or 1) if ordered else 0
            j = i + 1
            while j < close:
                if tokens[j].type == "list_item_open":
                    item_close = _matching_close(tokens, j)
                    marker = f"{n}." if ordered else "•"
                    _walk_item(b, tokens, j + 1, item_close, depth + 1, marker)
                    n += 1
                    j = item_close + 1
                else:
                    j += 1
            i = close + 1

        elif ty in ("fence", "code_block"):
            b.add("display", _render_tokens(b.md, [t]), None)
            i += 1

        elif ty == "html_block":
            body = t.content.strip()
            if not _HTML_COMMENT_RE.sub("", body).strip():
                i += 1  # a pure comment block: neither shown nor spoken
                continue
            b.add("display", _render_tokens(b.md, [t]), None)
            i += 1

        elif ty == "table_open":
            close = _matching_close(tokens, i)
            b.add("display", _render_tokens(b.md, tokens[i : close + 1]), None)
            i = close + 1

        elif ty == "hr":
            b.add("rule", "<hr>", None)
            i += 1

        elif t.nesting == 1:
            close = _matching_close(tokens, i)
            _walk(b, tokens, i + 1, close, depth, in_quote)
            i = close + 1

        else:
            i += 1


def _walk_item(b: _Builder, tokens: list[Token], i: int, end: int, depth: int, marker: str) -> None:
    """A list item: its first paragraph is the item text, nested blocks recurse."""
    first = True
    while i < end:
        t = tokens[i]
        if t.type == "paragraph_open":
            b.item_block(tokens[i + 1].content, depth, marker if first else "")
            first = False
            i = _matching_close(tokens, i) + 1
        elif t.type == "inline":
            b.item_block(t.content, depth, marker if first else "")
            first = False
            i += 1
        else:
            before = len(b.segments)
            _walk(b, tokens, i, i + 1 if t.nesting == 0 else _matching_close(tokens, i) + 1,
                  depth, False)
            if len(b.segments) > before:
                first = False
            i = i + 1 if t.nesting == 0 else _matching_close(tokens, i) + 1


def segment_markdown(
    text: str, pronunciations: dict[str, str] | None = None, md: MarkdownIt | None = None
) -> list[Segment]:
    """Segment one chapter body (frontmatter already stripped; tolerant if not)."""
    text = strip_frontmatter(text)[1]
    md = md or make_md()
    b = _Builder(md, pronunciations)
    tokens = md.parse(text)
    _walk(b, tokens, 0, len(tokens), 0, False)
    for n, seg in enumerate(b.segments):
        seg.i = n
    return b.segments


_FRONTMATTER_RE = re.compile(r"\A﻿?---\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)


def strip_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_yaml, body). Empty yaml when there is none."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return "", text.lstrip("﻿")
    return m.group(1), text[m.end() :]


# --------------------------------------------------------------------------
# pace model (references/writing-guide.md §6)
# --------------------------------------------------------------------------


def count_cjk(text: str) -> int:
    return len(_CJK_RE.findall(text))


def count_latin_words(text: str) -> int:
    return len(_LATIN_WORD_RE.findall(text))


def estimate_seconds(spoken: str, pause_ms: float = 0.0) -> float:
    """4 CJK chars/s, 2.5 latin words/s, plus the pause that follows the segment."""
    if not spoken:
        return pause_ms / 1000.0
    return (
        count_cjk(spoken) / CJK_PER_SEC
        + count_latin_words(spoken) / LATIN_WORDS_PER_SEC
        + pause_ms / 1000.0
    )


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split over-long spoken text at sentence punctuation, then at any space."""
    if len(text) <= max_chars:
        return [text]
    breaks = "。！？；!?;\n"
    soft = "，,、:：) ）"
    chunks: list[str] = []
    rest = text
    while len(rest) > max_chars:
        window = rest[:max_chars]
        cut = max((window.rfind(c) for c in breaks), default=-1)
        if cut < max_chars // 3:
            cut = max((window.rfind(c) for c in soft), default=-1)
        if cut < max_chars // 3:
            cut = max_chars - 1
        chunks.append(rest[: cut + 1].strip())
        rest = rest[cut + 1 :].lstrip()
    if rest:
        chunks.append(rest)
    return [c for c in chunks if c]
