import pytest

from revision_engine.anchors import AnchorSpec, load_anchors, resolve, resolve_all
from revision_engine.errors import BuildError
from revision_engine.sources import SourceFile

SRC = SourceFile(
    path="k.h",
    text="",
    lines=(
        "/* doc: static int add(int a, int b) */",  # 1
        "#include <x.h>",  # 2
        "static int add(int a, int b)",  # 3
        "{",  # 4
        "    return a + b;",  # 5
        "}",  # 6
        "int main(void)",  # 7
        "{",  # 8
        "    return add(1, 2);",  # 9
        "}",  # 10
    ),
)


def spec(**kw):
    base = dict(name="n", file="k.h", from_=None, to=None, match=None, lines=None, variant=False, label="n", within=None)
    base.update(kw)
    return AnchorSpec(**base)


def test_from_to_resolves_function_body():
    a = resolve(spec(from_="int main(void)", to=r"^}"), SRC)
    assert (a.start, a.end) == (7, 10)


def test_from_ambiguous_lists_candidates():
    with pytest.raises(BuildError) as e:
        resolve(spec(name="add-fn", from_="static int add(int a, int b)", to=r"^}"), SRC)
    msg = str(e.value)
    assert "anchor 'add-fn'" in msg and "k.h" in msg
    assert "line 1" in msg and "line 3" in msg


def test_match_single_line():
    a = resolve(spec(match="return a + b;"), SRC)
    assert (a.start, a.end) == (5, 5)


def test_match_missing_is_error():
    with pytest.raises(BuildError, match="no line contains 'nothing here'"):
        resolve(spec(match="nothing here"), SRC)


def test_to_missing_after_from_is_error():
    with pytest.raises(BuildError, match="no line after line 7 matches"):
        resolve(spec(from_="int main(void)", to=r"^never"), SRC)


def test_explicit_lines_within_bounds():
    a = resolve(spec(lines=(3, 6)), SRC)
    assert (a.start, a.end) == (3, 6)
    with pytest.raises(BuildError, match="lines 3-99 exceed file length 10"):
        resolve(spec(lines=(3, 99)), SRC)


def test_load_anchors_parses_forms_and_defaults(tmp_path):
    p = tmp_path / "anchors.yaml"
    p.write_text(
        "add-fn:\n  from: 'static int add'\n  to: '^}'\n  variant: true\n  label: add\n"
        "add-expr:\n  match: 'return a + b;'\n"
        "tail:\n  file: other.h\n  lines: 88-92\n",
        encoding="utf-8",
    )
    specs = load_anchors(p, default_file="k.h", where="L/anchors.yaml")
    assert list(specs) == ["add-fn", "add-expr", "tail"]
    assert specs["add-fn"].variant is True and specs["add-fn"].label == "add"
    assert specs["add-expr"].file == "k.h" and specs["add-expr"].label == "add-expr"
    assert specs["tail"].file == "other.h" and specs["tail"].lines == (88, 92)


def test_load_anchors_requires_exactly_one_form(tmp_path):
    p = tmp_path / "anchors.yaml"
    p.write_text("bad:\n  from: a\n  match: b\n", encoding="utf-8")
    with pytest.raises(BuildError, match=r"L/anchors\.yaml: anchor 'bad' must use exactly one of from/to, match, lines"):
        load_anchors(p, default_file="k.h", where="L/anchors.yaml")


def test_load_anchors_missing_file_is_empty(tmp_path):
    assert load_anchors(tmp_path / "none.yaml", default_file="k.h", where="x") == {}


def test_anchor_name_must_be_slug(tmp_path):
    p = tmp_path / "anchors.yaml"
    p.write_text("Bad Name:\n  match: x\n", encoding="utf-8")
    with pytest.raises(BuildError, match="'Bad Name' is not a slug"):
        load_anchors(p, default_file="k.h", where="x")


def test_resolve_all_preserves_order_and_uses_right_file():
    specs = {"m": spec(name="m", match="int main(void)"), "a": spec(name="a", match="return a + b;")}
    out = resolve_all(specs, {"k.h": SRC})
    assert list(out) == ["m", "a"] and out["m"].start == 7


def test_resolve_all_unknown_file():
    with pytest.raises(BuildError, match="anchor 'z' refers to file 'zz.h' which is not loaded"):
        resolve_all({"z": spec(name="z", file="zz.h", match="x")}, {"k.h": SRC})


TWIN = SourceFile(
    path="k.h",
    text="",
    lines=(
        "static inline void f_u(void)",  # 1
        "{",  # 2
        "    x = fma(a, b, x);",  # 3
        "}",  # 4
        "static inline void f_a(void)",  # 5
        "{",  # 6
        "    x = fma(a, b, x);",  # 7
        "}",  # 8
    ),
)


def test_within_restricts_match_to_enclosing_anchor():
    specs = {
        "f-u": spec(name="f-u", from_="void f_u(", to=r"^}"),
        "f-a": spec(name="f-a", from_="void f_a(", to=r"^}"),
        "fma-a": spec(name="fma-a", match="x = fma(a, b, x);", within="f-a"),
    }
    out = resolve_all(specs, {"k.h": TWIN})
    assert (out["fma-a"].start, out["fma-a"].end) == (7, 7)


def test_within_from_to_stay_inside_bounds():
    specs = {
        "f-u": spec(name="f-u", from_="void f_u(", to=r"^}"),
        "body-u": spec(name="body-u", from_="{", to=r"^}", within="f-u"),
    }
    out = resolve_all(specs, {"k.h": TWIN})
    assert (out["body-u"].start, out["body-u"].end) == (2, 4)


def test_within_to_cannot_escape_range():
    specs = {
        "f-u": spec(name="f-u", from_="void f_u(", to=r"^}"),
        "bad": spec(name="bad", from_="}", to=r"void f_a", within="f-u"),
    }
    with pytest.raises(BuildError, match=r"no line after line 4 within 'f-u' matches"):
        resolve_all(specs, {"k.h": TWIN})


def test_within_unknown_or_forward_reference_is_error():
    with pytest.raises(BuildError, match=r"anchor 'z' is within 'nope', which is not defined earlier in anchors\.yaml"):
        resolve_all({"z": spec(name="z", match="x", within="nope")}, {"k.h": TWIN})
    specs = {"z": spec(name="z", match="{", within="f-u"), "f-u": spec(name="f-u", from_="void f_u(", to=r"^}")}
    with pytest.raises(BuildError, match="not defined earlier"):
        resolve_all(specs, {"k.h": TWIN})


def test_load_anchors_reads_within(tmp_path):
    p = tmp_path / "anchors.yaml"
    p.write_text("outer:" + chr(10) + "  from: a" + chr(10) + "  to: b" + chr(10) + "inner:" + chr(10) + "  match: c" + chr(10) + "  within: outer" + chr(10), encoding="utf-8")
    specs = load_anchors(p, default_file="k.h", where="x")
    assert specs["inner"].within == "outer" and specs["outer"].within is None
