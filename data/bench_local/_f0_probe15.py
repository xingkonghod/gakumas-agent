"""F0 probe 15: test initial_deck-merged-into-deck hypotheses on remaining 24."""
import gzip
import json
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
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
aud = load("ProduceStepAuditionDifficulty")
aud_idx = {(r["id"], r["produceId"], r["stepType"]): r for r in aud}
npc_groups = defaultdict(int)
for r in load("ProduceExamBattleNpcGroup"):
    npc_groups[r["id"]] += 1
exam_decks = {r["id"]: r["produceCardIds"] for r in load("ExamInitialDeck")}
produce_init = {(r["produceId"], r["examEffectType"]): r["examInitialDeckId"] for r in load("ProduceInitialDeck")}
STEP = {16: "ProduceStepType_AuditionMid1", 17: "ProduceStepType_AuditionMid2", 18: "ProduceStepType_AuditionFinal"}

seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d.get("id")] = d


def parse_deck(entries):
    cards, add_idx = [], set()
    for entry in entries:
        segs = entry.split("/")
        cid, _, up = segs[0].partition("+")
        idx = len(cards)
        cards.append((cid, int(up) if up else 0))
        if any("g_effect-initial_add" in s for s in segs[1:]):
            add_idx.add(idx)
    return cards, add_idx


def npc_of(lo):
    idol = idols.get(lo.get("idol_card_id"))
    if not idol:
        return None
    row = aud_idx.get((idol.get("produceStepAuditionDifficultyId"), lo.get("produce_id"),
                       STEP.get(lo.get("step_type"))))
    if not row:
        return None
    return npc_groups.get(row.get("produceExamBattleNpcGroupId"))


def init_cards_of(lo):
    idol = idols.get(lo.get("idol_card_id"))
    if not idol:
        return []
    deck_id = produce_init.get((lo.get("produce_id"), idol.get("examEffectType")))
    return list(exam_decks.get(deck_id) or [])


def hand(cards, add_idx, seed, k, extra=(), tsd=3, extra_as_initial=False, limit=5):
    deck = list(cards) + [(c, 0) for c in extra]
    keys = {c for i, c in enumerate(cards) if c[0] in initial_bases or i in add_idx}
    if extra_as_initial:
        keys |= set(deck[len(cards):])
    turns = replay_initial_deck(seed, deck, k, initial_keys=frozenset(keys),
                                turn_start_distribute=tsd, hand_limit=limit)
    return [c[0] for c in turns[0]] if turns else []


miss = ['AS-323ADZVK','AS-357NNR8Y','AS-4T4FSXKG','AS-663NKTY4','AS-8MY3XH4R','AS-9MGMSGS9',
        'AS-CA5H82FC','AS-CKDKGJCM','AS-CVD67TFP','AS-D92HSANA','AS-DSYYTFYE','AS-FD4JEXVS',
        'AS-FZCFEXMX','AS-JC5BMB7P','AS-K46XXQEY','AS-KT8BWRT4','AS-NWX7R6SF','AS-PTJ4N63R',
        'AS-QD27AEW4','AS-QV6QCSN9','AS-SAKA4RM8','AS-SGWGCZWQ','AS-X9GNYH3W','AS-YMESH3GA']

# quick sanity: current best model status
summary = Counter()
for pid in miss:
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    turns = int(meta.get("turns") or 0)
    npc = npc_of(lo) or 2
    k = max(0, turns - 3) + npc * turns
    cards, add_idx = parse_deck(lo["deck_cards"])
    extra = init_cards_of(lo)
    expected = seeds["problems"][pid][0]["check"]["hand"]
    base_pred = hand(cards, add_idx, seeds["problems"][pid][0]["seed"], k)
    v_append = hand(cards, add_idx, seeds["problems"][pid][0]["seed"], k, extra=extra)
    v_initial = hand(cards, add_idx, seeds["problems"][pid][0]["seed"], k, extra=extra, extra_as_initial=True)
    # variant: hand = initial batch + extra + draws (append extra to hand after initial)
    keys = frozenset(c for i, c in enumerate(cards) if c[0] in initial_bases or i in add_idx)
    from gkagent.sim.exam_shuffle import opening_deck_and_rng
    _rng, remaining = opening_deck_and_rng(seeds["problems"][pid][0]["seed"], cards, k)
    h, overflow = [], []
    for c in reversed(list(remaining)):
        if c not in keys:
            continue
        remaining.remove(c)
        (h if len(h) < 5 else overflow).append(c)
    remaining.extend(overflow)
    h = [c[0] for c in h] + list(extra)[: max(0, 3 - len(h))]
    while len(h) < 3 and remaining:
        h.append(remaining.pop(0)[0])
    v_handappend = h
    summary["total"] += 1
    for name, v in (("base", base_pred), ("append", v_append), ("initial", v_initial), ("handappend", v_handappend)):
        if v == expected:
            summary[name] += 1
    print(f"\n{pid} expected={expected}")
    print("  base      :", base_pred)
    print("  +initdeck :", v_append)
    print("  +initdeckeys:", v_initial)
    print("  handappend:", v_handappend)

print("\nsummary:", dict(summary))
