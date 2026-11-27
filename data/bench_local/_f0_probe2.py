"""F0 probe 2: master cards schema + check correlations."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DL = ROOT / "data/bench_local/gkbench_dl/hif"
MASTER = ROOT / "data/hiro/vendor/gakumas-player/data/master"
cur = json.loads((MASTER / "current.json").read_text(encoding="utf-8"))
db = sqlite3.connect(MASTER / cur["database"])

print("== metadata ==")
for row in db.execute("select * from metadata"):
    print(str(row)[:400])

print("\n== cards schema ==")
for r in db.execute("pragma table_info(cards)"):
    print(r)

print("\n== cards sample ==")
cols = [r[1] for r in db.execute("pragma table_info(cards)")]
print("cols:", cols)
n = db.execute("select count(*) from cards").fetchone()[0]
print("count:", n)
for row in db.execute("select * from cards limit 3"):
    print(str(row)[:600])

# look at a known card
for cid in ("p_card-02-men-3_040", "p_card-02-men-0_034", "p_card-02-men-2_004"):
    print("\n--", cid)
    for row in db.execute("select * from cards where id=?", (cid,)):
        print(str(row)[:1000])

print("\n== records sample (types?) ==")
for r in db.execute("pragma table_info(records)"):
    print(r)
from collections import Counter as C
c = C(x[0] for x in db.execute("select type from records"))
print("record types:", c.most_common(30))

seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d.get("id")] = d
groups = [(pid, g) for pid, gl in seeds["problems"].items() for g in gl]

# correlation check.stamina vs loadout starting/max stamina
print("\n== stamina correlation ==")
for pid, g in groups[:10]:
    lo = saves[pid]["loadout"]
    print(pid, "check.stam", g["check"]["stamina"], "starting", lo.get("starting_stamina"), "max", lo.get("max_stamina"))
print("diffs:", C(g["check"]["stamina"] - (saves[p]["loadout"].get("starting_stamina") or 0) for p, g in groups).most_common(10))
print("check.stam range:", min(g["check"]["stamina"] for _, g in groups), max(g["check"]["stamina"] for _, g in groups))
print("starting range:", min(saves[p]["loadout"].get("starting_stamina") or 0 for p, _ in groups), max(saves[p]["loadout"].get("starting_stamina") or 0 for p, _ in groups))

# hand length distribution
print("hand len:", C(len(g["check"]["hand"]) for _, g in groups))
