"""Quiz choices show in a random order on each load; grading follows the choice, and marked or two-choice questions keep theirs."""

from __future__ import annotations

import pytest

from .conftest import build_example, open_lesson, serve

OLD_Q2 = "    answer: 1\n"
NEW_Q2 = "    answer: 1\n    shuffle: false\n"
# Choices quoted on purpose: unquoted yes/no would load as YAML booleans.
OLD_END = "    shuffle: false\n```\n"
NEW_END = "    shuffle: false\n  - q: Is 5 odd?\n    choices: ['odd', 'even']\n    answer: 0\n```\n"

AUTHORED = [["5", "6", "23"], ["add", "main", "printf"]]
# Fisher-Yates with Math.random() == 0 turns [a, b, c] into [b, c, a].
ROTATED = [c[1:] + c[:1] for c in AUTHORED]


@pytest.fixture(scope="module")
def fixed_url(tmp_path_factory):
    def edit(src):
        lesson = src / "docs/revision/chapters/01-intro/lessons/01-hello/lesson.md"
        text = lesson.read_text(encoding="utf-8")
        assert text.count(OLD_Q2) == 1
        text = text.replace(OLD_Q2, NEW_Q2)
        assert text.count(OLD_END) == 1
        lesson.write_text(text.replace(OLD_END, NEW_END), encoding="utf-8")

    with serve(build_example(tmp_path_factory, "fixed", edit=edit)) as url:
        yield url + "intro/hello/"


@pytest.fixture
def open_quiz(page):
    def go(url: str, r: float):
        return open_lesson(page, url, init_script=f"Math.random = () => {r}")

    return go


def labels(page):
    return [[t.strip() for t in fs.locator("label").all_inner_texts()] for fs in page.locator(".rv-q").all()]


def test_quiz_choices_reorder_when_random_says_so(open_quiz, site_url):
    page = open_quiz(site_url + "intro/hello/", 0)
    assert labels(page) == ROTATED
    assert page.errors == []


def test_quiz_choices_can_show_authored_order(open_quiz, site_url):
    page = open_quiz(site_url + "intro/hello/", 0.999999)
    assert labels(page) == AUTHORED
    assert page.errors == []


def test_quiz_grades_the_choice_not_its_position(open_quiz, site_url):
    page = open_quiz(site_url + "intro/hello/", 0)
    assert labels(page) != AUTHORED  # otherwise position and choice agree and this proves nothing
    for i, answer in enumerate(["5", "main"]):
        fs = page.locator(".rv-q").nth(i)
        feedback = fs.locator(".rv-q-feedback")
        for text in AUTHORED[i]:
            if text == answer:
                continue
            fs.get_by_label(text, exact=True).click()
            assert feedback.inner_text() == "Not quite. Try another answer."
        fs.get_by_label(answer, exact=True).click()
        assert feedback.inner_text() == "Correct."
    page.locator(".rv-quiz button").click()
    assert page.locator(".rv-quiz-score").inner_text() == "2 of 2 correct."
    assert page.errors == []


def test_quiz_marked_and_two_choice_questions_keep_authored_order(open_quiz, fixed_url):
    page = open_quiz(fixed_url, 0)
    # Question 1 shuffling on the same page shows the stubbed randomness was live.
    assert labels(page) == [ROTATED[0], AUTHORED[1], ["odd", "even"]]
    assert page.errors == []


def test_quiz_without_javascript_lists_authored_order(browser, site_url):
    ctx = browser.new_context(java_script_enabled=False)
    try:
        page = ctx.new_page()
        page.goto(site_url + "intro/hello/")
        assert labels(page) == AUTHORED
    finally:
        ctx.close()
