"""Audio I/O on top of ffmpeg.

Everything that touches samples goes through ffmpeg. A provider may hand back
whatever its API offers; the clip is normalized exactly once — on its way into
the cache — into canonical FLAC (mono, 16-bit, at the configured sample rate),
and a chapter is assembled by a single call to the concat demuxer.

FLAC because the cache is the one copy of every paid-for clip and is kept
indefinitely: it is lossless, so assembly sees exactly the normalized samples,
at well under half the size of PCM.

Timing stays sample-exact because it never comes from a decoder: the number of
frames in each clip (and in each silence clip) is read from FLAC's STREAMINFO
header, and the concat demuxer yields every frame when all the inputs share
rate/channels/codec, which normalization guarantees.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

SKILL_DIR = Path(__file__).resolve().parents[2]  # the repo checkout, when there is one

# single-pass EBU R128 normalization; the podcast/audiobook house numbers, so
# clips from different providers or voices end up at the same level
LOUDNORM = "I=-16:TP=-1.5:LRA=11"

# `slack` is how far the *container header* may legitimately overstate the
# duration: Ogg counts the Opus pre-skip and MP4/Ogg round the last frame up to
# a frame boundary, which the loudnorm filter's own framing can trigger. The
# decoded sample count stays exact in every case (measured); only the metadata
# drifts, by at most ~57 ms here, so the cross-check allows for it.
FORMATS: dict[str, dict[str, Any]] = {
    "mp3": {"ext": "mp3", "codec": ["-c:a", "libmp3lame"], "bitrate": 96, "slack": 0.0},
    "opus": {"ext": "opus", "codec": ["-c:a", "libopus"], "bitrate": 48, "slack": 0.06},
    "aac": {"ext": "m4a", "codec": ["-c:a", "aac"], "bitrate": 96, "slack": 0.06},
}

AUDIO_EXTS = tuple(sorted({f".{spec['ext']}" for spec in FORMATS.values()}))

VERBOSE = False


class AudioError(RuntimeError):
    pass


# the on-disk format of a normalized clip
CLIP_EXT = ".flac"


@dataclass
class Clip:
    """A normalized FLAC on disk: mono, 16-bit, `sample_rate`."""

    path: Path
    frames: int
    sample_rate: int
    words: list[tuple[float, float, str]] | None = None

    @property
    def duration(self) -> float:
        return self.frames / float(self.sample_rate)


# -- tools ------------------------------------------------------------------


def _tool(name: str, env_var: str) -> str:
    """`$FFMPEG` / `$FFPROBE` first, then PATH."""
    override = os.environ.get(env_var)
    candidate = override or name
    found = shutil.which(candidate)
    if found:
        return found
    if override and Path(override).is_file() and os.access(override, os.X_OK):
        return override
    where = (
        str(SKILL_DIR) if (SKILL_DIR / "flake.nix").is_file() else "the skill directory"
    )
    raise AudioError(
        f"{name} not found. On Nix: nix develop path:{where} "
        f"(or nix run path:{where}#synth). Otherwise install ffmpeg."
    )


def ffmpeg_path() -> str:
    return _tool("ffmpeg", "FFMPEG")


def ffprobe_path() -> str:
    return _tool("ffprobe", "FFPROBE")


def require_tools() -> None:
    """Fail early, with the friendly message, before anything is synthesized."""
    ffmpeg_path()
    ffprobe_path()


def set_verbose(flag: bool) -> None:
    global VERBOSE
    VERBOSE = bool(flag)


def _run(args: Sequence[str], stdin: bytes | None = None) -> bytes:
    if VERBOSE:
        print("  $ " + " ".join(_quote(a) for a in args))
    proc = subprocess.run(
        list(args), input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-12:]
        raise AudioError(
            f"{Path(args[0]).name} failed (exit {proc.returncode}):\n    "
            + "\n    ".join(tail)
        )
    return proc.stdout


def _quote(arg: str) -> str:
    return f"'{arg}'" if (" " in arg or "'" in arg) else arg


_BASE = ["-nostdin", "-hide_banner", "-loglevel", "error", "-y"]


# -- normalization ----------------------------------------------------------


_CLIP_CODEC = ["-c:a", "flac", "-sample_fmt", "s16", "-compression_level", "8", "-f", "flac"]


def normalize_clip(
    data: bytes, fmt: str, dest: str | Path, sample_rate: int, src_rate: int | None = None
) -> Clip:
    """Decode whatever the provider returned into a canonical FLAC at `dest`.

    `fmt` is `"pcm_s16le"` (headerless samples, `src_rate` required) or the
    name of a container/codec — `"wav"`, `"mp3"`, `"ogg"`, …; for those the
    bytes carry their own header, so ffmpeg probes them and the name is only
    documentation.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = [ffmpeg_path(), *_BASE]
    if fmt == "pcm_s16le":
        if not src_rate:
            raise AudioError("normalize_clip: pcm_s16le needs a sample_rate")
        args += ["-f", "s16le", "-ar", str(int(src_rate)), "-ac", "1"]
    args += ["-i", "pipe:0", "-ar", str(int(sample_rate)), "-ac", "1", *_CLIP_CODEC, str(dest)]
    _run(args, stdin=data)
    frames, rate = clip_info(dest)
    return Clip(path=dest, frames=frames, sample_rate=rate)


def clip_info(path: str | Path) -> tuple[int, int]:
    """(frames, sample_rate) straight from the header — the timing truth.

    FLAC requires STREAMINFO to be the first metadata block; from its byte 10:
    20 bits sample rate, 3 bits channels-1, 5 bits bits-per-sample-1, 36 bits
    total samples.
    """
    with open(path, "rb") as fh:
        head = fh.read(42)
    if len(head) < 42 or head[:4] != b"fLaC" or head[4] & 0x7F != 0:
        raise AudioError(f"{path}: not a FLAC file")
    bits = int.from_bytes(head[18:26], "big")
    rate = bits >> 44
    channels = ((bits >> 41) & 0x7) + 1
    depth = ((bits >> 36) & 0x1F) + 1
    frames = bits & ((1 << 36) - 1)
    if channels != 1 or depth != 16:
        raise AudioError(f"{path}: expected mono 16-bit flac")
    if frames == 0:  # the encoder never came back to fill it in
        raise AudioError(f"{path}: FLAC header has no sample count")
    return frames, rate


def silence_clip(ms: float, sample_rate: int, cache_dir: str | Path) -> Clip:
    """`ms` milliseconds of silence, generated once per distinct length — in the
    clip format, since the concat demuxer wants one codec across its inputs."""
    key = int(round(ms))
    path = Path(cache_dir) / f"{key}{CLIP_EXT}"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _run([
            ffmpeg_path(), *_BASE,
            "-f", "lavfi", "-i", f"anullsrc=r={int(sample_rate)}:cl=mono",
            "-t", f"{max(0.0, key / 1000.0):.6f}",
            *_CLIP_CODEC, str(path),
        ])
    frames, rate = clip_info(path)
    if rate != sample_rate:  # the cache dir is per sample rate, but be safe
        path.unlink()
        return silence_clip(ms, sample_rate, cache_dir)
    return Clip(path=path, frames=frames, sample_rate=rate)


# -- assembly ---------------------------------------------------------------


def concat_line(path: str | Path) -> str:
    """One `file '…'` line, escaped the way the concat demuxer unquotes it.

    Inside single quotes every byte is literal until the next quote, so the
    only character needing work is `'` itself: close, escape, reopen.
    """
    p = str(Path(path).resolve())
    return "file '" + p.replace("'", "'\\''") + "'\n"


def write_concat_list(dest: str | Path, clips: Sequence[Path]) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(concat_line(p) for p in clips), encoding="utf-8")
    return dest


def format_spec(fmt: str) -> dict[str, Any]:
    spec = FORMATS.get(str(fmt).lower())
    if spec is None:
        raise AudioError(
            f"unknown audio format {fmt!r}; known formats: {', '.join(sorted(FORMATS))}"
        )
    return spec


def encode_args(fmt: str, sample_rate: int, bitrate_kbps: int, loudnorm: bool) -> list[str]:
    """Output options for one chapter: filter, rate, codec, bitrate."""
    spec = format_spec(fmt)
    args: list[str] = []
    if loudnorm:
        args += ["-af", f"loudnorm={LOUDNORM}"]
    # always after the filter: loudnorm resamples to 192 kHz internally
    args += ["-ar", str(int(sample_rate)), "-ac", "1"]
    args += list(spec["codec"]) + ["-b:a", f"{int(bitrate_kbps)}k"]
    return args


def encode_concat(
    list_file: str | Path,
    dest: str | Path,
    *,
    sample_rate: int,
    fmt: str,
    bitrate_kbps: int,
    loudnorm: bool,
) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run([
        ffmpeg_path(), *_BASE,
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        *encode_args(fmt, sample_rate, bitrate_kbps, loudnorm),
        str(dest),
    ])


def probe_duration(path: str | Path) -> float | None:
    """Container duration in seconds, for cross-checking the frame arithmetic."""
    out = _run([
        ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
    ])
    try:
        return float(json.loads(out)["format"]["duration"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
