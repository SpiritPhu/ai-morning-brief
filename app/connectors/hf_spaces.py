"""Hugging Face trending spaces connector."""

from __future__ import annotations

from datetime import date

from loguru import logger

from app.connectors.base import BaseConnector, NormalizedItem
from app.connectors.hf_models import parse_hf_models_payload


class HFSpacesConnector(BaseConnector):
    key = "hf_spaces"
    item_type = "space"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        limit = int(self.params.get("limit", 50))
        url = (
            "https://huggingface.co/api/spaces"
            f"?sort=trendingScore&direction=-1&limit={limit}&full=false"
        )
        headers = {}
        if self.settings.hf_token:
            headers["Authorization"] = f"Bearer {self.settings.hf_token}"
        resp = self.http.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning("hf_spaces HTTP {}", resp.status_code)
            return []
        return parse_hf_models_payload(resp.json(), target_date, source_key="hf_spaces")
