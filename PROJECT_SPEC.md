# PROJECT_SPEC — ai-morning-brief

Dashboard cá nhân cho AI Head: mỗi sáng tự động thu thập tin/công nghệ AI từ nhiều nguồn, gộp trùng, phân loại, chấm điểm, tóm tắt bằng LLM và hiển thị trên Streamlit.

## Mục tiêu

- Mỗi sáng **07:00 (Asia/Ho_Chi_Minh)** có Daily Brief: TL;DR 5 ý, Top 10 stories, Rising Now, Big Tech Releases, My Watchlist, Topic Heatmap, PoC Candidates.
- Đọc trong **10–15 phút**. Mọi item đều có link nguồn gốc.
- Ngôn ngữ hiển thị tóm tắt: **tiếng Việt**. Giữ nguyên thuật ngữ kỹ thuật tiếng Anh.

## Tech stack (bắt buộc)

| Thành phần | Chi tiết |
|---|---|
| Python | 3.11, dependency qua `requirements.txt` |
| DB | PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`) |
| ORM | SQLAlchemy 2.x (typed, `Mapped[]`) + Alembic |
| HTTP / parse | `httpx` (sync), `feedparser`, `beautifulsoup4`, `tenacity` (retry), pydantic v2, pydantic-settings |
| Embeddings | `sentence-transformers`, mặc định `BAAI/bge-m3` (cấu hình được; fallback `intfloat/multilingual-e5-small` cho máy yếu) |
| LLM | OpenAI-compatible client (`openai`), `base_url` / `api_key` / `model` qua `.env` (OpenAI, Azure OpenAI, vLLM, Ollama) |
| Scheduler | APScheduler |
| UI | Streamlit + plotly |
| Logging | loguru |
| Deploy | Docker Compose: `db`, `worker`, `dashboard` |
| Test | pytest |

## Cấu trúc thư mục

```text
ai-morning-brief/
├── app/
│   ├── config.py            # pydantic-settings, đọc .env + config/*.yaml
│   ├── db/
│   │   ├── base.py, session.py
│   │   ├── models.py        # ORM
│   │   └── repository.py    # hàm CRUD/upsert
│   ├── connectors/
│   │   ├── base.py          # BaseConnector + NormalizedItem
│   │   ├── hf_papers.py, hf_models.py, hf_spaces.py
│   │   ├── github_trending.py, github_search.py
│   │   ├── arxiv.py, rss.py, hackernews.py, reddit.py
│   │   └── registry.py
│   ├── pipeline/
│   │   ├── collect.py, dedup.py, classify.py, score.py
│   │   ├── summarize.py, brief.py, notify.py
│   │   └── runner.py        # chạy toàn bộ pipeline, ghi pipeline_runs
│   ├── llm/
│   │   ├── client.py
│   │   └── prompts.py
│   ├── embeddings.py
│   └── scheduler.py
├── dashboard/
│   ├── Home.py              # Daily Brief
│   ├── pages/1_Explorer.py
│   ├── pages/2_Trends.py
│   ├── pages/3_Watchlist.py
│   ├── pages/4_Weekly_Review.py
│   ├── pages/5_Admin.py
│   └── components/          # card, charts, filters
├── config/
│   ├── sources.yaml         # bật/tắt connector, tham số, RSS feeds
│   ├── taxonomy.yaml        # danh sách nhãn đóng
│   ├── watchlist.yaml       # chủ đề quan tâm + keywords
│   └── scoring.yaml         # trọng số
├── alembic/
├── scripts/
│   ├── run_pipeline.py      # chạy tay: --date, --only collect|dedup|...
│   ├── backfill.py          # chạy cho N ngày quá khứ (nguồn nào hỗ trợ)
│   └── seed.py
├── tests/
├── docker-compose.yml, Dockerfile, .env.example, Makefile, README.md
└── PROJECT_SPEC.md
```

## Nguyên tắc

1. **Isolation:** Mỗi connector độc lập — một nguồn lỗi **không** làm hỏng pipeline (try/except, log, ghi status).
2. **Idempotent:** Chạy lại cùng ngày không tạo bản ghi trùng (upsert theo `(source, external_id)`).
3. **Metric snapshots:** Lưu snapshot metric theo ngày (stars, upvotes, downloads, likes, points) để tính velocity.
4. **Rate-limit + retry:** Exponential backoff (tenacity), timeout 20s, User-Agent rõ ràng.
5. **No hardcoded secrets:** Mọi cấu hình qua `.env` và `config/*.yaml`.
6. **LLM cost control:** Chỉ tóm tắt top N items (mặc định 50/ngày); cache theo `content_hash`.
7. **LLM output:** Phải là JSON, validate bằng pydantic; lỗi parse → retry 1 lần rồi fallback.
8. **Code style:** Type hints đầy đủ, docstring ngắn, không over-engineering.

---

## Bước 1 — Scaffold, config, DB schema, Docker

### Docker Compose

- **db:** `pgvector/pgvector:pg16`, volume `pgdata`, healthcheck `pg_isready`, port 5432
- **worker:** build `.`, command `python -m app.scheduler`, depends_on db healthy, mount `./config`, volume `hf_cache` cho model embedding
- **dashboard:** build `.`, command `streamlit run dashboard/Home.py --server.port 8501 --server.address 0.0.0.0`, port 8501
- Worker và dashboard dùng chung `env_file: .env`

### `.env.example`

```env
DATABASE_URL=postgresql+psycopg://brief:brief@db:5432/brief
TZ=Asia/Ho_Chi_Minh
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
LLM_MAX_ITEMS_PER_DAY=50
EMBEDDING_MODEL=BAAI/bge-m3
GITHUB_TOKEN=
HF_TOKEN=
REDDIT_USER_AGENT=ai-morning-brief/0.1 (by your_name)
BRIEF_SCHEDULE_HOUR=6
BRIEF_SCHEDULE_MINUTE=0
TEAMS_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_TO=
DASHBOARD_URL=
```

### `app/config.py`

- Class `Settings` (pydantic-settings)
- Hàm `load_yaml(name)` đọc `config/*.yaml`, cache bằng `lru_cache`

### DB models (`app/db/models.py`)

#### `sources`
- `id`, `key` (unique, vd `hf_papers`), `name`, `type` (`paper|model|space|repo|blog|community`), `weight` float, `enabled` bool

#### `items`
- `id`, `source_key`, `external_id`, `item_type`, `title`, `url`, `canonical_url`, `description` text, `content` text nullable
- `authors` jsonb, `organization` nullable, `published_at` timestamptz, `first_seen_at`, `last_seen_at`
- `extra` jsonb (tags, language, license, arxiv_id, github_repo, hf_model_id…)
- `content_hash`, `embedding` vector(1024) nullable (dimension từ config)
- `story_id` FK nullable
- **UNIQUE** `(source_key, external_id)`

#### `item_metrics`
- `id`, `item_id` FK, `snapshot_date` date
- `metric_name` (`stars|stars_today|forks|upvotes|likes|downloads|points|comments|trending_rank`)
- `value` float
- **UNIQUE** `(item_id, snapshot_date, metric_name)`

#### `stories`
- `id`, `story_date`, `title`, `canonical_url`, `primary_item_id`, `source_count` int, `item_count` int
- `topics` text[], `importance_score` float, `score_breakdown` jsonb, `is_big_tech` bool, `organization` nullable
- `watchlist_matches` text[], `created_at`, `updated_at`

#### `story_summaries`
- `id`, `story_id` FK unique, `title_vi`, `summary`, `why_it_matters`
- `maturity` (`research|early-oss|production-ready`)
- `action` (`ignore|read|try-poc|share-team`)
- `categories` text[], `related_watchlist` text[], `llm_model`, `content_hash`, `created_at`

#### `daily_briefs`
- `id`, `brief_date` unique, `tldr` jsonb (list), `top_story_ids` int[], `rising` jsonb, `big_tech` jsonb
- `poc_candidates` jsonb, `stats` jsonb, `markdown` text, `created_at`

#### `feedback`
- `id`, `story_id` FK, `vote` int (+1/−1), `note` text nullable, `created_at`

#### `pipeline_runs`
- `id`, `run_date`, `started_at`, `finished_at`, `status` (`running|success|partial|failed`), `step_status` jsonb, `error` text nullable

### Indexes

- `items(published_at)`, `items(story_id)`
- `item_metrics(item_id, snapshot_date)`
- `stories(story_date, importance_score DESC)`
- HNSW trên `items.embedding` (`vector_cosine_ops`)

### Alembic

- Init + migration đầu: `CREATE EXTENSION IF NOT EXISTS vector`
- Worker khi start: `alembic upgrade head`

### Repository (`app/db/repository.py`)

- `upsert_item` (ON CONFLICT → update `last_seen_at`, `description`, `extra`)
- `upsert_metric`, `get_items_by_date`, `get_stories_by_date`, `save_brief`, `add_feedback`

### Config YAML khởi tạo

#### `taxonomy.yaml` — nhóm và nhãn

Mỗi nhãn có: `id`, `name`, `description`, `keywords` (rule-based fallback).

| Nhóm | Nhãn |
|---|---|
| Models | LLM, Multimodal/VLM, Speech/ASR/TTS, Vision, Embedding, Small/On-device |
| Agents | Agent framework, Coding agent, MCP/Tool use, Multi-agent, Agent memory |
| Techniques | Fine-tuning/RLHF, Reasoning, RAG/Retrieval, Long context, Quantization/Distillation |
| Infra | Inference/Serving, Training infra, LLMOps/Observability, Evaluation/Benchmark |
| Risk | AI Security, Safety/Governance, License |
| Applied | Cybersecurity, Document AI/OCR, Customer support, Finance, Healthcare |

#### `watchlist.yaml`

Mỗi mục: `name`, `description`, `keywords`, `priority` (1–3).

| Name | Keywords |
|---|---|
| SOC AI | SOC, SIEM, alert triage, incident, threat detection, Sentinel, Defender |
| ASR/Speech | ASR, speech recognition, Zipformer, Whisper, sherpa-onnx, TTS, Vietnamese speech |
| Document AI/OCR | OCR, document understanding, VLM OCR, layout |
| Ticket classification | ticket, ITSM, helpdesk, text classification |
| RAG | RAG, retrieval, reranker, embedding |
| Agents | agent, MCP, tool calling, multi-agent |

#### `scoring.yaml`

```yaml
weights:
  velocity: 0.30
  cross_source: 0.25
  source_weight: 0.20
  relevance: 0.15
  freshness: 0.10
freshness_half_life_hours: 36
top_n: 10
dedup_similarity_threshold: 0.88
```

### Makefile

Targets: `up`, `down`, `logs`, `migrate`, `run`, `backfill`, `test`, `shell-db`

### Verify (bước 1)

`docker compose up -d db && make migrate`; `tests/test_models.py` kiểm tra tạo bảng trên DB test.

---

## Bước 2 — Connectors

### `app/connectors/base.py`

- Pydantic `NormalizedItem`: `source_key`, `external_id`, `item_type`, `title`, `url`, `description`, `authors`, `organization`, `published_at` (datetime tz-aware UTC), `metrics: dict[str, float]`, `extra: dict`
- `BaseConnector(ABC)`: `key`, `item_type`, `__init__(settings, source_cfg)`, `fetch(target_date: date) -> list[NormalizedItem]`
- HTTP client chung: `httpx.Client(timeout=20, headers User-Agent)`, retry tenacity (3 lần, exponential, chỉ retry 429/5xx/timeout), tôn trọng `Retry-After`
- Helper `canonicalize_url` (bỏ `utm_*`, trailing slash; chuẩn hóa arxiv abs/pdf → abs; github → `github.com/owner/repo`)

### Connectors (1 class / file, đăng ký `registry.py`, bật/tắt + tham số trong `config/sources.yaml`)

#### `hf_papers.py`
- `GET https://huggingface.co/api/daily_papers?date=YYYY-MM-DD` (thử thêm `limit` nếu hỗ trợ)
- `external_id` = paper id (arXiv id)
- metrics: `upvotes`, `comments` nếu có
- extra: `arxiv_id`, github repo nếu có, authors

#### `hf_models.py`
- `GET https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=50&full=false`
- metrics: `likes`, `downloads`, `trending_rank` (thứ tự trả về)
- extra: `pipeline_tag`, `library_name`, `tags`, `license` (từ tags `license:*`)
- `organization` = phần trước `/` của id

#### `hf_spaces.py`
- Tương tự `/api/spaces?sort=trendingScore`

#### `github_trending.py`
- Scrape `https://github.com/trending?since={daily|weekly|monthly}` (config; mặc định daily; có thể chạy thêm weekly vào thứ Hai)
- Parse `article.Box-row`: repo `full_name`, description, language, tổng stars, forks, “stars today/this week”
- metrics: `stars`, `forks`, `stars_today`, `trending_rank`
- Lọc AI bằng keywords taxonomy + danh sách chung (`llm`, `gpt`, `agent`, `diffusion`, `transformer`, `rag`, `embedding`, `model`, `inference`, `speech`, `vision`, `ai`, `ml`) trên name+description; giữ cờ `is_ai` trong extra
- HTML đổi cấu trúc → log warning, trả list rỗng, **không crash**

#### `github_search.py`
- GitHub Search API `/search/repositories` với queries trong config, ví dụ:
  - `topic:llm created:>{d-7}`
  - `topic:ai-agents created:>{d-7}`
  - `topic:rag pushed:>{d-1} stars:>200`
- `sort=stars`; dùng `GITHUB_TOKEN` nếu có; `per_page=30`
- metrics: `stars`, `forks`, `open_issues`
- extra: `topics`, `license`, `created_at`, `pushed_at`

#### `arxiv.py`
- `http://export.arxiv.org/api/query`
- `search_query` theo categories `cs.AI`, `cs.CL`, `cs.LG`, `cs.CV`, `cs.CR` (config)
- `sortBy=submittedDate`, `max_results=200`, parse bằng feedparser
- Chỉ lấy bài submit trong **36 giờ** gần nhất so với `target_date`
- Chờ **3 giây** giữa các request (khuyến nghị arXiv)

#### `rss.py`
- Feeds trong `config/sources.yaml`. Mỗi feed: `name`, `url`, `organization`, `is_big_tech`, `weight`
- Feeds khởi tạo (đánh dấu `verify: true` để kiểm tra URL sau):
  - Hugging Face Blog — `https://huggingface.co/blog/feed.xml`
  - OpenAI News — `https://openai.com/news/rss.xml`
  - Google DeepMind — `https://deepmind.google/blog/rss.xml`
  - Google Research — `https://research.google/blog/rss/`
  - Microsoft Research — `https://www.microsoft.com/en-us/research/feed/`
  - NVIDIA Technical Blog — `https://developer.nvidia.com/blog/feed`
  - AWS Machine Learning Blog — `https://aws.amazon.com/blogs/machine-learning/feed/`
  - Meta AI và Anthropic: entry với `url` rỗng + comment “chưa có RSS chính thức, bổ sung sau”
- Feed lỗi hoặc url rỗng → skip + log
- Chỉ lấy entry published trong **48 giờ**

#### `hackernews.py`
- Algolia: `https://hn.algolia.com/api/v1/search_by_date?tags=story&query={kw}&numericFilters=created_at_i>{ts},points>{min_points}`
- Keywords config: LLM, GPT, AI agent, open-source model, Hugging Face, RAG, diffusion, Claude, Gemini, Llama, Qwen, DeepSeek
- Dedup theo `objectID`
- metrics: `points`, `comments`
- `url` = URL bài gốc nếu có; `extra.hn_url` = link thread

#### `reddit.py`
- `https://www.reddit.com/r/{sub}/top.json?t=day&limit=25`
- Subs mặc định: `[MachineLearning, LocalLLaMA]` (config)
- Header User-Agent từ env
- metrics: `upvotes` (score), `comments`
- Bỏ qua post stickied
- Lỗi 403/429 → log và skip

### Scripts & tests (bước 2)

- `scripts/test_connectors.py`: chạy từng connector cho hôm nay, in số item + 3 item đầu (title, url, metrics), **không ghi DB**; cờ `--only <key>`
- Unit test parse từng connector bằng fixture JSON/HTML/XML trong `tests/fixtures` (không gọi network); test `canonicalize_url`

### Verify (bước 2)

`python scripts/test_connectors.py` chạy được; connector lỗi network vẫn in lỗi gọn và tiếp tục.

---

## Bước 3 — Pipeline: collect, dedup/story, classify, score

### `pipeline/collect.py`

- `collect(target_date)`: chạy tất cả connector enabled → upsert items → upsert `item_metrics` với `snapshot_date = target_date`
- Trả về `{source_key: count | "error: ..."}`

### `app/embeddings.py`

- Lazy load `SentenceTransformer` theo `EMBEDDING_MODEL`
- Encode batch (`normalize_embeddings=True`)
- Text = `title + " . " + description[:500]`
- Chỉ embed item chưa có embedding

### `pipeline/dedup.py` — gom items → stories

Cửa sổ: items `published` hoặc `first_seen` trong 48h quanh `target_date`.

1. **Exact link (union-find):** khóa liên kết `canonical_url`, `arxiv_id`, github repo `full_name`, hf model id. Ví dụ: paper HF có github repo X và repo X trên GitHub Trending → cùng story.
2. **Semantic:** cụm còn lại nối nếu cosine similarity embeddings ≥ `dedup_similarity_threshold` (pgvector hoặc numpy trên batch trong ngày).
3. Mỗi cụm: tạo/cập nhật story (`story_date = target_date`).
   - `primary_item` ưu tiên: blog chính thức > hf_papers > github > hf_models > hn/reddit
   - `title` = title primary item; `source_count` = số `source_key` khác nhau; gán `items.story_id`
4. Idempotent: khóa `story_date + primary item` — chạy lại cập nhật, không tạo trùng.

### `pipeline/classify.py`

1. Rule-based: match keywords `taxonomy.yaml` (case-insensitive, word boundary) trên title+description mọi item trong story.
2. Embedding: so embedding story (trung bình items) với embedding mô tả từng nhãn (cache); nhãn similarity > 0.45.
3. Gộp, tối đa 3 nhãn, ưu tiên rule-based. (LLM tinh chỉnh ở summarize.)
4. `watchlist_matches`: keywords watchlist + similarity description watchlist > 0.5.

### `pipeline/score.py` — `importance_score`

Theo `config/scoring.yaml`:

| Factor | Cách tính |
|---|---|
| **velocity** | Metric chính theo nguồn (github: `stars_today` hoặc delta stars; hf_papers: upvotes; hf_models: likes delta hoặc trending_rank đảo; hn: points; reddit: upvotes; arxiv/rss: 0). Chuẩn hóa percentile rank của `log1p(value)` **trong cùng `source_key`** ngày đó. Velocity story = max các item. |
| **cross_source** | `min(source_count - 1, 4) / 4` |
| **source_weight** | Max weight các source trong story (`sources.yaml`; rss big tech = 1.0, hf_papers 0.8, github 0.7, hn 0.6, reddit 0.5, arxiv 0.4) |
| **relevance** | Max similarity với watchlist (0..1), nhân priority |
| **freshness** | `0.5 ** (age_hours / half_life)` |

- `importance` = tổng có trọng số; lưu `score_breakdown` jsonb
- `is_big_tech` = có item từ feed `is_big_tech` hoặc organization thuộc: openai, google, deepmind, microsoft, meta, facebook, anthropic, nvidia, apple, amazon, qwen/alibaba, deepseek, mistralai

### `pipeline/runner.py`

- `run_pipeline(target_date, steps=None)`: collect → embed → dedup → classify → score → (summarize, brief, notify ở bước sau)
- Ghi `pipeline_runs` với `step_status`; bước lỗi → `partial`, vẫn chạy bước sau nếu có thể

### `scripts/run_pipeline.py`

- argparse `--date` (mặc định hôm nay theo TZ), `--only` step, `--skip` step

### Verify (bước 3)

Chạy `python scripts/run_pipeline.py` rồi in top 15 stories (title, source_count, topics, importance, breakdown). Test dedup (union-find, fixture 6 items → 2 stories) và score (percentile, freshness).

---

## Bước 4 — LLM summarize & Daily Brief

### `app/llm/client.py`

- Wrapper OpenAI-compatible (`base_url`, `api_key`, `model` từ settings)
- `chat_json(system, user, schema: type[BaseModel]) -> BaseModel`
  - `response_format json_object` nếu backend hỗ trợ; fallback trích JSON trong text
  - Validate pydantic; retry 1 lần khi parse lỗi; log token usage
- Nếu `LLM_API_KEY` rỗng và `base_url` không phải localhost → chế độ **no-LLM**: fallback (`summary` = description cắt 300 ký tự, `why_it_matters` rỗng, `action` = `"read"`)

### `app/llm/prompts.py`

#### STORY_SUMMARY

System: trợ lý tình báo công nghệ cho AI Head tại doanh nghiệp IT; tiếng Việt ngắn gọn; giữ thuật ngữ EN; chỉ dựa nội dung cung cấp; không bịa; trả JSON đúng schema.

User template input: danh sách nguồn (source, title, url, description cắt 800 ký tự, metrics) + taxonomy hợp lệ + watchlist.

Output JSON:

```json
{
  "title_vi": "tiêu đề ngắn tiếng Việt, <= 15 từ",
  "summary": "2 câu: cái gì mới",
  "why_it_matters": "1-2 câu: tác động với đội AI doanh nghiệp",
  "categories": ["tối đa 3 nhãn trong danh sách cho trước"],
  "maturity": "research | early-oss | production-ready",
  "action": "ignore | read | try-poc | share-team",
  "related_watchlist": ["chỉ tên trong watchlist"]
}
```

#### DAILY_TLDR

Input: top 15 story summaries (`title_vi`, `summary`, `why_it_matters`, `categories`, `score`).

Output:

```json
{
  "tldr": ["5 gạch đầu dòng, mỗi ý <= 30 từ, kèm [#story_id]"],
  "theme_of_the_day": "1 câu",
  "poc_candidates": [
    {"story_id": 1, "reason": "...", "suggested_experiment": "1-2 câu"}
  ]
}
```

- `poc_candidates`: tối đa 3; chỉ story `action=try-poc` hoặc maturity `early-oss` / `production-ready`.

### `pipeline/summarize.py`

- Top `LLM_MAX_ITEMS_PER_DAY` stories theo importance
- Bỏ qua story đã có summary với `content_hash` giống (cache)
- Gọi LLM; lưu `story_summaries`; cập nhật `stories.topics` bằng categories hợp lệ (lọc taxonomy)
- Tuần tự; concurrency tối đa 4 (ThreadPool)

### `pipeline/brief.py` — `build_daily_brief(target_date)`

- **top_story_ids:** top 10 theo importance, đa dạng (≤ 3 story cùng 1 topic chính; ưu tiên ≥ 1 watchlist nếu có)
- **rising:** top 5 repo theo `stars_today`; top 5 HF model/space theo trending; top 5 paper theo upvotes
- **big_tech:** stories `is_big_tech`, nhóm theo organization
- **tldr + poc_candidates** từ LLM
- **stats:** số item theo nguồn, số story, phân bố topic
- **markdown:** render toàn bộ brief (email/Teams/export)
- Lưu `daily_briefs` (upsert theo `brief_date`)

Gắn summarize + brief vào runner.

### Verify (bước 4)

Chạy pipeline, in markdown brief ra console. Test: `chat_json` với mock client trả JSON lỗi lần 1, đúng lần 2.

---

## Bước 5 — Streamlit Dashboard

Multipage, layout wide, đọc DB qua repository (`st.cache_data` ttl=300).

**Sidebar chung:** chọn ngày (mặc định brief mới nhất), chế độ Daily/Weekly/Monthly (weekly = 7 ngày, monthly = 30 ngày, gộp stories theo importance), filter topic, filter source, toggle “Chỉ watchlist”.

### `dashboard/Home.py` — “AI Morning Brief – {ngày}”

1. Hàng metric: tổng items, số stories, số nguồn hoạt động, số story watchlist, trạng thái pipeline run gần nhất
2. TL;DR: 5 bullet + “Theme of the day”
3. 2 cột: **Top Stories** (card: `title_vi`, link gốc, badge topics/maturity/action, summary, “Vì sao quan trọng”, icon nguồn + link, expander score_breakdown bar, nút 👍/👎 → `feedback`) | **Rising Now** (3 tab: Repos / Models & Spaces / Papers)
4. 2 cột: **Big Tech Releases** (nhóm organization) | **My Watchlist** (mỗi watchlist 1 expander)
5. **Topic Heatmap:** plotly heatmap topic × ngày 14 ngày (tổng importance); danh sách “đang nóng lên” / “đang nguội” (so 7 ngày gần vs 7 ngày trước)
6. **PoC Candidates:** card reason + suggested_experiment
7. Nút “Tải brief Markdown”

### Pages

| Page | Nội dung |
|---|---|
| `1_Explorer.py` | Bảng stories/items; search ILIKE + semantic (embed câu hỏi, pgvector cosine top 30); filter ngày/nguồn/topic/maturity/action; click → chi tiết story + items |
| `2_Trends.py` | Line chart story + importance theo topic 30/90 ngày; top repo tăng stars 7/30 ngày; top organization |
| `3_Watchlist.py` | Xem/sửa `watchlist.yaml` trên UI; timeline story match 30 ngày |
| `4_Weekly_Review.py` | Chọn tuần; top 10; topic tăng/giảm; PoC; “Generate weekly summary” (LLM executive summary tiếng Việt); tải Markdown |
| `5_Admin.py` | Lịch sử `pipeline_runs`; trạng thái connector; “Run pipeline now” (thread + log); thống kê feedback |

### UI components

`dashboard/components`: `story_card`, `source_badges`, `score_bar`. Màu badge cố định theo nhóm taxonomy. Không CSS phức tạp. DB rỗng → “Chưa có dữ liệu, vào Admin để chạy pipeline”.

### Verify (bước 5)

`docker compose up -d dashboard` → http://localhost:8501; mọi trang render được kể cả DB rỗng.

---

## Bước 6 — Scheduler, Notify, hoàn thiện

### `app/scheduler.py` — APScheduler `BlockingScheduler`, TZ `Asia/Ho_Chi_Minh`

- Job daily tại `BRIEF_SCHEDULE_HOUR:MINUTE`: `run_pipeline(today)`
- Job thứ Hai 06:30: thêm GitHub Trending weekly; ngày 1 hằng tháng: monthly
- Job snapshot metric 18:00: chỉ collect metrics (không summarize) — 2 điểm dữ liệu/ngày cho velocity
- Khi start: `alembic upgrade head`; nếu chưa có brief hôm nay và đã quá giờ chạy → chạy bù ngay
- `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1`

### `pipeline/notify.py`

Gửi brief sau khi build (kênh nào có cấu hình thì gửi); lỗi gửi **không** fail pipeline:

- **Teams** Incoming Webhook: message card ngắn (TL;DR + top 5 + link dashboard)
- **Telegram** bot: Markdown, tách tin nếu > 4000 ký tự
- **Email** SMTP: HTML render từ markdown

Thêm `DASHBOARD_URL` vào `.env.example`.

### `scripts/backfill.py --days 7`

Chạy pipeline N ngày trước (connector không hỗ trợ ngày quá khứ → skip; `hf_papers` và `arxiv` hỗ trợ).

### README.md

- Giới thiệu, kiến trúc (sơ đồ ASCII pipeline)
- Quick start: `cp .env.example .env` → `make up` → `make run` → mở 8501
- Thêm connector mới (`BaseConnector` + registry + `sources.yaml`)
- Thêm RSS feed; đổi LLM sang Ollama/vLLM
- Troubleshooting: rate limit GitHub, Reddit 403, model embedding tải chậm

### Chất lượng

- Ruff config; `pytest` toàn bộ; sửa hết lỗi
- `docker compose up -d --build` end-to-end từ đầu

### Checklist người dùng tự làm

- [ ] Điền `.env` (LLM key, tokens, webhook…)
- [ ] Kiểm tra các RSS URL đánh dấu `verify: true`
- [ ] Tạo GitHub token
- [ ] Tạo Teams webhook (nếu dùng)

---

## Prompt phụ (tham chiếu)

**Fix lỗi:** Tìm nguyên nhân gốc, sửa tối thiểu, giữ kiến trúc PROJECT_SPEC, thêm test tái hiện nếu hợp lý.

**Thêm nguồn mới:** Kế thừa `BaseConnector`, đăng ký registry, thêm `sources.yaml` + weight, test parse với fixture.

**Review:** Kiểm tra idempotent, isolation connector, N+1, LLM cache; sửa lỗi mức High.
