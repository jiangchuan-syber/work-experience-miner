# -*- coding: utf-8 -*-
"""固定模板：发现问题 → 推进问题 → 解决问题 + 指标（导出用）。"""
from __future__ import annotations

from typing import Any, TypedDict


class WorkExperience(TypedDict, total=False):
    company: str
    role: str
    period: str
    raw_description: str  # 左侧编辑的原始描述/要点


def build_markdown_export(
    experiences: list[dict[str, Any]],
    kb_hint: str,
) -> str:
    """生成供继续填写或粘贴到 Word 的 Markdown。"""
    lines: list[str] = [
        "# 工作经历挖掘导出",
        "",
        "---",
        "",
        "## 使用说明",
        "",
        "以下内容按「发现问题 → 推进问题 → 解决问题 → 可量化成果」组织。"
        "请在每条下用要点补全事实；暂不确定处请写「待补充」，避免编造数据。",
        "",
        "---",
        "",
        "## 目标岗位与行业参考（本地知识库摘要）",
        "",
        "```",
        (kb_hint[:3500] + "…") if len(kb_hint) > 3500 else kb_hint,
        "```",
        "",
        "---",
        "",
    ]
    for i, exp in enumerate(experiences, 1):
        company = (exp.get("company") or "").strip() or "（公司待填）"
        role = (exp.get("role") or "").strip() or "（岗位待填）"
        period = (exp.get("period") or "").strip() or "（时间待填）"
        raw = (exp.get("raw_description") or "").strip()

        lines.extend(
            [
                f"## 工作经历 {i}：{company} · {role}",
                "",
                f"- **时间**：{period}",
                "",
                "### 原始描述（来自左侧编辑区）",
                "",
                raw if raw else "（暂无，请在应用中填写）",
                "",
                "### 一、发现问题",
                "",
                "- **背景与痛点**：（行业/业务/技术层面的问题是什么？谁受影响？）",
                "- **你如何意识到该问题**：（数据、反馈、现场、评审等）",
                "",
                "### 二、推进问题",
                "",
                "- **目标与成功标准**：（当时约定或自我定义的标准）",
                "- **关键协作与取舍**：（跨谁、优先级、资源约束）",
                "- **阶段与里程碑**：（若无可写「待补充」）",
                "",
                "### 三、解决问题",
                "",
                "- **方案要点**：（方法、工具、流程、标准；工科可写技术栈/实验设计；管理科可写机制与协调）",
                "- **你的个人贡献**：（独立负责 / 主导 / 核心执行，避免只写「参与」）",
                "",
                "### 四、可量化成果",
                "",
                "- **核心指标**：（如效率、成本、质量、时效、满意度、规模；写清时间范围与对比基线）",
                "- **可验证证据**：（系统上线、报告、验收、获奖、他人评价——任选可公开表述的）",
                "",
                "---",
                "",
            ]
        )

    lines.extend(
        [
            "## 挖掘提问清单（面谈自用）",
            "",
            "1. 若没有你参与，这件事最可能卡在哪里？",
            "2. 你做过哪一个**具体决定**改变了走向？依据是什么？",
            "3. 约束条件是什么（时间/预算/合规/人手）？你如何 trade-off？",
            "4. 上线或交付后，**第一次**用什么数据/事实验证有效？",
            "5. 是否经历过失败、返工或范围变更？你学到了什么？",
            "",
        ]
    )
    return "\n".join(lines)
