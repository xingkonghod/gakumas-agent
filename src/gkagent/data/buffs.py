"""buff/机制知识库：把攻略里的状态效果变成可查表的数据。

数据文件 ``data/knowledge/buffs.json``（人工校订 + 来源链接），本模块只负责加载、
按卡面/说明文本做关键词命中，以及给策略层提供"这张牌属于哪类收益"的判断。

设计原则：
- 中文 UI 关键词优先（``cn``），日文攻略关键词备用（``jp``）；
- 数值只用于**排序和取舍**，不用于精确算分——精确分数直接读游戏界面上的预览；
- 没有把握的一律给保守权重，宁可少加分也不要让机器人乱打。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "buffs.json"


@dataclass(frozen=True)
class Buff:
    id: str
    cn: tuple[str, ...]
    jp: tuple[str, ...]
    kind: str  # buff / debuff
    scope: str  # common / sense / logic / anomaly
    category: str  # multiplier / flat_stack / amplifier / defense / resource / utility / dot / block
    duration: str
    score_flat: float
    score_mult: float
    play_order: int
    effect: str
    notes: str = ""

    def keywords(self) -> tuple[str, ...]:
        return self.cn + self.jp


@dataclass
class BuffLibrary:
    buffs: list[Buff] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> BuffLibrary:
        target = Path(path) if path else DEFAULT_PATH
        if not target.exists():
            return cls()
        raw = json.loads(target.read_text(encoding="utf-8"))
        buffs = [
            Buff(
                id=row.get("id", ""),
                cn=tuple(row.get("cn") or ()),
                jp=tuple(row.get("jp") or ()),
                kind=row.get("kind", "buff"),
                scope=row.get("scope", "common"),
                category=row.get("category", "utility"),
                duration=row.get("duration", ""),
                score_flat=float(row.get("score_flat") or 0.0),
                score_mult=float(row.get("score_mult") or 1.0),
                play_order=int(row.get("play_order") or 50),
                effect=row.get("effect", ""),
                notes=row.get("notes", ""),
            )
            for row in raw.get("buffs", [])
        ]
        return cls(buffs=buffs, weights=dict(raw.get("score_weights") or {}))

    # ------------------------------------------------------------------ 查询
    def find(self, text: str) -> list[Buff]:
        """返回文本里命中的所有 buff（按 play_order 排序）。"""
        if not text:
            return []
        hits = [buff for buff in self.buffs if any(word in text for word in buff.keywords())]
        hits.sort(key=lambda buff: buff.play_order)
        return hits

    def first(self, text: str) -> Buff | None:
        hits = self.find(text)
        return hits[0] if hits else None

    def has(self, text: str, buff_id: str) -> bool:
        return any(buff.id == buff_id for buff in self.find(text))

    def is_buff_card(self, text: str) -> bool:
        """是否"上 buff 的牌"（本身不加分、靠后续牌吃倍率）。"""
        if any(word in (text or "") for word in ("打分", "得分", "分数", "スコア")):
            return False
        hits = self.find(text)
        if not hits:
            return False
        positive = [buff for buff in hits if buff.kind == "buff"]
        if not positive:
            return False
        return not any(buff.category == "resource" and buff.score_flat >= 2.0 for buff in positive)

    def play_order(self, text: str) -> int:
        hits = self.find(text)
        return hits[0].play_order if hits else 50

    def matches(self, text: str, name: str) -> bool:
        """卡面文本是否命中名字叫 ``name`` 的 buff（中/日文关键词都算）。"""
        if not text or not name:
            return False
        return any(
            name in buff.cn or name in buff.jp
            for buff in self.find(text)
        )

    def plan_rank(self, text: str, priority: tuple[str, ...]) -> tuple[int, int]:
        """按方案优先级给一张牌排序：命中 ``priority[i]`` → ``(i, 0)``。

        没命中任何优先 buff 的牌排在所有优先项之后，再按原来的 ``play_order``
        细分（保留"元气/防御后置"这类全局经验）。返回值越小越先打。
        """
        hits = self.find(text)
        for rank, name in enumerate(priority):
            if any(name in buff.cn or name in buff.jp for buff in hits):
                return rank, 0
        return len(priority), hits[0].play_order if hits else 50

    def value(self, text: str, *, turns_left: int | None = None) -> float:
        """buff 文本折算成"等效分数"，只用于和打分牌排序。

        粗但可解释：倍率类按 1.5 倍覆盖后续 2 张牌算，叠层类按每层每回合算。
        """
        total = 0.0
        turns = turns_left if turns_left is not None else 2
        for buff in self.find(text):
            if buff.kind != "buff":
                total += buff.score_flat
                continue
            if buff.category == "multiplier":
                total += (buff.score_mult - 1.0) * 12.0 * max(1, min(turns, 3))
            elif buff.category == "dot":
                total += buff.score_flat * max(1, min(turns, 4))
            elif buff.category == "flat_stack":
                total += buff.score_flat * 3.0
            else:
                total += buff.score_flat
        return total
