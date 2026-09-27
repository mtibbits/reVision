"""Narration: authored segments -> synthesized audio + derived cue timings.

Authors write words, never timestamps. `narrate` derives start/end per segment from
the synthesized audio and records a hash of the words so `build` can detect drift.
"""

from __future__ import annotations

import difflib
import hashlib
import io
import json
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from revision_engine.config import DEFAULT_VOICE
from revision_engine.errors import BuildError
from revision_engine.lesson import load_lesson

DEFAULT_PAUSE = 0.4


@dataclass(frozen=True)
class Segment:
    text: str
    show: tuple[str, ...]
    diagram: str | None
    node: str | None
    pause: float


@dataclass(frozen=True)
class Narration:
    voice: str | None
    segments: tuple[Segment, ...]


def load_narration(path: Path, where: str) -> Narration:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise BuildError(f"{where}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise BuildError(f"{where}: top level must be a mapping")
    raw = data.get("segments")
    if not isinstance(raw, list) or not raw:
        raise BuildError(f"{where}: 'segments' must be a non-empty list")
    voice = data.get("voice")
    if voice is not None and not isinstance(voice, str):
        raise BuildError(f"{where}: 'voice' must be a string")
    segments: list[Segment] = []
    for i, s in enumerate(raw, start=1):
        if not isinstance(s, dict) or not isinstance(s.get("text"), str) or not s["text"].strip():
            raise BuildError(f"{where}: segment {i} needs a 'text' string")
        show = s.get("show", [])
        if isinstance(show, str):
            show = [show]
        if not isinstance(show, list) or not all(isinstance(x, str) for x in show):
            raise BuildError(f"{where}: segment {i}: 'show' must be an anchor name or a list of names")
        for key in ("diagram", "node"):
            if key in s and not isinstance(s[key], str):
                raise BuildError(f"{where}: segment {i}: '{key}' must be a string")
        pause = s.get("pause", DEFAULT_PAUSE)
        if isinstance(pause, bool) or not isinstance(pause, (int, float)) or pause < 0:
            raise BuildError(f"{where}: segment {i}: 'pause' must be a non-negative number of seconds")
        segments.append(
            Segment(
                text=" ".join(s["text"].split()),
                show=tuple(show),
                diagram=s.get("diagram"),
                node=s.get("node"),
                pause=float(pause),
            )
        )
    return Narration(voice=voice, segments=tuple(segments))


def text_hash(n: Narration) -> str:
    payload = json.dumps([[s.text, s.pause] for s in n.segments], ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> tuple[int, bytes]:
        """Return (sample_rate, 16-bit mono little-endian PCM) for one segment."""


class SilentSynthesizer:
    """Deterministic stand-in: silence whose length grows with the text. For tests and fixtures."""

    def __init__(self, rate: int = 8000, seconds_per_char: float = 0.05) -> None:
        self.rate = rate
        self.seconds_per_char = seconds_per_char

    def synthesize(self, text: str) -> tuple[int, bytes]:
        frames = int(round(len(text) * self.seconds_per_char * self.rate))
        return self.rate, b"\x00\x00" * frames


class PiperSynthesizer:
    """Runs the `piper` command with a voice model file; text on stdin, raw PCM on stdout."""

    def __init__(self, model: Path) -> None:
        if shutil.which("piper") is None:
            raise BuildError("piper is not installed or not on PATH (pip install piper-tts)")
        if not model.is_file():
            raise BuildError(f"piper voice model not found: {model}")
        self.model = model
        self.rate = _piper_sample_rate(model)

    def synthesize(self, text: str) -> tuple[int, bytes]:
        proc = subprocess.run(
            ["piper", "--model", str(self.model), "--output-raw"],
            input=text.encode("utf-8"),
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise BuildError(f"piper failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
        return self.rate, proc.stdout


def _piper_sample_rate(model: Path) -> int:
    cfg = model.with_suffix(model.suffix + ".json")
    if not cfg.is_file():
        raise BuildError(f"piper voice config not found: {cfg}")
    data = json.loads(cfg.read_text(encoding="utf-8"))
    return int(data["audio"]["sample_rate"])


def _write_wav(path: Path, rate: int, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    path.write_bytes(buf.getvalue())


def narrate(lesson_dir: Path, synth: Synthesizer, voice: str, media_name: str = "narration.wav") -> dict:
    where = f"{lesson_dir.name}/narration.yaml"
    n = load_narration(lesson_dir / "narration.yaml", where)
    rate: int | None = None
    pcm = bytearray()
    cues_segments: list[dict[str, Any]] = []
    for seg in n.segments:
        seg_rate, audio = synth.synthesize(seg.text)
        if rate is None:
            rate = seg_rate
        elif seg_rate != rate:
            raise BuildError(f"{where}: synthesizer changed sample rate mid-lesson ({rate} -> {seg_rate})")
        pcm += b"\x00\x00" * int(round(seg.pause * rate))
        start = len(pcm) / 2 / rate
        pcm += audio
        end = len(pcm) / 2 / rate
        entry: dict[str, Any] = {"start": round(start, 3), "end": round(end, 3), "text": seg.text}
        if seg.show:
            entry["show"] = list(seg.show)
        if seg.diagram:
            entry["diagram"] = seg.diagram
        if seg.node:
            entry["node"] = seg.node
        cues_segments.append(entry)
    assert rate is not None
    _write_wav(lesson_dir / "media" / media_name, rate, bytes(pcm))
    cues = {
        "media": f"media/{media_name}",
        "voice": voice,
        "text_hash": text_hash(n),
        "segments": cues_segments,
    }
    (lesson_dir / "cues.json").write_text(
        json.dumps(cues, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return cues


def load_cues(path: Path, where: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BuildError(f"{where}: invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise BuildError(f"{where}: top level must be an object")
    for key in ("media", "text_hash"):
        if not isinstance(data.get(key), str):
            raise BuildError(f"{where}: '{key}' must be a string")
    if not isinstance(data.get("segments"), list):
        raise BuildError(f"{where}: 'segments' must be a list")
    for i, s in enumerate(data["segments"], start=1):
        if not isinstance(s, dict) or not all(isinstance(s.get(k), (int, float)) for k in ("start", "end")):
            raise BuildError(f"{where}: segment {i} needs numeric 'start' and 'end'")
        if not isinstance(s.get("text"), str):
            raise BuildError(f"{where}: segment {i} needs a 'text' string")
    return data


def check_cues(n: Narration, cues: dict, where: str) -> None:
    if cues.get("text_hash") == text_hash(n):
        return
    old = [s["text"] for s in cues.get("segments", [])]
    new = [s.text for s in n.segments]
    diff = "\n".join(difflib.unified_diff(old, new, "cues.json", "narration.yaml", lineterm="", n=1))
    raise BuildError(
        f"{where}: narration.yaml changed since cues.json was generated; "
        f"rerun 'rv2 narrate' for this lesson.\n{diff}"
    )


def _project_voice(lesson_dir: Path) -> str | None:
    """The ``narration.voice`` of the first revision.yaml found walking up from the lesson."""
    resolved = lesson_dir.resolve()
    for parent in [resolved, *resolved.parents]:
        cfg = parent / "revision.yaml"
        if cfg.is_file():
            data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            narration = data.get("narration") if isinstance(data, dict) else None
            voice = narration.get("voice") if isinstance(narration, dict) else None
            return voice if isinstance(voice, str) else None
    return None


def resolve_voice_model(lesson_dir: Path, cli_voice: str | None, cli_model: Path | None) -> tuple[str, Path]:
    """Pick the voice name and Piper model for ``rv2 narrate``.

    Name: --voice, then narration.yaml's ``voice``, then the lesson's front matter, then the
    project's narration.voice, then the default. Model: --model if given, else ``<voice>.onnx``
    in $RV2_VOICES or ~/piper-voices. The returned name is what cues.json records.
    """
    if cli_model is not None:
        if not cli_model.is_file():
            raise BuildError(f"piper voice model not found: {cli_model}")
        return cli_voice or cli_model.name.removesuffix(".onnx"), cli_model
    voice = cli_voice
    if voice is None and (lesson_dir / "narration.yaml").is_file():
        voice = load_narration(lesson_dir / "narration.yaml", f"{lesson_dir.name}/narration.yaml").voice
    if voice is None and (lesson_dir / "lesson.md").is_file():
        voice = load_lesson(lesson_dir / "lesson.md", f"{lesson_dir.name}/lesson.md").voice
    if voice is None:
        voice = _project_voice(lesson_dir)
    if voice is None:
        voice = DEFAULT_VOICE
    voices_dir = Path(os.environ.get("RV2_VOICES") or Path.home() / "piper-voices")
    model = voices_dir / f"{voice}.onnx"
    if not model.is_file():
        raise BuildError(
            f"voice {voice!r}: no model at {model}. Download <voice>.onnx and .onnx.json from "
            "https://huggingface.co/rhasspy/piper-voices into that folder, or pass --model."
        )
    return voice, model
