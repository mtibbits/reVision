from revision_engine.intrinsics import lookup, vendors


def test_intel_name_links_to_intrinsics_guide():
    url = lookup("_mm256_fmadd_ps")
    assert url is not None and "intel.com" in url and url.endswith("#text=_mm256_fmadd_ps")


def test_arm_name_links_to_arm_developer():
    url = lookup("vmlaq_f32")
    assert url is not None and "developer.arm.com" in url and url.endswith("/vmlaq_f32")


def test_unknown_returns_none():
    assert lookup("printf") is None
    assert lookup("") is None


def test_vendors_listed():
    assert set(vendors()) == {"intel", "arm"}
