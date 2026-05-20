# -*- coding: utf-8 -*-
"""对话引导 Markdown → 模型 system 侧说明（不参与行业知识向量检索）。"""
from __future__ import annotations

from pathlib import Path

from rag.chunking import KB_DIR, SYSTEM_PROMPT_KB_FILENAMES


def guide_path() -> Path:
    """首份 system 文档（对话引导），便于单测或单独打开。"""
    return KB_DIR / SYSTEM_PROMPT_KB_FILENAMES[0]


def load_system_prompt(fallback: str = "") -> str:
    blocks: list[str] = []
    for name in SYSTEM_PROMPT_KB_FILENAMES:
        p = KB_DIR / name
        if p.is_file():
            blocks.append(p.read_text(encoding="utf-8").strip())
    if not blocks:
        return fallback or "你是简历与经历挖掘助手：先倾听、再结构化，不替用户编造事实。"
    return "\n\n---\n\n".join(blocks)


def build_llm_user_message(
    user_answer: str,
    rag_hits: list[dict],
    *,
    experience_snippet: str = "",
    job_role: str = "",
    task_hint: str = "",
    include_rag_kb: bool = True,
    include_experience_snippet: bool = True,
) -> str:
    """
    拼装供对话模型使用的 user 消息：用户原话 + 首轮可选岗位知识节选 + 可选经历摘录。

    「首轮附带知识、后续只靠多轮历史」模式下：后续轮可将 include_rag_kb /
    include_experience_snippet 设为 False，仅发送用户本条追问。

    rag_hits 建议使用 retrieve_with_rewrite_rerank 返回、已按 rerank 排序的条目。
    """
    parts: list[str] = []
    if task_hint.strip():
        parts.append("【任务说明】\n" + task_hint.strip())
    ua = (user_answer or "").strip()
    if ua:
        parts.append("【用户回答（原始）】\n" + ua)
    if include_experience_snippet and experience_snippet.strip():
        parts.append("【简历/经历摘录（可对照）】\n" + experience_snippet.strip())
    if include_experience_snippet and job_role.strip():
        parts.append("【目标岗位/角色】\n" + job_role.strip())

    kb_lines: list[str] = []
    if include_rag_kb:
        for i, h in enumerate(rag_hits, 1):
            meta = h.get("metadata") or {}
            src = meta.get("source", "")
            title = meta.get("title", "")
            doc = (h.get("document") or "").strip()
            rs = h.get("rerank_score")
            head = f"### 节选 {i}：{src} · {title}"
            if rs is not None:
                head += f"（rerank={rs:.4f}）"
            kb_lines.append(head + "\n" + doc)
        if kb_lines:
            parts.append(
                "【岗位知识库节选（至多 2 条；按 rerank）】\n" + "\n\n".join(kb_lines)
            )

    if include_rag_kb or include_experience_snippet:
        parts.append(
            "请基于用户原话与上述岗位知识与经历摘录做回应：先倾听、少评判，可作澄清式提问或结构化改写建议；"
            "缺信息与不确定处请标「待补充」，不要虚构量化成果。"
            "若用户要求润色简历要点、改 bullet、写或改 STAR、或明确说「按模板改稿」，"
            "须严格按 system 中《经历表达》文档「协助改稿：模型 / 导师必须遵守的交付结构」"
            "所列标题与顺序输出（可省略用户声明不需要的小节，并在首行说明）。"
        )
    else:
        parts.append(
            "【续写约束】你在当前经历下已在**上文首轮 user 消息中**收到了岗位知识节选（至多 2 条）与经历摘录；"
            "**请勿**要求用户再次粘贴长篇经历或重复贴岗位知识条目。"
            "仅针对本条用户追问延续对话；可作澄清提问或改写补充，不要编造事实。"
        )
    return "\n\n".join(parts)
