# Version History — Telegram Signal Bot

File này là nguồn duy nhất giữ lịch sử phiên bản product-level. Các context hiện hành nên nói V1.1; V1.0 được giữ ở đây để biết bot đã nâng cấp qua từng giai đoạn như thế nào.

## V1.0 — Baseline Signal Bot

Mục tiêu V1.0 là đưa bot vào trạng thái chạy được end-to-end cho paper trading / production nhẹ.

- Nhận webhook TradingView tại `POST /api/v1/webhooks/tradingview`.
- Audit-first vào `webhook_events`, kể cả invalid JSON/schema/secret.
- Idempotency bằng `signal_id`, duplicate trả `200 DUPLICATE`.
- Normalize payload và persist `signals`.
- Filter Engine boolean gate: `FAIL -> REJECT`, `WARN MEDIUM+ -> PASS_WARNING`, còn lại `PASS_MAIN`.
- `server_score` chỉ lưu analytics, không dùng route.
- Telegram routing `MAIN`, `WARN`, `ADMIN/NONE` theo decision/config.
- DB core tables: `webhook_events`, `signals`, `signal_filter_results`, `signal_decisions`, `telegram_messages`, `system_configs`, `market_events`, `signal_outcomes`.

## V1.1 — Strategy Validation, Reverify, Analytics

V1.1 giữ nguyên nguyên tắc V1.0 nhưng bổ sung rule/ops layer để debug và đánh giá signal tốt hơn.

- Thêm timeframe runtime whitelist `30m`, `1h` cùng threshold/cooldown tương ứng.
- Thêm strategy-specific validation cho `SHORT_SQUEEZE`, `SHORT_V73`, `LONG_V73`.
- Thêm quality floor WARN rules, `RR_PROFILE_MATCH`, và backend rescoring pilot (`BACKEND_SCORE_THRESHOLD` là WARN, không FAIL).
- Thêm `mom_direction`, `strategy_thresholds`, `rr_target_by_type`, `rescoring`, `score_pass_threshold` trong config/migration.
- Thêm `signal_reverify_results` và endpoint `POST /api/v1/signals/{id}/reverify`.
- Thêm `GET /api/v1/signals/{id}/reverify-results`.
- Thêm analytics/reject-stats, dashboard auth, và webhook rate limiting.
- Webhook notification flow được chuẩn hóa: commit business records trước, Telegram delivery chạy background và log `telegram_messages` bằng session riêng.

## Deferred Beyond V1.1

- Auto-trading, position sizing, position-state risk gate.
- SOFT_PASS decision type.
- User profile aggressive/conservative mode.
- Independent exchange market data source cho HTF/regime validation.
- Redis/distributed rate limiting nếu deploy nhiều instances.
