"""sim-fidelity type21 broad formula scan (no engine run, existing m1b data)."""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
tdir = ROOT / "data/GKMSMainWheel/GakumasCLI/ro/master/tables"
MASK = 0xFFFFFFFF


def xs(s):
    s ^= (s << 13) & MASK
    s ^= s >> 17
    s ^= (s << 5) & MASK
    return s & MASK


def stream(before, n):
    out = []
    s = before
    for _ in range(n):
        out.append(s)
        s = xs(s)
    return out


def signed(u):
    return u - (1 << 32) if u >= (1 << 31) else u


rows = [json.loads(l) for l in (tdir / "ProduceCardPool.jsonl").open(encoding="utf-8") if l.strip()]
dec = [r.get("decoded", r) for r in rows]
agg = {r["id"]: r for r in dec}
pool = [(r["id"], r.get("upgradeCount"), r.get("ratio")) for r in agg["p_random_pool-all-upgrade_1"]["produceCardRatios"]]
idx = {c: i for i, (c, u, r) in enumerate(pool)}
N = len(pool)
games = [
    {"pid": "AS-4BFABQK9", "before": 1204118744, "cons": 132, "gen": "p_card-01-act-2_061"},
    {"pid": "AS-3TJXEB7T", "before": 924402982, "cons": 135, "gen": "p_card-01-act-2_032"},
    {"pid": "AS-JQXN3NK5", "before": 1256600488, "cons": 136, "gen": "p_card-00-men-3_003"},
]
for g in games:
    n = g["cons"]
    st = stream(g["before"], n + 2)
    k = idx[g["gen"]]
    print("\n==", g["pid"], "cons", n, "gen agg_idx", k, "N", N)
    # scan range roll at any position j, any width m
    hits = []
    for j in range(n):
        v = st[j]
        for m in range(2, 201):
            if (v * m) >> 32 == k:
                hits.append((j, m))
    print("  range-roll hits (j,m):", hits[:20], "total", len(hits))
    # scan argmin/argmax signed over contiguous windows mapping to k
    sk = [signed(x) for x in st]
    am_hits = []
    for m in range(2, min(N, n) + 1):
        for j in range(0, n - m + 1):
            w = sk[j:j + m]
            if min(range(m), key=lambda i: w[i]) == k - j and 0 <= k - j < m:
                am_hits.append(("min", j, m))
            if max(range(m), key=lambda i: w[i]) == k - j and 0 <= k - j < m:
                am_hits.append(("max", j, m))
    print("  argmin/max window hits:", am_hits[:20], "total", len(am_hits))