# PROJECT CONTEXT — chrome-cdp-reader

> Dành cho AI agent (Codex / Antigravity / ChatGPT / Hermes) tiếp quản repo này.
> Cập nhật sau mỗi session lớn. Giữ ngắn gọn, sự thật, không đạo văn từ diff.

## Mục tiêu

`chrome-cdp-reader` (tên gói `crc`) là bridge đọc các website đã login của anh
(An An / Yu Jun'an, PDM engineer @ JinTai) từ WSL2 qua Chrome DevTools Protocol
(CDP) trên Windows. Nguyên tắc cốt lõi (master plan "standout"):

- **Không export credential.** Không copy cookie / `Login Data` / `Web Data`.
  Không `--remote-allow-origins=*`. Localhost only, dedicated debug profile.
- **Read-only mặc định**, bounded extraction trong JS.
- **Không kill process theo port** (`taskkill /IM chrome.exe` bị cấm); chỉ
  `/PID` sau khi verify.
- **Không expose arbitrary JS/CDP** cho agent.

## Trạng thái hiện tại (2026-07-18)

- **Phase 1 (Gate 0 + Phase 1) ĐÃ MERGE** → main `4e9b617`
  (PR #9, squash merge, 15 review/fix commits → 1 commit sạch).
- CI xanh Python 3.10–3.13. `ruff` clean. Non-live pytest: **148 passed,
  4 skipped, 2 deselected**.
- Live smoke (Chrome 150 debug :9222, dedicated profile
  `C:\chrome-debug-profile`) đã pass happy path: bounded read, URL blocking,
  screenshot. Failure paths covered bởi deterministic unit tests.

## Cấu trúc code (sau Phase 1)

| Module | Vai trò |
|---|---|
| `src/chrome_cdp_reader/bridge.py` | Core: `ChromeReader`, `_prepare_tab`, `create_tab`, `cdp_send`, `read`, `screenshot`, navigation lifecycle |
| `src/chrome_cdp_reader/errors.py` | Typed exception taxonomy + `exit_code_for()` + `UnsupportedMethodError(code=-32601)` |
| `src/chrome_cdp_reader/deadlines.py` | `Deadline` — một budget thời gian chung, `bounded(max)` |
| `src/chrome_cdp_reader/url_validation.py` | `validate_scheme()` — chặn file/javascript/data, chỉ about:blank + http(s) |
| `src/chrome_cdp_reader/models.py` | `TargetHandle(target_id, owned=False)` — nguồn sự thật tab ownership |
| `src/chrome_cdp_reader/cli.py` | `crc` CLI (click): `read`, `screenshot`, exit codes |
| `src/chrome_cdp_reader/__init__.py` | Package facade — export public API (__all__) |

## Quy tắc làm việc (bắt buộc)

1. **Mỗi phase = 1 PR**, không tự merge main. Anh review (Round 1..N) rồi mới
   merge. Agent được phép merge qua Chrome CDP nếu GitHub connector bị 403
   (như PR #9), hoặc dùng `gh pr merge --squash` (gh CLI đã auth).
2. **Không đụng main** trực tiếp. Luôn branch riêng.
3. **Test phải assert đúng code path** (tránh PASS giả). Live test thật cần
   Chrome debug :9222. Non-live (`-m "not live"`) phải pass đầy đủ.
4. **Verify trước khi báo done**: `ruff check src/ tests/` + `pytest -q -m
   "not live"` + CI 3.10–3.13. Không claim verified nếu chưa chạy.
5. **ADD code, không sửa code đang chạy** (trừ khi anh duyệt). Mỗi fix = 1
   commit nhỏ, backup trước data push.
6. **Không copy credential**, không `--remote-allow-origins=*`, không kill
   chrome theo port.
7. **Package version thật: 1.3.0a3** (SKILL.md cũ ghi a2 — mismatch đã biết).
8. **Chrome 150+ (Chromium 147+) yêu cầu origin**: websocket handshake phải
   `suppress_origin=True`, nếu không 403. `chrome_cdp_reader` bridge đã làm.

## Cách chạy local

```bash
cd chrome-cdp-reader
python3 -m pip install -e ".[dev]"
python3 -m ruff check src/ tests/
python3 -m pytest -q -m "not live"
# live (cần Chrome debug :9222, dedicated profile):
crc read https://github.com/dutuanan96/chrome-cdp-reader
crc read javascript:alert(1)   # expect rejected, exit 2
```

## Roadmap (master plan)

- Phase 2: `feat/compact-snapshot` — compact snapshot schema
- Phase 3: read-only policy engine / domain allowlist / audit
- Phase 4: GitHub extractor
- Phase 5: JSON stdio / MCP adapters
- Phase 6: benchmark matrix
- Phase 7: PyPI / launch

## Liên kết

- Repo: https://github.com/dutuanan96/chrome-cdp-reader
- PR #8 (Gate 0, merged): d8d64733
- PR #9 (Phase 1, merged): 4e9b617
- REVIEW_CONTEXT_phase1.md — chi tiết review Round 1–5
- CHANGELOG.md — lịch sử thay đổi
- Skill: ~/.hermes-shared/skills/devops/chrome-cdp-reader
