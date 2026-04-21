---
description: Chạy toàn bộ verify checklist cho sprint vừa xong
---

# Workflow: /verify-sprint
# Trigger: gõ /verify-sprint trong Agent Manager
# Mô tả: Chạy toàn bộ verify checklist cho sprint vừa xong

Xác định sprint vừa hoàn thành từ `docs/TASKS.md`, sau đó chạy lần lượt:

## Sprint 01 Verify (scaffold + domain)

```bash
python -c "from app.core.enums import SignalSide, DecisionType; print('enums OK')"
python -c "from app.core.config import settings; print('config OK')"
python -c "from app.domain.schemas import TradingViewWebhookPayload; print('schemas OK')"
python -c "from app.domain.models import Signal, WebhookEvent; print('models OK')"
psql $DATABASE_URL -c "\dt" | grep -E "signals|webhook_events|signal_filter"
```

## Sprint 02 Verify (repositories + services)

```bash
python -m pytest tests/unit/test_filter_engine.py -v
python -m pytest tests/unit/test_signal_normalizer.py -v
python -m pytest tests/unit/test_message_renderer.py -v
```

## Sprint 03 Verify (API + wiring)

```bash
uvicorn app.main:app --port 8080 &
curl http://localhost:8080/api/v1/health
curl -X POST http://localhost:8080/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d '{"secret":"test","signal_id":"smoke-001","signal":"long","symbol":"BTCUSDT","timeframe":"5m","timestamp":"2026-04-18T15:30:00Z","price":68250.5,"source":"test","confidence":0.82,"metadata":{"entry":68250.5,"stop_loss":67980.0,"take_profit":68740.0}}'
python -m pytest tests/integration/ -v
```

Báo cáo kết quả: pass/fail từng bước, đề xuất fix nếu cần.
