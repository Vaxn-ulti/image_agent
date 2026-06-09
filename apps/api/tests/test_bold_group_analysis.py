import pytest

from app.workflows.bold_group_analysis import validate_group_inputs


def test_group_analysis_requires_minimum_subjects_per_group():
    with pytest.raises(ValueError, match="at least 2 completed subjects per group"):
        validate_group_inputs(group_a=["sub-01"], group_b=["sub-02"])
