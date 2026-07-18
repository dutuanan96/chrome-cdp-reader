# Changelog

All notable changes to `chrome-cdp-reader` are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] — Phase 1 (PR #9, Round 5 Final)

### Added
- `TargetHandle` used as the runtime source of truth for tab ownership:
  `_prepare_tab` returns a WebSocket whose `_handle` is a `TargetHandle` with
  `owned=True` for a freshly created tab and `owned=False` for a reused tab.
  `_close_tab` consumes the handle and only closes `owned=True` tabs.
- Typed error taxonomy wired into the real CDP paths (method-aware):
  - `_connect` / `ws.send` / socket failures → `ConnectionError`
  - `Runtime.evaluate` protocol or timeout → `EvaluationError`
  - `Page.navigate` `errorText` → `NavigationError`; timeout →
    `NavigationTimeoutError`
  - `Target.createTarget` / `attachToTarget` / `closeTarget` /
    `attachToBrowserTarget` failures → `TargetError`
  - malformed / non-JSON CDP response → `ExtractionError`
  (bare `CDPError` is no longer used for every protocol error; helpers are not
  monkeypatched to pre-throw — tests drive real CDP response parsing.)
- `Deadline` starts at the very top of `_prepare_tab` (before tab lookup /
  create / connect) and budgets EVERY helper step: `get_tabs`,
  `_find_reusable_tab`, `create_tab`, `_get_tab_ws`, `_connect`, and the
  selector DOM-fallback `cdp_js` all receive `remaining()` — never a default
  large timeout.
- Strict navigation correlation:
  - cross-document (nav_loader set): only a `frameId`+`loaderId` matching
    lifecycle event completes; a wrong-loader event and a
    `navigatedWithinDocument` event are rejected.
  - same-document (nav_loader empty): only a `frameId`-matching
    `navigatedWithinDocument` event completes; a lifecycle event is rejected.
  - a stray `Page.loadEventFired` is rejected when lifecycle is enabled.
- `create_tab(url)` validates the URL at the boundary (`validate_scheme`),
  including a real-hostname requirement for http(s); only exactly
  `about:blank` (not the whole `about:` scheme) plus http(s) with a host are
  allowed; `file:`/`javascript:`/`data:`/`about:settings`/`about:version`/
  malformed-http are rejected.
- CLI `--max-chars` is `click.IntRange(min=1)` and is forwarded end-to-end into
  `read()` (and `read_gmail`/`read_zalo`/`read_facebook`); formatted / `--json`
  output uses `textLength` and `truncated` from the bounded extractor.
- Screenshot hardening:
  - output path is confined to a dedicated screenshot root (configurable via
    `reader.screenshot_root`, defaults to CWD) resolved with realpath +
    `Path.relative_to` so symlink / junction escapes are blocked;
  - `quality` must be a real `int` (bool / str / float rejected →
    `InvalidInputError`);
  - extension allowlist (`.png`/`.jpg`/`.jpeg`; `.bmp` rejected);
  - `overwrite=False` (default) uses a true no-replace create (`O_EXCL`): an
    existing file raises `FileExistsError` → `InvalidInputError` with no
    check-then-create TOCTOU window. `overwrite=True` uses a temp file +
    atomic `os.replace`.
  - **Backward compatible:** `screenshot()` returns a `str` path by default
    (original Phase-1-agnostic API). `return_metadata=True` returns the dict
    `{path, format, byteSize}`; the CLI uses `return_metadata=True`. No breaking
    change to the default return type.
- `open_tab()` passes the captured `TargetHandle` explicitly into `_close_tab`
  so cleanup uses the original ownership decision even if `ws._handle` is
  mutated in the caller's context. `_close_tab` types its handle as
  `TargetHandle` and rejects non-`TargetHandle` metadata.
- Package facade (`__init__.py`) now exports the typed errors, `Deadline`,
  `TargetHandle`, `validate_scheme`, and `exit_code_for`.

### Round 5 / R6 (failure-path hardening, final)
- `errors.py` adds `UnsupportedMethodError` carrying the CDP `code`
  (default `-32601`). `EXIT_CODES` maps it to `23`.
- `cdp_send()` maps a CDP error with `code == -32601` to
  `UnsupportedMethodError` (preserving the code) instead of a generic error;
  all other error/timeout paths stay method-aware.
- `_prepare_tab()` now falls back to `loadEventFired` ONLY when
  `Page.setLifecycleEventsEnabled` raises `UnsupportedMethodError` (protocol
  `-32601`). The previous free-text matching (`"not supported"` /
  `"unknown method"` / `"command is not"`) is removed; `ConnectionError`,
  timeout, `ExtractionError`, and any other error code all propagate.

### Changed
- Unknown internal errors exit with code `70` via `exit_code_for()` for every
  exception caught in the CLI (both `read` and `screenshot`).

### Tests
- New `tests/test_round3.py` covering all blocker regressions across Round 2,
  Round 3, Round 4, and Round 5 (shared Deadline budget, method-aware CDP
  errors + timeouts triggered by real responses/recv-timeouts, `-32601` →
  `UnsupportedMethodError` with code preserved, same message different code
  propagates, strict lifecycle edge cases, about-scheme rejection, handle
  immutability, lifecycle fallback keys on the protocol code not text).
- `tests/test_load_lifecycle.py` rewritten for strict correlation + typed
  errors.
- Non-live suite: **148 passed, 4 live skipped, 2 `@pytest.mark.live`
  deselected** on Python 3.10–3.13.

### Status
- **Phase 1 MERGED** (PR #9, squash) into `main` at `4e9b617`
  (2026-07-18). All Round 1–5 blockers resolved; ruff clean; CI green
  3.10–3.13. Next: Phase 2 `feat/compact-snapshot`.
