# -*- coding: utf-8 -*-
"""工作岗位知识库：Markdown 分块。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "工作岗位知识库"
MIN_CHUNK_CHARS = 40

# 以下 Markdown 全文进入对话 system prompt，不参与行业知识向量检索（避免重复与过长命中）
SYSTEM_PROMPT_KB_FILENAMES: tuple[str, ...] = (
    "经历挖掘-对话引导.md",
    "经历表达-模板与改稿规范.md",
)
RAG_EXCLUDE_NAMES: frozenset[str] = frozenset(
    set(SYSTEM_PROMPT_KB_FILENAMES) | {"README.md"}
)


@dataclass(frozen=True)
class DocChunk:
    chunk_id: str
    source: str
    title: str
    text: str


def _title_from_block(block: str) -> str:
    first = block.strip().split("\n", 1)[0]
    first = re.sub(r"^#+\s*", "", first).strip()
    return first[:120] if first else ""


def iter_md_files(*, for_rag: bool = False) -> list[Path]:
    if not KB_DIR.is_dir():
        return []
    files = sorted(KB_DIR.glob("*.md"))
    out = [p for p in files if p.is_file()]
    if for_rag:
        out = [p for p in out if p.name not in RAG_EXCLUDE_NAMES]
    return out


def chunk_markdown_file(path: Path) -> list[DocChunk]:
    """按 ### 优先、否则按 ## 切分；过小段落丢弃。"""
    text = path.read_text(encoding="utf-8")
    source = path.name
    if re.search(r"\n###\s+", text):
        parts = re.split(r"\n(?=###\s+)", text.strip())
    else:
        parts = re.split(r"\n(?=##\s+)", text.strip())

    out: list[DocChunk] = []
    for i, raw in enumerate(parts):
        block = raw.strip()
        if len(block) < MIN_CHUNK_CHARS:
            continue
        title = _title_from_block(block)
        if not title:
            title = source.replace(".md", "")
        cid = f"{source}#{i}"
        out.append(DocChunk(chunk_id=cid, source=source, title=title, text=block))
    if not out and len(text.strip()) >= MIN_CHUNK_CHARS:
        out.append(
            DocChunk(
                chunk_id=f"{source}#0",
                source=source,
                title=source.replace(".md", ""),
                text=text.strip(),
            )
        )
    return out


def load_rag_chunks() -> list[DocChunk]:
    """仅岗位/行业指标类文档，供向量索引（排除 README 与进入 system 的全文 policy 类 md）。"""
    chunks: list[DocChunk] = []
    for fp in iter_md_files(for_rag=True):
        chunks.extend(chunk_markdown_file(fp))
    return chunks


def load_all_chunks() -> list[DocChunk]:
    """兼容旧名：与 load_rag_chunks 相同。"""
    return load_rag_chunks()
