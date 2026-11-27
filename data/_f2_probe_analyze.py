"""一次性分析：汇总探针采集的真实 UIObs，验证 status/stance/playable 口径。"""
import json
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path(r"D:\Games\gakumas-agent\data\_f2_probe_obs.jsonl")
status_stats = defaultdict(list)
stance_counter = Counter()
legal_kinds = Counter()
playable_rel = Counter()
metas = []
n_steps = 0
n_begin = 0
select_examples = []
v_counter = Counter()
drink_ids = Counter()
hand_p_vs_legal = Counter()
for line in SRC.read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    if row["kind"] == "begin":
        n_begin += 1
        metas.append(row.get("meta") or {})
        continue
    n_steps += 1
    obs = row["obs"]
    v_counter[obs.get("v")] += 1
    for s in obs.get("status") or []:
        status_stats[s[0]].append((s[1], s[2]))
    st = obs.get("stance") or [None, 0]
    stance_counter[(str(st[0]), st[1] if len(st) > 1 else None)] += 1
    num = obs.get("num") or {}
    playable_rel[(num.get("playable"), num.get("plays"))] += 1
    for a in obs.get("legal") or []:
        legal_kinds[a[0]] += 1
        if a[0] == "select" and len(select_examples) < 3:
            select_examples.append(a)
    for d in obs.get("drinks") or []:
        drink_ids[d] += 1
    legal_play = {a[1] for a in obs.get("legal") or [] if a[0] == "play"}
    for i, c in enumerate(obs.get("hand") or []):
        hand_p_vs_legal[(c.get("p"), i in legal_play)] += 1

print(f"begins(episodes)={n_begin} steps={n_steps} v={dict(v_counter)}")
print("\n== status kinds (count, value min/max, turns min/max) ==")
for k, vs in sorted(status_stats.items()):
    vals = [v for v, t in vs]
    turns = [t for v, t in vs]
    print(f"{k:38s} n={len(vs):6d} val=[{min(vals):g},{max(vals):g}] turns=[{min(turns)},{max(turns)}]")
print("\n== stance ==", dict(stance_counter))
print("\n== legal kinds ==", dict(legal_kinds))
print("select examples:", select_examples)
print("\n== (playable, plays) top20 ==")
for k, n in playable_rel.most_common(20):
    print(k, n)
print("\n== hand p vs legal ==", dict(hand_p_vs_legal))
print("\n== drinks ==", dict(drink_ids))
print("\n== meta keys ==", sorted({k for m in metas for k in m}))
print("score_cap values:", Counter(str(m.get("score_cap")) for m in metas))
print("rival example:", json.dumps(metas[0].get("rival_scores"), ensure_ascii=False) if metas else None)
# 样例：含 review_multiple / full_power_lesson_multiple_add / lesson_parameter_multiple 的原始行
print("\n== raw examples of layer statuses ==")
seen = set()
for line in SRC.read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    if row["kind"] != "step":
        continue
    for s in row["obs"].get("status") or []:
        if s[0] in ("review_multiple", "full_power_lesson_multiple_add", "lesson_parameter_multiple",
                    "parameter_buff_gain_fix", "lesson_debuff", "slump", "lesson_buff_multiple",
                    "review_count_add", "concentration_lesson_multiple_add", "enthusiastic",
                    "parameter_buff_multiple", "stance_lock", "card_draw_down", "extra_turn"):
            if s[0] not in seen:
                seen.add(s[0])
                print(s)