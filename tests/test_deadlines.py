"""Unit tests for the Deadline helper (Phase 1). No Chrome required."""

import time

import pytest

from chrome_cdp_reader.deadlines import Deadline


def test_normal_timeout_has_full_remaining():
    d = Deadline(10)
    assert d.timeout == 10
    assert 9.5 < d.remaining() <= 10
    assert not d.expired()


def test_near_expiry():
    d = Deadline(0.05)
    time.sleep(0.1)
    assert d.expired()
    assert d.remaining() == 0.0


def test_expired_after_wait():
    d = Deadline(0.01)
    time.sleep(0.02)
    assert d.expired()


def test_maximum_cap_clamps_to_remaining():
    d = Deadline(1.0)
    # Ask for 100s but only remaining (~1s) is returned.
    assert d.bounded(100) <= 1.0
    assert d.bounded(100) >= 0.0


def test_bounded_never_negative():
    d = Deadline(0.01)
    time.sleep(0.02)
    assert d.bounded(5) == 0.0


def test_reject_bool_timeout():
    with pytest.raises(TypeError):
        Deadline(True)


def test_reject_string_timeout():
    with pytest.raises(TypeError):
        Deadline("10")  # type: ignore[arg-type]


def test_reject_zero_and_negative():
    with pytest.raises(ValueError):
        Deadline(0)
    with pytest.raises(ValueError):
        Deadline(-3)


def test_reject_nan_and_inf():
    with pytest.raises(ValueError):
        Deadline(float("nan"))
    with pytest.raises(ValueError):
        Deadline(float("inf"))
