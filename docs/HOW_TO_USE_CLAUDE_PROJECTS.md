# Cách dùng Claude.ai Projects cho dự án này

## 1. Setup Project (làm 1 lần)

### Tạo Project

1. Vào claude.ai → **Projects** → **New Project**
2. Đặt tên: `Signal Bot V1`

### Paste Project Instructions

1. Mở file `docs/PROJECT_INSTRUCTIONS.md`
2. Copy toàn bộ nội dung
3. Paste vào ô **"Project Instructions"** trong Project settings

> Project Instructions được inject vào đầu mỗi conversation trong project — đây là "system prompt" cố định.

### Upload files vào Project Knowledge

Upload các file sau vào **Project Files** (không phải conversation):

```
docs/FILTER_RULES.md        ← Claude đọc khi implement filter_engine
docs/PAYLOAD_CONTRACT.md    ← Claude đọc khi viết schemas
docs/DATABASE_SCHEMA.md     ← Claude đọc khi viết models + migration
docs/CONVENTIONS.md         ← Claude đọc khi viết bất kỳ code nào
docs/TEST_CASES.md          ← Claude đọc khi viết tests
docs/QA_STRATEGY.md         ← Claude đọc khi viết integration/QA tests
docs/PROMPTS.md             ← Prompt library theo lifecycle (tham khảo)
docs/TASKS.md               ← Claude đọc để biết thứ tự làm
```

> Files trong Project Knowledge được Claude truy cập trong mọi conversation thuộc project đó.

---

## 2. Workflow mỗi sprint

### Mỗi sprint = 1 conversation mới

Không dùng 1 conversation dài cho cả dự án. Context window sẽ đầy và Claude "quên" code đầu file.

**Quy tắc:** 1 sprint = 1 conversation = ~1 nhóm file liên quan.

### Bắt đầu sprint

1. Tạo conversation mới trong Project
2. Copy prompt từ file `SPRINT_0X.md` tương ứng
3. Paste vào conversation và gửi
4. Claude bắt đầu viết code từng file theo thứ tự

### Trong conversation

```
Bạn: [prompt từ SPRINT file]
Claude: [viết file 1]
Bạn: ok, tiếp tục
Claude: [viết file 2]
...
Bạn: [paste error nếu có]
Claude: [fix trực tiếp]
```

### Khi gặp lỗi

```
Bạn: Gặp lỗi này khi chạy app/services/filter_engine.py:
     [paste stack trace]
     
Claude: [fix trực tiếp, không rewrite từ đầu]
```

### Khi cần detail hơn về 1 topic

```
Bạn: Tôi cần implement cooldown logic. 
     Đọc FILTER_RULES.md section 4.9 và viết method check_cooldown()

Claude: [đọc file đã upload, implement đúng spec]
```

---

## 3. Thứ tự conversations đề xuất

| Conversation | Sprint file | Files được tạo | Thời gian ước tính |
|---|---|---|---|
| Conv 1 | `SPRINT_01.md` | requirements, enums, config, database, schemas, models, migration | 1–2h |
| Conv 2 | `SPRINT_02.md` | 7 repositories + 5 services | 2–3h |
| Conv 3 | `SPRINT_03.md` | 3 API controllers + main.py + tests | 2–3h |
| Conv 4+ | ad-hoc | Fix bugs, thêm feature | theo nhu cầu |

---

## 4. Tips khi làm việc với Claude Projects

### Nói Claude viết code hoàn chỉnh
```
# ❌ Dễ ra code không dùng được
"Implement filter engine"

# ✅ Ra code hoàn chỉnh
"Viết toàn bộ file app/services/filter_engine.py 
 theo đúng FILTER_RULES.md đang có trong Project Knowledge"
```

### Khi sửa code, không reprint toàn bộ
```
# ❌ Lãng phí context
"Viết lại toàn bộ filter_engine.py với fix này"

# ✅ Tiết kiệm context
"Fix method _has_hard_fail() trong filter_engine.py — 
 cần check cả severity HIGH, không chỉ CRITICAL"
```

### Khi context dài, bắt đầu conversation mới
```
# Dấu hiệu cần conversation mới:
- Claude bắt đầu "quên" conventions đã thống nhất
- Response chậm hơn
- Claude hỏi lại những gì đã nói trước đó

# Cách start lại không mất context:
"Tiếp tục từ Sprint 02. 
 Đã xong: repositories (1-7), auth_service, signal_normalizer.
 Cần làm tiếp: filter_engine.py
 Vấn đề hiện tại: [mô tả]"
```

### Khi cần validate business logic
```
"Theo FILTER_RULES.md, COOLDOWN_ACTIVE có nên reject cứng 
 hay chỉ giảm score? Tôi thấy code đang reject cứng."

→ Claude check lại docs và confirm/correct
```

---

## 5. Quản lý code output

Claude viết code vào conversation. Bạn cần copy vào file thủ công (Claude Projects không tự tạo file).

**Gợi ý workflow:**
```bash
# Mở terminal và editor song song
# Claude viết 1 file → bạn copy → paste vào đúng path → chạy test → báo kết quả

# Sau mỗi file hoạt động:
git add app/services/filter_engine.py
git commit -m "feat: implement filter engine phase 1-4"
```

**Không** accumulate nhiều file chưa test. Copy và verify từng file.

---

## 6. Khi dự án mở rộng sang V2

Tạo **Project mới** cho V2, không dùng lại Project V1.

Update `PROJECT_INSTRUCTIONS.md` với:
- Scope mới (auto outcome tracking, HTF market data...)
- Thay đổi tech stack nếu có (Redis, Celery...)
- Link reference đến V1 codebase

---

## Quick Reference

```
Project Instructions  ← PROJECT_INSTRUCTIONS.md (paste 1 lần, cố định)
Project Knowledge     ← 6 docs files (Claude tự đọc khi cần)
Conversation 1        ← SPRINT_01.md prompt
Conversation 2        ← SPRINT_02.md prompt  
Conversation 3        ← SPRINT_03.md prompt
Ad-hoc conversations  ← bug fix, feature request, câu hỏi cụ thể
```
