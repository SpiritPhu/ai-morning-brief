"""Prompt templates."""

from __future__ import annotations

STORY_SUMMARY_SYSTEM = (
    "Bạn là trợ lý tình báo công nghệ cho một AI Head tại doanh nghiệp IT. "
    "Viết tiếng Việt ngắn gọn, giữ thuật ngữ kỹ thuật tiếng Anh. "
    "Chỉ dựa trên nội dung được cung cấp, không bịa số liệu, tên hay ngày. "
    "Trả về JSON đúng schema."
)

STORY_SUMMARY_USER = """Story sources:
{sources_json}

Valid taxonomy labels: {taxonomy}
Watchlist names: {watchlist}

Return JSON:
{{
 "title_vi": "tiêu đề ngắn tiếng Việt, <= 15 từ",
 "summary": "2 câu: cái gì mới",
 "why_it_matters": "1-2 câu: tác động với đội AI doanh nghiệp",
 "categories": ["tối đa 3 nhãn trong danh sách cho trước"],
 "maturity": "research | early-oss | production-ready",
 "action": "ignore | read | try-poc | share-team",
 "related_watchlist": ["chỉ tên trong watchlist"]
}}
"""

DAILY_TLDR_SYSTEM = (
    "Bạn là trợ lý tóm tắt Daily Brief cho AI Head. "
    "Viết tiếng Việt ngắn gọn, giữ thuật ngữ tiếng Anh. Trả về JSON đúng schema."
)

DAILY_TLDR_USER = """Top stories:
{stories_json}

Return JSON:
{{
 "tldr": ["5 gạch đầu dòng, mỗi ý <= 30 từ, kèm [#story_id]"],
 "theme_of_the_day": "1 câu",
 "poc_candidates": [
   {{"story_id": 1, "reason": "...", "suggested_experiment": "1-2 câu"}}
 ]
}}
Chỉ chọn tối đa 3 poc_candidates với action try-poc hoặc maturity early-oss/production-ready.
"""

WEEKLY_SUMMARY_SYSTEM = (
    "Bạn viết executive summary tiếng Việt cho báo cáo tuần gửi sếp (AI Head). "
    "Ngắn gọn, actionable, giữ thuật ngữ tiếng Anh. Trả về JSON "
    '{{"markdown": "..."}}.'
)

WEEKLY_SUMMARY_USER = """Tuần {week_label}
Stories:
{stories_json}

Viết markdown 1 trang: điểm nổi bật, xu hướng topic, đề xuất PoC.
"""

CDO_BRIEF_SYSTEM = (
    "Bạn là strategic advisor cho một CDO / Head of AI tại doanh nghiệp IT Việt Nam. "
    "Người đọc chỉ có 5–7 phút buổi sáng. Viết tiếng Việt executive, rõ ràng, "
    "giữ thuật ngữ kỹ thuật tiếng Anh. Không hype, không bịa số liệu. "
    "Ưu tiên: tín hiệu chiến lược, rủi ro/cơ hội enterprise, quyết định nên cân nhắc, "
    "và 1 nudges giúp CDO trở nên sắc hơn mỗi ngày. Trả về JSON đúng schema."
)

CDO_BRIEF_USER = """Ngày: {brief_date}
Theme of the day: {theme}
Watchlist ưu tiên của tổ chức: {watchlist}
Phân bố topic hôm nay: {topic_stats}

Top stories (đã tóm tắt):
{stories_json}

Rising signals (repos/models/papers):
{rising_json}

Return JSON:
{{
  "executive_headline": "1 câu tầm nhìn ngày hôm nay (<= 25 từ)",
  "trend_summary": "2-3 câu: xu hướng đang nổi, dùng ngôn ngữ CDO (impact / timing / bets)",
  "strategic_signals": [
    "3-5 gạch đầu dòng: tín hiệu chiến lược (cơ hội, rủi ro, shift nền tảng)"
  ],
  "technology_radar": [
    {{
      "name": "công nghệ / pattern",
      "ring": "adopt | trial | assess | hold",
      "why": "1 câu vì sao CDO cần để ý"
    }}
  ],
  "enterprise_implications": "2-3 câu: ý nghĩa với AI roadmap / operating model / talent / risk của doanh nghiệp",
  "decisions_to_consider": [
    "2-4 câu hỏi hoặc quyết định CDO nên mang vào standup/leadership sync"
  ],
  "watchlist_lens": "1-2 câu nối tin hôm nay với watchlist nội bộ (SOC AI, ASR, RAG, Agents...)",
  "growth_nudge": "1 tip ngắn giúp CDO đọc tín hiệu tốt hơn / đặt câu hỏi tốt hơn hôm nay",
  "deep_dive_suggestion": "1 chủ đề nên đọc sâu hơn trong tuần (kèm lý do 1 câu)"
}}
Tối đa 5 mục technology_radar. Chỉ dựa trên dữ liệu được cung cấp.
"""
