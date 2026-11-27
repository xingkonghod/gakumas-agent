"""B10 探针 v5：idol-unique 判据（originIdolCardId）+ effect_group 语义验证。"""
import json, io, sqlite3, zlib, collections, re

out = io.open(r"D:\Games\gakumas-agent\data\_probe_b10_idol.txt", "w", encoding="utf-8")
def p(*a): print(*a, file=out)

db = r"D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master\d31baf6608ee4553091f28446f628cd3ad66ff01\catalog.sqlite"
con = sqlite3.connect(db)
def load(table):
    return [json.loads(zlib.decompress(pl).decode("utf-8","replace"))
            for _,_,pl in con.execute("select row_id, variant, payload from records where table_name=?", (table,))]
cards = load("ProduceCard")
idol = [c for c in cards if c.get("originIdolCardId")]
p("ProduceCard:", len(cards), "originIdolCardId non-empty:", len(idol))
p("ido-segment cards:", sum(1 for c in cards if "-ido-" in c["id"]))
p("idol origin sample:", [(c["id"], c["upgradeCount"], c["originIdolCardId"], c["name"]) for c in idol[:6]])
# upgrade>0 的 originIdolCardId 是否也有
p("idol by upgrade:", collections.Counter(c["upgradeCount"] for c in idol))
# 非 ido 段但有 originIdolCardId？
p("non-ido with origin:", [(c["id"], c["name"]) for c in idol if "-ido-" not in c["id"]][:10])
# ido 段但无 origin？
p("ido without origin:", [(c["id"], c["name"]) for c in cards if "-ido-" in c["id"] and not c.get("originIdolCardId")][:10])

# effect group 表
groups = load("ProduceExamGimmickEffectGroup")
p("\nEffectGroup rows:", len(groups), "keys:", list(groups[0].keys()))
for g in groups:
    gid = g.get("id","")
    if "visible-exam_concentration" in gid or "visible-exam_full_power" in gid:
        p(json.dumps(g, ensure_ascii=False)[:500])
con.close()

# 参考引擎 skillCards.js 的 sourceType
ref = open(r"D:\Games\gakumas-agent\data\dl\gt\gakumas-tools-master\packages\gakumas-data\data\skillCards.js", encoding="utf-8").read()
p("\nskillCards.js head:", ref[:300])
p("pIdol occurrences:", ref.count('"pIdol"') + ref.count("pIdol"))

# card_table 里 effect_group 过滤命中
ct = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\card_table.json", encoding="utf-8"))["cards"]
token_map = {
    "exam_concentration": "ExamConcentration",
    "exam_lesson_buff": "ExamLessonBuff",
    "exam_stamina_consumption_down": "ExamStaminaConsumptionDown",
    "exam_parameter_buff_multiple_per_turn": "ExamParameterBuffMultiplePerTurn",
    "exam_full_power": "ExamFullPower",
    "exam_preservation": "ExamPreservation",
}
for token, eff in token_map.items():
    hits = [n for n,r in ct.items() if any(e.get("type")==eff for e in r.get("effects") or [])]
    p(f"\n{token} -> {eff}: {len(hits)} cards, e.g. {hits[:6]}")
out.close()
print("written")