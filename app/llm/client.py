"""OpenAI-compatible JSON chat client."""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Type, TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client = None

    @property
    def no_llm(self) -> bool:
        key = (self.settings.llm_api_key or "").strip()
        base = (self.settings.llm_base_url or "").lower()
        local = "localhost" in base or "127.0.0.1" in base
        return not key and not local

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.settings.llm_api_key or "no-key",
                base_url=self.settings.llm_base_url,
            )
        return self._client

    def chat_json(
        self,
        system: str,
        user: str,
        schema: Type[T],
        fallback: Optional[dict[str, Any]] = None,
    ) -> T:
        if self.no_llm:
            data = fallback or {}
            try:
                return schema.model_validate(data)
            except ValidationError:
                # best-effort defaults
                return schema.model_validate(
                    {f: ("" if t == str else ([] if t == list else None))
                     for f, t in [(n, str) for n in schema.model_fields]}
                    if False
                    else _schema_defaults(schema, data)
                )

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                raw = self._chat(system, user)
                payload = _extract_json(raw)
                return schema.model_validate(payload)
            except Exception as exc:
                last_err = exc
                logger.warning("chat_json attempt {} failed: {}", attempt + 1, exc)
        if fallback:
            return schema.model_validate(fallback)
        raise RuntimeError(f"chat_json failed: {last_err}")

    def _chat(self, system: str, user: str) -> str:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        try:
            kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
        except Exception:
            kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**kwargs)

        usage = getattr(resp, "usage", None)
        if usage:
            logger.info(
                "LLM tokens prompt={} completion={}",
                getattr(usage, "prompt_tokens", "?"),
                getattr(usage, "completion_tokens", "?"),
            )
        return resp.choices[0].message.content or "{}"


def _schema_defaults(schema: Type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for name, field in schema.model_fields.items():
        if name in out:
            continue
        ann = field.annotation
        if ann is str:
            out[name] = ""
        elif ann is list or str(ann).startswith("list"):
            out[name] = []
        else:
            out[name] = None
    return out
