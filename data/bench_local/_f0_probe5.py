"""F0 probe 5: characterize the 46 remaining mismatches: features + parameter search."""
import json
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from gkagent.sim.exam_shuffle import opening_deck_and_rng, replay_initial_deck  # noqa: E402

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

NPC = {"hif.sel1": 5, "hif.sel2": 5, "hif.sel3": 5, "hif.main1": 2, "hif.main2": 2}


def parse_deck(entries):
    cards, add_idx, custom_n = [], set(), 0
    for entry in entries:
        segs = entry.split("/")
        cid, _, up = segs[0].partition("+")
        idx = len(cards)
        cards.append((cid, int(up) if up else 0))
        if len(segs) > 1:
            custom_n += 1
        if any("g_effect-initial_add" in s for s in segs[1:]):
            add_idx.add(idx)
    return cards, add_idx, custom_n


def base(hand):
    return [c[0] for c in hand]


def pred_hand(seed, cards, k, initial_mode="base+add", add_idx=frozenset(), tsd=3, limit=5, scan="bottom"):
    if initial_mode == "none":
        keys = frozenset()
    else:
        keys = frozenset(c for i, c in enumerate(cards) if c[0] in initial_bases or i in add_idx)
    if scan == "bottom":
        turns = replay_initial_deck(seed, cards, k, initial_keys=keys, turn_start_distribute=tsd, hand_limit=limit)
        return base(turns[0]) if turns else []
    # custom scan top->bottom
    from gkagent.sim.exam_shuffle import opening_deck_and_rng
    _rng, remaining = opening_deck_and_rng(seed, cards, k)
    hand, overflow = [], []
    for c in list(remaining):
        if c not in keys:
            continue
        remaining.remove(c)
        (hand if len(hand) < limit else overflow).append(c)
    remaining.extend(overflow)
    need = max(0, tsd - len(hand))
    for _ in range(need):
        if not remaining:
            break
        hand.append(remaining.pop(0))
    return base(hand)


rows = []
for pid, gl in seeds["problems"].items():
    sv = saves[pid]
    lo, meta = sv["loadout"], sv["meta"]
    stage = meta.get("stage")
    turns_conf = int(meta.get("turns") or 0)
    npc = NPC[stage]
    k = max(0, turns_conf - 3) + npc * turns_conf
    cards, add_idx, custom_n = parse_deck(lo["deck_cards"])
    for g in gl:
        actual = g["check"]["hand"]
        pred = pred_hand(g["seed"], cards, k, add_idx=add_idx)
        rows.append({
            "pid": pid, "index": g["index"], "stage": stage, "turns": turns_conf, "k": k,
            "label": g.get("label"), "source": (meta.get("source") or {}).get("kind"),
            "idol": lo.get("idol_card_id"), "mechanic": meta.get("mechanic"),
            "n_deck": len(cards), "n_init": sum(1 for c in cards if c[0] in initial_bases),
            "n_add": len(add_idx), "n_custom": custom_n,
            "pred": pred, "actual": actual, "ok": pred == actual,
            "absent": [c for c in actual if c not in {x[0] for x in cards}],
            "same_set": sorted(pred) == sorted(actual),
        })

ok = [r for r in rows if r["ok"]]
bad = [r for r in rows if not r["ok"]]
print(f"total {len(rows)} ok {len(ok)} bad {len(bad)}")
print("bad by stage:", Counter(r["stage"] for r in bad))
print("ok by stage:", Counter(r["stage"] for r in ok))
print("bad by label:", Counter(r["label"] for r in bad), "ok by label:", Counter(r["label"] for r in ok))
print("bad by source:", Counter(r["source"] for r in bad), "ok by source:", Counter(r["source"] for r in ok))
print("bad by mechanic:", Counter(r["mechanic"] for r in bad))
print("bad by idol:", Counter(r["idol"] for r in bad))
print("bad same_set:", sum(1 for r in bad if r["same_set"]), " bad absent:", sum(1 for r in bad if r["absent"]))
print("bad hand sizes:", Counter(len(r["actual"]) for r in bad), "ok hand sizes:", Counter(len(r["actual"]) for r in ok))
print("bad n_init:", Counter(r["n_init"] for r in bad), " ok n_init:", Counter(r["n_init"] for r in ok))
print("bad n_add:", Counter(r["n_add"] for r in bad), " ok n_add:", Counter(r["n_add"] for r in ok))

# parameter search on misses
print("\n=== parameter variants on misses ===")
fixes = Counter()
detail = defaultdict(list)
for r in bad:
    pid = r["pid"]
    gl = [g for g in seeds["problems"][pid] if g["index"] == r["index"]][0]
    lo = saves[pid]["loadout"]
    cards, add_idx, _ = parse_deck(lo["deck_cards"])
    matches = []
    base_k = r["k"]
    for npc in range(0, 7):
        for turns_add in (0,):
            k = max(0, r["turns"] - 3) + npc * r["turns"]
            for tsd in (2, 3, 4, 5):
                for scan in ("bottom", "top"):
                    ph = pred_hand(gl["seed"], cards, k, add_idx=add_idx, tsd=tsd, scan=scan)
                    if ph == r["actual"]:
                        matches.append(("npc", npc, "tsd", tsd, "scan", scan))
    # K offsets
    for off in range(-6, 7):
        if off == 0:
            continue
        for tsd in (3,):
            for scan in ("bottom",):
                ph = pred_hand(gl["seed"], cards, base_k + off, add_idx=add_idx, tsd=tsd, scan=scan)
                if ph == r["actual"]:
                    matches.append(("k_off", off, "tsd", tsd, "scan", scan))
    detail[r["pid"]].append((r["index"], matches))
    if matches:
        for m in matches:
            fixes[str(m)] += 1
print("fix counts:", fixes.most_common(20))
print("misses fixed by any variant:", sum(1 for v in detail.values() if any(m for _, m in v)), "/", len(bad))
