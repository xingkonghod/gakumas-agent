"""F0 probe 12: idol -> audition difficulty -> npc group count; initial deck mapping."""
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/hiro/vendor/gakumas-player/data/master/d31baf6608ee4553091f28446f628cd3ad66ff01/raw"


def load(n):
    p = RAW / f"{n}.yaml.gz"
    if not p.is_file():
        return []
    data = yaml.safe_load(gzip.decompress(p.read_bytes()))
    return data or []


idols = {r["id"]: r for r in load("IdolCard")}
print("IdolCard:", len(idols))

aud = load("ProduceStepAuditionDifficulty")
print("AuditionDifficulty:", len(aud), "keys:", list(aud[0].keys()))
# index by (id, produceId, stepType)
aud_idx = {}
for r in aud:
    aud_idx[(r["id"], r["produceId"], r["stepType"])] = r
hif_aud = [r for r in aud if r.get("produceId") in ("produce-007", "produce-008")]
print("HIF audition difficulty rows:", len(hif_aud))
print("HIF ids:", Counter(r["id"] for r in hif_aud).most_common(40))

npcs = load("ProduceExamBattleNpcGroup")
print("\nNpcGroup:", len(npcs), "keys:", list(npcs[0].keys()) if npcs else None)
if npcs:
    print(json.dumps(npcs[0], ensure_ascii=False)[:800])
    npc_by_id = defaultdict(list)
    for r in npcs:
        npc_by_id[r["id"]].append(r)
    print("npc group ids sample:", list(npc_by_id)[:5])
    for gid in ("p_npc_group-jsna-produce_008-01", "p_npc_group-shro-produce_008-01",
                "p_npc_group-jsna-produce_008-02", "p_npc_group-shro-produce_008-02",
                "p_npc_group-shro-produce_007-01"):
        rows = npc_by_id.get(gid)
        print(gid, "->", len(rows) if rows else None, json.dumps(rows[:3] if rows else None, ensure_ascii=False)[:500])

init_decks = load("ExamInitialDeck")
print("\nExamInitialDeck:", len(init_decks))
for r in init_decks:
    print(" ", r["id"], r.get("produceCardIds"))

# idol -> examInitialDeckId
print("\nIdol examInitialDeckId:", Counter(r.get("examInitialDeckId") for r in idols.values()))
