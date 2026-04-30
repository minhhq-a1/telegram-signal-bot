# Development Workflow — Release 1.2

> **Purpose:** Chuẩn hóa quy trình phát triển cho nhánh `release/1.2` để V1.2 được triển khai có kiểm soát, dễ review, và không làm bẩn `main`.

---

## 1. Mục tiêu của workflow này

Workflow này nhằm đảm bảo:

- V1.2 được phát triển theo roadmap đã chốt tại `docs/ROADMAP_V1.2.md`
- `release/1.2` là nhánh tích hợp ổn định cho toàn bộ scope V1.2
- mỗi thay đổi được tách nhỏ, dễ review, dễ rollback
- test, migration, docs và dashboard UX/UI được kiểm soát theo từng task
- chỉ merge vào `main` khi toàn bộ release đạt mức sẵn sàng

Workflow này áp dụng cho:

- backend API
- migrations
- analytics
- dashboard command center
- test suite
- docs và runbooks liên quan V1.2

---

## 2. Branching model

### Branch chính

- `main`
  - Nhánh ổn định nhất.
  - Chỉ nhận code đã đủ chất lượng để phát hành hoặc gần phát hành.

- `release/1.2`
  - Nhánh tích hợp cho toàn bộ công việc V1.2.
  - Tất cả feature branch của V1.2 merge vào đây trước.
  - Dùng để chạy verify tích hợp theo phase và theo milestone.

### Branch tác vụ

Mỗi task hoặc cụm task nhỏ phải đi trên branch riêng, cắt từ `release/1.2`.

Convention đề xuất:

```text
feature/v12-a1-verify-targets
feature/v12-a2-correlation-id
feature/v12-a3-health-endpoints
feature/v12-a4-telegram-hardening
feature/v12-b1-outcome-schema
feature/v12-c2-command-center-dashboard
fix/v12-dashboard-empty-state
chore/v12-docs-sync
```

### Nguyên tắc branching

- Không develop trực tiếp trên `release/1.2` trừ cập nhật rất nhỏ và đã thống nhất trước.
- Không merge task đang dở dang vào `release/1.2`.
- Không merge feature branch V1.2 trực tiếp vào `main`.
- Nếu task lớn, chia nhỏ thành nhiều branch theo PR breakdown trong `docs/ROADMAP_V1.2.md`.

---

## 3. Source of truth cho V1.2

Mọi quyết định implementation phải bám theo các tài liệu sau, theo thứ tự ưu tiên:

1. `AGENTS.md`
2. `docs/ROADMAP_V1.2.md`
3. `docs/FILTER_RULES.md`
4. `docs/PAYLOAD_CONTRACT.md`
5. `docs/DATABASE_SCHEMA.md`
6. `docs/QA_STRATEGY.md`
7. `docs/API_REFERENCE.md`

Nếu code hiện tại khác roadmap/spec:

- không tự ý “đoán” là code đúng hơn spec
- phải ghi rõ assumption trong PR hoặc cập nhật lại doc tương ứng
- nếu ảnh hưởng business rule, chốt lại trước khi merge

---

## 4. Quy trình làm việc cho mỗi task

### Bước 1: Chọn task từ roadmap

Chỉ lấy task từ `docs/ROADMAP_V1.2.md` hoặc bugfix phát sinh trực tiếp từ V1.2.

Ví dụ:

- `A1` Verify targets + docs cleanup
- `A2` Correlation ID + pipeline summary log
- `B3` Outcome API
- `C2` Dashboard Trading Ops Command Center

### Bước 2: Tạo branch từ `release/1.2`

```bash
git checkout release/1.2
git pull
git checkout -b feature/v12-a2-correlation-id
```

### Bước 3: Thực hiện thay đổi với scope nhỏ

Mỗi branch nên cố gắng chỉ chứa một thay đổi logic chính:

- một API slice
- một migration + repository slice
- một dashboard panel slice
- một observability slice

Nếu task lớn hơn mức đó, phải chia branch tiếp.

### Bước 4: Update test và docs liên quan

Nếu thay đổi chạm vào:

- API -> update `docs/API_REFERENCE.md`
- schema/migration -> update `docs/DATABASE_SCHEMA.md`
- QA flow -> update `docs/QA_STRATEGY.md` hoặc smoke checklist
- dashboard contract -> update `docs/ROADMAP_V1.2.md` nếu implementation phải tinh chỉnh spec

### Bước 5: Verify branch trước khi review

Tối thiểu phải chạy verify phù hợp với scope của branch.

Ví dụ:

```bash
python3 -m pytest tests/unit -q
python3 -m pytest tests/integration/test_api_regressions.py -q
python3 -m pytest tests/integration/test_dashboard_auth.py -q
bash scripts/smoke_local.sh
```

Không cần chạy full suite cho mọi task nhỏ nếu task chỉ đụng slice hẹp, nhưng trước khi merge phase lớn vào `release/1.2` thì bắt buộc full verify.

### Bước 6: Review và merge vào `release/1.2`

Checklist review:

- scope đúng roadmap
- không vi phạm project invariants
- test đủ cho phần thay đổi
- docs được cập nhật
- không có secret trong logs hoặc UI
- không làm sai persist-before-notify, idempotency, audit-first

Sau khi pass review, merge branch vào `release/1.2`.

---

## 5. Scope rules cho `release/1.2`

### Được phép vào `release/1.2`

- task nằm trong `docs/ROADMAP_V1.2.md`
- bugfix phát sinh do code V1.2
- test bổ sung để bảo vệ behavior V1.2
- docs/runbook phục vụ V1.2
- dashboard UX/UI improvements đã được chốt trong roadmap

### Không nên vào `release/1.2`

- feature ngoài roadmap
- refactor lớn không phục vụ trực tiếp V1.2
- đổi business rule không qua docs/spec review
- “tiện tay sửa thêm” unrelated module
- auto-trade hoặc broker execution

Nếu có ý tưởng mới nhưng chưa chắc:

- ghi backlog riêng
- không trộn vào branch release đang active

---

## 6. Merge strategy theo phase

Không merge big-bang cuối kỳ. Merge dần theo phase.

### Phase A — Production hardening

Ưu tiên merge trước:

- `A1` Verify targets + docs cleanup
- `A2` Correlation ID + summary log
- `A3` Health endpoints
- `A4` Telegram notifier hardening

### Phase B — Outcome loop

Sau khi Phase A ổn:

- `B1` Outcome schema upgrade
- `B2` Outcome repository
- `B3` Outcome API
- `B4` Auto-create OPEN outcome

### Phase C — Dashboard / analytics

Nên tách dashboard theo sub-slice:

- backend aggregation endpoint
- dashboard shell/layout
- ops snapshot cards
- signal radar
- risk & reliability panel
- performance intelligence
- recent outcomes + export shortcut
- calibration insight section

### Phase D/E — Calibration and governance

Làm sau khi data loop đủ dùng:

- batch reverify
- offline replay
- calibration report
- config audit/versioning
- config admin API
- market context snapshot slice

---

## 7. Verify gate cho mỗi feature branch

Trước khi merge branch vào `release/1.2`, branch owner phải xác nhận các mục phù hợp.

### Minimum gate

- code chạy được
- test liên quan pass
- docs liên quan được cập nhật
- không có placeholder, dead path, hoặc migration non-idempotent

### Nếu có backend business logic

Chạy ít nhất:

```bash
python3 -m pytest tests/unit -q
python3 -m pytest tests/integration/test_api_regressions.py -q
```

### Nếu có migration

Chạy thêm:

```bash
python3 scripts/db/migrate.py
python3 -m pytest tests/integration/test_ci_migration_fixture.py -q
```

### Nếu có dashboard/API analytics

Chạy thêm:

```bash
python3 -m pytest tests/integration/test_dashboard_auth.py -q
python3 -m pytest tests/integration/test_analytics.py -q
```

### Nếu có notifier / webhook pipeline

Chạy thêm:

```bash
python3 -m pytest tests/unit/test_telegram_notifier.py -q
python3 -m pytest tests/integration/test_webhook_endpoint.py -q
```

---

## 8. Verify gate cho `release/1.2`

Sau mỗi milestone hoặc trước khi chuẩn bị merge về `main`, phải verify trên chính `release/1.2`.

### Milestone verify

```bash
python3 -m pytest -q
bash scripts/smoke_local.sh
python3 scripts/db/migrate.py
python3 -m pytest tests/integration/test_ci_migration_fixture.py -q
```

### Functional checks bắt buộc

- webhook happy path
- invalid secret path
- invalid schema path
- duplicate/idempotency path
- Telegram fail path
- reverify path
- analytics path
- dashboard auth path
- dashboard command center empty state path
- outcome create/open/close path

### Command Center specific checks

- desktop layout usable
- mobile layout usable
- health pills render đúng state
- signal radar filter hoạt động
- risk alerts render đúng empty/non-empty state
- charts không crash khi data rỗng
- không lộ token hoặc secret trong UI

---

## 9. Hotfix flow trong thời gian làm V1.2

Có hai loại fix:

### Production-critical fix

Nếu bug ảnh hưởng production hiện tại:

1. tạo branch fix từ `main`
2. sửa và merge vào `main`
3. back-merge fix đó vào `release/1.2`

Không để production fix chỉ tồn tại trong `release/1.2`.

### Release-local fix

Nếu bug chỉ liên quan đến code đang phát triển trên V1.2:

1. tạo branch từ `release/1.2`
2. fix
3. merge lại vào `release/1.2`

---

## 10. Sync strategy với `main`

Trong thời gian `release/1.2` còn sống, cần sync định kỳ với `main` nếu có thay đổi quan trọng.

Recommended:

- sync theo nhịp nhỏ, không để diverge quá lâu
- ưu tiên merge `main` vào `release/1.2` thay vì rebase mạnh tay nếu đã có nhiều branch phụ thuộc
- sau mỗi lần sync, chạy lại regression tương ứng

Ví dụ:

```bash
git checkout release/1.2
git pull
git merge main
```

Nếu conflict ở docs/spec/test, phải giải quyết theo source of truth của V1.2.

---

## 11. Commit và PR convention

### Commit message

Ví dụ:

```text
feat(v1.2): add correlation id to webhook pipeline
test(v1.2): cover outcome close math for short signals
docs(v1.2): refine command center dashboard workflow
fix(v1.2): handle empty command center response safely
```

### PR title

Format đề xuất:

```text
[V1.2][A2] Correlation ID + pipeline summary log
[V1.2][B3] Outcome API
[V1.2][C2] Command Center dashboard shell and health panels
```

### PR description nên có

- task reference từ roadmap
- scope in/out
- migrations yes/no
- verify commands đã chạy
- screenshots nếu có dashboard/UI
- follow-up items nếu còn deferred

---

## 12. Dashboard-specific workflow

Dashboard V1.2 là hạng mục có UX/UI quan trọng, nên cần quy trình chặt hơn.

### Nguyên tắc

- backend contract đi trước hoặc đi song song với UI shell
- UI không phụ thuộc build tooling mới
- không thêm framework frontend lớn cho V1.2
- mọi panel phải có loading, empty, error states
- desktop và mobile đều phải check

### Thứ tự đề xuất

1. `ops-command-center` aggregation endpoint
2. dashboard shell + design tokens
3. command header + health pills
4. ops snapshot cards
5. signal radar
6. risk & reliability panel
7. performance intelligence charts
8. recent outcomes table
9. calibration insights
10. polish pass cho spacing, typography, empty states, motion

### UI review checklist

- có đúng visual direction “Trading Ops Command Center” không
- có còn giống generic admin template không
- hierarchy của số liệu có rõ không
- trạng thái WARN/FAIL có nổi bật nhưng không lòe loẹt không
- mobile có đọc được không
- table/chart có degrade gracefully không

---

## 13. Release readiness trước khi merge về `main`

`release/1.2` chỉ được promote sang `main` khi đạt đủ các điều kiện sau:

- roadmap core scope đã hoàn thành hoặc được explicit de-scope
- migrations chạy được từ DB sạch
- full test suite pass
- command center dashboard usable
- outcome loop usable cho paper trading
- docs vận hành đủ dùng
- không còn blocker severity cao
- invariants của project không bị vi phạm

Final checks nên có:

```bash
python3 -m pytest -q
bash scripts/smoke_local.sh
python3 scripts/db/migrate.py
```

Nếu có deploy staging hoặc pre-prod checklist, chạy thêm checklist đó trước khi merge.

---

## 14. Definition of Done cho workflow này

Workflow này được xem là đang được áp dụng đúng khi:

- mọi task V1.2 đi từ branch riêng cắt từ `release/1.2`
- `release/1.2` chỉ nhận code đã verify theo scope phù hợp
- docs/test/migration được update đồng bộ với code
- milestone verify được chạy định kỳ trên `release/1.2`
- dashboard UX/UI được review như một deliverable chính, không phải phần phụ
- chỉ merge `release/1.2` vào `main` khi đạt release readiness

---

## 15. Recommended next move

Sau khi tài liệu này được commit, thứ tự thực thi đề xuất là:

1. `A1` Verify targets + docs cleanup
2. `A2` Correlation ID + pipeline summary log
3. `A3` Health readiness endpoints
4. `A4` Telegram notifier hardening

Đây là Sprint V1.2-A — nền tảng cho toàn bộ phần outcome, analytics, và dashboard command center phía sau.
