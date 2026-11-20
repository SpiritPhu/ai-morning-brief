"""Notify channels after brief is built."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.config import get_settings


def notify_brief(brief: dict[str, Any]) -> dict[str, str]:
    """Send brief to configured channels. Errors are logged, never raised."""
    settings = get_settings()
    status: dict[str, str] = {}
    tldr = brief.get("tldr") or []
    markdown = brief.get("markdown") or ""
    top_ids = brief.get("top_story_ids") or []
    date_str = str(brief.get("brief_date") or "")

    if settings.teams_webhook_url:
        try:
            _send_teams(settings.teams_webhook_url, date_str, tldr, top_ids, settings.dashboard_url)
            status["teams"] = "ok"
        except Exception as exc:
            logger.warning("Teams notify failed: {}", exc)
            status["teams"] = f"error: {exc}"

    if settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            _send_telegram(
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                date_str,
                tldr,
                markdown,
                settings.dashboard_url,
            )
            status["telegram"] = "ok"
        except Exception as exc:
            logger.warning("Telegram notify failed: {}", exc)
            status["telegram"] = f"error: {exc}"

    if settings.smtp_host and settings.email_to:
        try:
            _send_email(settings, date_str, markdown)
            status["email"] = "ok"
        except Exception as exc:
            logger.warning("Email notify failed: {}", exc)
            status["email"] = f"error: {exc}"

    if not status:
        status["none"] = "no channels configured"
    return status


def _send_teams(webhook: str, date_str: str, tldr: list, top_ids: list, dashboard: str) -> None:
    facts = [{"name": f"{i+1}", "value": str(t)[:200]} for i, t in enumerate(tldr[:5])]
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/json",
        "summary": f"AI Morning Brief {date_str}",
        "themeColor": "0078D7",
        "title": f"AI Morning Brief – {date_str}",
        "sections": [
            {"facts": facts},
            {
                "text": f"Top story ids: {', '.join(map(str, top_ids[:5]))}<br/>"
                f"[Open dashboard]({dashboard})"
            },
        ],
    }
    resp = httpx.post(webhook, json=card, timeout=20)
    resp.raise_for_status()


def _send_telegram(
    token: str, chat_id: str, date_str: str, tldr: list, markdown: str, dashboard: str
) -> None:
    header = f"*AI Morning Brief – {date_str}*\n\n"
    body = "\n".join(f"• {t}" for t in tldr[:5])
    text = header + body + f"\n\n[Dashboard]({dashboard})"
    chunks = _chunk(text, 4000) or [text]
    # Prefer short TL;DR; if empty use truncated markdown
    if not tldr and markdown:
        chunks = _chunk(markdown, 4000)
    for chunk in chunks:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
            timeout=20,
        )
        resp.raise_for_status()


def _chunk(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _send_email(settings, date_str: str, markdown: str) -> None:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    try:
        import markdown as md

        html = md.markdown(markdown)
    except Exception:
        html = f"<pre>{markdown}</pre>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"AI Morning Brief – {date_str}"
    msg["From"] = settings.smtp_user or "noreply@localhost"
    msg["To"] = settings.email_to
    msg.attach(MIMEText(markdown, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.sendmail(msg["From"], [settings.email_to], msg.as_string())
