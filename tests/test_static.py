from importlib import resources


def read(name: str) -> str:
    return resources.files("revision_engine").joinpath("static", name).read_text(encoding="utf-8")


def test_css_defines_tokens_and_both_dark_selectors():
    css = read("styles.css")
    for token in ("--rv-bg", "--rv-fg", "--rv-accent", "--rv-box", "--rv-panel-w"):
        assert token in css
    assert ':root[data-theme="dark"]' in css
    assert ':root:not([data-theme="light"])' in css and "prefers-color-scheme: dark" in css
    assert "@media (max-width: 900px)" in css


def test_js_has_no_network_calls_and_guards_storage():
    js = read("app.js")
    assert "fetch(" not in js and "XMLHttpRequest" not in js
    assert "try {" in js and "localStorage" in js
    assert "window.RV" in js
