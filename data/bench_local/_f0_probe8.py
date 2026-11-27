"""F0 probe 8: commit/rules per group; correlate npc=3 with commit and upload date."""
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


def hand_for(seed, cards, k, add_idx):
    keys = frozenset(c for i, c in enumerate(cards) if c[0] in initial_bases or i in add_idx)
    turns = replay_initial_deck(seed, cards, k, initial_keys=keys, turn_start_distribute=3, hand_limit=5)
    return [c[0] for c in turns[0]] if turns else []


by_commit = defaultdict(Counter)
rows = []
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    stage = meta.get("stage")
    turns = int(meta.get("turns") or 0)
    cards, add_idx = parse_deck(lo["deck_cards"])
    cat = (meta.get("source") or {}).get("kind")
    for g in gl:
        actual = g["check"]["hand"]
        matches = []
        for npc in range(0, 7):
            k = max(0, turns - 3) + npc * turns
            if hand_for(g["seed"], cards, k, add_idx) == actual:
                matches.append(npc)
        commit = g["check"].get("commit")
        rules = g["check"].get("rules")
        by_commit[(commit, rules)][tuple(matches)] += 1
        rows.append((pid, g["index"], stage, commit, rules, tuple(matches),
                     lo.get("idol_card_id"), meta.get("tags")))

print("commit/rules distribution:")
for k, v in by_commit.items():
    print(" ", k, dict(v))

# npc=3 groups: commit distribution
m3 = [r for r in rows if 3 in r[5] and r[2].startswith("hif.main")]
print("\nnpc=3 groups commit:", Counter(r[3] for r in m3))
print("npc=2-only groups commit:", Counter(r[3] for r in rows if r[2].startswith("hif.main") and r[5] == (2,)))

# check whether npc=3 groups correlate with upload date in tags
def date_of(tags):
    for t in tags or []:
        if t.startswith("name:yz-"):
            return t.split("yz-")[1][:8]
    return None

print("\nnpc=3 by date:", Counter(date_of(r[7]) for r in m3))
print("npc=2 by date:", Counter(date_of(r[7]) for r in rows if r[2].startswith("hif.main") and r[5] == (2,)))
