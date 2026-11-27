"""M8 好调跨回合叠加 fresh 规则探针（1 局）。不提交。

030（好调3回合 + 打分，无额外次数）t1/t2 各打一次 → 好调 3→6，观察回合末衰减：
  整体保护（bool fresh）：end1 cond3 / end2 cond6 / end3 cond5 …
  部分保护（impression 式 fresh 计数）：end1 cond3 / end2 cond5（旧3→2+新3）…
"""
from __future__ import annotations
import gc, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
os.environ["GKMS_NATIVE_LIB"] = str(ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(WHEEL)); sys.path.insert(0, str(ROOT / "src"))
os.chdir(WHEEL / "GakumasCLI")
from GakumasCLI.scenario.exam_session import (Master, ExamLoading, ProduceState,  # noqa: E402
                                              SegmentConfig, open_exam)

master = Master.load(Path("ro/master/tables"))
CID = "p_card-01-act-2_030"
deck = [{"produce_card_id": CID, "base_upgrade_count": 0} for _ in range(10)]
produce = ProduceState(stamina=60, max_stamina=60, deck_cards=deck, item_enchant_ids=[], plan_type=1)
cfg = SegmentConfig(segment_id="m8cond", segment_type="Audition Mid1", limit_turn=8,
                    score_cap=None, parameter_type=None, seed=880002, gimmick_group_id=None,
                    audition_permils={1: 1000, 2: 1000, 3: 1000},
                    audition_parameter_values={1: 100, 2: 100, 3: 100},
                    audition_npc_rng_advances=0, turn_start_distribute=3, eligible_supports=(),
                    resolve_initial_cards=True, upgrade_tiers=set(master.cards), drink_ids=())
s = open_exam(ExamLoading(master, produce, cfg))
rows = []


def snap():
    st = s.state
    return {"turn": s.turn, "cond": int(st.parameter_buff_remaining),
            "until": st.parameter_buff_until_turn, "pass": bool(st.parameter_buff_passing_turn_start),
            "score": int(st.score)}


rows.append({"kind": "open", **snap()})
script = {1: CID, 2: CID}
for n in range(14):
    if s.finished:
        break
    t = s.turn
    want = script.get(t)
    action = ("end",); played = None
    if want:
        for i, inst in enumerate(s.deck.hand):
            if inst.get("produce_card_id") == want and s.can_play(inst):
                action = ("play", i); played = want; break
    before = snap()
    s.step(action, observe=False)
    after = snap()
    rows.append({"kind": "step", "i": n, "action": list(action), "played": played,
                 "turn_before": t, "score_delta": after["score"] - before["score"], **after})
    print(rows[-1])
del s; gc.collect()
(ROOT / "data" / "_m8_fresh_cond.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved data/_m8_fresh_cond.json")