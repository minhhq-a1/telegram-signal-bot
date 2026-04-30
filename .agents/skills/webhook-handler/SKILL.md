---
name: webhook-handler
description: "Implement or debug the TradingView webhook ingestion flow with audit-first and persist-before-notify guarantees."
---

# Skill: Webhook Handler
## Description
Implement hoặc debug `app/api/webhook_controller.py`, `app/services/webhook_ingestion_service.py`, và flow xử lý webhook end-to-end.
Trigger khi user đề cập: webhook, controller, flow, audit-first, persist trước notify, Telegram notify.

## Instructions

Đọc `docs/ARCHITECTURE.md`, `docs/API_REFERENCE.md`, `docs/QA_STRATEGY.md`, và code hiện tại trong `app/services/webhook_ingestion_service.py` trước khi sửa.

### Flow hiện tại bắt buộc

`webhook_controller.py` chỉ đọc raw body/request metadata, khởi tạo `WebhookIngestionService`, gọi `ingest()`, rồi schedule background notification nếu có.

```python
async def handle_tradingview_webhook(request, background_tasks, db):
    raw_body_text = (await request.body()).decode("utf-8", errors="replace")
    result = await service.ingest(raw_body_text, source_ip, headers)

    if result.is_error:
        return JSONResponse(status_code=result.status_code, content=result.body.model_dump(mode="json"))

    if result.notification_job is not None:
        background_tasks.add_task(service.deliver_notification, result.notification_job)

    return result.body
```

### `WebhookIngestionService.ingest()` order

Persist trước, notify sau. Audit-first cho invalid requests.

1. Parse raw JSON.
   - Invalid JSON: insert `webhook_events` with `is_valid_json=False`, `auth_status=MISSING`, commit, return `400 INVALID_JSON`.
2. Validate Pydantic schema.
   - Invalid schema: insert `webhook_events`, commit, return `400 INVALID_SCHEMA`.
3. Validate secret with `AuthService.validate_secret()`; implementation must use `secrets.compare_digest()`.
4. Insert `webhook_events` for valid JSON/schema payload, with redacted headers/body.
5. Invalid secret: mark auth failure, commit audit row, return `401 INVALID_SECRET`; do not insert `signals`.
6. Idempotency check by `signal_id`.
   - Existing signal: commit any audit work and return `200` with `decision="DUPLICATE"`; do not insert signal again.
7. Normalize payload via `SignalNormalizer.normalize(webhook_event.id, payload)`.
8. Insert `signals` inside nested transaction; handle race-condition `IntegrityError` by returning `DUPLICATE` if row now exists.
9. Load DB config via `ConfigRepository.get_signal_bot_config()`.
10. Run `FilterEngine(config, signal_repo, market_repo).run(norm_data)`; engine must not raise for normal rule failures.
11. Persist `server_score`, filter results, and signal decision.
12. Build `NotificationJob` for `PASS_MAIN`, `PASS_WARNING`, and `REJECT` only when `log_reject_to_admin` is true.
13. Commit DB transaction.
14. Return `200 accepted` immediately; controller schedules Telegram delivery in `BackgroundTasks`.
15. `deliver_notification()` sends Telegram and writes `telegram_messages` audit row in a fresh DB session.

### Notification behavior

| Decision / route | Message | Delivery |
|---|---|---|
| `PASS_MAIN` / `MAIN` | `MessageRenderer.render_main()` | background Telegram + audit row |
| `PASS_WARNING` / `WARN` | `MessageRenderer.render_warning()` | background Telegram + audit row |
| `REJECT` / `ADMIN` | only if `log_reject_to_admin=true` | background Telegram + audit row |
| `REJECT` / `NONE` | no notification job | no Telegram row unless design changes |

### Error handling

| Tình huống | Hành động |
|---|---|
| Invalid JSON/schema/secret | Always insert `webhook_events`, commit, return documented error |
| Duplicate `signal_id` | Return `200 DUPLICATE`, no duplicate signal insert |
| DB fail after signal insert starts | Roll back transaction; raw webhook row may already exist depending stage |
| Telegram fail after retries | Log `telegram_messages.delivery_status=FAILED`; do not roll back persisted signal/decision |
| Missing chat id | `notify()` returns `FAILED`; `deliver_notification()` logs audit row with error |

### Verify

```bash
rtk python -m pytest tests/integration/test_webhook_endpoint.py -v
rtk python -m pytest tests/integration/test_api_regressions.py -v
rtk python -m pytest tests/integration/test_v11_pipeline.py -v
rtk python -m pytest tests/unit/test_telegram_notifier.py -v
```

Manual smoke:

```bash
rtk curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d @docs/examples/sample_long_5m.json
```
