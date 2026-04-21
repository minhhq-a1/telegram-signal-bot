# Sprint 01 — Scaffold + Core Domain
<!-- 
  Dùng file này như conversation starter cho session đầu tiên.
  Copy prompt bên dưới vào Claude Projects sau khi đã setup Project Instructions.
  Upload kèm: CONVENTIONS.md, DATABASE_SCHEMA.md
-->

---

## Prompt để bắt đầu session

```
Tôi bắt đầu build Signal Bot V1 từ đầu (greenfield).

Hãy viết theo thứ tự sau, mỗi bước hoàn chỉnh trước khi sang bước tiếp:

1. requirements.txt
2. .env.example  
3. app/core/enums.py
4. app/core/config.py
5. app/core/database.py
6. app/core/logging.py    (structured JSON logger, không log secret)
7. app/domain/schemas.py  (TradingViewWebhookPayload + SignalMetadata + response schemas)
8. app/domain/models.py   (8 ORM models)
9. migrations/001_init.sql

Sau khi xong, tôi sẽ chạy thử và báo kết quả.
```

---

## Checklist sau Sprint 01

```bash
# Verify syntax
python -c "from app.domain.schemas import TradingViewWebhookPayload; print('OK')"
python -c "from app.domain.models import Signal; print('OK')"

# Verify migration
psql $DATABASE_URL -f migrations/001_init.sql
psql $DATABASE_URL -c "\dt"  # phải thấy 8 bảng

# Verify app start
uvicorn app.main:app --port 8080
curl http://localhost:8080/api/v1/health
```

---

## DoD Sprint 01

- [ ] `python -c "from app.domain import *"` không lỗi
- [ ] Migration chạy thành công, tạo đủ 8 bảng + 6 indexes
- [ ] `system_configs` có 1 row default config
- [ ] `.env.example` có đủ mọi biến cần thiết
