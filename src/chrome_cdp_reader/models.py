"""
Typed models (Phase 1 — base set; extended in Phase 2).

Phase 1 introduces ``TargetHandle`` which makes tab ownership explicit so the
reader only ever closes tabs it created (B1 / lifecycle correctness).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TargetHandle:
    """One browser tab/target and whether WE own it.

    ``owned`` is True only for tabs the reader created during an operation.
    Reused user tabs have ``owned=False`` and must NEVER be closed by cleanup.
    """

    target_id: str
    websocket_url: str = ""
    owned: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.target_id, str) or not self.target_id:
            raise ValueError("target_id must be a non-empty string")
        if not isinstance(self.owned, bool):
            raise TypeError("owned must be a bool")
