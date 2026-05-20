# -*- coding: utf-8 -*-
"""多查询检索 + RRF 融合 + Cross-Encoder 重排序。"""
from __future__ import annotations

from typing import Any

from rag.embed_store import JobKBIndex
from rag.query_rewrite import rewrite_queries
from rag.rerank import build_rerank_query, rerank_pairs


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    k: int = 60,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_id_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


def retrieve_with_rewrite_rerank(
    index: JobKBIndex,
    question: str = "",
    *,
    user_answer: str = "",
    student_track: str = "",
    job_role: str = "",
    company: str = "",
    experience_snippet: str = "",
    top_k_per_query: int = 8,
    rrf_top_n: int = 28,
    final_k: int = 8,
    max_queries: int = 6,
    do_rerank: bool = True,
    rerank_model: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], str]:
    """
    返回：(重排序后的 hits, 改写子查询列表, 用于 rerank 的查询串)。
    """
    queries = rewrite_queries(
        question,
        user_answer=user_answer,
        student_track=student_track,
        job_role=job_role,
        company=company,
        experience_snippet=experience_snippet,
        max_variants=max_queries,
    )

    ranked_lists: list[list[str]] = []
    id_to_hit: dict[str, dict[str, Any]] = {}

    for q in queries:
        hits = index.search_one(q, top_k=top_k_per_query)
        ranked: list[str] = []
        for h in hits:
            cid = h["id"]
            ranked.append(cid)
            if cid not in id_to_hit:
                id_to_hit[cid] = h
        ranked_lists.append(ranked)

    fused = reciprocal_rank_fusion(ranked_lists)
    top_ids = sorted(fused.keys(), key=lambda x: fused[x], reverse=True)[:rrf_top_n]

    merged: list[dict[str, Any]] = []
    for cid in top_ids:
        base = dict(
            id_to_hit.get(
                cid,
                {"id": cid, "document": "", "metadata": {}, "distance": None},
            )
        )
        base["rrf_score"] = round(float(fused.get(cid, 0.0)), 6)
        merged.append(base)

    rerank_q = build_rerank_query(
        user_answer or question,
        job_role=job_role,
        primary_rewritten=queries[0] if queries else "",
    )

    if do_rerank and merged:
        kwargs: dict[str, Any] = {"top_k": final_k}
        if rerank_model:
            kwargs["model_name"] = rerank_model
        try:
            merged = rerank_pairs(rerank_q, merged, **kwargs)
        except Exception:  # noqa: BLE001 — rerank 模型加载/推理失败时退化到 RRF 顺序
            merged = merged[:final_k]
    else:
        merged = merged[:final_k]

    return merged, queries, rerank_q


def retrieve_with_rewrite(
    index: JobKBIndex,
    question: str,
    **kwargs: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    """兼容旧接口：等价于不重排时仅 RRF（或传入 do_rerank=False）。"""
    hits, qs, _ = retrieve_with_rewrite_rerank(
        index, question, do_rerank=kwargs.pop("do_rerank", False), **kwargs
    )
    return hits, qs


__all__ = [
    "retrieve_with_rewrite",
    "retrieve_with_rewrite_rerank",
    "reciprocal_rank_fusion",
]
