def boxed(page):
    return page.evaluate("Array.from(document.querySelectorAll('.rv-line.rv-boxed')).map(l => +l.dataset.line)")


def test_loads_with_start_anchor_boxed_and_no_errors(hello):
    assert boxed(hello) == [5, 6, 7, 8]
    assert hello.errors == []


def test_rail_opens_and_closes_panel(hello):
    assert hello.locator("#rv-panel").is_hidden()
    hello.click('.rv-rail-btn[data-panel="curriculum"]')
    assert hello.locator('#rv-panel [data-view="curriculum"]').is_visible()
    assert hello.locator('#rv-panel [data-view="curriculum"] li.rv-current').inner_text().startswith("Adding")
    hello.click('.rv-rail-btn[data-panel="curriculum"]')
    assert hello.locator("#rv-panel").is_hidden()


def test_hover_boxes_and_leave_restores(hello):
    hello.hover('.rv-anchor[data-anchor="add-expr"]')
    assert boxed(hello) == [7]
    hello.mouse.move(0, 0)
    assert boxed(hello) == []


def test_click_pins_sets_hash_and_escape_clears(hello):
    hello.click('.rv-anchor[data-anchor="call-site"]')
    assert boxed(hello) == [12]
    assert hello.evaluate("location.hash") == "#call-site"
    assert hello.evaluate("document.body.classList.contains('rv-pinned')")
    hello.mouse.move(0, 0)
    assert boxed(hello) == [12]
    hello.keyboard.press("Escape")
    assert boxed(hello) == [] and hello.evaluate("location.hash") == ""


def test_fragment_pins_on_load(page, site_url):
    page.goto(site_url + "intro/hello/#main-fn")
    page.wait_for_function("window.RV !== undefined")
    assert boxed(page) == [10, 11, 12, 13, 14, 15]


def test_variants_panel_jumps(hello):
    hello.click('.rv-rail-btn[data-panel="variants"]')
    hello.click('.rv-variant[data-anchor="main-fn"]')
    assert boxed(hello) == [10, 11, 12, 13, 14, 15]


def test_transcript_click_seeks_and_fires_cue(hello):
    hello.click('.rv-seg[data-index="1"]')
    assert hello.locator('.rv-seg[data-index="1"]').get_attribute("class").split() == ["rv-seg", "rv-active"]
    assert boxed(hello) == [7]
    hello.click('.rv-seg[data-index="2"]')
    assert boxed(hello) == list(range(10, 16))
    assert hello.locator('.rv-diagram [data-node="main-fn"]').get_attribute("class").split().count("rv-node-active") == 1


def test_timeupdate_drives_cues(hello):
    hello.evaluate(
        "const m = document.getElementById('rv-media-el'); m.currentTime = 0.1; m.dispatchEvent(new Event('timeupdate'))"
    )
    assert hello.evaluate("window.RV.activeSegment()") == -1
    hello.evaluate("window.RV.seek(window.RV.data.cues[0].start + 0.05)")
    assert hello.evaluate("window.RV.activeSegment()") == 0
    assert boxed(hello) == [5, 6, 7, 8]


def test_quiz_grades_and_forgets(hello):
    hello.check('input[name="q0"][value="0"]')
    assert "Correct" in hello.locator('.rv-q[data-answer="0"] .rv-q-feedback').inner_text()
    hello.check('input[name="q1"][value="0"]')
    hello.click(".rv-quiz button")
    assert hello.locator(".rv-quiz-score").inner_text() == "1 of 2 correct."
    hello.reload()
    hello.wait_for_function("window.RV !== undefined")
    assert hello.locator(".rv-quiz-score").is_hidden()
    assert hello.evaluate("document.querySelectorAll('.rv-quiz input:checked').length") == 0


def test_lesson_without_media_has_no_pane_and_no_errors(page, site_url):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site_url + "intro/quiet/")
    page.wait_for_function("window.RV !== undefined")
    assert page.locator("#rv-media").is_hidden()
    assert errors == []


def test_bracket_keys_navigate(hello):
    hello.keyboard.press("]")
    hello.wait_for_url("**/intro/quiet/")
    hello.keyboard.press("[")
    hello.wait_for_url("**/intro/hello/")


def test_narrow_layout_stacks(page, site_url):
    page.set_viewport_size({"width": 700, "height": 900})
    page.goto(site_url + "intro/hello/")
    code = page.locator("#rv-code").bounding_box()
    lesson = page.locator("#rv-lesson").bounding_box()
    assert lesson["y"] >= code["y"] + code["height"] - 1


def test_theme_toggle_sets_attribute(hello):
    hello.click('.rv-rail-btn[data-panel="settings"]')
    hello.click('.rv-theme[data-theme="dark"]')
    assert hello.evaluate("document.documentElement.dataset.theme") == "dark"
    hello.click('.rv-theme[data-theme="auto"]')
    assert hello.evaluate("document.documentElement.dataset.theme") is None
