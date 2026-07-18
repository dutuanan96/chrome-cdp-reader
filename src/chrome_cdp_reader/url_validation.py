"""
URL / scheme validation (Phase 1).

The reader is read-only-first and must never navigate to or accept dangerous
schemes. We validate BEFORE any navigation or evaluation happens so a bad
URL fails fast with a clear error instead of surprising the agent.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .errors import InvalidInputError

# Schemes we are willing to load / accept.
ALLOWED_SCHEMES = frozenset({"http", "https", "about"})

# Schemes that must be blocked by default (local resources, chrome internals,
# script execution, data blobs).
BLOCKED_SCHEMES = frozenset({
    "file",
    "chrome",
    "chrome-extension",
    "devtools",
    "javascript",
    "data",
})


def validate_scheme(url: str) -> str:
    """Return the normalised scheme if allowed, else raise InvalidInputError.

    Examples
    --------
    >>> validate_scheme("https://github.com/x")        # -> "https"
    >>> validate_scheme("https://github.com/x#frag")   # -> "https" (fragment ok)
    >>> validate_scheme("javascript:alert(1)")         # -> raises
    >>> validate_scheme("  file:///etc/passwd  ")       # -> raises (whitespace stripped)
    """
    if not isinstance(url, str):
        raise InvalidInputError("url must be a string")
    cleaned = url.strip()
    if not cleaned:
        raise InvalidInputError("url must not be empty")

    # `javascript:` and similar have no `//` so urlparse keeps them in scheme.
    parsed = urlparse(cleaned)
    scheme = (parsed.scheme or "").lower()

    if scheme in BLOCKED_SCHEMES:
        raise InvalidInputError(f"scheme '{scheme}:' is not allowed")
    if scheme not in ALLOWED_SCHEMES:
        # Unknown / empty scheme (e.g. relative, "ftp", "mailto") -> reject.
        if scheme == "":
            raise InvalidInputError("url must include an explicit http(s) scheme")
        raise InvalidInputError(f"scheme '{scheme}:' is not supported")

    # http(s) require a real hostname (not just "http://" or "http:///x").
    if scheme in ("http", "https"):
        host = (parsed.hostname or "").strip()
        if not host:
            raise InvalidInputError(
                f"{scheme} URL must include a valid hostname: {url!r}")
        # Reject lone-dot / empty-after-strip placeholders.
        if host in (".", "..") or not any(c.isalnum() for c in host):
            raise InvalidInputError(
                f"{scheme} URL has an invalid hostname: {url!r}")

    # Reject embedded credentials (http://user:pass@host) per policy.
    if parsed.username is not None or parsed.password is not None:
        raise InvalidInputError("urls with embedded credentials are not allowed")

    return scheme
