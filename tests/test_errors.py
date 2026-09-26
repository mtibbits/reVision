from revision_engine.errors import BuildError, Report


def test_build_error_is_exception():
    assert issubclass(BuildError, Exception)


def test_report_collects_warnings_in_order():
    r = Report()
    r.warn("first")
    r.warn("second")
    assert r.warnings == ["first", "second"]
