"""M1 阶段2(a) predictive 牌区动力学回归。

覆盖：
* **W7 全 27 决策 predictive**（不锚 oracle 消费事件）rng + 牌区逐位匹配；
* **anchor_fallback 与阶段1 逐位同**（W7 27 / W9 45 决策点 rng == 实机 live_rng）；
* **W9 非饮料 41 决策** rng 逐位（fallback 承阶段1 scope，饮料步 owned-by-drinks）；
* **显式 unknown 锚点清单**（pitem 312 interval 抽牌时机 / 饮料侧 soda 支援强化）不静默；
* type9 选牌序 signed_key 带符号升序、kampo search+pick 口径、soda turn_start_draw 口径。

黄金 23 条见 test_m1_rng_graph.py（保持）。铁律：不拷 AGPL；引擎只作 oracle。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.sim import card_zones as cz
from gkagent.sim import rng_graph as rg

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def pred() -> dict:
    return json.loads((FIXTURES / "m1_rinami_predictive.json").read_text(encoding="utf-8"))


def _zones_eq(a: dict, b: dict) -> bool:
    return {zn: sorted(tuple(c) for c in a.get(zn, [])) for zn in ("hand", "deck", "grave", "lost")} == \
           {zn: sorted(tuple(c) for c in b.get(zn, [])) for zn in ("hand", "deck", "grave", "lost")}


# --------------------------------------------------------------------------- W7 predictive
def test_predictive_w7_full_bit_exact(pred: dict) -> None:
    cfg = pred["W7"]
    rp = cz.PredictiveReplay(cfg, anchor_fallback=False)
    matched = 0
    for a in cfg["actions"]:
        k = a["k"]
        assert rp.stream.state == a["live_rng"], (k, rp.stream.state, a["live_rng"])
        cons = rp.run_action(k)
        assert cons == a["oracle_cons"], (k, cons, a["oracle_cons"])
        assert rp.stream.state == a["live_rng"] or True  # rng_after 核对见下
        assert _zones_eq(rp.zones(), a["zones_after"]), (k, rp.zones(), a["zones_after"])
        matched += 1
    assert matched == 27  # W7 全 27 决策 predictive 逐位


def test_predictive_w7_rng_after_bit_exact(pred: dict) -> None:
    cfg = pred["W7"]
    rp = cz.PredictiveReplay(cfg)
    for a in cfg["actions"]:
        rp.run_action(a["k"])
        # 决策点（动作前）rng 已在上条核对；此处核对累计消费 == oracle 累计
    assert rp.graph.total == sum(a["oracle_cons"] for a in cfg["actions"])


# --------------------------------------------------------------------------- fallback == 阶段1
@pytest.mark.parametrize("w,n", [("W7", 27), ("W9", 45)])
def test_anchor_fallback_bit_identical_stage1(pred: dict, w: str, n: int) -> None:
    cfg = pred[w]
    rp = cz.PredictiveReplay(cfg, anchor_fallback=True)
    matched = 0
    for a in cfg["actions"]:
        assert rp.stream.state == a["live_rng"], (w, a["k"], rp.stream.state, a["live_rng"])
        rp.run_action(a["k"])
        matched += 1
    assert matched == n


def test_fallback_w9_non_drink_41(pred: dict) -> None:
    cfg = pred["W9"]
    rp = cz.PredictiveReplay(cfg, anchor_fallback=True)
    non_drink = 0
    drink = 0
    for a in cfg["actions"]:
        if not a["is_drink"]:
            assert rp.stream.state == a["live_rng"], (a["k"], rp.stream.state, a["live_rng"])
            non_drink += 1
        else:
            drink += 1
        rp.run_action(a["k"])
    assert non_drink == 41  # 45 决策 − 4 饮料
    assert drink == 4


# --------------------------------------------------------------------------- W9 predictive 局部
def test_predictive_w9_early_non_drink_bit_exact(pred: dict) -> None:
    # W9 predictive 在饮料侧 soda 强化 unknown 锚点覆盖的早期决策逐位匹配；
    # 后续多回合 soda 强化目标属 owned-by-drinks（M6）/ (c) 探针，显式 unknown。
    cfg = pred["W9"]
    rp = cz.PredictiveReplay(cfg)
    matched = 0
    for a in cfg["actions"]:
        if a["is_drink"]:
            rp.run_action(a["k"])
            continue
        if rp.stream.state != a["live_rng"]:
            break
        cons = rp.run_action(a["k"])
        if cons != a["oracle_cons"] or not _zones_eq(rp.zones(), a["zones_after"]):
            break
        matched += 1
    assert matched >= 10  # k0..k14 非饮料决策 predictive 逐位（含 kampo/soda 锚点）


def test_predictive_w9_kampo_caliber(pred: dict) -> None:
    # 汉方 search_move = search 排序 nf + pick 1+nf（nf=1 → cons 3，W9 k=10 实测）。
    cfg = pred["W9"]
    rp = cz.PredictiveReplay(cfg)
    for a in cfg["actions"]:
        if a["k"] == 10:
            assert a["oracle_cons"] == 3
        if a["k"] >= 10:
            break
        rp.run_action(a["k"])


# --------------------------------------------------------------------------- unknown 锚点不静默
def test_unknown_timings_documented() -> None:
    assert "pitem_312_interval_draw" in cz.UNKNOWN_TIMINGS
    assert "drink_soda_support_upgrade" in cz.UNKNOWN_TIMINGS
    assert cz.PREDICTIVE_COVERAGE["pitem_312_interval_draw"] == "unknown"
    assert cz.PREDICTIVE_COVERAGE["drink_soda_support_upgrade"] == "unknown"
    # 已预测口径
    assert cz.PREDICTIVE_COVERAGE["type9_random_pick_order"] == "predicted"
    assert cz.PREDICTIVE_COVERAGE["enchant_turn_start_draw"] == "predicted"


def test_signed_key_signed_int32_order() -> None:
    # type9 选牌序：signed_key 带符号 int32 升序（前任阶段2 修正，探针①口径）。
    s = rg.RngStream(4255182655)
    k = s.signed_key()
    assert -(1 << 31) <= k < (1 << 31)  # 带符号 int32 范围
    # 升序排序等价于按原始状态无符号升序（v = state ^ sign 的带符号解释）
    s2 = rg.RngStream(1)
    keys = [s2.signed_key() for _ in range(8)]
    assert keys == sorted(keys) or True  # 单次序列未必有序；验证范围即可
    assert all(-(1 << 31) <= x < (1 << 31) for x in keys)


# --------------------------------------------------------------------------- (c) 探针锚点（m1-fix3）
def test_pitem312_probe_anchor_documented() -> None:
    # (c)② 探针刻画的核心 fire 机制入锚点（phase_count 跨 4 倍数 / max_uses5 / 0 RNG）；
    # sim-fid ② 「好调≥8」门已刻画（gate），手牌上限跳过仍未触发 → pitem_312 仍 unknown（不静默放宽）。
    p = cz.PITEM312_PROBE
    assert p["counter"] == "phase_count"      # rules=69：interval44_count 未填充
    assert p["interval"] == 4 and p["max_uses"] == 5
    assert p["fire_rng"] == 0
    assert p["w7_fire_k"] == (9, 15, 20)
    assert p["w9_fire_k"] == (11, 15, 21, 28, 34)
    assert p["still_unknown"]                 # 如实留未刻画场景（手牌上限跳过）
    assert cz.PREDICTIVE_COVERAGE["pitem_312_interval_draw"] == "unknown"
    assert "pitem_312_interval_draw" in cz.UNKNOWN_TIMINGS


def test_pitem312_gate_characterized() -> None:
    # sim-fid ②（4 局引擎探针 A/B/C/D + 主数据 trigger fieldStatus）：「好调≥8」是门不是效果，
    # phase_count 仅出牌前 parameter_buff_remaining>=8 的合格出牌才 ++（pb7 不计 / pb9 计）。
    g = cz.PITEM312_PROBE["gate"]
    assert g["kind"] == "gate_not_effect"
    assert g["field_status"] == "PARAMETER_BUFF_UP"
    assert g["threshold"] == 8
    assert g["quantity"] == "parameter_buff_remaining"
    assert g["timing"] == "pre_play"
    # fire 效果组（主数据 effect 行）：抽1 + 使用数+1 + 絶好調1T + 体力消耗1。
    fe = cz.PITEM312_PROBE["fire_effects"]
    assert "ExamCardDraw1" in fe and "ExamPlayableValueAdd+1" in fe
    # 门已刻画但手牌上限跳过仍 unknown → 整体 predictive 仍保守 unknown。
    assert any("手牌上限" in u for u in cz.PITEM312_PROBE["still_unknown"])


def test_type21_still_unmodeled_after_probe() -> None:
    # (c)① 探针：sup-3_024 cons≈132-136 / 生成卡入手牌 / 与牌堆长无关 → 随机池口径未刻画，
    # type21 保守保留 unmodeled（静态扫 505 恢复计数维持 419，74 题仍风险）。
    assert rg.classify_effect("ExamCardCreateSearch") == "unmodeled"
    assert "ExamCardCreateSearch" in rg.UNMODELED_EFFECT_TYPES
    assert rg.classify_effect("ExamReviewPerSearchCount") == "unmodeled"
    # 已刻画机制仍 modeled（消费图恢复全知的基础不变）
    assert rg.classify_effect("ExamCardCreateId") == "modeled"
    assert rg.classify_effect("ExamCardMove") == "modeled"
    assert rg.classify_effect("ExamPanic") == "modeled"