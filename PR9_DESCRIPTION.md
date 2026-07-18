## Problem

Phase 1 of the master standout plan turns the already-merged B1/B2/B3 fixes
(safe process ownership, correlated navigation lifecycle, bounded read) into a
structured, testable foundation with a single error model and explicit tab
ownership — without changing runtime behaviour for valid inputs.

This PR (Round 2) also closes the one remaining blocker from Round-1 review:
the CLI collapsed *every* unexpected exception to exit code 1 instead of the
stable internal-error code 70.

## Design

### New modules (all ADD, no edit of B1/B2/B3 logic)
- `errors.py` — typed exception taxonomy + stable CLI exit codes. `ChromeCDPReaderError`
  is the single public base and an alias of the legacy `CDPError` (backward
  compatible). `exit_code_for()` maps typed errors to their codes and falls
  back to **70** for any unknown exception.
- `deadlines.py` — one monotonic navigation budget (`Deadline`); rejects
  bool/str/zero/negative/NaN/Inf.
- `url_validation.py` — scheme allow/block + embedded-credential check.
- `models.py` — `TargetHandle(target_id, owned=False)`; **defaults to
  `owned=False`** so a forgotten reuse can never close a user tab.

### Wired into the core (not scaffold-only)
- **URL validation at the core boundary.** `bridge._prepare_tab()` calls
  `validate_scheme(url)` as step 0, before any navigation. `read()`,
  `screenshot()`, `open_tab()` all route through it, so `file:`/`javascript:`/
  `data:` are rejected before the browser is touched.
- **Deadline integrated into `_prepare_tab`** — shared by every navigation
  step; ad-hoc `time.monotonic()` math removed.
- **Bounded read end-to-end.** `read()` calls `read_text(max_chars)`; returns
  `textLength` + `truncated`. CLI `--json --max-chars N` no longer returns full
  text.
- **Unified exceptions.** `bridge` raises typed errors; `CDPError` kept as
  alias. Unknown CLI errors exit **70**.
- **Screenshot hardening (complete).** Only `.png`/`.jpg`/`.jpeg`; quality 1–100;
  `.bmp` rejected (no fake JPEG); overwrite guard; parent-dir creation;
  returns `{path, format, byteSize}`.
- **CLI exit codes.** Both `read` and `screenshot` end with
  `sys.exit(exit_code_for(e))` — unknown → 70.

## Tests / CI
- `tests/test_deadlines.py`, `test_url_validation.py`, `test_models.py`,
  `test_errors.py`, `test_bridge_integration.py`, `test_cli_exit_codes.py`
  (new, deterministic, no Chrome).
- `tests/test_cli_exit_codes.py` uses `CliRunner` + monkeypatched core to prove
  a raw `RuntimeError` exits **70** for both `read` and `screenshot`.
- `pytest -q -m "not live"` → **98 passed, 2 live deselected**.
- `ruff check src/ tests/` → clean.
- CI green on Python 3.10 / 3.11 / 3.12 / 3.13 (default matrix excludes live).

## Security impact
None beyond the existing B1/B2/B3 guarantees. No cookie copy, no
`--remote-allow-origins=*`, no `taskkill /IM`, no arbitrary `Runtime.evaluate`.

## Backward compatibility
`from chrome_cdp_reader.bridge import CDPError` and `except CDPError` still
work (alias). `screenshot()` now returns a dict (was str) — see tests updated
accordingly.

## Known limitations (still open)
- Live tests (`@pytest.mark.live`) require a real Chrome debug instance and are
  excluded from the default CI matrix; they run via manual command.
- Owned-tab cleanup is best-effort (benign warning if a tab cannot be closed in
  time); content is always returned correctly.
- Compact snapshot schema, read-only policy engine, GitHub extractor, adapters,
  benchmark, and PyPI/launch are later phases (2–7), intentionally out of scope
  here.
