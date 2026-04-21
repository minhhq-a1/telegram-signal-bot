# QA Review History

File này lưu hồ sơ review, fix, và verify QA dùng chung cho tất cả sprint.

Status:
- tài liệu lịch sử
- không phải backlog mở
- không phải nguồn sự thật chính cho trạng thái QA hiện tại

Nguồn sự thật hiện tại:
- [docs/QA_STRATEGY.md](/Users/minhhq/Documents/telegram-signal-bot/docs/QA_STRATEGY.md:1)
- [docs/QA_COVERAGE_MATRIX.md](/Users/minhhq/Documents/telegram-signal-bot/docs/QA_COVERAGE_MATRIX.md:1)

---

## Sprint 03

### Review Scope

Nguồn xác nhận:
- code review trực tiếp
- kết quả `./.venv/bin/python -m pytest -q`
- integration regressions tại [tests/integration/test_api_regressions.py](/Users/minhhq/Documents/telegram-signal-bot/tests/integration/test_api_regressions.py:1)

### Current Status

Trạng thái hiện tại:
- tất cả findings trong sprint này đã được xử lý
- unit tests pass
- integration regressions chính pass
- regression tests ở nhánh `DUPLICATE` và `INVALID_SECRET` đã pass

Kết quả hiện tại:

```bash
./.venv/bin/python -m pytest -q
```

- `31` tests pass
- `0` integration regressions fail

### Findings Summary

Sprint 03 đã đóng các nhóm lỗi chính sau:
- webhook controller không còn `500` do thiếu import `datetime/timezone`
- Telegram delivery logging đã được thống nhất contract
- request timestamps được validate ở request boundary
- signal detail response đã khớp nested contract
- seeded DB config đã khớp V1 docs
- duplicate response contract đã hợp lệ
- invalid-secret response đã khớp API contract

### Verification Commands

```bash
./.venv/bin/python -m pytest tests/integration/test_api_regressions.py -q
./.venv/bin/python -m pytest -q
```

### Notes

- Chi tiết AC/TC coverage hiện tại xem ở [docs/QA_COVERAGE_MATRIX.md](/Users/minhhq/Documents/telegram-signal-bot/docs/QA_COVERAGE_MATRIX.md:1)
- Với các sprint sau, thêm section mới vào file này thay vì tạo thêm nhiều file `SPRINT_xx_*` cho QA
