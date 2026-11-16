"""三种方案（プラン）三套打法的知识库：感性 / 理性 / 非凡。

数据文件 ``data/knowledge/plans.json``（人工维护），本模块只做加载和校验：

- ``sense``（感性）：好调（打分上升量 ×1.5）+ 集中（每点 +1）→ 先铺后打；
- ``logic``（理性）：好印象（回合结束结算）+ やる気（元气/费用资源）→ 前期铺层；
- ``anomaly``（非凡）：温存 / 強気 / 全力 指針 → 温存攒全力值，窗口期兑现。

``buff_priority`` 的先后就是出牌顺序：文本策略（``policy.lesson``）用
``BuffLibrary`` 的关键词匹配，模拟器（``sim.lesson``）按 ``PLAN_BUFF_FIELDS``
把 buff 名映射到 ``CardSpec`` 字段。

设计原则与 ``buffs.py`` 一致：缺文件 / 坏 JSON / 未知方案一律退回 ``sense``，
绝不抛异常——真机跑到一半不能因为数据文件写错而停摆。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_PATH",
    "DEFAULT_PLAN",
    "PLAN_BUFF_FIELDS",
    "VALID_PLANS",
    "Plan",
    "PlanLibrary",
    "default_plan_library",
    "normalize_plan",
]

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "plans.json"

DEFAULT_PLAN = "sense"
VALID_PLANS: tuple[str, ...] = ("sense", "logic", "anomaly")

# 游戏内方案名 / 中文名 / 日文名都认，配置里写哪个都能落到同一个 key。
PLAN_ALIASES: dict[str, str] = {
    "sense": "sense",
    "感性": "sense",
    "センス": "sense",
    "logic": "logic",
    "理性": "logic",
    "ロジック": "logic",
    "anomaly": "anomaly",
    "非凡": "anomaly",
    "アノマリー": "anomaly",
}

# 方案优先级里的 buff 名 → 模拟器 CardSpec 字段。
# 文本策略不需要这张表：它用 BuffLibrary 的关键词直接匹配卡面文本。
PLAN_BUFF_FIELDS: dict[str, tuple[str, ...]] = {
    "好调": ("condition",),
    "绝好调": ("condition",),
    "集中": ("focus",),
    "好印象": ("impression",),
    "やる気": ("motivation",),
    "干劲": ("motivation",),
    "温存": ("preservation",),
    "強気": ("strong_level",),
    "强气": ("strong_level",),
    "全力": ("full_power_point", "full_power_scale"),
    "全力值": ("full_power_point",),
}

# plans.json 缺失/坏掉时的兜底：与仓库里的默认值保持一致。
_BUILTIN_ROWS: dict[str, dict[str, Any]] = {
    "sense": {
        "cn": "感性",
        "buff_priority": ["好调", "集中"],
        "early_buff_turns": 3,
        "score_after_buff": True,
        "notes": "好调覆盖爆发回合，集中永久叠；先铺再打",
    },
    "logic": {
        "cn": "理性",
        "buff_priority": ["好印象", "やる気"],
        "early_buff_turns": 4,
        "score_after_buff": True,
        "notes": "好印象铺到 15 层再兑现；留 3-5 やる気付费用",
    },
    "anomaly": {
        "cn": "非凡",
        "buff_priority": ["温存", "強気", "全力"],
        "early_buff_turns": 2,
        "score_after_buff": False,
        "notes": "温存攒到全力值 10，最后 1-2 回合切全力",
    },
}


def normalize_plan(value: object) -> str | None:
    """把方案名归一成 ``sense`` / ``logic`` / ``anomaly``；认不出返回 ``None``。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return PLAN_ALIASES.get(text.lower()) or PLAN_ALIASES.get(text)


@dataclass(frozen=True)
class Plan:
    """一个方案（プラン）的打法参数。"""

    key: str
    cn: str
    buff_priority: tuple[str, ...]
    early_buff_turns: int
    score_after_buff: bool
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan": self.key,
            "cn": self.cn,
            "buff_priority": list(self.buff_priority),
            "early_buff_turns": self.early_buff_turns,
            "score_after_buff": self.score_after_buff,
            "notes": self.notes,
        }


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _as_bool(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _as_priority(value: object, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return default
    names = tuple(str(item).strip() for item in value if isinstance(item, str) and item.strip())
    return names or default


def _plan_from_row(key: str, row: object) -> Plan:
    """按方案 key 解析一条配置；坏字段用该方案的兜底值，不抛异常。"""
    fallback = _BUILTIN_ROWS[key]
    data: dict[str, Any] = row if isinstance(row, dict) else {}
    return Plan(
        key=key,
        cn=str(data.get("cn") or fallback["cn"]),
        buff_priority=_as_priority(data.get("buff_priority"), tuple(fallback["buff_priority"])),
        early_buff_turns=_as_int(data.get("early_buff_turns"), int(fallback["early_buff_turns"])),
        score_after_buff=_as_bool(data.get("score_after_buff"), bool(fallback["score_after_buff"])),
        notes=str(data.get("notes") or fallback["notes"]),
    )


@dataclass
class PlanLibrary:
    """三个方案的配置；``get`` 对未知方案退回 ``sense``。"""

    plans: dict[str, Plan] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> PlanLibrary:
        target = Path(path) if path else DEFAULT_PATH
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raw = {}
        # 兼容 {"plans": {...}} 和直接 {"sense": {...}} 两种写法。
        section = raw.get("plans") if isinstance(raw, dict) else None
        if not isinstance(section, dict):
            section = raw if isinstance(raw, dict) else {}
        plans = {key: _plan_from_row(key, section.get(key)) for key in VALID_PLANS}
        return cls(plans=plans)

    def get(self, plan: object) -> Plan:
        """取方案配置；未知/缺省方案退回 ``sense``。"""
        key = normalize_plan(plan) or DEFAULT_PLAN
        return self.plans.get(key) or self.plans[DEFAULT_PLAN]

    def has(self, plan: object) -> bool:
        return normalize_plan(plan) in self.plans

    def keys(self) -> tuple[str, ...]:
        return tuple(self.plans)

    def priority(self, plan: object) -> tuple[str, ...]:
        return self.get(plan).buff_priority

    def early_buff_turns(self, plan: object) -> int:
        return self.get(plan).early_buff_turns


@lru_cache(maxsize=1)
def default_plan_library() -> PlanLibrary:
    """默认 plans.json（缓存一次；文件不存在时用内置兜底）。"""
    return PlanLibrary.load()
