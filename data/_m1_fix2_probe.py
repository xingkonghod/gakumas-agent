"""m1-fix2 开发探针（不提交）：W9 idol 轨迹 + kampo 候选 + soda 强化锚点。"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

w = "W9"
d = json.loads((ROOT / f"data/_m1_rinami_oracle_{w}.json").read_text(encoding="utf-8"))
rows = d["rows"]
IDOL = ("p_card-01-ido-3_200", "p_card-01-ido-3_213")
print("k=10 zones_before deck+grave idol:")
zb = rows[10]["zones_before"]
for zn in ("deck", "grave", "hand"):
    print(f"  {zn}:", [(c[0].split('-')[-1], c[1]) for c in zb[zn] if c[0] in IDOL])
print("ido-3_200 trajectory:")
for k, r in enumerate(rows):
    for zn in ("hand", "deck", "grave", "lost"):
        for c in r["zones_after"].get(zn, []):
            if c[0] == "p_card-01-ido-3_200":
                print(f"  k={k} {zn} upg={c[1]}")
# soda turn-start steps (turn transitions) and 3_035/3_006 upg changes
print("turn transitions:")
for k, r in enumerate(rows):
    if r["turn_after"] > r["turn_before"]:
        print(f"  k={k} t{r['turn_before']}->{r['turn_after']} cons={r['consumption']}")