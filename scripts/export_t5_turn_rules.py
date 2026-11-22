"""导出 B3/T5「回合规则」真机配对回归素材（tests/fixtures/t5_exam_turn_rules.json）。

数据源（本机采集，不入库）：
- ``C:\\GakumasLocal\\GakumasUnlock\\out\\exam_truth.json``：``decode_exam_actions.py``
  从 ``traffic.jsonl`` 的 ``StepAuditionEndExamBattle`` 解出的逐回合真值
  （每回合开始手牌 ``hand``、本回合实际出牌 ``played``、回合属性、分数）。
- ``data/knowledge/card_table.json``：卡牌效果（查首张牌是否带
  ``ExamPlayableValueAdd`` = 「技能卡使用数追加」）。

导出的只是**回合规则回归需要的最小事实**：每回合出牌数、手牌数、首张牌、
首张牌是否带额外出牌效果。用途：给 ``tests/test_t5_turn_rules.py`` 证明
「真机每回合基础 1 张，7 个 2 张回合里 3 个能被卡效果直接解释，其余是 P 道具
（采集不含 P 道具数据）」。

用法：
    .venv\\Scripts\\python.exe scripts/export_t5_turn_rules.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRUTH = Path(r"C:\GakumasLocal\GakumasUnlock\out\exam_truth.json")
DEFAULT_CARD_TABLE = ROOT / "data" / "knowledge" / "card_table.json"
DEFAULT_OUT = ROOT / "tests" / "fixtures" / "t5_exam_turn_rules.json"


def load_card_effects(path: Path) -> dict[tuple[str, int], list[str]]:
    """``(card_id, upgrade) -> [effect_type, ...]``。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    cards = doc.get("cards") or {}
    effects: dict[tuple[str, int], list[str]] = {}
    for row in cards.values():
        cid = str(row.get("id") or "")
        upgrade = int(row.get("upgrade") or 0)
        effects[(cid, upgrade)] = [
            str(effect.get("type") or "") for effect in row.get("effects") or []
        ]
    return effects


def split_card_key(key: str) -> tuple[str, int]:
    cid, _, upgrade = key.rpartition("+")
    return cid, int(upgrade or 0)


def build(truth_path: Path, card_table_path: Path) -> dict:
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    effects = load_card_effects(card_table_path)
    exams = []
    totals = {"turns": 0, "plays_1": 0, "plays_2": 0, "two_play_by_card": 0}
    for index, exam in enumerate(truth):
        turns = []
        for turn in exam.get("turns") or []:
            played = list(turn.get("played") or [])
            hand = list(turn.get("hand") or [])
            first = played[0] if played else ""
            first_cid, first_up = split_card_key(first) if first else ("", 0)
            first_extra = 0
            if first:
                first_extra = 1 if "ExamPlayableValueAdd" in effects.get(
                    (first_cid, first_up), ()
                ) else 0
            turns.append(
                {
                    "turn": int(turn.get("turn") or 0),
                    "plays": len(played),
                    "hand_size": len(hand),
                    "first_card": first,
                    "first_card_extra_play": first_extra,
                }
            )
            totals["turns"] += 1
            if len(played) == 1:
                totals["plays_1"] += 1
            elif len(played) == 2:
                totals["plays_2"] += 1
                if first_extra:
                    totals["two_play_by_card"] += 1
        exams.append(
            {
                "index": index,
                "ts": exam.get("ts"),
                "rank": exam.get("rank"),
                "final_score": exam.get("score"),
                "turns": turns,
            }
        )
    return {
        "source": {
            "traffic_derived": "exam_truth.json（decode_exam_actions.py 从 traffic.jsonl 解出）",
            "card_effects": "data/knowledge/card_table.json",
            "capture_date": "2026-11-20 / 2026-11-21 四场考试",
            "generated_by": "scripts/export_t5_turn_rules.py",
            "note": (
                "真机回合规则配对回归素材：每回合出牌数/手牌数/首张牌是否带"
                " ExamPlayableValueAdd。P 道具在采集里没有，因此不能用它解释的"
                " 2 张回合按未知处理（采集侧只能说明「不超过 2 张」）。"
            ),
        },
        "stats": totals,
        "exams": exams,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", default=str(DEFAULT_TRUTH))
    parser.add_argument("--card-table", default=str(DEFAULT_CARD_TABLE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    truth_path = Path(args.truth)
    if not truth_path.is_file():
        print(f"❌ 采集真值不存在：{truth_path}（先跑采集/ decode_exam_actions.py）")
        return 1
    doc = build(truth_path, Path(args.card_table))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    stats = doc["stats"]
    print(
        f"✅ {out}：{len(doc['exams'])} 场 / {stats['turns']} 回合，"
        f"1 张 {stats['plays_1']}、2 张 {stats['plays_2']}"
        f"（其中 {stats['two_play_by_card']} 个由卡效果 ExamPlayableValueAdd 解释）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
