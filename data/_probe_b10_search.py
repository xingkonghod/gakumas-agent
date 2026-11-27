"""B10 探针 v3：ProduceCardSearch 表结构 + 关键卡名/IdolUnique 口径。"""
import json, io, collections

out = io.open(r"D:\Games\gakumas-agent\data\_probe_b10_search.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out)

src = r"D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans\ProduceCardSearch.json"
data = json.load(open(src, encoding="utf-8"))
rows = data.get("data", [])
p("ProduceCardSearch rows:", len(rows))
p("first row keys:", list(rows[0].keys()))
for r in rows[:6]:
    p(json.dumps(r, ensure_ascii=False)[:800])
# 找 trigger id 里出现的搜索词
ids = [r.get("id","") for r in rows]
p("\nall ids sample:", ids[:40])
for token in ("idol-unique", "trouble", "deck_grave", "deck_all", "min_max", "effect_group", "r-sr-ssr-legend", "lost", "hold", "hand"):
    hits = [r for r in rows if token in r.get("id","")]
    p(f"\n=== token {token}: {len(hits)} hits ===")
    for r in hits[:4]:
        p(json.dumps(r, ensure_ascii=False)[:700])
out.close()
print("written")