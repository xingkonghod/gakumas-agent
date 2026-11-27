"""f2-engine-gap 探针①分析：开局牌序核对 + 机制卡效果数据 + 插入位置预测复核。只读。"""
from __future__ import annotations
import json, sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkagent.sim.exam_shuffle import opening_deck_and_rng
from gkbench.save import expand_loadout

rows = [json.loads(l) for l in open(ROOT / "data/_engine_probe_rng_p1.jsonl", encoding="utf-8")]
saves = {}
for line in open(ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl", encoding="utf-8"):
    r = json.loads(line); saves[r["id"]] = r

print("=== OPEN: engine_deck == model_deck minus hand (order-preserving)? ===")
seen = set()
for o in [r for r in rows if r["kind"] == "open"]:
    if o["pid"] in seen: continue
    seen.add(o["pid"])
    lo = expand_loadout(saves[o["pid"]]["loadout"])
    cards = [(c["produce_card_id"], int(c.get("current_upgrade_count") or 0)) for c in lo["deck_cards"]]
    _rng, sh = opening_deck_and_rng(o["seed"], cards, o["k"])
    model = [c[0] for c in sh]
    hand = [h[0] for h in o["hand"]]
    rem = list(model); ok = True
    for h in hand:
        if h in rem: rem.remove(h)
        else: ok = False
    eng = o["engine_deck_prefix"]; el = o["engine_deck_len"]
    # full engine deck not stored; compare prefix + length
    print(o["pid"], "hand_in_model=", ok, "len_rem=", len(rem), "eng_len=", el,
          "prefix_match=", rem[:len(eng)] == eng)

print()
print("=== mechanism card effect rows (engine master data, read-only) ===")
import os
os.environ.setdefault("GKMS_NATIVE_LIB", str(ROOT / "data/_f2sl_tools/kernel/gkmscore.dll"))
WHEEL = ROOT / "data/GKMSMainWheel"
sys.path.insert(0, str(WHEEL))
os.chdir(WHEEL / "GakumasCLI")
from GakumasCLI.scenario.exam_session import Master
master = Master.load(Path("ro/master/tables"))
mech_cards = ["p_card-01-men-2_099", "p_card-01-men-2_098", "p_card-03-men-2_103",
              "p_card-01-men-2_110", "p_card-03-act-2_102", "p_card-01-men-3_034",
              "p_card-03-men-2_064", "p_card-03-act-3_065", "p_card-00-sup-3_158",
              "p_card-01-men-3_006", "p_card-03-ido-100_042", "p_card-03-act-2_082",
              "p_card-03-ido-3_238", "p_card-03-men-3_063", "p_card-03-men-2_112"]
enums = json.loads((WHEEL / "GakumasCLI/engine/data/exam_enums.json").read_text(encoding="utf-8"))
etype = {int(k): v for k, v in enums.get("ProduceExamEffectType", {}).items()} if isinstance(enums.get("ProduceExamEffectType"), dict) else {}
for cid in mech_cards:
    row = master.cards.get((cid, 0)) or {}
    print(f"--- {cid} name={row.get('name')}")
    for link in row.get("playEffects", []) or []:
        eid = link.get("produceExamEffectId")
        eff = master.effects.get(eid, {})
        t = eff.get("effectType") or {}
        tn = t.get("number") if isinstance(t, dict) else t
        print("   ", eid, "type", tn, etype.get(int(tn), "?") if tn is not None else "?",
              "v1", eff.get("effectValue1"), "v2", eff.get("effectValue2"),
              "search", eff.get("produceCardSearchId"), "move", eff.get("movePositionType"),
              "pick", eff.get("pickCountType"), eff.get("pickMin"), eff.get("pickMax"))

print()
print("=== insertion prediction recheck (widths deck_b-1..deck_b+2) ===")
MASK = 0xFFFFFFFF
def xs(s):
    s ^= (s << 13) & MASK; s ^= s >> 17; s ^= (s << 5) & MASK
    return s & MASK
for r in rows:
    if r["kind"] == "step" and r.get("deck_inserted") and r["consumption"] is not None and r["consumption"] <= 60:
        states = []; s = r["rng_before"]
        for _ in range(r["consumption"]):
            states.append(s); s = xs(s)
        for ins in r["deck_inserted"]:
            hits = {}
            for w in range(max(1, r["deck_len_before"] - 1), r["deck_len_before"] + 3):
                m = [j for j, st in enumerate(states) if ((st * w) >> 32) == ins["index"]]
                if m: hits[w] = m
            if r["deck_len_before"] == 0:
                hits["w0_any"] = "width0 -> index0 always"
            print(r["pid"], "t", r["obs_before"]["turn"], r["played"], "ins", ins["card"], "@", ins["index"],
                  "deck_b", r["deck_len_before"], "cons", r["consumption"], "width_hits", hits)
