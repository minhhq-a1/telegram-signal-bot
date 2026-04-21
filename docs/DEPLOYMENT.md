# Deployment Guide — Signal Bot V1

---

## 1. Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Docker + Docker Compose (recommended)
- Domain với HTTPS (bắt buộc cho webhook)
- Telegram Bot Token (từ @BotFather)
- TradingView account có indicator Bot Webhook v8.4 [BTC]

---

## 2. Environment Variables

Copy `.env.example` → `.env` và điền đầy đủ:

```env
# App
APP_ENV=production
APP_PORT=8080
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/signal_bot

# Security
TRADINGVIEW_SHARED_SECRET=<mật-khẩu-mạnh-ngẫu-nhiên-tối-thiểu-32-chars>

# Symbols & Timeframes (phân cách bởi dấu phẩy)
ALLOWED_SYMBOLS=BTCUSDT,BTCUSD
ALLOWED_TIMEFRAMES=1m,3m,5m,12m,15m

# Telegram
TELEGRAM_BOT_TOKEN=<token-từ-BotFather>
TELEGRAM_MAIN_CHAT_ID=<chat_id-kênh-chính>
TELEGRAM_WARN_CHAT_ID=<chat_id-kênh-warning>
TELEGRAM_ADMIN_CHAT_ID=<chat_id-kênh-admin>

# Feature flags
ENABLE_NEWS_BLOCK=true
ENABLE_HTF_FILTER=false
LOG_REJECT_TO_ADMIN=true
```

### Cách lấy Telegram Chat ID

```bash
# 1. Add bot vào group/channel
# 2. Gửi 1 message bất kỳ
# 3. Gọi API:
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
# Chat ID nằm trong response: "chat": {"id": -100xxxxxxxxx}
```

### Generate shared secret mạnh

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 3. Local Development

### 3.1 Cài Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.2 Khởi động DB

```bash
docker-compose up -d db
```

### 3.3 Chạy migration

```bash
psql $DATABASE_URL -f migrations/001_init.sql
```

### 3.4 Chạy app

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

### 3.5 Verify

```bash
curl http://localhost:8080/api/v1/health
# Expected: {"status":"ok","service":"telegram-signal-bot","version":"1.0.0"}
```

---

## 4. Docker Deployment

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  app:
    build: .
    ports:
      - "8080:8080"
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: signal_bot
      POSTGRES_USER: ${POSTGRES_USER:-signal_bot}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./migrations/001_init.sql:/docker-entrypoint-initdb.d/001_init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U signal_bot"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  pgdata:
```

### Chạy với Docker Compose

```bash
docker-compose up -d
docker-compose logs -f app
```

---

## 5. Nginx Reverse Proxy (HTTPS)

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

---

## 6. TradingView Alert Setup

### Bước 1: Cập nhật Pine Script

Trong indicator Bot Webhook v8.4, vào Inputs → Webhook/Payload:
- **Webhook Secret:** điền cùng giá trị với `TRADINGVIEW_SHARED_SECRET`
- **Execution Symbol:** `BTCUSDT`
- **Market Type:** `perp`

### Bước 2: Tạo alert

Cho mỗi timeframe muốn chạy, tạo 1 alert riêng:

1. Click "Create Alert" trên chart
2. Condition: `Bot Webhook v8.4 [BTC]` → `alert() function calls`
3. Webhook URL: `https://your-domain.com/api/v1/webhooks/tradingview`
4. Message: để trống (Pine Script tự build JSON trong `alert()`)
5. Expiration: No expiration
6. Alert name: `BTC Signal Bot - 5m` (đặt tên rõ ràng)

### Bước 3: Timeframe được khuyến nghị khởi động

```
Tuần 1–2: Bật 3m, 5m, 15m
Tuần 3+:  Cân nhắc thêm 1m, 12m
```

> **Không bật 30S, 45S** — sẽ bị reject server với `UNSUPPORTED_TIMEFRAME`

---

## 7. Kiểm tra sau khi deploy

### Test webhook với Postman / curl

```bash
curl -X POST https://your-domain.com/api/v1/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "YOUR_SECRET",
    "signal_id": "test-001",
    "signal": "long",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "timestamp": "2026-04-18T15:30:00Z",
    "price": 68250.5,
    "source": "test",
    "confidence": 0.82,
    "metadata": {
      "entry": 68250.5,
      "stop_loss": 67980.0,
      "take_profit": 68740.0,
      "regime": "WEAK_TREND_DOWN",
      "vol_regime": "TRENDING_LOW_VOL"
    }
  }'
```

**Expected response:**
```json
{"status":"accepted","signal_id":"test-001","decision":"PASS_MAIN"}
```

### Test secret sai

```bash
# Thay secret bằng giá trị sai
# Expected: 401 {"status":"rejected","error_code":"INVALID_SECRET",...}
```

### Test TF bị reject

```bash
# Thay timeframe thành "30S"
# Expected: 400 {"error_code":"UNSUPPORTED_TIMEFRAME",...}
```

---

## 8. Go-Live Checklist

> **Xem thêm:** `docs/QA_STRATEGY.md` — Acceptance Criteria AC-001 đến AC-006 phải pass trước khi bật TradingView alert.


### Security
- [ ] `TRADINGVIEW_SHARED_SECRET` đã thay giá trị mạnh (≥32 chars)
- [ ] Secret không có trong git history
- [ ] HTTPS đang hoạt động (không HTTP)
- [ ] Admin endpoints chỉ truy cập nội bộ

### TradingView
- [ ] Indicator đã điền đúng `secret` và `symbol`
- [ ] Alert đã tạo cho các TF whitelist
- [ ] Test alert gửi thành công và bot nhận được
- [ ] **Không** bật alert cho 30S, 45S, 4m

### Telegram
- [ ] Bot token lưu an toàn trong `.env`
- [ ] Main channel nhận được message test
- [ ] Admin channel nhận được reject log test
- [ ] Format message hiển thị đẹp trên mobile

### Database
- [ ] Migration đã chạy thành công
- [ ] `system_configs` có default config
- [ ] Backup DB đang hoạt động (tối thiểu daily)
- [ ] Có thể trace: raw webhook → signal → decision → telegram

### App
- [ ] Health endpoint trả `200 ok`
- [ ] Logs có structured format (JSON)
- [ ] Error logs gửi admin Telegram
- [ ] Service restart tự động (`restart: unless-stopped`)

### Hiểu biết
- [ ] Owner hiểu bot chỉ là **signal assistant**
- [ ] Owner hiểu `expected_wr` là heuristic, không phải xác suất thực
- [ ] **Chưa** bật auto trade
- [ ] Lên kế hoạch chạy paper 2–4 tuần trước live

---

## 9. Monitoring & Logs

### Structured log format

```json
{
  "level": "INFO",
  "event": "signal_processed",
  "signal_id": "tv-btcusdt-5m-...",
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "side": "LONG",
  "decision": "PASS_MAIN",
  "server_score": 0.84,
  "timestamp": "2026-04-18T15:30:02Z"
}
```

### Xem logs Docker

```bash
docker-compose logs -f app
docker-compose logs -f app | grep "PASS_MAIN"
docker-compose logs -f app | grep "ERROR"
```

### Alerts quan trọng cần theo dõi

| Tình huống | Hành động |
|---|---|
| Telegram send liên tục fail | Kiểm tra bot token, chat ID |
| DB connection fail | Kiểm tra PostgreSQL container |
| Quá nhiều REJECT vì `UNSUPPORTED_TIMEFRAME` | Kiểm tra TradingView alert config |
| Không nhận được signal sau 1 ngày | Kiểm tra TradingView alert còn hoạt động |

---

## 10. Pilot Evaluation (2–4 tuần)

Sau khi deploy, track các metrics sau trước khi dùng live:

```sql
-- Số signal per TF per ngày
SELECT timeframe, DATE(created_at), COUNT(*) as total,
       COUNT(*) FILTER (WHERE id IN (SELECT signal_row_id FROM signal_decisions WHERE decision = 'PASS_MAIN')) as pass_main
FROM signals
GROUP BY timeframe, DATE(created_at)
ORDER BY 2 DESC, 1;

-- Pass rate theo TF
SELECT s.timeframe,
       COUNT(*) as total,
       COUNT(*) FILTER (WHERE d.decision = 'PASS_MAIN') as pass_main,
       COUNT(*) FILTER (WHERE d.decision = 'PASS_WARNING') as pass_warn,
       COUNT(*) FILTER (WHERE d.decision = 'REJECT') as rejected
FROM signals s
JOIN signal_decisions d ON d.signal_row_id = s.id
GROUP BY s.timeframe;

-- Top reject reasons
SELECT decision_reason, COUNT(*) as count
FROM signal_decisions
WHERE decision = 'REJECT'
GROUP BY decision_reason
ORDER BY count DESC
LIMIT 20;
```
