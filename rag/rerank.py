# -*- coding: utf-8 -*-
"""第二阶段：Cross-Encoder 对 RRF 候选重排序（比双塔向量更贴「查询-文档」匹配）。"""
from __future__ import annotations

from typing import Any

# 多语言；体量适中。可替换为 BAAI/bge-reranker-base 等中文更强的模型
DEFAULT_RERANKER = "cross-encoder/ms-marco-multilingual-MiniLM-L12-v2"


def _cross_encoder(model_name: str):  # type: ignore[no-untyped-def]
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


_cached_name: str | None = None
_cached_model: Any = None


def get_reranker(model_name: str = DEFAULT_RERANKER):  # type: ignore[no-untyped-def]
    global _cached_name, _cached_model
    if _cached_model is None or _cached_name != model_name:
        _cached_model = _cross_encoder(model_name)
        _cached_name = model_name
    return _cached_model


def rerank_pairs(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    top_k: int,
    model_name: str = DEFAULT_RERANKER,
    text_max: int = 3800,
) -> list[dict[str, Any]]:
    """
    candidates 须含 key `document`；返回新列表，按 rerank_score 降序，截断 top_k。
    """
    q = (query or "").strip()
    if not q or not candidates:
        return candidates[:top_k]

    model = get_reranker(model_name)
    texts = []
    for h in candidates:
        doc = (h.get("document") or "")[:text_max]
        texts.append(doc)

    pairs = [(q, t) for t in texts]
    raw_scores = model.predict(pairs, batch_size=8, show_progress_bar=False)
    try:
        scores_list = raw_scores.tolist()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        scores_list = list(raw_scores)

    enriched: list[dict[str, Any]] = []
    for h, sc in zip(candidates, scores_list):
        row = dict(h)
        row["rerank_score"] = float(sc)
        enriched.append(row)

    enriched.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    return enriched[:top_k]


def build_rerank_query(
    user_answer: str,
    job_role: str = "",
    primary_rewritten: str = "",
) -> str:
    """用于 cross-encoder 的单条查询：优先用户原话，辅以岗位与改写主句。"""
    parts: list[str] = []
    u = (user_answer or "").strip()
    if u:
        parts.append(u)
    r = (job_role or "").strip()
    if r and r not in u:
        parts.append(f"岗位：{r}")
    p = (primary_rewritten or "").strip()
    if p and p != u and p not in u:
        parts.append(p)
    parts.append("岗位特殊评价指标 差异化 证据 可量化")
    return " \n".join(parts)
