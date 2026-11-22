"""A5（T3 离线预演）：``build_exam_setup.py --current`` 候选 → ``ExamPlanSelector`` 逐回合核对。

不碰真机，用**已结束采集**的逐回合 truth 驱动生产同一套 ``ExamPlanSelector``：

1. **--current 路径**：对最近一场 ``StepAuditionStart`` 生成多个 ``config_turns`` 候选
   （等价 ``build_exam_setup.py --current --allow-finished``；默认输出
   ``out/exam_setup_current_test.json``），再用这场考试的真值手牌逐回合喂 selector，
   看候选是否收敛到 1、第几回合锁定、选中的 ``config_turns`` 是否等于真值。
2. **四场 sweep**：对 ``out/exam_setup.json`` 里每一场考试各造 ``--turns``（默认 9/11/12）
   候选，同样用 truth 驱动，验证「同 seed 不同 config_turns」时锁定机制对每场都成立。

DoD（脚本退出码 = 是否通过）：

* 候选收敛到 1（``chosen`` 非空、``alive`` 归 1）；
* ``locked_turn <= --max-lock-turn``（默认 3）；
* 选中的 ``config_turns`` == 这场考试的真值（全量 setup 检测出来的配置回合）；
* 锁定后逐回合核对全部通过（``verified`` = 驱动到停下的回合数）。

数据限制（与 ``verify_exam_wiring.py`` 同口径，不算失败）：考试里**打出考试内生成的卡**时
（11-20 期末 T8 / 11-21 期末 T12），弃牌堆无法从实机日志唯一重建，核对到该回合为止。

用法::

    .venv\\Scripts\\python.exe scripts\\verify_exam_plan_offline.py            # 默认
    .venv\\Scripts\\python.exe scripts\\verify_exam_plan_offline.py --refresh  # 先重建 current 候选
    .venv\\Scripts\\python.exe scripts\\verify_exam_plan_offline.py --json     # 额外打印 JSON
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.sim.exam_plan import (
    ExamDrawPlan,
    ExamPlanSelector,
    ExamSetup,
    load_exam_setups,
)

DEFAULT_SETUP = ROOT / "out" / "exam_setup.json"
DEFAULT_CURRENT = ROOT / "out" / "exam_setup_current_test.json"
DEFAULT_TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
DEFAULT_TURNS = (9, 11, 12)


def cards(items: Iterable[Any]) -> list[tuple[str, int]]:
    """``[[id, upgrade], ...]`` → ``[(id, upgrade), ...]``。"""
    return [(str(item[0]), int(item[1])) for item in items or ()]


def leftover_cards(
    hand: Sequence[tuple[str, int]], played: Sequence[tuple[str, int]]
) -> list[tuple[str, int]] | None:
    """truth 起始手牌 − 打出的牌（按 id 扣减、保持手牌顺序）；打了不在手牌里的卡返回 None。"""
    remaining = list(hand)
    for card in played:
        index = next((i for i, owned in enumerate(remaining) if owned[0] == card[0]), None)
        if index is None:
            return None
        remaining.pop(index)
    return remaining


def candidate_setups(exam: ExamSetup, turns: Sequence[int]) -> list[ExamSetup]:
    """同一场考试按 ``config_turns`` 候选复制多份 ``ExamSetup``（生产 --current 的候选形态）。"""
    return [dataclasses.replace(exam, config_turns=int(turn)) for turn in turns]


def drive_selector(selector: ExamPlanSelector, truth: Sequence[dict]) -> dict:
    """用逐回合 truth 驱动 selector（生产同一套 begin_turn/note_play/end_turn）。

    返回核对统计：``locked_turn`` / ``chosen_config_turns`` / ``verified`` /
    ``alive_by_turn`` / ``known_ok`` / ``known_total`` / ``stop_reason`` 等。
    """
    selector.start()
    result: dict[str, Any] = {
        "turns": 0,
        "verified": 0,
        "locked_turn": 0,
        "chosen_config_turns": None,
        "alive_by_turn": [],
        "known_ok": 0,
        "known_total": 0,
        "kwargs_ok": 0,
        "mismatch": False,
        "reason": "",
        "stop_reason": "",
    }
    turns = list(truth)
    retries = 0
    for position, turn in enumerate(turns):
        observed = cards(turn["hand"])
        parameter = int(turn.get("parameterType") or 0)
        ok = selector.begin_turn(observed, parameter)
        result["turns"] = position + 1
        result["alive_by_turn"].append(selector.alive)
        if selector.chosen is None:
            summary = selector.summary()
            if summary.get("retries", 0) > retries:
                # 本回合所有候选都不匹配 → selector 已整体重置重试；真值回放无法「下一帧再看」
                retries = int(summary.get("retries") or 0)
                result["mismatch"] = True
                result["reason"] = selector.reason or "候选全部不匹配"
                break
            if not selector.active:  # 候选全淘汰 + 重试次数用完
                result["mismatch"] = True
                result["reason"] = selector.reason
                break
        else:
            if not ok:  # 锁定后本回合核对失败 → 计划停用
                result["mismatch"] = True
                result["reason"] = selector.reason
                break
            if result["locked_turn"] == 0:
                result["locked_turn"] = selector.locked_turn
                result["chosen_config_turns"] = selector.chosen.setup.config_turns
            result["verified"] += 1
            # 锁定后：已知牌序的前几张 = 下一回合实机手牌（本回合有回合内抽牌时不计）
            if position + 1 < len(turns):
                next_hand = cards(turns[position + 1]["hand"])
                known = selector.known_draw
                if len(known) >= len(next_hand):
                    result["known_total"] += 1
                    if [card[0] for card in known[: len(next_hand)]] == [
                        card[0] for card in next_hand
                    ]:
                        result["known_ok"] += 1
            # 喂给搜索的 ExpectState 字段必须可用且非空
            kwargs = selector.expect_state_kwargs(
                to_specs=lambda items: list(items)
            )
            if kwargs.get("known_draw"):
                result["kwargs_ok"] += 1

        # 记账：出牌（按顺序）+ 回合末剩余手牌 → 下一回合 oracle 的 grave
        played = cards(turn.get("played") or ())
        for card in played:
            selector.note_play(card)
        leftover = leftover_cards(observed, played)
        if leftover is None:
            # 考试内生成的卡（不在起始手牌里）：grave 无法唯一重建，核对到此为止。
            result["stop_reason"] = (
                f"T{position + 1} 打出考试内生成的卡，grave 不可重建，核对提前结束"
            )
            break
        selector.end_turn(leftover)

    result["summary"] = selector.summary()
    selector.finish()
    return result


def evaluate_row(row: dict, truth_config_turns: int, *, max_lock_turn: int) -> list[str]:
    """单场 DoD 检查，返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    if row["chosen_config_turns"] is None:
        problems.append("候选未收敛（没有锁定任何 config_turns）")
        return problems
    if row["locked_turn"] != 1 and not (1 <= row["locked_turn"] <= max_lock_turn):
        problems.append(f"locked_turn={row['locked_turn']} 超过 {max_lock_turn}")
    expected_verified = row["turns"] - row["locked_turn"] + 1
    if row["verified"] != expected_verified:
        problems.append(
            f"锁定后核对 {row['verified']}/{expected_verified} 回合（锁定回合起应全中）"
        )
    if row["mismatch"]:
        problems.append(f"核对失败：{row['reason']}")
    if row["chosen_config_turns"] != truth_config_turns:
        problems.append(
            f"选中 config_turns={row['chosen_config_turns']} ≠ 真值 {truth_config_turns}"
        )
    summary = row.get("summary") or {}
    if summary.get("alive") not in (None, 1):
        problems.append(f"候选未收敛到 1（alive={summary.get('alive')}）")
    return problems


def format_row(label: str, row: dict, truth_config_turns: int, problems: list[str]) -> str:
    """一行可读结果。"""
    mark = "✅" if not problems else "❌"
    alive = "→".join(str(count) for count in row["alive_by_turn"]) or "?"
    locked = row["locked_turn"] or "-"
    chosen = row["chosen_config_turns"]
    after_lock = max(row["turns"] - row["locked_turn"] + 1, 0) if row["locked_turn"] else 0
    line = (
        f"{mark} {label} 真值 config_turns={truth_config_turns} → 选中 {chosen}"
        f"（第 {locked} 回合锁定，候选存活 {alive}）"
        f" | 锁定后手牌核对 {row['verified']}/{after_lock}（驱动 {row['turns']} 回合）"
        f" | known_draw 覆盖下一手 {row['known_ok']}/{row['known_total']}"
    )
    if row["stop_reason"]:
        line += f" | ⚠️ {row['stop_reason']}"
    if problems:
        line += f" | ❌ {'；'.join(problems)}"
    return line


def run_current_path(
    setups: list[ExamSetup], current_path: Path, *, turns: Sequence[int], max_lock_turn: int
) -> dict:
    """--current 候选（最近一场考试）用该场 truth 驱动 selector。"""
    current = load_exam_setups(current_path)
    if not current:
        raise SystemExit(f"❌ --current 候选文件不可用：{current_path}")
    seed = current[0].seed
    ground = next((exam for exam in setups if exam.seed == seed), None)
    if ground is None:
        raise SystemExit(f"❌ 全量 setup 里找不到 --current 的 seed=0x{seed:08X}（数据不同源？）")
    candidates = [
        dataclasses.replace(plan.setup, truth=ground.truth) for plan in map(ExamDrawPlan, current)
    ]
    selector = ExamPlanSelector([ExamDrawPlan(setup) for setup in candidates])
    row = drive_selector(selector, ground.truth)
    problems = evaluate_row(row, ground.config_turns, max_lock_turn=max_lock_turn)
    return {
        "label": f"--current seed=0x{seed:08X} 候选={[s.config_turns for s in candidates]}",
        "row": row,
        "truth_config_turns": ground.config_turns,
        "problems": problems,
    }


def run_sweep(
    setups: list[ExamSetup], *, turns: Sequence[int], max_lock_turn: int
) -> list[dict]:
    """四场已结束考试：各造 config_turns 候选，truth 驱动 selector。"""
    rows: list[dict] = []
    for exam in setups:
        candidates = candidate_setups(exam, turns)
        selector = ExamPlanSelector([ExamDrawPlan(setup) for setup in candidates])
        row = drive_selector(selector, exam.truth)
        problems = evaluate_row(row, exam.config_turns, max_lock_turn=max_lock_turn)
        rows.append(
            {
                "label": f"考试{exam.index} seed=0x{exam.seed:08X} 候选={[s.config_turns for s in candidates]}",
                "row": row,
                "truth_config_turns": exam.config_turns,
                "problems": problems,
            }
        )
    return rows


def refresh_current(
    traffic: Path, current_path: Path, turns: Sequence[int]
) -> None:
    """跑 ``build_exam_setup.py --current --allow-finished`` 等价流程并落盘。"""
    import build_exam_setup

    setup = build_exam_setup.build_current_setup(
        traffic, [int(turn) for turn in turns], allow_finished=True
    )
    current_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.write_text(json.dumps(setup, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[refresh] 已写入 {current_path}：当前考试候选 {len(setup['exams'])} 个"
        f"（seed=0x{setup['exams'][0]['seed']:08X}，turns={list(turns)}，"
        f"= build_exam_setup.py --current --allow-finished）"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A5：T3 离线预演（--current 候选 + ExamPlanSelector 核对）")
    parser.add_argument("--setup", default=str(DEFAULT_SETUP), help="全量 setup（含逐回合 truth）")
    parser.add_argument("--current", default=str(DEFAULT_CURRENT), help="--current 候选 JSON")
    parser.add_argument("--traffic", default=str(DEFAULT_TRAFFIC), help="traffic.jsonl（--refresh 用）")
    parser.add_argument("--turns", default=",".join(str(t) for t in DEFAULT_TURNS),
                        help="config_turns 候选（逗号分隔，默认 9,11,12）")
    parser.add_argument("--max-lock-turn", type=int, default=3, help="DoD：锁定回合上限（默认 3）")
    parser.add_argument("--refresh", action="store_true",
                        help="先用采集 traffic 重建 --current 候选（等价 build_exam_setup.py --current --allow-finished）")
    parser.add_argument("--json", action="store_true", help="额外打印 JSON 明细")
    args = parser.parse_args(argv)

    turns = [int(item) for item in str(args.turns).split(",") if item.strip()]
    setup_path = Path(args.setup)
    current_path = Path(args.current)
    if not setup_path.is_file():
        print(f"❌ 找不到 {setup_path}（先跑 scripts/build_exam_setup.py）")
        return 1
    setups = load_exam_setups(setup_path)
    if not setups:
        print(f"❌ {setup_path} 里没有可用的考试记录")
        return 1

    print("== A5 T3 离线预演：--current 候选 + ExamPlanSelector 逐回合核对 ==")
    print(f"[数据] 全量 setup={setup_path}（{len(setups)} 场）；候选 config_turns={turns}")
    if args.refresh or not current_path.is_file():
        traffic = Path(args.traffic)
        if not traffic.is_file():
            print(f"❌ 采集文件不存在：{traffic}（--refresh 需要）")
            return 1
        refresh_current(traffic, current_path, turns)
    else:
        print(f"[数据] --current 候选={current_path}（--refresh 可重建）")

    current_result = run_current_path(setups, current_path, turns=turns,
                                      max_lock_turn=args.max_lock_turn)
    print("\n[1] --current 路径（最近一场考试）")
    print("  " + format_row(current_result["label"], current_result["row"],
                            current_result["truth_config_turns"], current_result["problems"]))

    sweep_rows = run_sweep(setups, turns=turns, max_lock_turn=args.max_lock_turn)
    print(f"\n[2] 已结束考试 sweep（{len(sweep_rows)} 场，各造 {'/'.join(map(str, turns))} 候选）")
    for result in sweep_rows:
        print("  " + format_row(result["label"], result["row"],
                                result["truth_config_turns"], result["problems"]))

    all_rows = [current_result, *sweep_rows]
    bad = [item for item in all_rows if item["problems"]]
    lock_turns = [item["row"]["locked_turn"] for item in all_rows if item["row"]["locked_turn"]]
    print(
        f"\n汇总：--current 路径 {0 if current_result['problems'] else 1}/1 通过；"
        f"sweep {sum(1 for item in sweep_rows if not item['problems'])}/{len(sweep_rows)} 通过；"
        f"锁定回合 {lock_turns}（上限 {args.max_lock_turn}）；"
        f"候选全部收敛到 1"
        if not bad
        else f"\n汇总：❌ {len(bad)}/{len(all_rows)} 项不通过"
    )
    if args.json:
        print(json.dumps(
            {"current": current_result, "sweep": sweep_rows}, ensure_ascii=False, default=str
        ))
    if bad:
        print("❌ A5 DoD 未通过（见上方 ❌ 行）")
        return 1
    print("✅ A5 DoD 通过：候选收敛到 1、locked_turn<=3、选中 config_turns == 真值、锁定后逐回合核对全中")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
