# reVision²

A static-site build tool for teaching code by example. A reader sees a real source
file on the left and a lesson about it on the right. Phrases in the lesson box the
code they describe. A narration track drives the same boxes on a timeline.

Install with `pip install revision-engine`, add a `revision.yaml` and a
`docs/revision/` folder to the repository you want to teach, and run `rv2 build`.
Revision control, revisited.

## Add reVision to a repository

1. Install the engine. Until it is on PyPI, pin a release tag:
   `pip install "revision-engine @ git+https://github.com/mtibbits/reVision@v0.1.3"`.
   Graphviz (`dot`) must be on the PATH for diagrams.
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
| `rv2 check` | Runs every validation without writing. Use it as a pre-commit hook. |
| `rv2 serve` | Builds to a temp folder, serves on localhost, rebuilds on change. |
| `rv2 narrate LESSON [--model voice.onnx]` | Synthesizes `narration.yaml` with Piper into audio plus `cues.json`. Commit both. |

For `narrate`, `pip install piper-tts` and download a voice (`.onnx` plus its `.onnx.json`) from
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices); the example lesson uses
`en_US-lessac-medium`. Without `--model` the voice comes from the lesson's `voice`, then the project's
`narration.voice`, and the model is `<voice>.onnx` in `$RV2_VOICES` or `~/piper-voices`. `--silent` writes a
silent placeholder track with plausible timings when Piper is unavailable.

`revision` is an alias for `rv2`.

## Writing a lesson

- `lesson.md` starts with front matter: `title`, `file` (the source file shown), and optionally
  `summary`, `start` (the anchor boxed on load), `media`, and `voice`.
- `anchors.yaml` names code regions. Each anchor uses one form: `from`/`to` (a line containing
  `from`, then the first later line matching the `to` regex), `match` (one line), or
  `lines: 88-92`. Add `variant: true` and a `label` to list it in the Variants panel.
- `within: <anchor>` scopes `match`, `from` and `to` to another anchor's lines, for files where the
  same body appears twice (aligned and unaligned variants).
- In the body, `[phrase](@anchor)` boxes a region, `[name](!intrinsic)` links a SIMD intrinsic to
  its vendor documentation (Intel and Arm names to their intrinsic's page, RISC-V Vector names to
  their section of the v1.0 intrinsic reference; a bare `` `name` `` in inline code auto-links
  too), `![Alt](diagrams/x.dot)` inlines a Graphviz diagram (give a node `id="anchor-name"` to
  make it hover and click like a phrase), and a fenced block with the language `quiz` adds a
  page-local knowledge check.
- `narration.yaml` is a list of segments: `text` plus what to `show`, and optionally a `diagram`
  and `node` to bring into view. Timings are derived by `rv2 narrate`, never typed. If the words
  change and `narrate` is not rerun, `build` fails with the diff.

## Deploy

GitHub Actions: install Python and Graphviz, `pip install revision-engine`, `rv2 build`, then
upload `public/` with `actions/upload-pages-artifact`. GitLab CI: the same three commands in a
`pages` job with `public/` as its artifact. `.github/workflows/demo.yml` in this repository builds
`examples/minimal/` that way.

## Developing the engine

```bash
python -m venv .venv && source .venv/Scripts/activate   # or .venv/bin/activate
python -m pip install -e ".[dev]" && python -m playwright install chromium
python -m pytest --browser chromium
```

The golden test compares the built example site byte-for-byte, except that each diagram is reduced to its nodes (ids, anchor stamps, labels) and edges (endpoints, labels), so Graphviz layout and fonts do not matter.
That reduction was verified identical on Graphviz 16.1.0 (Windows) and on Ubuntu 22.04's `graphviz` 2.42.2 package (which reports itself as 2.43.0); a Graphviz that changes node ids, anchor stamps, edges or labels fails the test.
CI installs Ubuntu's `graphviz` package (2.42.2 on `ubuntu-latest`) and sets `RV_REQUIRE_GOLDEN=1`, so a skipped or missing golden test fails the job.
After an intentional rendering change, update your venv (`python -m pip install -U -e ".[dev]"`) so Pygments, markdown-it-py and Jinja2 match CI, then regenerate with `RV_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py`.

## License

MIT.
