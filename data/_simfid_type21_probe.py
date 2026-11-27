"""sim-fid ③ type21 ExamCardCreateSearch probe (no-commit, <=6 engine games, serial).

sup-3_024 (ExamCardCreateSearch random pool p_random_pool-all-upgrade_1 -> hand).
Controlled deck/hand/plan variation; capture full zones + cons + generated card.
Fit cons = f(pool, owned zones, plan). Engine oracle only, no DLL rebuild, no AGPL copy.
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

MASK = 0xFFFFFFFF
TARGET = "p_card-00-sup-3_024"
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
        print(f"  [mem] free {free_mb():.0f}MB < {min_mb}MB wait 60s", flush=True)
        time.sleep(60)


def xs(s):
    s ^= (s << 13) & MASK; s ^= s >> 17; s ^= (s << 5) & MASK
    return s & MASK


def steps(before, after, cap=200000):
    if before == after:
        return 0
    s = before
    for i in range(1, cap + 1):
        s = xs(s)
        if s == after:
            return i
    return None


def ids(zone):
    return [c.get("produce_card_id") for c in (zone or [])]


def build(master, deck, seed, plan, initial):
    produce = ProduceState(stamina=60, max_stamina=60, deck_cards=deck,
                           item_enchant_ids=[], plan_type=plan)
    cfg = SegmentConfig(segment_id="simfid21", segment_type="Audition Mid1", limit_turn=6,
                        score_cap=None, parameter_type=None, seed=seed, gimmick_group_id=None,
                        audition_permils={1: 1000, 2: 1000, 3: 1000},
                        audition_parameter_values={1: 100, 2: 100, 3: 100},
                        audition_npc_rng_advances=0, turn_start_distribute=3,
                        eligible_supports=(), resolve_initial_cards=True,
                        initial_card_ids=list(initial), upgrade_tiers=set(master.cards),
                        drink_ids=[], lesson_start_enchant_ids=[])
    return open_exam(ExamLoading(master, produce, cfg))


def run(master, tag, deck_ids, seed, plan, initial, plays=1):
    wait_free()
    deck = [{"produce_card_id": i, "base_upgrade_count": 0} for i in deck_ids]
    s = build(master, deck, seed, plan, initial)
    rows = []
    n = 0
    target_plays = 0
    while not s.finished and n < 40 and target_plays < plays:
        hand = list(s.deck.hand)
        pick = None
        for i, inst in enumerate(hand):
            if inst.get("produce_card_id") == TARGET and s.can_play(inst):
                pick = i; break
        if pick is None:
            action = ("end",)
        else:
            action = ("play", int(pick))
        before_rng = int(s.deck.rng.state)
        bz = {z: ids(getattr(s.deck, z, None)) for z in ("hand", "deck", "grave", "lost", "hold")}
        bturn = int(s.turn)
        s.step(action, observe=False)
        after_rng = int(s.deck.rng.state)
        az = {z: ids(getattr(s.deck, z, None)) for z in ("hand", "deck", "grave", "lost", "hold")}
        cons = steps(before_rng, after_rng)
        is_t = action[0] == "play" and hand[pick].get("produce_card_id") == TARGET
        gen = None
        if is_t:
            target_plays += 1
            new = [c for c in az["hand"] if c not in bz["hand"]]
            gen = new
        row = {"tag": tag, "i": n, "turn": bturn, "action": list(action), "is_target": is_t,
               "rng_before": before_rng, "rng_after": after_rng, "cons": cons,
               "before": bz, "after": az, "gen": gen,
               "gen_upg": [int(c.get("current_upgrade_count") or 0) for c in s.deck.hand] if is_t else None}
        rows.append(row)
        if is_t:
            owned = set(bz["hand"]) | set(bz["deck"]) | set(bz["grave"]) | set(bz["lost"])
            print(f"[{tag}] t{bturn} PLAY cons={cons} deck={len(bz['deck'])} hand={len(bz['hand'])} "
                  f"grave={len(bz['grave'])} owned_unique={len(owned)} gen={gen}", flush=True)
        n += 1
    del s; gc.collect()
    return rows


def main():
    t0 = time.perf_counter()
    master = Master.load(Path("ro/master/tables"))
    print(f"Master.load {time.perf_counter()-t0:.1f}s free={free_mb():.0f}MB", flush=True)
    SEED = 880021
    plans = []
    # G1 plan1 small deck; G2 plan1 large deck; G3 plan0; G4 plan2; G5 plan1 owned-heavy; G6 plan1 two plays
    g1 = [TARGET] + [FILLER] * 4
    g2 = [TARGET] + [FILLER] * 19
    poolcards = ["p_card-01-act-2_032", "p_card-00-men-3_003", "p_card-01-act-2_061",
                 "p_card-00-men-1_007", "p_card-00-men-1_005", "p_card-00-act-2_009"]
    g5 = [TARGET] + poolcards * 3 + [FILLER] * 2
    g6 = [TARGET, TARGET] + [FILLER] * 6
    specs = [
        ("G1_plan1_small", g1, 1, [TARGET, FILLER, FILLER], 1),
        ("G2_plan1_large", g2, 1, [TARGET, FILLER, FILLER], 1),
        ("G3_plan0_small", g1, 0, [TARGET, FILLER, FILLER], 1),
        ("G4_plan2_small", g1, 2, [TARGET, FILLER, FILLER], 1),
        ("G5_plan1_owned", g5, 1, [TARGET, FILLER, FILLER], 1),
        ("G6_plan1_twoplay", g6, 1, [TARGET, TARGET, FILLER], 2),
    ]
    out = ROOT / "data/_simfid_type21_probe.jsonl"
    summary = {"seed": SEED, "target": TARGET, "games": []}
    with out.open("w", encoding="utf-8") as f:
        for tag, deck, plan, initial, plays in specs:
            try:
                rows = run(master, tag, deck, SEED, plan, initial, plays)
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
                summary["games"].append({"tag": tag, "plan": plan, "deck_n": len(deck),
                                         "target_rows": [r for r in rows if r["is_target"]]})
            except Exception as e:  # noqa: BLE001
                import traceback; traceback.print_exc()
                summary["games"].append({"tag": tag, "error": f"{type(e).__name__}: {e}"})
                gc.collect()
    (ROOT / "data/_simfid_type21_probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", out, flush=True)


if __name__ == "__main__":
    main()