import sys, os, json, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data/GKMSMainWheel"))
os.chdir(ROOT / "data/GKMSMainWheel/GakumasCLI")
from GakumasCLI.engine.semantics import MasterCatalog
cat = MasterCatalog(Path("ro/master/tables"))
cd = cat.cards[("p_card-01-men-2_110", 0)]
print("110 effects:")
for e in cd.play_effect_ids:
    ed = cat.effects.get(e)
    print("  ", ed.type_name, "v1=", ed.value1, "turn=", ed.turn, "cnt=", ed.count, "groups=", ed.effect_group_ids)
print("--- qualifying group members (exam_parameter_buff, not multiple) ---")
qual = []
for (cid, up), c in cat.cards.items():
    if up != 0:
        continue
    for e in c.play_effect_ids:
        ed = cat.effects.get(e)
        if ed and any("exam_parameter_buff" in g and "multiple" not in g for g in ed.effect_group_ids):
            qual.append((cid, c.name, ed.type_name, ed.value1, ed.turn))
            break
print("n qual=", len(qual))
for r in sorted(qual, key=lambda x: (x[3] or 0))[:25]:
    print(r)