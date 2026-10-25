# Releasing the engine

A maintainer's runbook. Each release follows it. Steps marked *Untested* have not yet been run from this doc. When a step turns out to be wrong or missing, fix it in a pull request. Steps 1–3 can be fixed in the release PR itself. Steps 4–6 run after the release PR merges, so fix them in a separate PR, or at the latest in the next release's PR.

## What a release is

A release is an annotated tag `vX.Y.Z` on `main`, a GitHub release of the same name, and `revision-engine` X.Y.Z on PyPI: an sdist and a wheel built from the tag, uploaded to TestPyPI first and installed from there before they go to PyPI. CI does all of it when a release PR merges (step 4). Content repositories install the engine with `pip install revision-engine==X.Y.Z`, or a version range, or by tag:

```bash
pip install "revision-engine @ git+https://github.com/mtibbits/reVision@vX.Y.Z"
```

The **release PR** is the pull request that carries the version bump. It can be a bump-only PR or the last change PR of the release.

## Files that carry the version

<!-- tests/test_release_doc.py derives the tracked files that contain the current version and requires this list to equal them, and checks that the three agree. -->
- `pyproject.toml`: `version = "X.Y.Z"`
- `revision_engine/__init__.py`: `__version__ = "X.Y.Z"`
- `README.md`: the install line, `…/reVision@vX.Y.Z"`

## One-time setup

Maintainer actions outside the repository, done once before the first upload:

- On pypi.org and on test.pypi.org, add a pending trusted publisher: owner `mtibbits`, repository `reVision`, workflow `test.yml`, environment `pypi` on PyPI and `testpypi` on TestPyPI. A pending publisher does not reserve the name; the first upload does.
- On GitHub (Settings › Environments), create the environments `testpypi` and `pypi`, each with a deployment-branch policy of `main` only. This is required: without it, a same-repository `pull_request` run of `test.yml` can reach either publisher.
- Optional: a required reviewer on `pypi`. It pauses the run between `smoke` and `pypi` until approved.

## Steps

1. **Bump the version** in every file listed above, in the release PR. Past bump commits were titled `docs: version X.Y.Z` and `chore: release X.Y.Z`; no title is required.
   *Untested: not yet run from this doc.*

2. **Golden manifest.** Any PR that changes the built output regenerates `tests/golden/minimal.json` in the same PR, as described in README's [Developing the engine](README.md#developing-the-engine). That includes every change to `revision_engine/static/app.js` or `styles.css`, because they rename the hashed asset files. CI sets `RV_REQUIRE_GOLDEN=1`, so a stale manifest fails the PR. At release time, confirm CI is green on the release PR. If nothing in the built output changed, say so in the PR description.
   *Untested: not yet run from this doc.*

3. **Open the release PR.** Its description carries a `## Release notes` section, which becomes the GitHub release's description: a short, user-facing account of what changed, grouped under `###` subheads or bold labels such as **Fixes**, **New** and **Docs**, with issue numbers. Use no `#` or `##` heading inside it, because the next one ends the section, and leave out the install command, which step 4 appends. The job reads the description when it runs, not when the PR merges, so open the release PR yourself and check the published notes after step 4. Add a line saying "After merge: re-pin volk". When the change affects rendering, build the volk lessons against the branch before merging. With the branch's engine installed (for example the checkout's own `.venv`), run `rv2 check --root .` and then `rv2 build --root . --output <dir>` in a volk checkout of `dev/all-prs`. Outside a git checkout, such as a `git archive` export, both commands also need `--commit <sha>`. Merge once CI is green.
   *Untested: not yet run from this doc.*

4. **Tag and release (automated).** After the release PR merges, the `release` job of the `test` workflow run for that push tags the push's last commit `vX.Y.Z`, with the message `reVision engine vX.Y.Z`, and creates the GitHub release `reVision engine vX.Y.Z`. Its description is the PR's `## Release notes` section followed by the install command. The job runs only after the `test` and `browsers` jobs pass. A push that does not change the version, or changes it to a version that is not `X.Y.Z` (such as `X.Y.Z.dev0`), makes the job do nothing. A tag or release that already exists is left as it is.

   To see that it ran, list the `test` runs for the commit the release PR landed as, open that push run's `release` job, then run the commands in [Checking a release](#checking-a-release). Replace `<N>` with the release PR's number:

   ```bash
   oid=$(gh pr view <N> -R mtibbits/reVision --json mergeCommit -q .mergeCommit.oid)
   gh run list -R mtibbits/reVision --workflow test --commit "$oid"
   ```

   - **The job failed after tagging** because the PR description has no `## Release notes` section: add the section and re-run the run's failed jobs (`gh run rerun <run-id> --failed -R mtibbits/reVision`). The re-run finds the tag in place and creates only the release.
   - **The `release` job was skipped** because another job failed on the bump push: if that failure passes on a re-run, re-run the run's failed jobs, which runs `release` too. If the fix needed new commits, the push that brings them does not change the version, so the job does nothing; use the fallback and tag `main` itself, then finish with step 5, which includes the upload.
   - **The job failed because the version went down:** the version on `main` is wrong. Fix it in a new PR.
   - **The job failed because the tag already tags another commit:** if you placed that tag by hand with the fallback, nothing is wrong; finish with step 5: the release if it is missing, and the upload if the version is not on PyPI ([Checking a release](#checking-a-release)). Otherwise the version on `main` is wrong: fix it in a new PR. Never move or re-create the tag.
   - **Any other failure:** use the fallback.

   After `release`, the jobs `dist` → `testpypi` → `smoke` → `pypi` build from the tag and upload. `dist` builds the sdist and wheel from `vX.Y.Z` and stops before any upload when the built version is not exactly `X.Y.Z`. `testpypi` uploads both files to TestPyPI. `smoke` installs `revision-engine==X.Y.Z` from TestPyPI in a fresh venv and requires `rv2 --version` to print `rv2 X.Y.Z`. `pypi` uploads the same files to PyPI, and runs only if `smoke` passed. It first checks the files' sha256 digests against the ones `dist` recorded, because `smoke` runs code from TestPyPI. A version can never be uploaded twice to either index.

   - **`testpypi` or `pypi` failed with an OIDC or "publisher" error:** the [one-time setup](#one-time-setup) is missing or wrong. Fix it, then re-run the run's failed jobs.
   - **An upload failed because a file already exists:** if only one of the two files reached that index, upload the other by hand (step 5). Never re-upload a file that is already there.
   - **No file of the version reached PyPI:** upload by hand at once (step 5). If that is not possible the same day, revert README step 1 to the by-tag install in a PR: README must not send readers to an unclaimed name.
   - **TestPyPI is down or the project is gone:** upload to PyPI by hand (step 5), skipping TestPyPI, after installing the built wheel in a fresh venv and checking that `rv2 --version` prints `rv2 X.Y.Z`.
   - **`smoke` failed:** if its log shows the index had not yet served the version, re-run the run's failed jobs. Otherwise the build is bad, and it is on TestPyPI only. Fix it in a new PR with the next patch version, since TestPyPI never takes the same version twice. The `vX.Y.Z` tag and GitHub release stay: edit the release to say this version is not on PyPI and to name the next one. A content repository pinning `==X.Y.Z` gets "no matching distribution" and should install by tag. On the first PyPI release, also apply the "no file reached PyPI" README remedy.
   - **A bad version reached PyPI:** yank it on pypi.org and release the next patch version. Never delete it.

   *Untested: the automated path has not yet run for a release.*

   Fallback, by hand. Tag promptly, before any other PR merges to `main`. Until the tag exists, README's install line names a tag that is not there. Put the tag on the commit the release PR landed as on `main`, which is its merge commit or its squash commit. Replace `<N>` with the release PR's number:

   ```bash
   git fetch origin
   oid=$(gh pr view <N> -R mtibbits/reVision --json mergeCommit -q .mergeCommit.oid)
   git tag -a vX.Y.Z -m "reVision engine vX.Y.Z" "$oid"
   git push origin vX.Y.Z
   ```

   If other PRs have merged first, still tag the release PR's commit. Their changes ship in the next version.

   If `main` already carries a version that was never tagged, because its bump merged and step 4 was skipped, tag `main` itself rather than the old bump commit. Do this only when the `test` and `browsers` jobs are green on `main` and the version files there still name that version. Everything merged since the last tag then ships in this version, so the step 5 notes cover all of it.

5. **Fallback: create the GitHub release, and upload, by hand**, when step 4's jobs did not. Save the description in a notes file: the PR's `## Release notes` section, plus what else merged since the last tag when you tagged `main` itself, followed by `Install:` and the install command from [What a release is](#what-a-release-is) in a `bash` code block:

   ```bash
   gh release create vX.Y.Z -R mtibbits/reVision --verify-tag --title "reVision engine vX.Y.Z" --notes-file notes.md
   ```

   Keep `notes.md`, and step 6's `pr.md`, outside both checkouts so they are never committed; give their path if you run the command elsewhere.

   When the upload jobs did not run (for example, the tag was placed by hand), build from the tag in a clean export and check the build, then upload to TestPyPI, run the fresh-venv check from [Checking a release](#checking-a-release) against TestPyPI, and upload to PyPI. For the TestPyPI check, take no dependency from TestPyPI, where anyone can upload anything: in the fresh venv, first `pip install -c ci-constraints-requirements.txt pyyaml pygments jinja2 markdown-it-py` from PyPI, then `pip install --no-deps --index-url https://test.pypi.org/simple/ revision-engine==X.Y.Z`. Skip the TestPyPI leg only under step 4's "TestPyPI is down" bullet. The first upload needs an account-scoped API token, since no project exists yet; use project-scoped tokens after that. With `build` and `twine` installed:

   ```bash
   mkdir <dir> && git archive vX.Y.Z | tar -x -C <dir> && cd <dir>
   python -m build
   python tools/release.py dist --version X.Y.Z --dir dist
   twine upload --repository testpypi dist/*
   # the fresh-venv check against TestPyPI passes, then:
   twine upload dist/*
   ```

   *Untested: not yet run from this doc.*

6. **Re-pin the consumer.** `mtibbits/volk` installs the engine in `.github/workflows/publish_docs.yml` on its `dev/all-prs` branch, in the step "Install reVision engine". In a volk clone, on a branch off `dev/all-prs` named `chore/revision-engine-vX.Y.Z` (the name past re-pins used), change that step's tag to `vX.Y.Z`, commit, push with `git push -u origin chore/revision-engine-vX.Y.Z`, and open the PR. volk is a fork, so name the repository, base and head explicitly. The PR description, saved in `pr.md`, says what the release changes in the lessons and links the release:

   ```bash
   gh pr create -R mtibbits/volk --base dev/all-prs --head chore/revision-engine-vX.Y.Z --title "ci: build reVision lessons with engine vX.Y.Z" --body-file pr.md
   ```

   A worktree keeps an existing clone's branch and changes out of the way: `git worktree add -b chore/revision-engine-vX.Y.Z <dir> origin/dev/all-prs`. On Windows, volk tracks both `cmake/toolchains/` and `cmake/Toolchains/`, which collide on a case-insensitive filesystem, so a fresh checkout shows some toolchain files as modified. Stage only the workflow file.

   On that PR, volk's "Check reVision lessons" step installs the engine from the new tag and runs `rv2 check`, so a green check shows the tag installs. The published lessons use the new engine only once this PR merges, so follow it until it does.

## Checking a release

The tag is on the remote when the first command exits 0; exit 2 means it is absent. The GitHub release exists when the second exits 0; exit 1 means it is absent. The version is on PyPI when the third exits 0 and prints `200`, and absent when it exits 22 and prints `404`; anything else (a 5xx, or `000` when there is no connection) is undetermined, so run it again. The fourth checks TestPyPI the same way.

```bash
git ls-remote --exit-code --tags origin refs/tags/vX.Y.Z
gh release view vX.Y.Z -R mtibbits/reVision
curl -fsS -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/revision-engine/X.Y.Z/json
curl -fsS -o /dev/null -w '%{http_code}\n' https://test.pypi.org/pypi/revision-engine/X.Y.Z/json
```

To check that the release installs, use a fresh venv outside any checkout. `rv2 --version` prints `rv2 X.Y.Z`. On Windows the paths are `<dir>\Scripts\python` and `<dir>\Scripts\rv2`:

```bash
python -m venv <dir>
<dir>/bin/python -m pip install revision-engine==X.Y.Z
<dir>/bin/rv2 --version
```

Between releases, `main`'s README may describe changes that are not released yet, and `rv2 --version` reports the last bumped version for them.
