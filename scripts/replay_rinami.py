"""M6 莉波 W7/W9 实机样本引擎 oracle 重放（GKMS 原生核，只读外部 AGPL，不拷入 src）。

把 ``data/_rinami_live/<round>/`` 的 gkms-loadout + seed 开一场考试，按 battle-log
``result.examActions`` 逐动作重放，逐决策对比 execution.jsonl 的 rng/score/turn/card，
并记录每瓶饮料前后状态增量（供 sim 饮料效果引擎配对）。

引擎：``data/_f2sl_tools/kernel/gkmscore.dll``（rules=69，**不重编**）+
``data/GKMSMainWheel``（AGPL，按路径引用）。样本 ``data/_rinami_live`` 不提交，
缺样本/引擎时本脚本退出码 2（测试据此 skip）。

用法::

    .venv\\Scripts\\python.exe scripts/replay_rinami.py data/_rinami_live/W9 --out out.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _setup_engine() -> None:
    os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
    os.environ.setdefault(
        "GKMSCLIGPU_LIB", str(ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll")
    )
    if str(ROOT / "data" / "bench_repo") not in sys.path:
        sys.path.insert(0, str(ROOT / "data" / "bench_repo"))


def _card_key(c: dict) -> str:
    return f"{c['produce_card_id']}::{c.get('current_upgrade_count', 0)}"


def replay(round_dir: Path) -> dict:
    _setup_engine()
    from gkbench import engine  # noqa: E402

    engine.setup()
    from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402

    loadout = json.loads((round_dir / "gkms-loadout.json").read_text(encoding="utf-8"))
    opening = json.loads((round_dir / "opening.json").read_text(encoding="utf-8"))
    blog = json.loads((round_dir / "battle-log.json").read_text(encoding="utf-8"))
    execs = [
        json.loads(line)
        for line in (round_dir / "execution.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    decisions = [e["data"] for e in execs if e.get("kind") == "decision"]
    drink_labels = {
        e["data"]["i"]: e["data"]
        for e in execs
        if e.get("kind") == "auto-drink-confirm"
    }

    master = engine.master()
    nat, _ns = engine.native()
    session, meta = build_hif_loadout_session(master, loadout, int(loadout["seed"]))

    def snap(s) -> dict:
        st = s.state
        return {
            "turn": s.turn,
            "score": int(st.score),
            "stamina": int(st.stamina),
            "rng": int(s.deck.rng.state),
            "focus": int(st.lesson_buff),
            "condition": int(st.parameter_buff_remaining),
            "score_mult": float(st.lesson_parameter_multiple),
            "half_cost_until": st.stamina_consumption_down_until_turn,
            "extra_plays": int(st.turn_playable_adds),
            "hand": [_card_key(c) for c in s.deck.hand],
            "deck_n": len(s.deck.deck),
            "grave_n": len(s.deck.grave),
            "drinks": list(s.drinks),
        }

    s0 = snap(session)
    op_rng = opening["parameterScalars"]["currentRandom"]["state"]
    op_hand = [f"{c['id']}::{c['upgradeCount']}" for c in opening["zones"]["hand"]]
    op_deck = [f"{c['id']}::{c['upgradeCount']}" for c in opening["zones"]["deck"]]
    eng_deck = [_card_key(c) for c in session.deck.deck]

    acts = blog["result"]["examActions"]
    mismatches: list = []
    rows: list = []
    drink_steps: list = []
    n = min(len(acts), len(decisions))
    for i in range(n):
        a, dec = acts[i], decisions[i]
        before = snap(session)
        kind = a["actionType"].replace("ExamActionType_", "")
        idx = int(a["indexes"][0]) if a.get("indexes") else 0
        for key, want in (("rng", dec["rng"]), ("score", dec["score"]), ("turn", dec["turn"])):
            if before[key] != want:
                mismatches.append([i, key, before[key], want])
        if kind == "UseHand":
            card = before["hand"][idx] if idx < len(before["hand"]) else "?"
            if dec.get("card") and card != dec["card"]:
                mismatches.append([i, "card", card, dec["card"]])
            session.step(("play", idx), observe=False)
        elif kind == "UseDrink":
            drink_id = before["drinks"][idx] if idx < len(before["drinks"]) else "?"
            session.step(("drink", idx), observe=False)
            after = snap(session)
            drink_steps.append({
                "i": i, "idx": idx, "drink": drink_id,
                "decision_i": dec.get("i"),
                "label": drink_labels.get(dec.get("i"), {}),
                "before": before, "after": after,
            })
        elif kind == "TurnEnd":
            session.step(("end",), observe=False)
        else:
            mismatches.append([i, "action", kind, "UseHand/UseDrink/TurnEnd"])
        rows.append({"i": i, "kind": kind, "idx": idx, "before": before})

    final = snap(session)
    return {
        "round": round_dir.name,
        "rules": int(nat.exam_rules_version),
        "seed": int(loadout["seed"]),
        "final_score": final["score"],
        "expect_score": int(blog["result"]["score"]),
        "finished": bool(session.finished),
        "turns": final["turn"],
        "opening_rng_match": s0["rng"] == op_rng,
        "opening_rng": s0["rng"],
        "hand_match": s0["hand"] == op_hand,
        "deck_match": eng_deck == op_deck,
        "n_actions": len(acts),
        "n_decisions": len(decisions),
        "decision_mismatches": mismatches,
        "drink_steps": drink_steps,
        "drink_ids": list(loadout.get("drink_ids") or ()),
        "unverified": meta.get("unverified"),
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    parser = argparse.ArgumentParser(description="莉波实机样本引擎 oracle 重放")
    parser.add_argument("round_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    round_dir = args.round_dir
    if not round_dir.is_absolute():
        round_dir = ROOT / round_dir
    required = ["gkms-loadout.json", "opening.json", "battle-log.json", "execution.jsonl"]
    if not all((round_dir / f).is_file() for f in required):
        print(f"缺少实机样本: {round_dir}", file=sys.stderr)
        return 2
    if not (ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll").is_file():
        print("缺少引擎核心 gkmscore.dll", file=sys.stderr)
        return 2
    if not (ROOT / "data" / "bench_repo" / "gkbench").is_dir():
        print("缺少 data/bench_repo", file=sys.stderr)
        return 2

    result = replay(round_dir)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(f"round={result['round']} rules={result['rules']} "
          f"score={result['final_score']}/{result['expect_score']} "
          f"mismatches={len(result['decision_mismatches'])} "
          f"drinks={len(result['drink_steps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
