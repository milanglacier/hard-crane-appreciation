"""Offline provider checks plus the ffmpeg-backed audio layer.

No network call is made: cloud providers are only asked for metadata and for a
synthesis they are expected to refuse without credentials. The tests that touch
ffmpeg are skipped when it is not on PATH.
"""

from __future__ import annotations

import os
import shutil
import wave
from pathlib import Path

import pytest

from audiobook_lib import audio as A
from audiobook_lib.book import Book, effective_tts
from audiobook_lib.tts import KNOWN, TTSError, get_provider, price_per_1m

CFG = {
    "language": "zh",
    "sample_rate": 24000,
    "speed": 1.1,
    "instructions": "沉稳",
    "style": "narration-relaxed",
}
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch):
    """Make sure no real key is in the environment: nothing may reach a network."""
    for var in list(os.environ):
        if any(k in var for k in ("API_KEY", "SPEECH_KEY", "GROUP_ID", "DASHSCOPE")):
            monkeypatch.delenv(var, raising=False)


# -- providers --------------------------------------------------------------


def test_registry_lists_the_known_providers():
    assert set(KNOWN) == {
        "azure", "elevenlabs", "gemini", "minimax", "mock", "openai", "qwen",
    }


@pytest.mark.parametrize("name", KNOWN)
def test_provider_imports_and_reports_metadata(name):
    provider = get_provider(name)
    assert provider.chunk_limit(CFG) > 0
    price = price_per_1m(provider, CFG)
    assert price is None or price >= 0
    assert isinstance(provider.supports_words, bool)


@pytest.mark.parametrize("name", [n for n in KNOWN if n != "mock"])
def test_cloud_provider_refuses_without_credentials(name):
    with pytest.raises(TTSError):
        get_provider(name).synthesize("测试", CFG)


def test_mock_provider_synthesizes_offline():
    result = get_provider("mock").synthesize("一二三四五", CFG)
    assert (result.format, result.sample_rate) == ("pcm_s16le", 24000)
    assert len(result.data) > 0
    assert result.words  # the mock reports word timings


def test_azure_ssml_escapes_and_uses_the_config():
    azure = get_provider("azure")
    ssml = azure.build_ssml('你好 <world> & "友"', CFG)
    assert "&lt;world&gt;" in ssml and "&amp;" in ssml
    assert "<world>" not in ssml
    assert 'xml:lang="zh' in ssml
    plain = azure.build_ssml("plain", {"language": "en", "speed": 1.0})
    assert "plain" in plain and 'xml:lang="en' in plain


def test_unknown_provider_exits():
    with pytest.raises(SystemExit):
        get_provider("nope")


# -- format -> ffmpeg args --------------------------------------------------


def test_encode_args_per_format():
    assert A.encode_args("mp3", 24000, 96, True) == [
        "-af", LOUDNORM, "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "96k",
    ]
    assert A.encode_args("mp3", 24000, 96, False) == [
        "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "96k",
    ]
    assert A.encode_args("opus", 24000, 48, True) == [
        "-af", LOUDNORM, "-ar", "24000", "-ac", "1", "-c:a", "libopus", "-b:a", "48k",
    ]
    assert A.encode_args("aac", 22050, 64, False) == [
        "-ar", "22050", "-ac", "1", "-c:a", "aac", "-b:a", "64k",
    ]


def test_format_extensions():
    assert [A.format_spec(f)["ext"] for f in ("mp3", "opus", "aac")] == [
        "mp3", "opus", "m4a",
    ]
    assert A.AUDIO_EXTS == (".m4a", ".mp3", ".opus")


def test_unknown_format_raises():
    with pytest.raises(A.AudioError, match="unknown audio format 'flac'"):
        A.encode_args("flac", 24000, 96, True)


def test_effective_tts_defaults():
    book = Book(dir=Path("/tmp"), title="t", language="zh", tts={})
    assert effective_tts(book)["format"] == "mp3"
    assert effective_tts(book)["loudnorm"] is True
    assert effective_tts(book)["bitrate_kbps"] == 96
    assert effective_tts(book, None, {"format": "opus"})["bitrate_kbps"] == 48
    assert effective_tts(book, None, {"format": "opus", "bitrate_kbps": 72})[
        "bitrate_kbps"
    ] == 72
    assert effective_tts(book, None, {"loudnorm": False})["loudnorm"] is False


# -- concat list escaping ---------------------------------------------------


def test_concat_line_escaping():
    assert A.concat_line("/tmp/a b/c.wav") == "file '/tmp/a b/c.wav'\n"
    assert A.concat_line("/tmp/it's here/x.wav") == "file '/tmp/it'\\''s here/x.wav'\n"


@needs_ffmpeg
def test_ffmpeg_reads_back_a_quoted_path(tmp_path):
    odd = tmp_path / "it's a \"dir\", really"
    odd.mkdir()
    clip = A.silence_clip(250, 24000, odd)
    assert (clip.frames, clip.sample_rate) == (6000, 24000)  # sample-exact
    listing = A.write_concat_list(tmp_path / "list.txt", [clip.path, clip.path])
    out = tmp_path / "joined.mp3"
    A.encode_concat(
        listing, out, sample_rate=24000, fmt="mp3", bitrate_kbps=96, loudnorm=False
    )
    assert round(A.probe_duration(out) or 0, 2) == 0.5


@needs_ffmpeg
def test_pcm_is_normalized_into_the_cache(tmp_path):
    mock = get_provider("mock").synthesize("一二三四五", CFG)
    clip = A.normalize_clip(
        mock.data, mock.format, tmp_path / "raw.flac", 24000, mock.sample_rate
    )
    assert (clip.frames, clip.sample_rate) == (len(mock.data) // 2, 24000)


@needs_ffmpeg
def test_mp3_round_trip_keeps_rate_and_length(tmp_path):
    mock = get_provider("mock").synthesize("一二三四五", CFG)
    raw = A.normalize_clip(
        mock.data, mock.format, tmp_path / "raw.flac", 24000, mock.sample_rate
    )
    A.encode_concat(
        A.write_concat_list(tmp_path / "l2.txt", [raw.path]),
        tmp_path / "clip.mp3",
        sample_rate=24000, fmt="mp3", bitrate_kbps=96, loudnorm=False,
    )
    back = A.normalize_clip(
        (tmp_path / "clip.mp3").read_bytes(), "mp3", tmp_path / "back.flac", 24000
    )
    assert back.sample_rate == 24000
    assert abs(back.duration - raw.duration) < 0.06


@needs_ffmpeg
def test_low_rate_wav_is_resampled(tmp_path):
    wav16 = tmp_path / "16k.wav"
    with wave.open(str(wav16), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    up = A.normalize_clip(wav16.read_bytes(), "wav", tmp_path / "up.flac", 24000)
    assert (up.frames, up.sample_rate) == (24000, 24000)


# -- tool discovery ---------------------------------------------------------


def test_missing_ffmpeg_points_at_the_nix_shell(monkeypatch):
    monkeypatch.setenv("FFMPEG", "/nonexistent/ffmpeg-please")
    with pytest.raises(A.AudioError) as excinfo:
        A.ffmpeg_path()
    message = str(excinfo.value)
    assert message.startswith("ffmpeg not found.")
    assert "nix develop path:" in message
    assert "#synth" in message
