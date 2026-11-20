# AI Morning Brief

Dashboard cá nhân cho AI Head: mỗi sáng tự động thu thập tin AI từ HF / GitHub / arXiv / RSS / HN / Reddit, gộp trùng, phân loại, chấm điểm, tóm tắt bằng LLM và hiển thị trên Streamlit.

## Kiến trúc

```text
┌─────────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐
│ Connectors  │──▶│ Collect  │──▶│ Embed     │──▶│ Dedup    │
│ HF/GH/RSS…  │   │ upsert   │   │ bge-m3    │   │ stories  │
└─────────────┘   └──────────┘   └───────────┘   └────┬─────┘
                                                      │
     ┌──────────┐   ┌───────────┐   ┌──────────┐     │
     │ Notify   │◀──│ Brief     │◀──│ Summarize│◀────┤
     │ Teams/TG │   │ Daily MD  │   │ LLM JSON │     │
     └──────────┘   └───────────┘   └──────────┘     │
                           ▲                          │
                     ┌─────┴──────┐   ┌──────────┐   │
                     │ Streamlit  │   │ Classify │◀──┘
                     │ Dashboard  │   │ + Score  │
                     └────────────┘   └──────────┘
```

## Quick start (server / Docker)

```bash
git clone https://github.com/SpiritPhu/ai-morning-brief.git
cd ai-morning-brief
cp .env.example .env
# Điền LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, GITHUB_TOKEN, REDDIT_USER_AGENT

docker compose up -d --build
# worker chạy alembic khi start; dashboard: http://SERVER_IP:8501
make run              # chạy pipeline ngày hôm nay (hoặc đợi job 06:00)
```

### Local không Docker (SQLite lite)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# DATABASE_URL=sqlite:///./data/brief.db
python scripts/init_db.py
python scripts/run_pipeline.py --skip embed
streamlit run dashboard/Home.py
```

### Deploy checklist

1. Clone repo trên server  
2. Tạo `.env` từ `.env.example` (không commit secrets)  
3. `docker compose up -d --build` (Postgres+pgvector + worker + dashboard)  
4. Mở port `8501`; đặt `DASHBOARD_URL` nếu dùng notify  
5. Kiểm tra Admin → Run pipeline / chờ scheduler  

## Makefile

| Target | Mô tả |
|--------|--------|
| `make up` | `docker compose up -d --build` |
| `make down` | dừng services |
| `make migrate` | `alembic upgrade head` |
| `make run` | chạy pipeline hôm nay |
| `make backfill` | backfill 7 ngày |
| `make test` | pytest |
| `make shell-db` | psql vào container db |

## Thêm connector mới

1. Tạo class kế thừa `BaseConnector` trong `app/connectors/`.
2. Đăng ký trong `app/connectors/registry.py`.
3. Thêm entry vào `config/sources.yaml` (enabled, type, weight, params).
4. Viết unit test parse với fixture trong `tests/fixtures/`.

## Thêm RSS feed

Sửa `config/sources.yaml` → `connectors.rss.params.feeds`:

```yaml
- name: My Blog
  url: https://example.com/feed.xml
  organization: example
  is_big_tech: false
  weight: 0.8
  verify: true
```

## Đổi LLM sang Ollama / vLLM

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.1
```

Hoặc vLLM:

```env
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=dummy
LLM_MODEL=your-model
```

Nếu `LLM_API_KEY` trống và base_url không phải localhost → chế độ **no-LLM** (fallback tóm tắt cắt description).

## Troubleshooting

| Vấn đề | Cách xử lý |
|--------|------------|
| GitHub rate limit | Thêm `GITHUB_TOKEN` vào `.env` |
| Reddit 403 | Đổi `REDDIT_USER_AGENT` rõ ràng, tránh spam |
| Embedding tải chậm | Lần đầu tải `BAAI/bge-m3`; máy yếu đặt `EMBEDDING_MODEL=intfloat/multilingual-e5-small` và `EMBEDDING_DIM=384` (cần migration lại vector dim) |
| RSS lỗi | Kiểm tra URL đánh dấu `verify: true` trong `sources.yaml` |
| Pipeline partial | Xem Admin → pipeline history / `step_status` |

## Checklist tự cấu hình

- [ ] Copy `.env.example` → `.env` và điền secrets
- [ ] Kiểm tra các RSS URL (`verify: true`)
- [ ] Tạo GitHub Personal Access Token (public_repo / read)
- [ ] (Tuỳ chọn) Teams Incoming Webhook / Telegram bot / SMTP
- [ ] (Tuỳ chọn) Đặt `DASHBOARD_URL` cho link trong notify

## Dev

```bash
ruff check .
pytest -q
python scripts/test_connectors.py
python scripts/test_connectors.py --only hf_papers
```
