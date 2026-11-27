"""F0 probe 16: what causes check.stamina != loadout.starting_stamina (15 cases)."""
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/hiro/vendor/gakumas-player/data/master/d31baf6608ee4553091f28446f628cd3ad66ff01/raw"
DL = ROOT / "data/bench_local/gkbench_dl/hif"


def load(n):
    return yaml.safe_load(gzip.decompress((RAW / f"{n}.yaml.gz").read_bytes())) or []


seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d.get("id")] = d

exc, norm = [], []
for pid, gl in seeds["problems"].items():
    lo = saves[pid]["loadout"]
    start = lo.get("starting_stamina")
    for g in gl:
        row = (pid, g["check"]["stamina"], start, lo, saves[pid]["meta"])
        (norm if g["check"]["stamina"] == start else exc).append(row)

print("exceptions:", len(exc), "normal:", len(norm))
for pid, st, start, lo, meta in exc:
    print(f"{pid} {start}->{st} ({st - (start or 0):+d}) idol={lo.get('idol_card_id')} "
          f"stage={meta.get('stage')} items={lo.get('produce_item_ids')} drinks={lo.get('drink_ids')}")

# item counts in exceptions vs normal (per group)
def counts(rows):
    c = Counter()
    for pid, st, start, lo, meta in rows:
        for it in lo.get("produce_item_ids") or []:
            c[("item", it)] += 1
        for dr in lo.get("drink_ids") or []:
            c[("drink", dr)] += 1
        for en in lo.get("lesson_start_enchant_ids") or []:
            c[("enchant", en.split("-enc")[0])] += 1
        c[("idol", lo.get("idol_card_id"))] += 1
    return c

cexc, cnorm = counts(exc), counts(norm)
print("\nitems/drinks/enchants/idols in ALL 15 exceptions:")
for key, n in cexc.items():
    if n == len(exc):
        print("  ", key, "exc", n, "normal", cnorm.get(key, 0))

# look up item/drink names for exception-only common items
items = {r["id"]: r for r in load("ProduceItem")}
drinks = {r["id"]: r for r in load("ProduceDrink")}
effs = {r["id"]: r for r in load("ProduceItemEffect")}
print("\nexception-common item names:")
for key, n in cexc.items():
    if n == len(exc) and key[0] == "item":
        it = items.get(key[1], {})
        print(" ", key[1], it.get("name"), str(it.get("produceItemEffectId") or it.get("itemEffectId") or ""))
print("\nexception-common drink names:")
for key, n in cexc.items():
    if n == len(exc) and key[0] == "drink":
        dr = drinks.get(key[1], {})
        print(" ", key[1], dr.get("name"))
