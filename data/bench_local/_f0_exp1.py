"""F0 experiment: compare our shuffle model against official check.hand.

Try variants:
  A. no initial set (baseline from F0 precheck?)
  B. master isInitial by exact variant
  C. master isInitial by base id (all variants) + initial_add deck entries
Compare hand base-id sequences.
"""
import json
import sqlite3
import sys
import zlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from gkagent.sim.exam_shuffle import replay_initial_deck  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
MASTER = ROOT / "data/hiro/vendor/gakumas-player/data/master"
cur = json.loads((MASTER / "current.json").read_text(encoding="utf-8"))
db = sqlite3.connect(MASTER / cur["database"])

initial_exact = set()
initial_bases = set()
for row_id, variant, payload in db.execute(
    "select row_id, variant, payload from records where table_name='ProduceCard'"
):
    card = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
    if card.get("isInitial"):
        initial_exact.add((row_id, int(variant)))
        initial_bases.add(row_id)
db.close()
print("master isInitial: bases", len(initial_bases), "variants", len(initial_exact))

seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d.get("id")] = d

NPC = {"hif.sel1": 5, "hif.sel2": 5, "hif.sel3": 5, "hif.main1": 2, "hif.main2": 2}
TURN_START_DISTRIBUTE = 3
HAND_LIMIT = 5


def parse_deck(entries):
    """-> list[(cid, upgrade)], set of card indexes that are initial_add."""
    cards = []
    add_idx = set()
    for entry in entries:
        segs = entry.split("/")
        base = segs[0]
        cid, _, up = base.partition("+")
        up = int(up) if up else 0
        idx = len(cards)
        cards.append((cid, up))
        if any("g_effect-initial_add" in s for s in segs[1:]):
            add_idx.add(idx)
    return cards, add_idx


def predict(seed, cards, k, initial_variant, initial_add_idx, mode):
    if mode == "none":
        keys = frozenset()
    elif mode == "exact":
        keys = frozenset(c for c in cards if c in initial_exact)
    elif mode == "base+add":
        keys = frozenset(
            c for i, c in enumerate(cards) if c[0] in initial_bases or i in initial_add_idx
        )
    elif mode == "add_only":
        keys = frozenset(c for i, c in enumerate(cards) if i in initial_add_idx)
    else:
        raise ValueError(mode)
    turns = replay_initial_deck(
        seed, cards, k, initial_keys=keys,
        turn_start_distribute=TURN_START_DISTRIBUTE, hand_limit=HAND_LIMIT,
    )
    hand = turns[0] if turns else []
    return [c[0] for c in hand]


results = {}
for mode in ("none", "exact", "add_only", "base+add"):
    hit = 0
    miss = Counter()
    order_only = 0
    rows = []
    for pid, gl in seeds["problems"].items():
        sv = saves.get(pid)
        if not sv:
            miss["no-save"] += 1
            continue
        lo = sv["loadout"]
        meta = sv["meta"]
        stage = meta.get("stage")
        turns_conf = int(meta.get("turns") or 0)
        npc = NPC.get(stage)
        if npc is None or not turns_conf:
            miss[f"no-meta:{stage}"] += 1
            continue
        k = max(0, turns_conf - 3) + npc * turns_conf
        cards, add_idx = parse_deck(lo["deck_cards"])
        for g in gl:
            actual = g["check"]["hand"]
            pred = predict(g["seed"], cards, k, None, add_idx, mode)
            ok = pred == actual
            if ok:
                hit += 1
            else:
                if sorted(pred) == sorted(actual):
                    order_only += 1
                # classify
                if set(pred) == set(actual):
                    miss["order"] += 1
                elif len(pred) != len(actual):
                    miss["length"] += 1
                elif actual and actual[0] not in pred:
                    miss["missing-actual-first"] += 1
                else:
                    miss["set-diff"] += 1
            rows.append((pid, g["index"], pred, actual, ok))
    results[mode] = (hit, order_only, miss, rows)
    print(f"\nmode={mode}: hit {hit}/384  order-only {order_only}  miss={dict(miss)}")

# show first 10 misses of base+add
hit, order_only, miss, rows = results["base+add"]
print("\n=== base+add first 12 misses ===")
n = 0
for pid, idx, pred, actual, ok in rows:
    if ok:
        continue
    print(f"\n{pid}[{idx}]")
    print("  pred  :", pred)
    print("  actual:", actual)
    n += 1
    if n >= 12:
        break
