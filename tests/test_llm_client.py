from typing import Any
from unittest.mock import MagicMock

from pydantic import BaseModel

from app.config import Settings
from app.llm.client import LLMClient


class Out(BaseModel):
    title_vi: str
    summary: str
    action: str = "read"


def test_chat_json_retries_then_succeeds():
    settings = Settings(llm_api_key="test", llm_base_url="https://api.openai.com/v1")
    client = LLMClient(settings)

    class Choice:
        def __init__(self, content):
            self.message = MagicMock(content=content)

    class Resp:
        def __init__(self, content):
            self.choices = [Choice(content)]
            self.usage = None

    mock = MagicMock()
    mock.chat.completions.create.side_effect = [
        Resp("not-json"),
        Resp('{"title_vi":"ok","summary":"s","action":"read"}'),
    ]
    client._client = mock

    out = client.chat_json("sys", "user", Out)
    assert out.title_vi == "ok"
    assert mock.chat.completions.create.call_count == 2


def test_no_llm_fallback():
    settings = Settings(llm_api_key="", llm_base_url="https://api.openai.com/v1")
    client = LLMClient(settings)
    assert client.no_llm
    out = client.chat_json(
        "s",
        "u",
        Out,
        fallback={"title_vi": "t", "summary": "desc", "action": "read"},
    )
    assert out.summary == "desc"
