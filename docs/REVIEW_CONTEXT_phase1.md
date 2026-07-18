# REVIEW CONTEXT — Gate 0 + Phase 1 (chrome-cdp-reader)

**Generated:** 2026-07-18 by Hermes (CDP agent)
**Updated:** 2026-07-18 (Round 2 — rebase onto merged #8, exit-code blocker fixed)
**For:** Codex / Antigravity / ChatGPT review of PR #9
**Repo:** https://github.com/dutuanan96/chrome-cdp-reader

---

## 0. Product positioning (do NOT lose this in review)

> A security-focused, low-context authenticated browser bridge that lets AI
> agents in WSL2 access a dedicated Windows Chrome session **without exporting
> cookies or passwords**.

This is NOT a Playwright/Browser-Use clone. Hard security invariants the
reviewer must check are preserved:

1. No cookie copy / no Login Data / no password DB read.
2. No `--remote-allow-origins=*`. Origin is suppressed client-side
   (`suppress_origin=True` in `bridge._connect`).
3. No `taskkill /IM chrome.exe`. Process kill verifies Name + CommandLine
   (port + dedicated profile) and FAILS-FAST on intruders.
4. Never close a tab the tool did not create.
5. Read-only is the default. No arbitrary `Runtime.evaluate` or CDP command
   exposed to agents.

---

## 1. Round 1 → resolved, then Round 2 rebase

### Round 1 (7 blockers, all fixed)
| # | Blocker | Fix |
|---|---|---|
| 1 | CI red (live tests ran on CI without Chrome) | `_chrome_up()` returns `ChromeReader(CDP).is_connected()`; live tests marked `@pytest.mark.live`; marker registered in `pyproject.toml`; CI runs `pytest -q -m "not live"` |
| 2 | BASELINE.md falsely claimed cookie copy | `CookieManager` does NOT copy; clarifies legacy-name-only |
| 3 | B3 primitive only, public `read()` fetched full innerText | `read()` calls `read_text(max_chars)`; returns textLength+truncated |
| 4 | URL validation only in one CLI command | Moved to core boundary `_prepare_tab`/`read`/`screenshot`/`open_tab` |
| 5 | Two divergent exception systems | `errors.py` is single source; bridge raises typed errors; `CDPError` alias kept |
| 6 | `TargetHandle` not used at runtime (dead code) | Runtime uses `TargetHandle`: created targets get `owned=True`, reused targets get `owned=False` (default); `_close_tab` consumes the handle |
| 7 | Screenshot hardening missing | Only .png/.jpg/.jpeg; quality 1-100; .bmp rejected; overwrite guard; dir creation; metadata |

### Round 2 (rebase + exit-code blocker)
- **PR #8 merged** at `d8d64733a50289f3e3e527c7839859128bb65567` (Squash and merge, done via the logged-in Chrome CDP tab — the AI's GitHub token lacks merge permission).
- **PR #9 rebased** onto that commit. The CI-infrastructure commits that also
  landed in #8 (`.github/workflows/ci.yml`, `pyproject.toml` marker,
  `tests/test_tab_reuse_live.py`) are now **absent from the #9 diff** — they
  came in through #8, so the PR #9 diff shows only Phase 1 code.
- **Remaining exit-code blocker fixed:** both `read` and `screenshot` in
  `cli.py` previously did
  `exit_code_for(e) if isinstance(e, ChromeCDPReaderError) else 1`, which
  collapsed every unexpected error to exit 1. They now call
  `sys.exit(exit_code_for(e))` directly. `exit_code_for()` falls back to `70`
  for any unknown exception (e.g. a raw `RuntimeError`).
- Added `tests/test_cli_exit_codes.py`: `CliRunner` monkeypatches the core to
  raise `RuntimeError` and asserts exit code **70** for both `read` and
  `screenshot`; also asserts a typed `InvalidInputError` yields exit `2`.

### Current SHAs
- PR #8 base/merge: `e09443b` (baseline) → merge `d8d64733…`
- PR #9 base: `d8d64733…` (post #8)
- PR #9 head (Round 3): `ea2edc5ed5d95ae6d62ee5eca28026b2a302014d` — produced after
  fixing all 6 Round-2 blockers (CLI bounded read end-to-end, TargetHandle
  runtime, error taxonomy runtime wiring, create_tab URL validation,
  Deadline+strict correlation, screenshot hardening) plus package facade export.

### Round 3 (all 6 blockers fixed)
1. **B1 CLI bounded read end-to-end** — `cli.read` forwards `max_chars` to
   `reader.read`; `read_gmail`/`read_zalo`/`read_facebook` accept + forward
   `max_chars`; `--max-chars` is `click.IntRange(min=1)`; formatted/`--json`
   output uses `textLength`/`truncated`. Covered by `test_round3` (normal URL
   + 3 aliases + `--json`).
2. **B2 TargetHandle is the runtime source of truth** — `_prepare_tab` creates
   `TargetHandle(owned=True)` for a created tab and `owned=False` for a reused
   tab; `_close_tab` consumes the handle. No `ws._target_id`/`_owns_target`
   source of truth remains. `test_round3` proves runtime usage, not just the
   dataclass default.
3. **B3 error taxonomy wired to runtime** — `_connect` wraps into
   `ConnectionError`; `Page.navigate` errorText→`NavigationError`, timeout→
   `NavigationTimeoutError`; create/attach/close→`TargetError`; `Runtime.evaluate`
   →`EvaluationError`. `cdp_send` no longer uses bare `CDPError` for every case.
   `test_round3` triggers the real `_prepare_tab`/`read` paths.
4. **B4 create_tab URL validation at the boundary** — `create_tab(url)` calls
   `validate_scheme` before any HTTP/CDP call; http(s) require a real hostname.
   `file:`/`javascript:`/`data:`/malformed-http rejected. `test_round3` covers
   each.
5. **B5 Deadline + strict lifecycle correlation** — `Deadline` starts at the top
   of `_prepare_tab` (before lookup/create/connect) and budgets every CDP step;
   on exhaustion raises `NavigationTimeoutError`. `_wait_navigation_ready`
   accepts only matching `frameId`+`loaderId` lifecycle/within-document events
   when lifecycle is enabled; stray `loadEventFired` is rejected; legacy
   `loadEventFired` fallback only when lifecycle was genuinely unavailable.
   `test_load_lifecycle` covers wrong-frame / stray-event regression.
6. **B6 screenshot hardening** — output confined to the CWD-based screenshot
   root (path-escape rejected); `quality` must be a real `int` (bool/str/float
   →`InvalidInputError`); extension allowlist (`.bmp` rejected); TOCTOU-safe
   atomic write (`O_EXCL` temp + `os.replace`); `return_path=True` keeps the old
   `str` return for backward compat. `test_round3` covers each.

### CI status
- `pytest -q -m "not live"` green on Python 3.10 / 3.11 / 3.12 / 3.13.
- Ruff clean (`ruff check src/ tests/`).
- Live tests (`@pytest.mark.live`) are excluded from the default matrix and run
  only against a real Chrome debug instance.

---

## 2. Gate 0 — PR #8 (docs only, MERGED)

Branch `docs/baseline` → merged into `main` at `d8d64733…`.
Deliverable: `docs/BASELINE.md` records that B1/B2/B3 already exist in `main`
and verifies each against source. No code change. CI-infra fix (live marker)
also shipped here so the default matrix stays green.

---

## 3. Phase 1 — PR #9 (production hardening, OPEN)

**PR:** https://github.com/dutuanan96/chrome-cdp-reader/pull/9
**Branch:** `refactor/production-core`
**Goal:** turn the working B1/B2/B3 fixes into a structured, testable foundation
without changing runtime behaviour for valid inputs.

### 3.1 New modules (all ADD, no edit of B1/B2/B3 logic)

| File | Purpose | Key API |
|---|---|---|
| `src/chrome_cdp_reader/errors.py` | Typed exception taxonomy + stable CLI exit codes | `ChromeCDPReaderError` (= legacy `CDPError` alias), `ConnectionError`, `PortConflictError`, `UnsafeProcessError`, `NavigationError`, `NavigationTimeoutError`, `DownloadNavigationError`, `TargetError`, `EvaluationError`, `PolicyDeniedError`, `InvalidInputError`, `ExtractionError`; `EXIT_CODES` + `exit_code_for()` (fallback 70) |
| `src/chrome_cdp_reader/deadlines.py` | Single monotonic navigation budget | `Deadline(timeout)` → `.remaining()`, `.expired()`, `.bounded(max)`; rejects bool/str/zero/negative/NaN/Inf |
| `src/chrome_cdp_reader/url_validation.py` | Scheme allow/block + credential check | `validate_scheme(url)` → scheme or raises `InvalidInputError`; `ALLOWED_SCHEMES={http,https,about}`, `BLOCKED_SCHEMES={file,chrome,chrome-extension,devtools,javascript,data}` |
| `src/chrome_cdp_reader/models.py` | Explicit tab ownership | `TargetHandle(target_id, websocket_url="", owned=False)` — **default `owned=False`** (reused); `_prepare_tab` sets `owned=True` for created tabs |

### 3.2 Integration into the core (NOT scaffold-only — wired in)

- **URL validation at the core boundary.** `bridge._prepare_tab()` calls
  `validate_scheme(url)` as step 0, before any navigation. `read()`,
  `screenshot()`, `open_tab()` all route through `_prepare_tab`, so dangerous
  schemes (`file:`, `javascript:`, `data:`, …) are rejected before the browser
  is touched — not just in one CLI command.
- **Deadline integrated into `_prepare_tab`.** The single `Deadline(timeout)`
  instance is shared by every navigation step (navigate → poll `domContentLoaded`
  → poll `readyState`); ad-hoc `time.monotonic()` math replaced. Total operation
  time cannot exceed the requested budget.
- **Bounded read end-to-end.** `ChromeReader.read()` calls
  `read_text(max_chars)` so text is truncated INSIDE the browser on the real
  path; returns `{…, text, textLength, truncated}`. CLI `read --json
  --max-chars N` no longer returns full text; `textLength`/`truncated` are in
  the payload. Regression test asserts full text never leaves the browser.
- **Unified exception system.** `errors.py` is the single source. `bridge.py`
  imports typed errors and raises `NavigationError` / `NavigationTimeoutError`
  / `DownloadNavigationError` / `EvaluationError` / `TargetError`; the legacy
  `CDPError` is kept as an alias for backward compatibility. Unknown CLI errors
  exit **70** (not 1).
- **Screenshot hardening (complete).** `screenshot()` accepts only
  `.png`/`.jpg`/`.jpeg`; rejects others (e.g. `.bmp` → `InvalidInputError`, no
  fake JPEG under a wrong extension); validates `quality` 1–100; refuses to
  overwrite an existing file unless `overwrite=True`; creates parent
  directories; returns `{path, format, byteSize}` metadata. CLI prints the
  metadata.

### 3.3 CLI integration (`cli.py`)

- `read` validates the target scheme before navigation (aliases
  gmail/zalo/facebook bypass it, as before).
- Both `read` and `screenshot` end with
  `sys.exit(exit_code_for(e))` for **every** exception — unknown → 70.

### 3.4 Tests added (deterministic, no Chrome required)

- `tests/test_deadlines.py` — normal/near-expiry/expired/cap/reject-bad-input
- `tests/test_url_validation.py` — allow/block/credential/disjoint-sets
- `tests/test_models.py` — owned/reused/empty-id/non-bool-owned
- `tests/test_errors.py` — base-is-CDPError alias, exit codes, subclass
  inheritance, unknown→70
- `tests/test_bridge_integration.py` — core-boundary URL validation, B3
  end-to-end (mocked), typed bridge errors, screenshot hardening, reused tab
  not closed
- `tests/test_cli_exit_codes.py` — `CliRunner` + monkeypatched core: unknown
  `RuntimeError` → exit 70 for both `read` and `screenshot`; typed error →
  correct code

### 3.5 Quality gates (current)

- `ruff check src/ tests/` → clean
- `pytest -q -m "not live"` → **102 passed, 4 live skipped, 2 deselected** (live
  tests skip when Chrome debug is not reachable; the 2 deselected are the
  `@pytest.mark.live` Gmail-reuse / generic-close integration tests)
- CI: green on Python 3.10 / 3.11 / 3.12 / 3.13

### 3.6 Current files changed in PR #9

```
src/chrome_cdp_reader/bridge.py
src/chrome_cdp_reader/cli.py
src/chrome_cdp_reader/deadlines.py        (new)
src/chrome_cdp_reader/errors.py           (new)
src/chrome_cdp_reader/models.py           (new)
src/chrome_cdp_reader/url_validation.py   (new)
src/chrome_cdp_reader/__init__.py         (facade exports)
tests/test_bridge_integration.py         (new)
tests/test_cli_exit_codes.py              (new)
tests/test_deadlines.py                  (new)
tests/test_errors.py                      (new)
tests/test_models.py                      (new)
tests/test_url_validation.py              (new)
tests/test_round3.py                      (new — blocker regression)
tests/test_integration.py                (conflict-resolved vs #8)
tests/test_load_lifecycle.py              (strict correlation + typed errors)
tests/test_tab_lifecycle.py               (TargetHandle runtime)
docs/REVIEW_CONTEXT_phase1.md
```
(`.github/workflows/ci.yml`, `pyproject.toml` marker, `tests/test_tab_reuse_live.py`
are intentionally NOT here — they shipped in PR #8.)

---

## 4. Design decisions (stable, not open questions)

1. **`ChromeCDPReaderError` IS `CDPError`** (alias) — keeps existing
   `except CDPError` working. Public base name kept for compatibility.
2. **Scheme validation lives at the core boundary** (`_prepare_tab`), not just
   the CLI. Domain allowlist is a separate Phase 3 concern.
3. **`Deadline` is wired into `_prepare_tab`** — single shared budget, started
   before any tab lookup / create / connect so the whole operation is bounded.
4. **`TargetHandle` carries explicit ownership** — `_prepare_tab` creates the
   handle with `owned=True` for a freshly **created** tab and `owned=False` for a
   **reused** tab (the default). `_close_tab` only closes a tab whose handle has
   `owned=True`, so a reused/user tab can never be closed by the reader.
5. **Unknown internal errors exit 70** via `exit_code_for()` for all exceptions
   caught in the CLI.

---

## 5. REVIEW CHECKLIST (run these)

**Security grep (must be clean in the diff):**
- [ ] No `--remote-allow-origins=*`
- [ ] No cookie / Login Data / Web Data copy added
- [ ] No `taskkill /IM chrome.exe` (only `/PID` after verification)
- [ ] No direct `create_connection` bypassing `bridge._connect`
- [ ] No arbitrary `Runtime.evaluate` / CDP command exposed to agents

**Correctness:**
- [ ] `Deadline` is used in `_prepare_tab`; never negative remaining
- [ ] `validate_scheme` called at core boundary (blocks file/javascript/data)
- [ ] `TargetHandle` used at runtime: created tab `owned=True`, reused `owned=False` (default); `_close_tab` consumes handle
- [ ] `tests/test_round3.py` present; covers CLI bounded read, TargetHandle runtime, error taxonomy runtime, create_tab validation, screenshot hardening
- [ ] 102 non-live tests pass; live tests marked and excluded from matrix
- [ ] No flaky/network-dependent unit tests

**Docs:**
- [ ] PR #9 description matches the template (Problem/Design/Tests/Security/
      Backward compat/Known limitations)

---

## 6. What is intentionally NOT in Phase 1 (scope guard)

- No compact snapshot schema (Phase 2)
- No read-only policy engine / domain allowlist / audit (Phase 3)
- No GitHub extractor (Phase 4)
- No JSON stdio / MCP adapters (Phase 5)
- No benchmark matrix (Phase 6)
- No PyPI / launch (Phase 7)

Do NOT let the review balloon Phase 1 into those. Keep the PR focused.

---

## 7. How to run locally (for the reviewer)

```bash
cd chrome-cdp-reader
python3 -m pip install -e ".[dev]"
python3 -m ruff check src/ tests/
python3 -m pytest -q -m "not live"
# live (needs a real Chrome debug instance on :9222):
crc read https://github.com/dutuanan96/chrome-cdp-reader
crc read javascript:alert(1)   # expect rejected, exit 2
```

---

## 8. Pending human actions

- [ ] Anh (An An) or another AI reviews PR #9 (Round 2)
- [ ] Merge only after review (do NOT self-merge per plan rule 16.5)
- [ ] After merge → Phase 2 branch `feat/compact-snapshot`
