"""F0 probe: inspect gkbench seeds/saves/master structures."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DL = ROOT / "data/bench_local/gkbench_dl/hif"
MASTER = ROOT / "data/hiro/vendor/gakumas-player/data/master"
cur = json.loads((MASTER / "current.json").read_text(encoding="utf-8"))
db = sqlite3.connect(MASTER / cur["database"])
tables = [n for (n,) in db.execute("select name from sqlite_master where type='table'")]
print("tables:", tables)
for t in tables:
    if "roduce" in t or "Card" in t:
        cols = [r[1] for r in db.execute(f"pragma table_info({t})")]
        n = db.execute(f"select count(*) from {t}").fetchone()[0]
        print(f"\n== {t} ({n}) cols={cols}")

seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
print("\nschema:", seeds.get("schema"), "set:", seeds.get("set"), "problems:", len(seeds["problems"]))
groups = [(pid, g) for pid, gl in seeds["problems"].items() for g in gl]
print("groups:", len(groups))
print("check keys:", Counter(tuple(sorted(g["check"])) for _, g in groups))
for field in ("turn", "score", "stamina", "rules"):
    print(field, Counter(g["check"].get(field) for _, g in groups).most_common(8))
print("label:", Counter(g.get("label") for _, g in groups))
print("split:", Counter(g.get("split") for _, g in groups))

saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d.get("id")] = d
print("\nsaves:", len(saves), "seeds problems in saves:", sum(1 for p, _ in [groups[0]] if p in saves))
missing = [pid for pid in seeds["problems"] if pid not in saves]
print("seeds problems missing from saves:", len(missing), missing[:5])

# every check hand card has + suffix?
has_plus = 0
for pid, g in groups:
    for c in g["check"].get("hand", []):
        if "+" in c:
            has_plus += 1
print("check.hand cards with '+':", has_plus)
# compare hand cards present in loadout deck
absent = 0
for pid, g in groups:
    sv = saves.get(pid)
    if not sv:
        continue
    deck = sv["loadout"]["deck_cards"]
    base = [d.split("+")[0] for d in deck]
    for c in g["check"].get("hand", []):
        if c not in base:
            absent += 1
print("check.hand cards not in deck (base id):", absent)

# sample mismatched format: check hand card vs deck at same position?
import random
pid, g = groups[0]
sv = saves[pid]
print("\nsample", pid, "turns", sv["meta"]["turns"], "stage", sv["meta"]["stage"])
print("deck:", sv["loadout"]["deck_cards"])
print("hand:", g["check"]["hand"])

# stage -> turns distribution
print("\nstage/turns:", Counter((saves[p]["meta"]["stage"], saves[p]["meta"]["turns"]) for p, _ in groups if p in saves))
print("source:", Counter(json.dumps(saves[p]["meta"].get("source")) for p, _ in groups if p in saves))
print("mechanic:", Counter(saves[p]["meta"].get("mechanic") for p, _ in groups if p in saves).most_common(30))
print("round:", Counter(saves[p]["loadout"].get("round") for p, _ in groups if p in saves))
print("step_id:", Counter(saves[p]["loadout"].get("step_id") for p, _ in groups if p in saves))

# any custom cards in decks?
custom = Counter()
for p, _ in groups:
    sv = saves.get(p)
    if not sv:
        continue
    for c in sv["loadout"]["deck_cards"]:
        if "custom" in c:
            custom[c] += 1
print("\ncustom deck cards:", custom)
