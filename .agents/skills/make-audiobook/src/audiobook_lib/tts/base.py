"""Provider interface plus the HTTP plumbing every cloud provider shares."""

from __future__ import annotations

import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

Words = list[tuple[float, float, str]]


@dataclass
class SynthResult:
    """Whatever the provider handed back, plus the label ffmpeg needs to read it.

    `format` is `"pcm_s16le"` — headerless samples, `sample_rate` required — or
    a container/codec name (`"wav"`, `"mp3"`, `"ogg"`, …) whose bytes carry
    their own header. The cache normalizes every result to canonical FLAC on
    the way in, so a provider may return the format its API does best; ask for
    PCM or WAV where the API offers it, to avoid a lossy round trip.
    """

    data: bytes
    format: str = "pcm_s16le"
    sample_rate: int | None = None   # required for pcm_s16le
    words: Words | None = None       # (start, end, text) relative to this clip


class TTSError(RuntimeError):
    pass


class Provider(ABC):
    name: str = "base"
    max_chars: int = 2000
    price_per_1m_chars_usd: float | None = None
    price_is_approximate: bool = True
    supports_words: bool = False

    @abstractmethod
    def synthesize(self, text: str, cfg: dict[str, Any]) -> SynthResult: ...

    def list_voices(self, cfg: dict[str, Any]) -> list[tuple[str, str]] | None:
        return None

    def chunk_limit(self, cfg: dict[str, Any]) -> int:
        return int(cfg.get("max_chars") or self.max_chars)

    # -- helpers ---------------------------------------------------------

    def env(self, var: str, hint: str = "") -> str:
        val = os.environ.get(var)
        if not val:
            extra = f" ({hint})" if hint else ""
            raise TTSError(f"{self.name}: environment variable {var} is not set{extra}")
        return val

    def pcm(self, raw: bytes, src_rate: int) -> SynthResult:
        """Headerless 16-bit mono samples at `src_rate` (the usual API option)."""
        return SynthResult(data=raw, format="pcm_s16le", sample_rate=src_rate)

    def encoded(self, raw: bytes, fmt: str = "wav") -> SynthResult:
        """Bytes that carry their own header; ffmpeg probes them when decoding."""
        return SynthResult(data=raw, format=fmt)


def request_with_retries(
    method: str,
    url: str,
    *,
    provider: str,
    headers: dict[str, str] | None = None,
    json_body: Any = None,
    content: bytes | str | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 120.0,
    attempts: int = 3,
):
    """POST/GET with exponential backoff on 429/5xx/timeouts.

    The response body is surfaced on the final failure — TTS errors are almost
    always "voice not found" or "quota" and the body says which.
    """
    import httpx

    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.request(
                    method, url, headers=headers, json=json_body,
                    content=content, params=params,
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise TTSError(
                    f"{provider}: HTTP {resp.status_code}: {resp.text[:600]}"
                )
            if resp.status_code >= 400:
                raise TTSError(
                    f"{provider}: HTTP {resp.status_code}: {resp.text[:600]}"
                )
            return resp
        except TTSError as exc:
            last = exc
            retryable = " HTTP 429" in str(exc) or any(
                f" HTTP {c}" in str(exc) for c in (500, 502, 503, 504, 529)
            )
            if not retryable or attempt == attempts:
                raise
        except Exception as exc:  # timeouts, connection resets
            last = exc
            if attempt == attempts:
                raise TTSError(f"{provider}: {type(exc).__name__}: {exc}") from exc
        time.sleep(min(20.0, 2**attempt) + random.random())
    raise TTSError(f"{provider}: request failed: {last}")


def words_from_char_times(
    characters: list[str], starts: list[float], ends: list[float]
) -> Words:
    """Group per-character alignment into words.

    Latin letters/digits accumulate into a word; each CJK character is its own
    word; whitespace and punctuation are dropped (they carry no highlightable
    text).
    """
    from ..segmenter import _CJK_RE  # noqa: PLC0415  (single source of the CJK range)

    words: Words = []
    buf, buf_start, buf_end = "", 0.0, 0.0

    def flush() -> None:
        nonlocal buf
        if buf:
            words.append((buf_start, buf_end, buf))
            buf = ""

    for ch, s, e in zip(characters, starts, ends):
        if ch.isalnum() and not _CJK_RE.match(ch):
            if not buf:
                buf_start = s
            buf += ch
            buf_end = e
        elif _CJK_RE.match(ch):
            flush()
            words.append((s, e, ch))
        else:
            flush()
    flush()
    return words
