# Backup and Recovery Runbook

## Mục tiêu
Có checklist đủ ngắn để team vận hành backup, restore, và đánh giá nhanh khả năng recovery của PostgreSQL cho repo này.

## Phạm vi
- PostgreSQL của `telegram-signal-bot`
- App restart cơ bản sau restore
- Restore drill để chứng minh backup không chỉ tồn tại trên giấy

## 1. Backup tối thiểu trước release có rủi ro schema/data
### Logical dump
```bash
pg_dump -Fc "$DATABASE_URL" -f backup-$(date +%Y%m%d-%H%M%S).dump
```

### Verify backup file có thật
```bash
ls -lh backup-*.dump
pg_restore -l backup-*.dump | head
```

## 2. Recovery checklist
### Bước A. Chặn release / ghi mới nếu cần
- Tạm dừng rollout
- Nếu có worker/background job trong tương lai, dừng ghi vào DB trước

### Bước B. Tạo DB đích hoặc DB tạm để kiểm tra
```bash
createdb signal_bot_restore_check
```

### Bước C. Restore
```bash
pg_restore -d signal_bot_restore_check backup-YYYYMMDD-HHMMSS.dump
```

### Bước D. Verify sau restore
```bash
psql "$RESTORE_DB_URL" -c "SELECT count(*) FROM schema_migrations;"
psql "$RESTORE_DB_URL" -c "SELECT config_key FROM system_configs ORDER BY config_key;"
psql "$RESTORE_DB_URL" -c "SELECT count(*) FROM webhook_events;"
```

### Bước E. App readiness sau restore
- kiểm tra `schema_migrations` đủ version kỳ vọng
- kiểm tra `signal_bot_config` và `db_ops_baseline` tồn tại
- start app bằng `start.sh`
- gọi `/api/v1/health`

## 3. Restore drill chuẩn cho repo này
Script:
```bash
bash scripts/db/restore_drill.sh
```

Script sẽ:
- tạo source DB tạm
- apply versioned migrations
- insert một record audit mẫu
- dump DB
- restore sang DB tạm thứ hai
- verify `schema_migrations`, `db_ops_baseline`, và row audit đã được khôi phục

## 4. Bằng chứng restore drill hiện tại
Trong CI, job `restore-drill` là evidence mặc định cho mỗi PR đụng migration/recovery path.

## 5. Khi nào phải escalate
- `schema_migrations` thiếu version kỳ vọng
- `pg_restore` fail
- restore xong nhưng app health fail
- restore xong nhưng seed config hoặc dữ liệu audit quan trọng không còn
