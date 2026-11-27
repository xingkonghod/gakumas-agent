"""sim-fidelity discovery (no-commit, pure master read, NO engine game).

Dump: pitem312 enchant/trigger/effects (gate semantics), sup-3_024 effects +
card_search pool rows (type21 candidate pool), ExamParameterBuff card candidates.
"""
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data/GKMSMainWheel"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(WHEEL))
os.chdir(WHEEL / "GakumasCLI")

from GakumasCLI.engine.semantics import MasterCatalog  # noqa: E402

cat = MasterCatalog(Path("ro/master/tables"))
out = {}

# 1. pitem 312 enchant -> trigger -> effects
enc_id = "enchant-p_item_effect_01-3-312-0-enc01"
enc = cat.enchants.get(enc_id)
if enc:
    trig = cat.triggers.get(enc.trigger_id)
    out["pitem312"] = {
        "enchant": enc.raw,
        "trigger": trig.raw if trig else None,
        "effects": [cat.effects[e].raw for e in enc.effect_ids if e in cat.effects],
    }
    print("== pitem312 trigger ==")
    print(json.dumps(trig.raw if trig else None, ensure_ascii=False, indent=1))
    print("== pitem312 effects ==")
    for e in enc.effect_ids:
        if e in cat.effects:
            print(json.dumps(cat.effects[e].raw, ensure_ascii=False))
else:
    print("pitem312 enchant NOT FOUND")

# 2. sup-3_024 effects + search pool
cid = "p_card-00-sup-3_024"
cd = cat.cards.get((cid, 0))
print("\n== sup-3_024 ==")
if cd:
    effs = []
    for e in cd.play_effect_ids:
        if e in cat.effects:
            effs.append(cat.effects[e].raw)
    out["sup324_effects"] = effs
    for er in effs:
        print(json.dumps(er, ensure_ascii=False))
        sid = er.get("produceCardSearchId")
        if sid:
            sr = cat.searches.get(sid)
            print("  search row:", json.dumps(sr, ensure_ascii=False))
            out["sup324_search_" + str(sid)] = sr

# 3. ExamParameterBuff cards (value1 = layers) for probe decks
print("\n== ExamParameterBuff candidates (up=0) ==")
pb_cards = []
for (cid2, up), cd2 in cat.cards.items():
    if up != 0:
        continue
    for e in cd2.play_effect_ids:
        ed = cat.effects.get(e)
        if ed and ed.type_name == "ExamParameterBuff":
            pb_cards.append({"id": cid2, "name": cd2.name, "value1": ed.value1,
                             "turn": ed.turn, "count": ed.count,
                             "n_effects": len(cd2.play_effect_ids),
                             "types": [cat.effects[x].type_name for x in cd2.play_effect_ids if x in cat.effects]})
            break
pb_cards.sort(key=lambda r: (r["value1"] or 0))
for r in pb_cards[:40]:
    print(" ", r)
out["parameter_buff_cards"] = pb_cards

# 4. searches row structure + random pool tables
print("\n== searches sample ==")
for sid, sr in list(cat.searches.items())[:3]:
    print(" ", sid, json.dumps(sr, ensure_ascii=False)[:400])
print("\n== master tables files ==")
tdir = Path("ro/master/tables")
names = sorted(p.name for p in tdir.glob("*.jsonl"))
print(names)
pool_files = [n for n in names if "Random" in n or "Pool" in n]
print("pool files:", pool_files)
for n in pool_files:
    rows = [json.loads(l) for l in (tdir / n).open(encoding="utf-8") if l.strip()]
    dec = [r.get("decoded", r) for r in rows]
    print(f"  {n}: {len(dec)} rows; first:", json.dumps(dec[0], ensure_ascii=False)[:500])
    out["table_" + n] = {"n": len(dec), "first": dec[0] if dec else None}
    hits = [r for r in dec if "p_random_pool-all" in json.dumps(r)]
    print(f"    p_random_pool-all hits: {len(hits)}")
    if hits:
        print("    hit0:", json.dumps(hits[0], ensure_ascii=False)[:800])
        out["pool_all_hit0"] = hits[0]
        out["pool_all_hits_n"] = len(hits)

(ROOT / "data/_simfid_discover.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nsaved data/_simfid_discover.json")