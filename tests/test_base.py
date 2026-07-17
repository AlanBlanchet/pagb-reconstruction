"""Typed-boundary guards for the shared model base."""

import pytest
from pydantic import ValidationError


def test_unknown_config_fields_are_rejected():
    """A typo'd config kwarg must raise, never be silently ignored — a silently
    dropped parameter reads as 'the setting had no effect'."""
    from pagb_reconstruction.core.reconstruction import ReconstructionConfig

    with pytest.raises(ValidationError):
        ReconstructionConfig(this_field_does_not_exist=1.0)
