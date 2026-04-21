# Sprint 03 — API Layer + Wiring + Tests
<!--
  Dùng sau khi Sprint 02 hoàn thành.
  Upload kèm: TEST_CASES.md
-->

---

## Prompt để bắt đầu session

```
API & FIXES:
1. ĐỌC VÀ XỬ LÝ TRƯỚC: `docs/SPRINT_01_02_FIX_CHECKLIST.md` (Thực hiện tuần tự 14 FIXES để vá lỗi Sprint 1-2).
2. app/api/health_controller.py
3. app/api/webhook_controller.py   ← CORE: implement đúng flow được cập nhật (KHẮC PHỤC RỦI RO KIẾN TRÚC TỪ MAX)
4. app/api/signal_controller.py    ← GET /signals/{signal_id}
5. app/main.py                     ← wire up routers

🚨 THIÊN LÔI CHÚ Ý (Từ Max - Architect): Giải quyết 2 rủi ro kiến trúc trước khi code WebhookController!
Rủi ro 1: KHÔNG GỬI TELEGRAM TRƯỚC KHI COMMIT (xem TASK-018)
- Bắt buộc commit lần 1 (Signals, Filter, Decision) TRƯỚC.
- Gọi Telegram xong mới log và commit lần 2.
Rủi ro 2: MẤT THÔNG BÁO REJECT ADMIN
- Nếu final_decision == REJECT và config.get('LOG_REJECT_TO_ADMIN') == True, phải gởi tin nhắn Reject sang channel ADMIN.


TESTS (dùng TEST_CASES.md + QA_STRATEGY.md làm input):
5. tests/conftest.py                              ← fixtures + deep_merge()
6. tests/unit/test_filter_engine.py
7. tests/unit/test_signal_normalizer.py
8. tests/unit/test_message_renderer.py
9. tests/unit/test_telegram_notifier.py           ← retry + respx mock
10. tests/integration/test_webhook_endpoint.py    ← TC-001 đến TC-016
11. tests/integration/test_audit_trail.py         ← AC-006 (QA_STRATEGY)
12. tests/integration/test_failure_handling.py    ← AC-002, AC-004
13. tests/integration/test_news_block.py          ← AC-005, TC-019

Upload kèm TEST_CASES.md và QA_STRATEGY.md để viết test đúng.
```

---

## Checklist sau Sprint 03

```bash
# Integration test (cần test DB)
python -m pytest tests/integration/test_webhook_endpoint.py -v

# Core test cases phải pass
python -m pytest tests/ -k "tc001 or tc002 or tc003 or tc006 or tc007" -v

# End-to-end smoke test
curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d '{"secret":"...","signal_id":"smoke-001","signal":"long",...}'

# Verify audit trail
psql $DATABASE_URL -c "
  SELECT we.auth_status, s.signal_id, sd.decision, tm.delivery_status
  FROM webhook_events we
  JOIN signals s ON s.webhook_event_id = we.id
  JOIN signal_decisions sd ON sd.signal_row_id = s.id
  LEFT JOIN telegram_messages tm ON tm.signal_row_id = s.id
  ORDER BY we.received_at DESC LIMIT 5;
"
```

---

## DoD Sprint 03 = DoD toàn dự án

- [ ] `GET /api/v1/health` → 200
- [ ] Valid LONG 5m → 200 PASS_MAIN + Telegram sent
- [ ] Secret sai → 401
- [ ] TF `30S` → 400 UNSUPPORTED_TIMEFRAME
- [ ] Duplicate `signal_id` → 200 DUPLICATE, DB count không tăng
- [ ] Audit trail: trace raw webhook → signal → decision → telegram
- [ ] TC-001 đến TC-016 trong TEST_CASES.md pass
- [ ] AC-001 đến AC-006 trong QA_STRATEGY.md pass
- [ ] `GET /api/v1/signals/{id}` trả đúng detail

---

## Nếu có lỗi khi chạy

Paste error vào chat kèm:
- File đang chạy
- Lệnh đã dùng
- Stack trace đầy đủ

Claude sẽ fix trực tiếp, không rewrite từ đầu.
