"""sim-fidelity type21 formula fit vs existing m1b 3-game data (no engine run)."""
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


# aggregated pool (ProduceCardPool.jsonl)
rows = [json.loads(l) for l in (tdir / "ProduceCardPool.jsonl").open(encoding="utf-8") if l.strip()]
dec = [r.get("decoded", r) for r in rows]
agg = {r["id"]: r for r in dec}
poolrow = agg["p_random_pool-all-upgrade_1"]
ratios = poolrow["produceCardRatios"]
pool = [(r["id"], r.get("upgradeCount"), r.get("ratio")) for r in ratios]
print("agg pool n:", len(pool))
idx = {c: i for i, (c, u, r) in enumerate(pool)}
# flat pool (ProduceCardRandomPool.jsonl) order
rows2 = [json.loads(l) for l in (tdir / "ProduceCardRandomPool.jsonl").open(encoding="utf-8") if l.strip()]
dec2 = [r.get("decoded", r) for r in rows2]
flat = [(r["produceCardId"], r.get("upgradeCount"), r.get("ratio")) for r in dec2 if r.get("id") == "p_random_pool-all-upgrade_1"]
idx2 = {c: i for i, (c, u, r) in enumerate(flat)}
print("flat pool n:", len(flat))
print("act-2_061 agg idx:", idx.get("p_card-01-act-2_061"), "flat idx:", idx2.get("p_card-01-act-2_061"))
print("agg==flat order:", [c for c, _, _ in pool] == [c for c, _, _ in flat])

games = [
    {"pid": "AS-4BFABQK9", "before": 1204118744, "cons": 132, "gen": "p_card-01-act-2_061", "deck_len": 3},
    {"pid": "AS-3TJXEB7T", "before": 924402982, "cons": 135, "gen": "p_card-01-act-2_032", "deck_len": 7},
    {"pid": "AS-JQXN3NK5", "before": 1256600488, "cons": 136, "gen": "p_card-00-men-3_003", "deck_len": 12},
]
for g in games:
    n = g["cons"]
    st = stream(g["before"], n + 4)
    gen = g["gen"]
    print("\n==", g["pid"], "cons", n, "gen", gen, "agg_idx", idx.get(gen), "flat_idx", idx2.get(gen))
    # H_single: first draw scaled to pool size
    for name, order, ii in (("agg", pool, idx), ("flat", flat, idx2)):
        N = len(order)
        k = ii.get(gen)
        if k is None:
            print(f"  {name}: gen NOT in pool")
            continue
        v0 = (st[0] * N) >> 32
        print(f"  {name} single-roll idx={v0} want={k} match={v0 == k}")
        # H_argmin over first m draws (signed), m in candidates
        for m in (n - 2, n - 1, n, n + 1, N):
            if m > len(st):
                continue
            keys = [signed(x) for x in st[:m]]
            am = min(range(m), key=lambda i: keys[i])
            if am == k:
                print(f"  {name} argmin signed m={m} -> {am} MATCH")
            amx = max(range(m), key=lambda i: keys[i])
            if amx == k:
                print(f"  {name} argmax signed m={m} -> {amx} MATCH")
        # H_last: last draw scaled
        vl = (st[n - 1] * N) >> 32
        if vl == k:
            print(f"  {name} last-roll idx={vl} MATCH")
        # H_unsigned argmin
        for m in (n - 1, n, N):
            if m > len(st):
                continue
            am = min(range(m), key=lambda i: st[i])
            if am == k:
                print(f"  {name} argmin unsigned m={m} -> {am} MATCH")