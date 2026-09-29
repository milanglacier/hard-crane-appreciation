"""OpenAI /v1/audio/speech.

Verified against developers.openai.com/api/docs/api-reference/audio/createSpeech
(platform.openai.com now 301s there). `response_format: "pcm"` is raw 24 kHz
signed 16-bit little-endian mono — no RIFF header — which is exactly what we
want for gapless concatenation.
"""

from __future__ import annotations

import os
from typing import Any

from .base import Provider, SynthResult, TTSError, request_with_retries

_VOICES = [
    ("alloy", "neutral"), ("ash", "warm"), ("ballad", "expressive (gpt-4o-mini-tts)"),
    ("coral", "bright"), ("echo", "calm"), ("fable", "storyteller"),
    ("onyx", "deep"), ("nova", "energetic"), ("sage", "measured"),
    ("shimmer", "light"), ("verse", "expressive (gpt-4o-mini-tts)"),
    ("marin", "newer (gpt-4o-mini-tts)"), ("cedar", "newer (gpt-4o-mini-tts)"),
]

# rough $ per 1M input characters
_PRICES = {"tts-1": 15.0, "tts-1-hd": 30.0, "gpt-4o-mini-tts": 0.60}

# `instructions` only steers the newer model
_NO_INSTRUCTIONS = {"tts-1", "tts-1-hd"}


class OpenAIProvider(Provider):
    name = "openai"
    max_chars = 4096
    price_per_1m_chars_usd = 0.60   # gpt-4o-mini-tts text side (~$0.015/min)
    supports_words = False

    def price_for(self, cfg: dict[str, Any]) -> float | None:
        return _PRICES.get(str(cfg.get("model") or "gpt-4o-mini-tts"))

    def synthesize(self, text: str, cfg: dict[str, Any]) -> SynthResult:
        key = self.env("OPENAI_API_KEY")
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        model = str(cfg.get("model") or "gpt-4o-mini-tts")
        body: dict[str, Any] = {
            "model": model,
            "voice": cfg.get("voice") or "alloy",
            "input": text,
            "response_format": "pcm",
            "speed": float(cfg.get("speed") or 1.0),
        }
        if cfg.get("instructions") and model not in _NO_INSTRUCTIONS:
            body["instructions"] = cfg["instructions"]
        if isinstance(cfg.get("extra"), dict):
            body.update(cfg["extra"])

        resp = request_with_retries(
            "POST",
            f"{base}/v1/audio/speech",
            provider=self.name,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body=body,
        )
        if not resp.content:
            raise TTSError("openai: empty audio response")
        return self.pcm(resp.content, 24000)

    def list_voices(self, cfg: dict[str, Any]) -> list[tuple[str, str]]:
        return list(_VOICES)
