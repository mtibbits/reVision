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
    assert set(vendors()) == {"intel", "arm", "riscv"}


NEW_INTEL = ["_mm_or_ps", "_mm_moveldup_ps", "_mm_movehdup_ps", "_mm_addsub_ps", "_mm256_moveldup_ps",
             "_mm256_movehdup_ps", "_mm256_shuffle_ps", "_mm256_addsub_ps", "_mm256_fmaddsub_ps",
             "_mm512_store_ps", "_mm512_storeu_ps"]
NEW_ARM = ["vadd_f32", "vget_lane_f32", "vld2q_f32", "vst2q_f32", "vld4q_f32", "vmlsq_f32", "vfmsq_f32", "vsubq_f32"]


def test_dot_product_header_intrinsics_are_known():
    missing = [n for n in NEW_INTEL + NEW_ARM if lookup(n) is None]
    assert missing == []


# The 24 RISC-V Vector rows of reVision#14, copied from the issue's table (checked 2026-10-03).
# Load-bearing: this is an independent copy, NOT read back from riscv.yaml, so a wrong or dropped
# row in the package data fails here instead of agreeing with itself.
RVV_URLS = {
    "__riscv_vfadd": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/04_vector_floating-point_intrinsics.html#overloaded-vector-single-width-floating-point-add-subtract",
    "__riscv_vfadd_tu": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/policy_funcs/overloaded_intrinsic_funcs/04_vector_floating-point_intrinsics.html#policy-variant-overloadedvector-single-width-floating-point-add-subtract",
    "__riscv_vfmacc": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/04_vector_floating-point_intrinsics.html#overloaded-vector-single-width-floating-point-fused-multiply-add",
    "__riscv_vfmacc_tu": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/policy_funcs/overloaded_intrinsic_funcs/04_vector_floating-point_intrinsics.html#policy-variant-overloadedvector-single-width-floating-point-fused-multiply-add",
    "__riscv_vfmul": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/04_vector_floating-point_intrinsics.html#overloaded-vector-single-width-floating-point-multiply-divide",
    "__riscv_vfmv_f": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/07_vector_permutation_intrinsics.html#overloaded-integer-scalar-move",
    "__riscv_vfmv_s_f_f32m1": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/07_vector_permutation_intrinsics.html#integer-scalar-move",
    "__riscv_vfmv_v_f_f32m2": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/04_vector_floating-point_intrinsics.html#vector-floating-point-move",
    "__riscv_vfmv_v_f_f32m8": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/04_vector_floating-point_intrinsics.html#vector-floating-point-move",
    "__riscv_vfneg": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/04_vector_floating-point_intrinsics.html#overloaded-vector-single-width-floating-point-add-subtract",
    "__riscv_vfnmsac": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/04_vector_floating-point_intrinsics.html#overloaded-vector-single-width-floating-point-fused-multiply-add",
    "__riscv_vfredusum": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/05_vector_reduction_operations.html#overloaded-vector-single-width-floating-point-reduction",
    "__riscv_vget_f32m1": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/08_miscellaneous_vector_utility_intrinsics.html#overloaded-vector-extraction",
    "__riscv_vget_f32m2": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/08_miscellaneous_vector_utility_intrinsics.html#overloaded-vector-extraction",
    "__riscv_vle32_v_f32m8": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/00_vector_loads_and_stores_intrinsics.html#vector-unit-stride-load",
    "__riscv_vle64_v_u64m4": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/00_vector_loads_and_stores_intrinsics.html#vector-unit-stride-load",
    "__riscv_vlseg2e32_v_f32m2x2": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/01_vector_loads_and_stores_segment_intrinsics.html#vector-unit-stride-segment-load",
    "__riscv_vnsrl": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/02_vector_integer_arithmetic_intrinsics.html#overloaded-vector-narrowing-integer-right-shift",
    "__riscv_vreinterpret_f32m2": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/08_miscellaneous_vector_utility_intrinsics.html#overloaded-reinterpret-cast-conversion",
    "__riscv_vsetvl_e32m2": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/08_miscellaneous_vector_utility_intrinsics.html#set-vl-and-vtype",
    "__riscv_vsetvl_e32m8": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/08_miscellaneous_vector_utility_intrinsics.html#set-vl-and-vtype",
    "__riscv_vsetvlmax_e32m1": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/08_miscellaneous_vector_utility_intrinsics.html#set-vl-to-vlmax-with-specific-vtype",
    "__riscv_vsetvlmax_e32m2": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/08_miscellaneous_vector_utility_intrinsics.html#set-vl-to-vlmax-with-specific-vtype",
    "__riscv_vsetvlmax_e32m8": "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/08_miscellaneous_vector_utility_intrinsics.html#set-vl-to-vlmax-with-specific-vtype",
}


def test_riscv_table_has_24_expected_rows():
    assert len(RVV_URLS) == 24


def test_riscv_every_row_resolves_exactly():
    mismatched = {n: lookup(n) for n, u in RVV_URLS.items() if lookup(n) != u}
    assert mismatched == {}


def test_riscv_one_name_per_directory_class():
    assert lookup("__riscv_vle32_v_f32m8") == (
        "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/intrinsic_funcs/"
        "00_vector_loads_and_stores_intrinsics.html#vector-unit-stride-load")
    assert lookup("__riscv_vfredusum") == (
        "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/"
        "05_vector_reduction_operations.html#overloaded-vector-single-width-floating-point-reduction")
    assert lookup("__riscv_vfmacc_tu") == (
        "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/policy_funcs/overloaded_intrinsic_funcs/"
        "04_vector_floating-point_intrinsics.html"
        "#policy-variant-overloadedvector-single-width-floating-point-fused-multiply-add")


def test_riscv_vget_f32m1_is_on_overloaded_page():
    # A type suffix would suggest the explicit page; the name is listed only on the overloaded one.
    assert lookup("__riscv_vget_f32m1") == (
        "https://docs.riscv.org/reference/vector-c-intrinsics/v1.0/overloaded_intrinsic_funcs/"
        "08_miscellaneous_vector_utility_intrinsics.html#overloaded-vector-extraction")


def test_riscv_unlisted_names_return_none():
    assert lookup("__riscv_vfmacc_vv_f32m8") is None
    assert lookup("__riscv_vfredosum") is None
