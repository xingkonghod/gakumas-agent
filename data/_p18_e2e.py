# P1-8 端到端探针：天生的才能 apply_passive（不提交）
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\Games\gakumas-agent\src")
from gkagent.sim import p_items as P

data = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\p_items.json", encoding="utf-8"))
recs = {r["id"]: r for r in data["items"]}
s0 = P.record_to_specs(recs["pitem_01-3-346-0"])
s1 = P.record_to_specs(recs["pitem_01-3-346-1"])

ev = P.PassiveEvent(kind=P.CARD_PLAY, card_name="魅力の基本", card_category="ActiveSkill")
def st(pb, hand, known=True):
    return P.PassiveState(turn=1, stacks={"parameter_buff": pb}, hand=hand, zones_known=known)

print("== -0 好調の30%分 ==")
for pb, hand, known in [(10, ("睡意",), True), (10, ("魅力の基本",), True), (10, ("睡意",), False), (0, ("睡意",), True), (7, ("睡意",), True)]:
    d = P.apply_passive(s0, ev, st(pb, hand, known))
    print(f"  pb={pb} hand={hand} known={known} -> score={d.score} applied={d.applied}")
print("== -1 元気+1 好調の50%分 ==")
for pb, hand in [(10, ("睡意",)), (10, ("魅力の基本",))]:
    d = P.apply_passive(s1, ev, st(pb, hand))
    print(f"  pb={pb} hand={hand} -> score={d.score} stacks={d.stacks} applied={d.applied}")
# 日文别名 眠気 也应命中
d = P.apply_passive(s0, ev, st(10, ("眠気",)))
print("  眠気(ja alias) hand -> score=", d.score)