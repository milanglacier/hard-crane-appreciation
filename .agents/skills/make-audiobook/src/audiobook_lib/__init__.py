"""Shared library behind the make-audiobook commands.

All audio processing (decoding provider output, resampling, silence,
concatenation, loudness normalization, encoding) is done by ffmpeg; Python only
orchestrates and reads WAV headers for sample-exact segment timing.
"""

__all__ = ["audio", "book", "cache", "segmenter", "tts"]
