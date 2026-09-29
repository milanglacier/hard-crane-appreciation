"""Gemini TTS via the generateContent endpoint.

Verified against ai.google.dev/gemini-api/docs/speech-generation. Google has
since introduced a newer `POST /v1beta/interactions` front door (the
`generateContent` path is documented as legacy but still fully supported); the
older path is used here because it is the one with a stable, documented response
shape for single-speaker audio: candidates[0].content.parts[0].inlineData.data,
base64 LINEAR16 PCM at 24 kHz mono (mimeType "audio/L16;codec=pcm;rate=24000").
"""

from __future__ import annotations

import base64
import re
from typing import Any

from .base import Provider, SynthResult, TTSError, request_with_retries

_BASE = "https://generativelanguage.googleapis.com/v1beta"

_VOICES = [
    ("Zephyr", "bright"), ("Puck", "upbeat"), ("Charon", "informative"),
    ("Kore", "firm (default)"), ("Fenrir", "excitable"), ("Leda", "youthful"),
    ("Orus", "firm"), ("Aoede", "breezy"), ("Callirrhoe", "easy-going"),
    ("Autonoe", "bright"), ("Enceladus", "breathy"), ("Iapetus", "clear"),
    ("Umbriel", "easy-going"), ("Algieba", "smooth"), ("Despina", "smooth"),
    ("Erinome", "clear"), ("Algenib", "gravelly"), ("Rasalgethi", "informative"),
    ("Laomedeia", "upbeat"), ("Achernar", "soft"), ("Alnilam", "firm"),
    ("Schedar", "even"), ("Gacrux", "mature"), ("Pulcherrima", "forward"),
    ("Achird", "friendly"), ("Zubenelgenubi", "casual"), ("Vindemiatrix", "gentle"),
    ("Sadachbia", "lively"), ("Sadaltager", "knowledgeable"), ("Sulafat", "warm"),
]

_RATE_RE = re.compile(r"rate=(\d+)")


class GeminiProvider(Provider):
    name = "gemini"
    max_chars = 4000      # the context window is large; short clips are more reliable
    price_per_1m_chars_usd = 0.50   # approximate: flash-tts text side, audio billed per token
    supports_words = False

    def synthesize(self, text: str, cfg: dict[str, Any]) -> SynthResult:
        key = self.env("GEMINI_API_KEY")
        model = str(cfg.get("model") or "gemini-2.5-flash-preview-tts")
        prompt = text
        if cfg.get("instructions"):
            prompt = f"{cfg['instructions']}\n\n{text}"
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": cfg.get("voice") or "Kore"}
                    }
                },
            },
        }
        if isinstance(cfg.get("extra"), dict):
            body.update(cfg["extra"])

        resp = request_with_retries(
            "POST",
            f"{_BASE}/models/{model}:generateContent",
            provider=self.name,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json_body=body,
        )
        data = resp.json()
        try:
            part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
        except (KeyError, IndexError, TypeError):
            raise TTSError(f"gemini: no audio in response: {str(data)[:400]}") from None
        raw = base64.b64decode(part["data"])
        m = _RATE_RE.search(str(part.get("mimeType", "")))
        return self.pcm(raw, int(m.group(1)) if m else 24000)

    def list_voices(self, cfg: dict[str, Any]) -> list[tuple[str, str]]:
        return list(_VOICES)
