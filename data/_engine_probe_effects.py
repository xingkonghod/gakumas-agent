"""f2-engine-gap oracle 探针②：no-op effect 黑盒行为（塔 gimmick / panic / PBR / 成长）。

构造最小考试（自定义 SegmentConfig + 固定 seed + 脚本动作），成对跑「有 gimmick vs 无」，
记录 trouble_states / 手牌数 / RNG 消费 / 分数差 → 量化我们 sim no-op 项的真实行为。
只读引擎当 oracle，不拷源码不重编，探针不提交。

用法：.venv\\Scripts\\python.exe data\\_engine_probe_effects.py [tag]
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
                                              SegmentConfig, open_exam, greedy_policy)
from gkbench.save import expand_loadout  # noqa: E402

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


def build(master, deck, seed, gimmick=None, enchants=(), limit_turn=12, plan_type=1):
    produce = ProduceState(stamina=60, max_stamina=60, deck_cards=deck,
                           item_enchant_ids=list(enchants), plan_type=plan_type)
    cfg = SegmentConfig(segment_id="probe", segment_type="Audition Mid1", limit_turn=limit_turn,
                        score_cap=None, parameter_type=None, seed=seed,
                        gimmick_group_id=gimmick,
                        audition_permils={1: 1000, 2: 1000, 3: 1000},
                        audition_parameter_values={1: 100, 2: 100, 3: 100},
                        audition_npc_rng_advances=0, turn_start_distribute=3,
                        eligible_supports=(), resolve_initial_cards=False,
                        upgrade_tiers=set(master.cards), drink_ids=(),
                        lesson_start_enchant_ids=list(enchants))
    return open_exam(ExamLoading(master, produce, cfg))


def snap(s):
    o = s.observe()
    return {"rng": int(s.deck.rng.state), "turn": o.get("turn"), "score": o.get("score"),
            "stamina": o.get("stamina"), "hand": [(c.get("produce_card_id"), c.get("cost")) for c in o.get("hand", [])],
            "hand_n": len(o.get("hand", [])), "deck_count": o.get("deck_count"),
            "grave_count": o.get("grave_count"), "trouble": o.get("trouble_states"),
            "aggressive": o.get("aggressive"), "block": o.get("block"),
            "review": o.get("review"), "parameter_buff": (o.get("timed_layers") or {}).get("parameter_buff_remaining"),
            "finished": o.get("finished")}


def run(master, deck, seed, gimmick, script, tag, enchants=(), limit_turn=12, out=None):
    """script: dict turn->'play_best'|'skip' (default skip)."""
    wait_free()
    s = build(master, deck, seed, gimmick, enchants, limit_turn)
    rows = []
    prev = snap(s)
    rows.append({"tag": tag, "kind": "open", **prev})
    n = 0
    while not s.finished and n < 80:
        turn = prev["turn"]
        mode = script.get(turn, "skip")
        hand = list(s.deck.hand)
        action = ("end",)
        played = None
        if mode == "play_best":
            pick = greedy_policy(s, hand)
            if pick is not None:
                action = ("play", int(pick)); played = hand[pick].get("produce_card_id")
        before = snap(s)
        s.step(action, observe=False)
        after = snap(s)
        cons = rng_steps(before["rng"], after["rng"])
        rows.append({"tag": tag, "kind": "step", "i": n, "action": list(action), "played": played,
                     "turn_before": turn, "turn_after": after["turn"], "consumption": cons,
                     "before": before, "after": after})
        prev = after
        n += 1
    fin = {"tag": tag, "kind": "final", "gimmick": gimmick, "steps": n,
           "score": int(s.state.score), "finished": bool(s.finished)}
    for r in rows:
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
    out.write(json.dumps(fin, ensure_ascii=False) + "\n"); out.flush()
    print(f"[{tag}] gimmick={gimmick} score={fin['score']} steps={n}", flush=True)
    del s; gc.collect()
    return rows, fin


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "e1"
    master = Master.load(Path("ro/master/tables"))
    saves = {}
    with (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line); saves[r["id"]] = r
    base_lo = expand_loadout(saves["AS-227HBGHS"]["loadout"])
    base_deck = [dict(c) for c in base_lo["deck_cards"]]
    G = "p_exam_gimmick-tower_001-exam_card_play_aggressive-0001-stage_"
    out_path = ROOT / "data" / f"_engine_probe_effects_{tag}.jsonl"
    summary = {"tag": tag, "scenarios": []}
    SEED = 777001
    with out_path.open("w", encoding="utf-8") as out:
        def pair(name, gimmick, script, deck=None, enchants=(), limit_turn=12):
            deck = deck or base_deck
            try:
                r1, f1 = run(master, deck, SEED, gimmick, script, f"{name}/on", enchants, limit_turn, out)
                r0, f0 = run(master, deck, SEED, None, script, f"{name}/off", enchants, limit_turn, out)
                summary["scenarios"].append({"name": name, "gimmick": gimmick,
                                             "score_on": f1["score"], "score_off": f0["score"],
                                             "delta": f1["score"] - f0["score"],
                                             "rows_on": r1, "rows_off": r0})
            except Exception as e:  # noqa: BLE001
                import traceback; traceback.print_exc()
                summary["scenarios"].append({"name": name, "error": f"{type(e).__name__}: {e}"})
                gc.collect()
        # S1 抽牌减少（turn3 起 aggressive<7 → draw_down 1）：skip 梯
        pair("draw_down", G + "007", {})
        # S2 低谷 slump（turn5 aggressive<11）：t5/t6 打最大牌
        pair("slump", G + "002", {5: "play_best", 6: "play_best"})
        # S3 panic（turn10 block<80）：skip 到 12，看 t10/t11 消费与手牌费用
        pair("panic", G + "012", {}, limit_turn=12)
        # S4 gimmick_parameter_debuff（turn7 aggressive<18）：t7/t8 打牌
        pair("param_debuff", G + "001", {7: "play_best", 8: "play_best"})
        # S5 成长：042（add_grow_effect lesson_add-11 给集中卡）+ 102（集中卡）
        grow_deck = [{"produce_card_id": "p_card-03-ido-100_042", "base_upgrade_count": 0},
                     {"produce_card_id": "p_card-03-act-2_102", "base_upgrade_count": 0},
                     {"produce_card_id": "p_card-03-act-2_102", "base_upgrade_count": 0},
                     {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                     {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                     {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0}]
        pair("growth", None, {1: "play_best", 2: "play_best", 3: "play_best"}, deck=grow_deck)
        # S6 PBR：enchant-pitem_01-3-080-challenge-enc01（回合开始好调减少）+ 好调卡
        pbr_deck = [{"produce_card_id": "p_card-01-men-2_110", "base_upgrade_count": 0},
                    {"produce_card_id": "p_card-01-men-2_110", "base_upgrade_count": 0},
                    {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                    {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                    {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0},
                    {"produce_card_id": "p_card-00-act-0_001", "base_upgrade_count": 0}]
        pair("pbr", None, {1: "play_best", 2: "play_best", 3: "play_best"}, deck=pbr_deck,
             enchants=("enchant-pitem_01-3-080-challenge-enc01",))
    sp = ROOT / "data" / f"_engine_probe_effects_{tag}_summary.json"
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", out_path, sp, flush=True)


if __name__ == "__main__":
    main()
