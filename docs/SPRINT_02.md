# Sprint 02 — Repositories + Services
<!--
  Dùng sau khi Sprint 01 hoàn thành và verify xong.
  Upload kèm: FILTER_RULES.md, PAYLOAD_CONTRACT.md, CONVENTIONS.md
-->

---

## Prompt để bắt đầu session

```
Sprint 01 xong. Giờ viết repositories và services theo thứ tự:

REPOSITORIES:
1. app/repositories/webhook_event_repo.py
2. app/repositories/signal_repo.py       ← quan trọng: find_recent_same_side() và find_recent_similar()
3. app/repositories/filter_result_repo.py  ← bulk_insert()
4. app/repositories/decision_repo.py
5. app/repositories/telegram_repo.py
6. app/repositories/config_repo.py        ← get_signal_bot_config() với TTL cache 30s
7. app/repositories/market_event_repo.py  ← find_active_around()

SERVICES:
8. app/services/auth_service.py           ← secrets.compare_digest()
9. app/services/signal_normalizer.py      ← tính risk_reward
10. app/services/filter_engine.py         ← CORE: implement đúng 4 phases từ FILTER_RULES.md
11. app/services/message_renderer.py      ← render_main(), render_warning(), không expose expected_wr
12. app/services/telegram_notifier.py     ← async httpx + retry 3x exponential backoff

Upload kèm FILTER_RULES.md để implement filter_engine chính xác.
```

---

## Checklist sau Sprint 02

```bash
# Unit test filter engine (không cần DB)
python -m pytest tests/unit/test_filter_engine.py -v

# Verify 8 test cases core
python -m pytest tests/unit/test_filter_engine.py::test_pass_main -v
python -m pytest tests/unit/test_filter_engine.py::test_reject_low_confidence -v
python -m pytest tests/unit/test_filter_engine.py::test_reject_strong_downtrend_long -v
python -m pytest tests/unit/test_filter_engine.py::test_reject_low_rr -v
```

---

## DoD Sprint 02

- [ ] `FilterEngine.run()` không raise exception trong mọi trường hợp — luôn trả `FilterExecutionResult`
- [ ] Phase 1 short-circuit: symbol sai → không chạy phase 2, 3, 4
- [ ] `server_score` được tính đúng và lưu DB (analytics only — KHÔNG dùng làm routing threshold)
- [ ] `SHORT_SQUEEZE` dùng `rr_min_squeeze=2.0`, không phải `rr_min_base=1.5`
- [ ] Message renderer không crash với `None` optional fields (hiển thị N/A)
- [ ] Telegram notifier retry đúng 3 lần với backoff 1s/2s/4s
