"""M1 考试 RNG 消费图回归（阶段1）。

覆盖：
* 原语 xorshift32(13,17,5) / range / signed_key（每调用恰 1 次推进）；
* 消费节点：create_deck_random（1 range，空堆 width=0 仍消费）、move_search_random（2nf）、
  move_pick_random（1+nf）、reshuffle（grave−1）、panic（每手牌 1 range）、support_rolls；
* **探针①黄金回归**（tests/fixtures/m1_probe_p1.json，源自 data/_engine_probe_rng_p1.jsonl）：
  逐动作消费次数精确 + 生成插入位置命中（首调用 range(0, 插入前牌堆长)）；
* **rinami W7/W9 实机 rng 序列回归**（tests/fixtures/m1_rinami_trace.json，源自 data/_rinami_live）：
  从 opening 状态按动作序列重放，每决策点 xorshift32 state 与 data.rng 逐位匹配。
  牌区上下文 oracle 锚定（引擎可选 oracle）；消费次数由 clean-room 消费图按牌区计算，
  支援掷点余数 oracle 锚定（support_rolls 公式另有独立预测回归）。W9 饮料步标 owned-by-drinks。
* 全知门 opt-in（use_graph）：默认关逐位不变；打开后机制题恢复计数。
* 饮料消费 hook 扩展点（M6，接口不实现）。

铁律：不拷 AGPL/参考源码；引擎只作 oracle；旧投稿零改动。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.sim import rng_graph as rg
from gkagent.sim import exam_risk

FIXTURES = Path(__file__).parent / "fixtures"
MASK = 0xFFFFFFFF


def _xs(s: int) -> int:
    s ^= (s << 13) & MASK
    s ^= s >> 17
    s ^= (s << 5) & MASK
    return s & MASK


# --------------------------------------------------------------------------- 原语
def test_xorshift32_matches_reference_iteration() -> None:
    s = 123456789
    for _ in range(1000):
        assert rg.xorshift32_next(s) == _xs(s)
        s = _xs(s)


def test_range_and_signed_key_each_advance_once() -> None:
    stream = rg.RngStream(4255182655)
    start = stream.state
    v = stream.range(0, 20)
    assert v == ((start * 20) >> 32)
    assert stream.state == _xs(start)
    assert stream.calls == 1
    s2 = stream.state
    k = stream.signed_key()
    assert k == (s2 ^ 0x80000000)
    assert stream.state == _xs(s2)
    assert stream.calls == 2


def test_range_width_zero_still_consumes() -> None:
    stream = rg.RngStream(999)
    start = stream.state
    assert stream.range(0, 0) == 0  # 空堆 width=0 → index 0
    assert stream.state == _xs(start)  # 仍推进 1 次
    assert stream.calls == 1


def test_rng_steps_between() -> None:
    assert rg.rng_steps_between(100, 100) == 0
    s = 100
    for n in (1, 5, 50):
        t = s
        for _ in range(n):
            t = _xs(t)
        assert rg.rng_steps_between(s, t) == n
    assert rg.rng_steps_between(100, 200, cap=10) is None


# --------------------------------------------------------------------------- 消费节点
def test_create_deck_random_single_and_empty() -> None:
    g = rg.ConsumptionGraph()
    stream = rg.RngStream(3038551537)
    idx = rg.create_deck_random(stream, 20, 1, g)
    assert len(idx) == 1
    assert idx[0] == ((3038551537 * 20) >> 32)
    assert g.total == 1
    # 空堆
    s2 = rg.RngStream(7)
    g2 = rg.ConsumptionGraph()
    assert rg.create_deck_random(s2, 0, 1, g2) == [0]
    assert g2.total == 1


def test_move_search_random_2nf_when_playing() -> None:
    g = rg.ConsumptionGraph()
    stream = rg.RngStream(1366826046)
    keys = rg.move_search_random(stream, 5, playing=True, graph=g)
    assert len(keys) == 5
    assert g.total == 10  # 5 丢弃 + 5 排序
    # 非出牌上下文只 nf
    g2 = rg.ConsumptionGraph()
    rg.move_search_random(rg.RngStream(1), 5, playing=False, graph=g2)
    assert g2.total == 5


def test_move_pick_random_1_plus_nf() -> None:
    g = rg.ConsumptionGraph()
    stream = rg.RngStream(3418199402)
    count, keys = rg.move_pick_random(stream, 1, 1, 1, g)
    assert len(keys) == 1
    assert g.total == 2  # 1 count roll + 1 key
    assert 1 <= count <= 1


def test_reshuffle_grave_minus_one() -> None:
    for grave in (0, 1, 8, 12, 18):
        g = rg.ConsumptionGraph()
        n = rg.reshuffle(rg.RngStream(1799527681), grave, g)
        assert n == max(0, grave - 1)
        assert g.total == max(0, grave - 1)


def test_panic_one_range_per_hand_card() -> None:
    g = rg.ConsumptionGraph()
    stream = rg.RngStream(2026)
    fixes = rg.panic_tick(stream, 3, graph=g)
    assert len(fixes) == 3
    assert g.total == 3
    assert all(f in rg.PANIC_STAMINA_CANDIDATES for f in fixes)
    # 空手牌 0 消费
    g2 = rg.ConsumptionGraph()
    assert rg.panic_tick(rg.RngStream(1), 0, graph=g2) == []
    assert g2.total == 0


def test_support_rolls_predictive() -> None:
    # 3 张可强化牌 × 2 合格支援（Dance），无命中 → 6 掷点
    supports = [{"id": "a", "filter": 2, "permil": 0}, {"id": "b", "filter": 2, "permil": 0},
                {"id": "c", "filter": 3, "permil": 0}]
    cards = [("x", 0), ("y", 0), ("z", 0)]
    g = rg.ConsumptionGraph()
    used: list = []
    planned, rolls = rg.support_rolls(rg.RngStream(1), cards, supports, 2,
                                      used=used, upgradeable=lambda c: True, graph=g)
    assert rolls == 6  # 3 × 2（filter=3 的 c 不掷）
    assert g.total == 6
    assert planned == []
    # 不可强化整张跳过
    g2 = rg.ConsumptionGraph()
    _, rolls2 = rg.support_rolls(rg.RngStream(1), cards, supports, 2,
                                 upgradeable=lambda c: c[0] != "y", graph=g2)
    assert rolls2 == 4  # x,z × 2
    # 命中后本回合不再参与
    sup_hit = [{"id": "a", "filter": 0, "permil": 1000}]
    g3 = rg.ConsumptionGraph()
    used3: list = []
    planned3, rolls3 = rg.support_rolls(rg.RngStream(1), cards, sup_hit, 1,
                                        used=used3, upgradeable=lambda c: True, graph=g3)
    assert rolls3 == 1  # 第一张命中后 a 已用，后两张跳过
    assert len(planned3) == 1


# --------------------------------------------------------------------------- 探针①黄金回归
@pytest.fixture(scope="module")
def probe() -> dict:
    return json.loads((FIXTURES / "m1_probe_p1.json").read_text(encoding="utf-8"))


def test_probe_primitive_consumption_exact(probe: dict) -> None:
    # 逐动作：rng_before 正向迭代 consumption 步 == rng_after（unknown=0）
    for s in probe["all_steps"]:
        assert s["consumption"] is not None
        assert rg.rng_steps_between(s["rng_before"], s["rng_after"]) == s["consumption"]


def test_probe_create_insertion_first_call_hit(probe: dict) -> None:
    # 生成入牌堆随机位 = 恰 1 次 range(0, 插入前牌堆长)，且是该效果首次 RNG 调用
    assert len(probe["create_events"]) >= 12
    for c in probe["create_events"]:
        width = c["deck_len_before"] - c["draws_before_create"]
        stream = rg.RngStream(c["rng_before"])
        g = rg.ConsumptionGraph()
        idx = rg.create_deck_random(stream, width, 1, g)
        assert idx[0] == c["index"], (c["tag"], c["i"])
        assert g.total == 1
        assert 0 in c["pred_steps"]  # 首调用命中


def test_probe_reshuffle_exact(probe: dict) -> None:
    # nosup skip 局：消费 = (弃手牌后 grave 数) − 1（重洗回合），否则 0
    assert len(probe["reshuffle_events"]) >= 20
    for e in probe["reshuffle_events"]:
        g = rg.ConsumptionGraph()
        if e["grave_reset"]:
            n = rg.reshuffle(rg.RngStream(1), e["grave_count_after_discard"], g)
            assert n == e["consumption"] == e["grave_count_after_discard"] - 1
        else:
            assert e["consumption"] == 0


def test_probe_move_034_consumption(probe: dict) -> None:
    # 纯移动步（无抽牌/无回合转换）：cons = 2nf
    pure = [m for m in probe["move_events"] if not m["turn_changed"]]
    assert pure
    for m in pure:
        assert m["consumption"] % 2 == 0
        nf = m["consumption"] // 2
        g = rg.ConsumptionGraph()
        rg.move_search_random(rg.RngStream(1), nf, playing=True, graph=g)
        assert g.total == m["consumption"]


def test_probe_zero_rng_mechanism_variants(probe: dict) -> None:
    # type59/38 确定式变体 0 RNG（exam_risk 误报可放宽）
    assert probe["zero_steps"]
    for z in probe["zero_steps"]:
        assert z["consumption"] == 0


# --------------------------------------------------------------------------- rinami 实机 rng 回归
@pytest.fixture(scope="module")
def rinami() -> dict:
    return json.loads((FIXTURES / "m1_rinami_trace.json").read_text(encoding="utf-8"))


def _run_action_events(stream: rg.RngStream, action: dict) -> int:
    """按消费图计算一个动作的消费次数（支援余数 oracle 锚定），返回总消费。"""
    total = 0
    for kind, count, params in action["events"]:
        g = rg.ConsumptionGraph()
        if kind == "create_deck_random":
            rg.create_deck_random(stream, params["deck_len"], 1, g)
        elif kind == "move_search_random":
            rg.move_search_random(stream, params["nf"], playing=params["playing"], graph=g)
        elif kind == "move_pick_random":
            rg.move_pick_random(stream, params["nf"], params["pick_min"], params["pick_max"], g)
        elif kind == "reshuffle":
            rg.reshuffle(stream, params["grave_count"], g)
        elif kind == "support":
            # 支援掷点余数 oracle 锚定（公式见 test_support_rolls_predictive + 探针①）
            for _ in range(count):
                stream.advance()
            g.record("support", count)
        else:
            raise AssertionError(f"unknown event kind {kind}")
        assert g.total == count, (kind, g.total, count)
        total += g.total
    return total


@pytest.mark.parametrize("w", ["W7", "W9"])
def test_rinami_rng_sequence_bit_exact(rinami: dict, w: str) -> None:
    game = rinami[w]
    stream = rg.RngStream(game["opening_rng"])
    actions = game["actions"]
    matched = 0
    drink_steps = 0
    for a in actions:
        # 决策点状态（动作前）逐位对实机 data.rng
        assert stream.state == a["live_rng"], (w, a["k"], stream.state, a["live_rng"])
        matched += 1
        if a["is_drink"]:
            # 饮料消费入口 owned-by-drinks（M6）：按 oracle 次数推进，不声称图建模
            drink_steps += 1
            for _ in range(a["oracle_cons"]):
                stream.advance()
        else:
            cons = _run_action_events(stream, a)
            assert cons == a["oracle_cons"], (w, a["k"], cons, a["oracle_cons"])
    assert matched == len(actions)
    if w == "W7":
        assert drink_steps == 0  # W7 零饮料，全序列匹配
        assert matched == 27
    else:
        assert drink_steps == 4  # W9 四饮料步标 owned-by-drinks
        assert matched == 45


def test_rinami_w9_non_drink_decisions_match(rinami: dict) -> None:
    # W9 DoD（lead scope）：非饮料决策步逐位匹配
    game = rinami["W9"]
    stream = rg.RngStream(game["opening_rng"])
    non_drink = 0
    for a in game["actions"]:
        if not a["is_drink"]:
            assert stream.state == a["live_rng"]
            non_drink += 1
        if a["is_drink"]:
            for _ in range(a["oracle_cons"]):
                stream.advance()
        else:
            _run_action_events(stream, a)
    assert non_drink == 41  # 45 决策 − 4 饮料


# --------------------------------------------------------------------------- 全知门 opt-in
def test_gate_default_off_bit_identical() -> None:
    # 默认关：use_graph=False 与旧 deck_rng_risks 逐位一致
    deck = [["p_card-01-men-2_099", 1], ["p_card-01-men-3_034", 0], ["p_card-01-men-2_037", 1]]
    old = exam_risk.deck_rng_risks(deck)
    assert exam_risk.deck_rng_risks(deck, use_graph=False) == old
    assert exam_risk.known_info_ok(deck) == exam_risk.known_info_ok(deck, use_graph=False)


def test_gate_graph_relaxes_modeled_mechanisms() -> None:
    index = {
        "p_card-01-men-2_099": frozenset({"ExamCardCreateId"}),  # modeled
        "p_card-01-men-3_034": frozenset({"ExamCardMove"}),  # modeled
        "p_card-03-act-3_065": frozenset({"ExamSearchPlayCardStaminaConsumptionChange"}),  # 0 RNG
        "p_card-01-men-3_006": frozenset({"ExamCardSearchEffectPlayCountBuff"}),  # 0 RNG
        "p_card-xx-create-search": frozenset({"ExamCardCreateSearch"}),  # unmodeled
    }
    deck = [["p_card-01-men-2_099", 1], ["p_card-01-men-3_034", 0],
            ["p_card-03-act-3_065", 0], ["p_card-01-men-3_006", 1]]
    # 旧口径：全风险
    assert not exam_risk.known_info_ok(deck, index=index)
    # 图口径：全 modeled → 恢复全知
    assert exam_risk.known_info_ok(deck, index=index, use_graph=True)
    assert exam_risk.deck_rng_risks(deck, index=index, use_graph=True) == []
    # 含 unmodeled（随机池生成）仍风险
    deck2 = deck + [["p_card-xx-create-search", 0]]
    assert not exam_risk.known_info_ok(deck2, index=index, use_graph=True)
    risks = exam_risk.deck_rng_risks(deck2, index=index, use_graph=True)
    assert risks[0]["card_id"] == "p_card-xx-create-search"
    assert risks[0]["effects"] == ["ExamCardCreateSearch"]


def test_classify_effect() -> None:
    assert rg.classify_effect("ExamCardCreateId") == "modeled"
    assert rg.classify_effect("ExamCardMove") == "modeled"
    assert rg.classify_effect("ExamPanic") == "modeled"
    assert rg.classify_effect("ExamCardCreateSearch") == "unmodeled"
    assert rg.classify_effect("ExamLessonBuff") == "zero"


# --------------------------------------------------------------------------- 饮料 hook（M6 接口）
def test_drink_hook_extension_point() -> None:
    # 默认无 hook：consume_drink 返回空（阶段1 不建模饮料消费）
    rg.register_drink_hook(None)
    assert rg.consume_drink("pdrink_00-2-010", {}, rg.RngStream(1)) == []

    class _Hook:
        def consume_drink(self, drink_id, context, stream):
            stream.advance()
            return [rg.RngEvent("drink", 1, {"drink_id": drink_id})]

    rg.register_drink_hook(_Hook())
    try:
        s = rg.RngStream(1)
        evs = rg.consume_drink("pdrink_00-2-010", {}, s)
        assert len(evs) == 1 and evs[0].kind == "drink"
        assert s.calls == 1
    finally:
        rg.register_drink_hook(None)


# --------------------------------------------------------------------------- ledger
def test_consumption_graph_states_from() -> None:
    g = rg.ConsumptionGraph()
    g.record("reshuffle", 7)
    g.record("create_deck_random", 1)
    g.record("support", 4)
    assert g.total == 12
    states = g.states_from(3059505168)
    s = 3059505168
    expect = []
    for n in (7, 1, 4):
        for _ in range(n):
            s = _xs(s)
        expect.append(s)
    assert states == expect
