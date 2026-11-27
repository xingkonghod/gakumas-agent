"""M6 探针 3：W9 四瓶饮料前后全状态 + RNG 消费数（type9/search-move 口径）。不提交。"""
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
sys.path.insert(0, str(ROOT / "src"))

from gkbench import engine  # noqa: E402

engine.setup()
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from gkagent.sim.exam_shuffle import NativeRandom  # noqa: E402

W9 = ROOT / "data/_rinami_live/W9"
loadout = json.load(open(W9 / "gkms-loadout.json", encoding="utf-8"))
blog = json.load(open(W9 / "battle-log.json", encoding="utf-8"))
master = engine.master()
session, meta = build_hif_loadout_session(master, loadout, int(loadout["seed"]))


def advances(a, b, cap=200):
    """a→b 需要多少次 xorshift32 advance（None=cap 内找不到）。"""
    rng = NativeRandom(a)
    for k in range(cap + 1):
        if rng.state == b:
            return k
        rng.advance()
    return None


def full(s):
    st = s.state
    g = s._export()
    def zone(n):
        return [f"{c['produce_card_id']}::{c.get('current_upgrade_count',0)}" for c in s._zone(n)]
    return {
        "turn": s.turn, "score": int(st.score), "stamina": int(st.stamina),
        "rng": int(s.deck.rng.state),
        "focus": int(st.lesson_buff),
        "condition": int(st.parameter_buff_remaining),
        "score_mult": float(st.lesson_parameter_multiple),
        "half_cost": bool(st.stamina_consumption_down),
        "half_cost_until": st.stamina_consumption_down_until_turn,
        "hand": zone("hand"), "deck_n": len(zone("deck")), "grave_n": len(zone("grave")),
        "drinks": list(s.drinks),
        "extra_plays": int(st.turn_playable_adds),
    }


acts = blog["result"]["examActions"]
drink_steps = []
for i, a in enumerate(acts):
    kind = a["actionType"].replace("ExamActionType_", "")
    idx = int(a["indexes"][0])
    if kind == "UseDrink":
        before = full(session)
        # 记录候选（kampo search-move）
        choices = None
        session.step(("drink", idx), observe=False)
        after = full(session)
        adv = advances(before["rng"], after["rng"])
        drink_steps.append({"i": i, "idx": idx, "drink": before["drinks"][idx] if idx < len(before["drinks"]) else "?",
                            "before": before, "after": after, "rng_advances": adv})
    elif kind == "UseHand":
        session.step(("play", idx), observe=False)

for d in drink_steps:
    print(f"\n=== step {d['i']} drink={d['drink']} rng_advances={d['rng_advances']} ===")
    b, a = d["before"], d["after"]
    for k in b:
        if b[k] != a[k]:
            print(f"  {k}: {b[k]} -> {a[k]}")
    print("  hand after:", a["hand"])

(ROOT / "data/_drinks_probe3.json").write_text(json.dumps(drink_steps, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nwritten data/_drinks_probe3.json")
