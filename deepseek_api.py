# -*- coding: utf-8 -*-
"""
DeepSeek Chat API（OpenAI 兼容协议）。
环境变量见项目根目录 `.env.example`。
"""
from __future__ import annotations

import os
from typing import Any


def load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def deepseek_chat(
    system_prompt: str,
    user_message: str,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    """单轮：[system + 单条 user]。"""
    return deepseek_chat_messages(
        system_prompt,
        [{"role": "user", "content": user_message}],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def deepseek_chat_messages(
    system_prompt: str,
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    """
    多轮：system + 若干 user/assistant 顺序消息（通常为历史 + 本条 user）。
    OpenAI Chat Completions 兼容。
    """
    load_dotenv_if_present()
    api_key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        msg = "缺少环境变量 DEEPSEEK_API_KEY（可在项目根目录创建 .env 并填写）"
        raise ValueError(msg)

    base_url = (os.environ.get("DEEPSEEK_API_BASE") or "https://api.deepseek.com").strip()
    base_url = base_url.rstrip("/")
    m = (model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip()

    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
    client = OpenAI(**kwargs)

    conv: list[dict[str, str]] = []
    for mo in messages:
        role = (mo.get("role") or "").strip()
        raw = mo.get("content")
        body = raw.strip() if isinstance(raw, str) else str(raw or "").strip()
        if role not in {"user", "assistant"} or not body:
            continue
        conv.append({"role": role, "content": body})
    req: dict[str, Any] = {
        "model": m,
        "messages": [
            {"role": "system", "content": system_prompt or "You are a helpful assistant."},
            *conv,
        ],
        "temperature": temperature,
    }
    if max_tokens is not None:
        req["max_tokens"] = max_tokens

    resp = client.chat.completions.create(**req)
    choice = resp.choices[0].message
    content = getattr(choice, "content", None) or ""
    return content.strip()


def deepseek_chat_conversation(
    system_prompt: str,
    prior_turns: list[dict[str, Any]],
    user_message: str,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    """在多轮上下文 prior_turns（user/assistant 交替片段）末尾追加本条 user_message。"""
    seq: list[dict[str, Any]] = [*prior_turns, {"role": "user", "content": user_message}]
    return deepseek_chat_messages(
        system_prompt,
        seq,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
