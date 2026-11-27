"""sim-fid ③ crack: cons=2nf search (nf range discards + nf signed_key sorts), gen=argmin."""
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
pool = [(r["id"], r.get("upgradeCount"), r.get("ratio")) for r in agg["p_random_pool-all-upgrade_1"]["produceCardRatios"]]
N = len(pool)
ids = [c for c, u, r in pool]
print("pool N", N)
from collections import Counter
print("by plan:", dict(sorted(Counter(c.split('-')[1] for c in ids).items())))

recs = [json.loads(l) for l in (ROOT / "data/_simfid_type21_probe.jsonl").open(encoding="utf-8") if l.strip()]
for r in recs:
    if not r.get("is_target"):
        continue
    cons = r["cons"]; st = stream(r["rng_before"], cons + 2)
    gen = r["gen"][0] if r["gen"] else None
    print(f"\n== {r['tag']} cons={cons} gen={gen} pool_idx={ids.index(gen) if gen in ids else None}")
    # hypothesis: nf = cons//2 range rolls (index into N) then nf signed_keys, gen=argmin
    for nf in (cons // 2,):
        if 2 * nf != cons:
            print("  cons odd, skip 2nf"); continue
        cand_idx = [(st[j] * N) >> 32 for j in range(nf)]
        keys = [signed(st[nf + j]) for j in range(nf)]
        order = sorted(range(nf), key=lambda i: keys[i])
        pick = cand_idx[order[0]]
        print(f"  2nf nf={nf}: cand_idx={cand_idx}")
        print(f"    argmin pick idx={pick} card={ids[pick]} match={ids[pick] == gen}")
        # also try argmax
        pickmax = cand_idx[order[-1]]
        print(f"    argmax pick idx={pickmax} card={ids[pickmax]} match={ids[pickmax] == gen}")
    # alternative: nf signed_keys FIRST then nf range? or range over filtered subset
    # try: first nf steps signed_key over pool directly (nf candidates = first nf pool entries)
    nf = cons // 2
    keys2 = [signed(st[j]) for j in range(nf)]
    am = min(range(nf), key=lambda i: keys2[i])
    print(f"  first-nf-signed argmin idx={am} card={ids[am] if am < N else '?'} match={ids[am] == gen if am < N else False}")