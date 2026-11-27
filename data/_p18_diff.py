# P1-8 diff 校验：改前/改后 p_items.json 逐条对比（不提交）
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
before = json.load(open(r"D:\Games\gakumas-agent\data\_p18_pitems_before.json", encoding="utf-8"))
after = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\p_items.json", encoding="utf-8"))
b = {r["id"]: r for r in before["items"]}
a = {r["id"]: r for r in after["items"]}
assert set(b) == set(a), "id 集合变化！"
changed = []
for rid in b:
    if json.dumps(b[rid], ensure_ascii=False, sort_keys=True) != json.dumps(a[rid], ensure_ascii=False, sort_keys=True):
        changed.append(rid)
print("变化记录数:", len(changed))
for rid in changed:
    print("\n===", rid, a[rid]["name"], "===")
    for eb, ea in zip(b[rid]["effects"], a[rid]["effects"]):
        if json.dumps(eb, ensure_ascii=False, sort_keys=True) != json.dumps(ea, ensure_ascii=False, sort_keys=True):
            print("  before:", json.dumps(eb, ensure_ascii=False))
            print("  after :", json.dumps(ea, ensure_ascii=False))
# stats 对比
print("\nstats before depends_on:", before["stats"]["effects_depends_on"], "after:", after["stats"]["effects_depends_on"])
# implemented 汇总
sys.path.insert(0, r"D:\Games\gakumas-agent\src")
from gkagent.sim import p_items as P
sb = P.summarize(P.load_p_items(r"D:\Games\gakumas-agent\data\_p18_pitems_before.json"))
sa = P.summarize(P.load_p_items())
print("implemented before:", sb["implemented"], "after:", sa["implemented"])
print("depends_on_specs before:", sb["depends_on_specs"], "after:", sa["depends_on_specs"])
print("noop before:", sb["noop"], "after:", sa["noop"])