"""f2-engine-gap oracle 探针②b：no-op effect 精确测量（强制出牌 + 纯打分卡 + 原始手牌快照）。

修正②a：greedy 会避开功能卡 → 改 play_id 强制；slump/debuff 用 base9 纯打分卡测单卡分差；
growth 用 initial_card 把 042 放进开局手牌；pbr 强制打 110 上好调再看回合开始削减。
只读 oracle，不拷源码不重编，探针不提交。
"""
from __future__ import annotations
import ctypes, gc, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
DLL = ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"
os.environ["GKMS_NATIVE_LIB"] = str(DLL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(WHEEL))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
os.chdir(WHEEL / "GakumasCLI")

from GakumasCLI.scenario.exam_session import (Master, ExamLoading, ProduceState,  # noqa: E402
                                              SegmentConfig, open_exam)

MASK = 0xFFFFFFFF


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


def wait_free(min_mb=1024, cap_s=600):
    t0 = time.perf_counter()
    while free_mb() < min_mb and time.perf_counter() - t0 < cap_s:
        print(f"  [mem] free {free_mb():.0f}MB, wait 20s", flush=True); time.sleep(20)


def xs(s):
    s ^= (s << 13) & MASK; s ^= s >> 17; s ^= (s << 5) & MASK
    return s & MASK


def rng_steps(a, b, cap=200000):
    if a == b: return 0
    s = a
    for i in range(1, cap + 1):
        s = xs(s)
        if s == b: return i
    return None


def build(master, deck, seed, gimmick=None, enchants=(), limit_turn=12, initial=None):
    produce = ProduceState(stamina=60, max_stamina=60, deck_cards=deck,
                           item_enchant_ids=list(enchants), plan_type=1)
    cfg = SegmentConfig(segment_id="probe2b", segment_type="Audition Mid1", limit_turn=limit_turn,
                        score_cap=None, parameter_type=None, seed=seed, gimmick_group_id=gimmick,
                        audition_permils={1: 1000, 2: 1000, 3: 1000},
                        audition_parameter_values={1: 100, 2: 100, 3: 100},
                        audition_npc_rng_advances=0, turn_start_distribute=3,
                        eligible_supports=(), resolve_initial_cards=True,
                        initial_card_id=initial,
                        upgrade_tiers=set(master.cards), drink_ids=(),
                        lesson_start_enchant_ids=list(enchants))
    return open_exam(ExamLoading(master, produce, cfg))


def hand_raw(s):
    return [dict(c) for c in s.deck.hand]


def snap(s):
    o = s.observe()
    return {"rng": int(s.deck.rng.state), "turn": o.get("turn"), "score": o.get("score"),
            "stamina": o.get("stamina"), "hand_n": len(o.get("hand", [])),
            "hand_ids": [c.get("produce_card_id") for c in o.get("hand", [])],
            "deck_count": o.get("deck_count"), "grave_count": o.get("grave_count"),
            "trouble": o.get("trouble_states"), "aggressive": o.get("aggressive"),
            "block": o.get("block"), "review": o.get("review"),
            "parameter_buff": (o.get("timed_layers") or {}).get("parameter_buff_remaining"),
            "finished": o.get("finished")}


def run(master, deck, seed, gimmick, script, tag, enchants=(), limit_turn=12, initial=None, out=None):
    wait_free()
    s = build(master, deck, seed, gimmick, enchants, limit_turn, initial)
    rows = [{"tag": tag, "kind": "open", "hand_raw": hand_raw(s), **snap(s)}]
    prev = snap(s)
    n = 0
    while not s.finished and n < 80:
        turn = prev["turn"]
        mode = script.get(turn, "skip")
        hand = list(s.deck.hand)
        action = ("end",); played = None; resolved = None
        if isinstance(mode, tuple) and mode[0] == "play_id":
            for i, inst in enumerate(hand):
                if inst.get("produce_card_id") == mode[1] and s.can_play(inst):
                    action = ("play", i); played = mode[1]
                    rc = s.deck.refresh_card(inst)
                    resolved = {"playEffects": [{"id": l.get("produceExamEffectId"),
                                                 "v1": (master.effects.get(l.get("produceExamEffectId"), {}).get("effectValue1"))}
                                                for l in rc.get("playEffects", [])],
                                "customize_lesson_add": rc.get("customize_lesson_add"),
                                "dynamic_grow_effect_ids": rc.get("dynamic_grow_effect_ids")}
                    break
        before = snap(s)
        s.step(action, observe=False)
        after = snap(s)
        cons = rng_steps(before["rng"], after["rng"])
        rows.append({"tag": tag, "kind": "step", "i": n, "action": list(action), "played": played,
                     "resolved": resolved, "turn_before": turn, "turn_after": after["turn"],
                     "consumption": cons, "score_delta": after["score"] - before["score"],
                     "before": before, "after": after,
                     "hand_raw_after": hand_raw(s) if turn >= 9 else None})
        prev = after; n += 1
    fin = {"tag": tag, "kind": "final", "gimmick": gimmick, "enchants": list(enchants),
           "steps": n, "score": int(s.state.score), "finished": bool(s.finished)}
    for r in rows:
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
    out.write(json.dumps(fin, ensure_ascii=False) + "\n"); out.flush()
    print(f"[{tag}] score={fin['score']} steps={n}", flush=True)
    del s; gc.collect()
    return rows, fin


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "e2b"
    master = Master.load(Path("ro/master/tables"))
    G = "p_exam_gimmick-tower_001-exam_card_play_aggressive-0001-stage_"
    plain = [{"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0} for _ in range(10)]
    out_path = ROOT / "data" / f"_engine_probe_effects_{tag}.jsonl"
    summary = {"tag": tag, "scenarios": []}
    SEED = 777001
    with out_path.open("w", encoding="utf-8") as out:
        def pair(name, gimmick, script, deck=None, enchants=(), limit_turn=12, initial=None,
                 off_gimmick=None, off_enchants=None, off_initial="__same__", off_script=None):
            deck = deck or plain
            try:
                r1, f1 = run(master, deck, SEED, gimmick, script, f"{name}/on", enchants, limit_turn, initial, out)
                r0, f0 = run(master, deck, SEED, off_gimmick, off_script or script, f"{name}/off",
                             off_enchants if off_enchants is not None else (), limit_turn,
                             initial if off_initial == "__same__" else off_initial, out)
                summary["scenarios"].append({"name": name, "score_on": f1["score"], "score_off": f0["score"],
                                             "rows_on": r1, "rows_off": r0})
            except Exception as e:  # noqa: BLE001
                import traceback; traceback.print_exc()
                summary["scenarios"].append({"name": name, "error": f"{type(e).__name__}: {e}"})
                gc.collect()
        # slump：t5 强制打 base9（slump until_turn 5）
        pair("slump2", G + "002", {5: ("play_id", "p_card-00-act-0_001")}, limit_turn=8)
        # param_debuff：t7/t8 强制打 base9（debuff t7 起 until 11）
        pair("debuff2", G + "001", {7: ("play_id", "p_card-00-act-0_001"), 8: ("play_id", "p_card-00-act-0_001")}, limit_turn=12)
        # panic：skip 到 12，t10 起手牌原始快照（费用固定）
        pair("panic2", G + "012", {}, limit_turn=12)
        # growth：042 初始入手，t1 打 042 → t2/t3 打 102（集中卡被 add_grow_effect lesson_add-11）
        gdeck = [{"produce_card_id": "p_card-03-ido-100_042", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-03-act-2_102", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-03-act-2_102", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0}]
        pair("growth2", None, {1: ("play_id", "p_card-03-ido-100_042"), 2: ("play_id", "p_card-03-act-2_102"),
                               3: ("play_id", "p_card-03-act-2_102")}, deck=gdeck, initial="p_card-03-ido-100_042",
             off_script={1: "skip", 2: ("play_id", "p_card-03-act-2_102"), 3: ("play_id", "p_card-03-act-2_102")},
             off_initial=None)
        # pbr：110 初始入手，t1/t2 打 110 上好调；enchant 080-challenge 回合开始削减
        pdeck = [{"produce_card_id": "p_card-01-men-2_110", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-01-men-2_110", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                 {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0}]
        pair("pbr2", None, {1: ("play_id", "p_card-01-men-2_110"), 2: ("play_id", "p_card-01-men-2_110"),
                            3: ("play_id", "p_card-00-act-0_001")}, deck=pdeck, initial="p_card-01-men-2_110",
             enchants=("enchant-pitem_01-3-080-challenge-enc01",), off_enchants=())
    sp = ROOT / "data" / f"_engine_probe_effects_{tag}_summary.json"
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", out_path, sp, flush=True)


if __name__ == "__main__":
    main()
