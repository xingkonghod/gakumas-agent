"""gnrpa-spec 探针1（不提交）：核实 v3 session.drinks 现状 + SAFE_KINDS 划分 + 原生 GNRPA 饮料行为。

问题：lead 任务书假设「v3 session.drinks 现状=空？」——saves.jsonl loadout 带 drink_ids，
hif.build_hif_loadout_session → config.drink_ids → NativeSession.drinks 非空？
若真非空，原生 GNRPA 已在搜全部饮料（含青汁 create_random / 苏打 draw 等 UNSAFE）。
本探针：16 门题饮料清单 + 2 代表题 100k-transition 短搜（drinks 现状 / 空 / SAFE 子集三臂）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
V3 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v3"
os.environ["GKMS_ROOT"] = str(ROOT / "data" / "GKMSMainWheel")
os.environ["GKMSCLIGPU_LIB"] = str(V3 / "vendor" / "gkmscore.dll")
os.environ["GKMS_NATIVE_LIB"] = str(V3 / "vendor" / "gkmscore.dll")
os.environ["UINET_NATIVE_LIB"] = str(V3 / "vendor" / "gkmscore.dll")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.save import expand_loadout  # noqa: E402
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

LOW12 = ["AS-3G6FFZZT", "AS-QV6QCSN9", "AS-P8ZJTXNA", "AS-VH8WYE6J", "AS-5XB2AEHN", "AS-DE36RWPS",
         "AS-BD5EAA22", "AS-DEBX8BX7", "AS-WDKWQYW5", "AS-B38CARVV", "AS-VWAF2GDN", "AS-HTNFZWKG"]
MONSTER5 = ["AS-5KZSXANK", "AS-AXME8QK2", "AS-WDKWQYW5", "AS-WNK6ARRZ", "AS-3ZT8ZKB6"]
PIDS = sorted(set(LOW12) | set(MONSTER5))

# SAFE_KINDS = out/_drinks_phase2_plan.md 阶段2a 纯数值段（draw/turn_start_draw/search_move/
# extra_turn/create_random/force_play_search 排除；unknown kind 不在集合内自动排除）。
SAFE_KINDS = {"extra_plays", "score_buff", "half_cost", "double_cost", "stamina_cost",
              "stamina", "vitality", "aggressive", "impression", "full_power_point",
              "condition", "perfect_condition", "score"}
cat = json.loads((ROOT / "data" / "knowledge" / "drinks.json").read_text(encoding="utf-8"))
SAFE_IDS, DRINK_INFO = set(), {}
for d in cat["drinks"]:
    kinds = [e["kind"] for e in d.get("effects") or []]
    det = bool((d.get("rng") or {}).get("deterministic")) and not (d.get("rng") or {}).get("unknown")
    safe = bool(kinds) and all(k in SAFE_KINDS for k in kinds) and det
    DRINK_INFO[d["id"]] = {"name": d.get("name"), "kinds": kinds, "safe": safe}
    if safe:
        SAFE_IDS.add(d["id"])


def safe_subset(drinks):
    return [d for d in drinks if d in SAFE_IDS]


def main():
    nat, ns = engine.native()
    master = engine.master()
    print(f"rules_version={getattr(nat, 'exam_rules_version', '?')} safe_ids={len(SAFE_IDS)}", flush=True)
    inv = {}
    for pid in PIDS:
        if pid not in saves:
            print(f"{pid}: NOT IN SAVES", flush=True)
            continue
        lo = expand_loadout(saves[pid]["loadout"])
        drinks = list(lo.get("drink_ids") or [])
        ss = safe_subset(drinks)
        inv[pid] = {"drinks": drinks, "safe": ss,
                    "kinds": {d: DRINK_INFO.get(d, {}).get("kinds", ["?"]) for d in drinks}}
        print(f"{pid}: drinks={drinks} safe={ss}", flush=True)

    # 代表题：一个带 SAFE 大头（蛋白粉），一个混合 UNSAFE
    reps = []
    for pid in PIDS:
        if pid in inv and inv[pid]["safe"] and len(reps) < 1:
            reps.append(pid)
    for pid in PIDS:
        if pid in inv and any(d not in SAFE_IDS for d in inv[pid]["drinks"]) and pid not in reps:
            reps.append(pid)
            break
    out = {"safe_ids": sorted(SAFE_IDS), "inventory": inv, "reps": {}}
    for pid in reps:
        lo = expand_loadout(saves[pid]["loadout"])
        seed = int(seeds["problems"][pid][0]["seed"]) if pid in seeds["problems"] else 12345
        sess, _ = build_hif_loadout_session(master, lo, seed)
        legal = sess.legal_actions()
        rec = {"seed": seed, "drinks_native": list(sess.drinks),
               "legal_drinks": [list(a) for a in legal if a[0] == "drink"],
               "n_legal": len(legal), "arms": {}}
        print(f"\n== {pid} seed={seed} drinks={list(sess.drinks)} legal_drinks={rec['legal_drinks']}", flush=True)
        arms = {"current": list(sess.drinks), "empty": [], "safe": safe_subset(list(sess.drinks))}
        for name, dl in arms.items():
            s = sess.clone()
            if name != "current":
                s.drinks = dl
            ns._cache = None
            t0 = time.perf_counter()
            path, st = ns.policy_search(s, transitions=100000, seed=182, variant="gnrpa", stabilization=3)
            dt = time.perf_counter() - t0
            drinks_used = [list(a) for a in path if a[0] == "drink"]
            rec["arms"][name] = {"drinks": dl, "best": int(st["best_score"]), "status": int(st["status"]),
                                 "expansions": int(st["expansions"]), "seconds": round(dt, 2),
                                 "n_drink_actions": len(drinks_used), "drink_actions": drinks_used[:8],
                                 "path_len": len(path)}
            print(f"  {name}: best={st['best_score']:,} drinks_in_path={len(drinks_used)} "
                  f"{drinks_used[:4]} {dt:.2f}s status={st['status']}", flush=True)
            del s
        out["reps"][pid] = rec
        del sess
    (ROOT / "data" / "_gnrpa_probe1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved data/_gnrpa_probe1.json", flush=True)


if __name__ == "__main__":
    main()