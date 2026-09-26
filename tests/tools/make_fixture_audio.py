"""Regenerate examples/minimal narration audio and cues with the deterministic silent voice.

The committed example audio is real speech from Piper (en_US-lessac-medium), produced with
    rv2 narrate examples/minimal/docs/revision/chapters/01-intro/lessons/01-hello --model <voice>.onnx
This script is the fallback for a machine without Piper: it writes silence with plausible timings
so the build, golden, and browser tests still have a seekable file. Regenerate the golden manifest
after either (RV_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py).
"""

from pathlib import Path

from revision_engine.narration import SilentSynthesizer, narrate

LESSON = Path(__file__).resolve().parents[2] / "examples/minimal/docs/revision/chapters/01-intro/lessons/01-hello"

if __name__ == "__main__":
    cues = narrate(LESSON, SilentSynthesizer(rate=8000, seconds_per_char=0.06), voice="silent-fixture")
    print(f"wrote {len(cues['segments'])} segments, last ends at {cues['segments'][-1]['end']}s")
