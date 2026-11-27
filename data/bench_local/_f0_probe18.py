"""F0 probe 18: could remaining misses be check computed with ExamInitialDeck merged into deck?"""
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
from gkagent.sim.exam_shuffle import replay_initial_deck  # noqa: E402

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
aud = {(r["id"], r["produceId"], r["stepType"]): r for r in load("ProduceStepAuditionDifficulty")}
npc_rows = Counter(r["id"] for r in load("ProduceExamBattleNpcGroup"))
exam_decks = {r["id"]: r["produceCardIds"] for r in load("ExamInitialDeck")}
produce_init = {(r["produceId"], r["examEffectType"]): r["examInitialDeckId"] for r in load("ProduceInitialDeck")}
STEP = {16: "ProduceStepType_AuditionMid1", 17: "ProduceStepType_AuditionMid2", 18: "ProduceStepType_AuditionFinal"}
STEP_ID = {"AuditionMid1": "ProduceStepType_AuditionMid1", "AuditionMid2": "ProduceStepType_AuditionMid2",
           "AuditionFinal": "ProduceStepType_AuditionFinal"}

seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d["id"]] = d


def parse_deck(entries):
    cards, add = [], set()
    for e in entries:
        segs = e.split("/")
        cid, _, up = segs[0].partition("+")
        i = len(cards)
        cards.append((cid, int(up) if up else 0))
        if any("g_effect-initial_add" in s for s in segs[1:]):
            add.add(i)
    return cards, add


def init_cards(lo):
    idol = idols.get(lo.get("idol_card_id"))
    if not idol:
        return []
    deck_id = produce_init.get((lo.get("produce_id"), idol.get("examEffectType")))
    return list(exam_decks.get(deck_id) or [])


def npc_of(lo):
    idol = idols.get(lo.get("idol_card_id"))
    if not idol:
        return None
    step = STEP_ID.get(lo.get("step_id")) or STEP.get(lo.get("step_type"))
    row = aud.get((idol.get("produceStepAuditionDifficultyId"), lo.get("produce_id"), step))
    return npc_rows.get(row.get("produceExamBattleNpcGroupId")) if row else None


def model(seed, cards, add, npc, turns, mode, extra):
    if mode == "base":
        deck = list(cards)
    elif mode == "append":
        deck = list(cards) + [(c, 0) for c in extra]
    elif mode == "prepend":
        deck = [(c, 0) for c in extra] + list(cards)
    elif mode == "append_add":  # extra as initial_add
        deck = list(cards) + [(c, 0) for c in extra]
    keys = {c for i, c in enumerate(deck) if c[0] in initial_bases}
    if mode == "append_add":
        keys |= set(deck[len(cards):])
    hands = replay_initial_deck(seed, deck, max(0, turns - 3) + npc * turns,
                                initial_keys=frozenset(keys), turn_start_distribute=3, hand_limit=5)
    return [c[0] for c in hands[0]] if hands else []


results = Counter()
per_problem_hit = Counter()
for pid, rows in seeds["problems"].items():
    lo, meta = saves[pid]["loadout"], saves[pid]["meta"]
    turns = int(meta.get("turns") or 0)
    cards, add = parse_deck(lo["deck_cards"])
    npc = npc_of(lo) or 2
    extra = init_cards(lo)
    for g in rows:
        actual = g["check"]["hand"]
        for mode in ("base", "append", "prepend", "append_add"):
            pred = model(g["seed"], cards, add, npc, turns, mode, extra)
            if pred == actual:
                results[mode] += 1
print("match by mode:", dict(results), "of 384")

# detail on the 24 misses under base
print("\nbase-mode misses and whether alternate mode fixes:")
for pid, rows in seeds["problems"].items():
    lo, meta = saves[pid]["loadout"], saves[pid]["meta"]
    turns = int(meta.get("turns") or 0)
    cards, add = parse_deck(lo["deck_cards"])
    npc = npc_of(lo) or 2
    extra = init_cards(lo)
    for g in rows:
        actual = g["check"]["hand"]
        if model(g["seed"], cards, add, npc, turns, "base", extra) == actual:
            continue
        fixes = [m for m in ("append", "prepend", "append_add")
                 if model(g["seed"], cards, add, npc, turns, m, extra) == actual]
        print(pid, "fixes:", fixes, "idol", lo.get("idol_card_id"), "extra", len(extra))
