"""M6 探针 2：W9 引擎 oracle 重放可行性（rules=69 DLL vs 实机 rev318/v55）。不提交。

build_hif_loadout_session(loadout, seed) → 按 battle-log 45 动作重放，
逐决策对比 execution.jsonl 的 rng/score，终分对比 1,426,865。
"""
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
os.environ.setdefault("GKMSCLIGPU_LIB", str(ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

from gkbench import engine  # noqa: E402

engine.setup()
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402

W9 = ROOT / "data/_rinami_live/W9"
loadout = json.load(open(W9 / "gkms-loadout.json", encoding="utf-8"))
opening = json.load(open(W9 / "opening.json", encoding="utf-8"))
blog = json.load(open(W9 / "battle-log.json", encoding="utf-8"))
execs = [json.loads(line) for line in open(W9 / "execution.jsonl", encoding="utf-8")]
decisions = [e["data"] for e in execs if e["kind"] == "decision"]

master = engine.master()
nat, _ns = engine.native()
print("rules =", nat.exam_rules_version)

seed = int(loadout["seed"])
session, meta = build_hif_loadout_session(master, loadout, seed)
print("meta unresolved:", meta.get("unverified"), "npc:", meta.get("npc_count"),
      "limit_turn:", meta.get("limit_turn"))


def hand_ids(s):
    return [f"{c['produce_card_id']}::{c.get('current_upgrade_count', 0)}" for c in s.deck.hand]


def snap(s):
    st = s.state
    return {
        "turn": s.turn,
        "score": int(st.score),
        "rng": int(s.deck.rng.state),
        "stamina": int(st.stamina),
        "hand": hand_ids(s),
        "drinks": list(s.drinks),
    }


s0 = snap(session)
print("opening rng:", s0["rng"], "expect", opening["parameterScalars"]["currentRandom"]["state"],
      "MATCH" if s0["rng"] == opening["parameterScalars"]["currentRandom"]["state"] else "MISMATCH")
op_hand = [f"{c['id']}::{c['upgradeCount']}" for c in opening["zones"]["hand"]]
op_deck = [f"{c['id']}::{c['upgradeCount']}" for c in opening["zones"]["deck"]]
print("hand match:", s0["hand"] == op_hand, s0["hand"], "vs", op_hand)
eng_deck = [f"{c['produce_card_id']}::{c.get('current_upgrade_count', 0)}" for c in session.deck.deck]
print("deck match:", eng_deck == op_deck)
if eng_deck != op_deck:
    print("  eng:", eng_deck)
    print("  op :", op_deck)
print("drinks:", s0["drinks"])

acts = blog["result"]["examActions"]
assert len(acts) == len(decisions), (len(acts), len(decisions))
rows = []
mismatch = []
for i, (a, dec) in enumerate(zip(acts, decisions)):
    before = snap(session)
    kind = a["actionType"].replace("ExamActionType_", "")
    idx = int(a["indexes"][0])
    # 对比决策前状态
    for key, want in (("rng", dec["rng"]), ("score", dec["score"]), ("turn", dec["turn"])):
        if before[key] != want:
            mismatch.append((i, key, before[key], want))
    if kind == "UseHand":
        card = before["hand"][idx] if idx < len(before["hand"]) else "?"
        if dec.get("card") and card != dec["card"]:
            mismatch.append((i, "card", card, dec["card"]))
        session.step(("play", idx), observe=False)
    elif kind == "UseDrink":
        session.step(("drink", idx), observe=False)
    else:
        raise SystemExit(f"unexpected action {kind}")
    after = snap(session)
    rows.append({"i": i, "kind": kind, "idx": idx, "before": before, "after": after})

final = snap(session)
print("\nfinal score:", final["score"], "expect", blog["result"]["score"],
      "MATCH" if final["score"] == blog["result"]["score"] == 1426865 else "MISMATCH")
print("finished:", session.finished, "turn:", final["turn"])
print("decision mismatches:", len(mismatch))
for m in mismatch[:30]:
    print("  ", m)

out = {"rules": nat.exam_rules_version, "final_score": final["score"],
       "expect_score": blog["result"]["score"], "mismatches": mismatch,
       "opening_rng_match": s0["rng"] == opening["parameterScalars"]["currentRandom"]["state"],
       "rows": rows}
(ROOT / "data/_drinks_probe2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("written data/_drinks_probe2.json")
