"""A5（T3 离线预演）脚本单测：``scripts/verify_exam_plan_offline.py``。

不依赖采集文件：用合成牌组/seed 构造 ``ExamSetup``，truth 由 oracle 自产，
验证「多候选 config_turns → 逐回合收窄 → 唯一锁定 → 选中真值」这条离线预演链路。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_exam_plan_offline as offline

from gkagent.sim.exam_plan import ExamDrawPlan, ExamPlanSelector, ExamSetup

DECK = tuple((f"p_card-{index:02d}", 0) for index in range(20))
TRUTH_TURNS = 4


def _setup(config_turns: int = TRUTH_TURNS, seed: int = 0x1234) -> ExamSetup:
    return ExamSetup(seed=seed, deck=DECK, config_turns=config_turns, npc_count=5)


def _truth(setup: ExamSetup, turns: int = TRUTH_TURNS) -> list[dict]:
    """用该 setup 的 oracle 自产逐回合 truth（每回合打第一张、其余留手牌进弃牌堆）。"""
    oracle = setup.new_oracle()
    grave: list[tuple[str, int]] = []
    truth: list[dict] = []
    for _ in range(turns):
        hand = oracle.draw_next_turn(1, grave=grave or None)
        played = [hand[0]]
        truth.append(
            {
                "turn": len(truth) + 1,
                "parameterType": 1,
                "hand": [list(card) for card in hand],
                "played": [list(card) for card in played],
                "score": 0,
                "stamina": 0,
            }
        )
        grave.extend(played)
        grave.extend(hand[1:])
    return truth


def _drive(candidates: list[ExamSetup], truth: list[dict]) -> dict:
    selector = ExamPlanSelector([ExamDrawPlan(setup) for setup in candidates])
    return offline.drive_selector(selector, truth)


# ---------------------------------------------------------------- 基本工具


def test_leftover_cards_matches_by_id_and_reports_generated_card():
    hand = [("p_card-a", 0), ("p_card-b", 0), ("p_card-a", 0)]
    assert offline.leftover_cards(hand, [("p_card-a", 0)]) == [
        ("p_card-b", 0),
        ("p_card-a", 0),
    ]
    assert offline.leftover_cards(hand, [("p_card-b", 0)]) == [
        ("p_card-a", 0),
        ("p_card-a", 0),
    ]
    # 考试内生成的卡不在起始手牌里 → grave 不可重建
    assert offline.leftover_cards(hand, [("p_card-generated", 0)]) is None


def test_candidate_setups_share_seed_and_deck_but_vary_config_turns():
    base = _setup()
    candidates = offline.candidate_setups(base, [9, 11, 12])
    assert [candidate.config_turns for candidate in candidates] == [9, 11, 12]
    for candidate in candidates:
        assert candidate.seed == base.seed
        assert candidate.deck == base.deck
        assert candidate.npc_count == base.npc_count


# ---------------------------------------------------------------- 离线预演


def test_drive_selector_locks_true_config_turns_on_first_turn():
    base = _setup()
    truth = _truth(base)
    row = _drive(offline.candidate_setups(base, [4, 5, 7]), truth)
    assert row["chosen_config_turns"] == 4
    assert row["locked_turn"] == 1
    assert row["alive_by_turn"] == [1, 1, 1, 1]
    assert row["verified"] == row["turns"] == TRUTH_TURNS
    # 锁定后 known_draw 覆盖之后每一回合的实机手牌；搜索字段每回合都可用
    assert row["known_ok"] == row["known_total"] == TRUTH_TURNS - 1
    assert row["kwargs_ok"] == TRUTH_TURNS
    assert row["mismatch"] is False and row["stop_reason"] == ""
    assert offline.evaluate_row(row, 4, max_lock_turn=3) == []


def test_drive_selector_reports_generated_card_stop_without_mismatch():
    base = _setup()
    truth = _truth(base)
    # T2 打出考试内生成的卡（不在起始手牌里）→ 与生产同一口径：核对到 T2 为止，不算失败
    truth[1]["played"] = [["p_card-generated", 0]]
    row = _drive(offline.candidate_setups(base, [4, 5, 7]), truth)
    assert row["chosen_config_turns"] == 4
    assert row["locked_turn"] == 1
    assert row["turns"] == 2 and row["verified"] == 2
    assert "T2" in row["stop_reason"]
    assert row["mismatch"] is False
    assert offline.evaluate_row(row, 4, max_lock_turn=3) == []


def test_drive_selector_flags_no_candidate_matching():
    truth = _truth(_setup(TRUTH_TURNS, seed=0x9999))
    row = _drive(offline.candidate_setups(_setup(seed=0x1234), [4, 5, 7]), truth)
    assert row["chosen_config_turns"] is None
    assert row["mismatch"] is True
    assert row["reason"]
    assert offline.evaluate_row(row, 4, max_lock_turn=3)  # 非空 = 不通过


def test_evaluate_row_flags_late_lock_and_wrong_config():
    base = _setup()
    truth = _truth(base)
    row = _drive(offline.candidate_setups(base, [4, 5, 7]), truth)
    assert offline.evaluate_row(row, 4, max_lock_turn=3) == []
    # 真值配置对不上
    assert offline.evaluate_row(row, 11, max_lock_turn=3)
    # 锁定太晚（伪造 locked_turn；expected_verified 也随之为 0 → 只检查锁定上限这条）
    fake = dict(row, chosen_config_turns=4, locked_turn=5, turns=4, verified=0)
    assert any("locked_turn" in problem for problem in offline.evaluate_row(fake, 4, max_lock_turn=3))


# ---------------------------------------------------------------- CLI 全链路


def _write_setups(tmp_path: Path, base: ExamSetup, truth: list[dict]) -> tuple[Path, Path]:
    raw = base.to_dict()
    raw["truth"] = truth
    raw["played_turns"] = len(truth)
    full = tmp_path / "exam_setup.json"
    full.write_text(json.dumps({"exams": [raw]}, ensure_ascii=False), encoding="utf-8")
    current = {
        "mode": "current",
        "turns_candidates": [4, 5, 7],
        "exams": [
            dict(raw, index=index, config_turns=turns, truth=[])
            for index, turns in enumerate([4, 5, 7])
        ],
    }
    current_path = tmp_path / "exam_setup_current_test.json"
    current_path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    return full, current_path


def test_main_passes_with_synthetic_current_candidates(tmp_path: Path):
    base = _setup()
    truth = _truth(base)
    full, current = _write_setups(tmp_path, base, truth)
    assert (
        offline.main(
            ["--setup", str(full), "--current", str(current), "--turns", "4,5,7"]
        )
        == 0
    )


def test_main_reports_missing_setup(tmp_path: Path):
    assert offline.main(["--setup", str(tmp_path / "missing.json")]) == 1


def test_begin_turn_subset_ocr_miss_retries():
    """F#56：实机子集缺1张=OCR漏读→不mismatch、回退turn、重读重试成功。"""
    setup = _setup()
    truth = _truth(setup)
    plan = ExamDrawPlan(setup)
    assert plan.begin_turn(truth[0]["hand"], 1)
    missing = truth[1]["hand"][1:]
    assert not plan.begin_turn(missing, 1)
    assert plan.active and plan.ocr_miss
    assert plan.turn == 1
    assert plan.begin_turn(truth[1]["hand"], 1)
    assert plan.turn == 2 and not plan.ocr_miss


def test_selector_keeps_candidates_on_ocr_miss():
    """F#56：全候选子集漏读时不重置（重置会丢已核对回合）。"""
    setup = _setup()
    truth = _truth(setup)
    selector = ExamPlanSelector([ExamDrawPlan(setup), ExamDrawPlan(_setup(5))])
    missing0 = truth[0]["hand"][1:]
    assert not selector.begin_turn(missing0, 1)
    assert selector.reset_count == 0
    assert selector.alive == 2
    assert selector.begin_turn(truth[0]["hand"], 1)
    assert selector.reset_count == 0
    # 两候选 config_turns 不同但 T1 手牌同 → T2 才收敛
    assert selector.begin_turn(truth[1]["hand"], 1)
    assert selector.locked_turn == 2
