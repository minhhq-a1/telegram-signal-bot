# Skill: Sprint Runner
## Description
Bắt đầu hoặc tiếp tục một sprint từ TASKS.md.
Trigger khi user nói: "bắt đầu sprint", "tiếp tục từ task", "làm TASK-0XX", "sprint mới".

## Instructions

### Bước 1 — Đọc trạng thái

Trước khi làm bất kỳ thứ gì, đọc `docs/TASKS.md` và xác định:
- Task nào đã done (user confirm)
- Task nào cần làm tiếp
- Dependency: task N phải xong trước task N+1 theo dependency map

### Bước 2 — Confirm với user

Báo cáo ngắn:
```
Trạng thái: [X/22 tasks done]
Làm tiếp: TASK-0XX — [tên task]
File sẽ tạo: [danh sách]
Bắt đầu không?
```

### Bước 3 — Implement

Làm **từng file một**. Sau mỗi file:
1. Chạy syntax check: `python -c "from [module] import [class]"`
2. Tạo artifact tóm tắt
3. Dừng và chờ user confirm trước khi sang file tiếp

### Bước 4 — Verify DoD

Sau khi xong cả sprint, chạy đúng lệnh verify trong TASKS.md của task đó.

### Dependency Map (tóm tắt)

```
TASK-001 (scaffold)
  → TASK-002 (enums) → TASK-003 (schemas) → TASK-004 (models)
  → TASK-005 (config) → TASK-006 (database)
      → TASK-008 (migration)
      → TASK-009..011 (repositories)
          → TASK-012..016 (services)
              → TASK-017..020 (API)
                  → TASK-021 (integration test)
                  → TASK-022 (unit tests)
```

### Lưu ý

- Không skip dependency dù user yêu cầu
- Không làm 2 task song song trong 1 conversation
- Nếu gặp lỗi import → fix trước khi tiếp tục
