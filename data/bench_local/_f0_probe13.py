"""F0 probe 13: derive npc from idol->audition difficulty->npc group; retest match rate."""
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
STEP = {16: "ProduceStepType_AuditionMid1", 17: "ProduceStepType_AuditionMid2", 18: "ProduceStepType_AuditionFinal"}
STAGE_NPC = {"hif.sel1": 5, "hif.sel2": 5, "hif.sel3": 5, "hif.main1": 2, "hif.main2": 2}


def npc_of(lo, meta):
    idol = idols.get(lo.get("idol_card_id"))
    produce = lo.get("produce_id")
    step_type = STEP.get(lo.get("step_type"))
    if not idol or not produce or not step_type:
        return None, "fallback"
    adid = idol.get("produceStepAuditionDifficultyId")
    row = aud_idx.get((adid, produce, step_type))
    if not row:
        return None, "no-row"
    gid = row.get("produceExamBattleNpcGroupId")
    n = npc_groups.get(gid)
    if not n:
        return None, "no-group"
    return n, gid


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
    turns = replay_initial_deck(seed, cards, k, initial_keys=keys, turn_start_distribute=tsd, hand_limit=5)
    return [c[0] for c in turns[0]] if turns else []


hit = 0
bad = []
npc_used = Counter()
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    stage = meta.get("stage")
    turns = int(meta.get("turns") or 0)
    cards, add_idx = parse_deck(lo["deck_cards"])
    n, src = npc_of(lo, meta)
    npc = n if n is not None else STAGE_NPC[stage]
    npc_used[(stage, n, src)] += 1
    for g in gl:
        actual = g["check"]["hand"]
        pred = hand_for(g["seed"], cards, max(0, turns - 3) + npc * turns, add_idx)
        if pred == actual:
            hit += 1
        else:
            bad.append((pid, g["index"], stage, npc, pred, actual, turns))

print(f"hit with idol-derived npc: {hit}/384")
print("npc used:", dict(npc_used))
print("bad:", len(bad), "by stage:", Counter(b[2] for b in bad))
for b in bad[:30]:
    print(f"\n{b[0]}[{b[1]}] {b[2]} npc={b[3]} turns={b[6]}")
    print("  pred  :", b[4])
    print("  actual:", b[5])
