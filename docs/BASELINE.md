# Baseline

Recorded at Gate 0 of the master standout plan (2026-07-18).

## Merge SHA

- `e09443b99d95d041b0927a33fa5286b6d4cf60a6` (main, post PR #6 + #7)

This SHA contains the B1/B2/B3 fixes verified below.

## B1 — Safe process ownership (verified)

File: `src/chrome_cdp_reader/chrome_launcher.py`

- `kill_chrome(only_debug_profile=True)` never runs `taskkill /IM chrome.exe`.
- Kills ONLY a Chrome process whose `CommandLine` contains BOTH the debug
  port and the dedicated debug profile name.
- If the port is owned by a non-Chrome intruder (Python/Node/Docker),
  it FAILS-FAST and refuses to launch (returns `False`).
- After kill, it polls until the port is actually free before returning.
- Launch is verified via `GET /json/version` (not `netstat` alone).
- No `--remote-allow-origins=*`; Origin header suppressed client-side
  (`suppress_origin=True` in `bridge.py._connect`).

## B2 — Lifecycle-correct navigation (verified)

File: `src/chrome_cdp_reader/bridge.py`

- `Page.setLifecycleEventsEnabled` enabled; navigation correlated by
  `frameId` + `loaderId` (cross-document) and `Page.navigatedWithinDocument`
  (same-document / fragment / History API).
- Stale `about:blank` events drained via `_drain_old_events` before nav.
- Single monotonic overall deadline (no stacked timeouts).
- Redirects resolve to the final page; `errorText` raised; `isDownload`
  handled separately (see code paths).

## B3 — Bounded text extraction (verified)

File: `src/chrome_cdp_reader/bridge.py`

- `read_text(max_chars=...)` truncates INSIDE the browser (JS `slice`)
  before the payload leaves via CDP.
- Returns `{text, textLength, truncated}`.
- Rejects `bool`, non-`int`, zero and negative `max_chars`.
- Unicode (Vietnamese/Chinese/emoji) handled by JSON over CDP.
- Every direct WebSocket connection goes through
  `bridge._connect(suppress_origin=True)`.
- **STATUS AT GATE 0: primitive only.** `read_text` existed but
  `ChromeReader.read()` did NOT call it; it fetched full `innerText` instead.
  The end-to-end bounded path was wired in Phase 1 (PR #9), not at Gate 0.

## Python versions tested

- 3.13.13 (active WSL interpreter)

## Chrome version

- Chrome/150.0.7871.127 (debug profile, port 9222) — live verification
  confirmed `crc status` + `crc read` against a real GitHub page.

## Windows version

- Microsoft Windows [Version 10.0.26200.8737]

## WSL version

- WSL2, kernel `6.6.114.1-microsoft-standard-WSL2`

## Unit tests

- `tests/test_fixes_b1b2b3.py`
- `tests/test_basic.py`
- `tests/test_load_lifecycle.py`
- `tests/test_tab_lifecycle.py`
- `tests/test_tab_reuse_live.py` (live-marked)
- `tests/test_integration.py` (live-marked)

Run: `python3 -m pytest tests/ -q`

## Integration tests

- Live smoke confirmed: `crc status` → Connected (Chrome 150, 8 tabs);
  `crc read https://github.com/dutuanan96/chrome-cdp-reader` returned
  real page title + content text.

## Known limitations

- `crc read` emits a benign warning: `Target <id> could not be closed
  within 3.0s.` — owned tab cleanup is best-effort; content is returned
  correctly regardless. Target Phase 1 (TargetHandle ownership / tighter
  cleanup deadline).
- **Cookie handling is NOT a copy.** `CookieManager` only creates an empty,
  dedicated debug profile and lets the user log in ONCE; cookies then persist
  inside that profile. It does NOT read or copy cookies / Login Data / Web Data
  from the user's default Chrome profile. The class keeps the legacy name
  `CookieManager`; a later phase will rename it to `ChromeProfileManager`.
- **B3 — primitive present, public path incomplete (at Gate 0).** The helper
  `bridge.read_text(max_chars)` truncates text INSIDE the browser. However, at
  the time of this baseline, `ChromeReader.read()` still fetched the full
  `document.body.innerText` in one evaluate and only truncated in Python/CLI.
  So the bounded end-to-end path (JS-side cut on every `read()`) was wired in
  Phase 1, not at Gate 0. See PR #9.
- No compact structured snapshot schema yet (Phase 2).
- No read-only policy engine yet (Phase 3).
- No GitHub typed extractor yet (Phase 4).
- No JSON stdio / MCP adapters yet (Phase 5).
