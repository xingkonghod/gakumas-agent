"""卡牌属性表：来自 gakumasu-diff 的 ProduceCard.yaml（和游戏 master 同一套 ID）。

作用：出牌时**不用 OCR 猜体力费用**——卡面爱心小字 12px、确认帧预览会错位，
而这张表是按 ID 对出来的真值（1724 张全中）。

字段：cost（体力费用）、rarity、plan、category、effects（examEffectType 列表）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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

    def value(self, name: str) -> float | None:
        """奖励选卡用：打分 / 体力（0 费按 1 费算）。"""
        score = self.score_of(name)
        if score is None:
            return None
        cost = self.cost(name)
        return score / max(cost if cost is not None else 1, 1)

    @staticmethod
    def looks_conditional(text: str) -> bool:
        return any(word in (text or "") for word in CONDITION_WORDS)
