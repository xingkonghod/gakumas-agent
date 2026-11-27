# P1-8 探针3：の%分 / 日文换算源盘点（不提交）
import json, collections, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
data = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\p_items.json", encoding="utf-8"))
items = data["items"]

print("===== 所有 effect text 含 'の%分' 或 '%分' 的段 =====")
cnt = collections.Counter()
for rec in items:
    for eff in rec.get("effects", []):
        txt = eff.get("text", "")
        if "%分" in txt or "の%" in txt:
            cnt[txt] += 1
            print(f"  {rec['id']} | {rec['name']} | type={eff.get('type')} | values={eff.get('values')} | text={txt!r} | role={eff.get('role','')} | depends_on={eff.get('depends_on','')}")
print("\ntext 计数:", dict(cnt))

# 检查 天生的才能 当前 implemented 状态（用 sim 的 PItemSpec）
print("\n===== 天生的才能 spec 现状 =====")
sys.path.insert(0, r"D:\Games\gakumas-agent\src")
from gkagent.sim import p_items as P
# 找 record_to_specs 等价：build_p_items 里有 record_to_specs? 检查
for rec in items:
    if rec["id"].startswith("pitem_01-3-346"):
        specs = P.record_to_specs(rec)
        for s in specs:
            print(f"  spec: effect={s.effect_type} target={s.target!r} value={s.value} depends_on={s.depends_on!r} percent={s.percent} implemented={s.implemented} trig={s.trigger} zone_count={s.zone_count} cond_known={s.condition_known} trig_known={s.trigger_known}")
print("\n全局 summarize:", {k: P.summarize(P.load_p_items())[k] for k in ("specs","implemented","noop","depends_on_specs")})