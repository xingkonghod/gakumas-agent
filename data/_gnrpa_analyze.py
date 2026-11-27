import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
d = json.load(open(ROOT / "data" / "_gnrpa_gate1.json", encoding="utf-8"))
for k, v in d["ab"].items():
    print(k)
    for s, b in v.items():
        ci = [round(x) for x in b["ci95"]]
        print(f"  {s:8} mean={b['mean_delta']:>12,.0f} ci={ci} p/n/z={b['pos']}/{b['neg']}/{b['zero']}")
print("--- non-zero status rows ---")
for r in d["rows"]:
    if r["status"] != 0:
        print(r["pid"], r["seed"], r["arm"], r["best"], "status", r["status"], "wall", r["wall"])
print("--- per-problem distill delta (mean of 2 seeds) ---")
by = {(r["pid"], r["seed"], r["arm"]): r for r in d["rows"]}
pids = d["pids"]
for pid in pids:
    ss = [s for (s, lab) in d["pid_seeds"][pid]]
    dl = [by[(pid, s, "distill")]["best"] - by[(pid, s, "p0")]["best"] for s in ss]
    me = [by[(pid, s, "mech")]["best"] - by[(pid, s, "p0")]["best"] for s in ss]
    sf = [by[(pid, s, "safe")]["best"] - by[(pid, s, "p0")]["best"] for s in ss]
    tag = "MON" if pid in ["AS-5KZSXANK", "AS-AXME8QK2", "AS-WDKWQYW5", "AS-WNK6ARRZ", "AS-3ZT8ZKB6"] else "low"
    print(f"  {pid} {tag} distill={dl} mech={me} safe_vs_cur={sf}")