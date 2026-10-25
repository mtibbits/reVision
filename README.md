# reVision²

A static-site build tool for teaching code by example. A reader sees a real source
file on the left and a lesson about it on the right. Phrases in the lesson box the
code they describe. A narration track drives the same boxes on a timeline.

Install the engine as in [step 1](#add-revision-to-a-repository) below, add a `revision.yaml` and a
`docs/revision/` folder to the repository you want to teach, and run `rv2 build`.
Revision control, revisited.

## Add reVision to a repository

1. Install the engine. Until it is on PyPI, pin a release tag:
   `pip install "revision-engine @ git+https://github.com/mtibbits/reVision@v0.2.0"`.
   Graphviz (`dot`) must be on the PATH for diagrams, and `git` for the tagged install.
2. Create `revision.yaml` at the repository root:
   ```yaml
   site: { title: My project by example, base_url: "" }
   repo: { url: https://github.com/you/project, host: github }   # or host: gitlab
   content: docs/revision
   output: public
   ```
3. Create `docs/revision/curriculum.yaml` and one lesson folder holding `lesson.md`
   and `anchors.yaml`. Copy `examples/minimal/docs/revision/` from this repository to start.
4. `rv2 check` to validate, `rv2 serve` to preview, `rv2 build` to write `public/`.
   `--root` must be the repository's git root; the code pane's "open at commit" link is built from it.

## Commands

| Command | What it does |
|---|---|
| `rv2 build` | Writes the site into the output folder. No network. Same commit, same bytes. |
| `rv2 check [--strict] [--list-unlinked]` | Runs every validation without writing. Use it as a pre-commit hook or CI gate. `--strict` exits 1 if any warning is reported; `--list-unlinked` lists each inline code span (not fenced blocks) that matches no vendor intrinsic table, per lesson, without changing the exit code. |
| `rv2 serve` | Builds to a temp folder, serves on localhost, rebuilds on change. |
| `rv2 narrate LESSON [--model voice.onnx]` | Synthesizes `narration.yaml` with Piper into audio plus `cues.json`. Commit both. |

For `narrate`, `pip install piper-tts` and download a voice (`.onnx` plus its `.onnx.json`) from
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices); the example lesson uses
`en_US-lessac-medium`. Without `--model` the voice comes from `--voice`, then the lesson's `narration.yaml`
`voice`, then its front matter `voice`, then the project's `narration.voice`, and the model is `<voice>.onnx`
directly in `$RV2_VOICES` or `~/piper-voices`. A voice is a name, not a path: it may use only ASCII letters,
digits, `_`, `-` and `.`, not starting with `-` or `.`, and `rv2 narrate` refuses anything else. To use a model
file somewhere else, pass `--model`. `--silent` writes a silent placeholder track with plausible timings when
Piper is unavailable.

`revision` is an alias for `rv2`.

## Writing a lesson

- `lesson.md` starts with front matter: `title`, `file` (the source file shown), and optionally
  `summary`, `start` (the anchor boxed on load), `media`, and `voice` (a voice name, not a path; see
  `narrate`).
- `anchors.yaml` names code regions. Each anchor uses one form: `from`/`to` (a line containing
  `from`, then the first later line matching the `to` regex), `match` (one line), or
  `lines: 88-92`. Add `variant: true` and a `label` to list it in the Variants panel.
- `within: <anchor>` scopes `match`, `from` and `to` to another anchor's lines, for files where the
  same body appears twice (aligned and unaligned variants).
- In the body, `[phrase](@anchor)` boxes a region, `[name](!intrinsic)` links a SIMD intrinsic to
  its vendor documentation (Intel and Arm names to their intrinsic's page, RISC-V Vector names to
  their section of the v1.0 intrinsic reference; a bare `` `name` `` in inline code auto-links
  too, except inside another link's text, where it stays plain inline code; a code span in an
  anchor phrase still links), `![Alt](diagrams/x.dot)` inlines a Graphviz diagram (give a node
  `id="anchor-name"` to make it hover and click like a phrase; a `URL`, `href` or HTML-label `HREF`
  on such a node is removed with a warning, because a click on it pins the anchor), and a fenced
  block with the language `quiz` adds a page-local knowledge check.
- In a quiz, a question's `q` and its `choices` accept one kind of markup: a backtick code span,
  which renders as inline code (not linked to vendor documentation). Anything else, raw HTML and
  backslashes included, shows as written, so a backslash does not stop a backtick from opening a
  code span. YAML does not allow an unquoted value to begin with a backtick, so single-quote a `q`
  or choice that starts with one (`` q: '`vaddq_f32` adds how many lanes?' ``); unquoted, the
  build fails with "quiz block is not valid YAML". Use single quotes, not double: inside double
  quotes YAML reads a backslash as an escape, so `` `\n` `` would lose its backslash. Inside single
  quotes, write an apostrophe twice (`''`).
- A quiz block's only top-level key is `questions`. A question accepts `q`, `choices`, `answer`
  (the index of the right choice, counting from 0) and `shuffle`; any other key fails the build
  and is named in the error, so a misspelled `shufle: false` cannot leave a question shuffled.
- Each time the page loads, a question's choices appear in a random order, so the right answer is
  not always in the same place; grading follows the choice, not its position. Add `shuffle: false`
  to a question to keep its choices in the order written, for example numeric ranges or "all of
  the above". A question with two choices (True/False) always keeps its order, so `shuffle: true`
  on one is a build warning. With JavaScript off, choices appear in the order written.
- `narration.yaml` is a list of segments: `text` plus what to `show`, and optionally a `diagram`
  and `node` to bring into view. Timings are derived by `rv2 narrate`, never typed. If the words
  change and `narrate` is not rerun, `build` fails with the diff.

## Deploy

<!-- tests/test_release_doc.py::test_deploy_runs_the_strict_check_before_building checks that each platform's recipe below runs the strict check before building. -->
GitHub Actions: install Python and Graphviz, install the engine by tag as in
[step 1](#add-revision-to-a-repository) (pip fetches it with `git`, so the runner needs `git`),
run `rv2 check --strict` so any warning fails the job before anything is published, then
`rv2 build`, and upload `public/` with `actions/upload-pages-artifact`. GitLab CI: install Python,
Graphviz and the engine the same way and run `rv2 check --strict`, then `rv2 build`, in a `pages`
job with `public/` as its artifact, on an image that has `git`.
`.github/workflows/demo.yml` in this repository builds `examples/minimal/` that way.

## Developing the engine

```bash
python -m venv .venv && source .venv/Scripts/activate   # or .venv/bin/activate
python -m pip install -e ".[dev]" -c ci-constraints-requirements.txt && python -m playwright install chromium
python -m pytest --browser chromium
python -m playwright install firefox webkit
python -m pytest tests/browser --browser firefox --browser webkit
```

The golden test compares the built example site byte-for-byte, except that each diagram is reduced to its nodes (ids, anchor stamps, labels) and edges (endpoints, labels), so Graphviz layout and fonts do not matter.
That reduction was verified identical on Graphviz 16.1.0 (Windows) and on Ubuntu 22.04's `graphviz` 2.42.2 package (which reports itself as 2.43.0); a Graphviz that changes node ids, anchor stamps, edges, or node and edge labels fails the test (graph and cluster labels and link targets are not compared).
CI runs on the pinned `ubuntu-24.04` image and installs its `graphviz` package (2.42.2). Its `test` job sets `RV_REQUIRE_GOLDEN=1` and runs the whole suite in Chromium, so a skipped or missing golden test fails the job; the gate's message is the last line of the log. A separate `browsers` job runs `tests/browser` in Firefox and WebKit without the golden gate; a test that cannot pass in one engine carries `@pytest.mark.xfail_browser(...)` naming its tracking issue, and is a strict xfail there. On a push to `main` that bumps the version, a `release` job tags and releases it after both pass; see RELEASING.md step 4.
<!-- tests/test_ci_constraints.py checks that every README line installing .[dev], here and in the fence above, contains INSTALL_CMD from tests/ci_pins.py. -->
CI installs the runtime dependencies whose output the golden test hashes (Pygments, markdown-it-py, Jinja2, PyYAML and their dependencies) at the versions pinned in `ci-constraints-requirements.txt`; `pyproject.toml` keeps floors only, so installing the engine in a content repository is unaffected. To match CI locally, run `python -m pip install -e ".[dev]" -c ci-constraints-requirements.txt`; after an intentional rendering change, regenerate with `RV_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py`. `.github/dependabot.yml` asks Dependabot to propose pin bumps; a bump that changes output reddens the golden test on its own PR, where the manifest is regenerated after review.

To cut a release, follow [RELEASING.md](RELEASING.md).

## License

MIT.
