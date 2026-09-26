"""Regenerate examples/minimal narration audio and cues with the deterministic silent voice."""

from pathlib import Path

from revision_engine.narration import SilentSynthesizer, narrate

LESSON = Path(__file__).resolve().parents[2] / "examples/minimal/docs/revision/chapters/01-intro/lessons/01-hello"

if __name__ == "__main__":
    cues = narrate(LESSON, SilentSynthesizer(rate=8000, seconds_per_char=0.06), voice="silent-fixture")
    print(f"wrote {len(cues['segments'])} segments, last ends at {cues['segments'][-1]['end']}s")
