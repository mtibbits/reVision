"""Command-line entry point: rv2 build | check | serve | narrate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from revision_engine import __version__
from revision_engine.errors import BuildError


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rv2", description="reVision static-site builder. Revision control, revisited.")
    p.add_argument("--version", action="version", version=f"rv2 {__version__}")
    sub = p.add_subparsers(dest="command", metavar="command")

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--root", type=Path, default=Path("."), help="repository root holding revision.yaml (default: .)")
        sp.add_argument("--commit", help="40-char sha to label the build when not in a git checkout")

    b = sub.add_parser("build", help="build the static site into the output folder")
    common(b)
    b.add_argument("--output", type=Path, help="override the output folder from revision.yaml")

    c = sub.add_parser("check", help="run every build check without writing output")
    common(c)

    s = sub.add_parser("serve", help="build, serve on localhost, rebuild on change")
    common(s)
    s.add_argument("--port", type=int, default=8000)

    n = sub.add_parser("narrate", help="synthesize a lesson's narration.yaml into audio + cues.json")
    n.add_argument("lesson_dir", type=Path)
    n.add_argument("--model", type=Path, help="path to a Piper voice model (.onnx); default: <voice>.onnx in $RV2_VOICES or ~/piper-voices")
    n.add_argument("--voice", help="voice name (default: the lesson's voice, then the project's narration.voice)")
    n.add_argument("--silent", action="store_true", help="use the deterministic silent voice (fixtures and tests)")
    n.add_argument("--mp3", action="store_true", help="also transcode to MP3 with ffmpeg and point cues at it")
    return p


def _report(result) -> None:
    for w in result.report.warnings:
        print(f"warning: {w}")
    if result.report.warnings:
        print(f"{len(result.report.warnings)} warning(s)")


def _cmd_build(args) -> int:
    from revision_engine.build import build

    result = build(args.root, output=args.output, commit=args.commit)
    print(f"built {len(result.pages)} pages at commit {result.commit[:7]} -> {result.output}")
    _report(result)
    return 0


def _cmd_check(args) -> int:
    from revision_engine.build import build

    result = build(args.root, commit=args.commit, check_only=True)
    print(f"ok: all checks passed at commit {result.commit[:7]}")
    _report(result)
    return 0


def _cmd_serve(args) -> int:
    from revision_engine.serve import serve

    serve(args.root, port=args.port, commit=args.commit)
    return 0


def _cmd_narrate(args) -> int:
    from revision_engine.narration import PiperSynthesizer, SilentSynthesizer, narrate

    if args.silent:
        synth = SilentSynthesizer()
        voice = args.voice or "silent-fixture"
    else:
        from revision_engine.narration import resolve_voice_model

        voice, model = resolve_voice_model(args.lesson_dir, args.voice, args.model)
        synth = PiperSynthesizer(model)
    cues = narrate(args.lesson_dir, synth, voice=voice)
    if args.mp3:
        _transcode_mp3(args.lesson_dir, cues)
    print(f"wrote {len(cues['segments'])} segments -> {args.lesson_dir / cues['media']}")
    return 0


def _transcode_mp3(lesson_dir: Path, cues: dict) -> None:
    import json
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        raise BuildError("--mp3 needs ffmpeg on PATH")
    wav = lesson_dir / cues["media"]
    mp3 = wav.with_suffix(".mp3")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "4", str(mp3)],
        check=False,
    )
    if proc.returncode != 0:
        raise BuildError("ffmpeg failed to transcode narration")
    wav.unlink()
    cues["media"] = f"media/{mp3.name}"
    (lesson_dir / "cues.json").write_text(
        json.dumps(cues, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        if args.command == "build":
            return _cmd_build(args)
        if args.command == "check":
            return _cmd_check(args)
        if args.command == "serve":
            return _cmd_serve(args)
        if args.command == "narrate":
            return _cmd_narrate(args)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
