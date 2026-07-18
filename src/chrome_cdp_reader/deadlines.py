"""
Deadline — a single, monotonic navigation budget (Phase 1).

Why this exists
---------------
Navigation used to compute ``min(5, remaining())`` ad-hoc in many places.
That is easy to get wrong and can stack timeouts. Phase 1 centralises the
budget into one object that every navigation step shares, so the TOTAL wait
can never exceed the user's requested timeout.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Deadline:
    """A monotonic countdown used by every navigation step.

    All durations are in seconds. The object is created once per operation
    and passed down; nobody creates a second, longer deadline.
    """

    _expires_at: float
    _timeout: float

    def __init__(self, timeout: float):
        # Reject anything that is not a real positive number.
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a positive number")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        if timeout != timeout or timeout in (float("inf"), float("-inf")):
            raise ValueError("timeout must be finite")
        self._timeout = float(timeout)
        self._expires_at = time.monotonic() + self._timeout

    def remaining(self) -> float:
        """Seconds left, clamped to >= 0 (never negative)."""
        left = self._expires_at - time.monotonic()
        return left if left > 0 else 0.0

    def expired(self) -> bool:
        return self.remaining() <= 0

    def bounded(self, maximum: float) -> float:
        """Return ``min(remaining, maximum)``, both clamped to >= 0.

        Use this to size a per-step CDP call so it cannot blow the overall
        budget. ``maximum`` is itself clamped to the remaining time.
        """
        if isinstance(maximum, bool) or not isinstance(maximum, (int, float)):
            raise TypeError("maximum must be a number")
        cap = max(0.0, float(maximum))
        return min(self.remaining(), cap)

    @property
    def timeout(self) -> float:
        return self._timeout
