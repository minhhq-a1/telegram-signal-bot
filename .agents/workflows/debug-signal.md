---
description: Trace toàn bộ audit trail của 1 signal để tìm lý do reject hoặc routing sai
---

# Workflow: /debug-signal
# Trigger: gõ /debug-signal [signal_id] trong Agent Manager
# Mô tả: Trace toàn bộ audit trail của 1 signal để tìm lý do reject hoặc routing sai

Chạy query sau trong PostgreSQL để trace signal $INPUT:

```sql
-- 1. Raw webhook
SELECT id, received_at, auth_status, is_valid_json, error_message
FROM webhook_events
WHERE id = (SELECT webhook_event_id FROM signals WHERE signal_id = '$INPUT');

-- 2. Normalized signal
SELECT signal_id, side, symbol, timeframe, entry_price, stop_loss, take_profit,
       risk_reward, indicator_confidence, server_score,
       signal_type, regime, vol_regime, created_at
FROM signals WHERE signal_id = '$INPUT';

-- 3. Từng rule đã chạy
SELECT rule_code, rule_group, result, severity, score_delta, details
FROM signal_filter_results
WHERE signal_row_id = (SELECT id FROM signals WHERE signal_id = '$INPUT')
ORDER BY created_at;

-- 4. Decision
SELECT decision, decision_reason, telegram_route
FROM signal_decisions
WHERE signal_row_id = (SELECT id FROM signals WHERE signal_id = '$INPUT');

-- 5. Telegram delivery
SELECT channel_type, delivery_status, error_message, sent_at
FROM telegram_messages
WHERE signal_row_id = (SELECT id FROM signals WHERE signal_id = '$INPUT');
```

Sau khi lấy kết quả, phân tích:
- Rule nào FAIL và tại sao?
- server_score bao nhiêu? (analytics only, không phải lý do route)
- Decision có đúng với boolean gate logic không?
- Nếu Telegram fail, lỗi gì?

Đề xuất fix nếu có vấn đề.
