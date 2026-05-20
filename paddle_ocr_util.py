# -*- coding: utf-8 -*-
"""PaddleOCR 封装：对 PIL Image / 页面截图逐行拼接文本（中文简历）。"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
from PIL import Image

_ocr: Any = None

_log = logging.getLogger("ppocr")
_log.setLevel(logging.WARNING)


def get_paddle_ocr():  # type: ignore[no-untyped-def]
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR

        _ocr = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            show_log=False,
            use_gpu=False,
        )
    return _ocr


def image_to_text_paddle(image: Image.Image) -> str:
    """PIL RGB → Paddle 识别，返回多行文本。"""
    rgb = np.array(image.convert("RGB"))
    bgr = rgb[:, :, ::-1].copy()
    ocr = get_paddle_ocr()
    res = ocr.ocr(bgr, cls=True)
    if not res or res[0] is None:
        return ""
    lines: list[str] = []
    for item in res[0]:
        if item and len(item) >= 2 and item[1]:
            txt = item[1][0]
            if isinstance(txt, str) and txt.strip():
                lines.append(txt.strip())
    return "\n".join(lines)
