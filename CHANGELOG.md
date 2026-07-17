# Changelog

All notable changes to `chrome-cdp-reader` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0a3] — 2026-07-17

### Added
- **Safe process kill** (`ChromeLauncher.kill_chrome`): kills ONLY the Chrome
  instance that owns the debug port AND debug profile. Verifies process name +
  command line (`--remote-debugging-port` and `--user-data-dir=...chrome-debug-profile`)
  before killing — never `taskkill /IM chrome.exe`. Polls until the port is free.
- **Fail-fast on port conflict**: if the debug port is held by a different
  process (Python/Node/Docker/etc.), `kill_chrome` returns `False` and refuses
  to launch a debug Chrome on top of it.
- **Navigation correlation** (`ChromeReader._prepare_tab`): enables
  `Page.setLifecycleEventsEnabled`, drains stale events before navigating, and
  waits for completion via `Page.lifecycleEvent` correlated by `frameId` +
  `loaderId`. Same-document navigation (fragment / History API) is handled via
  `Page.navigatedWithinDocument`. `errorText` and `isDownload` from
  `Page.navigate` are surfaced immediately. Single monotonic deadline (no
  stacked timeouts). Falls back to `Page.loadEventFired` on older protocol.
- **Bounded text read** (`ChromeReader.read_text(max_chars=4000)`): truncates
  `document.body.innerText` INSIDE the browser before the JSON leaves via CDP,
  returning `{"text", "textLength", "truncated"}`. Validates `max_chars`
  (rejects non-int / `<=0` / bool).
- Regression tests for B1/B2/B3 (`tests/test_fixes_b1b2b3.py`).

### Changed
- `ChromeLauncher.launch` already verified `/json/version`; process-safety and
  fail-fast now wrap the full setup flow.
- Docs updated: README Features, ARCHITECTURE (process safety + navigation
  correlation + bounded read), TROUBLESHOOTING (no `taskkill /IM`, no hardcoded
  username).

### Security
- Kills are now scoped to the exact debug process; a stray `taskkill /IM
  chrome.exe` can no longer terminate unrelated Chrome windows.

## [1.3.0a2] — earlier

- Bounded JS polls, reliable tab lifecycle, tab cleanup, `suppress_origin=True`
  (Chrome 147+ 403 fix), OCR helpers in the sibling skill.

## [1.3.0a1] — earlier

- Race-condition and overall-timeout fixes, ws-leak fixes, wait propagation.
