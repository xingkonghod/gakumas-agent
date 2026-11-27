"""F0 probe 9: what distinguishes npc=3 main groups from npc=2? feature cross-tab."""
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


label = {}
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    if not str(meta.get("stage", "")).startswith("hif.main"):
        continue
    turns = int(meta.get("turns") or 0)
    cards, add_idx = parse_deck(lo["deck_cards"])
    for g in gl:
        actual = g["check"]["hand"]
        m2 = hand_for(g["seed"], cards, max(0, turns - 3) + 2 * turns, add_idx) == actual
        m3 = hand_for(g["seed"], cards, max(0, turns - 3) + 3 * turns, add_idx) == actual
        label[(pid, g["index"])] = ("3" if m3 else "2" if m2 else "x")

rows = []
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    for g in gl:
        lab = label.get((pid, g["index"]))
        if lab is None:
            continue
        rows.append({
            "pid": pid, "lab": lab,
            "idol": lo.get("idol_card_id"),
            "mechanic": meta.get("mechanic"),
            "max_stam": lo.get("max_stamina"),
            "start_stam": lo.get("starting_stamina"),
            "n_lesson_enchant": len(lo.get("lesson_start_enchant_ids") or []),
            "n_research": len(lo.get("research_card_ids") or []),
            "has_memory": bool(lo.get("memory_ability_ids")),
            "audition_number": lo.get("audition_number"),
            "step_select_number": lo.get("step_select_number"),
            "n_items": len(lo.get("produce_item_ids") or []),
            "n_drinks": len(lo.get("drink_ids") or []),
            "n_lesson2": len(lo.get("lesson_start_enchant_ids") or []),
            "stage": meta.get("stage"),
            "params": tuple(lo.get("parameters") or []),
            "permil": tuple(lo.get("score_bonus_permils") or []),
            "n_deck": len(lo.get("deck_cards") or []),
            "n_support": len(lo.get("support_cards") or []),
            "enchant_custom": any("customize_pitem" in x for x in (lo.get("lesson_start_enchant_ids") or [])),
        })

keys = ["lab", "idol", "mechanic", "max_stam", "start_stam", "n_lesson_enchant", "n_research",
        "has_memory", "audition_number", "step_select_number", "n_items", "n_drinks",
        "stage", "n_deck", "n_support", "enchant_custom"]
for k in keys:
    vals = defaultdict(Counter)
    for r in rows:
        vals[r["lab"]][r[k]] += 1
    print(f"\n{k}:")
    for lab in ("2", "3", "x"):
        if lab in vals:
            print(f"  lab={lab}: {dict(vals[lab].most_common(12))}")

print("\nrows:", Counter(r["lab"] for r in rows))
