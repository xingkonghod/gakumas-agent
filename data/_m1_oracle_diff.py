"""M1 分析2（不提交）：oracle trace 逐动作牌区 diff + 消费归因。"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.stdout = open(ROOT / "data/_m1_oracle_diff.txt", "w", encoding="utf-8")

SHORT = lambda cid: cid.replace("p_card-", "").replace("01-", "").replace("00-", "").replace("03-", "")

def fmt(z):
    return [f"{SHORT(c)}::{u}" for c, u in z]

for w in ("W7", "W9"):
    d = json.loads((ROOT / f"data/_m1_rinami_oracle_{w}.json").read_text(encoding="utf-8"))
    op = json.loads((ROOT / f"data/_rinami_live/{w}/opening.json").read_text(encoding="utf-8"))
    ta = op["turnAttributes"]
    print(f"===== {w} turnAttributes={ta} =====")
    for r in d["rows"]:
        zb, za = r["zones_before"], r["zones_after"]
        diffs = []
        for zn in ("hand", "deck", "grave", "lost", "hold"):
            b = [tuple(c) for c in zb.get(zn, [])]
            a = [tuple(c) for c in za.get(zn, [])]
            if b != a:
                # multiset diff
                mb, ma = {}, {}
                for c in b: mb[c] = mb.get(c, 0) + 1
                for c in a: ma[c] = ma.get(c, 0) + 1
                removed = [c for c in mb if mb[c] > ma.get(c, 0) for _ in range(mb[c] - ma.get(c, 0))]
                added = [c for c in ma if ma[c] > mb.get(c, 0) for _ in range(ma[c] - mb.get(c, 0))]
                diffs.append(f"{zn}: -{fmt(removed)} +{fmt(added)}")
        tb, taa = r["turn_before"], r["turn_after"]
        attr = ta[taa - 1] if taa <= len(ta) else "?"
        print(f'k={r["k"]:>2} {str(r["action"]):<12} t{tb}->{taa}(attr{attr}) cons={r["consumption"]} '
              f'card={r["live_card"]}')
        for df in diffs:
            print(f"     {df}")
        if r["consumption"] and r["consumption"] > 0:
            print(f'     deck_after={fmt(za.get("deck", []))}')
