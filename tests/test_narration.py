import json
import wave

import pytest

from revision_engine.errors import BuildError
from revision_engine.narration import (
    Narration,
    Segment,
    SilentSynthesizer,
    check_cues,
    load_cues,
    load_narration,
    narrate,
    text_hash,
)

YAML = """voice: en_US-test
segments:
  - text: First sentence.
    show: a
  - text: Second sentence.
    show: [b, c]
    diagram: flow
    node: main-fn
    pause: 1.0
"""


def test_load_narration(tmp_path):
    p = tmp_path / "narration.yaml"
    p.write_text(YAML, encoding="utf-8")
    n = load_narration(p, "L/narration.yaml")
    assert n.voice == "en_US-test"
    assert n.segments[0] == Segment("First sentence.", ("a",), None, None, 0.4)
    assert n.segments[1].show == ("b", "c") and n.segments[1].pause == 1.0 and n.segments[1].node == "main-fn"


def test_segment_requires_text(tmp_path):
    p = tmp_path / "narration.yaml"
    p.write_text("segments:\n  - show: a\n", encoding="utf-8")
    with pytest.raises(BuildError, match=r"L/narration\.yaml: segment 1 needs a 'text' string"):
        load_narration(p, "L/narration.yaml")


def test_hash_changes_with_pause_not_show():
    a = Narration(None, (Segment("t", ("x",), None, None, 0.4),))
    b = Narration(None, (Segment("t", ("y",), None, None, 0.4),))
    c = Narration(None, (Segment("t", ("x",), None, None, 0.9),))
    assert text_hash(a) == text_hash(b)
    assert text_hash(a) != text_hash(c)
    assert text_hash(a).startswith("sha256:")


def test_narrate_writes_wav_and_cues(tmp_path):
    (tmp_path / "narration.yaml").write_text(YAML, encoding="utf-8")
    synth = SilentSynthesizer(rate=8000, seconds_per_char=0.1)
    cues = narrate(tmp_path, synth, voice="en_US-test")
    wav = tmp_path / "media" / "narration.wav"
    assert wav.is_file()
    with wave.open(str(wav)) as w:
        assert w.getframerate() == 8000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        total = w.getnframes() / 8000
    seg = cues["segments"]
    # 15 chars * 0.1 = 1.5s after a 0.4 pause; then a 1.0 pause and 16 chars * 0.1 = 1.6s
    assert seg[0]["start"] == pytest.approx(0.4) and seg[0]["end"] == pytest.approx(1.9)
    assert seg[1]["start"] == pytest.approx(2.9) and seg[1]["end"] == pytest.approx(4.5)
    assert total == pytest.approx(4.5, abs=0.01)
    assert seg[0]["show"] == ["a"] and seg[1]["show"] == ["b", "c"] and seg[1]["diagram"] == "flow"
    on_disk = json.loads((tmp_path / "cues.json").read_text(encoding="utf-8"))
    assert on_disk == cues and on_disk["media"] == "media/narration.wav" and on_disk["voice"] == "en_US-test"


def test_cues_json_is_stable_text(tmp_path):
    (tmp_path / "narration.yaml").write_text(YAML, encoding="utf-8")
    narrate(tmp_path, SilentSynthesizer(), voice="v")
    first = (tmp_path / "cues.json").read_bytes()
    narrate(tmp_path, SilentSynthesizer(), voice="v")
    assert (tmp_path / "cues.json").read_bytes() == first
    assert first.endswith(b"}\n")


def test_check_cues_passes_when_hash_matches(tmp_path):
    (tmp_path / "narration.yaml").write_text(YAML, encoding="utf-8")
    n = load_narration(tmp_path / "narration.yaml", "w")
    cues = narrate(tmp_path, SilentSynthesizer(), voice="v")
    check_cues(n, cues, "L")


def test_check_cues_fails_with_diff_when_text_changed(tmp_path):
    (tmp_path / "narration.yaml").write_text(YAML, encoding="utf-8")
    narrate(tmp_path, SilentSynthesizer(), voice="v")
    cues = load_cues(tmp_path / "cues.json", "L/cues.json")
    (tmp_path / "narration.yaml").write_text(YAML.replace("Second sentence.", "Changed sentence."), encoding="utf-8")
    n = load_narration(tmp_path / "narration.yaml", "w")
    with pytest.raises(BuildError) as e:
        check_cues(n, cues, "L")
    msg = str(e.value)
    assert "rerun 'rv2 narrate'" in msg and "-Second sentence." in msg and "+Changed sentence." in msg


def test_load_cues_validates_shape(tmp_path):
    p = tmp_path / "cues.json"
    p.write_text('{"media": "m", "text_hash": "h", "segments": "nope"}', encoding="utf-8")
    with pytest.raises(BuildError, match=r"L/cues\.json: 'segments' must be a list"):
        load_cues(p, "L/cues.json")
