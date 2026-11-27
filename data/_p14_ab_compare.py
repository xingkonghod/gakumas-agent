"""P1-4 一次性对照：sim_engine_ab 改前/改后 64 局逐局非时间字段对照（不提交）。

P1-4 nullifyDebuff 来源（偷懒的毛巾 P 道具 + 塔 gimmick + 4 SSR 卡族）评测零落点
（gkbench loadout 0 命中、build_pool 无 ExamAntiDebuff 卡）→ 预期改前/改后逐位相同
（同 P1-1/P1-2）。本脚本逐局报告差异字段 + 评价点配对 Δ（rules/expectimax 各自）。
"""
import json
import statistics as stats
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
    before = load(f"out/_p14_ab_before_{seed}.json")
    after = load(f"out/_p14_ab_after_{seed}.json")
    b_rows = {(e, r["seed"]): r for e, rows in before["rows"].items() for r in rows}
    a_rows = {(e, r["seed"]): r for e, rows in after["rows"].items() for r in rows}
    assert set(b_rows) == set(a_rows), f"seed {seed}: 局集合不一致"
    for key in sorted(b_rows):
        total += 1
        b = strip_time(b_rows[key])
        a = strip_time(a_rows[key])
        if b != a:
            fields = [k for k in b if b.get(k) != a.get(k)]
            diffs.append((seed, key, fields))
    for engine in ("rules", "expectimax"):
        deltas = [
            a_rows[(engine, s)]["eval"] - b_rows[(engine, s)]["eval"]
            for s in range(seed, seed + 16)
        ]
        changed = sum(1 for d in deltas if d != 0)
        wins = sum(1 for d in deltas if d > 0)
        losses = sum(1 for d in deltas if d < 0)
        mean = stats.mean(deltas)
        se = stats.stdev(deltas) / len(deltas) ** 0.5 if len(deltas) > 1 else 0.0
        print(
            f"seed {seed} {engine}: 变化 {changed}/16（胜{wins}/负{losses}）"
            f" Δmean={mean:+.1f} CI95=[{mean - 1.96 * se:+.1f},{mean + 1.96 * se:+.1f}]"
        )
    for label, data in (("before", before), ("after", after)):
        rows = [r for rows in data["rows"].values() for r in rows]
        blocked = sum(1 for r in rows if r["blocked"])
        errors = sum(1 for r in rows if r["error"])
        cplus = sum(1 for r in rows if (r["eval"] or 0) >= 4500) / len(rows)
        print(f"seed {seed} {label}: blocked={blocked} error={errors} C+率={cplus:.3f}")

print(f"\n逐局对照: {total} 局（seed 9000/9100 各 16 局 × rules/expectimax）")
print(f"差异 {len(diffs)} 处:")
for d in diffs[:40]:
    print(" ", d)
