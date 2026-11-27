"""B10 探针 v6：pIdol 判据交叉验证 + effect_group 权威定义。"""
import json, io, sqlite3, zlib, collections, csv

out = io.open(r"D:\Games\gakumas-agent\data\_probe_b10_group.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out)

# 1) 参考 skill_cards.csv 的 sourceType=pIdol 集合
ref = r"D:\Games\gakumas-agent\data\dl\gt\gakumas-tools-master\packages\gakumas-data\csv\skill_cards.csv"
with open(ref, encoding="utf-8") as f:
    rd = csv.DictReader(f)
    p("csv columns:", rd.fieldnames)
    rows = list(rd)
p("csv rows:", len(rows))
pidol = [r for r in rows if r.get("sourceType") == "pIdol"]
p("pIdol rows:", len(pidol), "sample:", [(r.get("id"), r.get("name")) for r in pidol[:5]])
ref_pidol_ids = {r.get("id") for r in pidol}

db = r"D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master\d31baf6608ee4553091f28446f628cd3ad66ff01\catalog.sqlite"
con = sqlite3.connect(db)
def load(table):
    return [json.loads(zlib.decompress(pl).decode("utf-8","replace"))
            for _,_,pl in con.execute("select row_id, variant, payload from records where table_name=?", (table,))]
cards = load("ProduceCard")
# 参考 id 是数字 baseId；我们的 id 是 p_card-...。参考 csv 有没有 p_card id 列？
p("csv sample row:", json.dumps(rows[0], ensure_ascii=False)[:400])
our_idol = {c["id"] for c in cards if c.get("originIdolCardId")}
p("our originIdolCardId base ids:", len(our_idol))

# 2) effect group 权威定义
groups = load("ProduceExamGimmickEffectGroup")
p("\ngroup id samples:", [g["id"] for g in groups[:8]])
hits = [g for g in groups if "full_power" in g["id"] or "concentration" in g["id"]]
p("groups with full_power/concentration in id:", len(hits))
for g in hits[:6]:
    p(json.dumps({k: g[k] for k in ("id","priority","produceExamEffectId","fieldStatusProduceCardSearchId")}, ensure_ascii=False))
# ProduceExamEffect 表：id -> examEffectType
effects = load("ProduceExamEffect")
p("\nProduceExamEffect rows:", len(effects), "keys:", list(effects[0].keys()))
eff_by_id = {e["id"]: e for e in effects}
for g in hits[:6]:
    eid = g.get("produceExamEffectId")
    e = eff_by_id.get(eid)
    p("group", g["id"], "-> effect", eid, "type:", (e or {}).get("examEffectType") or (e or {}).get("type"))
con.close()

# 3) card_table 里 FullPower 相关效果类型
ct = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\card_table.json", encoding="utf-8"))["cards"]
types = collections.Counter(e.get("type") for r in ct.values() for e in r.get("effects") or [])
p("\nFullPower effect types in card_table:", {k:v for k,v in types.items() if "FullPower" in k})
out.close()
print("written")