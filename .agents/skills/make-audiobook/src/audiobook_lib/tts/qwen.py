"""Alibaba Model Studio (DashScope) Qwen3-TTS.

Verified against https://www.alibabacloud.com/help/en/model-studio/qwen-tts .
The call returns a short-lived URL rather than inline audio, so the clip is
fetched in a second request.
"""

from __future__ import annotations

import os
from typing import Any

from .base import Provider, SynthResult, TTSError, request_with_retries

_VOICES = [
    ("Cherry", "female, warm, multilingual (default)"),
    ("Ethan", "male, standard Mandarin narrator"),
    ("Serena", "female, calm"),
    ("Chelsie", "female, bright"),
    ("Jennifer", "female, English"),
    ("Ryan", "male, English"),
    ("Dylan", "male, Beijing dialect"),
    ("Jada", "female, Shanghai dialect"),
    ("Sunny", "female, Sichuan dialect"),
]

_LANGUAGE_TYPE = {"zh": "Chinese", "en": "English"}


class QwenProvider(Provider):
    name = "qwen"
    max_chars = 2000
    price_per_1m_chars_usd = 15.0   # approximate
    supports_words = False

    def _base(self) -> str:
        return os.environ.get(
            "DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com"
        ).rstrip("/")

    def synthesize(self, text: str, cfg: dict[str, Any]) -> SynthResult:
        key = self.env("DASHSCOPE_API_KEY")
        lang = str(cfg.get("language") or "zh")[:2]
        body: dict[str, Any] = {
            "model": cfg.get("model") or "qwen3-tts-flash",
            "input": {
                "text": text,
                "voice": cfg.get("voice") or "Cherry",
                "language_type": cfg.get("language_type") or _LANGUAGE_TYPE.get(lang, "Auto"),
            },
        }
        if cfg.get("instructions"):
            # only the instruct model reads this; harmless elsewhere
            body["input"]["instruction"] = cfg["instructions"]
        if isinstance(cfg.get("extra"), dict):
            body.update(cfg["extra"])

        resp = request_with_retries(
            "POST",
            f"{self._base()}/api/v1/services/aigc/multimodal-generation/generation",
            provider=self.name,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body=body,
        )
        data = resp.json()
        if data.get("code"):
            raise TTSError(f"qwen: {data.get('code')}: {data.get('message', '')}")
        url = (((data.get("output") or {}).get("audio")) or {}).get("url")
        if not url:
            raise TTSError(f"qwen: no audio url in response: {str(data)[:400]}")
        clip = request_with_retries("GET", url, provider=self.name)
        # a WAV download; ffmpeg reads the header, so nothing is stripped here
        return self.encoded(clip.content, "wav")

    def list_voices(self, cfg: dict[str, Any]) -> list[tuple[str, str]]:
        return list(_VOICES)
