"""f2-engine-gap oracle 探针①：考试 RNG 流黑盒记录（不拷源码、不重编、探针不提交）。

方法（同 F0）：固定 seed 建局 → 每步动作前后读 core RNG 状态（session.deck.rng.state），
xorshift32 正向迭代数消费次数 → 关联手牌/牌堆/生成卡变化，反推消费顺序。
对照：① 我们 exam_shuffle 开局牌序模型；② support_cards=[] 消融隔离支援掷点。

用法：.venv\\Scripts\\python.exe data\\_engine_probe_rng.py [tag]
输出：data/_engine_probe_rng_<tag>.jsonl + data/_engine_probe_rng_<tag>_summary.json
"""
from __future__ import annotations

import ctypes
import gc
import json
import os
import sys
import time
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

from GakumasCLI.scenario.exam_session import Master, greedy_policy  # noqa: E402
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402
from gkagent.sim.exam_risk import load_extra_rng_index  # noqa: E402
from gkagent.sim.exam_shuffle import k_before_shuffle, opening_deck_and_rng  # noqa: E402

MASK = 0xFFFFFFFF
RNG_INDEX = load_extra_rng_index()


def free_mb() -> float:
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
        print(f"  [mem] free {free_mb():.0f}MB < {min_mb}MB, wait 20s", flush=True)
        time.sleep(20)


def xs_next(s: int) -> int:
    s ^= (s << 13) & MASK
    s ^= s >> 17
    s ^= (s << 5) & MASK
    return s & MASK


def rng_steps(before: int, after: int, cap: int = 200000):
    """消费次数 = 从 before 正向迭代到 after 的步数；找不到返回 None。"""
    if before == after:
        return 0
    s = before
    for i in range(1, cap + 1):
        s = xs_next(s)
        if s == after:
            return i
    return None


def range_preds(before: int, n: int, width: int):
    """逐步 (state_used, predicted_index)：range = lo + ((state*width)>>32)。"""
    out = []
    s = before
    for _ in range(n):
        out.append((s, (s * width) >> 32))
        s = xs_next(s)
    return out


def deck_ids(session):
    return [c["produce_card_id"] for c in session.deck.deck]


def hand_sig(obs):
    return [(c.get("produce_card_id"), (c.get("number") or {}).get("n") if isinstance(c.get("number"), dict) else c.get("number"),
             (c.get("number") or {}).get("g") if isinstance(c.get("number"), dict) else None) for c in obs.get("hand", [])]


def snap(session):
    obs = session.observe()
    return {"rng": int(session.deck.rng.state), "obs": obs, "deck": deck_ids(session)}


OBS_KEYS = ("turn", "score", "stamina", "block", "playable", "turn_play_count", "stance", "stance_step",
            "full_power_point", "deck_count", "grave_count", "parameter_type", "finished",
            "trouble_states", "timed_layers", "extra_turns", "lesson_buff", "review", "aggressive")


def obs_lite(obs):
    return {k: obs.get(k) for k in OBS_KEYS if k in obs}


def run_game(master, saves, seeds, pid, policy, tag, strip_supports=False, out=None):
    wait_free()
    seed = int(seeds["problems"][pid][0]["seed"])
    lo = expand_loadout(saves[pid]["loadout"])
    if strip_supports:
        lo["support_cards"] = []
    t0 = time.perf_counter()
    session, meta = build_hif_loadout_session(master, lo, seed)
    build_s = time.perf_counter() - t0
    turns = int(saves[pid]["meta"].get("turns") or meta["limit_turn"])
    npc = int(meta.get("npc_count") or 5)
    cards = [(c["produce_card_id"], int(c.get("current_upgrade_count") or 0)) for c in lo["deck_cards"]]
    k = k_before_shuffle(turns, npc)
    _rng, shuffled = opening_deck_and_rng(seed, cards, k)
    model_deck = [c[0] for c in shuffled]
    eng_deck = deck_ids(session)
    open_match = model_deck == eng_deck
    open_row = {"tag": tag, "pid": pid, "seed": seed, "kind": "open", "policy": policy,
                "strip_supports": strip_supports, "build_s": round(build_s, 2),
                "turns": turns, "npc": npc, "k": k, "rng_after_open": int(session.deck.rng.state),
                "model_deck_match": open_match,
                "model_deck_prefix": model_deck[:8], "engine_deck_prefix": eng_deck[:8],
                "engine_deck_len": len(eng_deck), "model_deck_len": len(model_deck),
                "hand": hand_sig(session.observe()),
                "gimmick_group_id": meta.get("gimmick_group_id"),
                "n_supports": len(meta.get("eligible_supports") or []),
                "permils": meta.get("effective_permils")}
    out.write(json.dumps(open_row, ensure_ascii=False) + "\n"); out.flush()
    print(f"[{tag}] {pid} open match={open_match} supports={open_row['n_supports']} "
          f"gimmick={open_row['gimmick_group_id']} build={build_s:.2f}s", flush=True)

    rows = []
    n = 0
    while not session.finished and n < 300:
        before = snap(session)
        obs_b = before["obs"]
        hand = list(session.deck.hand)
        action = None
        played = None
        if policy == "skip":
            action = ("end",)
        else:
            pick = None
            if policy == "mech":
                for i, inst in enumerate(hand):
                    cid = inst.get("produce_card_id")
                    if cid in RNG_INDEX and session.can_play(inst):
                        pick = i
                        break
            if pick is None:
                pick = greedy_policy(session, hand)
            if pick is None:
                action = ("end",)
            else:
                action = ("play", int(pick))
                played = hand[pick].get("produce_card_id")
        session.step(action, observe=False)
        after = snap(session)
        cons = rng_steps(before["rng"], after["rng"])
        hb, ha = hand_sig(obs_b), hand_sig(after["obs"])
        new_in_hand = [x for x in ha if x not in hb]
        deck_b, deck_a = before["deck"], after["deck"]
        inserted = []
        if len(deck_a) > len(deck_b):
            set_b = {}
            for i, cid in enumerate(deck_b):
                set_b.setdefault(cid, []).append(i)
            used = set()
            for i, cid in enumerate(deck_a):
                lst = set_b.get(cid, [])
                pos = None
                for j in lst:
                    if j not in used:
                        pos = j; used.add(j); break
                if pos is None:
                    inserted.append({"index": i, "card": cid})
        row = {"tag": tag, "pid": pid, "seed": seed, "kind": "step", "i": n, "policy": policy,
               "strip_supports": strip_supports, "action": list(action), "played": played,
               "played_mech": sorted(RNG_INDEX.get(played, ())) if played else [],
               "rng_before": before["rng"], "rng_after": after["rng"], "consumption": cons,
               "obs_before": obs_lite(obs_b), "obs_after": obs_lite(after["obs"]),
               "hand_before": hb, "hand_after": ha, "new_in_hand": new_in_hand,
               "deck_len_before": len(deck_b), "deck_len_after": len(deck_a),
               "deck_inserted": inserted,
               "deck_order_changed": deck_b != deck_a and len(deck_b) == len(deck_a)}
        # 生成卡入牌堆：用消费序列预测插入位置（range 宽度=插入前牌堆长）
        if inserted and cons is not None and cons <= 4000:
            preds = range_preds(before["rng"], cons, len(deck_b))
            hits = []
            for ins in inserted:
                match = [j for j, (_s, p) in enumerate(preds) if p == ins["index"]]
                hits.append({"card": ins["card"], "index": ins["index"], "pred_steps": match})
            row["insert_pred"] = hits
        out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
        rows.append(row)
        n += 1
    final = {"tag": tag, "pid": pid, "seed": seed, "kind": "final", "policy": policy,
             "strip_supports": strip_supports, "steps": n, "score": int(session.state.score),
             "finished": bool(session.finished),
             "total_consumption": sum(r["consumption"] or 0 for r in rows),
             "unknown_consumption": sum(1 for r in rows if r["consumption"] is None)}
    out.write(json.dumps(final, ensure_ascii=False) + "\n"); out.flush()
    print(f"[{tag}] {pid} final score={final['score']} steps={n} "
          f"total_rng={final['total_consumption']} unknown={final['unknown_consumption']}", flush=True)
    del session
    gc.collect()
    return open_row, rows, final


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "p1"
    dl = ROOT / "data/bench_local/gkbench_dl/hif"
    seeds = json.loads((dl / "seeds.json").read_text(encoding="utf-8"))
    saves = {}
    with (dl / "saves.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            saves[str(r.get("id"))] = r
    t0 = time.perf_counter()
    master = Master.load(Path("ro/master/tables"))
    print(f"Master.load {time.perf_counter()-t0:.1f}s cards={len(master.cards)} free={free_mb():.0f}MB", flush=True)
    plan = [
        ("AS-227HBGHS", "skip", False), ("AS-227HBGHS", "skip", True),
        ("AS-2CRAZXA5", "skip", False), ("AS-2CRAZXA5", "skip", True),
        ("AS-2CRAZXA5", "mech", False), ("AS-23D5RE8A", "mech", False),
        ("AS-2B4ESEP7", "mech", False), ("AS-6HSQ9JWD", "mech", False),
        ("AS-3Y27F7B3", "mech", False),
    ]
    out_path = ROOT / "data" / f"_engine_probe_rng_{tag}.jsonl"
    summary = {"tag": tag, "dll": str(DLL), "games": []}
    with out_path.open("w", encoding="utf-8") as out:
        for pid, policy, strip in plan:
            gtag = f"{pid}/{policy}{'/nosup' if strip else ''}"
            try:
                open_row, rows, final = run_game(master, saves, seeds, pid, policy, gtag, strip, out)
                by_act = {}
                for r in rows:
                    a = r["action"][0]
                    key = a + ("_mech" if r["played_mech"] else "")
                    d = by_act.setdefault(key, {"n": 0, "cons": 0, "unknown": 0})
                    d["n"] += 1
                    d["cons"] += r["consumption"] or 0
                    d["unknown"] += 1 if r["consumption"] is None else 0
                summary["games"].append({"open": open_row, "final": final, "by_action": by_act,
                                         "mech_steps": [r for r in rows if r["played_mech"]],
                                         "insert_events": [r for r in rows if r["deck_inserted"]]})
            except Exception as e:  # noqa: BLE001
                import traceback; traceback.print_exc()
                summary["games"].append({"pid": pid, "policy": policy, "strip": strip,
                                         "error": f"{type(e).__name__}: {e}"})
                gc.collect()
    sp = ROOT / "data" / f"_engine_probe_rng_{tag}_summary.json"
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", out_path, "and", sp, flush=True)


if __name__ == "__main__":
    main()
