"""Offline provider: no network, used by tests, dry runs and frontend previews.

Duration follows the same pace model as audiobook-stats, so a mock-built
site scrolls at roughly the speed the real one will. The tone is generated in
plain Python rather than with ffmpeg's `sine` source — it still goes through
the same normalization path as every other provider's audio.
"""

from __future__ import annotations

import array
import hashlib
import math
from typing import Any

from ..segmenter import count_cjk, count_latin_words
from .base import Provider, SynthResult, Words


class MockProvider(Provider):
    name = "mock"
    max_chars = 100000
    price_per_1m_chars_usd = 0.0
    supports_words = True

    def synthesize(self, text: str, cfg: dict[str, Any]) -> SynthResult:
        sr = int(cfg.get("sample_rate") or 24000)
        speed = float(cfg.get("speed") or 1.0) or 1.0
        seconds = max(
            0.25,
            (count_cjk(text) / 4.0 + count_latin_words(text) / 2.5) / speed,
        )
        n = int(seconds * sr)
        # a quiet, text-dependent tone so different segments sound different
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
        freq = 180 + (seed % 120)
        buf = array.array("h", bytes(n * 2))
        two_pi_f = 2 * math.pi * freq / sr
        for i in range(n):
            env = min(1.0, i / (0.01 * sr + 1), (n - i) / (0.01 * sr + 1))
            buf[i] = int(1200 * env * math.sin(two_pi_f * i))
        return SynthResult(
            data=buf.tobytes(), format="pcm_s16le", sample_rate=sr,
            words=_fake_words(text, seconds),
        )

    def list_voices(self, cfg: dict[str, Any]) -> list[tuple[str, str]]:
        return [("mock-a", "mock voice A"), ("mock-b", "mock voice B")]


def _fake_words(text: str, seconds: float) -> Words:
    """One fake token per CJK char / latin word, spread evenly over the clip."""
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if ch.isalnum() and ord(ch) < 0x2E80:
            buf += ch
        else:
            if buf:
                tokens.append(buf)
                buf = ""
            if not ch.isspace() and ch.strip():
                tokens.append(ch)
    if buf:
        tokens.append(buf)
    if not tokens:
        return []
    step = seconds / len(tokens)
    return [(round(i * step, 3), round((i + 1) * step, 3), t) for i, t in enumerate(tokens)]
