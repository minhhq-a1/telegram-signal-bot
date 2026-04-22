# Pre-Production Sign-Off — Signal Bot V1

## Mục tiêu

Tài liệu này chốt trạng thái sẵn sàng trước khi bật TradingView alerts cho môi trường vận hành V1.

Phạm vi sign-off:
- webhook ingest
- audit trail
- filter engine
- decision persistence
- Telegram delivery

Bot vẫn là:
- **signal bot**
- **không auto-trade**

---

## Trạng thái hiện tại

### Verify snapshot

Lệnh verify gần nhất:

```bash
./.venv/bin/python -m pytest -q
```

Kết quả:
- `43 passed`

### Các remediation quan trọng đã hoàn thành

- Atomic idempotency ở DB boundary
- `signal_id` là idempotency key rõ ràng; nếu client không gửi thì server tự generate deterministic từ payload mạnh
- Runtime filter config đã thống nhất hơn, gồm `enable_news_block`
- Webhook orchestration đã tách khỏi controller sang application service
- `decision_reason` đủ cụ thể để phục vụ QA/debug/analytics
- Logging có sanitizer cho `secret`, `token`, `authorization`, `password`, `api_key`

---

## Sign-Off Criteria

### Architecture

- `audit-first` được giữ đúng cho invalid JSON, invalid schema, invalid secret
- `persist trước, notify sau` vẫn đúng
- `signal_id` là idempotency key rõ ràng, có thể do client gửi hoặc server generate
- duplicate race không còn dễ leak `500`
- controller không còn ôm toàn bộ orchestration logic

### Product

- Luồng decision vẫn bám boolean gate:
  - `FAIL` → `REJECT`
  - `WARN MEDIUM+` → `PASS_WARNING`
  - còn lại → `PASS_MAIN`
- `server_score` vẫn chỉ dùng cho analytics, không dùng để route
- phạm vi sản phẩm không drift sang auto-trading

### QA

- integration flow quan trọng đã có coverage
- regression cho duplicate, invalid schema, invalid secret, Telegram failure đều có
- audit trail có thể trace từ `webhook_events` → `signals` → `signal_filter_results` → `signal_decisions` → `telegram_messages`

---

## Open Constraints

Các điểm sau **được chấp nhận cho V1**, nhưng chưa phải kiến trúc cuối cùng:

1. Telegram delivery vẫn chạy đồng bộ trong request lifecycle.
2. Analytics vẫn query trực tiếp từ transactional tables.
3. Một số heuristics market context vẫn phụ thuộc payload-derived data.

Các điểm này **không block V1** nếu mục tiêu là production nhẹ hoặc paper-trading style rollout.

---

## Go / No-Go Decision

### GO nếu

- rollout ở tải thấp đến vừa
- team chấp nhận Telegram synchronous ở V1
- team hiểu rằng quality của một số filter vẫn phụ thuộc payload indicator context
- DB config production đã được kiểm tra trước khi bật alerts

### NO-GO nếu

- cần high-burst traffic ngay từ đầu
- cần delivery guarantee kiểu outbox/worker
- cần independent market data cho rules trước khi phát hành

---

## Pre-Launch Checklist

- [ ] `system_configs.signal_bot_config` trên DB production đã đúng
- [ ] `enable_news_block` được set đúng theo vận hành thực tế
- [ ] Telegram bot token và các chat IDs là giá trị production thật
- [ ] `TRADINGVIEW_SHARED_SECRET` là giá trị mạnh và đã đồng bộ với TradingView
- [ ] đã chạy smoke test với payload gần production nhất
- [ ] log collector/monitoring đang hoạt động
- [ ] nếu bật news block: `market_events` đã có dữ liệu cần thiết

---

## Final Verdict

### Architect

`GO` cho V1 trong phạm vi signal delivery production nhẹ.

### Product Owner

`GO` vì hành vi hệ thống đang đúng mục tiêu sản phẩm và đúng các business invariants quan trọng.

### QA

`GO` với điều kiện team hiểu rõ các open constraints của V1 và không kỳ vọng delivery architecture ở mức V2.
