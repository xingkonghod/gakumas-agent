"""卡牌价值库：用本地 master 数据 + 文本关键词给每张牌打分。

不依赖游戏自带推荐；后续接 OCR 读到的卡名/效果文本即可复用。
"""

from __future__ import annotations

from dataclasses import dataclass

from gkagent.data.master import MasterData, MasterEntry

# 关键词权重：正分是收益，负分是代价
KEYWORDS: dict[str, float] = {
    "得分": 3.0,
    "打分": 3.0,
    "伤害": 2.5,
    "攻击": 2.0,
    "スコア": 3.0,
    "护盾": 2.0,
    "防御": 1.5,
    "元气": 1.5,
    "体力": 1.0,
    "回复": 1.5,
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
    "回避": 1.5,
    "无敌": 2.0,
    "追加": 1.0,
    "常时": 1.0,
    "体力上限": 2.0,
    "分数": 2.0,
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
    score = 0.0
    for keyword, weight in KEYWORDS.items():
        score += text.count(keyword) * weight
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

    def score(self, name: str, text: str = "", cost: float | None = None) -> float:
        info = self.find(name)
        if info is not None and not text:
            return info.efficiency(cost)
        return score_text(text) / float(cost) if cost else score_text(text)

    def __len__(self) -> int:
        return len(self.by_name)
