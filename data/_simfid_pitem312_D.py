"""sim-fid ② game D: gate boundary pb 7 vs 8 + hand-full (1 engine game)."""
from __future__ import annotations
import gc, json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data/GKMSMainWheel"
os.environ["GKMS_NATIVE_LIB"] = str(ROOT / "data/_f2sl_tools/kernel/gkmscore.dll")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(WHEEL)); sys.path.insert(0, str(ROOT / "src"))
os.chdir(WHEEL / "GakumasCLI")
from GakumasCLI.scenario.exam_session import Master, ExamLoading, ProduceState, SegmentConfig, open_exam

ENC312 = "enchant-p_item_effect_01-3-312-0-enc01"
C110 = "p_card-01-men-2_110"   # +3 pb, +1 playcount
C1 = "p_card-01-act-2_042"     # +1 pb (祝福), no playcount
FILLER = "p_card-00-act-0_001"


def tes312(s):
    for t in getattr(s.state, "trigger_effect_states", []) or []:
        if isinstance(t, dict) and t.get("enchant_id") == ENC312:
            return {k: t.get(k) for k in ("phase_count", "spent_total", "limit_count") if t.get(k) is not None}
    return None


def snap(s):
    st = s.state
    def g(n):
        try: return getattr(st, n)
        except Exception: return None
    return {"turn": int(s.turn), "hand_n": len(s.deck.hand), "pb": g("parameter_buff_remaining"),
            "playable": g("turn_playable_adds"), "tes": tes312(s)}


def main():
    master = Master.load(Path("ro/master/tables"))
    # deck: 110 x3 then 祝福 x12; distribute 5 (hand full each turn). plan1.
    deck_ids = [C110] * 2 + [C1] * 14 + [FILLER] * 3
    deck = [{"produce_card_id": i, "base_upgrade_count": 0} for i in deck_ids]
    produce = ProduceState(stamina=60, max_stamina=60, deck_cards=deck, item_enchant_ids=[ENC312], plan_type=1)
    cfg = SegmentConfig(segment_id="simfid312d", segment_type="Audition Mid1", limit_turn=8,
                        score_cap=None, parameter_type=None, seed=880032, gimmick_group_id=None,
                        audition_permils={1: 1000, 2: 1000, 3: 1000},
                        audition_parameter_values={1: 100, 2: 100, 3: 100},
                        audition_npc_rng_advances=0, turn_start_distribute=5,
                        eligible_supports=(), resolve_initial_cards=True,
                        initial_card_ids=[C110, C110, C1], upgrade_tiers=set(master.cards),
                        drink_ids=[], lesson_start_enchant_ids=[ENC312])
    s = open_exam(ExamLoading(master, produce, cfg))
    rows = [{"kind": "open", **snap(s)}]
    # play 110 first (build pb), then 祝福 to step pb by 1 across boundary 7/8
    order = [C110, C110] + [C1] * 14
    oi = 0
    n = 0
    while not s.finished and n < 60:
        hand = list(s.deck.hand)
        want = order[oi] if oi < len(order) else None
        action = ("end",); played = None
        if want:
            for i, inst in enumerate(hand):
                if inst.get("produce_card_id") == want and s.can_play(inst):
                    action = ("play", i); played = want; break
        if action[0] == "play":
            oi += 1
        before = snap(s)
        s.step(action, observe=False)
        after = snap(s)
        tb, ta = before["tes"] or {}, after["tes"] or {}
        rows.append({"kind": "step", "i": n, "turn": before["turn"], "played": played,
                     "pre_pb": before["pb"], "post_pb": after["pb"],
                     "pre_phase": tb.get("phase_count"), "post_phase": ta.get("phase_count"),
                     "pre_spent": tb.get("spent_total"), "post_spent": ta.get("spent_total"),
                     "pre_hand": before["hand_n"], "post_hand": after["hand_n"],
                     "fire": ta.get("spent_total", 0) > tb.get("spent_total", 0)})
        if played:
            print(f"t{before['turn']} {played[-7:]} pre_pb={before['pb']} post_pb={after['pb']} "
                  f"phase {tb.get('phase_count')}->{ta.get('phase_count')} "
                  f"hand {before['hand_n']}->{after['hand_n']} FIRE={rows[-1]['fire']}", flush=True)
        n += 1
    (ROOT / "data/_simfid_pitem312_D.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print("saved D", flush=True)
    del s; gc.collect()


if __name__ == "__main__":
    main()