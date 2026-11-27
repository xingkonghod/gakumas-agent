"""B10 探针 v8：idol-unique 残余 origin 字段 + 参考 DSL 生成时机 + 自尊 id。"""
import json, io, sqlite3, zlib, csv

out = io.open(r"D:\Games\gakumas-agent\data\_probe_b10_final.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out)

db = r"D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master\d31baf6608ee4553091f28446f628cd3ad66ff01\catalog.sqlite"
con = sqlite3.connect(db)
def load(table):
    return [json.loads(zlib.decompress(pl).decode("utf-8","replace"))
            for _,_,pl in con.execute("select row_id, variant, payload from records where table_name=?", (table,))]
cards = load("ProduceCard")
for c in cards:
    if c["id"] in ("p_card-01-ido-3_191","p_card-02-ido-3_192","p_card-03-ido-3_193","p_card-02-ido-3_232") and c["upgradeCount"]==0:
        p(c["id"], c["name"], {k:c.get(k) for k in ("originIdolCardId","originSupportCardId","originCharacterId","originPrimaStellaIdolCardId","isInitialDeckProduceCard")})
# 全体：originCharacterId 非空数量
p("originCharacterId non-empty:", sum(1 for c in cards if c.get("originCharacterId")))
p("originSupportCardId non-empty:", sum(1 for c in cards if c.get("originSupportCardId")))
# 判据并集 vs 参考 pIdol（按名字）
ref = r"D:\Games\gakumas-agent\data\dl\gt\gakumas-tools-master\packages\gakumas-data\csv\skill_cards.csv"
rows = list(csv.DictReader(open(ref, encoding="utf-8")))
pidol_names = {(r["name"], 1 if r.get("upgraded")=="TRUE" else 0) for r in rows if r.get("sourceType")=="pIdol"}
by_name = {}
for c in cards:
    by_name.setdefault((c["name"], c["upgradeCount"]), c)
crit = lambda c: bool(c.get("originIdolCardId") or c.get("originCharacterId") or c.get("originPrimaStellaIdolCardId"))
matched = sum(1 for nm in pidol_names if nm in by_name and crit(by_name[nm]))
in_snapshot = sum(1 for nm in pidol_names if nm in by_name)
p("pIdol names:", len(pidol_names), "in snapshot:", in_snapshot, "criterion matches:", matched)
extra = [(nm, by_name[nm]["id"]) for nm in pidol_names if nm in by_name and not crit(by_name[nm])]
p("still missing:", extra)
# 反向：判据命中但参考不是 pIdol？
ref_all = {(r["name"], 1 if r.get("upgraded")=="TRUE" else 0): r.get("sourceType") for r in rows}
false_pos = [(c["name"], c["id"], ref_all.get((c["name"], c["upgradeCount"]))) for c in cards
             if crit(c) and (c["name"], c["upgradeCount"]) in ref_all and ref_all[(c["name"], c["upgradeCount"])] != "pIdol"]
p("false positives:", false_pos[:10], "count:", len(false_pos))
con.close()

# 参考 p_items.csv 生成类 DSL
csvp = r"D:\Games\gakumas-agent\data\dl\gt\gakumas-tools-master\packages\gakumas-data\csv\p_items.csv"
for r in csv.DictReader(open(csvp, encoding="utf-8")):
    eff = r.get("effects","")
    if "addCardTo" in eff or "addRandomBasic" in eff:
        p("\nCSV", r["id"], r["name"], "::", eff)

# 自尊 id
ct = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\card_table.json", encoding="utf-8"))["cards"]
for n in ("自尊","自尊+","沉静意志+","演出前夜+","睡意"):
    r = ct.get(n)
    p("card_table", n, "->", (r or {}).get("id"), (r or {}).get("upgrade"))
out.close()
print("written")