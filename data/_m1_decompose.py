"""M1 分析3（不提交）：分解关键动作的 rng 调用序列。"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
MASK = 0xFFFFFFFF

def xs(s):
    s ^= (s << 13) & MASK
    s ^= s >> 17
    s ^= (s << 5) & MASK
    return s & MASK

for w, ks in (("W7", (8, 19, 24, 14, 11)), ("W9", (17, 23, 30, 37, 40, 8, 10))):
    d = json.loads((ROOT / f"data/_m1_rinami_oracle_{w}.json").read_text(encoding="utf-8"))
    for k in ks:
        r = d["rows"][k]
        s = r["rng_before"]
        n = r["consumption"]
        card = r["live_card"]
        print(f"--- {w} k={k} cons={n} rng_before={s} card={card}")
        for j in range(n):
            key = s ^ 0x80000000
            vals = {ww: ((s * ww) >> 32) for ww in (2, 3, 4, 5, 6, 9, 12, 1000)}
            print(f"  j={j:>2} state={s:>10} key={key:>10} "
                  f"r2={vals[2]} r3={vals[3]} r4={vals[4]} r5={vals[5]} r9={vals[9]} r12={vals[12]} r1000={vals[1000]}")
            s = xs(s)
        print("  final", s, "== rng_after", r["rng_after"], s == r["rng_after"])
