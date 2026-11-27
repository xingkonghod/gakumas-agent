"""F0 probe 11: idol card -> audition difficulty -> npc group -> npc count."""
import gzip
import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/hiro/vendor/gakumas-player/data/master/d31baf6608ee4553091f28446f628cd3ad66ff01/raw"


def load(n):
    return yaml.safe_load(gzip.decompress((RAW / f"{n}.yaml.gz").read_bytes()))


idols = load("IdolCard")
print("IdolCard rows:", len(idols))
print("keys:", list(idols[0].keys()))
for r in idols:
    if r["id"] in ("i_card-jsna-3-017", "i_card-shro-3-007", "i_card-jsna-3-015", "i_card-atbm-3-015"):
        print(json.dumps(r, ensure_ascii=False)[:1200])

# extra tables
for name in ("IdolCardSimulation", "ProduceStepAuditionCharacter", "ProduceExamBattleNpcGroup"):
    data = load(name)
    print(f"\n{name}: rows={len(data)}")
    print("keys:", list(data[0].keys()) if data else None)
    print(json.dumps(data[:2], ensure_ascii=False)[:1500])
