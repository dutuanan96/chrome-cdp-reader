# Changelog

All notable changes to `chrome-cdp-reader` are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] — Phase 1 (PR #9, Round 3)

### Added
- `TargetHandle` used as the runtime source of truth for tab ownership:
  `_prepare_tab` returns a WebSocket whose `_handle` is a `TargetHandle` with
  `owned=True` for a freshly created tab and `owned=False` for a reused tab.
  `_close_tab` consumes the handle and only closes `owned=True` tabs.
- Typed error taxonomy wired into the real CDP paths:
  - `_connect` failures → `ConnectionError`
  - `Page.navigate` `errorText` → `NavigationError`; timeout → `NavigationTimeoutError`
  - target create / attach / close failures → `TargetError`
  - `Runtime.evaluate` protocol or timeout → `EvaluationError`
  (bare `CDPError` is no longer used for every protocol error.)
- `Deadline` starts at the very top of `_prepare_tab` (before tab lookup /
  create / connect) and budgets every CDP step; exhaustion raises
  `NavigationTimeoutError`.
- Strict navigation correlation: when lifecycle events are enabled, only a
  matching `frameId`+`loaderId` lifecycle / within-document event completes
  navigation; a stray `Page.loadEventFired` is rejected. The legacy
  `loadEventFired` fallback is used only when lifecycle was genuinely
  unavailable.
- `create_tab(url)` validates the URL at the boundary (`validate_scheme`),
  including a real-hostname requirement for http(s); `file:`/`javascript:`/
  `data:`/malformed-http are rejected.
- CLI `--max-chars` is `click.IntRange(min=1)` and is forwarded end-to-end into
  `read()` (and `read_gmail`/`read_zalo`/`read_facebook`); formatted / `--json`
  output uses `textLength` and `truncated` from the bounded extractor.
- Screenshot hardening:
  - output path is confined to the CWD-based screenshot root (path escape
    rejected);
  - `quality` must be a real `int` (bool / str / float rejected →
    `InvalidInputError`);
  - extension allowlist (`.png`/`.jpg`/`.jpeg`; `.bmp` rejected);
  - TOCTOU-safe atomic write (`O_EXCL` temp file + `os.replace`).
- Package facade (`__init__.py`) now exports the typed errors, `Deadline`,
  `TargetHandle`, `validate_scheme`, and `exit_code_for`.

### Changed
- **BREAKING (opt-in):** `screenshot()` now returns a metadata `dict`
  (`{path, format, byteSize}`) by default instead of a `str` path. The previous
  `str` return is preserved via `screenshot(..., return_path=True)`, so existing
  callers that want the path string can opt in without code change. This is
  flagged as a breaking change for any caller relying on the bare `str` return.
- Unknown internal errors exit with code `70` via `exit_code_for()` for every
  exception caught in the CLI (both `read` and `screenshot`).

### Tests
- New `tests/test_round3.py` covering all six Round-2 blocker regressions.
- `tests/test_load_lifecycle.py` rewritten for strict correlation + typed
  errors.
- Non-live suite: **102 passed** (4 live skipped, 2 `@pytest.mark.live`
  deselected) on Python 3.10–3.13.
