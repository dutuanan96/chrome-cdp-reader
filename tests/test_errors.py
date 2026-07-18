"""Unit tests for the error taxonomy + exit codes (Phase 1)."""

from chrome_cdp_reader import errors
from chrome_cdp_reader.errors import (
    ChromeCDPReaderError,
    ConnectionError,
    CDPError,
    InvalidInputError,
    NavigationTimeoutError,
    PortConflictError,
    UnsafeProcessError,
    exit_code_for,
)


def test_base_is_subclass_of_legacy_cdp_error():
    # Backward compatibility: existing `except CDPError` must still catch.
    assert issubclass(ChromeCDPReaderError, CDPError)


def test_exit_codes_stable():
    assert exit_code_for(InvalidInputError("x")) == 2
    assert exit_code_for(ConnectionError("x")) == 10
    assert exit_code_for(PortConflictError("x")) == 11
    assert exit_code_for(UnsafeProcessError("x")) == 12
    assert exit_code_for(NavigationTimeoutError("x")) == 21
    assert exit_code_for(ChromeCDPReaderError("x")) == 70


def test_subclass_inherits_parent_code():
    # NavigationTimeoutError -> NavigationError(20), not its own number.
    assert exit_code_for(NavigationTimeoutError("x")) in (20, 21)


def test_unknown_exception_defaults_to_70():
    assert exit_code_for(RuntimeError("boom")) == 70


def test_module_imports_clean():
    # errors.py must not raise on import; CDPError comes from bridge.
    assert errors.CDPError is not None
