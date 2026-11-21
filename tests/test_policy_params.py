"""出牌参数外置（data/knowledge/policy.json）的离线单测。

覆盖：默认参数行为不变、policy.json 覆盖预算、坏 JSON 回退、describe 完整、
buff_first 开关、最后回合/分数没读到等参数的接线。
"""

from __future__ import annotations

import json
from pathlib import Path

from gkagent.policy.lesson import LessonPolicy
from gkagent.vision.lesson import LessonCard, LessonState

DEFAULTS = dict(LessonPolicy.DEFAULT_PARAMS)
REQUIRED_KEYS = {
    "reserve_per_turn",
    "negligible",
    "min_gain",
    "buff_first",
    "buff_max_cost_ratio",
    "buff_score_guard",
    "last_turn_max_total",
    "unknown_score_fallback",
}


def _card(
    index: int,
    name: str,
    score: int | None,
    cost: int | None,
    *,
    buff: bool = False,
    text: str = "",
) -> LessonCard:
    return LessonCard(
        index=index,
        box=(index * 200, 900, 190, 232),
        point=(index * 200 + 95, 1000),
        name=name,
        score=score,
        cost=cost,
        buff=buff,
        text=text,
    )


def _state(cards, **kwargs) -> LessonState:
    return LessonState(cards=tuple(cards), **kwargs)


def _policy_without_file(tmp_path: Path, **kwargs) -> LessonPolicy:
    """强制走类默认值，避免受仓库里 policy.json 的后续调参影响。"""
    return LessonPolicy(params_path=tmp_path / "missing.json", **kwargs)


def _write_policy(path: Path, lesson: dict) -> None:
    path.write_text(
        json.dumps({"version": 1, "lesson": lesson}, ensure_ascii=False),
        encoding="utf-8",
    )


# --------------------------------------------------------------------- 默认行为
def test_default_params_match_legacy_behaviour(tmp_path: Path) -> None:
    """默认参数 = 外置前的硬编码行为（回归 test_lesson 的关键场景）。"""
    policy = _policy_without_file(tmp_path)
    assert policy.describe() == DEFAULTS

    # 84 分 / 6 体力的牌不能因为"把分数当费用"被跳过
    action = policy.decide(
        _state(
            [_card(0, "平衡感", 2, 2), _card(1, "聊天时间", 84, 6), _card(2, "表现的基础", 4, 0)],
            turns_left=9,
            stamina=28,
        )
    )
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "聊天时间"

    # 没有正收益的牌也不再 SKIP（2026-11-21 用户规则：读不到价值不算跳过理由）
    action = _policy_without_file(tmp_path).decide(
        _state([_card(0, "元气", 0, 2), _card(1, "护盾", 0, 3)], turns_left=3, stamina=20)
    )
    assert action.kind == "card"

    # 分数全没读到 → 打最便宜的保成长
    action = _policy_without_file(tmp_path).decide(
        _state(
            [_card(0, "聊天时间", None, 6), _card(1, "表现的基础", None, 0)],
            turns_left=3,
            stamina=20,
        )
    )
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "表现的基础"


def test_policy_json_reserve_per_turn_changes_budget(tmp_path: Path) -> None:
    """policy.json 的 reserve_per_turn 直接改变预算：调紧跳过贵牌，放松才打得动。"""
    cards = [_card(0, "高价高回报", 12, 4), _card(1, "便宜稳", 5, 2)]
    state = _state(cards, turns_left=4, stamina=10)
    assert _policy_without_file(tmp_path).decide(state).card.name == "高价高回报"

    tight_path = tmp_path / "tight.json"
    _write_policy(tight_path, {"reserve_per_turn": 3.0})
    tight = LessonPolicy(params_path=tight_path)
    assert tight.describe()["reserve_per_turn"] == 3.0
    assert tight.decide(state).card.name == "便宜稳"

    # 反向：reserve 调松后，默认预算下够不着的贵牌也能被选中
    loose_state = _state(
        [_card(0, "昂贵", 9, 3), _card(1, "便宜", 2, 1)],
        turns_left=4,
        stamina=6,
    )
    assert _policy_without_file(tmp_path).decide(loose_state).card.name == "便宜"
    loose_path = tmp_path / "loose.json"
    _write_policy(loose_path, {"reserve_per_turn": 0.0})
    assert LessonPolicy(params_path=loose_path).decide(loose_state).card.name == "昂贵"


# --------------------------------------------------------------------- 坏文件
def test_broken_json_falls_back_to_defaults(tmp_path: Path) -> None:
    """坏 JSON 不崩：整份回退默认值，策略照常出牌。"""
    broken = tmp_path / "broken.json"
    broken.write_text('{"lesson": {"reserve_per_turn": 3.0', encoding="utf-8")
    policy = LessonPolicy(params_path=broken)
    assert policy.describe() == DEFAULTS

    action = policy.decide(
        _state([_card(0, "聊天时间", 84, 6), _card(1, "平衡感", 2, 2)], turns_left=9, stamina=28)
    )
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "聊天时间"


def test_invalid_field_values_fall_back_per_field(tmp_path: Path) -> None:
    """字段类型不对只丢该字段，其它合法字段仍然生效。"""
    path = tmp_path / "bad_types.json"
    _write_policy(
        path,
        {
            "reserve_per_turn": "tight",
            "buff_first": "maybe",
            "last_turn_max_total": 2,
            "unknown_score_fallback": "nope",
            "min_gain": 2.5,
        },
    )
    described = LessonPolicy(params_path=path).describe()
    assert described["min_gain"] == 2.5
    for key in ("reserve_per_turn", "buff_first", "last_turn_max_total", "unknown_score_fallback"):
        assert described[key] == DEFAULTS[key]


def test_missing_file_and_partial_file_use_defaults(tmp_path: Path) -> None:
    """文件缺失 / 字段缺失都用默认值；也接受不带 lesson 层级的扁平写法。"""
    assert LessonPolicy(params_path=tmp_path / "absent.json").describe() == DEFAULTS

    partial = tmp_path / "partial.json"
    _write_policy(partial, {"negligible": 2.0})
    described = LessonPolicy(params_path=partial).describe()
    assert described["negligible"] == 2.0
    assert described["reserve_per_turn"] == DEFAULTS["reserve_per_turn"]

    flat = tmp_path / "flat.json"
    flat.write_text(json.dumps({"min_gain": 3.0}), encoding="utf-8")
    assert LessonPolicy(params_path=flat).describe()["min_gain"] == 3.0


# --------------------------------------------------------------------- 参数接口
def test_describe_contains_all_effective_keys(tmp_path: Path) -> None:
    policy = _policy_without_file(tmp_path)
    described = policy.describe()
    assert REQUIRED_KEYS <= set(described)
    assert described == DEFAULTS

    # 返回的是拷贝，改它不能影响策略内部
    described["reserve_per_turn"] = 99.0
    assert policy.describe()["reserve_per_turn"] == DEFAULTS["reserve_per_turn"]


def test_explicit_params_override_file_and_kwargs(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    _write_policy(path, {"reserve_per_turn": 3.0, "negligible": 2.0})
    policy = LessonPolicy(
        params_path=path,
        params={"reserve_per_turn": 0.0, "min_gain": 2.0},
        min_gain=1.5,
    )
    described = policy.describe()
    assert described["reserve_per_turn"] == 0.0  # params 覆盖文件
    assert described["negligible"] == 2.0  # 文件里未覆盖的字段保留
    assert described["min_gain"] == 1.5  # 显式关键字参数优先级最高


# --------------------------------------------------------------------- 开关接线
def test_buff_first_false_never_opens_with_buff(tmp_path: Path) -> None:
    buff_card = _card(0, "好调", 0, 2, buff=True, text="好调+2")
    score_card = _card(1, "魅力的基础", 9, 5, text="打分+9")
    state = _state([buff_card, score_card], turns_left=4, stamina=20)

    assert _policy_without_file(tmp_path).decide(state).card.name == "好调"

    path = tmp_path / "no_buff.json"
    _write_policy(path, {"buff_first": False})
    action = LessonPolicy(params_path=path).decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "魅力的基础"

    # 兼容旧构造方式
    legacy = _policy_without_file(tmp_path, buff_first=False)
    assert legacy.buff_first is False


def test_last_turn_max_total_can_be_disabled(tmp_path: Path) -> None:
    state = _state(
        [_card(0, "聊天时间", 30, 6), _card(1, "击掌", 22, 4)],
        turns_left=1,
        stamina=25,
    )
    assert _policy_without_file(tmp_path).decide(state).card.name == "聊天时间"

    path = tmp_path / "efficiency.json"
    _write_policy(path, {"last_turn_max_total": False})
    action = LessonPolicy(params_path=path).decide(state)
    assert action.card is not None and action.card.name == "击掌"


def test_unknown_score_fallback_skip(tmp_path: Path) -> None:
    state = _state(
        [_card(0, "聊天时间", None, 6), _card(1, "表现的基础", None, 0)],
        turns_left=3,
        stamina=20,
    )
    assert _policy_without_file(tmp_path).decide(state).kind == "card"

    path = tmp_path / "skip_unknown.json"
    _write_policy(path, {"unknown_score_fallback": "skip"})
    # 2026-11-21 用户规则：旧 "skip" 取值已废弃——读不到分数也不许跳过
    policy = LessonPolicy(params_path=path)
    assert policy.params["unknown_score_fallback"] == "cheapest"
    action = policy.decide(state)
    assert action.kind == "card"


def test_buff_score_guard_controls_opening_buff(tmp_path: Path) -> None:
    buff_card = _card(0, "好调", 0, 2, buff=True, text="好调+2")
    score_card = _card(1, "魅力的基础", 9, 5, text="打分+9")
    # 早期回合（剩余 ≥ buff_early_turns=3）：buff 优先，这是用户打法「先攒倍率」
    early = _state([buff_card, score_card], turns_left=4, stamina=20)
    assert _policy_without_file(tmp_path).decide(early).card.name == "好调"

    # 非早期回合（剩余 2 < buff_early_turns）：guard 才会压过 buff。
    # guard 调到 0：只要分数牌有收益就先打分，不再铺 buff。
    state = _state([buff_card, score_card], turns_left=2, stamina=20)
    path = tmp_path / "no_guard.json"
    _write_policy(path, {"buff_score_guard": 0.0})
    action = LessonPolicy(params_path=path).decide(state)
    assert action.card is not None and action.card.name == "魅力的基础"
