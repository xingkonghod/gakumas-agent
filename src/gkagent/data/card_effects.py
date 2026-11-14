"""卡面文本 → 结构化效果 → 机制加权估值。

用途：
- 卡牌奖励/事件选择时，按机制价值挑牌（而不是按关键词个数）；
- 手牌分数预览读不到时，用卡名查卡库取兜底估值；
- 判断一张牌是"打分牌 / buff 牌 / 保命牌"，给策略层定出牌顺序。

文本形态（master 导出）：``"打分 / + / 9 / 元气 / + / 2"``，先归一化成 ``"打分+9 元气+2"``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from gkagent.data.buffs import BuffLibrary

# 中文 UI 关键词 → 效果类型；顺序有意义（先长词后短词，避免"体力消耗"被"体力"吃掉）
EFFECT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("heal", ("体力回复", "回复体力", "回复")),
    ("cost", ("体力消耗", "消耗体力", "体力")),
    ("score", ("打分", "得分", "分数", "スコア")),
    ("vitality", ("元气",)),
    ("condition", ("好调",)),
    ("focus", ("集中",)),
    ("motivation", ("干劲",)),
    ("impression", ("好印象",)),
    ("draw", ("抽牌", "抽卡")),
    ("strength", ("上升量增加", "力量")),
)

_NUMBER = re.compile(r"(\d{1,3})")


@dataclass(frozen=True)
class CardEffect:
    kind: str
    amount: float
    text: str = ""


@dataclass
class CardValue:
    """一张牌在当前局面下的估值。"""

    score: float = 0.0
    effects: list[CardEffect] = field(default_factory=list)
    kinds: frozenset[str] = frozenset()
    buff: bool = False
    reason: str = ""

    @property
    def is_score_card(self) -> bool:
        return "score" in self.kinds


def normalize_text(text: str) -> str:
    """``"打分 / + / 9"`` → ``"打分+9"``；去掉多余分隔符。"""
    if not text:
        return ""
    cleaned = re.sub(r"\s*[/／]\s*", "", text)
    cleaned = cleaned.replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_effects(text: str) -> list[CardEffect]:
    """粗粒度解析：关键词 + 其后第一个数字。识别不了就返回空。"""
    normalized = normalize_text(text)
    if not normalized:
        return []
    effects: list[CardEffect] = []
    consumed: list[tuple[int, int]] = []
    for kind, keywords in EFFECT_KEYWORDS:
        for keyword in keywords:
            for match in re.finditer(re.escape(keyword), normalized):
                span = (match.start(), match.end())
                if any(span[0] >= a and span[1] <= b for a, b in consumed):
                    continue
                tail = normalized[match.end() : match.end() + 12]
                number = _NUMBER.search(tail)
                if number is None:
                    continue
                effects.append(CardEffect(kind=kind, amount=float(number.group(1)), text=keyword))
                consumed.append(span)
                break
    return effects


def is_buff_text(text: str) -> bool:
    """这张牌是不是"上 buff"（不加分、靠后续牌吃倍率）。"""
    effects = parse_effects(text)
    kinds = {effect.kind for effect in effects}
    if "score" in kinds:
        return False
    return bool(kinds & {"condition", "focus", "motivation", "impression"})


def estimate_value(
    text: str,
    *,
    library: BuffLibrary | None = None,
    turns_left: int | None = None,
    stamina_ratio: float | None = None,
) -> CardValue:
    """按机制权重给卡面文本打分（只用于排序，不要求数值精确）。"""
    lib = library or BuffLibrary()
    normalized = normalize_text(text)
    effects = parse_effects(normalized)
    kinds = frozenset(effect.kind for effect in effects)
    value = 0.0
    reasons: list[str] = []
    for effect in effects:
        if effect.kind == "score":
            value += effect.amount
            reasons.append(f"打分{effect.amount:.0f}")
        elif effect.kind == "heal":
            value += effect.amount * 2.0
            reasons.append(f"回复{effect.amount:.0f}")
        elif effect.kind == "vitality":
            weight = 0.05 if (stamina_ratio is None or stamina_ratio > 0.4) else 0.6
            value += effect.amount * weight
            reasons.append(f"元气{effect.amount:.0f}")
        elif effect.kind == "focus":
            value += effect.amount * 3.0
            reasons.append(f"集中{effect.amount:.0f}")
        elif effect.kind == "condition":
            value += effect.amount * 4.0
            reasons.append(f"好调{effect.amount:.0f}")
        elif effect.kind == "motivation":
            value += effect.amount * 0.3
        elif effect.kind == "impression":
            value += effect.amount * 1.5
        elif effect.kind == "draw":
            value += 3.0
        elif effect.kind == "cost":
            value -= effect.amount * 0.6
            reasons.append(f"耗体力{effect.amount:.0f}")
    buff_value = lib.value(normalized, turns_left=turns_left)
    if buff_value and not kinds.intersection({"score"}):
        value += buff_value
        if buff_value >= 1.0:
            reasons.append(f"buff等效{buff_value:.1f}")
    return CardValue(
        score=value,
        effects=effects,
        kinds=kinds,
        buff=lib.is_buff_card(normalized),
        reason=" ".join(reasons),
    )
