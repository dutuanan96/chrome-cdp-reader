"""Unit tests for URL / scheme validation (Phase 1)."""

import pytest

from chrome_cdp_reader.errors import InvalidInputError
from chrome_cdp_reader.url_validation import (
    ALLOWED_SCHEMES,
    BLOCKED_SCHEMES,
    validate_scheme,
)


def test_https_allowed():
    assert validate_scheme("https://github.com/x") == "https"


def test_fragment_ok():
    assert validate_scheme("https://github.com/x#section") == "https"


def test_punycode_ok():
    assert validate_scheme("https://xn--tda.edu.vn/") == "https"


def test_about_blank_allowed():
    assert validate_scheme("about:blank") == "about"


def test_javascript_rejected():
    with pytest.raises(InvalidInputError):
        validate_scheme("javascript:alert(1)")


def test_file_rejected():
    with pytest.raises(InvalidInputError):
        validate_scheme("file:///etc/passwd")


def test_data_rejected():
    with pytest.raises(InvalidInputError):
        validate_scheme("data:text/html,<script>")


def test_chrome_internal_rejected():
    with pytest.raises(InvalidInputError):
        validate_scheme("chrome://settings")


def test_whitespace_rejected_not_silent():
    with pytest.raises(InvalidInputError):
        validate_scheme("  file:///etc/passwd  ")


def test_malformed_url_rejected():
    with pytest.raises(InvalidInputError):
        validate_scheme("not a url")


def test_embedded_credentials_rejected():
    with pytest.raises(InvalidInputError):
        validate_scheme("https://user:pass@example.com/")


def test_relative_url_rejected():
    with pytest.raises(InvalidInputError):
        validate_scheme("/just/a/path")


def test_unknown_scheme_rejected():
    with pytest.raises(InvalidInputError):
        validate_scheme("ftp://example.com/")


def test_constant_sets_disjoint():
    # Defence-in-depth: a scheme must never be both allowed and blocked.
    assert ALLOWED_SCHEMES.isdisjoint(BLOCKED_SCHEMES)
