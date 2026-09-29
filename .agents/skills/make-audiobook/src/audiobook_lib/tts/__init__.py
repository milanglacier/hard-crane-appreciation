"""Provider registry."""

from __future__ import annotations

from .base import Provider, SynthResult, TTSError, Words

_FACTORIES = {
    "azure": ("azure", "AzureProvider"),
    "openai": ("openai", "OpenAIProvider"),
    "elevenlabs": ("elevenlabs", "ElevenLabsProvider"),
    "gemini": ("gemini", "GeminiProvider"),
    "minimax": ("minimax", "MiniMaxProvider"),
    "qwen": ("qwen", "QwenProvider"),
    "mock": ("mock", "MockProvider"),
}

KNOWN = tuple(sorted(_FACTORIES))

_cache: dict[str, Provider] = {}


def get_provider(name: str) -> Provider:
    """Providers are cached so per-instance state (voice-id lookups, one-time
    notices) survives across the segments of a chapter."""
    key = (name or "").strip().lower()
    if key not in _FACTORIES:
        raise SystemExit(
            f"unknown tts provider {name!r}; known providers: {', '.join(KNOWN)}"
        )
    if key not in _cache:
        module_name, cls_name = _FACTORIES[key]
        module = __import__(f"{__name__}.{module_name}", fromlist=[cls_name])
        _cache[key] = getattr(module, cls_name)()
    return _cache[key]


def price_per_1m(provider: Provider, cfg: dict) -> float | None:
    fn = getattr(provider, "price_for", None)
    return fn(cfg) if fn else provider.price_per_1m_chars_usd


__all__ = ["Provider", "SynthResult", "TTSError", "Words", "get_provider", "KNOWN", "price_per_1m"]
