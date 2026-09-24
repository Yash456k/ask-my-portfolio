from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import PipelineConfig

PROJECT_ROOT = Path(__file__).parents[1]


def test_shipped_embedder_ladder_has_unique_schema_backed_columns(pipeline: PipelineConfig) -> None:
    expected = {
        "minilm-l6": ("embedding_minilm", 384),
        "bge-small": ("embedding_bge_small", 384),
        "bge-base": ("embedding_bge_base", 768),
        "qwen3-embedding": ("embedding_qwen3", 1024),
        "portfolio-e5-small": ("embedding_portfolio_e5", 384),
        "portfolio-gte-small": ("embedding_portfolio_gte", 384),
    }
    actual = {item.id: (item.column, item.dimensions) for item in pipeline.embedders}

    assert actual == expected
    assert len({item.column for item in pipeline.embedders}) == len(pipeline.embedders)

    schema = (PROJECT_ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    for embedder in pipeline.embedders:
        pattern = rf"\b{re.escape(embedder.column)}\s+vector\({embedder.dimensions}\)"
        assert re.search(pattern, schema), f"schema does not match {embedder.id}"


def test_public_registry_defaults_and_fallbacks_only_reference_visible_choices(
    pipeline: PipelineConfig,
) -> None:
    public = pipeline.public_dict()
    embedder_ids = {item.id for item in pipeline.embedders}
    llm_ids = {item.id for item in pipeline.llms}

    assert 3 <= len(llm_ids) <= 5
    assert public["defaults"]["embedder"] in embedder_ids
    assert public["defaults"]["llm"] == "deepseek/deepseek-v4.1-flash"
    assert {item["id"] for item in public["embedders"]} == embedder_ids
    assert {item["id"] for item in public["llms"]} == llm_ids
    assert set(pipeline.fallback_order).issubset(llm_ids)
    assert public["retrieval"] == {
        "topK": 3,
        "selectableTopK": [3, 5, 7],
        "historyAware": True,
    }
    tuned = next(item for item in public["embedders"] if item["id"] == "portfolio-e5-small")
    assert tuned["optimization"]["portfolioTuned"] is True
    assert tuned["optimization"]["queryTransform"] == "E5 query/passage prefixes"


def test_deepseek_flash_and_model_weighted_budget_reserves(pipeline: PipelineConfig) -> None:
    deepseek = pipeline.llm("deepseek/deepseek-v4.1-flash")

    assert deepseek.provider == "openrouter"
    assert deepseek.input_usd_per_million == 0.14
    assert deepseek.output_usd_per_million == 0.42
    # Only the selected OpenRouter model is charged; the Groq fallback is free here.
    assert pipeline.request_cost_reserve_micro_usd(deepseek.id, 32_000) == 4_732
    assert pipeline.request_cost_reserve_micro_usd("qwen/qwen3.6-27b", 32_000) == 0
    assert pipeline.request_cost_reserve_micro_usd("openrouter/free", 32_000) == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_embedder_id", "embedder ids must be unique"),
        ("duplicate_embedder_column", "each embedder must have its own vector column"),
        ("duplicate_llm_id", "LLM ids must be unique"),
        ("unknown_default_llm", "default_llm must reference a configured LLM id"),
        ("unknown_fallback", "fallback_order may only contain configured LLM ids"),
    ],
)
def test_registry_rejects_ambiguous_or_unknown_mappings(
    pipeline_data: dict, mutation: str, message: str
) -> None:
    if mutation == "duplicate_embedder_id":
        pipeline_data["embedders"][1]["id"] = pipeline_data["embedders"][0]["id"]
    elif mutation == "duplicate_embedder_column":
        pipeline_data["embedders"][1]["column"] = pipeline_data["embedders"][0]["column"]
    elif mutation == "duplicate_llm_id":
        pipeline_data["llms"][1]["id"] = pipeline_data["llms"][0]["id"]
    elif mutation == "unknown_default_llm":
        pipeline_data["default_llm"] = "not/a-configured-model"
    else:
        pipeline_data["fallback_order"].append("not/a-configured-model")

    with pytest.raises(ValidationError, match=message):
        PipelineConfig.model_validate(pipeline_data)


def test_registry_lookup_fails_closed_for_unknown_ids(pipeline: PipelineConfig) -> None:
    with pytest.raises(KeyError, match="missing-embedder"):
        pipeline.embedder("missing-embedder")
    with pytest.raises(KeyError, match="missing-model"):
        pipeline.llm("missing-model")


def test_local_portfolio_embedders_allow_no_revision_and_define_expected_prefixes(
    pipeline: PipelineConfig,
) -> None:
    e5 = pipeline.embedder("portfolio-e5-small")
    gte = pipeline.embedder("portfolio-gte-small")

    assert e5.revision is None
    assert e5.query_prefix == "query: "
    assert e5.document_prefix == "passage: "
    assert gte.revision is None
    assert gte.query_prefix == ""
    assert gte.document_prefix == ""


def test_remote_embedder_requires_a_pinned_revision(pipeline_data: dict) -> None:
    pipeline_data["embedders"][0]["revision"] = None

    with pytest.raises(ValidationError, match="remote embedder models require a pinned revision"):
        PipelineConfig.model_validate(pipeline_data)
