"""B10 探针 v9：parse_card_search 逐条对比旧 trigger_known。"""
import json, io, sys, collections
sys.path.insert(0, r"D:\Games\gakumas-agent\scripts")
sys.path.insert(0, r"D:\Games\gakumas-agent\src")
import build_p_items as b

out = io.open(r"D:\Games\gakumas-agent\data\_probe_b10_parse.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out)

data = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\p_items.json", encoding="utf-8"))
recs = data["items"]
old_false = {r["id"] for r in recs if r.get("trigger_known") is False}
new_false = set()
diff_newly = []
diff_fixed = []
for r in recs:
    tid = r.get("trigger_id") or ""
    pf, zc, unres = b.parse_card_search(tid)
    if unres and r.get("trigger_domain") == "exam":
        new_false.add(r["id"])
        if r["id"] not in old_false:
            diff_newly.append((r["id"], tid, pf, zc))
    elif r["id"] in old_false:
        diff_fixed.append((r["id"], tid, pf, zc))
p("old trigger_unknown:", len(old_false), "new:", len(new_false))
p("newly unresolved:", len(diff_newly), "fixed:", len(diff_fixed))
p("\n=== newly unresolved samples ===")
for x in diff_newly[:25]:
    p(json.dumps(x, ensure_ascii=False))
p("\n=== fixed samples ===")
for x in diff_fixed[:12]:
    p(json.dumps(x, ensure_ascii=False))
# 统计 fixed 的限定类型
kinds = collections.Counter()
for _, _, pf, zc in diff_fixed:
    if pf: kinds["play:" + pf.get("kind", "?")] += 1
    if zc: kinds["zone:" + ",".join(zc["zones"])] += 1
p("\nfixed kinds:", dict(kinds))
out.close()
print("written")