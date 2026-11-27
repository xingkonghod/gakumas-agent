"""F0 probe 17: idol card start-stamina deltas — look up card item/effect."""
import gzip
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/hiro/vendor/gakumas-player/data/master/d31baf6608ee4553091f28446f628cd3ad66ff01/raw"


def load(n):
    p = RAW / f"{n}.yaml.gz"
    return yaml.safe_load(gzip.decompress(p.read_bytes())) or [] if p.is_file() else []


idols = {r["id"]: r for r in load("IdolCard")}
items = {r["id"]: r for r in load("ProduceItem")}
ieffs = {r["id"]: r for r in load("ProduceItemEffect")}
drinks = {r["id"]: r for r in load("ProduceDrink")}
deffs = {r["id"]: r for r in load("ProduceDrinkEffect")}

print("idols:", len(idols), "items:", len(items), "item effects:", len(ieffs))
for iid in ("i_card-shro-3-016", "i_card-atbm-3-015", "i_card-ssmk-3-002", "i_card-kcna-3-019",
            "i_card-kllj-3-005", "i_card-shro-3-007"):
    r = idols[iid]
    print(f"\n{iid} {r.get('name')} plan={r.get('planType')} examEffect={r.get('examEffectType')} "
          f"produceStamina={r.get('produceStamina')}")
    print("  beforeItem:", r.get("beforeProduceItemId"), "afterItem:", r.get("afterProduceItemId"))
    for pid in (r.get("beforeProduceItemId"), r.get("afterProduceItemId")):
        if pid and pid in items:
            it = items[pid]
            print("   item", pid, "keys:", list(it.keys()))
            print("    name:", it.get("name"), "effectIds:", it.get("produceItemEffectIds") or it.get("produceItemEffectId"))
            for eid in (it.get("produceItemEffectIds") or [it.get("produceItemEffectId")]):
                e = ieffs.get(eid)
                if e:
                    print("     effect", eid, json.dumps(e, ensure_ascii=False)[:600])
print("\nProduceItemEffect keys:", list(next(iter(ieffs.values())).keys()) if ieffs else None)
print("ProduceDrinkEffect keys:", list(next(iter(deffs.values())).keys()) if deffs else None)
