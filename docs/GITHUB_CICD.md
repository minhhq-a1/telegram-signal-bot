# GitHub CI/CD — Signal Bot V1

## Mục tiêu

Thiết lập CI/CD qua GitHub Actions cho các mục tiêu sau:
- tự động chạy test khi có push hoặc pull request
- xác thực Docker image vẫn build được
- tự động publish image production lên GHCR khi merge vào `main`
- tùy chọn trigger deploy Railway qua deploy hook

---

## Workflows đã có

### 1. CI

File:
- `.github/workflows/ci.yml`

Trigger:
- `pull_request`
- `push` vào `main`
- `push` vào các nhánh `codex-*`, `feature/**`, `fix/**`, `chore/**`

Luồng chạy:
1. checkout code
2. setup Python 3.12
3. `pip install -r requirements.txt`
4. `python -m pytest -q`
5. build Docker image để bắt lỗi packaging/runtime sớm

---

### 2. CD

File:
- `.github/workflows/cd.yml`

Trigger:
- `push` vào `main`
- `workflow_dispatch`

Luồng chạy:
1. build Docker image
2. push image lên `ghcr.io/<owner>/<repo>`
3. gắn tags:
   - `latest`
   - `sha-<short_commit>` dạng metadata-generated SHA tag
4. nếu có secret `RAILWAY_DEPLOY_HOOK_URL` thì trigger Railway deploy hook

---

## GitHub Secrets / Settings cần cấu hình

### Bắt buộc cho publish image

Không cần secret riêng nếu dùng GHCR với `GITHUB_TOKEN`, nhưng repo phải cho phép workflow có quyền:
- `packages: write`

Workflow `cd.yml` đã khai báo permission này.

### Tùy chọn cho Railway deploy

Tạo GitHub Actions secret:

```text
RAILWAY_DEPLOY_HOOK_URL
```

Giá trị là Railway deploy hook URL của service.

Nếu không cấu hình secret này:
- workflow vẫn build và push image bình thường
- bước deploy Railway sẽ tự bỏ qua

---

## Cách dùng thực tế

### Với pull request

Khi mở PR:
- GitHub sẽ tự chạy `CI`
- team review sau khi test pass và Docker build pass

### Với merge vào `main`

Khi merge:
- `CD` sẽ tự build image mới
- image mới được publish lên GHCR
- nếu đã có `RAILWAY_DEPLOY_HOOK_URL`, Railway sẽ được trigger deploy

---

## Image registry output

Image sẽ được push lên:

```text
ghcr.io/<github-owner>/<repository>
```

Ví dụ với repo này:

```text
ghcr.io/minhhq-a1/telegram-signal-bot
```

---

## Khuyến nghị vận hành

- bật branch protection cho `main`
- yêu cầu `CI` phải pass trước khi merge
- nếu dùng Railway webhook deploy, nên gắn environment `production` trên GitHub để theo dõi deploy history
- chỉ merge vào `main` sau khi đã review code changes và smoke test các thay đổi có ảnh hưởng deployment
