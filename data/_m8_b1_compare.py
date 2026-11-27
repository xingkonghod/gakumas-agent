"""M8 B1 harness 改前/改后配对 Δ+CI（不提交）。small 60 局 within/beam × unknown/known。"""
import json
import statistics as stats

before = json.load(open("out/_m8_b1_before.json", encoding="utf-8"))["results"]
after = json.load(open("out/_m8_b1_after.json", encoding="utf-8"))["results"]
for info in ("unknown", "known"):
    for pol in ("within", "beam"):
        b = before[info][pol]["scores"]
        a = after[info][pol]["scores"]
        d = [x - y for x, y in zip(a, b)]
        m = stats.mean(d)
        se = stats.stdev(d) / len(d) ** 0.5
        w = sum(1 for x in d if x > 0)
        l = sum(1 for x in d if x < 0)
        t = sum(1 for x in d if x == 0)
        ch = sum(1 for x in d if x != 0)
        print(f"{info:7} {pol:6}: 变化{ch}/60 胜/负/平={w}/{l}/{t} "
              f"Δmean={m:+.2f} CI95=[{m - 1.96 * se:+.2f},{m + 1.96 * se:+.2f}] "
              f"(before {stats.mean(b):.1f} → after {stats.mean(a):.1f})")