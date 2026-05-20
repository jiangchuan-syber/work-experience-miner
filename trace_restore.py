# -*- coding: utf-8 -*-
"""从本地 `local_chat_traces/trace_*.json`（或旧版 `.md`）解析并恢复会话。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedTraceTurn:
    turn_index: int
    display_user: str
    api_user_message: str
    api_assistant: str
    experience_snapshot: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedTraceRestore:
    trace_session_id: str | None
    turns: list[ParsedTraceTurn]


def _leading_backticks(line: str) -> int:
    s = line.lstrip()
    n = 0
    while n < len(s) and s[n] == "`":
        n += 1
    return n


def _extract_fenced_after_heading(block: str, heading_line: str) -> str | None:
    """heading 形如「### xxx」独占一节之后，抓取第一个 fenced code block。"""
    idx = block.find(heading_line)
    if idx < 0:
        return None
    sub = block[idx + len(heading_line) :]
    lines = sub.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return None
    n = _leading_backticks(lines[i])
    if n < 3:
        return None
    body: list[str] = []
    for ln in lines[i + 1 :]:
        if ln.strip() == "`" * n:
            break
        body.append(ln)
    return "\n".join(body)


def _parse_snapshot(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    sec = "### 当前经历快照"
    p = block.find(sec)
    if p < 0:
        return out
    sub = block[p + len(sec) :].split("\n### ", 1)[0]
    for line in sub.splitlines():
        line = line.strip()
        mm = re.match(r"^- \*\*([^*]+)\*\*：(.*?)$", line)
        if mm:
            out[mm.group(1).strip()] = mm.group(2).strip()
    return out


_HEAD_TURN = re.compile(r"(?m)^## 第 (\d+) 轮对话 · `([^`]+)`\s*$")
_SESSION_HDR = re.compile(r"- \*\*session_id\*\*[：:]\s*`([^`]+)`")


def extract_raw_description_from_api_user(api_user: str) -> str:
    """从首轮完整 user 中抠出「经历摘录」正文（若有）。"""
    m = re.search(
        r"【简历/经历摘录（可对照）】\s*\r?\n(.+?)(?=\r?\n【目标岗位/角色】)",
        api_user,
        re.DOTALL,
    )
    if not m:
        return ""
    body = (m.group(1) or "").strip()
    lines = body.splitlines()
    if lines and "【当前选中经历" in lines[0]:
        return "\n".join(lines[1:]).strip()
    return body


def _snapshot_to_str_map(snap: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (snap or {}).items():
        if v is None:
            continue
        out[str(k)] = str(v)
    return out


def parse_trace_json_for_restore(data: dict[str, Any] | str) -> ParsedTraceRestore:
    if isinstance(data, str):
        raw = json.loads(data)
    else:
        raw = data
    if not isinstance(raw, dict):
        raise ValueError("trace JSON 根节点须为对象")

    trace_sid = str(raw.get("session_id") or "").strip() or None
    turns: list[ParsedTraceTurn] = []

    for ev in raw.get("events") or []:
        if not isinstance(ev, dict) or ev.get("event") != "chat_turn":
            continue
        snap = _snapshot_to_str_map(ev.get("experience_snapshot"))
        api_user = str(ev.get("api_user_payload") or "")
        if not snap.get("raw_description"):
            guessed = extract_raw_description_from_api_user(api_user)
            if guessed:
                snap["raw_description"] = guessed

        turns.append(
            ParsedTraceTurn(
                turn_index=int(ev.get("turn_index") or 0),
                display_user=str(ev.get("display_user") or "").strip(),
                api_user_message=api_user.strip(),
                api_assistant=str(ev.get("api_assistant") or "").strip(),
                experience_snapshot=snap,
            )
        )

    if not turns:
        raise ValueError("JSON trace 中未找到 chat_turn 事件，无法恢复")

    turns.sort(key=lambda t: t.turn_index)
    return ParsedTraceRestore(trace_session_id=trace_sid, turns=turns)


def parse_trace_md_for_restore(md: str) -> ParsedTraceRestore:
    if not md or not md.strip():
        raise ValueError("Markdown 为空")

    sid_m = _SESSION_HDR.search(md)
    trace_sid = sid_m.group(1).strip() if sid_m else None

    matches = list(_HEAD_TURN.finditer(md))
    if not matches:
        raise ValueError("未找到「## 第 N 轮对话」章节，无法恢复")

    turns: list[ParsedTraceTurn] = []
    for i, m in enumerate(matches):
        tidx = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        block = md[start:end]

        ds = "### 界面输入（用户原话）"
        api = "### 发往模型的完整 user 消息"
        asst = "### 助手回复"

        display = _extract_fenced_after_heading(block, ds)
        api_user = _extract_fenced_after_heading(block, api)
        assistant = _extract_fenced_after_heading(block, asst)
        if display is None:
            raise ValueError(f"第 {tidx} 轮：找不到「界面输入」代码块")
        if api_user is None:
            raise ValueError(f"第 {tidx} 轮：找不到「发往模型的完整 user 消息」代码块")
        if assistant is None:
            raise ValueError(f"第 {tidx} 轮：找不到「助手回复」代码块")

        snap = _parse_snapshot(block)
        if not snap.get("raw_description"):
            guessed = extract_raw_description_from_api_user(api_user.strip())
            if guessed:
                snap["raw_description"] = guessed

        turns.append(
            ParsedTraceTurn(
                turn_index=tidx,
                display_user=display.strip(),
                api_user_message=api_user.strip(),
                api_assistant=assistant.strip(),
                experience_snapshot=snap,
            )
        )

    turns.sort(key=lambda t: t.turn_index)
    return ParsedTraceRestore(trace_session_id=trace_sid, turns=turns)


def parse_trace_for_restore(text: str) -> ParsedTraceRestore:
    """自动识别 JSON / 旧版 Markdown trace。"""
    t = (text or "").lstrip()
    if t.startswith("{"):
        return parse_trace_json_for_restore(t)
    return parse_trace_md_for_restore(text)
