"""B10 探针 v7：pIdol 名字交叉核对 + card.effectGroupIds 权威分组。"""
import json, io, sqlite3, zlib, collections, csv

out = io.open(r"D:\Games\gakumas-agent\data\_probe_b10_x.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out)

db = r"D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master\d31baf6608ee4553091f28446f628cd3ad66ff01\catalog.sqlite"
con = sqlite3.connect(db)
tables = [r[0] for r in con.execute("select distinct table_name from records order by 1")]
p("tables:", tables)
def load(table):
    return [json.loads(zlib.decompress(pl).decode("utf-8","replace"))
            for _,_,pl in con.execute("select row_id, variant, payload from records where table_name=?", (table,))]
cards = load("ProduceCard")
by_name = {}
for c in cards:
    by_name.setdefault(c["name"], []).append(c)

ref = r"D:\Games\gakumas-agent\data\dl\gt\gakumas-tools-master\packages\gakumas-data\csv\skill_cards.csv"
rows = list(csv.DictReader(open(ref, encoding="utf-8")))
pidol = [r for r in rows if r.get("sourceType") == "pIdol"]
match_origin = 0; match_prima = 0; miss = []
for r in pidol:
    up = 1 if r.get("upgraded") == "TRUE" else 0
    cand = [c for c in by_name.get(r["name"], []) if c["upgradeCount"] == up]
    if not cand:
        miss.append((r["name"], up, "no-name"))
        continue
    c = cand[0]
    if c.get("originIdolCardId"):
        match_origin += 1
    elif c.get("originPrimaStellaIdolCardId"):
        match_prima += 1
    else:
        miss.append((r["name"], up, c["id"], "no-origin"))
p("pIdol rows:", len(pidol), "match originIdolCardId:", match_origin, "match prima:", match_prima, "miss:", len(miss))
p("miss sample:", miss[:15])
# unique 列与 pIdol 的关系
p("unique==TRUE rows:", sum(1 for r in rows if r.get("unique")=="TRUE"))
p("pIdol & unique:", sum(1 for r in pidol if r.get("unique")=="TRUE"))

# effectGroupIds
sample_ids = ["p_card-03-act-1_040", "p_card-00-act-0_001", "p_card-01-men-2_035"]
for c in cards:
    if c["id"] in sample_ids and c["upgradeCount"] == 0:
        p("\ncard", c["id"], c["name"], "effectGroupIds:", c.get("effectGroupIds"), "searchTag:", c.get("searchTag"))
# 找 effect group 定义表
for t in tables:
    if "EffectGroup" in t and "Gimmick" not in t:
        g = load(t)
        p("\ntable", t, "rows:", len(g), "keys:", list(g[0].keys()) if g else [])
        for row in g[:3]:
            p(json.dumps(row, ensure_ascii=False)[:400])
con.close()
out.close()
print("written")