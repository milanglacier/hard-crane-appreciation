"""Azure AI Speech, real-time synthesis REST API (the default provider).

Verified against
https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech
and the SSML voice reference. No word-level timing over REST (the word-boundary
events are a WebSocket/SDK feature), so the player falls back to segment-level
highlighting — which is the design the transcript format assumes anyway.
"""

from __future__ import annotations

import re
import xml.sax.saxutils as sax
from typing import Any

from .base import Provider, SynthResult, TTSError, request_with_retries

# raw (headerless) PCM at the rates Azure offers; we ask for the closest one
_RAW_FORMATS = {
    8000: "raw-8khz-16bit-mono-pcm",
    16000: "raw-16khz-16bit-mono-pcm",
    24000: "raw-24khz-16bit-mono-pcm",
    48000: "raw-48khz-16bit-mono-pcm",
}

_DEFAULT_VOICE = {
    "zh": "zh-CN-XiaoxiaoMultilingualNeural",
    "en": "en-US-AvaMultilingualNeural",
}

_LANG_TAG = {"zh": "zh-CN", "en": "en-US"}


class AzureProvider(Provider):
    name = "azure"
    max_chars = 3000          # real limit is 64 KB of SSML / 10 min of audio
    price_per_1m_chars_usd = 16.0   # neural, pay-as-you-go; 500k chars/month free
    supports_words = False

    def __init__(self) -> None:
        self._warned_instructions = False

    # -- config ----------------------------------------------------------

    def _auth(self) -> tuple[str, str]:
        key = self.env("AZURE_SPEECH_KEY")
        region = self.env(
            "AZURE_SPEECH_REGION", "e.g. eastasia, japaneast, westus2"
        )
        return key, region.strip()

    def _voice(self, cfg: dict[str, Any]) -> str:
        if cfg.get("voice"):
            return str(cfg["voice"])
        lang = str(cfg.get("language") or "zh")[:2]
        return _DEFAULT_VOICE.get(lang, _DEFAULT_VOICE["en"])

    def _xml_lang(self, cfg: dict[str, Any]) -> str:
        if cfg.get("lang"):
            return str(cfg["lang"])
        lang = str(cfg.get("language") or "zh")[:2]
        return _LANG_TAG.get(lang, "en-US")

    def build_ssml(self, text: str, cfg: dict[str, Any]) -> str:
        body = sax.escape(text)
        style = cfg.get("style")
        if style:
            degree = cfg.get("style_degree")
            deg = f' styledegree="{float(degree)}"' if degree else ""
            body = f'<mstts:express-as style="{sax.escape(str(style))}"{deg}>{body}</mstts:express-as>'
        speed = float(cfg.get("speed") or 1.0)
        if abs(speed - 1.0) > 1e-6:
            body = f'<prosody rate="{(speed - 1.0) * 100:+.0f}%">{body}</prosody>'
        return (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="https://www.w3.org/2001/mstts" '
            f'xml:lang="{self._xml_lang(cfg)}">'
            f'<voice name="{sax.escape(self._voice(cfg))}">{body}</voice></speak>'
        )

    # -- api -------------------------------------------------------------

    def synthesize(self, text: str, cfg: dict[str, Any]) -> SynthResult:
        if cfg.get("instructions") and not self._warned_instructions:
            print("  note: azure ignores `instructions`; use `style:` (mstts express-as) instead")
            self._warned_instructions = True
        key, region = self._auth()
        want = int(cfg.get("sample_rate") or 24000)
        rate = want if want in _RAW_FORMATS else 24000
        resp = request_with_retries(
            "POST",
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
            provider=self.name,
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml; charset=utf-8",
                "X-Microsoft-OutputFormat": _RAW_FORMATS[rate],
                "User-Agent": "make-audiobook",
            },
            content=self.build_ssml(text, cfg).encode("utf-8"),
        )
        if not resp.content:
            raise TTSError("azure: empty audio response (check the voice name and region)")
        return self.pcm(resp.content, rate)

    def list_voices(self, cfg: dict[str, Any]) -> list[tuple[str, str]]:
        key, region = self._auth()
        resp = request_with_retries(
            "GET",
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
            provider=self.name,
            headers={"Ocp-Apim-Subscription-Key": key, "User-Agent": "make-audiobook"},
        )
        want = str(cfg.get("lang") or _LANG_TAG.get(str(cfg.get("language") or "")[:2], ""))
        prefix = re.split(r"[-_]", want)[0] if want else ""
        out: list[tuple[str, str]] = []
        for v in resp.json():
            if prefix and not str(v.get("Locale", "")).lower().startswith(prefix.lower()):
                continue
            desc = f"{v.get('Gender', '?')}, {v.get('VoiceType', '?')}, {v.get('LocaleName', '')}"
            styles = v.get("StyleList")
            if styles:
                desc += f", styles: {', '.join(styles[:6])}"
            out.append((str(v.get("ShortName")), desc))
        return sorted(out)
