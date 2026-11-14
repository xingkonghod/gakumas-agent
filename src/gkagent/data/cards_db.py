"""卡牌价值库：用本地 master 数据 + 文本关键词给每张牌打分。

不依赖游戏自带推荐；后续接 OCR 读到的卡名/效果文本即可复用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gkagent.data.master import MasterData, MasterEntry

# 关键词权重：正分是收益，负分是代价
# 目标以「打分/结算分数」为第一优先：盾/血只作为保命，权重压低
KEYWORDS: dict[str, float] = {
    "得分": 6.0,
    "打分": 6.0,
    "スコア": 6.0,
    "分数": 4.0,
    "伤害": 4.0,
    "攻击": 2.0,
    "护盾": 0.8,
    "防御": 0.6,
    "元气": 0.6,
    "体力": 0.4,
    "回复": 0.8,
    "抽牌": 2.5,
    "手牌": 1.5,
    "集中": 2.0,
    "好调": 2.0,
    "好印象": 2.0,
    "やる気": 2.0,
    "强气": 2.0,
    "全力": 2.0,
    "温存": 1.5,
    "SP": 1.5,
    "回避": 0.8,
    "无敌": 0.8,
    "追加": 1.0,
    "常时": 1.0,
    "体力上限": 1.0,
    "消耗": -1.0,
    "减少": -1.0,
    "降低": -1.0,
}


@dataclass(frozen=True)
class CardInfo:
    id: str
    name: str
    text: str
    value: float

    def efficiency(self, cost: float | None) -> float:
        if not cost or cost <= 0:
            return self.value
        return self.value / float(cost)


def score_text(text: str) -> float:
    """按效果文本估算「这张卡能带来多少分」。

    优先用真实数值（打分+27 就是 27 分），而不是关键词次数；
    防御/恢复类按收益折算，状态类给固定分。
    """
    if not text:
        return 0.0
    score = 0.0
    # 打分/得分/伤害/スコア + 数值（兼容 "打分 / + / 9" 这种分片 OCR）
    for keyword in ("打分", "得分", "伤害", "スコア"):
        for match in re.finditer(keyword + r"[^0-9]{0,20}(\d{1,3})", text):
            score += float(match.group(1))
    # 元气/护盾（保命，折算低价值）
    for keyword in ("元气", "护盾", "防御"):
        for match in re.finditer(keyword + r"[^0-9]{0,20}(\d{1,3})", text):
            score += float(match.group(1)) * 0.25
    # 体力回复
    for keyword in ("体力回复", "回复"):
        for match in re.finditer(keyword + r"[^0-9]{0,20}(\d{1,3})", text):
            score += float(match.group(1)) * 0.4
    # 抽牌/状态类：给固定收益
    if "抽牌" in text or "抽卡" in text:
        score += 4.0
    if any(word in text for word in ("好调", "好印象", "集中", "强气", "やる気")):
        score += 3.0
    if "训练中仅限1次" in text:
        score += 1.0
    if score == 0.0:
        # 纯关键词兜底（没有数值的效果）
        for keyword, weight in KEYWORDS.items():
            score += text.count(keyword) * weight * 0.5
    return score


class CardLibrary:
    """按卡名查卡，或者直接给效果文本打分。"""

    def __init__(self, master: MasterData | None = None) -> None:
        self.master = master or MasterData()
        self.by_name: dict[str, CardInfo] = {}
        self.by_id: dict[str, CardInfo] = {}
        for entry in self.master.produce_cards:
            info = self._info(entry)
            self.by_id[info.id] = info
            if info.name:
                self.by_name.setdefault(info.name, info)

    @staticmethod
    def _info(entry: MasterEntry) -> CardInfo:
        return CardInfo(
            id=entry.id,
            name=entry.name,
            text=entry.text,
            value=score_text(entry.text),
        )

    def find(self, name: str) -> CardInfo | None:
        if not name:
            return None
        if name in self.by_name:
            return self.by_name[name]
        for card_name, info in self.by_name.items():
            if name in card_name or card_name in name:
                return info
        return None

    def lookup(self, name: str) -> CardInfo | None:
        """严格查卡：全等优先，其次唯一的子串匹配（至少 3 字）。

        手牌 OCR 只给卡名，``find`` 的双向子串会把「平衡感」撞到别的卡上，
        导致文本/估值全错；出牌决策必须用这个。
        """
        if not name:
            return None
        cleaned = name.strip()
        if not cleaned:
            return None
        if cleaned in self.by_name:
            return self.by_name[cleaned]
        if len(cleaned) < 3:
            return None
        matches = [info for card_name, info in self.by_name.items() if cleaned in card_name]
        if not matches:
            return None
        matches.sort(key=lambda info: (len(info.name), info.id))
        return matches[0]

    def score(self, name: str, text: str = "", cost: float | None = None) -> float:
        info = self.find(name)
        if info is not None and not text:
            return info.efficiency(cost)
        return score_text(text) / float(cost) if cost else score_text(text)

    def __len__(self) -> int:
        return len(self.by_name)
