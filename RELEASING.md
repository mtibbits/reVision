# Releasing the engine

A maintainer's runbook. Each release follows it. When a step turns out to be wrong or missing, fix it in that release's pull request.

## What a release is

A release is an annotated tag `vX.Y.Z` on `main` plus a GitHub release of the same name. Content repositories install the engine by tag:

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

1. **Bump the version** in all three files above, in the release PR. Past bump commits were titled `docs: version X.Y.Z` and `chore: release X.Y.Z`; no title is required.
   <!-- untested: not yet run from this doc; correct it in the next release's PR -->

2. **Golden manifest.** Any PR that changes the built output regenerates `tests/golden/minimal.json` in the same PR, as described in README's [Developing the engine](README.md#developing-the-engine). That includes every change to `revision_engine/static/app.js` or `styles.css`, because they rename the hashed asset files. CI sets `RV_REQUIRE_GOLDEN=1`, so a stale manifest fails the PR. At release time, confirm CI is green on the release PR. If nothing in the built output changed, say so in the PR description.
   <!-- untested: not yet run from this doc; correct it in the next release's PR -->

3. **Open the release PR** with a line saying "After merge: tag, release, re-pin volk". When the change affects rendering, build the volk lessons against the branch before merging. Merge once CI is green.
   <!-- untested: not yet run from this doc; correct it in the next release's PR -->

4. **Tag promptly**, before any other PR merges to `main`. Until the tag exists, README's install line names a tag that is not there. Put the tag on the commit the release PR landed as on `main`, which is its merge commit or its squash commit. Replace `<N>` with the release PR's number:

   ```bash
   git fetch origin
   oid=$(gh pr view <N> -R mtibbits/reVision --json mergeCommit -q .mergeCommit.oid)
   git tag -a vX.Y.Z -m "reVision engine vX.Y.Z" "$oid"
   git push origin vX.Y.Z
   ```

   If other PRs have merged first, still tag the release PR's commit. Their changes ship in the next version.

5. **Create the GitHub release** with a short, user-facing description of what changed, saved in a notes file:
   <!-- untested: not yet run from this doc; correct it in the next release's PR -->

   ```bash
   gh release create vX.Y.Z -R mtibbits/reVision --verify-tag --title "reVision engine vX.Y.Z" --notes-file notes.md
   ```

6. **Re-pin the consumer.** `mtibbits/volk` installs the engine in `.github/workflows/publish_docs.yml` on its `dev/all-prs` branch, in the step "Install reVision engine". In a volk clone, on a branch off `dev/all-prs`, change that step's tag to `vX.Y.Z`, push, and open the PR. volk is a fork, so name the repository and base explicitly. The PR description, saved in `pr.md`, says what the release changes in the lessons and links the release:
   <!-- untested: not yet run from this doc; correct it in the next release's PR -->

   ```bash
   gh pr create -R mtibbits/volk --base dev/all-prs --title "ci: build reVision lessons with engine vX.Y.Z" --body-file pr.md
   ```

   On that PR, volk's "Check reVision lessons" step installs the engine from the new tag and runs `rv2 check`, so a green check shows the tag installs. The published lessons use the new engine only once this PR merges, so follow it until it does.

## Checking a release

The tag is on the remote when this exits 0. Exit 2 means it is absent.

```bash
git ls-remote --exit-code --tags origin refs/tags/vX.Y.Z
```

Between releases, `main`'s README may describe changes that are not released yet, and `rv2 --version` reports the last bumped version for them.
