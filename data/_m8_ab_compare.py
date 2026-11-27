"""M8 sim_engine_ab 改前/改后 64 局配对对照（不提交）。

改前 = data/_m8_ab_before.py（monkeypatch 恢复 M8 前 fresh 口径，单变量隔离）；
改后 = scripts/sim_engine_ab.py（通用 fresh 对齐）。seed 9000/9100 各 16 局 × rules/expectimax。
"""
import json
import statistics as stats

TIME_KEYS = {"seconds", "mean_seconds", "max_seconds", "elapsed_ms", "elapsed",
             "wall_seconds", "duration_ms", "ms", "decision_ms", "search_ms"}


def load(p):
    return json.load(open(p, encoding="utf-8"))


def strip_time(o):
    if isinstance(o, dict):
        return {k: strip_time(v) for k, v in o.items() if k not in TIME_KEYS}
    if isinstance(o, list):
        return [strip_time(v) for v in o]
    return o


total = 0
diffs = []
pooled = {"rules": [], "expectimax": []}
for seed in (9000, 9100):
    before = load(f"out/_m8_ab_before_{seed}.json")
    after = load(f"out/_m8_ab_after_{seed}.json")
    b = {(e, r["seed"]): r for e, rows in before["rows"].items() for r in rows}
    a = {(e, r["seed"]): r for e, rows in after["rows"].items() for r in rows}
    assert set(b) == set(a)
    for key in sorted(b):
        total += 1
        if strip_time(b[key]) != strip_time(a[key]):
            fields = [k for k in b[key] if b[key].get(k) != a[key].get(k)]
            diffs.append((seed, key, fields))
    for engine in ("rules", "expectimax"):
        d = [a[(engine, s)]["eval"] - b[(engine, s)]["eval"] for s in range(seed, seed + 16)]
        pooled[engine].extend(d)
        ch = sum(1 for x in d if x != 0)
        w = sum(1 for x in d if x > 0)
        l = sum(1 for x in d if x < 0)
        m = stats.mean(d)
        se = stats.stdev(d) / len(d) ** 0.5 if len(d) > 1 else 0.0
        print(f"seed {seed} {engine}: 变化 {ch}/16（胜{w}/负{l}）Δmean={m:+.1f} "
              f"CI95=[{m - 1.96 * se:+.1f},{m + 1.96 * se:+.1f}]")

print(f"\n逐局对照 {total} 局，非时间字段差异 {len(diffs)} 处")
for engine in ("rules", "expectimax"):
    d = pooled[engine]
    m = stats.mean(d)
    se = stats.stdev(d) / len(d) ** 0.5
    w = sum(1 for x in d if x > 0)
    l = sum(1 for x in d if x < 0)
    t = sum(1 for x in d if x == 0)
    print(f"池化 {engine}（32 局）: Δmean={m:+.1f} CI95=[{m - 1.96 * se:+.1f},{m + 1.96 * se:+.1f}] "
          f"胜/负/平={w}/{l}/{t}")
for seed in (9000, 9100):
    after = load(f"out/_m8_ab_after_{seed}.json")
    rows = {(e, r["seed"]): r for e, rr in after["rows"].items() for r in rr}
    for engine in ("rules", "expectimax"):
        vals = [rows[(engine, s)]["eval"] for s in range(seed, seed + 16)]
        print(f"seed {seed} {engine} 改后绝对水位 mean={stats.mean(vals):.1f}")