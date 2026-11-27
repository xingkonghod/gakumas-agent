"""B10 探针 v2：ExamCardCreateId 段 + trigger_known=False 形态（只读，不提交）。输出 UTF-8 文件。"""
import json, collections, io

out = io.open(r"D:\Games\gakumas-agent\data\_probe_b10_out.txt", "w", encoding="utf-8")
def p(*a):
    print(*a, file=out)

data = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\p_items.json", encoding="utf-8"))
recs = data["items"]
p("items:", len(recs), "stats:", json.dumps(data.get("stats", {}), ensure_ascii=False))

# 1) ExamCardCreateId 段（effects 内）
p("\n=== ExamCardCreateId effects ===")
n = 0
for r in recs:
    for e in r.get("effects", []):
        if e.get("type") == "ExamCardCreateId":
            n += 1
            p(json.dumps({"id": r["id"], "name": r.get("name"),
                          "trigger": r.get("trigger"), "trigger_id": r.get("trigger_id"),
                          "trigger_text": r.get("trigger_text"), "trigger_params": r.get("trigger_params"),
                          "condition": r.get("condition"), "trigger_known": r.get("trigger_known", True),
                          "effect": e, "text_zh": r.get("text_zh"), "text_ja": r.get("text_ja"),
                          "max_uses": r.get("max_uses")}, ensure_ascii=False))
p("total ExamCardCreateId effects:", n)

# 2) trigger_known=False 形态（记录级）
p("\n=== trigger_known=False records ===")
cnt = collections.Counter()
samples = collections.defaultdict(list)
nitems = 0; nspecs = 0
for r in recs:
    if r.get("trigger_known") is not False:
        continue
    nitems += 1
    nspecs += len(r.get("effects", []))
    tid = r.get("trigger_id") or ""
    key = tid.split("-p_card-")[0] if "-p_card-" in tid else tid
    cnt[key] += 1
    if len(samples[key]) < 4:
        samples[key].append({"id": r["id"], "trigger_id": tid, "trigger": r.get("trigger"),
                             "trigger_text": r.get("trigger_text"),
                             "effect_types": [e.get("type") for e in r.get("effects", [])],
                             "text_zh": (r.get("text_zh") or "")[:100], "text_ja": (r.get("text_ja") or "")[:100]})
p("items:", nitems, "effect segments:", nspecs)
for k, v in cnt.most_common(40):
    p(f"\n[{v}] {k}")
    for s in samples[k]:
        p("   ", json.dumps(s, ensure_ascii=False))
out.close()
print("written")