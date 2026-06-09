from app.workflows.bold_seed_registry import DEFAULT_SEED_PRESETS, get_seed_preset


def test_default_seed_presets_include_classic_network_anchors():
    assert "PCC_DMN" in DEFAULT_SEED_PRESETS
    assert "mPFC_DMN" in DEFAULT_SEED_PRESETS
    assert "dACC_SN" in DEFAULT_SEED_PRESETS
    assert get_seed_preset("PCC_DMN")["radius_mm"] == 6


def test_default_seed_registry_has_fixed_15_seed_mni_profile():
    assert len(DEFAULT_SEED_PRESETS) == 15
    for required in ("PCC_DMN", "L_HIPPOCAMPUS", "R_HIPPOCAMPUS", "L_STG", "R_STG"):
        seed = get_seed_preset(required)
        assert seed["space"] == "MNI152"
        assert len(seed["coordinate_mni"]) == 3
        assert seed["radius_mm"] > 0
