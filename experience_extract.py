# -*- coding: utf-8 -*-
"""从一段中文简历/经历原文中提取「公司、岗位、起止时间」。"""
from __future__ import annotations

import json
import re
from typing import Any


def _strip_fence(s: str) -> str:
    t = (s or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def extract_with_llm(raw_text: str) -> dict[str, str]:
    """需要 DEEPSEEK_API_KEY；返回 company, role, period。"""
    from deepseek_api import deepseek_chat

    chunk = (raw_text or "").strip()[:6000]
    if not chunk:
        return {"company": "", "role": "", "period": ""}

    system = (
        "你是简历信息抽取助手。只输出一个 JSON 对象，不要其它文字。"
        '键：company（公司全称）、role（岗位/实习头衔）、period（起止，统一为 YYYY.MM–YYYY.MM，'
        "中文年月要先换算数字月份。"
        "无法确定的字段用空字符串。不要编造。"
    )
    user = "从下列文本中提取**最主要的一段工作或实习经历**的三个字段：\n\n" + chunk
    out = deepseek_chat(system, user, temperature=0.1, max_tokens=500)
    text = _strip_fence(out)
    # 容错：截取第一个 { 到最后一个 }
    if "{" in text:
        a, b = text.find("{"), text.rfind("}")
        if b > a:
            text = text[a : b + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"company": "", "role": "", "period": ""}

    return {
        "company": str(data.get("company") or "").strip(),
        "role": str(data.get("role") or "").strip(),
        "period": str(data.get("period") or "").strip(),
    }


def _norm_period(m: re.Match[str]) -> str | None:
    """多种日期形式 → YYYY.MM–YYYY.MM"""
    g = m.groupdict()
    if g.get("y1") and g.get("m1") and g.get("y2") and g.get("m2"):
        y1, m1, y2, m2 = g["y1"], g["m1"], g["y2"], g["m2"]
        return f"{int(y1):04d}.{int(m1):02d}–{int(y2):04d}.{int(m2):02d}"
    return None


def extract_with_rules(raw_text: str) -> dict[str, str]:
    """无 API 时的规则抽取（覆盖常见中文实习表述）。"""
    t = (raw_text or "").replace("—", "–").replace("－", "–")
    if not t.strip():
        return {"company": "", "role": "", "period": ""}

    period = ""
    patterns = [
        r"(?P<y1>\d{4})\s*年\s*(?P<m1>\d{1,2})\s*月\s*[至到\-–]\s*(?P<y2>\d{4})\s*年\s*(?P<m2>\d{1,2})\s*月",
        r"(?P<y1>\d{4})\s*\.\s*(?P<m1>\d{1,2})\s*[至到\-–]\s*(?P<y2>\d{4})\s*\.\s*(?P<m2>\d{1,2})",
        r"(?P<y1>\d{4})\s*/\s*(?P<m1>\d{1,2})\s*[至到\-–]\s*(?P<y2>\d{4})\s*/\s*(?P<m2>\d{1,2})",
    ]
    mtime = re.search(
        r"(?:实习)?(?:时间|期间|起止)[:：]\s*([^\n]+)", t, re.I
    )
    if mtime:
        t = mtime.group(1).strip() + "\n" + t
    for p in patterns:
        m = re.search(p, t)
        if m:
            np = _norm_period(m)
            if np:
                period = np
                break

    company = ""
    # 含「有限/股份/公司」的典型公司名一行
    for line in t.splitlines():
        line = line.strip()
        if not line or len(line) < 4:
            continue
        if re.search(r"(有限公司|股份有限公司|股份公司|集团|咨询|科技|企业)", line):
            if "大学" not in line[:6] and "学院" not in line[:6]:
                company = line
                break
    munit = re.search(r"(?:实习)?单位[:：]\s*([^\n]+)", t)
    if munit:
        company = munit.group(1).strip().strip("，,")
    if not company:
        mco = re.search(
            r"([\u4e00-\u9fa5（）()、\w]{4,40}(?:有限公司|股份有限公司|公司|集团))",
            t,
        )
        if mco:
            company = mco.group(1).strip()

    role = ""
    mpos = re.search(r"(?:实习)?(?:岗位|职位)[:：]\s*([^\n]+)", t)
    if mpos:
        role = mpos.group(1).strip()
    if not role and "实习生" in t:
        role = "实习生"
        mdept = re.search(
            r"([\u4e00-\u9fa5]{2,12}(?:部|组|中心|室)?)\s*实习生", t
        )
        if mdept:
            role = mdept.group(1).strip() + "实习生"
    if not role:
        mr = re.search(
            r"(人力资源(?:专员|助理|实习生)?|HR(?:实习生)?|产品经理(?:实习生)?|"
            r"软件开发(?:实习生)?|算法(?:实习生)?|运营(?:实习生)?)",
            t,
            re.I,
        )
        if mr:
            role = mr.group(1)

    return {"company": company.strip(), "role": role.strip(), "period": period}


def extract_fields(raw_text: str, *, prefer_llm: bool) -> dict[str, str]:
    if prefer_llm:
        try:
            llm = extract_with_llm(raw_text)
            if any(llm.values()):
                return llm
        except Exception:  # noqa: BLE001
            pass
    return extract_with_rules(raw_text)
