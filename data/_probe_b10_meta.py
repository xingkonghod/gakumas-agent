"""B10 探针 v4：catalog ProduceCard 列 + 关键 P 道具完整记录 + gkbench loadout 覆盖。"""
import json, io, sqlite3, collections, zlib

out = io.open(r"D:\Games\gakumas-agent\data\_probe_b10_meta.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out)

# 1) catalog ProduceCard（records 通用表，payload JSON）
db = r"D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master\d31baf6608ee4553091f28446f628cd3ad66ff01\catalog.sqlite"
con = sqlite3.connect(db)
rows = con.execute("select row_id, variant, payload from records where table_name='ProduceCard'").fetchall()
p("ProduceCard rows:", len(rows))
parsed = [json.loads(zlib.decompress(pl).decode("utf-8", "replace")) for _, _, pl in rows]
sample = parsed[0]
p("payload keys:", list(sample.keys()))
p("sample payload:", json.dumps(sample, ensure_ascii=False)[:900])
keys = collections.Counter()
for row in parsed:
    for k in row.keys():
        keys[k] += 1
p("all keys:", dict(keys))
for field in ("sourceType", "produceCardSourceType", "category", "produceCardCategory", "idolCardId", "produceIdolCardId", "rarity"):
    if field in keys:
        dist = collections.Counter(r.get(field) for r in parsed)
        p(f"  {field}: {dict(dist.most_common(12))}")
con.close()

# 2) 关键 P 道具完整记录
data = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\p_items.json", encoding="utf-8"))
recs = {r["id"]: r for r in data["items"]}
for pid in ("pitem_01-3-131-0", "pitem_01-3-127-0", "pitem_01-3-266-0",
            "pitem_tower_001-exam_review-1-stage_022", "pitem_01-3-346-0"):
    p("\n=== ", pid, " ===")
    p(json.dumps(recs.get(pid), ensure_ascii=False, indent=1))

# 3) gkbench hif loadout 里有哪些生成卡/trigger未知道具
import glob
saves = glob.glob(r"D:\Games\gakumas-agent\data\bench_local\gkbench_dl\hif\**\saves.jsonl", recursive=True)
p("\nsaves files:", saves[:5])
ids = collections.Counter()
for f in saves[:1]:
    for line in open(f, encoding="utf-8"):
        try:
            row = json.loads(line)
        except Exception:
            continue
        lo = row.get("loadout") or {}
        for i in lo.get("produce_item_ids") or []:
            ids[i] += 1
p("unique loadout ids:", len(ids))
gen_ids = [r["id"] for r in data["items"] if any(e.get("type")=="ExamCardCreateId" for e in r.get("effects",[]))]
unk_ids = [r["id"] for r in data["items"] if r.get("trigger_known") is False]
p("generation items in loadout:", {i: ids[i] for i in gen_ids if i in ids})
p("trigger-unknown items in loadout:", {i: ids[i] for i in unk_ids if i in ids})
out.close()
print("written")