"""F0 probe 14: initial_deck mechanism — do loadout decks already include initial-deck cards?"""
import gzip
import json
import sqlite3
import sys
import zlib
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
DL = ROOT / "data/bench_local/gkbench_dl/hif"
RAW = ROOT / "data/hiro/vendor/gakumas-player/data/master/d31baf6608ee4553091f28446f628cd3ad66ff01/raw"
MASTER = ROOT / "data/hiro/vendor/gakumas-player/data/master"
cur = json.loads((MASTER / "current.json").read_text(encoding="utf-8"))
db = sqlite3.connect(MASTER / cur["database"])
initial_bases = set()
for row_id, variant, payload in db.execute(
    "select row_id, variant, payload from records where table_name='ProduceCard'"
):
    card = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
    if card.get("isInitial"):
        initial_bases.add(row_id)
db.close()


def load(n):
    return yaml.safe_load(gzip.decompress((RAW / f"{n}.yaml.gz").read_bytes())) or []


idols = {r["id"]: r for r in load("IdolCard")}
exam_decks = {r["id"]: r["produceCardIds"] for r in load("ExamInitialDeck")}
produce_init = {(r["produceId"], r["examEffectType"]): r["examInitialDeckId"] for r in load("ProduceInitialDeck")}

seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d.get("id")] = d


def base_card(entry):
    return entry.split("/")[0].split("+")[0]


rows = []
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    idol = idols.get(lo.get("idol_card_id"))
    if not idol:
        continue
    eet = idol.get("examEffectType")
    deck_id = produce_init.get((lo.get("produce_id"), eet))
    init_cards = exam_decks.get(deck_id, [])
    deck = lo["deck_cards"]
    deck_bases = [base_card(e) for e in deck]
    overlap = sum(1 for c in set(init_cards) if c in deck_bases)
    rows.append((pid, meta.get("stage"), lo.get("idol_card_id"), eet, deck_id, len(init_cards),
                 overlap, len(deck), meta.get("mechanic")))

print("groups:", len(rows))
c = Counter((r[1], r[7] > 0) for r in rows)
print("overlap>0 by stage:", c)
print("\noverlap distribution:", Counter(r[6] for r in rows))
print("\nby deck_id (stage):", Counter((r[1], r[4]) for r in rows))
print("\nexamples overlap=0:", [r for r in rows if r[6] == 0][:5])
print("\nexamples overlap>0:", [r for r in rows if r[6] > 0][:5])

# for the 24 remaining misses, get detail
miss_ids = ['AS-323ADZVK','AS-357NNR8Y','AS-4T4FSXKG','AS-663NKTY4','AS-8MY3XH4R','AS-9MGMSGS9',
            'AS-CA5H82FC','AS-CKDKGJCM','AS-CVD67TFP','AS-D92HSANA','AS-DSYYTFYE','AS-FD4JEXVS',
            'AS-FZCFEXMX','AS-JC5BMB7P','AS-K46XXQEY','AS-KT8BWRT4','AS-NWX7R6SF','AS-PTJ4N63R',
            'AS-QD27AEW4','AS-QV6QCSN9','AS-SAKA4RM8','AS-SGWGCZWQ','AS-X9GNYH3W','AS-YMESH3GA']
print("\n=== remaining misses: idol/mechanic/initdeck/overlap ===")
for pid in miss_ids:
    sv = saves.get(pid)
    if not sv:
        print(pid, "NO SAVE")
        continue
    lo, meta = sv["loadout"], sv["meta"]
    idol = idols.get(lo.get("idol_card_id"))
    eet = idol.get("examEffectType") if idol else None
    deck_id = produce_init.get((lo.get("produce_id"), eet))
    init_cards = exam_decks.get(deck_id, [])
    deck_bases = [base_card(e) for e in lo["deck_cards"]]
    overlap = [c for c in set(init_cards) if c in deck_bases]
    print(pid, meta.get("stage"), lo.get("idol_card_id"), "eet=", (eet or "").replace("ProduceExamEffectType_Exam", ""),
          "deck_id=", deck_id, "init=", len(init_cards), "overlap=", overlap,
          "hand=", [g["check"]["hand"] for g in seeds["problems"][pid]][:2])
