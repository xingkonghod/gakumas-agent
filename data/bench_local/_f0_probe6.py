"""F0 probe 6: npc count per (produce, stage, round...) — cross tab exact-match npc."""
import json
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from gkagent.sim.exam_shuffle import replay_initial_deck  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
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


def hand_for(seed, cards, k, add_idx, tsd=3, scan="bottom", limit=5):
    keys = frozenset(c for i, c in enumerate(cards) if c[0] in initial_bases or i in add_idx)
    if scan == "bottom":
        turns = replay_initial_deck(seed, cards, k, initial_keys=keys,
                                    turn_start_distribute=tsd, hand_limit=limit)
        return [c[0] for c in turns[0]] if turns else []
    from gkagent.sim.exam_shuffle import opening_deck_and_rng
    _rng, remaining = opening_deck_and_rng(seed, cards, k)
    hand, overflow = [], []
    for c in list(remaining):
        if c not in keys:
            continue
        remaining.remove(c)
        (hand if len(hand) < limit else overflow).append(c)
    remaining.extend(overflow)
    for _ in range(max(0, tsd - len(hand))):
        if not remaining:
            break
        hand.append(remaining.pop(0))
    return [c[0] for c in hand]


# for each group find matching npc values (scan bottom, tsd=3)
combo = defaultdict(lambda: Counter())
records = []
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    stage = meta.get("stage")
    turns = int(meta.get("turns") or 0)
    cards, add_idx = parse_deck(lo["deck_cards"])
    for g in gl:
        actual = g["check"]["hand"]
        n_matches = []
        for npc in range(0, 7):
            k = max(0, turns - 3) + npc * turns
            if hand_for(g["seed"], cards, k, add_idx) == actual:
                n_matches.append(npc)
        key = (
            lo.get("produce_id"), stage, lo.get("round"), lo.get("step_id"),
            lo.get("audition_number"), lo.get("step_number"), lo.get("step_select_number"),
        )
        combo[key][tuple(n_matches)] += 1
        records.append({"pid": pid, "index": g["index"], "key": key, "n": tuple(n_matches),
                        "stage": stage, "turns": turns})

print("produce/share:", Counter(r["key"][0] for r in records))
print("stage by produce:", Counter((r["key"][0], r["stage"]) for r in records))
print("\n(npc matches tuple) overall:", Counter(r["n"] for r in records))
print("\ncombo -> npc match tuples:")
for key in sorted(combo, key=str):
    print(" ", key, dict(combo[key]))
