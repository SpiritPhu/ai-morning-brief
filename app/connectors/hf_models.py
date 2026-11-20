"""Hugging Face trending models connector."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from loguru import logger

from app.connectors.base import BaseConnector, NormalizedItem


class HFModelsConnector(BaseConnector):
    key = "hf_models"
    item_type = "model"

    def fetch(self, target_date: date) -> list[NormalizedItem]:
        limit = int(self.params.get("limit", 50))
        url = (
            "https://huggingface.co/api/models"
            f"?sort=trendingScore&direction=-1&limit={limit}&full=false"
        )
        headers = {}
        if self.settings.hf_token:
            headers["Authorization"] = f"Bearer {self.settings.hf_token}"
        resp = self.http.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning("hf_models HTTP {}", resp.status_code)
            return []
        return parse_hf_models_payload(resp.json(), target_date)


def parse_hf_models_payload(
    data: list[dict[str, Any]], target_date: date, source_key: str = "hf_models"
) -> list[NormalizedItem]:
    items: list[NormalizedItem] = []
    for rank, row in enumerate(data, start=1):
        model_id = row.get("id") or row.get("modelId")
        if not model_id:
            continue
        org = model_id.split("/")[0] if "/" in model_id else None
        tags = row.get("tags") or []
        license_tag = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None)
        items.append(
            NormalizedItem(
                source_key=source_key,
                external_id=model_id,
                item_type="model" if source_key == "hf_models" else "space",
                title=model_id,
                url=f"https://huggingface.co/{model_id}",
                description=row.get("pipeline_tag") or "",
                organization=org,
                published_at=datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc),
                metrics={
                    "likes": float(row.get("likes") or 0),
                    "downloads": float(row.get("downloads") or 0),
                    "trending_rank": float(rank),
                },
                extra={
                    "hf_model_id": model_id,
                    "pipeline_tag": row.get("pipeline_tag"),
                    "library_name": row.get("library_name"),
                    "tags": tags,
                    "license": license_tag,
                },
            )
        )
    return items
