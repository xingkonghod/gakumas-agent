"""界面识别：OCR 关键词规则 → 屏幕类型 + 置信度。

识别顺序：先看关键词，不依赖固定坐标；模板匹配留给按钮级校验。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from gkagent.vision.ocr import OcrEngine, OcrLine


class ScreenType(str, Enum):
    HOME = "home"
    IDOL_MENU = "idol_menu"
    SUPPORT_LIST = "support_list"
    IDOL_DETAIL = "idol_detail"
    PRODUCE = "produce"
    BATTLE = "battle"
    UNKNOWN = "unknown"


RULES: dict[ScreenType, tuple[str, ...]] = {
    ScreenType.HOME: ("亲密度", "活动经费", "工作", "任务", "商店", "プロデュース"),
    ScreenType.IDOL_MENU: ("培养P偶像", "支援卡", "回忆", "培育编成"),
    ScreenType.SUPPORT_LIST: ("支援卡", "强化", "等级", "特训"),
    ScreenType.IDOL_DETAIL: ("特训", "才能开花", "名册"),
    ScreenType.BATTLE: ("剩余回合", "SKIP", "体力"),
    ScreenType.PRODUCE: ("冲刺", "审查基准", "Vi训练", "Da训练", "Vo训练"),
}


@dataclass(frozen=True)
class Recognition:
    screen: ScreenType
    confidence: float
    lines: list[OcrLine]

    def text(self) -> str:
        return " ".join(line.text for line in self.lines)


class ScreenRecognizer:
    def __init__(self, ocr: OcrEngine | None = None) -> None:
        self.ocr = ocr or OcrEngine()

    def recognize(self, image: np.ndarray) -> Recognition:
        lines = self.ocr.read(image)
        text = " ".join(line.text for line in lines)
        best = ScreenType.UNKNOWN
        best_hits = 0
        for screen, keywords in RULES.items():
            hits = sum(1 for keyword in keywords if keyword in text)
            if hits > best_hits:
                best, best_hits = screen, hits
        total = len(RULES.get(best, ())) or 1
        confidence = best_hits / total if best_hits else 0.0
        return Recognition(best, confidence, lines)

    def is_screen(self, image: np.ndarray, screen: ScreenType, min_confidence: float = 0.5) -> bool:
        result = self.recognize(image)
        return result.screen is screen and result.confidence >= min_confidence
