"""ElevenLabs text-to-speech with character-level timestamps.

Verified against elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps.
This is the only provider here that returns alignment, so it is the one that
gives the player word-level highlighting.
"""

from __future__ import annotations

from typing import Any

from .base import (
    Provider,
    SynthResult,
    TTSError,
    request_with_retries,
    words_from_char_times,
)

_BASE = "https://api.elevenlabs.io"
_ALLOWED_RATES = (8000, 16000, 22050, 24000, 32000, 44100, 48000)


class ElevenLabsProvider(Provider):
    name = "elevenlabs"
    max_chars = 3000     # multilingual_v2 allows 10000, eleven_v3 5000; stay conservative
    price_per_1m_chars_usd = 150.0   # ≈$0.15/1k chars, plan-dependent
    supports_words = True

    def __init__(self) -> None:
        self._voice_ids: dict[str, str] = {}

    def _key(self) -> str:
        return self.env("ELEVENLABS_API_KEY")

    def _resolve_voice(self, voice: str) -> str:
        """Accept either a voice id or a human voice name."""
        if not voice:
            return "21m00Tcm4TlvDq8ikWAM"  # Rachel, the account-wide default
        if len(voice) >= 20 and " " not in voice:
            return voice
        if voice in self._voice_ids:
            return self._voice_ids[voice]
        for v in self._fetch_voices():
            self._voice_ids[str(v.get("name"))] = str(v.get("voice_id"))
        if voice not in self._voice_ids:
            raise TTSError(
                f"elevenlabs: no voice named {voice!r}; run --list-voices to see the options"
            )
        return self._voice_ids[voice]

    def _fetch_voices(self) -> list[dict[str, Any]]:
        for path in ("/v2/voices", "/v1/voices"):
            try:
                resp = request_with_retries(
                    "GET", f"{_BASE}{path}", provider=self.name,
                    headers={"xi-api-key": self._key()},
                )
            except TTSError:
                continue
            return list(resp.json().get("voices") or [])
        raise TTSError("elevenlabs: could not list voices")

    def synthesize(self, text: str, cfg: dict[str, Any]) -> SynthResult:
        want = int(cfg.get("sample_rate") or 24000)
        rate = want if want in _ALLOWED_RATES else 24000
        voice_id = self._resolve_voice(str(cfg.get("voice") or ""))
        body: dict[str, Any] = {
            "text": text,
            "model_id": cfg.get("model") or "eleven_multilingual_v2",
        }
        settings = dict(cfg.get("voice_settings") or {})
        speed = float(cfg.get("speed") or 1.0)
        if abs(speed - 1.0) > 1e-6:
            settings.setdefault("speed", speed)
        if settings:
            body["voice_settings"] = settings
        if cfg.get("lang"):
            body["language_code"] = cfg["lang"]
        if isinstance(cfg.get("extra"), dict):
            body.update(cfg["extra"])

        resp = request_with_retries(
            "POST",
            f"{_BASE}/v1/text-to-speech/{voice_id}/with-timestamps",
            provider=self.name,
            headers={"xi-api-key": self._key(), "Content-Type": "application/json"},
            params={"output_format": f"pcm_{rate}"},
            json_body=body,
        )
        data = resp.json()
        b64 = data.get("audio_base64")
        if not b64:
            raise TTSError(f"elevenlabs: no audio in response: {str(data)[:400]}")
        import base64

        result = self.pcm(base64.b64decode(b64), rate)
        align = data.get("alignment") or data.get("normalized_alignment") or {}
        chars = align.get("characters")
        if chars:
            # alignment is in seconds, so it survives normalization
            result.words = words_from_char_times(
                chars,
                align.get("character_start_times_seconds") or [],
                align.get("character_end_times_seconds") or [],
            )
        return result

    def list_voices(self, cfg: dict[str, Any]) -> list[tuple[str, str]]:
        out = []
        for v in self._fetch_voices():
            labels = v.get("labels") or {}
            desc = ", ".join(
                str(labels[k]) for k in ("gender", "accent", "language", "use_case")
                if labels.get(k)
            )
            out.append((f"{v.get('name')} ({v.get('voice_id')})", desc or str(v.get("category", ""))))
        return out
