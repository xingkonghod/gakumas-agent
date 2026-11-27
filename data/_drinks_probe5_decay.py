"""M6 探针 5b：好印象衰减口径测定（fresh 保护？）。不提交。

场景：
  A 路易波士茶（imp+3 立即，无附魔）喝后 end×3；
  B 严选初星茶（回合结束 imp+1 附魔）喝后 end×3；
  C 路易波士茶 + 严选初星茶 同回合喝后 end×3。
逐 end 步记录 impression/score + turn_start_reads.review（回合开始读数）。
"""
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
os.environ.setdefault("GKMSCLIGPU_LIB", str(ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
from gkbench import engine  # noqa: E402

engine.setup()
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402

BASE = json.load(open(ROOT / "data/_rinami_live/W9/gkms-loadout.json", encoding="utf-8"))
master = engine.master()


def loadout_for(dids):
    doc = dict(BASE)
    doc["drink_ids"] = list(dids)
    doc["produce_item_ids"] = []
    doc["lesson_start_enchant_ids"] = []
    doc["main_item_enchant_ids"] = []
    doc["support_cards"] = []
    return doc


def snap(s):
    st = s.state
    return {"turn": s.turn, "score": int(st.score), "impression": int(st.review),
            "focus": int(st.lesson_buff), "aggressive": int(st.aggressive)}


out = {}
for label, dids in (
    ("A_rooibos", ["pdrink_02-1-006"]),
    ("B_tea", ["pdrink_02-3-006"]),
    ("C_rooibos_tea", ["pdrink_02-1-006", "pdrink_02-3-006"]),
):
    doc = loadout_for(dids)
    s, _ = build_hif_loadout_session(master, doc, int(doc["seed"]))
    rows = [{"step": "start", **snap(s)}]
    for i in range(len(dids)):
        s.step(("drink", 0), observe=False)  # 喝掉的瓶从列表移除，下一瓶仍是 idx0
        rows.append({"step": f"drink{i}", **snap(s)})
    for k in range(3):
        s.step(("end",), observe=False)
        rows.append({"step": f"end{k+1}", **snap(s),
                     "ts_review": s.turn_start_reads.get(s.turn, {}).get("review"),
                     "te_score": s.turn_end_reads.get(s.turn - 1, {}).get("score")})
    out[label] = rows
    print(f"\n=== {label} {dids} ===")
    for r in rows:
        print("  ", r)
    del s

(ROOT / "data/_drinks_probe5_decay.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nwritten data/_drinks_probe5_decay.json")
