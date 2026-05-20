# -*- coding: utf-8 -*-
"""
本地对话 trace：按会话写入 JSON 文件（trace_<会话ID>.json），事件数组追加，含完整上下文。
环境变量：
- CHAT_TRACE_ENABLED：默认启用；设为 0 / false / no 则关闭写入
- CHAT_TRACE_DIR：trace 目录，默认项目根目录下 local_chat_traces
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
_DEFAULT_DIR = ROOT / "local_chat_traces"
TRACE_VERSION = 1


def _trace_enabled() -> bool:
    v = (os.environ.get("CHAT_TRACE_ENABLED") or "1").strip().lower()
    return v not in {"", "0", "false", "no", "off"}


def is_chat_trace_enabled() -> bool:
    """供 app 判断是否写入 trace。"""
    return _trace_enabled()


def trace_root() -> Path:
    raw = (os.environ.get("CHAT_TRACE_DIR") or "").strip()
    p = Path(raw) if raw else _DEFAULT_DIR
    return p if p.is_absolute() else (ROOT / p)


def _ts_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def trace_path(session_id: str) -> Path:
    sid = (session_id or "").strip()
    return trace_root() / f"trace_{sid}.json"


def _load_trace_doc(session_id: str) -> dict[str, Any]:
    sid = (session_id or "").strip()
    path = trace_path(sid)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("session_id"):
                raw.setdefault("version", TRACE_VERSION)
                raw.setdefault("events", [])
                return raw
        except (OSError, json.JSONDecodeError):
            pass
    now = _ts_utc()
    return {
        "version": TRACE_VERSION,
        "session_id": sid,
        "created_at": now,
        "updated_at": now,
        "events": [],
    }


def _append_event(session_id: str, event: Mapping[str, Any]) -> Path | None:
    if not _trace_enabled():
        return None
    sid = (session_id or "").strip()
    if not sid:
        return None
    trace_root().mkdir(parents=True, exist_ok=True)
    path = trace_path(sid)
    doc = _load_trace_doc(sid)
    ev = dict(event)
    ev.setdefault("ts", _ts_utc())
    doc["events"].append(ev)
    doc["updated_at"] = ev["ts"]
    try:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path
    except OSError:
        return None


def summarize_kb_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in hits:
        meta = h.get("metadata") if isinstance(h.get("metadata"), dict) else {}
        doc = str(h.get("document") or "")
        out.append(
            {
                "source": meta.get("source"),
                "title": meta.get("title"),
                "rerank_score": h.get("rerank_score"),
                "document_chars": len(doc),
            }
        )
    return out


def _serializable_hits(hits: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in hits or []:
        if not isinstance(h, dict):
            continue
        meta = h.get("metadata") if isinstance(h.get("metadata"), dict) else {}
        safe_meta: dict[str, Any] = {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                safe_meta[str(k)] = v
            else:
                safe_meta[str(k)] = str(v)
        out.append(
            {
                "document": str(h.get("document") or ""),
                "metadata": safe_meta,
                "rerank_score": h.get("rerank_score"),
            }
        )
    return out


def trace_session_start(session_id: str, *, meta: Mapping[str, Any] | None = None) -> None:
    _append_event(
        session_id,
        {
            "event": "session_start",
            "meta": dict(meta) if meta else {},
        },
    )


def trace_kb_refresh(session_id: str, payload: Mapping[str, Any]) -> None:
    p = dict(payload)
    hits = _serializable_hits(list(p.pop("hits", []) or []))
    outline = list(p.pop("hits_outline", []) or [])
    _append_event(
        session_id,
        {
            "event": "kb_refresh",
            **p,
            "hits_outline": outline,
            "hits": hits,
        },
    )


def trace_chat_blocked(session_id: str, *, reason_code: str, detail: str) -> None:
    _append_event(
        session_id,
        {
            "event": "chat_blocked",
            "reason_code": reason_code,
            "detail": (detail or "")[:8000],
        },
    )


def trace_chat_turn(
    session_id: str,
    *,
    turn_index: int,
    experience_snapshot: Mapping[str, Any],
    display_user: str,
    api_shadow_prior: list[dict[str, Any]],
    api_user_payload: str,
    api_assistant: str,
    system_prompt: str,
    temperature: float,
    first_kb_turn: bool,
    kb_hits: list[dict[str, Any]] | None = None,
    kb_outline: list[dict[str, Any]] | None = None,
    model: str,
) -> None:
    sy = system_prompt or ""
    digest = hashlib.sha256(sy.encode("utf-8")).hexdigest()
    exp = dict(experience_snapshot)
    hits_full = _serializable_hits(kb_hits)
    outline = list(kb_outline or summarize_kb_hits(hits_full))

    prior = [
        {"role": str(m.get("role") or ""), "content": str(m.get("content") or "")}
        for m in (api_shadow_prior or [])
        if (m.get("role") or "") in ("user", "assistant")
    ]

    _append_event(
        session_id,
        {
            "event": "chat_turn",
            "turn_index": turn_index,
            "experience_snapshot": exp,
            "display_user": display_user or "",
            "api_shadow_prior": prior,
            "api_user_payload": api_user_payload or "",
            "api_assistant": str(api_assistant or ""),
            "params": {
                "model": model,
                "temperature": temperature,
                "first_kb_turn": first_kb_turn,
                "system_prompt": sy,
                "system_chars": len(sy),
                "system_sha256": digest,
            },
            "kb_outline": outline,
            "kb_hits": hits_full,
        },
    )
