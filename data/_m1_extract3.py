"""M1 补充抽取3（不提交）：卡的 playMovePositionType/isEndTurnLost + 关键 enchant + drink_effects + exam_setting。"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["GKMS_NATIVE_LIB"] = str(ROOT / "data/_f2sl_tools/kernel/gkmscore.dll")
WHEEL = ROOT / "data/GKMSMainWheel"
sys.path.insert(0, str(WHEEL))
os.chdir(WHEEL / "GakumasCLI")
from GakumasCLI.scenario.exam_session import Master
master = Master.load(Path("ro/master/tables"))

w7cards = ["p_card-00-men-3_003", "p_card-01-men-2_035", "p_card-01-men-2_037",
           "p_card-01-ido-3_200", "p_card-01-men-2_036", "p_card-01-act-2_001",
           "p_card-01-men-3_036", "p_card-00-men-3_012", "p_card-01-men-2_043",
           "p_card-01-men-3_034", "p_card-01-ido-3_213", "p_card-01-men-3_006",
           "p_card-01-men-3_035", "p_card-01-men-2_099", "p_card-01-act-2_059",
           "p_card-01-men-2_098", "p_card-01-men-2_011", "p_card-00-acc-0_002",
           "p_card-01-act-3_049", "p_card-01-men-3_033", "p_card-01-men-2_038",
           "p_card-01-act-3_010"]
print("=== card move/lost fields ===")
for cid in w7cards:
    row = master.cards.get((cid, 0)) or {}
    interesting = {k: v for k, v in row.items() if any(
        s in k.lower() for s in ("move", "lost", "grave", "initial", "rarity", "position"))}
    print(cid, json.dumps(interesting, ensure_ascii=False, default=str))
print("\nfull row keys:", sorted((master.cards.get(("p_card-01-men-2_099", 0)) or {}).keys()))

print("\n=== enchants (card) ===")
for enc in ["enchant-p_card-01-men-3_035-enc01", "enchant-p_card-01-act-3_049-enc01",
            "enchant-p_card-01-ido-3_200-enc01", "enchant-p_card-01-men-2_038-enc01",
            "enchant-pdrink_00-2-010-enc01"]:
    row = master.enchants.get(enc) or master.card_status_enchants.get(enc) or {}
    slim = {k: v for k, v in row.items() if k != "produceDescriptions"}
    print(enc, json.dumps(slim, ensure_ascii=False, default=str)[:900])

print("\n=== drink effects ===")
for de in ["p_drink_effect-e_effect-exam_card_draw-0002",
           "p_drink_effect-e_effect-exam_card_move-p_card_search-deck_grave-idol-unique-1-hand-all-0_0",
           "p_drink_effect-e_effect-exam_playable_value_add-01",
           "p_drink_effect-e_effect-exam_status_enchant-05-enchant-pdrink_00-2-010-enc01"]:
    row = master.drink_effects.get(de, {})
    slim = {k: v for k, v in row.items() if k != "produceDescriptions"}
    print(de, json.dumps(slim, ensure_ascii=False, default=str)[:700])

print("\n=== searches: idol-unique / acc ===")
for sid in ["p_card_search-deck_grave-idol-unique-1", "p_card_search-deck_grave-p_card-00-acc-0_002"]:
    row = master.searches.get(sid, {})
    slim = {k: v for k, v in row.items() if k != "produceDescriptions"}
    print(sid, json.dumps(slim, ensure_ascii=False, default=str))

print("\n=== exam_setting panic/hand ===")
es = master.exam_setting
for k, v in es.items():
    if any(s in k.lower() for s in ("panic", "hand", "hold", "distribute", "shuffle", "grave", "lost")):
        print(k, "=", json.dumps(v, ensure_ascii=False, default=str)[:300])

print("\n=== support card table search ===")
# support cards 可能在 audition_catalog / lesson_catalog
for attr in ("audition_catalog", "lesson_catalog"):
    v = getattr(master, attr)
    print(attr, type(v), (list(v.keys())[:5] if isinstance(v, dict) else len(v)))
