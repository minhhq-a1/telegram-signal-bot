# Prompt Library — Signal Bot V1
<!-- 
  Tập hợp toàn bộ prompt theo lifecycle dự án.
  Copy và dùng ngay — không cần chỉnh sửa trừ phần [IN HOA].
  
  Trạng thái:
  ✅ Đã có sẵn trong Sprint/Workflow files
  🆕 Prompt mới trong file này
-->

---

## Nhóm 1 — Development (3 sprints)

> ✅ Đã có chi tiết trong `SPRINT_01.md`, `SPRINT_02.md`, `SPRINT_03.md`

### P-01: Bắt đầu Sprint 01 — Scaffold + Core Domain

```
Tôi bắt đầu build Signal Bot V1 từ đầu (greenfield).

Hãy viết theo thứ tự sau, mỗi bước hoàn chỉnh trước khi sang bước tiếp:

1. requirements.txt
2. .env.example
3. app/core/enums.py
4. app/core/config.py
5. app/core/database.py
6. app/core/logging.py
7. app/domain/schemas.py
8. app/domain/models.py
9. migrations/001_init.sql

Dừng sau mỗi file để tôi copy và verify.
```

*Upload kèm: `CONVENTIONS.md`, `DATABASE_SCHEMA.md`*

---

### P-02: Bắt đầu Sprint 02 — Repositories + Services

```
Sprint 01 xong. Giờ viết repositories và services theo thứ tự:

REPOSITORIES:
1. app/repositories/webhook_event_repo.py
2. app/repositories/signal_repo.py
3. app/repositories/filter_result_repo.py
4. app/repositories/decision_repo.py
5. app/repositories/telegram_repo.py
6. app/repositories/config_repo.py
7. app/repositories/market_event_repo.py

SERVICES:
8. app/services/auth_service.py
9. app/services/signal_normalizer.py
10. app/services/filter_engine.py  ← CORE: implement đúng 4 phases từ FILTER_RULES.md
11. app/services/message_renderer.py
12. app/services/telegram_notifier.py

Dừng sau mỗi file để tôi verify.
```

*Upload kèm: `FILTER_RULES.md`, `PAYLOAD_CONTRACT.md`, `CONVENTIONS.md`*

---

### P-03: Bắt đầu Sprint 03 — API + Wiring + Tests

```
Sprint 02 xong. Giờ viết API layer và tests:

API:
1. app/api/health_controller.py
2. app/api/webhook_controller.py
3. app/api/signal_controller.py
4. app/main.py

TESTS:
5. tests/conftest.py
6. tests/unit/test_filter_engine.py
7. tests/unit/test_signal_normalizer.py
8. tests/unit/test_message_renderer.py
9. tests/unit/test_telegram_notifier.py
10. tests/integration/test_webhook_endpoint.py
11. tests/integration/test_audit_trail.py
12. tests/integration/test_failure_handling.py
13. tests/integration/test_news_block.py

Dừng sau mỗi file để tôi verify.
```

*Upload kèm: `TEST_CASES.md`, `QA_STRATEGY.md`*

---

## Nhóm 2 — Debug & Fix

### P-04: Fix lỗi cụ thể 🆕

```
Gặp lỗi khi chạy [TÊN FILE]:

[PASTE FULL STACK TRACE]

Lệnh đã chạy: [LỆNH]

Fix trực tiếp — không rewrite toàn bộ file, chỉ show phần thay đổi.
```

---

### P-05: Debug signal bị route sai 🆕

```
Signal [SIGNAL_ID] bị route [PASS_WARNING/REJECT] nhưng tôi expect [PASS_MAIN].

Kết quả filter_results từ DB:
[PASTE OUTPUT CỦA QUERY:
SELECT rule_code, result, severity, score_delta, details
FROM signal_filter_results
WHERE signal_row_id = (SELECT id FROM signals WHERE signal_id = '[SIGNAL_ID]')
ORDER BY created_at;]

Phân tích: rule nào gây ra routing sai và lý do?
```

---

### P-06: Debug import error hoặc test fail 🆕

```
Test fail với lỗi sau:

[PASTE pytest output]

File liên quan: [TÊN FILE]

Fix lỗi — không thay đổi test logic, chỉ fix implementation.
```

---

## Nhóm 3 — Code Review

### P-07: Review một file trước khi commit 🆕

```
Review file app/services/filter_engine.py trước khi commit.

Kiểm tra:
1. Boolean gate logic đúng không — routing dựa trên FAIL/WARN, không dựa trên server_score threshold
2. Phase order đúng không — Phase 1 short-circuit trước Phase 2, 3
3. server_score chỉ tính để log, không dùng để route
4. Không raise exception — luôn return FilterExecutionResult
5. Conventions: type hints, SQLAlchemy 2.0 style, secrets.compare_digest

[PASTE NỘI DUNG FILE]
```

---

### P-08: Review toàn bộ sprint trước khi merge 🆕

```
Sprint [01/02/03] xong. Review toàn bộ trước khi merge.

Files đã tạo: [DANH SÁCH]

Kiểm tra:
1. Import consistency — không circular import
2. Convention violations — Optional[], db.query(), hardcoded threshold
3. Missing type hints
4. Anti-patterns: server_score làm threshold, Telegram trước db.commit(), log secret
5. Test coverage — mỗi service có ít nhất 1 unit test

Chỉ báo vấn đề, không rewrite.
```

---

## Nhóm 4 — Testing & QA

### P-09: Viết test cho một tình huống cụ thể 🆕

```
Viết pytest test cho tình huống:
[MÔ TẢ TÌNH HUỐNG — VD: "signal với NEWS_BLOCK active phải bị REJECT"]

Yêu cầu:
- Dùng fixtures từ conftest.py đã có
- Setup DB data trực tiếp nếu cần (không đi qua API)
- Assert cả response lẫn DB state
- Map với AC hoặc TC trong QA_STRATEGY.md nếu có
```

---

### P-10: Chạy acceptance criteria check trước go-live 🆕

```
Chuẩn bị go-live. Giúp tôi verify 6 acceptance criteria trong QA_STRATEGY.md.

Môi trường: [local/staging]
DB URL: [đã set trong .env]
Telegram: [mock/real]

Chạy lần lượt từng AC, dừng nếu fail và báo lý do.
```

---

### P-11: Phân tích test coverage gaps 🆕

```
Đọc QA_STRATEGY.md và TEST_CASES.md.

Liệt kê:
1. TC nào chưa có test file tương ứng trong tests/
2. AC nào chưa được cover
3. Đề xuất viết test theo thứ tự ưu tiên (critical path trước)
```

---

## Nhóm 5 — Paper Trading

### P-12: Setup paper trading 🆕

```
Sprint 03 done, chuẩn bị bắt đầu paper trading.

Giúp tôi:
1. Verify deployment checklist từ DEPLOYMENT.md
2. Tạo TradingView alert cho 3 TF đầu tiên: 3m, 5m, 15m
3. Confirm Telegram channels nhận được message đúng format
4. Setup monitoring query để track daily

Bắt đầu từ bước nào còn thiếu.
```

---

### P-13: Weekly paper trading review 🆕

```
Tuần [N] paper trading. Kết quả từ DB:

[PASTE OUTPUT 3 QUERIES TỪ QA_STRATEGY.md section 7]

Phân tích:
1. Pass rate theo TF có bình thường không? (red flag: >80% hoặc <10%)
2. Reject reason nào chiếm nhiều nhất — có phải misconfigured rule không?
3. Có signal nào bị miss mà tôi muốn catch không?
4. Đề xuất điều chỉnh config nếu cần (thay đổi trong system_configs, không hardcode)
```

---

### P-14: Kết thúc paper trading — quyết định go-live 🆕

```
Kết thúc [N] tuần paper trading. Tổng hợp:

Pass rate: [%]
Tổng signals: [N]
Reject reasons top 3: [LIST]
TF hiệu quả nhất: [TF]
TF nhiều noise nhất: [TF]

Dựa trên kết quả này:
1. Đánh giá: có nên go-live không?
2. Rule nào cần điều chỉnh ngưỡng?
3. TF nào nên disable tạm?
4. Config changes cụ thể (SQL UPDATE vào system_configs)
```

---

## Nhóm 6 — Vận hành thường ngày

### P-15: Thêm news block event 🆕

```
Sắp có sự kiện kinh tế: [TÊN SỰ KIỆN]
Thời gian: [ISO-8601 UTC]
Impact: HIGH/MEDIUM

Viết SQL INSERT vào market_events để block signal trong window 15 phút trước, 30 phút sau.
Verify bằng query check active events.
```

---

### P-16: Điều chỉnh config không cần redeploy 🆕

```
Muốn thay đổi config:
- [THAY ĐỔI 1 — VD: confidence threshold 5m từ 0.78 xuống 0.76]
- [THAY ĐỔI 2]

Viết SQL UPDATE vào system_configs.
Confirm config_repo cache 30s — thay đổi sẽ có hiệu lực sau tối đa 30s.
```

---

### P-17: Investigate signal bất thường 🆕

```
Thấy [HIỆN TƯỢNG — VD: "không nhận được signal nào trong 6 giờ" / "spam 20 signals trong 1 phút"].

Chạy query diagnostic:
[PASTE OUTPUT CỦA]:
SELECT * FROM signals ORDER BY created_at DESC LIMIT 20;
SELECT * FROM signal_decisions WHERE created_at > NOW() - INTERVAL '6 hours';
SELECT decision_reason, COUNT(*) FROM signal_decisions GROUP BY decision_reason ORDER BY count DESC;

Phân tích nguyên nhân và đề xuất fix.
```

---

### P-18: Tạo Dockerfile và deploy 🆕

```
Chuẩn bị deploy lên production.

Tạo:
1. Dockerfile (Python 3.12-slim, non-root user, health check)
2. docker-compose.yml (app + postgres, với volumes và restart policy)
3. nginx.conf (reverse proxy, HTTPS redirect)

Theo đúng cấu hình trong DEPLOYMENT.md.
```

---

## Nhóm 7 — V1.1 Planning

### P-19: Sau paper trading — plan V1.1 improvements 🆕

```
Paper trading xong. Kết quả đã có. Giờ plan V1.1.

Known issues cần fix:
1. HTF bias: hiện disabled vì circular dependency — cần independent market data source
2. Confidence threshold: sample 136 signals nhỏ — cần calibrate với outcome thực
3. News block: nhập tay dễ miss — cần automation

Đề xuất V1.1 scope theo thứ tự ưu tiên dựa trên impact vs effort.
Giữ đúng tinh thần: notification-only, audit-first, không auto-trade.
```

---

### P-20: Thêm timeframe mới vào whitelist 🆕

```
Muốn thêm timeframe [TF] vào whitelist sau khi đã có đủ data paper trading.

Cần làm:
1. UPDATE system_configs — thêm TF vào allowed_timeframes và confidence_thresholds
2. Tạo TradingView alert cho TF này
3. Verify không break existing tests

Có gì cần thận trọng khi thêm TF này không?
```

---

## Nhóm 8 — Context Management

### P-21: Tiếp tục conversation mới (resume) 🆕

```
Tiếp tục dự án Signal Bot V1.

Trạng thái hiện tại:
- Đã xong: [LIỆT KÊ FILES/TASKS ĐÃ DONE]
- Đang làm: [TASK HIỆN TẠI]
- Vấn đề: [MÔ TẢ NẾU CÓ]

Cần làm tiếp: [TASK CỤ THỂ]
```

---

### P-22: Hỏi về business logic cụ thể 🆕

```
Câu hỏi về [TOPIC]:

[CÂU HỎI]

Tham chiếu docs liên quan nếu có câu trả lời trong:
FILTER_RULES.md / PAYLOAD_CONTRACT.md / DATABASE_SCHEMA.md / QA_STRATEGY.md
```

---

## Index nhanh

| Tình huống | Prompt |
|---|---|
| Bắt đầu Sprint 01 | P-01 |
| Bắt đầu Sprint 02 | P-02 |
| Bắt đầu Sprint 03 | P-03 |
| Fix lỗi / stack trace | P-04 |
| Debug signal route sai | P-05 |
| Debug test fail | P-06 |
| Review file trước commit | P-07 |
| Review toàn sprint | P-08 |
| Viết test case mới | P-09 |
| Verify acceptance criteria | P-10 |
| Phân tích test coverage | P-11 |
| Setup paper trading | P-12 |
| Weekly paper review | P-13 |
| Quyết định go-live | P-14 |
| Thêm news block event | P-15 |
| Điều chỉnh config runtime | P-16 |
| Investigate bất thường | P-17 |
| Deploy production | P-18 |
| Plan V1.1 | P-19 |
| Thêm timeframe mới | P-20 |
| Resume conversation | P-21 |
| Hỏi business logic | P-22 |

---

## Nguyên tắc dùng prompt hiệu quả

**Ngắn hơn khi đã có Project Instructions.** P-01 đến P-03 ngắn vì Project Instructions đã inject context. Không cần nhắc lại tech stack hay principles.

**Paste output thực tế.** P-05, P-13, P-17 yêu cầu paste DB query output — đừng mô tả bằng lời, paste trực tiếp.

**1 việc / 1 conversation.** Không mix P-04 (fix bug) với P-07 (review) trong cùng conversation. Context dài làm giảm chất lượng.

**Resume bằng P-21.** Khi bắt đầu conversation mới giữa chừng dự án, luôn dùng P-21 để set lại context trước khi làm việc.
