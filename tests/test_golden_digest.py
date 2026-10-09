import shutil

from revision_engine.build import build
from tests.golden_digest import golden_hashes, svg_structure

FIXED = "0123456789abcdef0123456789abcdef01234567"

NODE_A = (
    '<g id="main-fn" class="node rv-svg-anchor" data-node="main-fn" data-anchor="main-fn">\n'
    "<title>main</title>\n"
    '<polygon fill="none" stroke="black" points="55,-90 0,-90 0,-54 55,-54 55,-90"/>\n'
    '<text text-anchor="middle" x="27.5" y="-66.58" font-size="14.00">main()</text>\n'
    "</g>\n"
)
NODE_B = (
    '<g id="printf-node" class="node" data-node="printf-node">\n'
    "<title>out</title>\n"
    '<polygon fill="none" stroke="black" points="153,-36 99,-36 99,0 153,0 153,-36"/>\n'
    '<text text-anchor="middle" x="126" y="-12.57" font-size="14.00">printf</text>\n'
    "</g>\n"
)
EDGE = (
    '<g id="edge1" class="edge">\n<title>main&#45;&gt;out</title>\n'
    '<path fill="none" stroke="black" d="M55.38,-65.88C62.81,-65.41 71.09,-65.21 79.27,-65.26"/>\n</g>\n'
)


def _svg(body: str, *, w="169pt", h="98pt", graph_id="graph0") -> str:
    return (
        f'<svg class="rv-svg" width="{w}" height="{h}" viewBox="0.00 0.00 169.00 98.00">\n'
        f'<g id="{graph_id}" class="graph" transform="scale(1 1) rotate(0) translate(4 94)">\n'
        f"<title>flow</title>\n{body}</g>\n</svg>"
    )


BASE = _svg(NODE_A + EDGE + NODE_B)


def test_structure_ignores_geometry_and_graphviz_ids():
    moved_b = (
        NODE_B.replace('points="153,-36 99,-36 99,0 153,0 153,-36"', 'points="1,2 3,4"')
        .replace('x="126" y="-12.57"', 'x="7" y="8" transform="rotate(3)"')
        .replace("<text ", '<text xml:space="preserve" ')
    )
    edge7 = EDGE.replace('id="edge1"', 'id="edge7"').replace('d="M55.38', 'd="M1.00')
    other = _svg(moved_b + edge7 + NODE_A, w="200pt", h="10pt", graph_id="graph9")
    assert svg_structure(other) == svg_structure(BASE)


def test_structure_sees_engine_and_author_output():
    base = svg_structure(BASE)
    assert svg_structure(BASE.replace('data-anchor="main-fn"', 'data-anchor="other"')) != base
    assert svg_structure(BASE.replace('class="node rv-svg-anchor"', 'class="node"')) != base
    assert svg_structure(BASE.replace(">printf</text>", ">puts</text>")) != base
    assert svg_structure(BASE.replace('id="printf-node"', 'id="puts-node"')) != base


def test_structure_sees_edges():
    base = svg_structure(BASE)
    assert svg_structure(BASE.replace(EDGE, "")) != base
    assert svg_structure(BASE.replace("main&#45;&gt;out", "main&#45;&gt;add")) != base
    labelled = _svg(NODE_A + EDGE.replace("/>\n</g>", '/>\n<text x="1" y="2">calls</text>\n</g>') + NODE_B)
    assert svg_structure(labelled) != base
    assert svg_structure(labelled.replace(">calls<", ">returns<")) != svg_structure(labelled)


def test_structure_sees_labels_of_linked_nodes():
    linked = _svg(
        '<g id="n1" class="node" data-node="n1">\n<title>n</title>\n'
        '<g id="a_n1"><a xlink:href="https://x" xlink:title="t">\n'
        '<polygon points="1,2 3,4"/>\n<text x="1" y="2">hello</text>\n</a>\n</g>\n</g>\n'
    )
    assert "hello" in svg_structure(linked)
    assert svg_structure(linked.replace(">hello<", ">bye<")) != svg_structure(linked)


def test_structure_unescapes_entities():
    escaped = _svg('<g id="a&#45;b" class="node" data-node="a&#45;b">\n<text>x&#45;&gt;y</text>\n</g>\n')
    plain = _svg('<g id="a-b" class="node" data-node="a-b">\n<text>x->y</text>\n</g>\n')
    assert svg_structure(escaped) == svg_structure(plain)


def test_golden_hashes_normalises_every_diagram(minimal_example, tmp_path):
    src = tmp_path / "m"
    shutil.copytree(minimal_example, src)
    out = tmp_path / "out"
    build(src, output=out, commit=FIXED)
    _, counts = golden_hashes(out)
    assert {k: n for k, n in counts.items() if n} == {"intro/hello/index.html": 1}
