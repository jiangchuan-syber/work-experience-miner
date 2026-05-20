# -*- coding: utf-8 -*-
"""检索查询改写：以用户对话回答为主信号，多路扩展（无需外网 LLM）。"""
from __future__ import annotations

import re
from typing import Iterable


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _normalize(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t


def synthetic_question_from_experience(
    snippet: str,
    job_role: str = "",
) -> str:
    """经历描述过短且无话术回答时，从经历抽一个检索主题句。"""
    s = _normalize(snippet)
    if not s:
        return "实习岗位 特殊评价指标 证据 可量化成果"
    head = s[:320]
    role = _normalize(job_role)
    if role:
        return f"{role} {head} 岗位职责 评价指标 常见证据"
    return f"{head} 业务产出 难点 协作 评价维度"


def rewrite_queries(
    question: str = "",
    *,
    user_answer: str = "",
    student_track: str = "",
    job_role: str = "",
    company: str = "",
    experience_snippet: str = "",
    max_variants: int = 6,
) -> list[str]:
    """
    生成多路检索 query。**优先**使用 `user_answer`（模型交互里用户真实回答），
    再退回显式 `question`，最后才用经历摘要合成。
    扩展方向对齐知识库用途：特殊评价指标、差异化观察点、证据链、可量化影响。
    """
    primary = _normalize(user_answer)
    if not primary:
        primary = _normalize(question)
    if not primary and experience_snippet:
        primary = synthetic_question_from_experience(experience_snippet, job_role)
    if not primary:
        primary = "岗位 特殊评价指标 差异化 证据链 可量化"

    role = _normalize(job_role)
    org = _normalize(company)
    track = _normalize(student_track)
    tail = experience_snippet.strip()[:200] if experience_snippet else ""

    variants: list[str] = [
        primary,
        f"特殊评价指标 差异化 {primary}",
        f"典型产出 常见证据 {primary}",
        f"业务影响 可量化 结果 {primary}",
        f"难点 推进 协作 复盘 {primary}",
    ]
    if role:
        variants.append(f"{role} 实习 评价维度 {primary}")
    if org:
        variants.append(f"{org} {role or '实习'} {primary}")
    if track and track not in primary:
        variants.append(f"{track} {primary}")
    if tail:
        variants.append(f"{primary} {tail}")

    extra_q = _normalize(question)
    if (
        extra_q
        and primary
        and extra_q != primary
        and extra_q not in primary
        and primary not in extra_q
    ):
        variants.append(f"{primary} {extra_q}")

    return _dedupe_keep_order(variants)[:max_variants]
