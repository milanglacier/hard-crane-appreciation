"""Alt voices: the `<!-- voice: NAME -->` marker, the `tts.alt_voices` merge,
and a cache key that follows every setting that changes how a clip sounds."""

from __future__ import annotations

from pathlib import Path

import pytest

from audiobook_lib.book import effective_tts, load_book, voice_tts
from audiobook_lib.cache import cache_key
from audiobook_lib.housekeeping import plan_pieces
from audiobook_lib.segmenter import segment_markdown


def voices(src: str) -> list[tuple[str, str | None]]:
    return [(s.kind, s.alt_voice) for s in segment_markdown(src) if s.spoken]


# -- the marker ----------------------------------------------------------------


def test_marker_applies_to_the_next_block_only():
    src = "开头一段。\n\n<!-- voice: verse -->\n\n诗人这样写。\n\n回到旁白。\n"
    assert voices(src) == [("para", None), ("para", "verse"), ("para", None)]


def test_marker_covers_every_stanza_of_a_blockquote():
    src = (
        "<!-- voice: verse -->\n"
        "> And onward, as bells off San Salvador\n"
        "> Salute the crocus lustres of the stars,\n"
        ">\n"
        "> Adagios of islands, O my Prodigal,\n"
        "\n"
        "这里的意象是……\n"
    )
    assert voices(src) == [("stanza", "verse"), ("stanza", "verse"), ("para", None)]


def test_marker_inside_a_blockquote_picks_one_stanza():
    src = "> 第一节。\n>\n> <!-- voice: verse -->\n> Second stanza.\n"
    assert voices(src) == [("stanza", None), ("stanza", "verse")]


def test_ordinary_comment_between_marker_and_block_is_skipped():
    src = "<!-- voice: verse -->\n\n<!-- a note to the reviewer -->\n\nThe line.\n"
    assert voices(src) == [("para", "verse")]


def test_marker_with_nothing_spoken_after_it_warns():
    segs = segment_markdown("一段。\n\n<!-- voice: verse -->\n\n---\n\n另一段。\n")
    assert [s.alt_voice for s in segs if s.spoken] == [None, None]
    warned = [w for s in segs for w in s.warnings]
    assert warned == ["voice marker `verse` is not followed by a spoken block"]


def test_marker_at_the_end_of_the_chapter_warns():
    segs = segment_markdown("一段。\n\n<!-- voice: verse -->\n")
    assert segs[-1].warnings == ["voice marker `verse` is not followed by a spoken block"]


def test_marker_is_neither_shown_nor_spoken():
    segs = segment_markdown("<!-- voice: verse -->\n\nThe line.\n")
    assert len(segs) == 1
    assert segs[0].html == "<p>The line.</p>" and segs[0].spoken == "The line."


# -- the config merge ----------------------------------------------------------

BASE = {
    "provider": "minimax", "voice": "zh-voice", "speed": 1.0, "sample_rate": 24000,
    "format": "mp3", "extra": {"a": 1},
    "alt_voices": {
        "verse": {"voice": "en-voice", "speed": 0.9, "language_boost": "English", "extra": {"b": 2}},
    },
}


def test_voice_tts_lays_the_alt_voice_over_the_main_settings():
    assert voice_tts(BASE, None) is BASE
    cfg = voice_tts(BASE, "verse")
    assert cfg["voice"] == "en-voice" and cfg["speed"] == 0.9
    assert cfg["language_boost"] == "English"
    assert cfg["extra"] == {"a": 1, "b": 2}
    assert cfg["provider"] == "minimax" and cfg["format"] == "mp3"


def test_unknown_alt_voice_is_an_error():
    with pytest.raises(SystemExit, match="unknown alt voice 'poem'.*verse"):
        voice_tts(BASE, "poem")


def write_book(tmp_path: Path, alt_voices: str) -> Path:
    book = tmp_path / "book"
    (book / "chapters").mkdir(parents=True)
    (book / "book.yaml").write_text(
        "title: 书\nlanguage: zh\ntts:\n  provider: mock\n  voice: mock-a\n"
        f"  alt_voices:\n{alt_voices}",
        encoding="utf-8",
    )
    return book


@pytest.mark.parametrize("key", ["sample_rate", "format", "pause_ms", "loudnorm"])
def test_alt_voice_cannot_set_chapter_wide_settings(tmp_path, key):
    book = load_book(write_book(tmp_path, f"    verse:\n      {key}: 1\n"))
    with pytest.raises(SystemExit, match=f"{key}.*whole chapter"):
        effective_tts(book)


def test_each_piece_carries_its_own_voice_settings(tmp_path):
    book = load_book(write_book(tmp_path, "    verse:\n      voice: mock-b\n"))
    cfg = effective_tts(book)
    segs = segment_markdown("旁白。\n\n<!-- voice: verse -->\n> A line.\n")
    main, verse = (pieces[0] for pieces in plan_pieces(segs, cfg))
    assert main.cfg["voice"] == "mock-a" and verse.cfg["voice"] == "mock-b"
    assert main.key == cache_key(cfg, "旁白。")
    assert verse.key == cache_key(voice_tts(cfg, "verse"), "A line.")


# -- the cache key -------------------------------------------------------------


def test_cache_key_follows_every_setting_that_changes_the_sound():
    base = {"provider": "minimax", "voice": "v", "speed": 1.0, "sample_rate": 24000}
    key = cache_key(base, "text")
    assert cache_key({**base, "language_boost": "English"}, "text") != key
    assert cache_key({**base, "extra": {"emotion": "calm"}}, "text") != key
    assert cache_key({**base, "voice": "w"}, "text") != key
    assert cache_key(base, "other") != key


def test_cache_key_ignores_chapter_wide_settings():
    base = {"provider": "minimax", "voice": "v", "speed": 1.0, "sample_rate": 24000}
    key = cache_key(base, "text")
    chapter_wide = {
        "format": "opus", "loudnorm": False, "bitrate_kbps": 48, "concurrency": 8,
        "pause_ms": {"paragraph": 1}, "max_chars": 10, "alt_voices": {"x": {}}, "model": None,
    }
    assert cache_key({**base, **chapter_wide}, "text") == key
