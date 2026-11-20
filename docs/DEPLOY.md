# Hướng dẫn deploy AI Morning Brief trên server khác

Repo: https://github.com/SpiritPhu/ai-morning-brief

Tài liệu này dành cho máy Linux server (Ubuntu 22.04/24.04 hoặc tương đương). Mục tiêu: chạy **dashboard Streamlit** + **worker scheduler** + **Postgres/pgvector** bằng Docker Compose.

---

## 1. Yêu cầu máy chủ

| Thành phần | Khuyến nghị |
|------------|-------------|
| OS | Ubuntu 22.04+ / Debian 12+ |
| CPU / RAM | ≥ 2 vCPU, ≥ 4 GB RAM (8 GB nếu dùng embedding lớn) |
| Disk | ≥ 20 GB trống (model embedding + Docker images) |
| Network | Outbound HTTPS tới Hugging Face, GitHub, arXiv, RSS, LLM API |
| Phần mềm | Git, Docker Engine, Docker Compose plugin |

### Cài Docker (Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
# Đăng xuất / đăng nhập lại để group docker có hiệu lực
docker --version
docker compose version
```

Mở firewall port dashboard (nếu dùng UFW):

```bash
sudo ufw allow 8501/tcp
sudo ufw status
```

---

## 2. Clone mã nguồn

```bash
cd /opt   # hoặc thư mục bạn muốn
sudo mkdir -p /opt/ai-morning-brief
sudo chown "$USER":"$USER" /opt/ai-morning-brief
cd /opt/ai-morning-brief

git clone https://github.com/SpiritPhu/ai-morning-brief.git .
# Nếu đã clone trước đó:
# git pull origin main
```

---

## 3. Cấu hình `.env`

```bash
cp .env.example .env
nano .env   # hoặc vim / vi
```

### Bắt buộc trên server Docker

```env
# Trong Docker Compose, hostname DB là "db" (tên service)
DATABASE_URL=postgresql+psycopg://brief:brief@db:5432/brief
TZ=Asia/Ho_Chi_Minh

# LLM — ví dụ Gemini (OpenAI-compatible)
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=YOUR_GEMINI_OR_OPENAI_KEY
LLM_MODEL=gemini-2.5-flash
LLM_MAX_ITEMS_PER_DAY=30

# Embedding (máy yếu dùng e5-small + dim 384; máy mạnh có thể dùng bge-m3 + 1024)
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIM=384

GITHUB_TOKEN=ghp_xxxxxxxx
REDDIT_USER_AGENT=ai-morning-brief/0.1 (by your_name)

# Lịch brief (Asia/Ho_Chi_Minh)
BRIEF_SCHEDULE_HOUR=6
BRIEF_SCHEDULE_MINUTE=0

# URL public để link trong email/Teams/Telegram
DASHBOARD_URL=http://YOUR_SERVER_IP:8501
USER_AGENT=ai-morning-brief/0.1 (+https://github.com/SpiritPhu/ai-morning-brief)
```

### Tuỳ chọn notify

```env
TEAMS_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_TO=
```

**Lưu ý bảo mật**

- Không commit file `.env` lên Git.
- Đổi mật khẩu Postgres production nếu expose port `5432` ra ngoài (mặc định compose map `5432:5432` — có thể bỏ mapping port DB nếu chỉ dùng nội bộ Docker network).
- Rotate API key / GitHub token nếu từng lộ ra ngoài.

### Đồng bộ dimension embedding với DB

`EMBEDDING_DIM` phải khớp vector column. Lần đầu deploy sạch với `384` là ổn. Nếu đổi dim sau khi DB đã có dữ liệu, cần migrate/rebuild DB (xoá volume hoặc tạo migration mới).

---

## 4. Chạy bằng Docker Compose

```bash
cd /opt/ai-morning-brief
docker compose up -d --build
```

Services:

| Service | Vai trò | Port |
|---------|---------|------|
| `db` | Postgres 16 + pgvector | 5432 (host) |
| `worker` | APScheduler: brief sáng, snapshot 18:00, catch-up | — |
| `dashboard` | Streamlit UI | **8501** |

Kiểm tra:

```bash
docker compose ps
docker compose logs -f worker
docker compose logs -f dashboard
```

Mở trình duyệt: `http://YOUR_SERVER_IP:8501`

Worker khi start sẽ chạy `alembic upgrade head` (Postgres).

---

## 5. Chạy pipeline lần đầu

Scheduler mặc định chạy ~06:00 (theo `BRIEF_SCHEDULE_*`). Để có dữ liệu ngay:

```bash
# Chạy pipeline trong container worker
docker compose exec worker python scripts/run_pipeline.py

# Hoặc bỏ qua embed nếu muốn nhanh hơn lần đầu (classify rule-based vẫn chạy)
docker compose exec worker python scripts/run_pipeline.py --skip embed

# Chỉ build lại brief / CDO section
docker compose exec worker python scripts/run_pipeline.py --only brief
```

Hoặc trên UI: **Admin → Run pipeline now**.

Backfill vài ngày (nếu cần):

```bash
docker compose exec worker python scripts/backfill.py --days 3
```

---

## 6. Cập nhật phiên bản mới từ GitHub

```bash
cd /opt/ai-morning-brief
git pull origin main
docker compose up -d --build
# Nếu có migration DB mới:
docker compose exec worker alembic upgrade head
# hoặc restart worker (worker tự upgrade khi start)
docker compose restart worker
```

Watchlist / taxonomy / sources nằm ở `./config` và được mount vào container — sửa trên server sẽ có hiệu lực sau khi pipeline chạy lại (một số trang UI đọc YAML trực tiếp).

---

## 7. Vận hành hàng ngày

| Thời điểm | Việc xảy ra |
|-----------|-------------|
| `BRIEF_SCHEDULE_HOUR:MINUTE` | Worker chạy full pipeline → Daily Brief + CDO Brief |
| 18:00 | Snapshot metrics (velocity) |
| Thứ Hai 06:30 | GitHub Trending weekly (bổ sung) |
| Dashboard | Chỉ **đọc DB** — không tự crawl |

Chọn ngày trên sidebar Home để xem brief từng ngày. Chế độ Weekly/Monthly gộp nhiều ngày.

---

## 8. Makefile tiện ích (trên host có `make`)

```bash
make up          # docker compose up -d --build
make down        # dừng
make logs        # xem log
make migrate     # alembic upgrade head (cần env local trỏ đúng DB)
make run         # python scripts/run_pipeline.py
make shell-db    # psql vào container db
```

Trên server chỉ Docker, ưu tiên `docker compose exec ...` như mục 5.

---

## 9. Phương án không Docker (SQLite lite — chỉ test)

Không khuyến nghị production, nhưng dùng được để thử nhanh:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# DATABASE_URL=sqlite:///./data/brief.db
# điền LLM_API_KEY, GITHUB_TOKEN...
python scripts/init_db.py
python scripts/run_pipeline.py --skip embed
streamlit run dashboard/Home.py --server.address 0.0.0.0 --server.port 8501
```

Scheduler riêng (nếu cần):

```bash
python -m app.scheduler
```

---

## 10. Cấu hình LLM phổ biến

### Gemini (Google AI Studio)

```env
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=YOUR_KEY
LLM_MODEL=gemini-2.5-flash
```

### OpenAI

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

### Ollama trên cùng máy / LAN

```env
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.1
```

Trên Linux, `host.docker.internal` có thể cần thêm trong `docker-compose.yml`:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

---

## 11. Troubleshooting

| Triệu chứng | Cách xử lý |
|-------------|------------|
| Dashboard trống | Chạy `docker compose exec worker python scripts/run_pipeline.py` |
| `db` unhealthy | `docker compose logs db`; đợi healthcheck; kiểm tra disk |
| Worker lỗi migrate | Xem log worker; đảm bảo `DATABASE_URL` dùng host `db` |
| GitHub 403/rate limit | Thêm `GITHUB_TOKEN` |
| Reddit 403 | Đổi `REDDIT_USER_AGENT` |
| Embedding tải lâu / OOM | Dùng `intfloat/multilingual-e5-small` + `EMBEDDING_DIM=384`; tăng RAM |
| Gemini JSON lỗi parse | App có retry + fallback; giảm `LLM_MAX_ITEMS_PER_DAY` nếu timeout |
| Không vào được :8501 | Kiểm tra `ufw`, security group cloud, `docker compose ps` |
| Đổi watchlist không thấy | Sửa `config/watchlist.yaml` rồi chạy lại `classify` + `brief` |

Sao lưu DB (Postgres):

```bash
docker compose exec -T db pg_dump -U brief brief > backup-$(date +%F).sql
```

Khôi phục:

```bash
cat backup-YYYY-MM-DD.sql | docker compose exec -T db psql -U brief brief
```

---

## 12. Checklist trước khi giao cho user cuối

- [ ] `git clone` / `git pull` thành công  
- [ ] `.env` đã điền `DATABASE_URL` (Postgres `@db`), LLM, `GITHUB_TOKEN`  
- [ ] `docker compose up -d --build` — 3 service healthy/running  
- [ ] Mở được `http://SERVER_IP:8501`  
- [ ] Pipeline chạy thành công ít nhất 1 lần  
- [ ] Home hiện TL;DR + CDO Brief  
- [ ] `DASHBOARD_URL` đúng nếu bật notify  
- [ ] Đã `git pull` khi có bản mới  

---

## Liên hệ / repo

- GitHub: https://github.com/SpiritPhu/ai-morning-brief  
- Spec nội bộ: `PROJECT_SPEC.md`  
- Watchlist: `config/watchlist.yaml`  
- Nguồn tin: `config/sources.yaml`  
