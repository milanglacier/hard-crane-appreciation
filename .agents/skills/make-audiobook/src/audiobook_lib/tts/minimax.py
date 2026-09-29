"""MiniMax T2A v2 (HTTP).

Verified against https://platform.minimax.io/docs/api-reference/speech-t2a-http .
The current docs authenticate with a bearer token alone; older account keys also
want `?GroupId=`, so MINIMAX_GROUP_ID is honoured when present but not required.
"""

from __future__ import annotations

import os
from typing import Any

from .base import Provider, SynthResult, TTSError, request_with_retries

_ALLOWED_RATES = (8000, 16000, 22050, 24000, 32000, 44100)

# A handful of built-in ids; the full list lives at
# https://platform.minimax.io/docs/api-reference/speech-voice-list
_VOICES = [
    ("male-qn-jingying", "青年男声・精英 (Chinese narrator)"),
    ("male-qn-qingse", "青年男声・青涩 (Chinese)"),
    ("female-shaonv", "少女音 (Chinese)"),
    ("female-yujie", "御姐音 (Chinese)"),
    ("presenter_male", "male presenter"),
    ("presenter_female", "female presenter"),
    ("audiobook_male_1", "audiobook male"),
    ("audiobook_female_1", "audiobook female"),
    ("English_expressive_narrator", "expressive English narrator"),
]


class MiniMaxProvider(Provider):
    name = "minimax"
    max_chars = 3000          # hard limit is 10000 per call
    price_per_1m_chars_usd = 100.0   # hd tier, approximate
    supports_words = False

    def _base(self) -> str:
        return os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.io").rstrip("/")

    def synthesize(self, text: str, cfg: dict[str, Any]) -> SynthResult:
        key = self.env("MINIMAX_API_KEY")
        want = int(cfg.get("sample_rate") or 24000)
        rate = want if want in _ALLOWED_RATES else 24000
        body: dict[str, Any] = {
            "model": cfg.get("model") or "speech-2.8-hd",
            "text": text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": {
                "voice_id": cfg.get("voice") or "male-qn-jingying",
                "speed": float(cfg.get("speed") or 1.0),
                "vol": float(cfg.get("vol") or 1.0),
                "pitch": int(cfg.get("pitch") or 0),
            },
            "audio_setting": {"sample_rate": rate, "format": "pcm", "channel": 1},
        }
        if cfg.get("emotion"):
            body["voice_setting"]["emotion"] = cfg["emotion"]
        if cfg.get("language_boost"):
            body["language_boost"] = cfg["language_boost"]
        if cfg.get("pronunciation_dict"):
            body["pronunciation_dict"] = {"tone": list(cfg["pronunciation_dict"])}
        if isinstance(cfg.get("extra"), dict):
            body.update(cfg["extra"])

        params = {}
        group = os.environ.get("MINIMAX_GROUP_ID")
        if group:
            params["GroupId"] = group

        resp = request_with_retries(
            "POST",
            f"{self._base()}/v1/t2a_v2",
            provider=self.name,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json_body=body,
            params=params or None,
        )
        data = resp.json()
        status = (data.get("base_resp") or {}).get("status_code", 0)
        if status:
            msg = (data.get("base_resp") or {}).get("status_msg", "")
            hint = ""
            if status in (1004, 1008, 2013):
                hint = (
                    " — MINIMAX_API_KEY must match MINIMAX_BASE_URL: keys from "
                    "api.minimax.io (global) and api.minimaxi.com (mainland) are "
                    "not interchangeable"
                )
            raise TTSError(f"minimax: status {status}: {msg}{hint}")
        hexed = (data.get("data") or {}).get("audio")
        if not hexed:
            raise TTSError(f"minimax: no audio in response: {str(data)[:400]}")
        raw = bytes.fromhex(hexed)
        src_rate = int((data.get("extra_info") or {}).get("audio_sample_rate") or rate)
        return self.pcm(raw, src_rate)

    def list_voices(self, cfg: dict[str, Any]) -> list[tuple[str, str]]:
        return list(_VOICES)
