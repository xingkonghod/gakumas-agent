"""F0 probe 3: check correlations + deck/initial analysis."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DL = ROOT / "data/bench_local/gkbench_dl/hif"
MASTER = ROOT / "data/hiro/vendor/gakumas-player/data/master"
cur = json.loads((MASTER / "current.json").read_text(encoding="utf-8"))
db = sqlite3.connect(MASTER / cur["database"])

# master isInitial via records (compressed JSON payload)
import zlib
initial_variants = set()
all_variants = set()
for row_id, variant, payload in db.execute(
    "select row_id, variant, payload from records where table_name='ProduceCard'"
):
    card = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
    all_variants.add((row_id, int(variant)))
    if card.get("isInitial"):
        initial_variants.add((row_id, int(variant)))
print("isInitial variants:", sorted(initial_variants))
print("isInitial base ids:", sorted({i for i, _ in initial_variants}))
# for each isInitial base id, are all variants initial?
by_base = {}
for cid, v in all_variants:
    by_base.setdefault(cid, set()).add(v)
for cid, _ in sorted(initial_variants):
    print(" ", cid, "initial variants:", sorted(v for i, v in initial_variants if i == cid), "all:", sorted(by_base[cid]))

seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d.get("id")] = d
groups = [(pid, g) for pid, gl in seeds["problems"].items() for g in gl]

# stamina correlation
print("\n== check.stamina vs loadout ==")
rows = []
for pid, g in groups:
    lo = saves[pid]["loadout"]
    rows.append((g["check"]["stamina"], lo.get("starting_stamina"), lo.get("max_stamina"), pid))
print("first 15:", rows[:15])
print("stam==starting:", sum(1 for s, st, _, _ in rows if s == st), "/", len(rows))
print("stam==max:", sum(1 for s, _, mx, _ in rows if s == mx), "/", len(rows))
print("stam values:", Counter(s for s, _, _, _ in rows).most_common(15))
print("starting values:", Counter(st for _, st, _, _ in rows).most_common(15))
print("diff stam-starting:", Counter(s - (st or 0) for s, st, _, _ in rows).most_common(10))

# deck / hand analysis
def base_of(entry):
    return entry.split("/")[0].split("+")[0]

def is_initial_add(entry):
    return "g_effect-initial_add" in entry

absent = []
init_add_hits = []
for pid, g in groups:
    lo = saves[pid]["loadout"]
    deck = lo["deck_cards"]
    deck_bases = [base_of(e) for e in deck]
    hand = g["check"]["hand"]
    for c in hand:
        if c not in deck_bases:
            absent.append((pid, c, deck))
    if any(is_initial_add(e) for e in deck):
        init_add_hits.append(pid)
print("\nabsent hand cards:", len(absent))
for a in absent[:10]:
    print(a[0], a[1], "deck=", a[2])

print("\nproblems with initial_add:", len(init_add_hits))
# hand cards with +? already 0

# Which hand cards are master-isInitial (base-level)?
init_bases = {i for i, _ in initial_variants}
hit_initial = 0
hand_total = 0
for pid, g in groups:
    for c in g["check"]["hand"]:
        hand_total += 1
        if c in init_bases:
            hit_initial += 1
print(f"\ncheck.hand cards that are master-isInitial: {hit_initial}/{hand_total}")
# For each group: how many of hand cards are initial vs initial_add?
cnt = Counter()
for pid, g in groups:
    lo = saves[pid]["loadout"]
    n_ia = sum(1 for e in lo["deck_cards"] if is_initial_add(e))
    n_ini = sum(1 for c in g["check"]["hand"] if c in init_bases)
    cnt[(n_ini, n_ia)] += 1
print("(hand master-initial count, deck initial_add count) distribution:", cnt.most_common(20))
