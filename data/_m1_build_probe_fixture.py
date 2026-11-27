"""M1 probe fixture 构建（脚本不提交；产物 tests/fixtures/m1_probe_p1.json 提交）。
从 data/_engine_probe_rng_p1.jsonl 抽取消费图回归所需的逐动作黄金数据。
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CREATORS = {"p_card-01-men-2_099": 1, "p_card-01-men-2_098": 1, "p_card-01-men-2_110": 0,
            "p_card-03-act-2_102": 0, "p_card-03-men-2_112": 3, "p_card-03-men-2_103": 2}
ZERO_MECH = {"ExamSearchPlayCardStaminaConsumptionChange", "ExamCardSearchEffectPlayCountBuff"}

rows = [json.loads(l) for l in open(ROOT / "data/_engine_probe_rng_p1.jsonl", encoding="utf-8")]
steps = [r for r in rows if r["kind"] == "step"]

create_events = []
for r in steps:
    pid = r["played"]
    if pid in CREATORS and r.get("deck_inserted"):
        draws = CREATORS[pid]
        for ins in r["deck_inserted"]:
            if ins["card"] == "p_card-00-acc-0_002":
                pred = next((p for p in r.get("insert_pred", []) if p["card"] == ins["card"] and p["index"] == ins["index"]), {})
                create_events.append({
                    "tag": r["tag"], "i": r["i"], "played": pid, "rng_before": r["rng_before"],
                    "deck_len_before": r["deck_len_before"], "draws_before_create": draws,
                    "index": ins["index"], "pred_steps": pred.get("pred_steps", []),
                    "consumption": r["consumption"],
                })

# 重洗：nosup skip 局（support=0），消费 = 弃手牌后 grave - 1
reshuffle_events = []
for r in steps:
    if r["policy"] == "skip" and r["strip_supports"]:
        ob, oa = r["obs_before"], r["obs_after"]
        grave_reset = oa["grave_count"] == 0 and ob["grave_count"] > 0
        discard = len(r["hand_before"])  # skip 不出牌，回合末手牌全弃
        grave_count = ob["grave_count"] + discard
        reshuffle_events.append({
            "tag": r["tag"], "i": r["i"], "grave_before": ob["grave_count"],
            "hand_before": len(r["hand_before"]), "grave_count_after_discard": grave_count,
            "grave_reset": grave_reset, "consumption": r["consumption"],
            "expected_cons": (grave_count - 1) if grave_reset else 0,
        })

# 034 移动（search random + pick all）：cons = 2nf（无抽牌/无回合转换的纯移动步）
move_events = []
for r in steps:
    if r["played"] == "p_card-01-men-3_034":
        ob, oa = r["obs_before"], r["obs_after"]
        move_events.append({
            "tag": r["tag"], "i": r["i"], "consumption": r["consumption"],
            "turn_changed": oa["turn"] > ob["turn"],
            "deck_len_before": r["deck_len_before"], "grave_before": ob["grave_count"],
            "deck_inserted": r.get("deck_inserted", []),
        })

# 0 RNG 机制步（type59/38 等确定式变体）
zero_steps = []
for r in steps:
    if r["played_mech"] and set(r["played_mech"]) <= ZERO_MECH and r["consumption"] == 0:
        zero_steps.append({"tag": r["tag"], "i": r["i"], "played": r["played"],
                           "mech": r["played_mech"], "consumption": 0})

# 全步原语核对
all_steps = [{"tag": r["tag"], "i": r["i"], "rng_before": r["rng_before"],
              "rng_after": r["rng_after"], "consumption": r["consumption"]} for r in steps]

out = {"create_events": create_events, "reshuffle_events": reshuffle_events,
       "move_events": move_events, "zero_steps": zero_steps, "all_steps": all_steps,
       "n_steps": len(steps)}
p = ROOT / "tests/fixtures/m1_probe_p1.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved", p)
print("create", len(create_events), "reshuffle", len(reshuffle_events), "move", len(move_events),
      "zero", len(zero_steps), "all", len(all_steps))
# 自检
for c in create_events:
    idx = ((c["rng_before"] * (c["deck_len_before"] - c["draws_before_create"])) >> 32)
    assert idx == c["index"], (c["tag"], c["i"], idx, c["index"])
    assert 0 in c["pred_steps"], (c["tag"], c["i"])
for e in reshuffle_events:
    assert e["consumption"] == e["expected_cons"], (e["tag"], e["i"], e["consumption"], e["expected_cons"])
print("create insertion + reshuffle self-check OK")
