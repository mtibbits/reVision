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


NEW_INTEL = ["_mm_or_ps", "_mm_moveldup_ps", "_mm_movehdup_ps", "_mm_addsub_ps", "_mm256_moveldup_ps",
             "_mm256_movehdup_ps", "_mm256_shuffle_ps", "_mm256_addsub_ps", "_mm256_fmaddsub_ps",
             "_mm512_store_ps", "_mm512_storeu_ps"]
NEW_ARM = ["vadd_f32", "vget_lane_f32", "vld2q_f32", "vst2q_f32", "vld4q_f32", "vmlsq_f32", "vfmsq_f32", "vsubq_f32"]


def test_dot_product_header_intrinsics_are_known():
    missing = [n for n in NEW_INTEL + NEW_ARM if lookup(n) is None]
    assert missing == []
