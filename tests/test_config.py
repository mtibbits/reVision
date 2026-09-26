import pytest

from revision_engine.config import load_curriculum, load_project_config
from revision_engine.errors import BuildError


def test_loads_project_config(repo):
    cfg = load_project_config(repo)
    assert cfg.site.title == "T"
    assert cfg.repo.host == "github"
    assert cfg.content == repo / "docs" / "revision"
    assert cfg.output == repo / "public"
    assert cfg.voice == "en_US-lessac-medium"


def test_defaults_for_optional_keys(repo):
    repo.write("revision.yaml", "site:\n  title: T\nrepo:\n  url: https://gitlab.example/a/b\n  host: gitlab\n")
    cfg = load_project_config(repo)
    assert cfg.site.base_url == ""
    assert cfg.content == repo / "docs" / "revision"
    assert cfg.output == repo / "public"
    assert cfg.voice == "en_US-lessac-medium"


def test_missing_repo_url_names_key(repo):
    repo.write("revision.yaml", "site:\n  title: T\nrepo:\n  host: github\n")
    with pytest.raises(BuildError, match=r"revision\.yaml: repo\.url is required"):
        load_project_config(repo)


def test_bad_host_rejected(repo):
    repo.write("revision.yaml", "site:\n  title: T\nrepo:\n  url: u\n  host: bitbucket\n")
    with pytest.raises(BuildError, match="repo.host must be one of: github, gitlab"):
        load_project_config(repo)


def test_missing_config_file(tmp_path):
    with pytest.raises(BuildError, match="revision.yaml not found"):
        load_project_config(tmp_path)


def test_loads_curriculum(repo):
    repo.write("docs/revision/chapters/01-a/lessons/01-b/lesson.md", "---\ntitle: x\nfile: f\n---\nbody\n")
    repo.write(
        "docs/revision/curriculum.yaml",
        "chapters:\n  - slug: a\n    title: A\n    lessons:\n      - slug: b\n        title: B\n"
        "        path: chapters/01-a/lessons/01-b\n",
    )
    cur = load_curriculum(load_project_config(repo))
    assert cur.chapters[0].slug == "a"
    lesson = cur.chapters[0].lessons[0]
    assert lesson.slug == "b"
    assert lesson.type == "lesson"
    assert lesson.path == repo / "docs/revision/chapters/01-a/lessons/01-b"


def test_lesson_path_must_contain_lesson_md(repo):
    repo.write(
        "docs/revision/curriculum.yaml",
        "chapters:\n  - slug: a\n    title: A\n    lessons:\n      - slug: b\n        title: B\n        path: nowhere\n",
    )
    with pytest.raises(BuildError, match=r"chapters\[0\]\.lessons\[0\]\.path: .*lesson\.md not found"):
        load_curriculum(load_project_config(repo))


def test_bad_slug_rejected(repo):
    repo.write("docs/revision/curriculum.yaml", "chapters:\n  - slug: 'Bad Slug'\n    title: A\n    lessons: []\n")
    with pytest.raises(BuildError, match=r"chapters\[0\]\.slug: 'Bad Slug' is not a slug"):
        load_curriculum(load_project_config(repo))


def test_duplicate_lesson_slug_rejected(repo):
    repo.write("docs/revision/chapters/01-a/lessons/01-b/lesson.md", "---\ntitle: x\nfile: f\n---\n")
    repo.write(
        "docs/revision/curriculum.yaml",
        "chapters:\n  - slug: a\n    title: A\n    lessons:\n"
        "      - {slug: b, title: B, path: chapters/01-a/lessons/01-b}\n"
        "      - {slug: b, title: C, path: chapters/01-a/lessons/01-b}\n",
    )
    with pytest.raises(BuildError, match="duplicate lesson slug 'b'"):
        load_curriculum(load_project_config(repo))
