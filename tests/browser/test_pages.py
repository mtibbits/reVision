import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

MEDIA_READY = "document.getElementById('rv-media-el').readyState >= 1"
AT_5_5 = "Math.abs(document.getElementById('rv-media-el').currentTime - 5.5) < 0.01"
MAIN_FN = '.rv-anchor[data-anchor="main-fn"]'
CALL_SITE = '.rv-anchor[data-anchor="call-site"]'
SEG_1 = '.rv-seg[data-index="1"]'
SETTLED_ON_SEG_1 = (
    "(() => { const m = document.getElementById('rv-media-el'); return !m.seeking && window.RV.activeSegment() === 1; })()"
)


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


def _goto_collecting_errors(page, url):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    return errors


def _assert_page_works(page, errors):
    assert errors == []
    assert page.evaluate("typeof window.RV") == "object"
    page.check('input[name="q0"][value="0"]')
    assert "Correct" in page.locator('.rv-q[data-answer="0"] .rv-q-feedback').inner_text()


def test_malformed_fragment_keeps_page_working(page, site_url):
    errors = _goto_collecting_errors(page, site_url + "intro/hello/#%")
    _assert_page_works(page, errors)
    assert boxed(page) == [5, 6, 7, 8]


def _assert_seeked_to_5_5(page):
    try:
        page.wait_for_function(AT_5_5, timeout=3000)
    except PlaywrightTimeoutError:
        pass  # the assertions below name what went wrong
    assert page.evaluate("document.getElementById('rv-media-el').currentTime") == pytest.approx(5.5, abs=0.01)
    assert page.evaluate("window.RV.activeSegment()") == 1
    assert boxed(page) == [7]


def test_fragment_t_seeks_after_load(hello):
    hello.wait_for_function(MEDIA_READY)
    hello.evaluate("location.hash = '#t=5.5'")
    _assert_seeked_to_5_5(hello)
    assert hello.errors == []


def test_fragment_t_seeks_on_load(page, site_url):
    page.goto(site_url + "intro/hello/#t=5.5")
    page.wait_for_function("window.RV !== undefined")
    page.wait_for_function(MEDIA_READY)
    _assert_seeked_to_5_5(page)


def test_non_finite_t_fragment_keeps_page_working(page, site_url):
    errors = _goto_collecting_errors(page, site_url + "intro/hello/#t=Infinity")
    page.wait_for_function(MEDIA_READY)
    _assert_page_works(page, errors)
    assert boxed(page) == [5, 6, 7, 8]
    page.evaluate("document.getElementById('rv-media-el').currentTime = window.RV.data.cues[0].start + 0.05")
    page.wait_for_function("window.RV.activeSegment() === 0", timeout=3000)


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


def _pin_main_fn(page):
    page.click(MAIN_FN)
    assert boxed(page) == list(range(10, 16))


def _assert_unpinned(page):
    assert page.evaluate("window.RV.pinned") is None
    assert page.evaluate("document.querySelectorAll('.rv-pinned').length") == 0


def _hover_call_site_and_leave(page):
    page.hover(CALL_SITE)
    page.mouse.move(0, 0)


def test_fragment_t_seek_releases_pin(hello):
    hello.wait_for_function(MEDIA_READY)
    _pin_main_fn(hello)
    hello.evaluate("location.hash = '#t=5.5'")
    _assert_seeked_to_5_5(hello)
    _assert_unpinned(hello)
    assert hello.evaluate("location.hash") == "#t=5.5"
    _hover_call_site_and_leave(hello)
    assert boxed(hello) == [7]
    hello.keyboard.press("Escape")
    assert boxed(hello) == [7]
    assert hello.evaluate("location.hash") == "#t=5.5"
    assert hello.errors == []


def test_transcript_click_releases_pin(hello):
    _pin_main_fn(hello)
    hello.click(SEG_1)
    _assert_unpinned(hello)
    assert boxed(hello) == [7]
    assert hello.evaluate("location.hash") == ""
    _hover_call_site_and_leave(hello)
    assert boxed(hello) == [7]


def test_transcript_click_on_active_segment_releases_pin(hello):
    hello.wait_for_function(MEDIA_READY)
    hello.click(SEG_1)
    hello.wait_for_function(SETTLED_ON_SEG_1)
    assert boxed(hello) == [7]
    _pin_main_fn(hello)
    assert hello.evaluate("window.RV.activeSegment()") == 1
    hello.click(SEG_1)
    _assert_unpinned(hello)
    assert boxed(hello) == [7]
    assert hello.evaluate("window.RV.activeSegment()") == 1
    assert hello.evaluate("location.hash") == ""


def test_playback_cue_keeps_pinned_box(hello):
    hello.wait_for_function(MEDIA_READY)
    _pin_main_fn(hello)
    hello.evaluate("document.getElementById('rv-media-el').currentTime = window.RV.data.cues[1].start + 0.05")
    hello.wait_for_function("window.RV.activeSegment() === 1", timeout=3000)
    assert boxed(hello) == list(range(10, 16))
    assert hello.evaluate("window.RV.pinned") == "main-fn"
    assert "rv-active" in hello.locator(SEG_1).get_attribute("class").split()
    hello.keyboard.press("Escape")
    assert boxed(hello) == [7]
    assert hello.evaluate("location.hash") == ""
    _assert_unpinned(hello)


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


def test_quiz_forgets_after_back(page, site_url):
    page.add_init_script('addEventListener("pageshow", e => { (window.__rvShows ||= []).push(e.persisted); })')
    errors = _goto_collecting_errors(page, site_url + "intro/hello/")
    page.wait_for_function("window.RV !== undefined")
    page.check('input[name="q0"][value="0"]')
    page.check('input[name="q1"][value="2"]')
    assert page.locator('.rv-q[data-answer="0"] .rv-q-feedback').is_visible()
    page.goto(site_url + "intro/quiet/")
    page.go_back()
    page.wait_for_url("**/intro/hello/")
    page.wait_for_function("window.RV !== undefined && Array.isArray(window.__rvShows)")
    assert page.evaluate("window.__rvShows") == [False], (
        "page came from the back/forward cache; Playwright normally disables it in Chromium"
    )
    # the hello quiz: two questions of three choices
    assert page.evaluate("document.querySelectorAll('.rv-quiz input[type=radio]').length") == 6
    assert page.evaluate("document.querySelectorAll('.rv-quiz input:checked').length") == 0
    # Belt and braces: these catch a future change that grades on load.
    assert page.locator(".rv-q-feedback").count() == 2
    assert all(f.is_hidden() for f in page.locator(".rv-q-feedback").all())
    assert page.locator(".rv-quiz-score").count() == 1
    assert page.locator(".rv-quiz-score").is_hidden()
    assert errors == []


def test_quiz_feedback_adds_one_line_whether_right_or_wrong(hello):
    q = hello.locator('.rv-q[data-answer="0"]')
    hello.check('input[name="q0"][value="1"]')
    wrong = q.bounding_box()["height"]
    hello.check('input[name="q0"][value="0"]')
    assert "Correct" in q.locator(".rv-q-feedback").inner_text()
    assert q.evaluate("el => getComputedStyle(el).display") == "block"
    assert q.bounding_box()["height"] == wrong


def test_quiz_text_reads_as_written(hello):
    assert hello.locator(".rv-q legend").all_inner_texts() == [
        "1. What does add(2, 3) return?",
        "2. Which function is the program's entry point?",
    ]
    # Choices are shuffled on load, so compare each question's set of choices.
    labels = [sorted(t.strip() for t in fs.locator("label").all_inner_texts()) for fs in hello.locator(".rv-q").all()]
    assert labels == [sorted(["5", "6", "23"]), sorted(["add", "main", "printf"])]


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


def test_splitter_reclamps_when_window_shrinks(page, site_url):
    page.set_viewport_size({"width": 1400, "height": 800})
    page.goto(site_url + "intro/hello/")
    page.wait_for_function("window.RV !== undefined")
    page.evaluate("window.RV.setCodeWidth(1100)")
    assert page.locator("#rv-code").bounding_box()["width"] > 1000
    page.set_viewport_size({"width": 1000, "height": 800})
    page.wait_for_timeout(100)
    assert page.locator("#rv-lesson").bounding_box()["width"] > 200


def test_theme_toggle_sets_attribute(hello):
    hello.click('.rv-rail-btn[data-panel="settings"]')
    hello.click('.rv-theme[data-theme="dark"]')
    assert hello.evaluate("document.documentElement.dataset.theme") == "dark"
    hello.click('.rv-theme[data-theme="auto"]')
    assert hello.evaluate("document.documentElement.dataset.theme") is None
