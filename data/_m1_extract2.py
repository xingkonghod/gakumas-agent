"""M1 补充抽取（不提交）：支援卡表定位 + rinami 关键卡效果 + 全部 search 定义。"""
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
attrs = [a for a in dir(master) if not a.startswith("_")]
print("Master attrs:", attrs)
for a in attrs:
    v = getattr(master, a)
    if isinstance(v, dict):
        ks = list(v.keys())[:3]
        print(f"  {a}: dict n={len(v)} sample_keys={ks}")

# 找支援卡
for a in attrs:
    v = getattr(master, a)
    if isinstance(v, dict) and any("s_card" in str(k) for k in list(v.keys())[:50]):
        print(f"== support table candidate: {a}")
        row = v.get("s_card-2-0007")
        print(json.dumps(row, ensure_ascii=False, default=str)[:1500])
        break

dump = json.loads((ROOT / "data/_m1_effects_dump.json").read_text(encoding="utf-8"))
print("\n=== all searches ===")
for sid, s in dump["searches"].items():
    slim = {k: v for k, v in s.items() if k != "produceDescriptions"}
    print(sid, json.dumps(slim, ensure_ascii=False, default=str))

print("\n=== key rinami card effects (compact) ===")
keys = ["p_card-01-men-2_099::1", "p_card-01-men-2_099::2", "p_card-01-men-2_098::1",
        "p_card-01-act-2_001::1", "p_card-01-act-2_001::2", "p_card-01-ido-3_213::1",
        "p_card-01-ido-3_213::2", "p_card-01-ido-3_200::1", "p_card-00-acc-0_002::0",
        "p_card-01-men-2_043::0", "p_card-01-men-2_043::1", "p_card-01-act-2_059::0",
        "p_card-01-men-2_038::1", "p_card-01-act-3_010::1", "p_card-01-act-3_049::0",
        "p_card-01-men-2_011::1", "p_card-01-men-2_011::2", "p_card-01-men-2_037::1",
        "p_card-01-men-2_037::2", "p_card-00-men-3_012::1", "p_card-01-men-2_036::1",
        "p_card-01-men-3_036::1", "p_card-00-men-3_003::1", "p_card-01-men-2_035::0",
        "p_card-01-men-3_033::1", "p_card-01-men-3_006::1", "p_card-01-men-3_035::1"]
for k in keys:
    c = dump["cards"].get(k)
    if not c:
        print(k, "MISSING")
        continue
    effs = []
    for link in c["playEffects"] or []:
        eid = link.get("produceExamEffectId")
        e = dump["effects"].get(eid, {})
        t = e.get("effectType") or {}
        tn = t.get("number") if isinstance(t, dict) else t
        effs.append(f'{eid}[t{tn} v1={e.get("effectValue1")} v2={e.get("effectValue2")} '
                    f'move={(e.get("movePositionType") or {}).get("number") if isinstance(e.get("movePositionType"),dict) else e.get("movePositionType")} '
                    f'search={e.get("produceCardSearchId")}]')
    print(f"--- {k} {c['name']}")
    for e in effs:
        print("   ", e)

# 支援卡 filter：尝试常见表名
print("\n=== support rows ===")
sup_ids = ["s_card-2-0007", "s_card-3-0030", "s_card-3-0070", "s_card-3-0025", "s_card-3-0064", "s_card-3-0069"]
found = False
for a in attrs:
    v = getattr(master, a)
    if isinstance(v, dict) and "s_card-2-0007" in v:
        found = True
        print("table:", a)
        for sid in sup_ids:
            row = v.get(sid, {})
            slim = {kk: vv for kk, vv in row.items() if kk not in ("produceDescriptions",)}
            print(sid, json.dumps(slim, ensure_ascii=False, default=str)[:800])
        break
if not found:
    print("no dict table contains s_card-2-0007; trying master.support_cards attr types")
