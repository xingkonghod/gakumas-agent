"""卡牌元数据索引（B10 / T5 剩余机制②）：卡名 → 触发限定需要的静态属性。

合并两份 tracked 数据（都是静态参考数据，懒加载一次）：

* ``data/knowledge/card_table.json`` —— 中文卡名 → cost/rarity/plan/category/effects
  （+ id/upgrade），出牌卡表真值（1817 张按 id 对出来的）；
* ``data/knowledge/card_meta.json`` —— 卡名 → ``idol_unique`` / ``effect_groups``
  （``scripts/build_card_meta.py`` 从主数据 ``ProduceCard`` 的
  ``originIdolCardId``/``originCharacterId``/``effectGroupIds`` 构建，
  偶像固有判据与 BSD-3 参考引擎 pIdol 集合交叉验证 340/342、0 误报）。

给 ``sim/p_items.py`` 的触发限定求值用：「偶像固有技能卡使用时」「X效果的技能卡
使用时」「[卡名]使用时/后」「牌堆或弃牌中的干扰卡在 N 张以上」等。``apply_passive``
仍是纯函数（同样的输入永远同样的结果）——本索引只是常量参考数据，不是对局状态。

保守口径：

* 卡名查不到 → ``meta()`` 返回 None（调用方按"不知道"处理，不触发）；
* ``card_meta.json`` 缺失或某张卡没有 meta（主数据快照后新增的 12 张）→
  ``idol_unique`` / ``effect_group`` 限定返回 None（不猜），id/rarity/category/cost
  仍可从 card_table 用；
* 日文卡名（主数据 ``name``）经 ``ja_aliases`` 解析到中文卡名（生成卡文本解析用）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_KNOWLEDGE = Path(__file__).resolve().parents[3] / "data" / "knowledge"
CARD_TABLE_PATH = _KNOWLEDGE / "card_table.json"
CARD_META_PATH = _KNOWLEDGE / "card_meta.json"

#: card_table 的 rarity 写法 → 统一大写（触发限定 r-sr-ssr-legend 用）。
RARITY_NORMALIZE = {
    "n": "N",
    "r": "R",
    "sr": "SR",
    "ssr": "SSR",
    "legend": "LEGEND",
    "t": "T",
}


@dataclass(frozen=True)
class CardMetaInfo:
    """一张卡（按名字索引，含强化变体）的触发限定属性。"""

    name: str
    card_id: str
    upgrade: int
    rarity: str  # N / R / SR / SSR / LEGEND（大写）
    category: str  # ActiveSkill / MentalSkill / Trouble
    plan: str  # Plan1 / Plan2 / Plan3 / Common（卡表原值）
    cost: int  # 卡面原始体力费用（「原本的消耗体力值」限定用）
    effects: tuple[str, ...]  # examEffectType 列表
    idol_unique: bool  # 偶像固有（originIdolCardId/originCharacterId）
    effect_groups: tuple[str, ...]  # effect_group-visible-exam_*-000
    has_meta: bool  # card_meta.json 里有这张卡（False → 固有/效果组限定不可判）


class CardMetaIndex:
    """卡名 → CardMetaInfo 的懒加载索引（两份 JSON 合并）。"""

    def __init__(
        self,
        table_path: str | Path | None = None,
        meta_path: str | Path | None = None,
    ) -> None:
        self._table_path = Path(table_path) if table_path else CARD_TABLE_PATH
        self._meta_path = Path(meta_path) if meta_path else CARD_META_PATH
        self._rows: dict[str, dict] | None = None
        self._meta: dict[str, dict] = {}
        self._ja_aliases: dict[str, str] = {}
        self._reverse: dict[tuple[str, int], str] | None = None

    # ---- 懒加载 -----------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._rows is not None:
            return
        rows: dict[str, dict] = {}
        if self._table_path.is_file():
            try:
                rows = dict(json.loads(self._table_path.read_text(encoding="utf-8")).get("cards") or {})
            except (OSError, json.JSONDecodeError):
                rows = {}
        self._rows = rows
        if self._meta_path.is_file():
            try:
                payload = json.loads(self._meta_path.read_text(encoding="utf-8"))
                self._meta = dict(payload.get("cards") or {})
                self._ja_aliases = dict(payload.get("ja_aliases") or {})
            except (OSError, json.JSONDecodeError):
                self._meta = {}
                self._ja_aliases = {}

    @property
    def meta_available(self) -> bool:
        """card_meta.json 是否可用（缺失时固有/效果组限定一律不可判）。"""
        self._ensure_loaded()
        return bool(self._meta)

    # ---- 查询 -------------------------------------------------------------
    def resolve(self, name: str) -> str | None:
        """卡名规范化：中文精确 / 日文别名 / 丢 ``+`` 退回未强化（同 CardTable.get）。"""
        self._ensure_loaded()
        if not name:
            return None
        name = name.strip()
        assert self._rows is not None
        if name in self._rows:
            return name
        if name in self._ja_aliases:
            return self._ja_aliases[name]
        base = name.rstrip("+＋")
        if base in self._rows:
            return base
        if base in self._ja_aliases:
            return self._ja_aliases[base]
        return None

    def meta(self, name: str) -> CardMetaInfo | None:
        """卡名 → 元数据；查不到返回 None（调用方保守不触发）。"""
        resolved = self.resolve(name)
        if resolved is None:
            return None
        assert self._rows is not None
        row = self._rows.get(resolved) or {}
        extra = self._meta.get(resolved)
        rarity = RARITY_NORMALIZE.get(str(row.get("rarity") or "").strip().lower(), "")
        return CardMetaInfo(
            name=resolved,
            card_id=str(row.get("id") or ""),
            upgrade=int(row.get("upgrade") or 0),
            rarity=rarity,
            category=str(row.get("category") or ""),
            plan=str(row.get("plan") or ""),
            cost=int(row.get("cost") or 0),
            effects=tuple(str(e.get("type") or "") for e in row.get("effects") or ()),
            idol_unique=bool(extra and extra.get("idol_unique")),
            effect_groups=tuple(extra.get("effect_groups") or ()) if extra else (),
            has_meta=extra is not None,
        )

    def name_of(self, card_id: str, upgrade: int = 0) -> str | None:
        """``(ProduceCardId, upgrade)`` → 中文卡名（生成卡按 id 找卡用）。"""
        self._ensure_loaded()
        if self._reverse is None:
            assert self._rows is not None
            reverse: dict[tuple[str, int], str] = {}
            for name, row in self._rows.items():
                rid = row.get("id")
                if isinstance(rid, str) and rid:
                    reverse.setdefault((rid, int(row.get("upgrade") or 0)), name)
            self._reverse = reverse
        return self._reverse.get((str(card_id), int(upgrade)))

    def names(self) -> tuple[str, ...]:
        """全部已知卡名（中文 + 日文别名）；生成卡文本的最长后缀匹配用。"""
        self._ensure_loaded()
        assert self._rows is not None
        return tuple(self._rows.keys()) + tuple(self._ja_aliases.keys())


_INDEX: CardMetaIndex | None = None


def card_meta_index() -> CardMetaIndex:
    """进程级单例（静态参考数据，加载一次）。"""
    global _INDEX
    if _INDEX is None:
        _INDEX = CardMetaIndex()
    return _INDEX


__all__ = [
    "CARD_META_PATH",
    "CARD_TABLE_PATH",
    "RARITY_NORMALIZE",
    "CardMetaIndex",
    "CardMetaInfo",
    "card_meta_index",
]