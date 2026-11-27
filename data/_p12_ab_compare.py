"""P1-2 一次性对照：sim_engine_ab 改前/改后 64 局逐局非时间字段全等校验（不提交）。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TIME_KEYS = {
    "seconds", "mean_seconds", "max_seconds", "elapsed_ms", "elapsed",
    "wall_seconds", "duration_ms", "ms", "decision_ms", "search_ms",
}


def load(path):
    return json.load(open(path, encoding="utf-8"))


def strip_time(obj):
    if isinstance(obj, dict):
        return {k: strip_time(v) for k, v in obj.items() if k not in TIME_KEYS}
    if isinstance(obj, list):
        return [strip_time(v) for v in obj]
    return obj


total = 0
diffs = []
for seed in (9000, 9100):
    before = load(f"out/_p12_ab_before_{seed}.json")
    after = load(f"out/_p12_ab_after_{seed}.json")
    b_rows = {
        (engine, r["seed"]): r
        for engine, rows in before["rows"].items()
        for r in rows
    }
    a_rows = {
        (engine, r["seed"]): r
        for engine, rows in after["rows"].items()
        for r in rows
    }
    assert set(b_rows) == set(a_rows), f"seed {seed}: 局集合不一致"
    for key in sorted(b_rows):
        total += 1
        b = strip_time(b_rows[key])
        a = strip_time(a_rows[key])
        if b != a:
            fields = [k for k in b if b.get(k) != a.get(k)]
            diffs.append((seed, key, fields))
    # summary 也对照（去时间）
    if strip_time(before["summary"]) != strip_time(after["summary"]):
        diffs.append((seed, "summary", "summary"))

print(f"逐局对照: {total} 局（seed 9000/9100 各 16 局 × rules/expectimax）")
if diffs:
    print(f"差异 {len(diffs)} 处:")
    for d in diffs[:20]:
        print(" ", d)
    raise SystemExit(1)
print("差异 = 0：改前/改后逐局非时间字段全等 ✅")
