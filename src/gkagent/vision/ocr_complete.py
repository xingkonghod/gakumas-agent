"""OCR 字段 opt-in 引擎补全（matto 基准缺口 B：屏幕读不到的字段用引擎状态补）。

matto 49 帧横比（https://hiro.matto.top/ocr-dataset/check.html，本地参考不入库）里
有三类字段**所有 5 个 OCR 后端都没读**——不是 OCR 质量问题，是屏幕上根本没有
可读文字（或只有图标）：

- ``deck_left``（牌库剩余）：右上角卡背图标旁的小数字，5 后端全没读；
  引擎侧 ``LessonSim.deck`` 长度就是真值（我们自己的 Draws/牌组计数）。
- ``statuses[*].kind == card_effect``（卡片/饮料效果图标状态）：图标无文字，
  5 后端全没读；引擎侧 sim 状态镜（buff/饮料效果计数）才有。
- ``multiplier_pct``（考试属性倍率）：ppocr5/winocr 没读；屏幕读到时以 OCR 为准，
  读不到时可用 B4 ``sim.exam_multiplier.calculate_bonus`` 从屏幕三维 + 本场
  审查基准/分数表算出（千分比 → 屏幕百分比 = permil // 10）。

**opt-in 铁律**：``enable=False``（默认）时 :func:`complete_fields` 原样返回输入
（逐位不变，不碰生产读屏路径）；只有调用方显式 ``enable=True`` 且给了补全源才填。
本模块**只读** sim 的公开状态，不修改 sim/drinks/rng_graph/card_zones/exam_risk
（sim-fidelity owns）；card_effect 状态镜的具体映射由调用方（sim 侧）提供，
这里只负责接线与去重，不臆造图标语义。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from gkagent.sim.exam_multiplier import ATTRS, ExamBonus

# 屏幕百分比与千分比的换算：屏幕「2805%」= 28050 permil（B4 口径 4110 → 411%）。
_PERMIL_PER_PCT = 10


@dataclass(frozen=True)
class CompletionSources:
    """补全源：全部可选；缺哪项就不补哪项（绝不编造）。

    - ``deck_count``：牌库剩余张数（``len(LessonSim.deck)``）。
    - ``card_effects``：sim 状态镜投影出的 card_effect 状态条目，
      每条形如 ``{"kind": "card_effect", "name": None, "value": 1}``；
      ``name`` 允许 None（图标状态屏幕上本来就没有名字）。
    - ``bonus`` + ``exam_attr``：B4 算出的本场三项倍率 + 当前回合属性
      （vocal/dance/visual），用于 multiplier_pct 兜底。
    """

    deck_count: int | None = None
    card_effects: tuple[Mapping[str, Any], ...] = ()
    bonus: ExamBonus | None = None
    exam_attr: str | None = None


def sources_from_sim(sim: Any, *, bonus: ExamBonus | None = None, exam_attr: str | None = None) -> CompletionSources:
    """从 LessonSim（或任何带 ``deck`` 列表的对象）取牌库计数。

    card_effect 状态镜不在此臆造：sim 侧语义归 sim-fidelity，调用方需要时
    自行投影 ``card_effects`` 传进 :class:`CompletionSources`。
    """
    deck = getattr(sim, "deck", None)
    count = len(deck) if deck is not None else None
    return CompletionSources(deck_count=count, bonus=bonus, exam_attr=exam_attr)


def _norm_status(entry: Mapping[str, Any]) -> tuple:
    return (
        str(entry.get("kind") or ""),
        str(entry.get("name") or ""),
        entry.get("value"),
    )


def complete_fields(
    fields: Mapping[str, Any],
    sources: CompletionSources | None = None,
    *,
    enable: bool = False,
) -> dict[str, Any]:
    """对读屏字段字典做 opt-in 补全，返回**新字典**（不改输入）。

    规则（只填 None 缺口，OCR 已读到的值一律不动）：

    1. ``deck_left`` 为 None 且 ``sources.deck_count`` 已知 → 填牌库计数；
    2. ``statuses`` 里缺 card_effect 条目 → 按状态镜追加（去重，保持既有顺序）；
    3. ``multiplier_pct`` 为 None 且 ``bonus``/``exam_attr`` 已知 → 填 permil//10。

    ``enable=False`` 或 ``sources=None``：逐位返回输入拷贝（默认关）。
    """
    out = dict(fields)
    if not enable or sources is None:
        return out
    if out.get("deck_left") is None and sources.deck_count is not None:
        out["deck_left"] = int(sources.deck_count)
    effects = [e for e in sources.card_effects if str(e.get("kind") or "") == "card_effect"]
    if effects:
        statuses: list[Mapping[str, Any]] = list(out.get("statuses") or ())
        seen = {_norm_status(s) for s in statuses}
        for entry in effects:
            key = _norm_status(entry)
            if key not in seen:
                statuses.append(dict(entry))
                seen.add(key)
        out["statuses"] = statuses
    if (
        out.get("multiplier_pct") is None
        and sources.bonus is not None
        and sources.exam_attr in ATTRS
    ):
        permil = int(sources.bonus.permil[sources.exam_attr])
        out["multiplier_pct"] = permil // _PERMIL_PER_PCT
    return out


__all__ = [
    "CompletionSources",
    "complete_fields",
    "sources_from_sim",
]
