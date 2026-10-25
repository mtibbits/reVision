# Releasing the engine

A maintainer's runbook. Each release follows it. Steps marked *Untested* have not yet been run from this doc. When a step turns out to be wrong or missing, fix it in a pull request. Steps 1–3 can be fixed in the release PR itself. Steps 4–6 run after the release PR merges, so fix them in a separate PR, or at the latest in the next release's PR.

## What a release is

A release is an annotated tag `vX.Y.Z` on `main` plus a GitHub release of the same name. CI makes both when a release PR merges (step 4). Content repositories install the engine by tag:

```bash
pip install "revision-engine @ git+https://github.com/mtibbits/reVision@vX.Y.Z"
```

The engine is not published to PyPI.

The **release PR** is the pull request that carries the version bump. It can be a bump-only PR or the last change PR of the release.

## Files that carry the version

<!-- tests/test_release_doc.py derives the tracked files that contain the current version and requires this list to equal them, and checks that the three agree. -->
- `pyproject.toml`: `version = "X.Y.Z"`
- `revision_engine/__init__.py`: `__version__ = "X.Y.Z"`
- `README.md`: the install line, `…/reVision@vX.Y.Z"`

## Steps

1. **Bump the version** in every file listed above, in the release PR. Past bump commits were titled `docs: version X.Y.Z` and `chore: release X.Y.Z`; no title is required.
   *Untested: not yet run from this doc.*

2. **Golden manifest.** Any PR that changes the built output regenerates `tests/golden/minimal.json` in the same PR, as described in README's [Developing the engine](README.md#developing-the-engine). That includes every change to `revision_engine/static/app.js` or `styles.css`, because they rename the hashed asset files. CI sets `RV_REQUIRE_GOLDEN=1`, so a stale manifest fails the PR. At release time, confirm CI is green on the release PR. If nothing in the built output changed, say so in the PR description.
   *Untested: not yet run from this doc.*

3. **Open the release PR.** Its description carries a `## Release notes` section, which becomes the GitHub release's description: a short, user-facing account of what changed, grouped under `###` subheads or bold labels such as **Fixes**, **New** and **Docs**, with issue numbers. Use no `#` or `##` heading inside it, because the next one ends the section, and leave out the install command, which step 4 appends. The job reads the description when it runs, not when the PR merges, so open the release PR yourself and check the published notes after step 4. Add a line saying "After merge: re-pin volk". When the change affects rendering, build the volk lessons against the branch before merging. With the branch's engine installed (for example the checkout's own `.venv`), run `rv2 check --root .` and then `rv2 build --root . --output <dir>` in a volk checkout of `dev/all-prs`. Outside a git checkout, such as a `git archive` export, both commands also need `--commit <sha>`. Merge once CI is green.
   *Untested: not yet run from this doc.*

4. **Tag and release (automated).** After the release PR merges, the `release` job of the `test` workflow run for that push tags the push's last commit `vX.Y.Z`, with the message `reVision engine vX.Y.Z`, and creates the GitHub release `reVision engine vX.Y.Z`. Its description is the PR's `## Release notes` section followed by the install command. The job runs only after the run's other jobs pass. A push that does not change the version, or changes it to a version that is not `X.Y.Z` (such as `X.Y.Z.dev0`), makes the job do nothing. A tag or release that already exists is left as it is.

   To see that it ran, list the `test` runs for the commit the release PR landed as, open that push run's `release` job, then run the commands in [Checking a release](#checking-a-release). Replace `<N>` with the release PR's number:

   ```bash
   oid=$(gh pr view <N> -R mtibbits/reVision --json mergeCommit -q .mergeCommit.oid)
   gh run list -R mtibbits/reVision --workflow test --commit "$oid"
   ```

   - **The job failed after tagging** because the PR description has no `## Release notes` section: add the section and re-run the run's failed jobs (`gh run rerun <run-id> --failed -R mtibbits/reVision`). The re-run finds the tag in place and creates only the release.
   - **The `release` job was skipped** because another job failed on the bump push: if that failure passes on a re-run, re-run the run's failed jobs, which runs `release` too. If the fix needed new commits, the push that brings them does not change the version, so the job does nothing; use the fallback and tag `main` itself.
   - **The job failed because the version went down:** the version on `main` is wrong. Fix it in a new PR.
   - **The job failed because the tag already tags another commit:** if you placed that tag by hand with the fallback, nothing is wrong; finish with step 5 if the release is missing. Otherwise the version on `main` is wrong: fix it in a new PR. Never move or re-create the tag.
   - **Any other failure:** use the fallback.

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

5. **Fallback: create the GitHub release by hand**, when step 4's job did not. Save the description in a notes file: the PR's `## Release notes` section, plus what else merged since the last tag when you tagged `main` itself, followed by `Install:` and the install command from [What a release is](#what-a-release-is) in a `bash` code block:

   ```bash
   gh release create vX.Y.Z -R mtibbits/reVision --verify-tag --title "reVision engine vX.Y.Z" --notes-file notes.md
   ```

   Keep `notes.md`, and step 6's `pr.md`, outside both checkouts so they are never committed; give their path if you run the command elsewhere.

6. **Re-pin the consumer.** `mtibbits/volk` installs the engine in `.github/workflows/publish_docs.yml` on its `dev/all-prs` branch, in the step "Install reVision engine". In a volk clone, on a branch off `dev/all-prs` named `chore/revision-engine-vX.Y.Z` (the name past re-pins used), change that step's tag to `vX.Y.Z`, commit, push with `git push -u origin chore/revision-engine-vX.Y.Z`, and open the PR. volk is a fork, so name the repository, base and head explicitly. The PR description, saved in `pr.md`, says what the release changes in the lessons and links the release:

   ```bash
   gh pr create -R mtibbits/volk --base dev/all-prs --head chore/revision-engine-vX.Y.Z --title "ci: build reVision lessons with engine vX.Y.Z" --body-file pr.md
   ```

   A worktree keeps an existing clone's branch and changes out of the way: `git worktree add -b chore/revision-engine-vX.Y.Z <dir> origin/dev/all-prs`. On Windows, volk tracks both `cmake/toolchains/` and `cmake/Toolchains/`, which collide on a case-insensitive filesystem, so a fresh checkout shows some toolchain files as modified. Stage only the workflow file.

   On that PR, volk's "Check reVision lessons" step installs the engine from the new tag and runs `rv2 check`, so a green check shows the tag installs. The published lessons use the new engine only once this PR merges, so follow it until it does.

## Checking a release

The tag is on the remote when the first command exits 0; exit 2 means it is absent. The GitHub release exists when the second exits 0; exit 1 means it is absent.

```bash
git ls-remote --exit-code --tags origin refs/tags/vX.Y.Z
gh release view vX.Y.Z -R mtibbits/reVision
```

Between releases, `main`'s README may describe changes that are not released yet, and `rv2 --version` reports the last bumped version for them.
