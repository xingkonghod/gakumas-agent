"""gkbench 提交：把 gkagent 的回合内 expectimax 包成 UIObs v1 算法。

这个文件只做三件事：

1. ``obs -> ExpectState``：手牌/山札/弃牌/除外按 UIObs 的 id+强化次数查卡表，
   体力/元气/分数/回合/出牌数/状态按画面字段填；画面没有的（回忆、饮料效果、
   定制、成长、保留区）用保守默认（见 ``_state`` / ``_spec``）。P 道具从
   ``ctx.loadout.produce_item_ids``（开局就公开的配置，不含种子）映射成本地
   ``PItemSpec`` 清单，交给 ``gkagent.sim.expectimax`` 在回合/出牌时机结算。
2. 调 ``gkagent.sim.expectimax``：枚举本回合所有合法有序出牌序列，抽牌是精确
   机会节点，目标函数是 ``E[a·P(score≥CLEAR) + b·P(score≥PERFECT)]``。
3. 把首牌映射回 ``("play", i)`` / ``("drink", j)`` / ``("end",)``，并**保证**
   返回的动作属于 ``ctx.obs["legal"]``；模型和画面分歧时退回合法动作，不报错。

关键约束（对应任务要求）：

- 局面状态只读 ``ctx.obs``；时间读 ``ctx.budget``。CLEAR/PERFECT 优先用
  ``ctx.meta`` 里**开考就公开**的 ``rival_scores`` / ``score_cap``（base.py 明确
  说 meta 不含种子）；拿不到就退回 hif 尺度的常量，可用参数覆盖。
- 不用 ``ctx.seed`` / ``ctx.worlds`` / ``ctx.true_session``；``needs_gkms = False``。
- 画面里读不到的字段一律保守：牌序未知（我们的引擎本来就只吃多重集）、
  回忆/定制/成长不建模、饮料不建模、保留区不进牌库；P 道具已结算但已用次数未知
  （obs 里没有 uses，保守按 0 开始 → 可能高估剩余可用次数，见 ``_resolve_p_items``）。

本地跑（需要仓库的 ``src`` 在 PYTHONPATH，或把 ``src/gkagent`` 放进本目录的
``vendor/``）：

    python -m gkbench eval --set hif --algo submissions/expectimax/algo.py:ExpectimaxAlgo --seeds 2

提交到 gkbench 时把 ``data/knowledge/card_table.json`` 和
``data/knowledge/p_items.json`` 复制到本目录旁即可；``gkbench`` 会先把本目录加进
``sys.path``，同目录的辅助模块/数据能直接读。缺 P 道具数据时算法仍会跑（P 道具
按空清单处理，并在 ``Decision.meta["p_items_error"]`` 里记录原因，不假装结算过）。
"""
from __future__ import annotations

import functools
import json
import math
import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

from gkbench.algos.base import Algorithm, Decision

# 评测沙盒里通常没有安装 gkagent；把本提交自带的 vendor/ 加进路径（没有就跳过）。
_VENDOR = Path(__file__).resolve().parent / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from gkagent.data.p_items_db import (  # noqa: I001 - 必须在 vendor 路径之后导入
    PItemDataUnavailable,
    load_p_item_catalog,
    resolve_produce_item_ids,
)
from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    ExpectState,
    ExpectimaxConfig,
    expectimax_with_stats,
)
from gkagent.sim.lesson import CardSpec
from gkagent.sim.p_items import PItemSpec
from gkagent.sim.stance import score_multiplier

__all__ = ["ExpectimaxAlgo"]

# 真机每回合基础出牌数（UIObs 的 num.playable 是「额外次数」，不是上限）。
DEFAULT_PLAY_LIMIT = 3
# 卡表查不到时的保守牌费：按 3 费处理，搜索会自然少打。
DEFAULT_CARD_COST = 3
# hif 题集的分数尺度（random≈2 万，greedy≈4 万，uinet≈28 万，oracle≈60 万）。
# 没有 ctx.meta 时用这组兜底；有对手分/分数上限时优先用画面公开信息。
DEFAULT_CLEAR = 150_000
DEFAULT_PERFECT = 450_000
# 叶子 σ 取 CLEAR 的比例。考试分数尺度比训练大两个数量级，固定 σ=80 会让档位
# 效用变成硬阶跃（不是 0 就是 1），搜索失去区分度；按阈值缩放后才是软档位。
DEFAULT_SIGMA_RATIO = 0.35
# 卡表候选路径：优先同目录（提交时复制一份），再退回仓库 data/knowledge。
_TABLE_NAME = "card_table.json"
# P 道具目录（T5③）：与卡表同样优先同目录，再退回仓库 data/knowledge。
_P_ITEMS_NAME = "p_items.json"


def _table_candidates() -> Iterable[Path]:
    env = os.environ.get("GKAGENT_CARD_TABLE")
    if env:
        yield Path(env).expanduser()
    here = Path(__file__).resolve().parent
    yield here / _TABLE_NAME
    # here = <repo>/submissions/expectimax，parents[1] = <repo>。
    yield here.parents[1] / "data" / "knowledge" / _TABLE_NAME


def _p_items_candidates() -> Iterable[Path]:
    env = os.environ.get("GKAGENT_P_ITEMS")
    if env:
        yield Path(env).expanduser()
    here = Path(__file__).resolve().parent
    yield here / _P_ITEMS_NAME
    yield here.parents[1] / "data" / "knowledge" / _P_ITEMS_NAME


@functools.lru_cache(maxsize=1)
def _load_p_item_catalog():
    """读 P 道具目录（同目录/仓库 data/knowledge 任一）；找不到抛 PItemDataUnavailable。"""
    tried: list[str] = []
    for path in _p_items_candidates():
        if not path.is_file():
            tried.append(str(path))
            continue
        return load_p_item_catalog(path)
    raise PItemDataUnavailable("找不到 P 道具数据（试过：" + "、".join(tried) + "）")


# --------------------------------------------------------------- 卡表 -> CardSpec
def _buff_turns(effect: Mapping[str, Any]) -> int:
    """持续类效果的剩余回合：``turn < 0`` = 永久（-1），否则至少 1 回合。"""
    turn = int(effect.get("turn") or 0)
    return -1 if turn < 0 else max(1, turn)


def _merge_turns(current: int, new: int) -> int:
    """合并同一种持续效果：任一永久则永久，否则取更长。"""
    if current < 0 or new < 0:
        return -1
    return max(current, new)


def _effect_fields(row: Mapping[str, Any]) -> dict[str, int]:
    """卡表一行的 ``effects`` -> ``CardSpec`` 字段。

    口径与 ``scripts/sim_produce.py::_effect_fields`` 基本一致（那份是训练模拟器
    实际在用的 25 字段版本，有测试覆盖）。两处主动差异：

    - ``ExamLesson`` 的 ``count > 1`` 按多段打点乘上去
      （``play_choice._score_from_row`` 同口径），否则连击牌会被低估一半以上；
    - ``ExamLessonBuffDependParameterBuff`` 按至少 1 回合好调记
      （``play_choice._DEPENDENT_BUFF_FLOOR`` 同口径），sim_produce 直接忽略它。
    """
    fields: dict[str, int] = {
        "score": 0,
        "condition": 0,
        "focus": 0,
        "draw": 0,
        "impression": 0,
        "impression_scale": 0,
        "preservation": 0,
        "full_power_point": 0,
        "extra_play": 0,
        "block_scale": 0,
        "parameter_buff": 0,
        "parameter_buff_turns": 1,
        "strong_level": 0,
        "vitality": 0,
        "stamina_recover": 0,
        "full_power_scale": 0,
        "encore": 0,
        "review_multiple": 0,
        "review_multiple_turns": 0,
        "condition_additive": 0,
        "condition_additive_turns": 0,
        "full_power_lesson_multiple": 0,
        "full_power_lesson_multiple_turns": 0,
        "grow_score": 0,
        "motivation": 0,
    }
    approx_draw = 0

    def absorb(effects: Iterable[Mapping[str, Any]] | None) -> None:
        nonlocal approx_draw
        for effect in effects or ():
            kind = str(effect.get("type") or "")
            values = [int(v) for v in effect.get("values") or () if v]
            value = values[0] if values else 0

            # ---- 2026-11-16 新卡池：精确 / 近似口径同 sim_produce ----
            if kind == "ExamStatusEnchant":
                absorb(effect.get("inner") or ())
                continue
            if kind == "ExamStatusEnchantEncore":
                fields["encore"] = 1
                continue
            if kind in ("ExamForcePlayCardSearch", "ExamCardCreateId", "ExamCardMove"):
                # 免费检索/生成/移回手牌 → 至少 +1 抽牌（低估）；有额外次数时不
                # 再加，避免 0 费循环在搜索里无限过牌。
                approx_draw = 1
                continue
            if kind in ("ExamEffectTimer", "ExamEffectTimerEndTurn", "ExamAntiDebuff"):
                # 延迟效果/低下无效：搜索里按立刻生效或 no-op 处理。
                continue
            if kind == "ExamAddGrowEffect":
                fields["grow_score"] = max(fields["grow_score"], value)
                continue
            if kind == "ExamStaminaRecoverFix":
                fields["stamina_recover"] = max(fields["stamina_recover"], value)
                continue
            if kind == "ExamLessonFullPowerPoint":
                if len(values) >= 2:
                    # 双值：[固定打分, 折算千分比]
                    fields["score"] = max(fields["score"], values[0])
                    fields["full_power_scale"] = max(fields["full_power_scale"], values[-1])
                else:
                    fields["full_power_scale"] = max(fields["full_power_scale"], value)
                continue
            if kind == "ExamReviewMultiple":
                fields["review_multiple"] = max(fields["review_multiple"], value)
                fields["review_multiple_turns"] = _merge_turns(
                    fields["review_multiple_turns"], _buff_turns(effect)
                )
                continue
            if kind == "ExamParameterBuffAdditiveFix":
                fields["condition_additive"] = max(fields["condition_additive"], value)
                fields["condition_additive_turns"] = _merge_turns(
                    fields["condition_additive_turns"], _buff_turns(effect)
                )
                continue
            if kind == "ExamFullPowerLessonMultipleAdditive":
                fields["full_power_lesson_multiple"] = max(
                    fields["full_power_lesson_multiple"], value
                )
                fields["full_power_lesson_multiple_turns"] = _merge_turns(
                    fields["full_power_lesson_multiple_turns"], _buff_turns(effect)
                )
                continue
            if kind == "ExamEnthusiasticTurnAdd":
                # 热意延长：模拟器没有独立热意资源，按训练口径并进好调回合数。
                fields["condition"] += value
                continue
            if kind == "ExamCardPlayAggressive":
                fields["motivation"] = max(fields["motivation"], value)
                continue

            # ---- 旧 13 类（与 sim_produce 一致）----
            if kind == "ExamPlayableValueAdd":
                fields["extra_play"] = max(
                    fields["extra_play"], value or int(effect.get("count") or 1)
                )
                continue
            if kind in ("ExamParameterBuff", "ExamParameterBuffMultiplePerTurn"):
                # 卡面是「好调 N 回合 / 绝好调 N 回合」；turn 才是持续回合数。
                turn = int(effect.get("turn") or 0)
                if turn > 0:
                    fields["condition"] = max(fields["condition"], turn)
                fields["parameter_buff"] = max(fields["parameter_buff"], value)
                if kind == "ExamParameterBuffMultiplePerTurn" and value > 0:
                    fields["parameter_buff_turns"] = max(
                        fields["parameter_buff_turns"], turn or 2
                    )
                continue
            if kind == "ExamLessonBuffDependParameterBuff":
                # 好调回合数依赖「审查基准加成」层数，模拟器没有该状态；
                # 保守下限取 1 回合（和 play_choice._DEPENDENT_BUFF_FLOOR 同口径）。
                # 这类效果的 values 常为空，必须放在 `if not value` 之前。
                fields["condition"] = max(fields["condition"], 1)
                continue
            if not value:
                continue
            if kind == "ExamLesson":
                # count > 1 = 多段打点（97 张）；训练脚本旧口径没乘，这里乘上。
                count = max(int(effect.get("count") or 1), 1)
                fields["score"] = max(fields["score"], value * count)
            elif kind == "ExamLessonBuff":
                fields["focus"] = max(fields["focus"], value)
            elif kind == "ExamConcentration":
                # 卡面「強気変更」的段階 1/2，不是集中层数（见 scripts/sim_produce）。
                fields["strong_level"] = max(fields["strong_level"], value)
            elif kind == "ExamBlock":
                fields["vitality"] = max(fields["vitality"], value)
            elif kind == "ExamCardDraw":
                fields["draw"] = max(fields["draw"], value)
            elif kind == "ExamReview":
                fields["impression"] = max(fields["impression"], value)
            elif kind == "ExamLessonDependExamReview":
                fields["impression_scale"] = max(fields["impression_scale"], value)
            elif kind == "ExamLessonDependBlock":
                fields["block_scale"] = max(fields["block_scale"], value)
            elif kind == "ExamPreservation":
                fields["preservation"] = max(fields["preservation"], value)
            elif kind == "ExamFullPowerPoint":
                fields["full_power_point"] = max(fields["full_power_point"], value)

    absorb(row.get("effects") or ())
    if approx_draw and fields["extra_play"] == 0:
        fields["draw"] = max(fields["draw"], 1)
    return fields


def _spec_from_row(name: str, row: Mapping[str, Any]) -> CardSpec:
    """卡表一行 -> ``CardSpec``（未建模的定制/成长/once 用保守默认）。"""
    fields = _effect_fields(row)
    cost = row.get("cost")
    return CardSpec(
        name=name or str(row.get("id") or "?"),
        cost=max(int(cost), 0) if isinstance(cost, int) else DEFAULT_CARD_COST,
        score=float(fields["score"]),
        category=str(row.get("category") or ""),
        vitality=fields["vitality"],
        condition=fields["condition"],
        focus=fields["focus"],
        motivation=fields["motivation"],
        impression=fields["impression"],
        draw=fields["draw"],
        impression_scale=fields["impression_scale"],
        preservation=fields["preservation"],
        full_power_point=fields["full_power_point"],
        extra_play=fields["extra_play"],
        block_scale=fields["block_scale"],
        parameter_buff=fields["parameter_buff"],
        parameter_buff_turns=fields["parameter_buff_turns"],
        strong_level=fields["strong_level"],
        stamina_recover=fields["stamina_recover"],
        full_power_scale=fields["full_power_scale"],
        encore=bool(fields["encore"]),
        review_multiple=fields["review_multiple"],
        review_multiple_turns=fields["review_multiple_turns"],
        condition_additive=fields["condition_additive"],
        condition_additive_turns=fields["condition_additive_turns"],
        full_power_lesson_multiple=fields["full_power_lesson_multiple"],
        full_power_lesson_multiple_turns=fields["full_power_lesson_multiple_turns"],
        grow_score=fields["grow_score"],
    )


def _load_card_rows() -> dict[tuple[str, int], tuple[str, Mapping[str, Any]]]:
    """``(produce_card_id, upgrade) -> (name, row)``；找不到文件返回空表。"""
    for path in _table_candidates():
        try:
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = raw.get("cards") or {}
        if not isinstance(rows, Mapping):
            continue
        by_key: dict[tuple[str, int], tuple[str, Mapping[str, Any]]] = {}
        for name, row in rows.items():
            if not isinstance(row, Mapping):
                continue
            card_id = str(row.get("id") or "")
            if not card_id:
                continue
            upgrade = int(row.get("upgrade") or 0)
            by_key.setdefault((card_id, upgrade), (str(name), row))
        return by_key
    return {}


# --------------------------------------------------------------- 解析式叶子
class _ExamLeafValue(AnalyticLeafValue):
    """把考试属性倍率/指針倍率补进解析式 V_leaf。

    ``AnalyticLeafValue.predict`` 是训练口径（属性倍率 1.0、指針倍率 1.0）；
    考试画面的 ``exam.permil`` 是 2 万～4 万（= 20～40 倍），不补会把未来分
    低估几十倍，搜索就会退化成「只看本回合已得分」。
    """

    def predict(self, state: ExpectState) -> tuple[float, float]:
        if state.turns_left <= 0:
            return 0.0, 0.0
        n = self.playable_count(state)
        mean = self.mean_card_score(state)
        factor = max(float(state.attribute_coefficient), 1.0) * max(
            score_multiplier(state.stance_state), 0.0
        )
        mu = (float(n) * float(state.focus) + mean * n) * factor
        if state.condition_turns > 0 and self.condition_multiplier > 1.0:
            conditioned = min(n, state.play_limit * state.condition_turns)
            mu += mean * (self.condition_multiplier - 1.0) * conditioned * factor
        mu += self.impression_annuity(state)
        # 依赖元气/好印象的牌：剩余牌里这类牌越多、当前层数越高，未来分越高。
        # 这段按 LessonSim._card_award 的口径不乘属性倍率（依赖分单独加）。
        cards = (*state.hand, *state.deck, *state.discard)
        block_cards = [card for card in cards if card.block_scale > 0]
        review_cards = [card for card in cards if card.impression_scale > 0]
        if block_cards and state.vitality > 0:
            avg = sum(card.block_scale for card in block_cards) / len(block_cards)
            mu += min(len(block_cards), n) * state.vitality * avg / 100.0
        if review_cards and state.impression > 0:
            avg = sum(card.impression_scale for card in review_cards) / len(review_cards)
            mu += min(len(review_cards), n) * state.impression * avg / 100.0
        if not math.isfinite(mu):
            mu = 0.0
        return max(mu, 0.0), max(float(self.sigma), 0.0)


# --------------------------------------------------------------- obs -> 状态
def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _attribute_coefficient(exam: Mapping[str, Any]) -> float:
    """当前回合的分数倍率（画面「歌唱 3866%」= 38.66）；课程/无倍率时 1.0。"""
    permil = [_as_int(v) for v in exam.get("permil") or ()]
    types = [_as_int(v) for v in exam.get("types") or ()]
    turn = _as_int(exam.get("turn"), 1)
    if permil and types:
        # 追加回合（turn > len(types)）沿用最后一回合的属性，和真机一致。
        index = types[min(max(turn, 1), len(types)) - 1] - 1
        if 0 <= index < len(permil) and permil[index] > 0:
            return permil[index] / 1000.0
    positive = [value for value in permil if value > 0]
    return max(positive) / 1000.0 if positive else 1.0


def _stance_from_obs(obs: Mapping[str, Any], full_power_point: int) -> tuple[str, int, int, int]:
    """UIObs ``stance`` -> ``ExpectState.stance`` 四元组。

    UIObs v1 在不同引擎版本里可能是字符串（"Concentration"/"Preservation"/
    "FullPower"）或整数；两种都认，认不出按无指針（保守）。
    """
    raw = obs.get("stance") or (None, 0)
    kind = raw[0] if len(raw) > 0 else None
    step = max(_as_int(raw[1] if len(raw) > 1 else 0), 0)
    stance, strong_level, save_level = "normal", 0, 0
    text = str(kind or "").strip().lower()
    if isinstance(kind, str):
        if "full" in text:
            stance = "full"
        elif "concentration" in text or "strong" in text:
            level = min(max(step, 1), 2)
            stance, strong_level = f"strong{level}", level
        elif "preservation" in text or "save" in text:
            stance, save_level = "save", min(max(step, 1), 2)
        elif "leisurely" in text:
            stance = "normal"
    elif isinstance(kind, int):
        if kind == 1:
            level = min(max(step, 1), 2)
            stance, strong_level = f"strong{level}", level
        elif kind == 2:
            stance, save_level = "save", min(max(step, 1), 2)
        elif kind == 3:
            stance = "full"
    return stance, strong_level, save_level, max(full_power_point, 0)


def _status_fields(obs: Mapping[str, Any], turns_left: int) -> dict[str, Any]:
    """把 UIObs ``status`` 图标折算成 ExpectState 的 buff 字段。

    只映射我们建模了的种类；未建模的（スランプ/パニック/费用增减/元气限制/
    绝好调/审查基准层等）直接忽略——保守，不虚构收益。
    """
    out: dict[str, Any] = {
        "focus": 0,
        "impression": 0,
        "motivation": 0,
        "condition_turns": 0,
        "review_multiple": 0,
        "review_multiple_turns": 0,
        "full_power_lesson_multiple": 0,
        "full_power_lesson_multiple_turns": 0,
        "condition_additive": 0,
        "condition_additive_turns": 0,
        "parameter_buff": 0,
        "full_power_point": 0,
        "permanent_multiplier": 0.0,
    }
    turn_multipliers = 0.0
    for row in obs.get("status") or ():
        try:
            kind = str(row[0])
            value = _as_float(row[1])
            turns = _as_int(row[2], 0)
        except (TypeError, ValueError, IndexError):
            continue
        if kind == "review":
            out["impression"] = max(out["impression"], int(value))
        elif kind == "aggressive":
            out["motivation"] = max(out["motivation"], int(value))
        elif kind == "lesson_buff":
            out["focus"] = max(out["focus"], int(value))
        elif kind == "parameter_buff":
            # 好调：value 是剩余回合数；永久（-1）按当前剩余回合当保守下限。
            out["condition_turns"] = max(
                out["condition_turns"], turns if turns > 0 else max(turns_left, 1)
            )
        elif kind == "review_multiple":
            permil = round(value * 1000.0)
            out["review_multiple"] = max(out["review_multiple"], permil)
            out["review_multiple_turns"] = _merge_turns(
                out["review_multiple_turns"], turns
            )
        elif kind == "full_power_lesson_multiple_add":
            permil = round(value * 1000.0)
            out["full_power_lesson_multiple"] = max(
                out["full_power_lesson_multiple"], permil
            )
            out["full_power_lesson_multiple_turns"] = _merge_turns(
                out["full_power_lesson_multiple_turns"], turns
            )
        elif kind == "full_power_point":
            out["full_power_point"] = max(out["full_power_point"], int(value))
        elif kind == "lesson_parameter_multiple":
            # 打分上升量增加（0.2 = +20%）。永久层折进属性倍率；有限层当成
            # 本回合的 parameter_buff（我们的 state 只在当前回合保留它）。
            if turns < 0 or turns >= 1_000_000:
                out["permanent_multiplier"] += value
            else:
                turn_multipliers += value
        elif kind == "parameter_buff_additive_fix":
            out["condition_additive"] = max(out["condition_additive"], int(value))
            out["condition_additive_turns"] = _merge_turns(
                out["condition_additive_turns"], turns
            )
    if turn_multipliers:
        out["parameter_buff"] = max(
            out["parameter_buff"], round(1000.0 + turn_multipliers * 1000.0)
        )
    return out


def _hand_action(hand: tuple[CardSpec, ...], playable: set[int], card: CardSpec) -> int | None:
    """把搜索返回的 CardSpec 映射回 obs 手牌下标；只返回 legal 里的下标。"""
    for index, spec in enumerate(hand):
        if index in playable and spec == card:
            return index
    # 同名牌/强化不同导致 CardSpec 不相等时，按名字兜底（仍然只挑 legal）。
    for index, spec in enumerate(hand):
        if index in playable and spec.name == card.name:
            return index
    return None


class ExpectimaxAlgo(Algorithm):
    """回合内精确 expectimax；只读公开观测，纯 Python 搜索。"""

    name = "expectimax"
    needs_gkms = False
    about: ClassVar[dict[str, Any]] = {
        "summary": "回合内精确搜索 + 档位效用叶评估",
        "sees": "screen",
        "detail": [
            "枚举本回合所有合法有序出牌序列（抽牌作为精确机会节点）",
            "目标 = E[CLEAR/PERFECT 档位效用]，不是期望分",
            "P 道具用 ctx.loadout.produce_item_ids（开考公开、不含种子）映射成本地规则结算",
            "画面没有的回忆/定制/饮料/牌序/已用次数用保守默认，不用种子和世界",
        ],
        "links": [
            {
                "title": "实现（gkagent 的 sim/expectimax.py）",
                "url": "https://github.com/xingkonghod/gakumas-agent",
            }
        ],
    }

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.time_budget_ms = max(_as_float(params.get("budget_ms"), 800.0), 1.0)
        self.max_nodes = max(_as_int(params.get("max_nodes"), 200_000), 1)
        self.sigma_ratio = max(_as_float(params.get("sigma_ratio"), DEFAULT_SIGMA_RATIO), 0.0)
        self.sigma_fixed = max(_as_float(params.get("sigma"), 0.0), 0.0)
        self.a_clear = _as_float(params.get("a_clear"), 1.0)
        self.a_perfect = _as_float(params.get("a_perfect"), 1.0)
        self.clear_override = max(_as_int(params.get("clear"), 0), 0)
        self.perfect_override = max(_as_int(params.get("perfect"), 0), 0)
        self.allow_drinks = bool(params.get("allow_drinks", False))
        # P 道具开关（F1/F2 A/B 对照：p_items=false 即旧行为）
        self.use_p_items = bool(params.get("p_items", True))
        self._rows: dict[tuple[str, int], tuple[str, Mapping[str, Any]]] | None = None
        self._spec_cache: dict[tuple[str, int], CardSpec] = {}
        self._p_items: tuple[PItemSpec, ...] | None = None
        self._p_items_meta: dict[str, Any] = {}

    # ------------------------------------------------------------- P 道具
    def _resolve_p_items(self, loadout: Any) -> tuple[PItemSpec, ...]:
        """``ctx.loadout.produce_item_ids`` -> ``PItemSpec``（一局解析一次）。

        loadout 是 base.py 明说的「开局配置（不含种子）」，用它是公平的。
        未知 id（p_items.json 快照之后新增的道具）在 ``_p_items_meta`` 里显式列出；
        缺数据文件时按空清单跑，但 ``meta["p_items_error"]`` 会记录原因——不假装
        结算过（旧行为 = 不建模 P 道具）。
        """
        if self._p_items is not None:
            return self._p_items
        self._p_items = ()
        ids: Any = None
        if isinstance(loadout, Mapping):
            ids = loadout.get("produce_item_ids")
        if not self.use_p_items or not ids:
            self._p_items_meta = {"ids": 0, "enabled": bool(self.use_p_items)}
            return self._p_items
        try:
            catalog = _load_p_item_catalog()
            resolved = resolve_produce_item_ids(ids, catalog=catalog)
        except PItemDataUnavailable as exc:
            self._p_items_meta = {
                "ids": len(list(ids)) if isinstance(ids, Iterable) else 0,
                "error": str(exc),
            }
            return self._p_items
        self._p_items = resolved.specs
        summary = resolved.summary()
        self._p_items_meta = {
            "ids": summary["ids"],
            "known": summary["known_ids"],
            "unknown": list(summary["unknown_ids"]),
            "specs": summary["specs"],
            "implemented": summary["implemented"],
        }
        return self._p_items

    # ------------------------------------------------------------- 卡表
    def _ensure_rows(self) -> dict[tuple[str, int], tuple[str, Mapping[str, Any]]]:
        if self._rows is None:
            self._rows = _load_card_rows()
        return self._rows

    def _spec(self, card: Mapping[str, Any]) -> CardSpec:
        """UIObs 的 ``{id,u,c,g}`` -> CardSpec；强化次数按卡表的 upgrade 选行。

        ``c``（定制）和 ``g``（考试中成长）没有进 CardSpec：前者会改分数/依赖
        倍率，后者真实卡表 GrowEffect 数据为空；忽略是低估，不会凭空加分。
        """
        card_id = str(card.get("id") or "")
        upgrade = max(_as_int(card.get("u"), 0), 0)
        key = (card_id, upgrade)
        cached = self._spec_cache.get(key)
        if cached is not None:
            return cached
        rows = self._ensure_rows()
        spec: CardSpec | None = None
        for level in range(min(upgrade, 3), -1, -1):
            hit = rows.get((card_id, level))
            if hit is not None:
                spec = _spec_from_row(*hit)
                break
        if spec is None:
            # 卡表缺这张：0 分、3 费的保守牌，搜索自然少打；不假装它有收益。
            spec = CardSpec(
                name=card_id or "unknown",
                cost=DEFAULT_CARD_COST,
                score=0.0,
            )
        self._spec_cache[key] = spec
        return spec

    # ------------------------------------------------------------- 阈值
    def _targets(self, ctx: Any, obs: Mapping[str, Any]) -> tuple[int, int]:
        if self.clear_override or self.perfect_override:
            clear = self.clear_override or DEFAULT_CLEAR
            perfect = self.perfect_override or max(clear * 2, clear + 1)
            return clear, perfect
        meta = getattr(ctx, "meta", None)
        meta = meta if isinstance(meta, Mapping) else {}
        cap = _as_int(meta.get("score_cap"), 0)
        if cap > 0:
            return max(cap // 2, 1), max(cap, 2)
        rivals = meta.get("rival_scores") or ()
        tops = [
            max(_as_int(row.get("score_max"), 0), _as_int(row.get("score_min"), 0))
            for row in rivals
            if isinstance(row, Mapping)
        ]
        top = max(tops, default=0)
        if top > 0:
            return top, max(int(top * 1.5), top + 1)
        # 没有公开 meta（严格只给 obs）时退回 hif 尺度；submission.json 的
        # sets 只跑 hif，这个兜底可用参数覆盖。
        return DEFAULT_CLEAR, DEFAULT_PERFECT

    # ------------------------------------------------------------- 状态
    def _state(
        self,
        obs: Mapping[str, Any],
        clear: int,
        perfect: int,
        *,
        p_items: tuple[PItemSpec, ...] = (),
    ) -> ExpectState:
        exam = obs.get("exam") or {}
        num = obs.get("num") or {}
        turn = max(_as_int(exam.get("turn"), 1), 1)
        limit = max(_as_int(exam.get("limit"), turn), turn)
        turns_left = max(limit - turn + 1, 1)
        status = _status_fields(obs, turns_left)
        coefficient = _attribute_coefficient(exam) * (
            1.0 + float(status["permanent_multiplier"])
        )
        stance = _stance_from_obs(obs, int(status["full_power_point"]))
        hand = tuple(self._spec(card) for card in obs.get("hand") or ())
        deck = tuple(self._spec(card) for card in obs.get("deck") or ())
        discard = tuple(self._spec(card) for card in obs.get("grave") or ())
        excluded = tuple(self._spec(card) for card in obs.get("lost") or ())
        # UIObs 的 played 已经在 grave 里（引擎口径），不再并进 discard，避免重复。
        return ExpectState(
            hand=hand,
            deck=deck,
            discard=discard,
            excluded=excluded,
            stamina=max(_as_int(num.get("stamina"), 0), 0),
            stamina_max=max(_as_int(num.get("max_stamina"), 0), 0),
            vitality=max(_as_int(num.get("block"), 0), 0),
            score=max(_as_int(num.get("score"), 0), 0),
            turns_left=turns_left,
            total_turns=limit,
            plays_used=max(_as_int(num.get("plays"), 0), 0),
            play_limit=DEFAULT_PLAY_LIMIT,
            extra_plays=max(_as_int(num.get("playable"), 0), 0),
            clear=max(clear, 0),
            perfect=max(perfect, max(clear, 0)),
            condition_turns=int(status["condition_turns"]),
            focus=int(status["focus"]),
            impression=int(status["impression"]),
            motivation=int(status["motivation"]),
            condition_additive=int(status["condition_additive"]),
            condition_additive_turns=int(status["condition_additive_turns"]),
            review_multiple=int(status["review_multiple"]),
            review_multiple_turns=int(status["review_multiple_turns"]),
            full_power_lesson_multiple=int(status["full_power_lesson_multiple"]),
            full_power_lesson_multiple_turns=int(
                status["full_power_lesson_multiple_turns"]
            ),
            parameter_buff=int(status["parameter_buff"]),
            stance=stance,
            attribute_coefficient=coefficient,
            hand_size=max(len(hand), 1),
            # 回忆/饮料：obs 只有 id，没有可结算的数值；不塞进状态。
            # P 道具：id 清单来自 ctx.loadout（公开配置），已映射成 PItemSpec；
            # 已用次数 obs 里没有，保守按 0 开始（可能高估剩余可用次数）。
            p_items=p_items,
            drinks=(),
            drinks_per_turn=0 if not self.allow_drinks else None,
        )

    # ------------------------------------------------------------- 决策
    def decide(self, ctx: Any) -> Decision:
        obs = ctx.obs
        legal = [tuple(action) for action in obs.get("legal") or ()]
        if not legal:
            return Decision(("end",), {"why": "obs.legal 为空，保守结束回合"})
        if not any(action[0] in ("play", "drink", "end") for action in legal):
            # 选牌等我们不负责的决策：和示例算法一样取第一个合法动作。
            return Decision(legal[0], {"why": "非出牌决策，取第一个合法动作"})

        playable = {
            int(action[1]) for action in legal if len(action) > 1 and action[0] == "play"
        }
        hand = tuple(self._spec(card) for card in obs.get("hand") or ())
        if not playable:
            # 没有可打牌时喝饮料可能更好，但 obs 里没有饮料效果；结束是合法的。
            if ("end",) in legal:
                return Decision(("end",), {"why": "没有可打牌，结束回合"})
            return Decision(legal[0], {"why": "没有可打牌，取第一个合法动作"})
        if not self._ensure_rows():
            # 提交目录里没有 card_table.json（例如只拷了 algo.py）：至少别摆烂，
            # 按示例算法打第一张能打的牌；这不影响正常有卡表时的搜索。
            return Decision(
                ("play", min(playable)), {"why": "卡表缺失，退回第一张能打的牌"}
            )

        clear, perfect = self._targets(ctx, obs)
        p_items = self._resolve_p_items(getattr(ctx, "loadout", None))
        state = self._state(obs, clear, perfect, p_items=p_items)
        sigma = self.sigma_fixed or max(clear * self.sigma_ratio, 1.0)
        leaf = _ExamLeafValue(
            sigma=sigma, a_clear=self.a_clear, a_perfect=self.a_perfect
        )
        budget_s = _as_float(getattr(ctx, "budget", 5.0), 5.0)
        budget_ms = min(self.time_budget_ms, max(budget_s * 1000.0 * 0.6, 50.0))
        config = ExpectimaxConfig(
            a_clear=self.a_clear,
            a_perfect=self.a_perfect,
            sigma=sigma,
            max_nodes=self.max_nodes,
            time_budget_ms=budget_ms,
            allow_drinks=self.allow_drinks,
        )
        result = expectimax_with_stats(state, leaf, config=config)
        meta = {
            "why": "回合内 expectimax（档位效用）",
            "utility": round(result.utility, 6),
            "skip": round(result.skip_utility, 6),
            "nodes": result.nodes,
            "ms": round(result.elapsed_ms, 1),
            "complete": result.complete,
            "clear": clear,
            "perfect": perfect,
            "sigma": round(sigma, 2),
        }
        if self._p_items_meta:
            meta["p_items"] = dict(self._p_items_meta)

        if result.card is None and playable and not result.actions:
            # 搜索在展开第一张牌之前就超时/模型认为一张都打不了：画面仍说这些牌
            # 能打，取第一张合法牌，至少保证动作合法且推进回合。
            meta["why"] = "搜索未展开任何牌，退回第一张合法牌"
            return Decision(("play", min(playable)), meta)

        if result.card is not None:
            index = _hand_action(hand, playable, result.card)
            if index is not None:
                return Decision(("play", index), meta)
            # 模型认为合法、画面不认：用「只含 legal 手牌」的状态再搜一次。
            legal_hand = tuple(spec for i, spec in enumerate(hand) if i in playable)
            if legal_hand:
                fallback_state = replace(
                    state, hand=legal_hand, hand_size=max(len(legal_hand), 1)
                )
                retry = expectimax_with_stats(fallback_state, leaf, config=config)
                index = (
                    _hand_action(hand, playable, retry.card)
                    if retry.card is not None
                    else None
                )
                if index is not None:
                    meta["why"] = "首搜动作不在 legal，改用 legal 手牌重搜"
                    return Decision(("play", index), meta)
            # 仍然对不上：不冒非法动作的风险，结束回合（end 在出牌阶段总是合法）。
            meta["why"] = "搜索动作与画面 legal 不一致，保守结束回合"

        if ("end",) in legal:
            return Decision(("end",), meta)
        return Decision(legal[0], meta)
