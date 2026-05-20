# -*- coding: utf-8 -*-
"""
简历 PDF：文本层 → 弱文档时用 PaddleOCR（可回退 Tesseract）→ 去噪 → 多段拆分 → 字段填充。
配置 DeepSeek 时优先 API 拆分与补字段。
"""
from __future__ import annotations

import io
import json
import os
import re
import uuid
from typing import Any

from experience_extract import extract_fields, extract_with_rules


def _ocr_pages_paddle(doc: Any) -> str:
    from PIL import Image

    from paddle_ocr_util import image_to_text_paddle

    chunks: list[str] = []
    for i in range(len(doc)):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=200, alpha=False)
        pil = Image.open(io.BytesIO(pix.tobytes("png")))
        chunks.append(image_to_text_paddle(pil))
    return "\n".join(chunks).strip()


def _ocr_pages_tesseract(doc: Any) -> str:
    import pytesseract
    from PIL import Image

    chunks: list[str] = []
    for i in range(len(doc)):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=200, alpha=False)
        pil = Image.open(io.BytesIO(pix.tobytes("png")))
        chunks.append(pytesseract.image_to_string(pil, lang="chi_sim+eng"))
    return "\n".join(chunks).strip()


def extract_pdf_bytes(
    data: bytes,
    *,
    min_chars_per_page: int = 35,
) -> tuple[str, str]:
    """
    返回 (全文, 方法标签)。
    默认识别引擎：PaddleOCR；环境变量 OCR_ENGINE=tesseract 可强制仅用 Tesseract。
    """
    import fitz  # PyMuPDF

    engine_pref = (os.environ.get("OCR_ENGINE") or "paddle").strip().lower()

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        n = len(doc)
        page_texts: list[str] = []
        for i in range(n):
            page_texts.append((doc.load_page(i).get_text("text") or "").strip())
        joined = "\n".join(page_texts).strip()
        avg = len(joined) / max(n, 1)

        if avg >= float(min_chars_per_page) and len(joined) > 40:
            return joined, "pdf_text_layer"

        ocr_parts: list[str] = []
        methods: list[str] = []

        if engine_pref != "tesseract":
            try:
                paddle_txt = _ocr_pages_paddle(doc)
                if paddle_txt.strip():
                    ocr_parts.append(paddle_txt)
                    methods.append("paddle")
            except Exception as e:  # noqa: BLE001
                methods.append(f"paddle_err:{str(e)[:80]}")

        if engine_pref == "tesseract" or not ocr_parts:
            try:
                tess_txt = _ocr_pages_tesseract(doc)
                if tess_txt.strip():
                    ocr_parts.append(tess_txt)
                    methods.append("tesseract")
            except Exception as e:  # noqa: BLE001
                methods.append(f"tesseract_err:{str(e)[:80]}")

        ocr_text = "\n".join(ocr_parts).strip()
        tag = "+".join(methods) if methods else "ocr_none"

        if len(ocr_text) >= len(joined) and ocr_text:
            return ocr_text, f"ocr_{tag}"
        if ocr_text and joined:
            return (joined + "\n" + ocr_text).strip(), f"pdf_text+{tag}"
        if ocr_text:
            return ocr_text, f"ocr_{tag}"
        if joined:
            return joined, f"pdf_text_layer_ocr_empty({tag})"
        return "（未能从 PDF 提取有效文字，请检查是否需安装 paddlepaddle / PaddleOCR）", "ocr_fail"
    finally:
        doc.close()


_NOISE_START = (
    "姓名",
    "性别",
    "年龄",
    "出生",
    "民族",
    "籍贯",
    "政治面貌",
    "入党",
    "共青团",
    "电话",
    "手机",
    "联系电话",
    "Tel",
    "微信",
    "邮箱",
    "Email",
)
_NOISE_BLOCK = (
    "地址",
    "现居",
    "身高",
    "体重",
    "身份证",
    "求职意向",
    "期望薪资",
    "期望职位",
    "期望城市",
    "到岗时间",
)


def strip_personal_noise(text: str) -> str:
    """删除简历中与「经历描述」无关的基础信息行与常见隐私模式。"""
    raw_lines: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            raw_lines.append("")
            continue
        if len(s) < 100:
            if any(s.startswith(k) or s.startswith(k + "：") or s.startswith(k + ":") for k in _NOISE_START):
                continue
            if any((k in s[:8] or s.startswith(k + "：") or s.startswith(k + ":")) for k in _NOISE_BLOCK):
                continue
        if re.fullmatch(r"[\d\s\-\+\(\)（）]{7,}", s) and re.search(r"1[3-9]\d{9}", s):
            continue
        if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", s) and len(s) < 120 and s.count("@") == 1:
            continue
        raw_lines.append(line)

    t = "\n".join(raw_lines)
    t = re.sub(r"1[3-9]\d{9}", "", t)
    t = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _is_toc_or_nav_noise(t: str) -> bool:
    s = (t or "").strip()
    if not s:
        return True
    if len(s) < 120 and s.count("/") >= 2 and all(
        k in s for k in ("实习", "教育", "自我")
    ):
        return True
    if re.fullmatch(r"[\s\u4e00-\u9fff/·\-—]{5,120}", s) and "经历" in s:
        return True
    return False


def _work_region(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    markers = (
        "实习经历",
        "工作经历",
        "工作/实习",
        "实习/工作",
        "实践经历",
        "工作经验",
        "职业经历",
    )
    best_start = -1
    for m in markers:
        idx = t.find(m)
        if idx >= 0 and (best_start < 0 or idx < best_start):
            best_start = idx
    if best_start >= 0:
        t = t[best_start:]
    end_pat = re.compile(
        r"\n\s*(教育背景|教育经历|在校经历|项目经历|项目经验|专业技能|"
        r"技能特长|荣誉|证书|自我评价|兴趣爱好)\s*[:：]?"
    )
    mm = end_pat.search(t[10:])
    if mm:
        t = t[: mm.start() + 10].strip()
    return t.strip() or (text or "").strip()


def work_text_for_llm(cleaned_full: str) -> str:
    """截取实习/工作区块；若像目录或未截到实质内容则用全文供模型判断。"""
    work = _work_region(cleaned_full)
    if len(work.strip()) < 80 or _is_toc_or_nav_noise(work):
        return cleaned_full.strip()
    return work.strip()


def _split_heuristic(work_text: str) -> list[str]:
    t = work_text.strip()
    if not t:
        return []
    parts = re.split(
        r"\n(?=(?:(?:\d+|[一二三四五六七八九十]+)[、.．]\s*)"
        r".{0,30}?(?:公司|实习|兼职|任职|工作))",
        t,
    )
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        parts = re.split(r"\n{2,}", t)
        parts = [p.strip() for p in parts if len(p.strip()) > 20]
    if not parts:
        return [t]
    return parts


def _strip_fence(s: str) -> str:
    x = (s or "").strip()
    if x.startswith("```"):
        x = re.sub(r"^```(?:json)?\s*", "", x)
        x = re.sub(r"\s*```\s*$", "", x)
    return x.strip()


def split_experiences_llm(work_text: str) -> list[dict[str, str]]:
    from deepseek_api import deepseek_chat

    chunk = work_text.strip()[:8000]
    if not chunk:
        return []

    system = (
        "你是简历结构化助手。只输出 JSON 数组，不要其它文字。"
        "每项为对象，键：company, role, period, content。"
        "period 尽量为 YYYY.MM–YYYY.MM，无法确定填空字符串。"
        "company 必须使用原文中的单位全称或一致简称，不要把学校院系误写成公司。"
        "content 仅保留该段职责、成果、工具与业务描述；不得含姓名、电话、邮箱、地址。"
        "只抽取正式工作、实习、兼职雇佣类段落；排除校园社团项目、竞赛、志愿服务、课题（非雇佣）；"
        "不要整段教育背景。每条经历对应一段连续的雇佣叙述；不要合并多段。"
        "没有把握时不要编造条目；不确定的字段填空字符串。"
    )
    raw = deepseek_chat(system, chunk, temperature=0.1, max_tokens=4500)
    text = _strip_fence(raw)
    if "[" in text:
        a, b = text.find("["), text.rfind("]")
        if b > a:
            text = text[a : b + 1]
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(arr, list):
        return []
    out: list[dict[str, str]] = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "company": str(item.get("company") or "").strip(),
                "role": str(item.get("role") or "").strip(),
                "period": str(item.get("period") or "").strip(),
                "content": str(item.get("content") or "").strip(),
            }
        )
    return [x for x in out if x.get("content") or x.get("company")]


def segments_to_rows(
    segments: list[dict[str, str]],
    *,
    prefer_llm_fill: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seg in segments:
        body = (seg.get("content") or "").strip()
        company = (seg.get("company") or "").strip()
        role = (seg.get("role") or "").strip()
        period = (seg.get("period") or "").strip()
        blob = "\n".join(x for x in (company, role, period, body) if x).strip()
        if not blob:
            continue
        if not (company and role and period):
            fx = extract_fields(blob, prefer_llm=prefer_llm_fill)
            company = company or (fx.get("company") or "").strip()
            role = role or (fx.get("role") or "").strip()
            period = period or (fx.get("period") or "").strip()
        if body and not (company and role and period):
            fx2 = extract_fields(body, prefer_llm=prefer_llm_fill)
            company = company or (fx2.get("company") or "").strip()
            role = role or (fx2.get("role") or "").strip()
            period = period or (fx2.get("period") or "").strip()

        raw_desc = strip_personal_noise(body or blob)
        rows.append(
            {
                "_id": str(uuid.uuid4()),
                "company": company,
                "role": role,
                "period": period,
                "raw_description": raw_desc,
            }
        )
    return rows


def process_pdf_bytes_to_experiences(
    data: bytes,
    *,
    prefer_llm: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    full, pdf_method = extract_pdf_bytes(data)
    meta: dict[str, Any] = {
        "pdf_method": pdf_method,
        "extract_method": pdf_method,
        "used_llm_split": False,
        "used_llm_fill": bool(prefer_llm),
        "segment_count": 0,
    }
    if full.startswith("（"):
        meta["note"] = full[:200]
        return [], meta

    cleaned = strip_personal_noise(full)
    work_for_api = work_text_for_llm(cleaned)

    segments_dicts: list[dict[str, str]] = []
    if prefer_llm:
        try:
            segments_dicts = split_experiences_llm(work_for_api)
            meta["used_llm_split"] = bool(segments_dicts)
        except Exception as ex:  # noqa: BLE001
            meta["llm_split_error"] = str(ex)[:200]
            segments_dicts = []
        if not segments_dicts:
            try:
                segments_dicts = split_experiences_llm(cleaned[:8000])
                meta["used_llm_split"] = bool(segments_dicts)
                meta["llm_retry"] = "full_resume"
            except Exception as ex2:  # noqa: BLE001
                meta["llm_retry_error"] = str(ex2)[:120]

    used = "heuristic"
    if not segments_dicts and not prefer_llm:
        chunks = _split_heuristic(work_for_api)
        for ch in chunks:
            fx = extract_with_rules(ch)
            segments_dicts.append(
                {
                    "company": fx.get("company", ""),
                    "role": fx.get("role", ""),
                    "period": fx.get("period", ""),
                    "content": ch,
                }
            )
    elif not segments_dicts and prefer_llm:
        used = "api_failed_fallback_rules"
        chunks = _split_heuristic(work_for_api)
        for ch in chunks:
            if not ch.strip():
                continue
            fx = extract_with_rules(ch)
            segments_dicts.append(
                {
                    "company": fx.get("company", ""),
                    "role": fx.get("role", ""),
                    "period": fx.get("period", ""),
                    "content": ch,
                }
            )
    elif prefer_llm and segments_dicts:
        used = "llm"

    if not segments_dicts and work_for_api.strip():
        if prefer_llm:
            try:
                one = split_experiences_llm(work_for_api[:6000])
                if one:
                    segments_dicts = one
                    used = "llm_single_pass"
            except Exception:  # noqa: BLE001
                pass
        if not segments_dicts:
            fx = extract_with_rules(work_for_api)
            segments_dicts.append(
                {
                    "company": fx.get("company", ""),
                    "role": fx.get("role", ""),
                    "period": fx.get("period", ""),
                    "content": work_for_api.strip(),
                }
            )
            if used != "llm_single_pass":
                used = "rules_bundle"

    rows = segments_to_rows(segments_dicts, prefer_llm_fill=prefer_llm)
    meta["segment_count"] = len(rows)
    meta["extract_method"] = f"{pdf_method};split={used}"
    if not rows:
        meta["note"] = "未识别到经历段落。请安装 PaddleOCR 依赖（含 paddlepaddle），并配置 .env 中 DeepSeek API。"
    return rows, meta


def should_replace_default_experiences(experiences: list[dict[str, Any]]) -> bool:
    if len(experiences) != 1:
        return False

    def _empty(e: dict[str, Any]) -> bool:
        return not any(
            [
                (e.get("company") or "").strip(),
                (e.get("role") or "").strip(),
                (e.get("period") or "").strip(),
                (e.get("raw_description") or "").strip(),
            ]
        )

    return _empty(experiences[0])
