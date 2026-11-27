"""m1-fix3 (b) 诊断（不提交）：4 失锁怪物 deck-modify 失锁根因 + 重扫可行性。

对每个怪物：固定 seed 建局 → 贪心打完，逐步喂 uinet obs 给 v3 vendor Draws，记录 open/seen/skip
轨迹与 open=False 时机；在 true seed 附近小范围跑 seed_scan 内核，对比 (a) 冻结 seen/skip vs
(b) 仅开局可靠抽牌（turn1，任何 deck-modify 之前）是否命中 true seed → 判定重扫能否恢复锁定。
AGPL 引擎只作 oracle；不重编 DLL；不改 v2/v3 原版。

用法：.venv\\Scripts\\python.exe data\\_m1b_monster_diag.py
输出：data/_m1b_monster_diag.json
"""
from __future__ import annotations
import gc, json, os, random, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v3"
VENDOR = SUB / "vendor"
sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(ROOT / "data/bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 复用 v3 的引擎路径自配置（vendor DLL，不重编）
import importlib.util
spec = importlib.util.spec_from_file_location("algo_v3_diag", SUB / "algo.py")
V3 = importlib.util.module_from_spec(spec); sys.modules["algo_v3_diag"] = V3
spec.loader.exec_module(V3)
from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.save import expand_loadout  # noqa: E402
import draws as draws_mod  # noqa: E402
import opening as opening_mod  # noqa: E402
import seedscan  # noqa: E402
from uinet.env import Battle  # noqa: E402
from GakumasCLI.scenario.exam_session import greedy_policy  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line); saves[str(r.get("id"))] = r

MONSTERS = ["AS-5KZSXANK", "AS-B38CARVV", "AS-VWAF2GDN", "AS-HTNFZWKG"]
OPENING_SEEDS = V3.OPENING_SEEDS


def kernel_match(kernel, k, pre, seen, skip, pool, turns, true_seed, span=60000):
    """在 [true-span, true+span] 跑内核，返回 true_seed 是否命中（小范围快扫）。"""
    lo, hi = max(0, true_seed - span), true_seed + span + 1
    job = seedscan.Scan(k, pre, list(seen), list(skip), pool, turns, procs=4, lo=lo, hi=hi)
    t0 = time.perf_counter()
    while True:
        res = job.poll()
        if res is not None:
            break
        if time.perf_counter() - t0 > 60:
            job.stop(); return None
        time.sleep(0.05)
    return true_seed in res, len(res)


def diag(pid):
    lo = expand_loadout(saves[pid]["loadout"])
    if pid in seeds["problems"]:
        seed = int(seeds["problems"][pid][0]["seed"]); slab = "dev"
    else:
        seed = random.Random(f"{pid}/exv3/0").randrange(1, 1 << 31); slab = "gen"
    master = engine.master()
    opens = [opening_mod.opening(master, lo, s) for s in OPENING_SEEDS]
    pre, k = opens[0][0], opens[0][1]
    pool, mutable = opening_mod.turn_pool(opens[0][2])
    inv = draws_mod.invariant_hand([V3._ids(o[2].deck.hand) for o in opens])
    tr = draws_mod.Draws(pre, inv)
    # 贪心打完，喂 obs
    b = Battle(dict(lo, seed=seed))
    actions, hands = [], []
    open_false_at = None
    seen_at_open = None
    opening_seen = None
    opening_skip = None
    traj = []
    n = 0
    while not b.finished and n < 300:
        obs = b.obs()
        tr.update(obs)
        hands.append([c["id"] for c in obs["hand"]])
        if n == 0:
            opening_seen = list(tr.seen)  # 首 obs（turn1 开局抽牌，任何 play/deck-modify 之前）= 可靠
            opening_skip = list(tr.skip.elements())
        if not tr.open and open_false_at is None:
            open_false_at = n
            seen_at_open = list(tr.seen)
        traj.append({"k": n, "turn": int(obs["exam"]["turn"]), "open": tr.open,
                     "seen_n": len(tr.seen), "skip_n": sum(tr.skip.values()),
                     "deck_n": len(obs["deck"]), "hand_n": len(obs["hand"])})
        sess = b.session
        choice = greedy_policy(sess, list(sess.deck.hand))
        a = ("end",) if choice is None else ("play", int(choice))
        actions.append(a)
        b.step(a)
        n += 1
    if opening_seen is None:
        opening_seen = list(tr.seen)
        opening_skip = list(tr.skip.elements())
    frozen_seen, frozen_skip = list(tr.seen), list(tr.skip.elements())
    kernel = seedscan.kernel()
    turns = [int(t) for t in b.obs()["exam"]["types"][:mutable]] if pool else None
    # 用开局 turn attrs（前 mutable 个）——贪心局全程一致
    res = {"pid": pid, "seed": seed, "seed_lab": slab, "steps": n, "score": int(b.session.state.score),
           "pre_n": len(pre), "k": k, "mutable": mutable,
           "open_false_at": open_false_at, "seen_at_open": seen_at_open,
           "frozen_seen_n": len(frozen_seen), "frozen_skip_n": len(frozen_skip),
           "opening_seen": opening_seen, "traj": traj}
    # 内核命中测试（true seed 附近）
    if kernel and pre and len(pre) <= 64:
        try:
            ma = kernel_match(kernel, k, pre, frozen_seen, frozen_skip, pool, turns, seed)
            res["kernel_frozen_match"] = ma
        except Exception as e:  # noqa: BLE001
            res["kernel_frozen_match"] = f"err {type(e).__name__}: {e}"
        try:
            mb = kernel_match(kernel, k, pre, opening_seen, opening_skip or [], pool, turns, seed)
            res["kernel_opening_match"] = mb
        except Exception as e:  # noqa: BLE001
            res["kernel_opening_match"] = f"err {type(e).__name__}: {e}"
    print(f"[{pid}] seed={seed}({slab}) steps={n} open_false_at={open_false_at} "
          f"frozen_seen={len(frozen_seen)} opening_seen={len(opening_seen)} "
          f"frozen_match={res.get('kernel_frozen_match')} opening_match={res.get('kernel_opening_match')}", flush=True)
    del b; gc.collect()
    return res


def main():
    out = {}
    for pid in MONSTERS:
        if pid not in saves:
            print(f"skip {pid}", flush=True); continue
        try:
            out[pid] = diag(pid)
        except Exception as e:  # noqa: BLE001
            import traceback; traceback.print_exc()
            out[pid] = {"error": f"{type(e).__name__}: {e}"}
        gc.collect()
    (ROOT / "data/_m1b_monster_diag.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved data/_m1b_monster_diag.json", flush=True)


if __name__ == "__main__":
    main()