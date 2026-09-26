"""Golden build: examples/minimal must render to a known tree.

Regenerate after an intentional rendering change with:
    RV_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py
The manifest records the Graphviz version; the test skips on a different one because
layout coordinates change between Graphviz releases.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from revision_engine.build import build
from revision_engine.diagrams import graphviz_version
from tests.test_determinism import tree_hashes

FIXED = "0123456789abcdef0123456789abcdef01234567"
MANIFEST = Path(__file__).parent / "golden" / "minimal.json"


def test_minimal_matches_golden(minimal_example, tmp_path):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    out = tmp_path / "out"
    build(src, output=out, commit=FIXED)
    current = {"graphviz": graphviz_version(), "files": tree_hashes(out)}
    if os.environ.get("RV_UPDATE_GOLDEN"):
        MANIFEST.parent.mkdir(exist_ok=True)
        MANIFEST.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        pytest.skip("golden manifest updated")
    if not MANIFEST.is_file():
        pytest.fail("tests/golden/minimal.json missing; run with RV_UPDATE_GOLDEN=1")
    golden = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if golden["graphviz"] != current["graphviz"]:
        pytest.skip(f"graphviz {current['graphviz']} differs from golden {golden['graphviz']}")
    keys = set(golden["files"]) | set(current["files"])
    diff = {k: (golden["files"].get(k), current["files"].get(k)) for k in keys if golden["files"].get(k) != current["files"].get(k)}
    assert diff == {}, f"rendering changed for: {sorted(diff)}. If intentional, rerun with RV_UPDATE_GOLDEN=1"
