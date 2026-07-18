"""

Error taxonomy for chrome-cdp-reader (Phase 1).

Design notes
------------
* ``ChromeCDPReaderError`` is the single public base for all reader errors.
  The legacy ``CDPError`` name (historically defined in ``bridge.py``) is kept
  as an alias so existing ``from chrome_cdp_reader.bridge import CDPError`` and
  ``except CDPError`` keep working. We define the base HERE (not in bridge) to
  avoid a circular import: bridge imports from this module.
"""

from __future__ import annotations


class ChromeCDPReaderError(Exception):
    """Public base exception for all reader errors."""


# Backward-compatible alias for the old ``bridge.CDPError``.
CDPError = ChromeCDPReaderError


class ConnectionError(ChromeCDPReaderError):
    """Cannot reach the Chrome debug endpoint."""


class PortConflictError(ChromeCDPReaderError):
    """The debug port is owned by an unexpected / unsafe process."""


class UnsafeProcessError(ChromeCDPReaderError):
    """Refused to terminate or launch because a process is unsafe to touch."""


class NavigationError(ChromeCDPReaderError):
    """Page navigation failed (errorText / bad URL / TLS / DNS)."""


class NavigationTimeoutError(NavigationError):
    """Navigation did not reach a settled state within the deadline."""


class DownloadNavigationError(NavigationError):
    """The URL resolved to a download instead of a page."""


class TargetError(ChromeCDPReaderError):
    """Tab/target creation, attach or close failed."""


class EvaluationError(ChromeCDPReaderError):
    """A Runtime.evaluate call failed inside the page."""


class PolicyDeniedError(ChromeCDPReaderError):
    """The read-only policy denied the requested operation."""


class InvalidInputError(ChromeCDPReaderError):
    """Caller passed invalid arguments (bad URL, bad limit, etc.)."""


class ExtractionError(ChromeCDPReaderError):
    """A structured extractor failed to produce its schema."""


# Stable CLI exit codes. Never reuse 0 (success) or 1 (uncaught).
EXIT_CODES: dict[type, int] = {
    InvalidInputError: 2,
    ConnectionError: 10,
    PortConflictError: 11,
    UnsafeProcessError: 12,
    NavigationError: 20,
    NavigationTimeoutError: 21,
    DownloadNavigationError: 20,
    TargetError: 22,
    EvaluationError: 23,
    PolicyDeniedError: 30,
    ExtractionError: 40,
    ChromeCDPReaderError: 70,
}


def exit_code_for(exc: BaseException) -> int:
    """Return the stable exit code for an exception.

    Walks the MRO so subclasses inherit their parent's code, falling back to
    70 (unexpected internal error) for anything unknown.
    """
    for cls in type(exc).__mro__:
        if cls in EXIT_CODES:
            return EXIT_CODES[cls]
    return 70
