# -*- coding: utf-8 -*-
"""
对话历史：每条对话对应本地一个完整卡片（`local_chat_histories/{id}.json`）。
与 `local_chat_traces/trace_{id}.json` 共用同一 conversation id（= trace session id）。
列表从磁盘扫描；切换时优先读 JSON 历史，否则从 trace JSON（或旧版 .md）解析并回写 JSON。
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from chat_trace import trace_path, trace_root
from trace_restore import ParsedTraceRestore, parse_trace_for_restore

ROOT = Path(__file__).resolve().parent
_HISTORY_DIR = ROOT / "local_chat_histories"

_HEAD_TURN_TS = re.compile(r"(?m)^## 第 \d+ 轮对话 · `([^`]+)`\s*$")


def history_root() -> Path:
    return _HISTORY_DIR


def conversation_json_path(conversation_id: str) -> Path:
    return history_root() / f"{conversation_id}.json"


def conversation_trace_path(conversation_id: str) -> Path:
    return trace_path(conversation_id)


def conversation_trace_legacy_md_path(conversation_id: str) -> Path:
    return trace_root() / f"trace_{conversation_id}.md"


def default_welcome_messages() -> list[dict[str, str]]:
    return [
        {
            "role": "assistant",
            "content": (
                "你好。切换上方「对话选用」会按该段经历匹配岗位知识（top-2）；"
                "同一对话内首轮消息会带上节选与经历摘录，后续追问靠多轮历史延续。"
                "左侧历史来自本机已保存的对话，每条一张卡片。"
            ),
        }
    ]


def _first_user_line(messages: list[dict[str, Any]]) -> str:
    for m in messages:
        if (m.get("role") or "") == "user":
            t = str(m.get("content") or "").strip()
            if t:
                return t
    return ""


def _last_user_line(messages: list[dict[str, Any]]) -> str:
    last = ""
    for m in messages:
        if (m.get("role") or "") == "user":
            t = str(m.get("content") or "").strip()
            if t:
                last = t
    return last


def chat_title_from_state(
    messages: list[dict[str, Any]],
    *,
    experiences: list[dict[str, Any]] | None = None,
    active_exp_index: int = 0,
) -> str:
    user = _first_user_line(messages)
    if user:
        one = user.replace("\n", " ").strip()
        return (one[:28] + "…") if len(one) > 28 else one
    exps = experiences or []
    if exps and 0 <= active_exp_index < len(exps):
        e = exps[active_exp_index]
        co = (e.get("company") or "").strip() or "未填公司"
        ro = (e.get("role") or "").strip()
        base = co if not ro else f"{co}·{ro}"
        return (base[:28] + "…") if len(base) > 28 else base
    return "新对话"


def chat_preview_from_messages(messages: list[dict[str, Any]]) -> str:
    last = _last_user_line(messages)
    if not last:
        for m in reversed(messages):
            if (m.get("role") or "") == "assistant":
                t = str(m.get("content") or "").strip().replace("\n", " ")
                if t:
                    return (t[:36] + "…") if len(t) > 36 else t
        return "暂无消息"
    one = last.replace("\n", " ").strip()
    return (one[:36] + "…") if len(one) > 36 else one


def _unify_conversation_id(ss: Any) -> str:
    cid = (
        str(ss.get("jx_trace_session_id") or "").strip()
        or str(ss.get("jx_active_chat_id") or "").strip()
    )
    if not cid:
        cid = str(uuid.uuid4())
    ss.jx_active_chat_id = cid
    ss.jx_trace_session_id = cid
    return cid


def snapshot_from_session(ss: Any) -> dict[str, Any]:
    cid = _unify_conversation_id(ss)
    anchor = ss.get("jx_kb_anchor_key")
    anchor_serial: list[Any] | None
    if anchor is None:
        anchor_serial = None
    elif isinstance(anchor, (list, tuple)):
        anchor_serial = [int(anchor[0]), str(anchor[1])]
    else:
        anchor_serial = None

    messages = list(ss.get("chat_messages") or [])
    return {
        "id": cid,
        "title": chat_title_from_state(
            messages,
            experiences=list(ss.get("experiences") or []),
            active_exp_index=int(ss.get("active_exp_index") or 0),
        ),
        "preview": chat_preview_from_messages(messages),
        "updated_at": float(time.time()),
        "turn_count": sum(1 for m in messages if (m.get("role") or "") == "user"),
        "chat_messages": [dict(m) for m in messages],
        "jx_shadow_messages": [dict(m) for m in (ss.get("jx_shadow_messages") or [])],
        "jx_trace_session_id": cid,
        "jx_trace_turn_index": int(ss.get("jx_trace_turn_index") or 0),
        "active_exp_index": int(ss.get("active_exp_index") or 0),
        "jx_kb_anchor_key": anchor_serial,
        "jx_kb_top2_hits": [dict(h) for h in (ss.get("jx_kb_top2_hits") or [])],
    }


def save_conversation_record(record: dict[str, Any]) -> None:
    cid = str(record.get("id") or "").strip()
    if not cid:
        return
    history_root().mkdir(parents=True, exist_ok=True)
    out = dict(record)
    out["id"] = cid
    out["updated_at"] = float(out.get("updated_at") or time.time())
    path = conversation_json_path(cid)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def load_conversation_record(conversation_id: str) -> dict[str, Any] | None:
    cid = (conversation_id or "").strip()
    if not cid:
        return None
    path = conversation_json_path(cid)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["id"] = cid
            return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def record_from_parsed_trace(parsed: ParsedTraceRestore) -> dict[str, Any]:
    turns = sorted(parsed.turns, key=lambda t: t.turn_index)
    cid = (parsed.trace_session_id or "").strip() or str(uuid.uuid4())
    chat_pairs: list[dict[str, str]] = []
    shadow: list[dict[str, str]] = []
    for pt in turns:
        chat_pairs.append({"role": "user", "content": pt.display_user})
        chat_pairs.append({"role": "assistant", "content": pt.api_assistant})
        shadow.append({"role": "user", "content": pt.api_user_message})
        shadow.append({"role": "assistant", "content": pt.api_assistant})

    last = turns[-1].experience_snapshot if turns else {}
    try:
        active_idx = int(last.get("experience_index", 0))
    except (TypeError, ValueError):
        active_idx = 0

    return {
        "id": cid,
        "title": chat_title_from_state(chat_pairs),
        "preview": chat_preview_from_messages(chat_pairs),
        "updated_at": float(time.time()),
        "turn_count": len(turns),
        "chat_messages": chat_pairs,
        "jx_shadow_messages": shadow,
        "jx_trace_session_id": cid,
        "jx_trace_turn_index": len(turns),
        "active_exp_index": active_idx,
        "jx_kb_anchor_key": None,
        "jx_kb_top2_hits": [],
        "experience_id": (last.get("experience_id") or "").strip(),
        "company": (last.get("company") or "").strip(),
        "role": (last.get("role") or "").strip(),
    }


def _trace_updated_at_from_json(doc: dict[str, Any], fallback: float) -> float:
    ts = str(doc.get("updated_at") or "").strip()
    if ts:
        try:
            from datetime import datetime

            return datetime.fromisoformat(ts).timestamp()
        except ValueError:
            pass
    events = doc.get("events") or []
    if events and isinstance(events[-1], dict):
        ets = str(events[-1].get("ts") or "").strip()
        if ets:
            try:
                from datetime import datetime

                return datetime.fromisoformat(ets).timestamp()
            except ValueError:
                pass
    return fallback


def summarize_trace_file(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    cid = path.stem.replace("trace_", "", 1) or path.stem
    updated_at = path.stat().st_mtime

    if path.suffix.lower() == ".json":
        doc: dict[str, Any] | None = None
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                doc = loaded
        except json.JSONDecodeError:
            return None
        if doc:
            cid = str(doc.get("session_id") or cid).strip() or cid
            updated_at = _trace_updated_at_from_json(doc, updated_at)
        try:
            parsed = parse_trace_for_restore(text)
        except ValueError:
            parsed = None
        if parsed and parsed.turns:
            rec = record_from_parsed_trace(parsed)
            rec["updated_at"] = updated_at
            rec["storage"] = "trace"
            return rec
        title = "新对话"
        preview = "仅有会话启动记录"
        if doc:
            for ev in doc.get("events") or []:
                if isinstance(ev, dict) and ev.get("event") == "kb_refresh":
                    co = str(ev.get("company") or "").strip()
                    ro = str(ev.get("role") or "").strip()
                    if co:
                        title = (co + (f"·{ro}" if ro else ""))[:28]
                    break
        return {
            "id": cid,
            "title": title,
            "preview": preview,
            "updated_at": updated_at,
            "turn_count": 0,
            "storage": "trace",
        }

    sid_m = re.search(r"- \*\*session_id\*\*[：:]\s*`([^`]+)`", text)
    cid = (sid_m.group(1).strip() if sid_m else cid) or path.stem
    ts_matches = list(_HEAD_TURN_TS.finditer(text))
    if ts_matches:
        try:
            from datetime import datetime

            updated_at = datetime.fromisoformat(ts_matches[-1].group(1)).timestamp()
        except ValueError:
            pass
    try:
        parsed = parse_trace_for_restore(text)
    except ValueError:
        parsed = None
    if parsed and parsed.turns:
        rec = record_from_parsed_trace(parsed)
        rec["updated_at"] = updated_at
        rec["storage"] = "trace"
        return rec
    title = "新对话"
    preview = "仅有会话启动记录" if "会话启动" in text else "本地 trace"
    m_co = re.search(r"- \*\*company\*\*：(.+)$", text, re.MULTILINE)
    m_ro = re.search(r"- \*\*role\*\*：(.+)$", text, re.MULTILINE)
    if m_co and m_co.group(1).strip():
        title = (m_co.group(1).strip() + (f"·{m_ro.group(1).strip()}" if m_ro else ""))[:28]
    return {
        "id": cid,
        "title": title,
        "preview": preview,
        "updated_at": updated_at,
        "turn_count": 0,
        "storage": "trace",
    }


def list_conversation_cards() -> list[dict[str, Any]]:
    """扫描本机 JSON + trace，每条对话一张卡片（按 updated_at 降序）。"""
    by_id: dict[str, dict[str, Any]] = {}
    history_root().mkdir(parents=True, exist_ok=True)

    for p in history_root().glob("*.json"):
        cid = p.stem
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            data["id"] = cid
            data["storage"] = "json"
            data["turn_count"] = int(
                data.get("turn_count")
                or sum(1 for m in (data.get("chat_messages") or []) if m.get("role") == "user")
            )
            by_id[cid] = data
        except (OSError, json.JSONDecodeError):
            continue

    tr_root = trace_root()
    if tr_root.is_dir():
        seen_trace: set[str] = set()
        for pattern in ("trace_*.json", "trace_*.md"):
            for p in tr_root.glob(pattern):
                cid = p.stem.replace("trace_", "", 1)
                if cid in seen_trace:
                    if cid in by_id:
                        by_id[cid]["has_trace"] = True
                        tp = p.stat().st_mtime
                        if float(by_id[cid].get("updated_at") or 0) < tp:
                            by_id[cid]["updated_at"] = tp
                    continue
                seen_trace.add(cid)
                if cid in by_id:
                    by_id[cid]["has_trace"] = True
                    tp = p.stat().st_mtime
                    if float(by_id[cid].get("updated_at") or 0) < tp:
                        by_id[cid]["updated_at"] = tp
                    continue
                card = summarize_trace_file(p)
                if card:
                    card["has_trace"] = True
                    by_id[cid] = card

    return sorted(by_id.values(), key=lambda h: float(h.get("updated_at") or 0), reverse=True)


def apply_snapshot_to_session(ss: Any, record: dict[str, Any]) -> None:
    cid = str(record.get("id") or record.get("jx_trace_session_id") or uuid.uuid4())
    ss.jx_active_chat_id = cid
    ss.jx_trace_session_id = cid
    ss.chat_messages = [dict(m) for m in (record.get("chat_messages") or default_welcome_messages())]
    ss.jx_shadow_messages = [dict(m) for m in (record.get("jx_shadow_messages") or [])]
    ss.jx_trace_turn_index = int(record.get("jx_trace_turn_index") or 0)
    ss.active_exp_index = int(record.get("active_exp_index") or 0)
    ak = record.get("jx_kb_anchor_key")
    if ak is None:
        ss.jx_kb_anchor_key = None
    elif isinstance(ak, (list, tuple)) and len(ak) >= 2:
        ss.jx_kb_anchor_key = (int(ak[0]), str(ak[1]))
    else:
        ss.jx_kb_anchor_key = None
    ss.jx_kb_top2_hits = [dict(h) for h in (record.get("jx_kb_top2_hits") or [])]
    ss.pop("_pending_active_exp_idx", None)


def persist_active_chat(ss: Any) -> None:
    """当前对话写入本地 JSON（完整卡片）。"""
    save_conversation_record(snapshot_from_session(ss))


def _load_conversation_into_session(ss: Any, conversation_id: str) -> bool:
    cid = (conversation_id or "").strip()
    if not cid:
        return False
    rec = load_conversation_record(cid)
    if rec and (rec.get("chat_messages") or rec.get("jx_shadow_messages")):
        apply_snapshot_to_session(ss, rec)
        return True
    tp = conversation_trace_path(cid)
    if not tp.is_file():
        tp = conversation_trace_legacy_md_path(cid)
    if not tp.is_file():
        return False
    try:
        parsed = parse_trace_for_restore(tp.read_text(encoding="utf-8"))
    except ValueError:
        return False
    if not parsed.turns:
        return False
    rec = record_from_parsed_trace(parsed)
    apply_snapshot_to_session(ss, rec)
    save_conversation_record(rec)
    return True


def switch_to_chat(ss: Any, chat_id: str) -> bool:
    chat_id = (chat_id or "").strip()
    if not chat_id or chat_id == str(ss.get("jx_active_chat_id") or ""):
        return False
    persist_active_chat(ss)
    return _load_conversation_into_session(ss, chat_id)


def create_new_chat(ss: Any) -> str:
    persist_active_chat(ss)
    new_id = str(uuid.uuid4())
    ss.jx_active_chat_id = new_id
    ss.jx_trace_session_id = new_id
    ss.chat_messages = default_welcome_messages()
    ss.jx_shadow_messages = []
    ss.jx_trace_turn_index = 0
    ss.jx_kb_anchor_key = None
    ss.jx_kb_top2_hits = []
    ss.pop("_pending_active_exp_idx", None)
    save_conversation_record(snapshot_from_session(ss))
    return new_id


def ensure_chat_histories_initialized(ss: Any) -> None:
    """首次进入：若本机已有对话卡片则载入最近一条，否则创建新对话并落盘。"""
    active = str(ss.get("jx_active_chat_id") or "").strip()
    if active and (
        load_conversation_record(active) is not None
        or conversation_trace_path(active).is_file()
        or conversation_trace_legacy_md_path(active).is_file()
    ):
        _unify_conversation_id(ss)
        return

    cards = list_conversation_cards()
    if cards:
        apply_snapshot_to_session(ss, cards[0])
        return

    if not ss.get("chat_messages"):
        ss.chat_messages = default_welcome_messages()
    _unify_conversation_id(ss)
    if not ss.get("jx_shadow_messages"):
        ss.jx_shadow_messages = []
    save_conversation_record(snapshot_from_session(ss))


def sorted_histories(ss: Any) -> list[dict[str, Any]]:
    """兼容旧名：列表仅来自本机存储，与 session 无关。"""
    del ss
    return list_conversation_cards()
