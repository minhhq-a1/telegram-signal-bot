# Skill: Webhook Handler
## Description
Implement hoặc debug `app/api/webhook_controller.py` và flow xử lý webhook end-to-end.
Trigger khi user đề cập: webhook, controller, flow, 13 bước, persist, Telegram notify.

## Instructions

### Flow bắt buộc (13 bước, đúng thứ tự)

```python
async def receive_tradingview_webhook(payload, db):

    # 1. Auth
    if not AuthService.validate_secret(payload.secret):
        raise HTTPException(status_code=401, ...)

    # 2. Idempotency
    existing = signal_repo.find_by_signal_id(payload.signal_id)
    if existing:
        return {"status": "accepted", "signal_id": ..., "decision": "DUPLICATE"}

    # 3. Store raw webhook (commit ngay, độc lập với flow chính)
    webhook_event = webhook_event_repo.create(...)
    db.commit()

    # 4. Normalize
    normalized = SignalNormalizer.normalize(payload)

    # 5. Direction sanity (trước khi insert signal)
    # Được handle bởi filter_engine Phase 2

    # 6. Store signal
    signal = signal_repo.create(normalized)

    # 7. Run filter engine
    config = config_repo.get_signal_bot_config()
    result = FilterEngine(config, signal_repo, market_event_repo).run(normalized)

    # 8. Store filter results
    filter_result_repo.bulk_insert(result.filter_results, signal.id)

    # 9. Store decision
    decision_repo.create(result, signal.id)

    # 10-11. Telegram + log (chỉ nếu PASS)
    if result.final_decision in ("PASS_MAIN", "PASS_WARNING"):
        text = MessageRenderer.render_main/warning(...)
        status, data = await TelegramNotifier().notify(result.route, text)
        telegram_repo.create(...)

    # 12. Commit (bước 6-11 trong 1 transaction)
    db.commit()

    # 13. Return
    return {"status": "accepted", "signal_id": ..., "decision": result.final_decision}
```

### Error handling

| Tình huống | Hành động |
|---|---|
| DB fail tại bước 6+ | Log error, return 500. Raw webhook đã được lưu ở bước 3 |
| Telegram fail (sau retry 3x) | Log FAILED, KHÔNG rollback DB, return 200 |
| Direction sai | Filter engine trả REJECT tại Phase 2 |

### Verify

```bash
# Test full flow với real DB
curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d @docs/examples/sample_long_5m.json

# Expected: 200 {"decision": "PASS_MAIN"}
# DB check: webhook_events(1) + signals(1) + filter_results(5+) + decisions(1) + telegram_msgs(1)
```
