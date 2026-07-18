"""Unit tests for typed models — TargetHandle (Phase 1)."""

import pytest

from chrome_cdp_reader.models import TargetHandle


def test_owned_target():
    h = TargetHandle(target_id="ABC", websocket_url="ws://x", owned=True)
    assert h.owned is True
    assert h.target_id == "ABC"


def test_reused_target_not_owned():
    h = TargetHandle(target_id="ABC", owned=False)
    assert h.owned is False


def test_empty_target_id_rejected():
    with pytest.raises(ValueError):
        TargetHandle(target_id="")


def test_non_bool_owned_rejected():
    with pytest.raises(TypeError):
        TargetHandle(target_id="ABC", owned="yes")  # type: ignore[arg-type]
