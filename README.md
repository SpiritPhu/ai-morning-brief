# AI Morning Brief

Dashboard cá nhân cho **CDO / Head of AI**: mỗi sáng tự động thu thập tin AI từ HF / GitHub / arXiv / RSS / HN / Reddit, gộp trùng, phân loại, chấm điểm, tóm tắt bằng LLM (kèm **CDO Brief** tầm nhìn/xu hướng), hiển thị trên Streamlit.

Repo: https://github.com/SpiritPhu/ai-morning-brief

## Kiến trúc

```text
┌─────────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐
│ Connectors  │──▶│ Collect  │──▶│ Embed     │──▶│ Dedup    │
│ HF/GH/RSS…  │   │ upsert   │   │ embeddings│   │ stories  │
└─────────────┘   └──────────┘   └───────────┘   └────┬─────┘
                                                      │
     ┌──────────┐   ┌───────────┐   ┌──────────┐     │
     │ Notify   │◀──│ Brief     │◀──│ Summarize│◀────┤
     │ Teams/TG │   │ + CDO     │   │ LLM JSON │     │
     └──────────┘   └───────────┘   └──────────┘     │
                           ▲                          │
                     ┌─────┴──────┐   ┌──────────┐   │
                     │ Streamlit  │   │ Classify │◀──┘
                     │ Dashboard  │   │ + Score  │
                     └────────────┘   └──────────┘
```

## Deploy trên server khác (tóm tắt)

> **Hướng dẫn đầy đủ:** [`docs/DEPLOY.md`](docs/DEPLOY.md)

```bash
# 1) Cài Docker + Git trên server (Ubuntu)
# 2) Clone
git clone https://github.com/SpiritPhu/ai-morning-brief.git
cd ai-morning-brief

# 3) Cấu hình secrets
cp .env.example .env
nano .env
# Bắt buộc khi dùng Docker Compose:
#   DATABASE_URL=postgresql+psycopg://brief:brief@db:5432/brief
#   LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
#   GITHUB_TOKEN, REDDIT_USER_AGENT
#   DASHBOARD_URL=http://YOUR_SERVER_IP:8501

# 4) Chạy
docker compose up -d --build

# 5) Pipeline lần đầu (hoặc đợi job ~06:00)
docker compose exec worker python scripts/run_pipeline.py

# 6) Mở UI
# http://YOUR_SERVER_IP:8501
```

### Cập nhật bản mới

```bash
cd /path/to/ai-morning-brief
git pull origin main
docker compose up -d --build
docker compose restart worker
```

### Local không Docker (SQLite — chỉ test)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# DATABASE_URL=sqlite:///./data/brief.db + điền LLM/GitHub
python scripts/init_db.py
python scripts/run_pipeline.py --skip embed
streamlit run dashboard/Home.py
```

## Makefile

| Target | Mô tả |
|--------|--------|
| `make up` | `docker compose up -d --build` |
| `make down` | dừng services |
| `make logs` | theo dõi log |
| `make migrate` | `alembic upgrade head` |
| `make run` | chạy pipeline hôm nay |
| `make backfill` | backfill 7 ngày |
| `make test` | pytest |
| `make shell-db` | psql vào container db |

## Watchlist & cấu hình

- Ưu tiên chủ đề: `config/watchlist.yaml` (banking, insurance, cards, treasury, RAG, Agents, Big Tech…)
- Nguồn tin: `config/sources.yaml`
- Taxonomy phân loại: `config/taxonomy.yaml`
- Trọng số điểm: `config/scoring.yaml`

## Thêm connector / RSS / đổi LLM

**Connector mới:** kế thừa `BaseConnector` → đăng ký `registry.py` → thêm `sources.yaml` → test fixture.

**RSS:** thêm feed trong `config/sources.yaml` → `connectors.rss.params.feeds`.

**LLM Gemini:**

```env
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=YOUR_KEY
LLM_MODEL=gemini-2.5-flash
```

**Ollama / vLLM:** xem chi tiết trong [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Troubleshooting nhanh

| Vấn đề | Cách xử lý |
|--------|------------|
| Dashboard trống | `docker compose exec worker python scripts/run_pipeline.py` |
| GitHub rate limit | Thêm `GITHUB_TOKEN` |
| Reddit 403 | Đổi `REDDIT_USER_AGENT` |
| Embedding chậm / OOM | `EMBEDDING_MODEL=intfloat/multilingual-e5-small`, `EMBEDDING_DIM=384` |
| Không mở :8501 | Firewall / security group / `docker compose ps` |

Chi tiết hơn: [`docs/DEPLOY.md`](docs/DEPLOY.md) mục Troubleshooting.

## Dev

```bash
ruff check .
pytest -q
python scripts/test_connectors.py
```

## Checklist cấu hình

- [ ] `.env` từ `.env.example` (không commit secrets)
- [ ] Postgres URL `@db` khi Docker; SQLite chỉ khi test local
- [ ] LLM key + model
- [ ] GitHub token
- [ ] `DASHBOARD_URL` nếu dùng notify
- [ ] Pipeline chạy thành công ít nhất 1 lần
