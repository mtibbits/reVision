"""Golden build: examples/minimal must render to a known tree.

Files are compared byte-for-byte, except that each diagram is reduced to its structure
(node ids, anchor stamps, edges, labels), so Graphviz layout and fonts do not matter; see
tests/golden_digest.py for why. Regenerate after an intentional rendering change, in an
up-to-date venv (`python -m pip install -U -e ".[dev]"`), with:
    RV_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from revision_engine.build import build
from tests.golden_digest import golden_hashes

FIXED = "0123456789abcdef0123456789abcdef01234567"
MANIFEST = Path(__file__).parent / "golden" / "minimal.json"
REGENERATE = "RV_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py"


def test_minimal_matches_golden(minimal_example, tmp_path):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    out = tmp_path / "out"
    build(src, output=out, commit=FIXED)
    hashes, _ = golden_hashes(out)
    current = {"files": hashes}
    if os.environ.get("RV_UPDATE_GOLDEN"):
        MANIFEST.parent.mkdir(exist_ok=True)
        MANIFEST.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        pytest.skip("golden manifest updated")
    if not MANIFEST.is_file():
        pytest.fail(f"tests/golden/minimal.json missing; run with {REGENERATE}")
    golden = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if set(golden) != {"files"}:
        pytest.fail(f"tests/golden/minimal.json has keys {sorted(golden)}, expected only 'files'; regenerate with {REGENERATE}")
    keys = set(golden["files"]) | set(current["files"])
    diff = {k: (golden["files"].get(k), current["files"].get(k)) for k in keys if golden["files"].get(k) != current["files"].get(k)}
    assert diff == {}, f"rendering changed for: {sorted(diff)}. If intentional, rerun with {REGENERATE}"
