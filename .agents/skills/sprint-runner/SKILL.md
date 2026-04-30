---
name: sprint-runner
description: "Start or continue a documented project sprint or task while respecting current repository state."
---

# Skill: Sprint Runner
## Description
Bắt đầu hoặc tiếp tục một sprint/task từ docs project.
Trigger khi user nói: "bắt đầu sprint", "tiếp tục từ task", "làm TASK-0XX", "sprint mới", "làm plan".

## Instructions

Repo hiện tại đã vượt qua scaffold V1 ban đầu và có V1.1/rate-limit/reverify changes. Trước khi làm task, xác định nguồn task đúng thay vì giả định `docs/TASKS.md` còn là backlog duy nhất.

### Bước 1 — Đọc trạng thái

Đọc các file liên quan theo thứ tự:

1. `docs/TASKS.md` nếu user nhắc `TASK-0XX` V1.
2. `docs/SPRINT_*.md` nếu user nhắc sprint.
3. `docs/POST_V11_OPTIMIZATION_PLAN.md`, `docs/superpowers/plans/*.md`, hoặc issue/context file nếu user nhắc V1.1/rate-limit/reverify.
4. `git status --short` để biết worktree có dirty không; không revert thay đổi không phải của mình.

Xác định:
- Task nào đã done theo code/tests hiện tại, không chỉ checkbox cũ.
- Task tiếp theo thực sự còn thiếu.
- Dependency còn hiệu lực hay đã obsolete.
- File sẽ sửa/tạo.

### Bước 2 — Confirm với user khi scope lớn/không rõ

Báo cáo ngắn:

```text
Trạng thái: [tóm tắt]
Làm tiếp: [task/tên việc]
File dự kiến sửa: [danh sách]
Verify: [lệnh test]
Bắt đầu không?
```

Không cần confirm nếu user đã yêu cầu rõ một fix nhỏ và scope an toàn.

### Bước 3 — Implement

- Làm theo dependency thật của code hiện tại.
- Không làm 2 task độc lập trong cùng lượt nếu dễ gây conflict.
- Với mỗi file quan trọng, chạy syntax/import check hoặc test focused phù hợp.
- Dùng `rtk` prefix cho shell commands.
- Dùng `select()` SQLAlchemy 2.0, không dùng `db.query()`.
- Không hardcode config đáng ra đọc DB.
- Giữ nguyên nguyên tắc: audit-first, idempotency, persist trước notify, không log secret.

### Bước 4 — Verify DoD

Chạy verify gần nhất với thay đổi:

```bash
rtk python -m pytest tests/unit/test_filter_engine.py -v
rtk python -m pytest tests/unit/test_telegram_notifier.py -v
rtk python -m pytest tests/integration/test_webhook_endpoint.py -v
rtk python -m pytest tests/integration/test_api_regressions.py -v
```

Nếu không chạy được test vì thiếu DB/env, báo rõ lệnh đã thử và lý do.

### Legacy dependency map từ `docs/TASKS.md`

Chỉ dùng khi user đang làm lại V1 tasks từ đầu:

```
TASK-001 (scaffold)
  → TASK-002 (enums)
  → TASK-005 (config)
  → TASK-006 (database)
      → TASK-003 (schemas)
      → TASK-004 (models)
          → TASK-008 (migration)
          → TASK-009..011 (repositories)
              → TASK-012..016 (services)
                  → TASK-017..020 (API)
                      → TASK-021 (integration)
                      → TASK-022 (tests)
```

### Lưu ý

- Không skip dependency còn hiệu lực.
- Không chờ user sau từng file trừ khi user yêu cầu hoặc scope/risk cao.
- Nếu gặp unexpected dirty changes trong file đang sửa, dừng và hỏi user.
