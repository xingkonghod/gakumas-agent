"""sim-fid ③ crack v2: search discard(nf) + sort(nf), gen=argmin sort key over candidate set."""
import io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
tdir = ROOT / "data/GKMSMainWheel/GakumasCLI/ro/master/tables"
MASK = 0xFFFFFFFF


def xs(s):
    s ^= (s << 13) & MASK; s ^= s >> 17; s ^= (s << 5) & MASK
    return s & MASK


def stream(before, n):
    out = []; s = before
    for _ in range(n):
        out.append(s); s = xs(s)
    return out


def signed(u):
    return u - (1 << 32) if u >= (1 << 31) else u


rows = [json.loads(l) for l in (tdir / "ProduceCardPool.jsonl").open(encoding="utf-8") if l.strip()]
agg = {r["id"]: r for r in [r.get("decoded", r) for r in rows]}
pool = [r["id"] for r in agg["p_random_pool-all-upgrade_1"]["produceCardRatios"]]
N = len(pool)
plan00 = [i for i, c in enumerate(pool) if c.split("-")[1] == "00"]
plan01 = [i for i, c in enumerate(pool) if c.split("-")[1] == "01"]
print("plan00 idx:", plan00)
print("plan00+01 count:", len(plan00) + len(plan01))

recs = [json.loads(l) for l in (ROOT / "data/_simfid_type21_probe.jsonl").open(encoding="utf-8") if l.strip()]
for r in recs:
    if not r.get("is_target"):
        continue
    cons = r["cons"]; st = stream(r["rng_before"], cons + 2)
    gen = r["gen"][0]
    gi = pool.index(gen)
    nf = cons // 2
    print(f"\n== {r['tag']} cons={cons} nf={nf} gen_idx={gi}")
    # candidate sets to try
    candsets = {"first_nf": list(range(nf)), "plan00": plan00, "plan00+01": plan00 + plan01,
                "first_nf_plus1": list(range(nf + 1))}
    for cname, cands in candsets.items():
        k = len(cands)
        # sort keys at various offsets
        for off in (nf, 0, cons - k, 1):
            if off < 0 or off + k > len(st):
                continue
            keys = [signed(st[off + j]) for j in range(k)]
            am = min(range(k), key=lambda i: keys[i])
            if cands[am] == gi:
                print(f"  MATCH cand={cname}(k={k}) sort_off={off} argmin_pos={am} -> idx{gi}")