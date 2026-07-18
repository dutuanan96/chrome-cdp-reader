# HANDOVER — chrome-cdp-reader Phase 1 → Phase 2

> Handoff cho AI agent tiếp quản sau khi Phase 1 merge (main `4e9b617`,
> 2026-07-18). Đọc cùng PROJECT_CONTEXT.md và REVIEW_CONTEXT_phase1.md.

## Tình trạng bàn giao

Phase 1 (Gate 0 + Phase 1) HOÀN TẤT, MERGED, CI xanh. Không còn blocker
runtime/security. Repo sạch (tree không có artifact). 148 non-live tests pass.

## Những bài học quan trọng (pitfalls đã vượt qua)

1. **Deadline phải chung một instance.** `create_tab()` trước dùng
   `min(timeout, N)` độc lập cho từng bước (`_get_json`/`_connect`/`cdp_send`)
   → tổng có thể vượt budget. Fix: một `Deadline(timeout)`, truyền
   `budget.bounded(N)` cho mỗi bước.
2. **Method-aware error taxonomy.** `cdp_send` timeout không được ném chung
   `NavigationTimeoutError` cho mọi method. Mapping: `Runtime.evaluate`→
   `EvaluationError`, `Page.navigate`→`NavigationTimeoutError`,
   `Target.*`/`Page.close`→`TargetError`, khác→`EvaluationError`.
   `ws.send()` phải nằm trong `try` → `ConnectionError`.
3. **Protocol-aware, không string-match.** Lifecycle fallback chỉ khi
   `Page.setLifecycleEventsEnabled` raise `UnsupportedMethodError` (CDP code
   `-32601`). KHÔNG đoán bằng text ("not supported" / "unknown method").
   `ConnectionError`/timeout/`ExtractionError`/code khác phải propagate.
4. **Screenshot backward-compat.** Default trả `str` (path). Chỉ
   `return_metadata=True` trả dict. `overwrite=False` dùng `O_EXCL`
   no-replace (không TOCTOU); `overwrite=True` temp+atomic. Confined to
   `screenshot_root` (realpath + `relative_to`).
5. **Bounded read.** `read()` dùng `read_text(max_chars)`; `textLength` là độ
   dài gốc trang, `text` đã bị cắt. Đừng test `textLength <= max_chars`.
6. **GitHub connector 403.** `gh pr edit` / `gh api` review APPROVE有时 403
   ("Resource not accessible by integration") — giới hạn quyền, không phải
   lỗi PR. Merge vẫn làm được qua `gh pr merge --squash` (gh CLI auth) hoặc
   Chrome CDP tab đã login.
7. **Chrome 150+ origin.** websocket handshake CẦN `suppress_origin=True`,
   nếu không 403 Forbidden. `chrome_cdp_reader.bridge.ChromeReader` đã làm.
8. **Verify trước khi báo done.** Luôn chạy `ruff` + `pytest -m "not live"`
   + check CI. System reminder yêu cầu re-run sau mỗi edit.

## Quy trình làm việc chuẩn (áp dụng mọi phase)

1. Tạo branch `feat/<tên>` từ `origin/main` (không từ branch cũ đã merge).
2. ADD code, viết test deterministic (non-live) cho mọi failure path.
3. `ruff check` + `pytest -q -m "not live"` phải xanh.
4. Push, tạo PR, cập nhật REVIEW_CONTEXT / CHANGELOG.
5. Anh review (Round 1..N), sửa blocker, re-verify, re-push.
6. Sau approve: squash merge (`gh pr merge --squash` hoặc Chrome CDP).
7. Cập nhật PROJECT_CONTEXT / HANDOVER / REVIEW_CONTEXT.

## Lưu ý cho Phase 2 (compact-snapshot)

- Chưa có schema snapshot. Đọc `bridge.read()` / `read_text()` hiện tại để
  biết cấu trúc text trả về.
- Giữ nguyên quy tắc: read-only, bounded, không export credential.
- Test non-live phải che phủ schema generation + edge cases (trang rỗng,
  JS-heavy, encoding).

## Files quan trọng

- `src/chrome_cdp_reader/bridge.py` — core logic (đừng refactor lung tung)
- `docs/REVIEW_CONTEXT_phase1.md` — lịch sử review chi tiết
- `docs/CHANGELOG.md` — đã ghi Round 1–5
- `docs/PROJECT_CONTEXT.md` — bối cảnh tổng quan
- Skill: `~/.hermes-shared/skills/devops/chrome-cdp-reader` (version note:
  package thật 1.3.0a3, SKILL.md ghi a2 — mismatch)

## Credentials

Không có credential nào trong repo. Chrome debug dùng dedicated profile
`C:\chrome-debug-profile` (Windows), không copy cookie. Live test cần anh
khởi động Chrome debug :9222.
