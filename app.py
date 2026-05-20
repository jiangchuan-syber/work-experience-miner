# -*- coding: utf-8 -*-
"""
本地运行：pip install -r requirements.txt && streamlit run app.py

左侧：工作经历；底部：固定对话栏（输入条贴浏览器底）。
PDF：上传后自动抽字 / OCR / 去隐私 / 拆段与填字段。
侧栏：`app.py` 中渲染「API Key」「对话历史」；页头右上为「简历导入」「导出」；
DeepSeek **密钥 / 默认模型**请在项目根 `.env`（见 `.env.example`）维护。
"""
from __future__ import annotations

import html
import os
import uuid
from pathlib import Path
from typing import Any

import streamlit as st

from export_template import build_markdown_export
from knowledge import load_raw

from chat_trace import (
    is_chat_trace_enabled,
    summarize_kb_hits,
    trace_chat_blocked,
    trace_chat_turn,
    trace_kb_refresh,
    trace_session_start,
)
from chat_history import (
    create_new_chat,
    default_welcome_messages,
    ensure_chat_histories_initialized,
    list_conversation_cards,
    load_conversation_record,
    persist_active_chat,
    switch_to_chat,
)
from trace_restore import (
    ParsedTraceRestore,
    extract_raw_description_from_api_user,
    parse_trace_for_restore,
)

ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env"

try:
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)
except ImportError:
    pass


def merge_write_deepseek_env(
    path: Path,
    *,
    api_key: str,
    api_base: str,
    model: str,
) -> None:
    """更新或写入 `.env` 中的 DEEPSEEK_*，尽量保留其余行。"""
    b = (api_base or "").strip().rstrip("/") or "https://api.deepseek.com"
    m = (model or "").strip() or "deepseek-v4-flash"
    k = (api_key or "").strip()
    updates = {
        "DEEPSEEK_API_KEY": k,
        "DEEPSEEK_API_BASE": b,
        "DEEPSEEK_MODEL": m,
    }
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            var = stripped.split("=", 1)[0].strip()
            if var in updates:
                out.append(f"{var}={updates[var]}")
                seen.add(var)
                continue
        out.append(line)
    for var, val in updates.items():
        if var not in seen:
            out.append(f"{var}={val}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def apply_deepseek_from_ui() -> None:
    """把侧栏中的 API 配置同步到当前进程的 os.environ（本页立即生效）。"""
    k = (st.session_state.get("ds_api_key_ui") or "").strip()
    base = (st.session_state.get("ds_api_base_ui") or "").strip() or "https://api.deepseek.com"
    model = (st.session_state.get("ds_model_ui") or "").strip() or "deepseek-v4-flash"
    if k:
        os.environ["DEEPSEEK_API_KEY"] = k
    else:
        os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ["DEEPSEEK_API_BASE"] = base.rstrip("/")
    os.environ["DEEPSEEK_MODEL"] = model


st.set_page_config(page_title="工作经历挖掘", layout="wide", initial_sidebar_state="expanded")


st.markdown(
    """
<style>
    /* ── 极简浅色底，弱化 Streamlit 默认「卡片感」 ── */
    [data-testid="stAppViewContainer"] {
        background: #f6f7f9 !important;
        background-image: none !important;
    }
    [data-testid="stHeader"] {
        background: #f6f7f9 !important;
        border-bottom: none !important;
        box-shadow: none !important;
        overflow: visible !important;
    }
    header[data-testid="stHeader"] {
        min-height: 2.75rem !important;
    }
    /* 侧栏收起后靠顶栏按钮再展开；禁止 display:none 整条 stToolbar */
    [data-testid="stToolbar"] {
        visibility: visible !important;
        display: flex !important;
        z-index: 300 !important;
        pointer-events: auto !important;
    }
    [data-testid="stExpandSidebarButton"],
    [data-testid="collapsedControl"],
    button[data-testid="stBaseButton-headerNoPadding"] {
        display: inline-flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        z-index: 301 !important;
    }
    [data-testid="stToolbar"] [data-testid="stAppDeployButton"],
    button[data-testid="stAppDeployButton"] {
        display: none !important;
    }
    /* 中间栏可读宽度：大屏略放宽，小屏留白随视窗收缩 */
    .main .block-container {
        padding-top: 0.35rem !important;
        padding-bottom: calc(5.5rem + env(safe-area-inset-bottom)) !important;
        padding-left: clamp(1rem, 4vw, 2.25rem) !important;
        padding-right: clamp(1rem, 4vw, 2.25rem) !important;
        max-width: min(1240px, 100%);
        overflow-x: clip;
        overflow-y: visible !important;
    }
    /* 正文区 Markdown 段落默认间距；对话坞内由下方 .st-key-jx_chat_dock … 规则覆盖（更高特异） */
    div[data-testid="stMarkdownContainer"] p {
        margin-top: 0.2rem;
        margin-bottom: 0.5rem !important;
        line-height: 1.6 !important;
    }
    h1 {
        font-size: clamp(1.35rem, 2.5vw, 1.625rem) !important;
        font-weight: 600 !important;
        letter-spacing: -0.035em !important;
        color: #111827 !important;
        border-left: none !important;
        padding-left: 0 !important;
        margin-bottom: 0.08rem !important;
        line-height: 1.2 !important;
    }
    h3 {
        font-size: 0.9375rem !important;
        font-weight: 600 !important;
        color: #111827 !important;
        letter-spacing: -0.02em !important;
        margin: 0 0 0.35rem !important;
    }
    div[data-testid="stCaptionContainer"] {
        color: #9ca3af !important;
        font-size: 0.8125rem !important;
    }
    .jx-mini-notice {
        margin: 0.35rem 0;
        padding: 0.45rem 0.65rem;
        font-size: 0.8125rem;
        color: #4b5563;
        background: #fff;
        border-radius: 8px;
        border: 1px solid #eceef2;
    }
    section[data-testid="stSidebar"] > div:first-child {
        background: #f3f4f6 !important;
        border-right: 1px solid #e8eaef !important;
    }
    div[data-testid="stVerticalBlock"] > div[data-testid="stExpander"] {
        background: #fff !important;
        border: 1px solid #e8eaef !important;
        border-radius: 10px !important;
        margin-bottom: 0.45rem !important;
        box-shadow: none !important;
    }
    /* 仅置顶工具条（对话选用 / 栏目题），不包含下方展开卡片，避免整列贴屏过高 */
    .st-key-exp_sticky_header {
        position: sticky;
        top: 2.85rem;
        z-index: 80;
        background: rgba(246, 247, 249, 0.98) !important;
        backdrop-filter: blur(8px);
        padding-top: 0.2rem;
        padding-bottom: 0.55rem;
        margin-bottom: 0.35rem;
        border-bottom: 1px solid #e8eaef;
    }
    .st-key-exp_card_stack {
        position: relative;
        z-index: 1;
        margin-bottom: 0.35rem;
    }
    /* 对话消息区（可随页滚动） */
    .st-key-jx_chat_scroll {
        padding-bottom: calc(4.75rem + env(safe-area-inset-bottom)) !important;
        box-sizing: border-box !important;
        margin-top: 0.5rem;
    }
    /* 输入条：由 _pin_chat_input_bar 脚本对齐主栏宽度并 fixed 贴底；此处为兜底样式 */
    .st-key-jx_chat_input_bar {
        z-index: 200 !important;
        box-sizing: border-box !important;
        margin-top: 0.5rem !important;
        padding: 0.55rem clamp(1rem, 4vw, 2.25rem) calc(10px + env(safe-area-inset-bottom))
            clamp(1rem, 4vw, 2.25rem) !important;
        background: rgba(255, 255, 255, 0.98) !important;
        backdrop-filter: blur(10px);
        border-top: 1px solid #e8eaef;
        box-shadow: 0 -4px 24px rgba(15, 23, 42, 0.08);
    }
    .st-key-jx_chat_input_bar [data-testid="stChatInput"] {
        padding-left: 0 !important;
        padding-right: 0 !important;
    }

    [data-testid="stChatMessage"] { background-color: transparent !important; }
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] {
        max-width: 100%;
        align-items: flex-start !important;
    }

    /* 对话气泡 Markdown：中英文长回复时避免行距过挤、列表与标题摞在一起 */
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
        font-size: 0.9625rem !important;
        line-height: 1.65 !important;
    }
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
        margin: 0.45em 0 0.6em !important;
        line-height: 1.72 !important;
    }
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {
        margin: 0.35em 0 !important;
        line-height: 1.72 !important;
    }
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] ul,
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] ol {
        margin: 0.55em 0 0.75em !important;
        padding-left: 1.4rem !important;
    }
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h1,
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h2,
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h3,
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h4 {
        margin: 0.85em 0 0.45em !important;
        line-height: 1.35 !important;
        font-weight: 600 !important;
    }
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] strong {
        font-weight: 600 !important;
    }
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] pre,
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] pre {
        margin: 0.65em 0 !important;
        line-height: 1.5 !important;
        white-space: pre-wrap !important;
    }
    .st-key-jx_chat_scroll [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] blockquote {
        margin: 0.55em 0 !important;
        padding-left: 0.85rem !important;
        border-left: 3px solid #e5e7eb;
    }

    .st-key-jx_chat_input_bar div[data-testid="stChatInput"] textarea {
        border-radius: 11px !important;
        font-size: 0.9625rem !important;
        line-height: 1.45 !important;
        min-height: 3.125rem !important;
        padding-top: 0.65rem !important;
        padding-bottom: 0.65rem !important;
    }

    .st-key-jx_chat_input_bar div[data-testid="stChatInput"] {
        min-height: 3.125rem !important;
    }

    .st-key-jx_chat_input_bar div[data-testid="stChatInput"] textarea:focus {
        min-height: 3.5rem !important;
    }

    /* 侧栏对话历史：不单独设 max-height/overflow，随 Streamlit 侧栏整体滚动 */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
        gap: 0.35rem !important;
    }
    section[data-testid="stSidebar"] h5 {
        font-size: 0.9rem !important;
        margin: 0 0 0.25rem !important;
    }
    div[data-testid="stButton"] > button.jx-hist-active {
        border-color: #b91c1c !important;
        background: #fef2f2 !important;
        color: #991b1b !important;
        font-weight: 600 !important;
    }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def cached_job_kb_index() -> Any:
    from rag.embed_store import JobKBIndex

    return JobKBIndex()


def rebuild_job_kb_index(idx: Any) -> int:
    from rag.chunking import load_rag_chunks

    return idx.rebuild(load_rag_chunks())


def _ensure_rag_kb_rebuilt_this_session() -> None:
    """本会话首次进入页面时：从磁盘 Markdown 重建岗位知识向量索引，检索与仓库内知识库对齐。"""
    if st.session_state.get("_jx_rag_kb_init_done"):
        return
    with st.spinner("正在从磁盘重建岗位知识库向量索引…"):
        try:
            kb = cached_job_kb_index()
            st.session_state["_jx_kb_chunk_count"] = rebuild_job_kb_index(kb)
            st.session_state.pop("_jx_kb_rebuild_err", None)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)[:380]
            st.session_state["_jx_kb_rebuild_err"] = msg
            _toast = getattr(st, "toast", None)
            if callable(_toast):
                _toast("岗位知识索引重建失败，对话检索可能不可用：" + msg, icon="⚠️")
            else:
                st.warning("岗位知识索引重建失败：" + msg)
    st.session_state["_jx_rag_kb_init_done"] = True


def _warm_rag_retrieval_once_per_session() -> None:
    """预热句向量检索（不写 session）；不与「按经历的 top-2 缓存」重复做 rerank。"""
    if st.session_state.get("_jx_rag_warm_retrieval_done"):
        return
    st.session_state["_jx_rag_warm_retrieval_done"] = True
    try:
        kb = cached_job_kb_index()
        if kb.count() <= 0:
            return
        kb.search_one("岗位实习 职责 产出", top_k=1)
    except Exception:  # noqa: BLE001
        pass


def _slim_rag_hit(h: dict[str, Any]) -> dict[str, Any]:
    """仅保留可序列化、供 UI 外状态与 prompt 使用的字段。"""
    meta = h.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    safe_meta: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            safe_meta[str(k)] = v
        else:
            safe_meta[str(k)] = str(v)
    return {
        "document": str(h.get("document") or ""),
        "metadata": safe_meta,
        "rerank_score": h.get("rerank_score"),
    }


def _job_kb_anchor_key() -> tuple[int, str] | None:
    exps = st.session_state.get("experiences") or []
    if not exps:
        return None
    idx = effective_active_exp_index()
    if idx < 0 or idx >= len(exps):
        return None
    return (idx, str(exps[idx].get("_id") or ""))


def refresh_job_kb_for_active_if_needed(*, show_spinner: bool = False) -> None:
    """
    切换「对话选用」或「设为对话」后：仅按当前经历的岗位/组织等做检索与 rerank，
    保留 top-2 写入 session；并清空多轮 API 影子历史（首轮重新注入知识节选）。
    """
    anchor = _job_kb_anchor_key()
    if anchor is None:
        st.session_state.jx_kb_top2_hits = []
        st.session_state.jx_kb_anchor_key = None
        return
    if st.session_state.get("jx_kb_anchor_key") == anchor:
        return

    st.session_state.jx_shadow_messages = []

    def _retrieve_top2() -> list[dict[str, Any]]:
        slim: list[dict[str, Any]] = []
        try:
            kb_idx = cached_job_kb_index()
            if kb_idx.count() > 0:
                idx_a, _eid = anchor
                exp = st.session_state.experiences[idx_a]
                c = (exp.get("company") or "").strip()
                r = (exp.get("role") or "").strip()
                p = (exp.get("period") or "").strip()
                d = (exp.get("raw_description") or "").strip()
                match_blob = (
                    f"岗位：{r}\n组织：{c}\n时间段：{p}\n简述：{(d.strip()[:500])}".strip()
                )
                from rag.retrieve import retrieve_with_rewrite_rerank

                raw, _, _ = retrieve_with_rewrite_rerank(
                    kb_idx,
                    "",
                    user_answer="",
                    student_track="",
                    job_role=r,
                    company=c,
                    experience_snippet=match_blob or f"岗位：{r} 实习 评价维度",
                    final_k=2,
                    top_k_per_query=8,
                    rrf_top_n=24,
                    max_queries=6,
                    do_rerank=True,
                )
                slim = [_slim_rag_hit(x) for x in raw[:2]]
        except Exception:  # noqa: BLE001
            slim = []
        return slim

    if show_spinner:
        with st.spinner("正在为当前经历匹配岗位知识（top-2）…"):
            slim_done = _retrieve_top2()
    else:
        slim_done = _retrieve_top2()

    st.session_state.jx_kb_top2_hits = slim_done
    st.session_state.jx_kb_anchor_key = anchor
    if is_chat_trace_enabled():
        sid_kb = str(st.session_state.get("jx_trace_session_id") or "")
        idx_kb, exp_id_kb = anchor
        exp_row = st.session_state.experiences[idx_kb]
        trace_kb_refresh(
            sid_kb,
            {
                "experience_index": idx_kb,
                "experience_id": exp_id_kb,
                "company": (exp_row.get("company") or "").strip(),
                "role": (exp_row.get("role") or "").strip(),
                "hits_outline": summarize_kb_hits(slim_done),
                "hits": slim_done,
            },
        )


DEFAULT_EXP: dict[str, Any] = {
    "_id": "",
    "company": "",
    "role": "",
    "period": "",
    "raw_description": "",
}


def new_experience_row() -> dict[str, Any]:
    row = {**DEFAULT_EXP, "_id": str(uuid.uuid4())}
    return row


def apply_trace_restore_to_session(ss: Any, parsed: ParsedTraceRestore) -> str:
    """用解析结果覆盖对话 UI、jx_shadow_messages、轮次计数；对齐或补全经历条目；作废 KB 缓存以触发下一轮重建。"""
    turns = sorted(parsed.turns, key=lambda t: t.turn_index)
    if not turns:
        raise ValueError("没有有效轮次")

    chat_pairs: list[dict[str, str]] = []
    shadow: list[dict[str, str]] = []
    for pt in turns:
        chat_pairs.append({"role": "user", "content": pt.display_user})
        chat_pairs.append({"role": "assistant", "content": pt.api_assistant})
        shadow.append({"role": "user", "content": pt.api_user_message})
        shadow.append({"role": "assistant", "content": pt.api_assistant})

    ss.chat_messages = chat_pairs
    ss.jx_shadow_messages = shadow
    ss.jx_trace_turn_index = len(turns)
    ss.jx_kb_anchor_key = None
    ss.jx_kb_top2_hits = []

    last = turns[-1].experience_snapshot
    eid = (last.get("experience_id") or "").strip()
    idx_txt = last.get("experience_index", "")
    try:
        idx_snap = int(idx_txt) if str(idx_txt).strip() != "" else 0
    except ValueError:
        idx_snap = 0

    exps: list[dict[str, Any]] = ss.experiences
    picked: int | None = None
    if eid:
        for j, er in enumerate(exps):
            if str(er.get("_id") or "") == eid:
                picked = j
                break
    if picked is None and 0 <= idx_snap < len(exps):
        picked = idx_snap

    raw_guess = (last.get("raw_description") or "").strip()
    if not raw_guess and turns:
        raw_guess = extract_raw_description_from_api_user(turns[0].api_user_message)

    if picked is not None:
        ss.active_exp_index = picked
        er = exps[picked]
        if last.get("company") is not None:
            er["company"] = str(last.get("company") or "")
        if last.get("role") is not None:
            er["role"] = str(last.get("role") or "")
        if last.get("period") is not None:
            er["period"] = str(last.get("period") or "")
        if eid:
            er["_id"] = eid
        if raw_guess and not (str(er.get("raw_description") or "").strip()):
            er["raw_description"] = raw_guess
    else:
        row = new_experience_row()
        if eid:
            row["_id"] = eid
        row["company"] = str(last.get("company") or "")
        row["role"] = str(last.get("role") or "")
        row["period"] = str(last.get("period") or "")
        row["raw_description"] = raw_guess
        exps.append(row)
        ss.active_exp_index = len(exps) - 1

    if parsed.trace_session_id:
        tid = str(parsed.trace_session_id).strip()
        ss.jx_trace_session_id = tid
        ss.jx_active_chat_id = tid

    ss.pop("_pending_active_exp_idx", None)
    persist_active_chat(ss)
    return f"已从 trace 恢复 {len(turns)} 轮；当前对话选用索引：{int(ss.active_exp_index)}。"


def sync_active_exp_index_pre_widget() -> None:
    """仅在「绑定 key=active_exp_index」的控件渲染之前写入 session_state。"""
    exps = st.session_state.get("experiences") or []
    n = len(exps)
    pend = st.session_state.pop("_pending_active_exp_idx", None)
    if pend is not None:
        st.session_state.active_exp_index = 0 if n <= 0 else max(0, min(int(pend), n - 1))
        return
    if n <= 0:
        st.session_state.active_exp_index = 0
        return
    idx = int(st.session_state.get("active_exp_index") or 0)
    if idx < 0 or idx >= n:
        st.session_state.active_exp_index = max(0, min(idx, n - 1))


def effective_active_exp_index() -> int:
    """只读裁剪：不在此处写 session_state（避免与已与 widget 绑定的 key 冲突）。"""
    exps = st.session_state.get("experiences") or []
    n = len(exps)
    if n <= 0:
        return 0
    idx = int(st.session_state.get("active_exp_index") or 0)
    return max(0, min(idx, n - 1))


def experience_short_label(i: int, exp: dict[str, Any], *, max_len: int = 22) -> str:
    co = (exp.get("company") or "").strip() or "未填公司"
    ro = (exp.get("role") or "").strip()
    base = f"{i + 1}·{co}"
    if ro:
        base += f"·{ro}"
    if len(base) > max_len:
        return base[: max_len - 1] + "…"
    return base


def init_state() -> None:
    if "experiences" not in st.session_state:
        st.session_state.experiences = [new_experience_row()]
    st.session_state.pop("student_type", None)
    if "_pdf_auto_sig" not in st.session_state:
        st.session_state._pdf_auto_sig = None
    if "jx_shadow_messages" not in st.session_state:
        st.session_state.jx_shadow_messages = []
    if "jx_kb_top2_hits" not in st.session_state:
        st.session_state.jx_kb_top2_hits = []
    if "jx_kb_anchor_key" not in st.session_state:
        st.session_state.jx_kb_anchor_key = None
    if "jx_trace_session_id" not in st.session_state:
        st.session_state.jx_trace_session_id = str(uuid.uuid4())
    if "jx_trace_turn_index" not in st.session_state:
        st.session_state.jx_trace_turn_index = 0
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = default_welcome_messages()
    if "jx_active_chat_id" not in st.session_state:
        st.session_state.jx_active_chat_id = str(uuid.uuid4())
    ensure_chat_histories_initialized(st.session_state)
    for row in st.session_state.experiences:
        if not row.get("_id"):
            row["_id"] = str(uuid.uuid4())

    if "ds_api_key_ui" not in st.session_state:
        st.session_state.ds_api_key_ui = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if "ds_api_base_ui" not in st.session_state:
        st.session_state.ds_api_base_ui = (
            (os.environ.get("DEEPSEEK_API_BASE") or "").strip() or "https://api.deepseek.com"
        )
    if "ds_model_ui" not in st.session_state:
        st.session_state.ds_model_ui = (
            (os.environ.get("DEEPSEEK_MODEL") or "").strip() or "deepseek-v4-flash"
        )
    if "active_exp_index" not in st.session_state:
        legacy = st.session_state.pop("chat_focus_exp_index", 0)
        st.session_state.active_exp_index = int(legacy) if legacy is not None else 0
    st.session_state.pop("chat_focus_exp_index", None)
    if not st.session_state.get("_jx_trace_logged_session_start"):
        if is_chat_trace_enabled():
            trace_session_start(
                str(st.session_state.jx_trace_session_id),
                meta={"app": "工作经历挖掘 streamlit"},
            )
        st.session_state._jx_trace_logged_session_start = True
    sync_active_exp_index_pre_widget()


init_state()
_ensure_rag_kb_rebuilt_this_session()
_warm_rag_retrieval_once_per_session()

raw_md = load_raw()

with st.sidebar:
    st.text_input(
        "API Key",
        type="password",
        key="ds_api_key_ui",
        placeholder="sk-…",
        help="DeepSeek 开放平台密钥；页面刷新或交互后会自动带入当前会话环境。API 地址与模型请在根目录 `.env` 配置。",
    )


apply_deepseek_from_ui()

_key_ok = bool((os.environ.get("DEEPSEEK_API_KEY") or "").strip())

exps_main: list[dict[str, Any]] = st.session_state.experiences
sync_active_exp_index_pre_widget()
refresh_job_kb_for_active_if_needed(show_spinner=True)
_n_exp = len(exps_main)
_export_md = build_markdown_export(
    experiences=st.session_state.experiences,  # type: ignore[arg-type]
    kb_hint=raw_md[:5000],
)

_hdr_title, _hdr_actions = st.columns([4, 2], vertical_alignment="center")
with _hdr_title:
    st.title("工作经历挖掘")
with _hdr_actions:
    _hdr_import, _hdr_export = st.columns(2, gap="small")
    with _hdr_import:
        with st.popover("简历导入", use_container_width=True, help="上传 PDF，自动 OCR 并拆分经历卡片"):
            _resume_pdf = st.file_uploader(
                "选择 PDF 简历",
                type=["pdf"],
                key="resume_pdf_uploader",
                help="200MB 以内 · 上传后自动解析",
            )
    with _hdr_export:
        st.download_button(
            "导出",
            data=_export_md.encode("utf-8"),
            file_name="工作经历挖掘导出.md",
            mime="text/markdown; charset=utf-8",
            key="header_export_md",
            use_container_width=True,
            help="导出当前全部经历与整理结果为 Markdown",
        )

if _resume_pdf is not None:
    sig = (_resume_pdf.name, len(_resume_pdf.getvalue() or b""))
    if st.session_state.get("_pdf_auto_sig") != sig:
        from resume_pipeline import (
            process_pdf_bytes_to_experiences,
            should_replace_default_experiences,
        )

        with st.spinner("正在解析 PDF（必要时 OCR）并拆分经历…"):
            pdf_bytes = _resume_pdf.getvalue()
            rows, meta = process_pdf_bytes_to_experiences(
                pdf_bytes, prefer_llm=_key_ok
            )
        st.session_state._pdf_auto_sig = sig
        st.session_state._pdf_last_meta = meta
        if rows:
            if should_replace_default_experiences(st.session_state.experiences):
                st.session_state.experiences = rows
                st.session_state._pending_active_exp_idx = 0
            else:
                start_len = len(st.session_state.experiences)
                st.session_state.experiences.extend(rows)
                st.session_state._pending_active_exp_idx = start_len
            method = meta.get("extract_method", "")
            n_pdf = len(rows)
            st.session_state["parse_notice"] = (
                f"已从 PDF 生成 {n_pdf} 段经历卡片（{method}）。可在主区核对、编辑。"
            )
        else:
            note = meta.get("note", "未能得到经历条目。")
            st.session_state["parse_notice"] = f"PDF 解析未完成：{note}"
        st.rerun()


def _header_status_caption(*, key_ok: bool) -> str:
    parts: list[str] = []
    if key_ok:
        parts.append("对话已就绪")
    else:
        parts.append("未配置 API · 侧栏填 Key 或 `.env` 配置后可与模型对话")
    if exps_main:
        idx = effective_active_exp_index()
        e = exps_main[idx]
        co = (e.get("company") or "").strip() or "未填公司"
        ro = (e.get("role") or "").strip()
        seg = f"当前对话：第 {idx + 1} 段 · {co}"
        if ro:
            seg += f" · {ro}"
        parts.append(seg)
    else:
        parts.append("请先导入或添加一段经历")
    return " · ".join(parts)


st.caption(_header_status_caption(key_ok=_key_ok))
with st.expander("使用说明", expanded=False):
    st.markdown(
        "- **API / 会话**：侧栏填密钥、切换「对话历史」；页头 **简历导入** 上传 PDF；侧栏收起后点左上角 **⟩** 展开\n"
        "- **环境变量**：亦可在项目根 `.env` 配置 `DEEPSEEK_API_KEY`\n"
        "- **岗位知识**：在上方切换「对话选用」的经历后，会自动匹配岗位知识；同一段对话里只在第一轮附带知识节选\n"
        "- **索引**：刷新页面时会重建本地知识库索引，首次可能稍慢"
    )

_sn = st.session_state.pop("parse_notice", None)
if _sn:
    _toast = getattr(st, "toast", None)
    if callable(_toast):
        _toast(_sn)
    else:
        st.markdown(
            '<p class="jx-mini-notice">' + html.escape(str(_sn)) + "</p>",
            unsafe_allow_html=True,
        )


def _chat_reply(user_text: str, *, key_ok: bool, focus_idx: int) -> str:
    from deepseek_api import deepseek_chat_conversation
    from rag.dialogue_guide import build_llm_user_message, load_system_prompt

    sid = str(st.session_state.get("jx_trace_session_id") or "")

    if not key_ok:
        if sid and is_chat_trace_enabled():
            trace_chat_blocked(sid, reason_code="missing_api_key", detail="DEEPSEEK_API_KEY 未配置")
        return (
            "未检测到可用的 DeepSeek API Key。"
            "请在项目根目录的 `.env` 中配置 `DEEPSEEK_API_KEY`，然后重新刷新本页。"
        )

    exps = st.session_state.experiences
    if not exps:
        if sid and is_chat_trace_enabled():
            trace_chat_blocked(sid, reason_code="no_experiences", detail="工作经历列表为空")
        return "当前没有任何经历条目，请用页头「简历导入」上传 PDF，或点击「管理经历」添加后再提问。"

    idx = max(0, min(focus_idx, len(exps) - 1))
    exp = exps[idx]
    c = (exp.get("company") or "").strip()
    r = (exp.get("role") or "").strip()
    p = (exp.get("period") or "").strip()
    d = (exp.get("raw_description") or "").strip()
    blob = f"【当前选中经历 #{idx + 1}】{c} · {r} · {p}\n{d}".strip()[:4000]
    role_hint = r
    system = load_system_prompt()
    cached_hits: list[dict[str, Any]] = list(st.session_state.get("jx_kb_top2_hits") or [])
    shadow: list[dict[str, Any]] = list(st.session_state.get("jx_shadow_messages") or [])
    first_kb_turn = len(shadow) == 0
    shadow_snapshot = [
        {"role": str(m.get("role") or ""), "content": str(m.get("content") or "")}
        for m in shadow
        if (m.get("role") or "") in ("user", "assistant") and str(m.get("content") or "").strip()
    ]
    experience_snapshot = {
        "experience_index": idx,
        "experience_id": str(exp.get("_id") or ""),
        "company": c,
        "role": r,
        "period": p,
        "raw_description": d,
        "raw_description_chars": len(d),
    }
    ds_model_trace = ((os.environ.get("DEEPSEEK_MODEL") or "").strip()) or "deepseek-v4-flash"

    if first_kb_turn:
        task_hint_init = (
            "请按对话引导文档的风格回应：先倾听、少评判，用澄清式提问帮用户回忆细节；"
            "结合下方「岗位知识库节选」（至多 2 条）中与用户经历相关的差异化指标给出改写方向。不要编造用户未说的事实。"
        )
        user_payload = build_llm_user_message(
            user_text,
            cached_hits,
            experience_snippet=blob,
            job_role=role_hint,
            task_hint=task_hint_init,
            include_rag_kb=True,
            include_experience_snippet=True,
        )
        if not cached_hits:
            user_payload += (
                "\n\n（说明：本段经历暂未从岗位知识库中匹配到条目。请确认索引已建好，并可回到经历卡补充岗位/原文后再切换一次「对话选用」重试检索。）"
            )
    else:
        task_hint_follow = (
            "延续上一轮已给出的本条经历摘录与岗位知识节选（你已在上文中收到）；"
            "仅针对用户本条新问题回应，可作澄清提问或改写补充；不要编造事实。"
        )
        user_payload = build_llm_user_message(
            user_text,
            [],
            experience_snippet="",
            job_role="",
            task_hint=task_hint_follow,
            include_rag_kb=False,
            include_experience_snippet=False,
        )

    temp = 0.55
    try:
        reply = deepseek_chat_conversation(
            system,
            shadow,
            user_payload,
            temperature=temp,
        )
    except Exception as e:  # noqa: BLE001
        if sid and is_chat_trace_enabled():
            trace_chat_blocked(
                sid,
                reason_code="chat_api_exception",
                detail=f"{type(e).__name__}: {e}",
            )
        return f"调用模型失败：{e}"
    shadow.append({"role": "user", "content": user_payload})
    shadow.append({"role": "assistant", "content": reply})
    st.session_state.jx_shadow_messages = shadow

    if sid and is_chat_trace_enabled():
        st.session_state.jx_trace_turn_index = int(st.session_state.jx_trace_turn_index or 0) + 1
        tin = int(st.session_state.jx_trace_turn_index)
        trace_chat_turn(
            sid,
            turn_index=tin,
            experience_snapshot=experience_snapshot,
            display_user=user_text or "",
            api_shadow_prior=shadow_snapshot,
            api_user_payload=user_payload,
            api_assistant=str(reply),
            system_prompt=system,
            temperature=temp,
            first_kb_turn=first_kb_turn,
            kb_hits=cached_hits,
            kb_outline=summarize_kb_hits(cached_hits),
            model=ds_model_trace,
        )

    return reply


def _experience_card_title(i: int, exp: dict[str, Any]) -> str:
    co = (exp.get("company") or "").strip() or "未填公司"
    ro = (exp.get("role") or "").strip()
    p = (exp.get("period") or "").strip()
    bits = [f"{i + 1} · {co}"]
    if ro:
        bits.append(ro[:18] + ("…" if len(ro) > 18 else ""))
    if p:
        bits.append(p)
    s = " · ".join(bits)
    return s[:56] + ("…" if len(s) > 56 else "")


def _render_experience_card(i: int, exp: dict[str, Any]) -> None:
    eid = str(exp.get("_id", i))
    exp["raw_description"] = st.text_area(
        "原文",
        value=exp.get("raw_description", ""),
        height=200,
        key=f"desc_{eid}",
        placeholder="粘贴简历段落…",
    )
    g1, g2 = st.columns(2)
    with g1:
        exp["company"] = st.text_input("公司", value=exp.get("company", ""), key=f"company_{eid}")
    with g2:
        exp["role"] = st.text_input("岗位", value=exp.get("role", ""), key=f"role_{eid}")
    exp["period"] = st.text_input(
        "时间",
        value=exp.get("period", ""),
        key=f"period_{eid}",
        placeholder="2024.06–2024.09",
    )


def _render_chat_history_panel(*, in_sidebar: bool = False) -> None:
    st.markdown("##### 对话历史")
    if in_sidebar:
        st.caption("本机已保存；点选切换会话。")
    else:
        st.caption("每条卡片对应本机一条已保存对话。")
    if st.button("＋ 新对话", key="jx_new_chat_btn", use_container_width=True, type="primary"):
        create_new_chat(st.session_state)
        if is_chat_trace_enabled():
            trace_session_start(
                str(st.session_state.jx_trace_session_id),
                meta={"app": "工作经历挖掘 streamlit"},
            )
        st.rerun()

    active_id = str(st.session_state.get("jx_active_chat_id") or "")
    cards = list_conversation_cards()
    if not cards:
        st.caption("暂无本地对话记录。")
        return

    for rec in cards:
        hid = str(rec.get("id") or "")
        if not hid:
            continue
        title = str(rec.get("title") or "对话")
        preview = str(rec.get("preview") or "")
        n_turn = int(rec.get("turn_count") or 0)
        storage = str(rec.get("storage") or "json")
        tip = f"{preview} · {n_turn} 轮"
        if storage == "trace" and not load_conversation_record(hid):
            tip += " · 仅 trace"
        is_active = hid == active_id
        if st.button(
            ("● " if is_active else "") + title,
            key=f"jx_hist_{hid}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
            help=tip,
        ):
            if switch_to_chat(st.session_state, hid):
                st.rerun()


@st.fragment
def _render_chat_messages() -> None:
    with st.container(border=False, key="jx_chat_scroll"):
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])


def _pin_chat_input_bar() -> None:
    """将输入条 fixed 到视口底，宽度与主内容区（侧栏右侧）对齐。"""
    import streamlit.components.v1 as components

    components.html(
        """
        <script>
        (function () {
          const doc = window.parent.document;
          function apply() {
            const main = doc.querySelector('section[data-testid="stMain"]');
            const bar = doc.querySelector('.st-key-jx_chat_input_bar');
            if (!main || !bar) return;
            const r = main.getBoundingClientRect();
            bar.style.setProperty('position', 'fixed', 'important');
            bar.style.setProperty('bottom', '0', 'important');
            bar.style.setProperty('left', r.left + 'px', 'important');
            bar.style.setProperty('width', r.width + 'px', 'important');
            bar.style.setProperty('z-index', '200', 'important');
            bar.style.setProperty('box-sizing', 'border-box', 'important');
          }
          apply();
          const main = doc.querySelector('section[data-testid="stMain"]');
          if (main) new ResizeObserver(apply).observe(main);
          window.parent.addEventListener('resize', apply);
          new MutationObserver(apply).observe(doc.body, {
            subtree: true,
            attributes: true,
            attributeFilter: ['style', 'class', 'aria-expanded'],
          });
        })();
        </script>
        """,
        height=0,
    )


def _render_chat_input_bar(*, key_ok: bool) -> None:
    idx = effective_active_exp_index()
    with st.container(key="jx_chat_input_bar"):
        if prompt := st.chat_input("输入消息，与 AI 一起挖掘、润色经历…"):
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            with st.spinner("思考中…"):
                reply = _chat_reply(prompt, key_ok=key_ok, focus_idx=idx)
            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
            persist_active_chat(st.session_state)
            st.rerun()
    _pin_chat_input_bar()


with st.sidebar:
    st.divider()
    _render_chat_history_panel(in_sidebar=True)
    st.divider()
    with st.expander("高级 · 调试", expanded=False):
        st.caption("从本地 trace 还原对话与会话上下文（开发排错用）")
        st.text_input(
            "相对路径（在项目根目录下）",
            value="",
            placeholder="local_chat_traces/trace_xxx.json",
            key="jx_trace_restore_path_ui",
            help="亦可在下方上传；二选一生效。路径须在本项目目录内。支持旧版 .md。",
        )
        _trace_up = st.file_uploader(
            "或上传 trace_{会话}.json / .md",
            type=["json", "md"],
            key="jx_trace_restore_upload",
        )
        if st.button("恢复对话", key="jx_trace_restore_run", use_container_width=True):
            text: str | None = None
            if _trace_up is not None:
                text = _trace_up.getvalue().decode("utf-8")
            else:
                rel = str(st.session_state.get("jx_trace_restore_path_ui") or "").strip()
                if not rel:
                    st.sidebar.error("请填写路径或上传文件。")
                else:
                    cand = (ROOT_DIR / rel.replace("\\", "/").lstrip("/")).resolve()
                    try:
                        cand.relative_to(ROOT_DIR.resolve())
                    except ValueError:
                        st.sidebar.error("路径必须位于本项目目录内。")
                    else:
                        if not cand.is_file():
                            st.sidebar.error(f"找不到文件：{cand}")
                        else:
                            text = cand.read_text(encoding="utf-8")
            if text:
                try:
                    pr = parse_trace_for_restore(text)
                    st.sidebar.success(apply_trace_restore_to_session(st.session_state, pr))
                    st.rerun()
                except Exception as ex:  # noqa: BLE001
                    st.sidebar.error(str(ex))

with st.container(key="exp_sticky_header"):
    _elist = st.session_state.experiences
    if _n_exp > 1:
        _exp_opts = list(range(_n_exp))
        if _n_exp <= 5:
            st.segmented_control(
                "对话选用",
                options=_exp_opts,
                format_func=lambda x: experience_short_label(x, exps_main[x]),
                key="active_exp_index",
            )
        else:
            st.selectbox(
                "对话选用",
                options=_exp_opts,
                format_func=lambda x: experience_short_label(x, exps_main[x], max_len=48),
                key="active_exp_index",
            )
    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown("##### 工作经历")
        st.caption("展开下方卡片可编辑；多段时在上方切换「对话选用」。")
    with h2:
        with st.popover("管理经历", use_container_width=True):
            if st.button("添加一段", key="popover_add_exp", use_container_width=True):
                st.session_state.experiences.append(new_experience_row())
                st.session_state._pending_active_exp_idx = len(st.session_state.experiences) - 1
                st.rerun()
            ii = effective_active_exp_index()
            if st.button(
                "删除本条",
                key="popover_rem_exp",
                use_container_width=True,
                disabled=len(st.session_state.experiences) <= 1,
            ):
                st.session_state.experiences.pop(ii)
                nn = len(st.session_state.experiences)
                st.session_state._pending_active_exp_idx = 0 if nn <= 0 else min(ii, nn - 1)
                st.rerun()

if not _elist:
    st.info(
        '暂无经历。请使用侧栏「简历导入」，或点击「管理经历」添加一段。',
    )
else:
    _act_idx = effective_active_exp_index()
    with st.container(key="exp_card_stack"):
        for _j, _exp_row in enumerate(_elist):
            with st.expander(
                _experience_card_title(_j, _exp_row),
                expanded=(_j == _act_idx),
            ):
                _render_experience_card(_j, _exp_row)

_render_chat_messages()
_render_chat_input_bar(key_ok=_key_ok)
