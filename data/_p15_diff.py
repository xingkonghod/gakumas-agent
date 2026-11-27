import io, json, subprocess, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(open("data/_p15_diff.out.txt", "wb"), encoding="utf-8")
head = json.loads(subprocess.check_output(["git", "show", "HEAD:data/knowledge/p_items.json"]).decode("utf-8"))["items"]
new = json.loads(Path("data/knowledge/p_items.json").read_text(encoding="utf-8"))["items"]
h = {r["id"]: r for r in head}
n = {r["id"]: r for r in new}
assert set(h) == set(n), "id set changed!"
changed = []
for id_ in h:
    if json.dumps(h[id_], ensure_ascii=False, sort_keys=True) != json.dumps(n[id_], ensure_ascii=False, sort_keys=True):
        changed.append(id_)
print(f"changed records: {len(changed)} / {len(h)}")
# categorize changes
from collections import Counter
cat = Counter()
for id_ in changed:
    he = {i: e for i, e in enumerate(h[id_]["effects"])}
    ne = {i: e for i, e in enumerate(n[id_]["effects"])}
    diffs = []
    for i in he:
        a, b = he[i], ne.get(i, {})
        if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
            keys = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
            diffs.append((a.get("type"), keys))
    for t, keys in diffs:
        cat[(t, tuple(sorted(keys)))] += 1
for k, c in cat.most_common():
    print(f"  {c:3d}  {k}")
print("\nsample changed ids:", changed[:20])
# show a few full diffs for 好调 conversion + reduce
for id_ in ("pitem_01-1-022-0", "pitem_02-1-016-0", "pitem_03-3-298-0", "pitem_00-2-010-0", "pitem_00-2-012-0"):
    if id_ in changed:
        print(f"\n== {id_} {n[id_]['name']} ==")
        for i, e in enumerate(n[id_]["effects"]):
            oe = h[id_]["effects"][i]
            if json.dumps(e, sort_keys=True) != json.dumps(oe, sort_keys=True):
                print(f"  [{e.get('type')}] old={oe.get('values')}/role={oe.get('role','')}/dep={oe.get('depends_on','')} -> new={e.get('values')}/role={e.get('role','')}/dep={e.get('depends_on','')}")
