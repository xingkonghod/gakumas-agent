"""m1-fix3 (c)① 探针（不提交）：type21 ExamCardCreateSearch 随机池消费次数公式。

sup-3_024「花枝萌芽的季节」= ExamCardCreateSearch(1) + ExamPlayableValueAdd + ExamEffectTimer + ExamCardDraw(1)。
黑盒：固定 seed 建局 → 优先打 sup-3_024 → 每步前后读 session.deck.rng.state 迭代数消费次数，
关联生成卡入牌堆位置 / 牌堆长 / 手牌变化，反推随机池选取口径（候选池权重 / signed_key）。
对照 _engine_probe_rng.py 口径。AGPL 引擎只作 oracle，不拷源码、不重编。

用法：.venv\\Scripts\\python.exe data\\_m1b_type21.py [tag]
输出：data/_m1b_type21_<tag>.jsonl + data/_m1b_type21_<tag>_summary.json
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
sys.path.insert(0, str(ROOT / "data/bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
os.chdir(WHEEL / "GakumasCLI")

from GakumasCLI.scenario.exam_session import Master, greedy_policy  # noqa: E402
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

MASK = 0xFFFFFFFF
TARGET = "p_card-00-sup-3_024"


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
        print(f"  [mem] free {free_mb():.0f}MB < {min_mb}MB, wait 30s", flush=True)
        time.sleep(30)


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


def range_preds(before, n, width):
    out = []; s = before
    for _ in range(n):
        out.append((s, (s * width) >> 32)); s = xs(s)
    return out


def deck_ids(session):
    return [c["produce_card_id"] for c in session.deck.deck]


def snap(session):
    return {"rng": int(session.deck.rng.state), "deck": deck_ids(session),
            "hand": [c["produce_card_id"] for c in session.deck.hand],
            "grave": [c["produce_card_id"] for c in session.deck.grave]}


def run_game(master, saves, seeds, pid, seed, tag, out):
    wait_free()
    lo = expand_loadout(saves[pid]["loadout"])
    t0 = time.perf_counter()
    session, meta = build_hif_loadout_session(master, lo, seed)
    print(f"[{tag}] {pid} seed={seed} build={time.perf_counter()-t0:.2f}s "
          f"sup324_in_deck={sum(c['produce_card_id']==TARGET for c in lo['deck_cards'])}", flush=True)
    rows = []; n = 0
    while not session.finished and n < 300:
        before = snap(session)
        hand = list(session.deck.hand)
        # 优先打 sup-3_024（可出时），否则贪心
        pick = None
        for i, inst in enumerate(hand):
            if inst.get("produce_card_id") == TARGET and session.can_play(inst):
                pick = i; break
        if pick is None:
            pick = greedy_policy(session, hand)
        if pick is None:
            action = ("end",); played = None
        else:
            action = ("play", int(pick)); played = hand[pick].get("produce_card_id")
        session.step(action, observe=False)
        after = snap(session)
        cons = steps(before["rng"], after["rng"])
        deck_b, deck_a = before["deck"], after["deck"]
        inserted = []
        if len(deck_a) > len(deck_b):
            set_b = {}
            for i, cid in enumerate(deck_b):
                set_b.setdefault(cid, []).append(i)
            used = set()
            for i, cid in enumerate(deck_a):
                lst = set_b.get(cid, []); pos = None
                for j in lst:
                    if j not in used:
                        pos = j; used.add(j); break
                if pos is None:
                    inserted.append({"index": i, "card": cid})
        row = {"tag": tag, "pid": pid, "seed": seed, "i": n, "action": list(action), "played": played,
               "is_target": played == TARGET, "rng_before": before["rng"], "rng_after": after["rng"],
               "consumption": cons, "deck_len_before": len(deck_b), "deck_len_after": len(deck_a),
               "hand_before": before["hand"], "hand_after": after["hand"],
               "grave_len_before": len(before["grave"]), "grave_len_after": len(after["grave"]),
               "deck_inserted": inserted}
        if inserted and cons is not None and cons <= 4000:
            preds = range_preds(before["rng"], cons, len(deck_b))
            row["insert_pred"] = [{"card": ins["card"], "index": ins["index"],
                                   "pred_steps": [j for j, (_s, p) in enumerate(preds) if p == ins["index"]]}
                                  for ins in inserted]
        out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
        rows.append(row)
        if played == TARGET:
            print(f"  k={n} PLAY sup324 cons={cons} deck_len={len(deck_b)} inserted={inserted} "
                  f"insert_pred={row.get('insert_pred')}", flush=True)
        n += 1
    final = {"tag": tag, "pid": pid, "seed": seed, "steps": n, "score": int(session.state.score),
             "target_plays": sum(1 for r in rows if r["is_target"]),
             "target_cons": [r["consumption"] for r in rows if r["is_target"]]}
    out.write(json.dumps(final, ensure_ascii=False) + "\n"); out.flush()
    print(f"[{tag}] {pid} final score={final['score']} target_plays={final['target_plays']} "
          f"target_cons={final['target_cons']}", flush=True)
    del session; gc.collect()
    return rows, final


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "p1"
    dl = ROOT / "data/bench_local/gkbench_dl/hif"
    seeds = json.loads((dl / "seeds.json").read_text(encoding="utf-8"))
    saves = {}
    with (dl / "saves.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line); saves[str(r.get("id"))] = r
    t0 = time.perf_counter()
    master = Master.load(Path("ro/master/tables"))
    print(f"Master.load {time.perf_counter()-t0:.1f}s free={free_mb():.0f}MB", flush=True)
    # 3 题含 sup-3_024（dev seed），优先打它，观察消费次数 vs 牌堆长 / 生成卡
    plan = ["AS-4BFABQK9", "AS-3TJXEB7T", "AS-JQXN3NK5"]
    out_path = ROOT / f"data/_m1b_type21_{tag}.jsonl"
    summary = {"tag": tag, "dll": str(DLL), "target": TARGET, "games": []}
    with out_path.open("w", encoding="utf-8") as out:
        for pid in plan:
            if pid not in saves:
                print(f"skip {pid} (no save)", flush=True); continue
            seed = int(seeds["problems"][pid][0]["seed"]) if pid in seeds["problems"] else 12345
            try:
                rows, final = run_game(master, saves, seeds, pid, seed, f"{pid}", out)
                summary["games"].append({"final": final,
                                         "target_rows": [r for r in rows if r["is_target"]],
                                         "insert_events": [r for r in rows if r["deck_inserted"]]})
            except Exception as e:  # noqa: BLE001
                import traceback; traceback.print_exc()
                summary["games"].append({"pid": pid, "error": f"{type(e).__name__}: {e}"})
                gc.collect()
    (ROOT / f"data/_m1b_type21_{tag}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", out_path, flush=True)


if __name__ == "__main__":
    main()