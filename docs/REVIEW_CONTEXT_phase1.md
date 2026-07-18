# REVIEW CONTEXT — Gate 0 + Phase 1 (chrome-cdp-reader)

**Generated:** 2026-07-18 by Hermes (CDP agent)
**For:** Codex / Antigravity / ChatGPT review of PR #8 and PR #9
**Repo:** https://github.com/dutuanan96/chrome-cdp-reader
**Master plan:** `/mnt/c/Users/HP/Downloads/chrome-cdp-reader_master_standout_plan_vi.md` (2286 lines, Vietnamese)

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

## 1. Gate 0 — PR #8 (docs only)

**PR:** https://github.com/dutuanan96/chrome-cdp-reader/pull/8
**Branch:** `docs/baseline`
**Change:** added `docs/BASELINE.md` — records that B1/B2/B3 already exist in
`main` (SHA `e09443b`) and verifies each against source.

B1/B2/B3 are ALREADY merged (PR #6, #7). Verified by reading source, not by
trusting docs:
- B1 safe process ownership — `chrome_launcher.kill_chrome(only_debug_profile=True)`
- B2 lifecycle navigation — `bridge._wait_navigation_ready` (frameId+loaderId,
  `navigatedWithinDocument`, drain, single deadline)
- B3 bounded text — `bridge.read_text(max_chars)` truncates INSIDE the browser,
  rejects bool/zero/negative, returns {text,textLength,truncated}

**Reviewer note:** Gate 0 is documentation. Only check that the SHA/claims
match the current `main`. No code change.

---

## 2. Phase 1 — PR #9 (production hardening)

**PR:** https://github.com/dutuanan96/chrome-cdp-reader/pull/9
**Branch:** `refactor/production-core`
**Goal:** turn the working B1/B2/B3 fixes into a structured, testable foundation
without changing runtime behaviour for valid inputs.

### 2.1 New modules (all ADD, no edit of B1/B2/B3 logic)

| File | Purpose | Key API |
|---|---|---|
| `src/chrome_cdp_reader/errors.py` | Typed exception taxonomy + stable CLI exit codes | `ChromeCDPReaderError` (subclass of legacy `CDPError`), `ConnectionError`, `PortConflictError`, `UnsafeProcessError`, `NavigationError`, `NavigationTimeoutError`, `DownloadNavigationError`, `TargetError`, `EvaluationError`, `PolicyDeniedError`, `InvalidInputError`, `ExtractionError`; `EXIT_CODES` + `exit_code_for()` |
| `src/chrome_cdp_reader/deadlines.py` | Single monotonic navigation budget | `Deadline(timeout)` → `.remaining()`, `.expired()`, `.bounded(max)`; rejects bool/str/zero/negative/NaN/Inf |
| `src/chrome_cdp_reader/url_validation.py` | Scheme allow/block + credential check | `validate_scheme(url)` → scheme or raises `InvalidInputError`; `ALLOWED_SCHEMES={http,https,about}`, `BLOCKED_SCHEMES={file,chrome,chrome-extension,devtools,javascript,data}` |
| `src/chrome_cdp_reader/models.py` | Explicit tab ownership | `TargetHandle(target_id, websocket_url="", owned=True)` |

### 2.2 CLI integration (`cli.py`, minimal)

- `read` command now calls `validate_scheme(target)` BEFORE navigation
  (aliases gmail/zalo/facebook bypass it, as before).
- The `except Exception` block maps `ChromeCDPReaderError` → `exit_code_for(e)`,
  other exceptions → 1.

### 2.3 Tests added (32 new, deterministic, no Chrome)

- `tests/test_deadlines.py` — normal/near-expiry/expired/cap/reject-bool/
  reject-str/reject-zero/reject-nan-inf
- `tests/test_url_validation.py` — https/fragment/punycode/about/javascript/
  file/data/chrome/whitespace/malformed/embedded-creds/relative/unknown/
  disjoint-constant-sets
- `tests/test_models.py` — owned/reused/empty-id/non-bool-owned
- `tests/test_errors.py` — base-is-subclass-of-CDPError, exit codes, subclass
  inherits parent code, unknown→70

### 2.4 Live evidence (real Chrome 150, port 9222)

| Command | Result | Exit |
|---|---|---|
| `crc read https://github.com/dutuanan96/chrome-cdp-reader` | real title+content | 0 |
| `crc read javascript:alert(1)` | "scheme not allowed" | 2 |
| `crc read file:///etc/passwd` | "scheme not allowed" | 2 |

### 2.5 Quality gates

- `pytest tests/ -q --ignore=tests/test_tab_reuse_live.py` → **84 passed**
- `ruff check src/ tests/` → **all checks passed**
- The only failing test in the whole suite is `test_tab_reuse_live.py`
  (live Gmail, needs login) — excluded from the default matrix by design.

---

## 3. Design decisions the reviewer should challenge

1. **`ChromeCDPReaderError` subclasses legacy `CDPError`** — keeps existing
   `except CDPError` working. Trade-off: public base name is slightly odd.
   Acceptable for Phase 1; can rename later.

2. **`validate_scheme` blocks `javascript:`/`data:` at the CLI layer only.**
   The deeper `bridge.read()` still accepts whatever URL string; the block is a
   guard rail at the entry point. Reviewer: is that enough, or should the
   guard move into `bridge`? (Domain allowlist is Phase 3, not here.)

3. **`Deadline` is NOT yet wired into `bridge._prepare_tab`** which still uses
   ad-hoc `min(5, remaining())`. Kept out to keep PR #9 focused and small
   (<400 lines of new code). Follow-up: adopt `Deadline` in bridge. Reviewer:
   confirm this is safe to defer.

4. **`TargetHandle` is defined + tested but bridge still tracks ownership via
   `ws._owns_target` / `self._owned_target_ids`.** Migration deferred to
   Phase 2 (snapshot work owns the lifecycle refactor). Reviewer: confirm
   deferred migration is acceptable.

5. **Exit code 1 for non-`ChromeCDPReaderError` exceptions** — broad, but
   matches "unexpected internal error = 70"? Actually 1 is used for generic
   CLI failure; the plan's table reserves 70 for unexpected internal. Reviewer:
   should generic CLI exceptions map to 70 instead of 1? (Minor.)

---

## 4. REVIEW CHECKLIST (run these)

**Security grep (must be clean in the diff):**
- [ ] No `--remote-allow-origins=*`
- [ ] No cookie / Login Data / Web Data copy added
- [ ] No `taskkill /IM chrome.exe` (only `/PID` after verification)
- [ ] No direct `create_connection` bypassing `bridge._connect`
- [ ] No arbitrary `Runtime.evaluate` / CDP command exposed to agents

**Correctness:**
- [ ] `Deadline` never returns negative remaining; rejects bad input
- [ ] `validate_scheme` blocks file/javascript/data/chrome internals
- [ ] `TargetHandle` rejects empty id / non-bool owned
- [ ] Exit codes match the plan's table (2=invalid, 10=conn, 11=port, 20/21=nav, 70=internal)
- [ ] Backward compat: existing `except CDPError` still catches new errors

**Tests:**
- [ ] 32 new tests present and passing
- [ ] No flaky/network-dependent unit tests
- [ ] Live smoke results reproducible on the reviewer's Chrome (optional)

**Docs:**
- [ ] PR description follows the plan's template (Problem/Design/Tests/Security/
      Backward compat/Known limitations)

---

## 5. What is intentionally NOT in Phase 1 (scope guard)

- No compact snapshot schema (Phase 2)
- No read-only policy engine / domain allowlist / audit (Phase 3)
- No GitHub extractor (Phase 4)
- No JSON stdio / MCP adapters (Phase 5)
- No benchmark matrix (Phase 6)
- No PyPI / launch (Phase 7)

Do NOT let the review balloon Phase 1 into those. Keep the PR focused.

---

## 6. How to run locally (for the reviewer)

```bash
cd chrome-cdp-reader
python3 -m pip install -e .
python3 -m pytest tests/ -q --ignore=tests/test_tab_reuse_live.py
python3 -m ruff check src/ tests/
# live (needs Windows Chrome debug on :9222):
crc read https://github.com/dutuanan96/chrome-cdp-reader
crc read javascript:alert(1)   # expect rejected, exit 2
```

---

## 7. Pending human actions

- [ ] Anh (An An) or another AI reviews PR #8 + PR #9
- [ ] Merge only after review (do NOT self-merge per plan rule 16.5)
- [ ] After merge → Phase 2 branch `feat/compact-snapshot`
