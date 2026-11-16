"""三种方案（プラン）三套打法的离线单测。

覆盖：plans.json 数据、LessonPolicy 按 plan 切 buff 优先级 / early_buff_turns /
非凡窗口、缺省与未知 plan 回退、policy.json produce.plan 读取、模拟器
greedy_policy 按方案选牌。
"""

from __future__ import annotations

import json
from pathlib import Path

from gkagent.data.plans import (
    DEFAULT_PLAN,
    PlanLibrary,
    default_plan_library,
    normalize_plan,
)
from gkagent.policy.lesson import LessonPolicy
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim, greedy_policy
from gkagent.vision.lesson import LessonCard, LessonState

ROOT = Path(__file__).resolve().parents[1]
PLANS_PATH = ROOT / "data" / "knowledge" / "plans.json"


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


def _policy(tmp_path: Path, **kwargs) -> LessonPolicy:
    """走代码默认值 + plans.json，避免仓库 policy.json 的后续调参影响断言。"""
    return LessonPolicy(params_path=tmp_path / "missing.json", **kwargs)


def _buff(
    index: int, name: str, text: str, *, cost: int = 2
) -> LessonCard:
    return _card(index, name, 0, cost, buff=True, text=text)


def _score_card(index: int = 2, *, score: int = 40, cost: int = 3) -> LessonCard:
    return _card(index, "大分牌", score, cost, text=f"打分+{score}")


# --------------------------------------------------------------------- 数据
def test_plans_json_priority_matches_game_rules() -> None:
    raw = json.loads(PLANS_PATH.read_text(encoding="utf-8"))
    assert raw["sense"]["buff_priority"] == ["好调", "集中"]
    assert raw["logic"]["buff_priority"] == ["好印象", "やる気"]
    assert raw["anomaly"]["buff_priority"] == ["温存", "強気", "全力"]
    assert raw["sense"]["early_buff_turns"] == 3
    assert raw["logic"]["early_buff_turns"] == 4
    assert raw["anomaly"]["early_buff_turns"] == 2
    assert raw["anomaly"]["score_after_buff"] is False

    library = PlanLibrary.load()
    assert library.get("sense").cn == "感性"
    assert library.get("logic").buff_priority == ("好印象", "やる気")
    assert library.get("anomaly").buff_priority[0] == "温存"
    # 未知方案退回 sense，不抛异常
    assert library.get("bogus").key == DEFAULT_PLAN
    assert normalize_plan("感性") == "sense"
    assert normalize_plan("unknown") is None


# --------------------------------------------------------------------- 文本策略
def test_sense_plan_plays_condition_before_focus(tmp_path: Path) -> None:
    state = _state(
        [_buff(0, "集中", "集中+3"), _buff(1, "好调", "好调+2"), _score_card()],
        turns_left=5,
        stamina=20,
    )
    action = _policy(tmp_path, plan="sense").decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "好调"


def test_logic_plan_plays_impression_before_focus(tmp_path: Path) -> None:
    state = _state(
        [
            _buff(0, "集中", "集中+3"),
            _buff(1, "好印象", "好印象+2"),
            _score_card(),
        ],
        turns_left=5,
        stamina=20,
    )
    action = _policy(tmp_path, plan="logic").decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "好印象"


def test_anomaly_plan_prefers_save_and_cashes_out_last_two_turns(tmp_path: Path) -> None:
    cards = [
        _buff(0, "强气", "強気+1"),
        _buff(1, "温存", "温存+1"),
        _score_card(),
    ]
    early = _policy(tmp_path, plan="anomaly").decide(
        _state(cards, turns_left=4, stamina=20)
    )
    assert early.card is not None and early.card.name == "温存"

    for turns in (2, 1):
        late = _policy(tmp_path, plan="anomaly").decide(
            _state(cards, turns_left=turns, stamina=20)
        )
        assert late.kind == "card"
        assert late.card is not None and late.card.name == "大分牌"


def test_anomaly_does_not_blindly_buff_early_without_save(tmp_path: Path) -> None:
    """非凡早期没有温存时不要先铺強気/全力，先把分数打出去。"""
    state = _state(
        [_buff(0, "强气", "強気+1"), _score_card()],
        turns_left=4,
        stamina=20,
    )
    action = _policy(tmp_path, plan="anomaly").decide(state)
    assert action.card is not None and action.card.name == "大分牌"


def test_three_plans_pick_different_buffs_on_same_hand(tmp_path: Path) -> None:
    cards = [
        _buff(0, "好调", "好调+2"),
        _buff(1, "好印象", "好印象+2"),
        _buff(2, "温存", "温存+1"),
        _score_card(3),
    ]
    state = _state(cards, turns_left=5, stamina=20)
    picks = {
        plan: _policy(tmp_path, plan=plan).decide(state).card.name
        for plan in ("sense", "logic", "anomaly")
    }
    assert picks == {"sense": "好调", "logic": "好印象", "anomaly": "温存"}


# --------------------------------------------------------------------- 缺省/回退
def test_plan_defaults_to_sense(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    assert policy.plan == "sense"
    assert policy.describe()["plan"] == "sense"
    assert policy.early_buff_turns == 3
    # 仓库 policy.json 当前打的是感性
    raw = json.loads((ROOT / "data" / "knowledge" / "policy.json").read_text(encoding="utf-8"))
    assert raw["produce"]["plan"] == "sense"
    assert LessonPolicy().plan == "sense"


def test_unknown_plan_falls_back_to_sense(tmp_path: Path) -> None:
    state = _state(
        [_buff(0, "集中", "集中+3"), _buff(1, "好调", "好调+2"), _score_card()],
        turns_left=5,
        stamina=20,
    )
    unknown = _policy(tmp_path, plan="not-a-plan")
    assert unknown.plan == "sense"
    assert unknown.decide(state).card.name == _policy(tmp_path, plan="sense").decide(state).card.name

    # params 里写未知方案同样退回 sense
    assert _policy(tmp_path, params={"plan": "wat"}).plan == "sense"


def test_policy_json_produce_plan_is_read(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps({"version": 1, "produce": {"plan": "logic"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    policy = LessonPolicy(params_path=path)
    assert policy.plan == "logic"
    assert policy.describe_plan()["cn"] == "理性"
    assert policy.buff_priority == ("好印象", "やる気")


# --------------------------------------------------------------------- 模拟器
def _sim(plan: str, hand: list[CardSpec], *, turns: int = 5) -> LessonSim:
    sim = LessonSim(
        [CardSpec("垫", 0, 0)],
        LessonConfig(turns=turns, stamina=20, target_clear=1, hand_size=2, plan=plan),
        rng_seed=3,
    )
    sim.hand = list(hand)
    sim.deck = []
    sim.discard = []
    return sim


def test_greedy_policy_buff_order_follows_plan() -> None:
    hand = [CardSpec("集中", 1, 0, focus=3), CardSpec("好印象", 1, 0, impression=3)]
    assert greedy_policy(_sim("sense", hand)) == 0
    assert greedy_policy(_sim("logic", hand)) == 1


def test_greedy_policy_anomaly_saves_then_cashes_last_turn() -> None:
    hand = [
        CardSpec("温存", 1, 0, preservation=1),
        CardSpec("全力值", 1, 0, full_power_point=5),
        CardSpec("大分", 2, 20),
    ]
    assert greedy_policy(_sim("anomaly", hand, turns=5)) == 0
    assert greedy_policy(_sim("anomaly", hand, turns=1)) == 2


def test_lesson_sim_plan_field_defaults_and_falls_back() -> None:
    default = LessonSim([CardSpec("垫", 0, 0)], LessonConfig(turns=1, stamina=5, target_clear=1))
    assert default.plan == "sense"
    unknown = LessonSim(
        [CardSpec("垫", 0, 0)],
        LessonConfig(turns=1, stamina=5, target_clear=1, plan="wat"),
    )
    assert unknown.plan == "sense"
    assert default_plan_library().get("logic").early_buff_turns == 4


def test_produce_config_plan_field_and_forwarding() -> None:
    from gkagent.sim.produce import ProduceConfig

    assert ProduceConfig().plan == "sense"
    assert ProduceConfig(plan="logic").plan == "logic"
    assert ProduceConfig().audition_coefficient == 4.11  # 旧字段不受影响


def test_same_deck_scores_differ_by_plan() -> None:
    """同一牌组/同一 seed：三套 buff 顺序必须打出不同的终试分。"""
    deck = [
        CardSpec("好调", 1, 0, condition=3),
        CardSpec("集中", 1, 0, focus=3),
        CardSpec("好印象", 1, 0, impression=3),
        CardSpec("温存", 1, 0, preservation=1),
        CardSpec("全力值", 1, 0, full_power_point=5),
        CardSpec("强气", 1, 0, strong_level=1),
        CardSpec("大分", 3, 30),
        CardSpec("中分", 2, 12),
    ]
    scores = {}
    for plan in ("sense", "logic", "anomaly"):
        sim = LessonSim(
            deck,
            LessonConfig(turns=6, stamina=30, target_clear=1, hand_size=3, plan=plan),
            rng_seed=0,
        )
        scores[plan] = sim.run(greedy_policy)[0]
    assert len(set(scores.values())) >= 2, scores
