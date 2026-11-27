"""F0 probe 4: inspect remaining mismatches + stamina exceptions + absent cards."""
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

initial_bases = set()
master_cards = {}
for row_id, variant, payload in db.execute(
    "select row_id, variant, payload from records where table_name='ProduceCard'"
):
    card = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
    master_cards.setdefault((row_id, int(variant)), card)
    if card.get("isInitial"):
        initial_bases.add(row_id)

seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with open(DL / "saves.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        saves[d.get("id")] = d

NPC = {"hif.sel1": 5, "hif.sel2": 5, "hif.sel3": 5, "hif.main1": 2, "hif.main2": 2}


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


def hand_of(pid, g, npc_override=None):
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    stage = meta.get("stage")
    turns_conf = int(meta.get("turns") or 0)
    npc = npc_override or NPC[stage]
    k = max(0, turns_conf - 3) + npc * turns_conf
    cards, add_idx = parse_deck(lo["deck_cards"])
    keys = frozenset(c for i, c in enumerate(cards) if c[0] in initial_bases or i in add_idx)
    turns = replay_initial_deck(
        g["seed"], cards, k, initial_keys=keys,
        turn_start_distribute=3, hand_limit=5,
    )
    return (turns[0] if turns else []), [c[0] for c in (turns[0] if turns else [])], lo


# ---------------------------------------------------------------- 1) stamina exceptions
print("=" * 30, "stamina exceptions", "=" * 30)
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo = sv["loadout"]
    start = lo.get("starting_stamina")
    for g in gl:
        st = g["check"]["stamina"]
        if st != start:
            print(f"\n{pid}[{g['index']}] stamina {start} -> {st} (max {lo.get('max_stamina')})")
            print("  items:", lo.get("produce_item_ids"), " drinks:", lo.get("drink_ids"))
            print("  idol:", lo.get("idol_card_id"), " deck trouble:",
                  [e for e in lo["deck_cards"] if "acc" in e or "trouble" in e])
            print("  enable ids:", lo.get("lesson_start_enchant_ids"))

# ---------------------------------------------------------------- 2) mismatch detail
print("\n" + "=" * 30, "mismatches (base+add)", "=" * 30)
n_miss = 0
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo = sv["loadout"]
    deck_bases = [e.split("/")[0].split("+")[0] for e in lo["deck_cards"]]
    for g in gl:
        hand, ids, _ = hand_of(pid, g)
        actual = g["check"]["hand"]
        if ids == actual:
            continue
        n_miss += 1
        extra = [c for c in ids if c not in actual]
        missing = [c for c in actual if c not in ids]
        absent = [c for c in actual if c not in deck_bases]
        print(f"\n{pid}[{g['index']}] stage={sv['meta'].get('stage')} turns={sv['meta'].get('turns')}")
        print("  pred  :", ids)
        print("  actual:", actual)
        print("  extra:", extra, " missing:", missing, " absent-from-deck:", absent)
        for c in missing:
            base = c.rsplit("_", 1)
            variants = [(cid, v) for (cid, v) in master_cards if cid == c]
            info = [(cid, v, master_cards[(cid, v)].get("name"),
                     master_cards[(cid, v)].get("category"),
                     master_cards[(cid, v)].get("isInitial")) for cid, v in sorted(variants)]
            print("   master:", info)
print("\nmisses:", n_miss)
