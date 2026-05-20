# -*- coding: utf-8 -*-
"""加载根目录岗位/行业参考 Markdown，按章节供本地检索与展示。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KB_FILE = ROOT / "工科与管理学-实习就业岗位参考.md"


def load_raw() -> str:
    if not KB_FILE.exists():
        return ""
    return KB_FILE.read_text(encoding="utf-8")


def sections_by_h2(md: str) -> list[tuple[str, str]]:
    """按二级标题切分，返回 [(标题, 正文含其子标题), ...]。"""
    if not md.strip():
        return []
    parts = re.split(r"\n(?=## )", md.strip())
    out: list[tuple[str, str]] = []
    for block in parts:
        block = block.strip()
        if not block.startswith("## "):
            continue
        first_line, _, rest = block.partition("\n")
        title = first_line.replace("## ", "").strip()
        out.append((title, rest.strip()))
    return out


def flat_nav_options(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    构造下拉选项：(显示名, 该选项对应要展示的 Markdown 片段)。
    对「一、工科类」「二、管理学类」再按 ### 细分为可选项。
    """
    options: list[tuple[str, str]] = []
    for h2_title, body in sections:
        if h2_title.startswith("一、") or h2_title.startswith("二、"):
            prefix = "工科" if h2_title.startswith("一、") else "管理"
            subs = re.split(r"\n(?=### )", body)
            for idx, sub in enumerate(subs):
                sub = sub.strip()
                if not sub:
                    continue
                if sub.startswith("### "):
                    name = sub.split("\n", 1)[0].replace("### ", "").strip()
                    options.append((f"{prefix} · {name}", sub))
                elif idx == 0:
                    options.append((f"{prefix} · 总述", sub[:4000]))
        elif h2_title.startswith("三、") or h2_title.startswith("四、"):
            options.append((h2_title, body[:6000]))
    if not options:
        options.append(("全文预览", md_preview(load_raw(), 8000)))
    return options


def md_preview(md: str, max_len: int) -> str:
    if len(md) <= max_len:
        return md
    return md[:max_len] + "\n\n…（已截断，数据完全在本地，可打开源文件查看全文）"


def get_knowledge_context(display_key: str | None, selected_snippet: str) -> str:
    """供右侧展示或后续 RAG 拼接的固定知识片段。"""
    if selected_snippet:
        return selected_snippet
    return md_preview(load_raw(), 6000)
