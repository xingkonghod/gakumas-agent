"""T5 考试属性倍率（审查倍率分段 + 联动惩罚）回归。

覆盖：
1. 纯公式（分段折线 / 联动惩罚 / 归一化 / 客户端单精度取整）——合成分数表；
2. 真机配对夹具（``tests/fixtures/t5_exam_multipliers.json``）：2026-11-20 采集局
   期中和期末两场的偶像卡/剧本/三维 → 主数据分数表 → 算出的三项倍率
   （Vo 4.09 / Da 2.20 / Vi 2.60 与 6.97 / 2.85 / 4.96）；
3. 模拟器接线：``LessonConfig.attribute_bonuses`` + ``turn_attributes`` 按回合属性
   乘法与取整、回合末好印象也吃倍率、默认（不配）行为逐位不变；
4. 生产接线：屏幕读到的「舞蹈 207%」→ 搜索 ``ExpectState.attribute_coefficient``=2.07
   （真机截图 ``tests/fixtures/exam_card_overlay_20261115.png``）；
5. 主数据解析器（缺偶像卡显式报错，不静默回退常数）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.data.exam_bonus import ExamBonusResolver, ExamConfigUnavailable
from gkagent.policy.lesson import LessonPolicy, audition_coefficient
from gkagent.sim.exam_multiplier import (
    battle_bonus_score,
    calculate_bonus,
    component_permil,
    f32,
    interpolate_component,
    normalize_bonus,
    penalty_permil,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.vision.lesson import LessonCard, LessonReader, LessonState

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "t5_exam_multipliers.json"
EXAM_FRAME = ROOT / "tests" / "fixtures" / "exam_card_overlay_20261115.png"
OCR_CONFIG = ROOT / "configs" / "ocr_jp.example.yaml"
OCR_MODEL_DIR = ROOT / "data" / "models" / "ocr_jp"

# 合成分数表：节点 0 / 100（三项同值，方便手算）
SYNTHETIC_TABLE = [
    {"parameter": 0, "vocalPermil": 1000, "dancePermil": 1000, "visualPermil": 1000},
    {"parameter": 100, "vocalPermil": 2000, "dancePermil": 2000, "visualPermil": 2000},
]
SYNTHETIC_CRITERIA = {"vocal": 100, "dance": 100, "visual": 100}


def fixture_doc() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fixture_score_table(exam: dict) -> list[dict]:
    return [
        {
            "parameter": row[0],
            "vocalPermil": row[1],
            "dancePermil": row[2],
            "visualPermil": row[3],
        }
        for row in exam["config"]["score_table"]
    ]


# --------------------------------------------------------------------------- 夹具
def test_fixture_present_and_format() -> None:
    doc = fixture_doc()
    assert doc["format"] == "gkagent.exam_multipliers.v1"
    assert doc["attribute_order"] == ["vocal", "dance", "visual"]
    assert len(doc["exams"]) == 2, "2026-11-20 采集局期中/期末两场应可解析"
    # 2026-11-21 的 hkne-3-000 不在主数据快照里 → 显式跳过（生产侧用屏幕倍率）
    assert len(doc["skipped"]) == 2
    assert "i_card-hkne-3-000" in doc["skipped"][0]["reason"]


def test_captured_exam_multipliers_recompute_from_fixture() -> None:
    """夹具里两场真机考试：配置 + 三维 → 与记录的倍率逐项一致。"""
    doc = fixture_doc()
    for exam in doc["exams"]:
        bonus = calculate_bonus(
            exam["params"],
            exam["config"]["criteria"],
            fixture_score_table(exam),
            penalty_min_permil=exam["config"]["penalty_min_permil"],
            penalty_max_permil=exam["config"]["penalty_max_permil"],
        )
        expected = exam["expected"]
        assert dict(bonus.permil) == expected["permil"], exam["config"]["id"]
        assert dict(bonus.components) == expected["components"]
        assert dict(bonus.penalties) == expected["penalties"]
        assert bonus.common_permil == expected["common_permil"]


def test_captured_exam_expected_values() -> None:
    """真机采集两场的倍率值（锁定 T5 结果；换主数据/改公式会红）。"""
    doc = fixture_doc()
    mid, final = doc["exams"]
    assert mid["idol_card_id"] == "i_card-hmsz-3-018"
    assert mid["config"]["id"] == "p_exam_battle_config-vovi-01-produce-002-1-2"
    assert mid["config"]["turn"] == 9
    assert mid["played_turns"] == 9
    # 期中：Vi 187 低于审查基准 192 → 联动惩罚 103‰ → common=897 把三项一起压低
    assert mid["expected"]["penalties"] == {"vocal": 0, "dance": 0, "visual": 103}
    assert mid["expected"]["common_permil"] == 897
    assert mid["expected"]["permil"] == {"vocal": 4090, "dance": 2200, "visual": 2600}
    # 期末：Vo 842 < 961、Da 350 < 384 两项不达标
    assert final["config"]["id"] == "p_exam_battle_config-vovi-01-produce-002-2-2"
    assert final["config"]["turn"] == 11
    assert final["expected"]["penalties"]["vocal"] > 0
    assert final["expected"]["penalties"]["dance"] > 0
    assert final["expected"]["permil"] == {"vocal": 6970, "dance": 2850, "visual": 4960}


# --------------------------------------------------------------------------- 公式
def test_interpolation_between_knots_and_above_max() -> None:
    assert component_permil(0, "vocal", SYNTHETIC_TABLE) == 1000
    assert component_permil(50, "vocal", SYNTHETIC_TABLE) == 1500
    assert component_permil(100, "vocal", SYNTHETIC_TABLE) == 2000
    # 超过最大节点取最大节点值（客户端 low 为唯一命中、high 为 None）
    assert component_permil(999, "vocal", SYNTHETIC_TABLE) == 2000
    # 三项各自按自己的值插值（防止"只按 vocal 插值"的 bug：参数不同结果必须不同）
    mixed = {"parameter": 0, "vocalPermil": 0, "dancePermil": 1000, "visualPermil": 2000}
    mixed2 = {"parameter": 100, "vocalPermil": 1000, "dancePermil": 2000, "visualPermil": 3000}
    table = [mixed, mixed2]
    components = interpolate_component(50, table)
    assert components == {"vocal": 500, "dance": 1500, "visual": 2500}


def test_interpolation_rejects_bad_table() -> None:
    with pytest.raises(ValueError):
        interpolate_component(10, [{"parameter": 5, "vocalPermil": 1}])
    with pytest.raises(ValueError):
        interpolate_component(
            10,
            [
                {"parameter": 0, "vocalPermil": 1, "dancePermil": 1, "visualPermil": 1},
                {"parameter": 0, "vocalPermil": 2, "dancePermil": 2, "visualPermil": 2},
            ],
        )


def test_penalty_zero_at_or_above_baseline_and_full_below_zero() -> None:
    assert penalty_permil(320, 320) == 0
    assert penalty_permil(400, 320) == 0
    # value=0, baseline=320：min=100、max=250 → 250‰
    assert penalty_permil(0, 320) == 250
    # 线性中间：baseline=100、value=50 → 100 + 150×50/100 = 175
    assert penalty_permil(50, 100) == 175
    # baseline 0 = 不设基准
    assert penalty_permil(10, 0) == 0


def test_linked_penalty_hits_all_three_attributes() -> None:
    """联动惩罚：一项低于基准会把三项倍率一起压低（common 共享）。"""
    table = [
        {"parameter": 0, "vocalPermil": 1000, "dancePermil": 1000, "visualPermil": 1000},
        {"parameter": 1000, "vocalPermil": 10000, "dancePermil": 10000, "visualPermil": 10000},
    ]
    criteria = {"vocal": 100, "dance": 100, "visual": 100}
    healthy = calculate_bonus(
        {"vocal": 100, "dance": 100, "visual": 100}, criteria, table
    )
    short = calculate_bonus({"vocal": 100, "dance": 100, "visual": 50}, criteria, table)
    assert healthy.common_permil == 1000
    assert healthy.penalties == {"vocal": 0, "dance": 0, "visual": 0}
    assert short.common_permil < 1000
    # 视觉自己的 component 也因为值低而小；两项达标的属性也被 common 压低
    assert short.permil["vocal"] < healthy.permil["vocal"]
    assert short.permil["dance"] < healthy.permil["dance"]
    assert short.permil["visual"] < healthy.permil["visual"]


def test_normalize_bonus_rounds_up_to_ten() -> None:
    assert normalize_bonus(1000, 1000) == 2000
    assert normalize_bonus(3443, 897) == 4090
    assert normalize_bonus(3449, 1000) == 4450  # 4449 → 4450
    assert normalize_bonus(0, 1000) == 1000


def test_battle_bonus_score_matches_client_rounding() -> None:
    # 实机回放黄金值：250% 回合 アピールの基本 9 → 23（ceil，不是 round）
    assert battle_bonus_score(9, 2500) == 23
    assert battle_bonus_score(5, 2500) == 13
    assert battle_bonus_score(2, 2500) == 5
    # 精确整数不被 epsilon 影响：10×2.5=25 → f32(25)-eps → ceil 25
    assert battle_bonus_score(10, 2500) == 25
    assert battle_bonus_score(4, 2500) == 10
    # 真机采集局里 Vo=4090‰：9×4.09=36.81 → 37
    assert battle_bonus_score(9, 4090) == 37
    # 纯 buff 牌（0 分）不参与倍率
    assert battle_bonus_score(0, 4090) == 0
    assert battle_bonus_score(-5, 4090) == -5
    # f32 单精度：2.5 是精确值，4090/1000 不是
    assert f32(2.5) == 2.5
    assert f32(4.11) != 4.11


def test_calculate_bonus_rejects_negative_result() -> None:
    # 客户端会拒绝负的派生倍率（分数表里出现负值就是数据坏了）
    table = [
        {"parameter": 0, "vocalPermil": -5000, "dancePermil": 1000, "visualPermil": 1000},
        {"parameter": 100, "vocalPermil": -5000, "dancePermil": 1000, "visualPermil": 1000},
    ]
    with pytest.raises(ValueError):
        calculate_bonus({"vocal": 10, "dance": 10, "visual": 10}, SYNTHETIC_CRITERIA, table)


# --------------------------------------------------------------------------- 模拟器接线
def _bonus_sim(turns: int, *, bonuses, turn_attributes, deck, **config) -> LessonSim:
    return LessonSim(
        list(deck),
        LessonConfig(
            turns=turns,
            stamina=int(config.pop("stamina", 20)),
            target_clear=0,
            hand_size=int(config.pop("hand_size", 1)),
            plays_per_turn=1,
            attribute_bonuses=bonuses,
            turn_attributes=turn_attributes,
            **config,
        ),
        rng_seed=7,
    )


def test_sim_applies_per_turn_attribute_bonus() -> None:
    """每回合按 ExamTurnEndLog.parameterType 取倍率：Vo 2000‰ / Vi 3000‰ / Da 4000‰。"""
    deck = [CardSpec(name=f"card{i}", cost=0, score=10) for i in range(3)]
    sim = _bonus_sim(
        3,
        bonuses=(2000, 4000, 3000),  # Vo / Da / Vi
        turn_attributes=(1, 3, 2),  # 第 1 回合歌唱、第 2 视觉、第 3 舞蹈
        deck=deck,
        hand_size=1,
    )
    scores = []
    while not sim.done:
        sim.step(0)
        scores.append(sim.score)
    # 10×2.0=20、10×3.0=30、10×4.0=40 → 累计
    assert scores == [20, 50, 90]


def test_sim_turn_bonus_applies_to_end_turn_impression() -> None:
    """回合末好印象合成结算同样吃属性倍率（3 层 × 2500‰ = 8，不是 3）。"""
    deck = [CardSpec(name="impression", cost=0, score=0, impression=3)]
    sim = _bonus_sim(
        1,
        bonuses=(2500, 2500, 2500),
        turn_attributes=(1,),
        deck=deck,
        hand_size=1,
    )
    sim.step(0)  # 打满 1 张自动结束回合，回合末好印象 3×2.5 → 8
    assert sim.score == 8
    assert sim.trace[-1]["score"] == 8


def test_sim_without_bonus_fields_keeps_scalar_coefficient() -> None:
    """不配 attribute_bonuses/turn_attributes 时行为不变（旧标量倍率路径）。"""
    deck = [CardSpec(name="card", cost=0, score=10)]
    plain = LessonSim(
        list(deck), LessonConfig(turns=1, stamina=10, target_clear=0, hand_size=1), rng_seed=7
    )
    plain.step(0)
    scalar = LessonSim(
        list(deck),
        LessonConfig(
            turns=1, stamina=10, target_clear=0, hand_size=1, attribute_coefficient=2.0
        ),
        rng_seed=7,
    )
    scalar.step(0)
    assert plain.score == 10
    assert scalar.score == 20


def test_sim_requires_both_bonus_and_turn_attributes() -> None:
    """只给 attribute_bonuses 不给 turn_attributes：不启用（不猜回合属性）。"""
    deck = [CardSpec(name="card", cost=0, score=10)]
    sim = LessonSim(
        list(deck),
        LessonConfig(
            turns=1,
            stamina=10,
            target_clear=0,
            hand_size=1,
            attribute_bonuses=(4000, 4000, 4000),
            turn_attributes=(),
        ),
        rng_seed=7,
    )
    sim.step(0)
    assert sim.score == 10


def test_sim_rejects_unknown_parameter_type() -> None:
    deck = [CardSpec(name="card", cost=0, score=10)]
    sim = _bonus_sim(
        1, bonuses=(2000, 2000, 2000), turn_attributes=(9,), deck=deck, hand_size=1
    )
    with pytest.raises(ValueError):
        sim.step(0)


# --------------------------------------------------------------------------- 生产接线
def test_audition_coefficient_from_screen_multiplier() -> None:
    assert audition_coefficient(LessonState(kind="audition", multiplier=207)) == 2.07
    assert audition_coefficient(LessonState(kind="audition", multiplier=411)) == 4.11
    # 课程/训练不是考试：不用这个倍率
    assert audition_coefficient(LessonState(kind="lesson", multiplier=207)) is None
    assert audition_coefficient(LessonState(kind="audition", multiplier=None)) is None
    assert audition_coefficient(LessonState(kind="audition", multiplier=0)) is None
    # 超出 LessonReader 合理范围（10~999）的读数不用
    assert audition_coefficient(LessonState(kind="audition", multiplier=1200)) is None


def test_policy_search_state_uses_screen_multiplier() -> None:
    policy = LessonPolicy(params={"engine": "expectimax"}, params_path=ROOT / "out" / "no-such-policy.json")
    state = LessonState(
        kind="audition",
        turns_left=3,
        total_turns=9,
        stamina=10,
        score=0,
        gauge=250,
        attribute="舞蹈",
        multiplier=207,
        cards=(
            LessonCard(index=0, box=(0, 0, 0, 0), point=(0, 0), name="魅力的基础", cost=3),
        ),
    )
    built = policy._search_state(state)
    assert built is not None
    sim_state, _play_cards, _reshuffle = built
    assert sim_state.attribute_coefficient == pytest.approx(2.07)


def test_policy_search_state_without_multiplier_keeps_default() -> None:
    policy = LessonPolicy(params={"engine": "expectimax"}, params_path=ROOT / "out" / "no-such-policy.json")
    state = LessonState(
        kind="audition",
        turns_left=3,
        total_turns=9,
        stamina=10,
        score=0,
        gauge=250,
        cards=(
            LessonCard(index=0, box=(0, 0, 0, 0), point=(0, 0), name="魅力的基础", cost=3),
        ),
    )
    built = policy._search_state(state)
    assert built is not None
    sim_state, _play_cards, _reshuffle = built
    assert sim_state.attribute_coefficient == 1.0


@pytest.mark.skipif(not EXAM_FRAME.is_file(), reason="缺少考试真机帧")
@pytest.mark.skipif(not OCR_CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml")
@pytest.mark.skipif(
    not all((OCR_MODEL_DIR / name).is_file() for name in ("det.onnx", "rec.onnx", "keys.txt")),
    reason="缺少日文 OCR 模型（先跑 scripts/download_ocr_models.py）",
)
def test_real_exam_frame_multiplier_feeds_search() -> None:
    """真机考试帧「舞蹈 207%」：OCR 读数 → 搜索倍率 2.07（生产链路）。"""
    import numpy as np
    from PIL import Image

    from gkagent.vision.ocr import OcrEngine

    image = np.asarray(Image.open(EXAM_FRAME).convert("RGB"), dtype=np.uint8)
    state = LessonReader(OcrEngine()).read(image, kind="audition")
    assert state.multiplier == 207, f"真机帧倍率读数变了：{state.multiplier}"
    assert state.attribute == "舞蹈"
    policy = LessonPolicy(params={"engine": "expectimax"}, params_path=ROOT / "out" / "no-such-policy.json")
    built = policy._search_state(state)
    assert built is not None
    sim_state, _play_cards, _reshuffle = built
    assert sim_state.attribute_coefficient == pytest.approx(2.07)


# --------------------------------------------------------------------------- 主数据解析器
def _resolver_or_skip() -> ExamBonusResolver:
    resolver = ExamBonusResolver()
    if not resolver.available:
        pytest.skip("主数据 catalog.sqlite 不可用（干净 checkout 不跑）")
    return resolver


def test_resolver_resolves_captured_exam_configs() -> None:
    resolver = _resolver_or_skip()
    mid = resolver.battle_config(
        idol_card_id="i_card-hmsz-3-018", produce_id="produce-002", step_type="mid"
    )
    final = resolver.battle_config(
        idol_card_id="i_card-hmsz-3-018", produce_id="produce-002", step_type="final"
    )
    assert (mid.turn, final.turn) == (9, 11)
    assert mid.criteria == {"vocal": 320, "dance": 128, "visual": 192}
    assert (mid.penalty_min_permil, mid.penalty_max_permil) == (100, 250)
    assert len(mid.score_table) == 5
    bonus = mid.bonus({"vocal": 373, "dance": 218, "visual": 187})
    assert dict(bonus.permil) == {"vocal": 4090, "dance": 2200, "visual": 2600}


def test_resolver_missing_idol_card_raises() -> None:
    resolver = _resolver_or_skip()
    # 2026-11-21 的新卡不在主数据快照里：显式报错，不静默退回 4.11
    with pytest.raises(ExamConfigUnavailable):
        resolver.battle_config(
            idol_card_id="i_card-hkne-3-000", produce_id="produce-002", step_type="mid"
        )
    with pytest.raises(ExamConfigUnavailable):
        resolver.battle_config(
            idol_card_id="i_card-no-such-999", produce_id="produce-002", step_type="mid"
        )
