"""一次性诊断：c/g 覆盖率 + 真实 obs 特征分布 vs 训练 mean/scale + 逐题配对对比。"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

import httpx
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ei-r13"))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "algo", ROOT / "data/bench_repo/submissions/gkagent-ei-r13/algo.py")
algo = importlib.util.module_from_spec(spec)
sys.modules["algo"] = algo
spec.loader.exec_module(algo)

# ---- 1) c/g 覆盖与模式
probe = ROOT / "data" / "_f2_probe_obs.jsonl"
g_pat = Counter()
c_ids = Counter()
n_hand = n_c = n_g = 0
plan_counter = Counter()
for line in probe.read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    if row["kind"] != "step":
        continue
    obs = row["obs"]
    plan_counter[(obs.get("exam") or {}).get("plan")] += 1
    for card in obs.get("hand") or []:
        n_hand += 1
        if card.get("c"):
            n_c += 1
            for cid, cnt in card["c"]:
                c_ids[cid] += 1
        if card.get("g"):
            n_g += 1
            for gid in card["g"]:
                g_pat[gid] += 1
print(f"hand cards={n_hand}, with customize={n_c} ({n_c/n_hand:.1%}), with grow={n_g} ({n_g/n_hand:.1%})")
print("plan dist (steps):", dict(plan_counter))
print("grow patterns:", dict(g_pat.most_common(10)))
print("top customizes:")
for cid, n in c_ids.most_common(15):
    print(f"  {n:5d}  {cid}")

# ---- 2) 真实 obs 特征 z 分布（相对训练 mean/scale）
a = algo.EiR13Algo()
mean, scale = a.net.mean, a.net.scale
leaf_abs_z = np.zeros(104)
leaf_max_z = np.zeros(104)
act_abs_z = np.zeros(33)
n = 0
for line in probe.read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    if row["kind"] != "step":
        continue
    obs = row["obs"]
    legal_play = [x[1] for x in obs.get("legal") or [] if x[0] == "play"]
    if not legal_play:
        continue
    a.begin({"obs": obs, "loadout": {}, "meta": {}}) if False else None
    st = a._state(obs)
    lv = algo.leaf_features(st)
    z = np.abs((lv - mean[:104]) / scale[:104])
    leaf_abs_z += z
    leaf_max_z = np.maximum(leaf_max_z, z)
    card = st.hand[legal_play[0]]
    av = algo.action_features(st, card)
    act_abs_z += np.abs((av - mean[104:]) / scale[104:])
    n += 1
leaf_abs_z /= n
act_abs_z /= n
order = np.argsort(-leaf_abs_z)
print(f"\nfeature OOD (mean |z| vs training, n={n} decision steps), top 20 leaf:")
for i in order[:20]:
    print(f"  {algo.FEATURE_NAMES[i]:32s} mean|z|={leaf_abs_z[i]:8.2f} max|z|={leaf_max_z[i]:10.1f}")
print("top 10 action:")
for i in np.argsort(-act_abs_z)[:10]:
    print(f"  {algo.ACTION_FEATURE_NAMES[i]:32s} mean|z|={act_abs_z[i]:8.2f}")
in_dist = int((leaf_abs_z < 2).sum())
print(f"leaf features with mean|z|<2: {in_dist}/104")

# ---- 3) 逐题配对（按题号聚合各种子）
tok = Path.home().joinpath(".config/gkbench/token").read_text().strip()
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": f"Bearer {tok}"}, timeout=120)
runs = {
    "ours": "template-hif-gkagent-ei-r13-xingkonghod-7b0da3c354fd",
    "uinet": "20261112-040508-hif-template-uinet-matto",
    "greedy": "20261112-003434-hif-template-greedy-matto",
    "random": "20261111-231109-hif-template-random-matto",
}
by_problem = {}
for tag, run in runs.items():
    j = c.get(f"/api/runs/{run}").json()
    agg = {}
    for e in j.get("episodes") or []:
        agg.setdefault(e["id"], []).append(e["score"])
    by_problem[tag] = {pid: sum(v) / len(v) for pid, v in agg.items()}
    print(f"{tag}: {len(agg)} problems, overall mean {sum(e['score'] for e in j['episodes'])/len(j['episodes']):,.0f}")

ours = by_problem["ours"]
for tag in ("uinet", "greedy", "random"):
    other = by_problem[tag]
    common = sorted(set(ours) & set(other))
    if not common:
        print(f"no common problems with {tag}")
        continue
    om = sum(ours[p] for p in common) / len(common)
    tm = sum(other[p] for p in common) / len(common)
    wins = sum(1 for p in common if ours[p] > other[p])
    geo = math.exp(sum(math.log(max(ours[p], 1) / max(other[p], 1)) for p in common) / len(common))
    print(f"paired {len(common)} problems vs {tag}: ours {om:,.0f} vs {tm:,.0f} | "
          f"win {wins}/{len(common)} ({wins/len(common):.1%}) | geomean ratio {geo:.3f}")