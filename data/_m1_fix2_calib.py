"""m1-fix2 校准（不提交）：迭代推导 W9 pitem 312 抽牌步（unknown 锚点）。"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import importlib.util
spec = importlib.util.spec_from_file_location("replay_dev", ROOT / "data/_m1_replay_dev.py")
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)


def run(w, pitem, drink_upg):
    rd.PITEM_DRAW[w] = set(pitem)
    rd.DRINK_UPG[w] = drink_upg
    op = json.loads((ROOT / f"data/_rinami_live/{w}/opening.json").read_text(encoding="utf-8"))
    oracle = json.loads((ROOT / f"data/_m1_rinami_oracle_{w}.json").read_text(encoding="utf-8"))
    rp = rd.Replay(w, op, oracle, op["turnAttributes"])
    first_mism = None
    for k in range(len(rp.rows)):
        rp.run_action(k)
        r = rp.rows[k]
        za = {zn: sorted(tuple(c) for c in r["zones_after"].get(zn, [])) for zn in ("hand", "deck", "grave", "lost")}
        zp = {"hand": sorted(rp.hand), "deck": sorted(rp.deck), "grave": sorted(rp.grave), "lost": sorted(rp.lost)}
        ok_rng = rp.stream.state == r["rng_after"]
        if za != zp or not ok_rng:
            first_mism = (k, za != zp, ok_rng, r["consumption"], rp.graph.total)
            break
    return first_mism, len(rp.rows)


w = "W9"
pitem = {11, 21, 28, 34}
drink_upg = {7: {"p_card-01-men-3_035": 1}}
for it in range(20):
    fm, n = run(w, pitem, drink_upg)
    if fm is None:
        print(f"W9 FULL MATCH pitem={sorted(pitem)} drink_upg={drink_upg}")
        break
    k, zone_bad, rng_ok, cons_o, cons_p = fm
    print(f"iter{it} first_mism k={k} zone_bad={zone_bad} rng_ok={rng_ok} cons_o={cons_o} cons_p={cons_p} pitem={sorted(pitem)}")
    # if zone bad at a play step with cons 0 and rng ok -> likely missing pitem draw
    op = json.loads((ROOT / f"data/_rinami_live/{w}/opening.json").read_text(encoding="utf-8"))
    oracle = json.loads((ROOT / f"data/_m1_rinami_oracle_{w}.json").read_text(encoding="utf-8"))
    r = oracle["rows"][k]
    if zone_bad and rng_ok and r["action"][0] == "play" and cons_o == 0 and k not in pitem:
        pitem.add(k)
        continue
    print("  cannot auto-calibrate (rng diverged or non-play); stop")
    break