"""卡牌属性表：来自 gakumasu-diff 的 ProduceCard.yaml（和游戏 master 同一套 ID）。

作用：出牌时**不用 OCR 猜体力费用**——卡面爱心小字 12px、确认帧预览会错位，
而这张表是按 ID 对出来的真值（1724 张全中）。

字段：cost（体力费用）、rarity、plan、category、effects（examEffectType 列表）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "card_table.json"

# 中文卡面里表示"有前提条件才能打"的说法
CONDITION_WORDS = ("状态的时候", "的情况下", "情况下，可以使用", "以上时", "低于", "训练中仅限")


@dataclass(frozen=True)
class CardMeta:
    name: str
    cost: int
    rarity: str
    plan: str
    category: str
    effects: tuple[str, ...]

    @property
    def conditional(self) -> bool:
        return False


class CardTable:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._cards: dict[str, dict] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._cards = dict(raw.get("cards") or {})
            except (OSError, json.JSONDecodeError):
                self._cards = {}

    def __len__(self) -> int:
        return len(self._cards)

    def get(self, name: str) -> dict | None:
        if not name:
            return None
        row = self._cards.get(name.strip())
        if row is not None:
            return row
        # OCR 常丢末尾的 "+"：退回未强化版本
        base = name.strip().rstrip("+＋")
        return self._cards.get(base)

    def cost(self, name: str) -> int | None:
        row = self.get(name)
        if row is None:
            return None
        value = row.get("cost")
        return int(value) if isinstance(value, int) else None

    def meta(self, name: str) -> CardMeta | None:
        row = self.get(name)
        if row is None:
            return None
        return CardMeta(
            name=name,
            cost=int(row.get("cost") or 0),
            rarity=str(row.get("rarity") or ""),
            plan=str(row.get("plan") or ""),
            category=str(row.get("category") or ""),
            effects=tuple(str(effect.get("type", "")) for effect in row.get("effects") or ()),
        )

    def score_of(self, name: str) -> int | None:
        """卡面打分数值（ExamLesson 的 v1）；查不到返回 None。"""
        row = self.get(name)
        if row is None:
            return None
        for effect in row.get("effects") or []:
            if effect.get("type") == "ExamLesson":
                values = [v for v in effect.get("values") or [] if v]
                if values:
                    return int(values[0])
        return 0

    # 能滚雪球的 buff 类效果（打法知识库：感性先铺集中/好调）
    COMBO_EFFECTS = ("ExamLessonBuff", "ExamConcentration", "ExamParameterBuff")

    # 纯 buff / 功能牌按效果类型给等效白值（8-15）：集中/好调/温存高，纯元气中等。
    # 旧公式 score/cost 对 score=0 的 buff 卡恒为 0，奖励界面永远跳过它们
    # （真机：换盾攒 buff 的牌和 SSR 卡被白值更高的普通卡挤掉）。
    BUFF_EFFECT_VALUES: ClassVar[dict[str, float]] = {
        "ExamPreservation": 14.0,  # 温存：跨回合保留 buff
        "ExamConcentration": 13.0,  # 集中：每层放大后续所有打分
        "ExamLessonBuff": 12.0,  # 好调/干劲：覆盖本回合后续牌
        "ExamPrerequisite": 12.0,  # 前提：攒够层数才解锁强效果
        "ExamParameterBuff": 11.0,  # 参数上升
        "ExamFullPowerPoint": 10.0,  # 全力点（攒满打一发大的）
        "ExamReview": 10.0,  # 好印象
        "ExamCardDraw": 9.0,  # 抽牌/过牌
        "ExamBlock": 8.0,  # 纯元气（保命，不加分）
        "ExamStaminaRecoverFix": 8.0,
        "ExamStaminaConsumptionDown": 8.0,
    }
    # SSR 的强度很大程度来自技能连带，卡表模型只能这样近似（Legend 同档）
    RARE_RARITIES = ("ssr", "legend")

    def value(self, name: str) -> float | None:
        """奖励选卡估值（只用于排序，不要求精确）。

        分档：
        - 白值卡：``score / cost``；
        - 纯 buff 卡（score=0）：按效果类型给 8-15 的等效值；多种 buff 取最高，
          额外种类每种 +0.5，封顶 15（集中/好调/温存高，纯元气中等）；
        - SSR/Legend 稀有度 +3；
        - 已有 combo 加分保留（+2）。
        """
        score = self.score_of(name)
        if score is None:
            return None
        cost = self.cost(name)
        base = score / max(cost if cost is not None else 1, 1)
        row = self.get(name) or {}
        effects = {str(effect.get("type", "")) for effect in row.get("effects") or []}
        if score <= 0:
            buff_values = sorted(
                (self.BUFF_EFFECT_VALUES[t] for t in effects if t in self.BUFF_EFFECT_VALUES),
                reverse=True,
            )
            if buff_values:
                # 多个 buff 有协同，但等效值不超过 15
                base = min(15.0, buff_values[0] + 0.5 * (len(buff_values) - 1))
        if effects & set(self.COMBO_EFFECTS):
            base += 2.0  # 滚雪球价值：约等于多 2 点性价比
        if str(row.get("rarity") or "").strip().lower() in self.RARE_RARITIES:
            base += 3.0  # SSR/Legend：技能连带强度，模型里只能这样近似
        return base

    @staticmethod
    def looks_conditional(text: str) -> bool:
        return any(word in (text or "") for word in CONDITION_WORDS)
