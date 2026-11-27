"""sim-fid ② pitem312 gate + hand-full probe (no-commit, <=4 engine games, serial).

Static master: trigger fieldStatus PARAMETER_BUFF_UP>=8 (好調が8ターン以上) = GATE;
fire effects = ExamCardDraw1 + ExamPlayableValueAdd+1 + ExamParameterBuffMultiplePerTurn(絶好調1T)
+ ExamStaminaReduceFix1. Probe verifies gate quantity (pb remaining) + hand-full skip.
Engine oracle only, no DLL rebuild, no AGPL copy.
"""
from __future__ import annotations
import ctypes, gc, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data/GKMSMainWheel"
DLL = ROOT / "data/_f2sl_tools/kernel/gkmscore.dll"
os.environ["GKMS_NATIVE_LIB"] = str(DLL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(WHEEL))
sys.path.insert(0, str(ROOT / "src"))
os.chdir(WHEEL / "GakumasCLI")

from GakumasCLI.scenario.exam_session import (Master, ExamLoading, ProduceState,  # noqa: E402
                                              SegmentConfig, open_exam)

ENC312 = "enchant-p_item_effect_01-3-312-0-enc01"
C110 = "p_card-01-men-2_110"      # 好調3T + 集中5 + playcount+1 + create
C1 = "p_card-01-act-2_042"        # 祝福 好調1T (no playcount add)
FILLER = "p_card-00-act-0_001"


def free_mb():
    class M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = M(); m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1048576


def wait_free(min_mb=900, cap_s=600):
    t0 = time.perf_counter()
    while free_mb() < min_mb and time.perf_counter() - t0 < cap_s:
        print(f"  [mem] free {free_mb():.0f}MB wait 60s", flush=True)
        time.sleep(60)


def tes312(s):
    for t in getattr(s.state, "trigger_effect_states", []) or []:
        if isinstance(t, dict) and t.get("enchant_id") == ENC312:
            return {k: t.get(k) for k in ("phase_count", "spent_total", "limit_count",
                                          "limit_count_in_turn", "installed_play_count",
                                          "skip_play_count_once", "skip_card_played_once")
                    if t.get(k) is not None}
    return None


def snap(s):
    st = s.state
    o = s.observe()
    def g(n):
        try:
            return getattr(st, n)
        except Exception:  # noqa: BLE001
            return None
    return {"turn": int(s.turn), "hand_n": len(s.deck.hand), "deck_n": len(s.deck.deck),
            "pb": g("parameter_buff_remaining"), "pb_until": g("parameter_buff_until_turn"),
            "pb_pass": g("parameter_buff_passing_turn_start"),
            "playable_adds": g("turn_playable_adds"),
            "perfect": g("perfect_condition_turns"),
            "stamina_down_until": g("stamina_consumption_down_until_turn"),
            "hand_limit": getattr(s.deck, "hand_limit", None),
            "tes": tes312(s), "stance": o.get("stance")}


def build(master, deck, seed, initial, distribute):
    produce = ProduceState(stamina=60, max_stamina=60, deck_cards=deck,
                           item_enchant_ids=[ENC312], plan_type=1)
    cfg = SegmentConfig(segment_id="simfid312", segment_type="Audition Mid1", limit_turn=8,
                        score_cap=None, parameter_type=None, seed=seed, gimmick_group_id=None,
                        audition_permils={1: 1000, 2: 1000, 3: 1000},
                        audition_parameter_values={1: 100, 2: 100, 3: 100},
                        audition_npc_rng_advances=0, turn_start_distribute=distribute,
                        eligible_supports=(), resolve_initial_cards=True,
                        initial_card_ids=list(initial), upgrade_tiers=set(master.cards),
                        drink_ids=[], lesson_start_enchant_ids=[ENC312])
    return open_exam(ExamLoading(master, produce, cfg))


def run(master, tag, deck_ids, seed, initial, distribute, script):
    wait_free()
    deck = [{"produce_card_id": i, "base_upgrade_count": 0} for i in deck_ids]
    s = build(master, deck, seed, initial, distribute)
    rows = [{"tag": tag, "kind": "open", **snap(s)}]
    print(f"[{tag}] open hand={len(s.deck.hand)} limit={getattr(s.deck,'hand_limit',None)} tes={tes312(s)}", flush=True)
    n = 0
    while not s.finished and n < 50:
        turn = int(s.turn)
        want = script.get(turn)
        hand = list(s.deck.hand)
        action = ("end",); played = None
        if want:
            for i, inst in enumerate(hand):
                if inst.get("produce_card_id") == want and s.can_play(inst):
                    action = ("play", i); played = want; break
        before = snap(s)
        s.step(action, observe=False)
        after = snap(s)
        row = {"tag": tag, "kind": "step", "i": n, "turn": turn, "played": played,
               "action": list(action), "before": before, "after": after}
        rows.append(row)
        tb, ta = before["tes"] or {}, after["tes"] or {}
        fired = ta.get("spent_total", 0) > tb.get("spent_total", 0)
        print(f"  t{turn} play={played} hand {before['hand_n']}->{after['hand_n']} "
              f"pb {before['pb']}->{after['pb']} phase {tb.get('phase_count')}->{ta.get('phase_count')} "
              f"spent {tb.get('spent_total')}->{ta.get('spent_total')} FIRE={fired} "
              f"playable {before['playable_adds']}->{after['playable_adds']} perfect {before['perfect']}->{after['perfect']}", flush=True)
        n += 1
    del s; gc.collect()
    return rows


def main():
    t0 = time.perf_counter()
    master = Master.load(Path("ro/master/tables"))
    print(f"Master.load {time.perf_counter()-t0:.1f}s free={free_mb():.0f}MB", flush=True)
    SEED = 880031
    out = ROOT / "data/_simfid_pitem312_probe.jsonl"
    summary = {"seed": SEED, "enchant": ENC312, "games": []}
    # A gate-high: 110 x4 turn1 (pb12 phase4 -> fire), distribute 3
    deckA = [C110] * 10 + [FILLER] * 5
    # B gate-low: 祝福(turn1) x12, 1 play/turn, phase4 at turn4 pb~2 (<8) -> no fire
    deckB = [C1] * 12 + [FILLER] * 5
    # C hand-full: 110 deck, distribute 5 (hand=limit), play 110 x4 turn1
    deckC = [C110] * 12 + [FILLER] * 3
    specs = [
        ("A_gate_high", deckA, [C110, C110, C110], 3, {1: C110, 2: C110, 3: C110}),
        ("B_gate_low", deckB, [C1, C1, C1], 3, {t: C1 for t in range(1, 7)}),
        ("C_hand_full", deckC, [C110, C110, C110], 5, {1: C110, 2: C110, 3: C110}),
    ]
    with out.open("w", encoding="utf-8") as f:
        for tag, deck, initial, dist, script in specs:
            try:
                rows = run(master, tag, deck, SEED, initial, dist, script)
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
                summary["games"].append({"tag": tag, "rows": rows})
            except Exception as e:  # noqa: BLE001
                import traceback; traceback.print_exc()
                summary["games"].append({"tag": tag, "error": f"{type(e).__name__}: {e}"})
                gc.collect()
    (ROOT / "data/_simfid_pitem312_probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", out, flush=True)


if __name__ == "__main__":
    main()