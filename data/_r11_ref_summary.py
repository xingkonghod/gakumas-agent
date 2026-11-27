"""P2 一次性：参照臂新规则重评汇总 + 规则分移（vs 旧规则 JSON）。不提交。

新规则参照（HEAD 13ee719，P1-1…P1-8 后）：
  ref_small_r9v6: net=r9 / teacher_net=v6 / beam / greedy
  ref_small_r10v1: net=r10 / teacher_net=v1 / beam / greedy
  ref_large_*: 同。
旧规则参照：ei_r6_eval_v6_confirm500（small v6/v1）、ei_r9/r10_eval（small/large）。
"""
import json
import statistics as st
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(name):
    return json.load(open(f"out/{name}", encoding="utf-8"))


def mean(doc, arm):
    return st.fmean(doc["results"]["unknown"][arm]["scores"])


def scores(doc, arm):
    return doc["results"]["unknown"][arm]["scores"]


rs9 = load("ei_r11_ref_small_r9v6.json")
rs10 = load("ei_r11_ref_small_r10v1.json")
rl9 = load("ei_r11_ref_large_r9v6.json")
rl10 = load("ei_r11_ref_large_r10v1.json")

print("=== 新规则参照臂均值（500 局 seed3000-3499）===")
print(f"{'arm':<10}{'small':>10}{'large':>10}")
for label, sarm, larm in [
    ("v6", ("teacher_net", rs9), ("teacher_net", rl9)),
    ("v1", ("teacher_net", rs10), ("teacher_net", rl10)),
    ("r9", ("net", rs9), ("net", rl9)),
    ("r10", ("net", rs10), ("net", rl10)),
    ("beam", ("beam_analytic", rs9), ("beam_analytic", rl9)),
    ("greedy", ("greedy", rs9), ("greedy", rl9)),
]:
    sk, sd = sarm
    lk, ld = larm
    print(f"{label:<10}{mean(sd, sk):>10.3f}{mean(ld, lk):>10.3f}")

print("\n=== beam 臂跨 run 一致性（同 scenario 同 seed，应与 net 模型无关）===")
for sc, a, b in (("small", rs9, rs10), ("large", rl9, rl10)):
    same = scores(a, "beam_analytic") == scores(b, "beam_analytic")
    print(f"{sc} beam A==B: {'逐位一致 ✅' if same else '不一致 ❌（负载/时序）'}")
for sc, a, b in (("small", rs9, rs10), ("large", rl9, rl10)):
    same = scores(a, "greedy") == scores(b, "greedy")
    print(f"{sc} greedy A==B: {'逐位一致 ✅' if same else '不一致 ❌'}")

print("\n=== 规则分移（旧模型 新规则 − 旧规则）===")
# 旧规则 small500: r6 confirm500 net=v6, teacher_net=v1
r6s = load("ei_r6_eval_v6_confirm500.json")
r9s = load("ei_r9_eval_v9_small500.json")
r10s = load("ei_r10_eval_v10_small500.json")
r9l = load("ei_r9_eval_v9_large500.json")
r10l = load("ei_r10_eval_v10_large500.json")
old_small = {
    "v6": mean(r6s, "net"),
    "v1": mean(r6s, "teacher_net"),
    "r9": mean(r9s, "net"),
    "r10": mean(r10s, "net"),
    "beam": mean(r10s, "beam_analytic"),
}
old_large = {
    "v6": mean(r9l, "teacher_net"),
    "r9": mean(r9l, "net"),
    "r10": mean(r10l, "net"),
    "beam": mean(r10l, "beam_analytic"),
    "greedy": mean(r10l, "greedy"),
}
new_small = {
    "v6": mean(rs9, "teacher_net"),
    "v1": mean(rs10, "teacher_net"),
    "r9": mean(rs9, "net"),
    "r10": mean(rs10, "net"),
    "beam": mean(rs9, "beam_analytic"),
}
new_large = {
    "v6": mean(rl9, "teacher_net"),
    "v1": mean(rl10, "teacher_net"),
    "r9": mean(rl9, "net"),
    "r10": mean(rl10, "net"),
    "beam": mean(rl9, "beam_analytic"),
    "greedy": mean(rl9, "greedy"),
}
print(f"{'arm':<8}{'small旧':>9}{'small新':>9}{'Δsmall':>9}{'large旧':>9}{'large新':>9}{'Δlarge':>9}")
for arm in ("v6", "v1", "r9", "r10", "beam", "greedy"):
    os_ = old_small.get(arm)
    ns = new_small.get(arm)
    ol = old_large.get(arm)
    nl = new_large.get(arm)
    ds = f"{ns - os_:+.3f}" if os_ is not None and ns is not None else "—"
    dl = f"{nl - ol:+.3f}" if ol is not None and nl is not None else "—"
    sos = f"{os_:.3f}" if os_ is not None else "—"
    sns = f"{ns:.3f}" if ns is not None else "—"
    sol = f"{ol:.3f}" if ol is not None else "—"
    snl = f"{nl:.3f}" if nl is not None else "—"
    print(f"{arm:<8}{sos:>9}{sns:>9}{ds:>9}{sol:>9}{snl:>9}{dl:>9}")

# 新规则门基线（供 r11 双门）
print("\n=== 新规则门基线（r11 双门用）===")
print(f"large500 v6 = {new_large['v6']:.3f}（主门基线）")
print(f"large500 beam = {new_large['beam']:.3f}（vs beam 参照）")
print(f"small500 v6 = {new_small['v6']:.3f}（不回退护栏基线）")
print(f"small500 v1 = {new_small['v1']:.3f}（原门保持基线）")
