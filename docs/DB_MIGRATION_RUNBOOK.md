# DB Migration Runbook

## Mục tiêu
Giữ migration theo **raw SQL versioned flow** thay vì chuyển sang Alembic trong scope hiện tại.

## Nguồn sự thật
- SQL migrations nằm trong thư mục `migrations/`
- File phải theo format: `NNN_short_description.sql`
- Runner chính thức: `python scripts/db/migrate.py apply`
- Bảng tracking: `schema_migrations`

## Quy ước
- Không sửa nội dung migration đã apply ở môi trường dùng chung
- Mọi thay đổi schema mới phải đi bằng file migration mới
- Checksum mismatch ở `schema_migrations` được coi là blocker, không bypass tay

## Luồng apply chuẩn
### Local / CI / app startup
```bash
python scripts/db/migrate.py apply
```

### Xem trạng thái migration
```bash
python scripts/db/migrate.py status
```

## Thêm migration mới
1. Tạo file mới, ví dụ: `migrations/003_add_xxx.sql`
2. Viết SQL theo hướng idempotent nếu có thể
3. Chạy local:
   ```bash
   python scripts/db/migrate.py apply
   python scripts/db/migrate.py status
   ```
4. Nếu migration ảnh hưởng release, cập nhật luôn rollback notes trong PR

## Rollback strategy hiện tại
Repo này đang dùng **forward-fix first**, rollback có kiểm soát theo 2 mức:

### Mức 1. Migration an toàn, có thể forward-fix
- Dùng khi lỗi nhỏ, không phá dữ liệu
- Tạo migration mới để sửa tiếp, không sửa file cũ đã apply

### Mức 2. Cần quay lại trạng thái trước release
- Dùng backup/restore theo `docs/BACKUP_RECOVERY_RUNBOOK.md`
- Áp dụng khi schema change hoặc data change không an toàn để vá tiếp bằng forward migration

## Baseline hiện tại
- `001_init.sql`: schema khởi tạo + seed config gốc
- `002_add_ops_migration_baseline.sql`: baseline metadata cho raw SQL versioned flow và restore-drill discipline

## Verify trước khi báo done
- `schema_migrations` có record đúng cho migration mới
- `python scripts/db/migrate.py status` không báo mismatch
- CI `test` pass
- CI `restore-drill` pass nếu đụng migration/recovery path
