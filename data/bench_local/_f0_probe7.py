"""F0 probe 7: per-problem npc match consistency + npc=3 correlation with features."""
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
master_cards = {}
for row_id, variant, payload in db.execute(
    "select row_id, variant, payload from records where table_name='ProduceCard'"
):
    card = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
    master_cards.setdefault(row_id, card)
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


def hand_for(seed, cards, k, add_idx, tsd=3):
    keys = frozenset(c for i, c in enumerate(cards) if c[0] in initial_bases or i in add_idx)
    turns = replay_initial_deck(seed, cards, k, initial_keys=keys,
                                turn_start_distribute=tsd, hand_limit=5)
    return [c[0] for c in turns[0]] if turns else []


per_pid = defaultdict(list)
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    stage = meta.get("stage")
    turns = int(meta.get("turns") or 0)
    cards, add_idx = parse_deck(lo["deck_cards"])
    for g in gl:
        actual = g["check"]["hand"]
        matches = []
        for npc in range(0, 7):
            k = max(0, turns - 3) + npc * turns
            if hand_for(g["seed"], cards, k, add_idx) == actual:
                matches.append(npc)
        per_pid[pid].append((g["index"], tuple(matches), actual))

diff_pid = [pid for pid, v in per_pid.items() if len({m for _, m, _ in v}) > 1]
print("pids with >1 seed and different npc match:", len(diff_pid), diff_pid[:10])
print("pids with >1 seed:", sum(1 for v in per_pid.values() if len(v) > 1))

# per-problem: decide npc from any seed; then check all seeds consistent
pid_npc = {}
for pid, v in per_pid.items():
    sets = [set(m) for _, m, _ in v]
    common = set.intersection(*sets) if sets else set()
    pid_npc[pid] = sorted(common)
print("\npid common npc dist:", Counter(tuple(v) for v in pid_npc.values()))

# correlate npc=3 (main) with features
print("\n=== main groups requiring npc=3 ===")
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    if not str(meta.get("stage", "")).startswith("hif.main"):
        continue
    turns = int(meta.get("turns") or 0)
    cards, add_idx = parse_deck(lo["deck_cards"])
    for g in gl:
        actual = g["check"]["hand"]
        m3 = hand_for(g["seed"], cards, max(0, turns - 3) + 3 * turns, add_idx) == actual
        if not m3:
            continue
        print(pid, "idx", g["index"], "stage", meta["stage"], "turns", turns, "idol", lo.get("idol_card_id"),
              "tags", meta.get("tags"), "step_select", lo.get("step_select_number"),
              "nitems", len(lo.get("produce_item_ids") or []), "ndrinks", len(lo.get("drink_ids") or []),
              "deck", len(cards), "params", lo.get("parameters"))
