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

    Default is ``False`` on purpose: a forgotten ``owned=False`` when reusing a
    tab is safe (we just don't close it), whereas a forgotten ``owned=True``
    could close a tab the user had open. Code that creates a tab MUST pass
    ``owned=True`` explicitly.
    """

    target_id: str
    websocket_url: str = ""
    owned: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.target_id, str) or not self.target_id:
            raise ValueError("target_id must be a non-empty string")
        if not isinstance(self.owned, bool):
            raise TypeError("owned must be a bool")
