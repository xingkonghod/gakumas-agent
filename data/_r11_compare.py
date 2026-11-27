"""P2-1b 一次性：新旧对比——分清「规则分移」与「学生改进」。不提交。

同 seed 段（small/large 500 局 3000–3499）配对：
* 规则分移 rule_shift(M) = M_新规则 − M_旧规则（旧模型在新 sim 下也变）；
* 学生改进 student_gain = r11_新规则 − v6_新规则（同新规则，纯学生差异）；
* 分解：r11_新 − v6_旧 = (r11_新 − v6_新) + (v6_新 − v6_旧) = 学生改进 + 规则分移(v6)。

旧规则 JSON：ei_r6_eval_v6_confirm500（small v6/v1）、ei_r9/r10_eval_*500。
新规则 JSON：ei_r11_ref_*（v6/v1/r9/r10）、ei_r11_eval_v11_*500（r11）。
"""
import json
import statistics as st
import sys

sys.path.insert(0, "scripts")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from eval_t4_b1 import _paired_ci


def load(name):
    return json.load(open(f"out/{name}", encoding="utf-8"))


def sc(doc, arm):
    return doc["results"]["unknown"][arm]["scores"]


def paired(a, b):
    m, h = _paired_ci([x - y for x, y in zip(a, b)])
    w = sum(1 for x, y in zip(a, b) if x > y)
    l = sum(1 for x, y in zip(a, b) if x < y)
    t = sum(1 for x, y in zip(a, b) if x == y)
    return m, m - h, m + h, w, t, l


def fmt(label, a, b):
    m, lo, hi, w, t, l = paired(a, b)
    print(f"{label:<26} Δ={m:+8.3f} CI[{lo:+7.3f},{hi:+7.3f}] 胜/平/负={w}/{t}/{l}")
    return m


# ---- 加载 ----
r6s = load("ei_r6_eval_v6_confirm500.json")
r9s_old = load("ei_r9_eval_v9_small500.json")
r10s_old = load("ei_r10_eval_v10_small500.json")
r9l_old = load("ei_r9_eval_v9_large500.json")
r10l_old = load("ei_r10_eval_v10_large500.json")
rs9 = load("ei_r11_ref_small_r9v6.json")
rs10 = load("ei_r11_ref_small_r10v1.json")
rl9 = load("ei_r11_ref_large_r9v6.json")
rl10 = load("ei_r11_ref_large_r10v1.json")
r11s = load("ei_r11_eval_v11_small500.json")
r11l = load("ei_r11_eval_v11_large500.json")

old = {
    "small": {"v6": sc(r6s, "net"), "v1": sc(r6s, "teacher_net"),
              "r9": sc(r9s_old, "net"), "r10": sc(r10s_old, "net")},
    "large": {"v6": sc(r9l_old, "teacher_net"), "r9": sc(r9l_old, "net"),
              "r10": sc(r10l_old, "net")},
}
new = {
    "small": {"v6": sc(rs9, "teacher_net"), "v1": sc(rs10, "teacher_net"),
              "r9": sc(rs9, "net"), "r10": sc(rs10, "net"), "r11": sc(r11s, "net")},
    "large": {"v6": sc(rl9, "teacher_net"), "v1": sc(rl10, "teacher_net"),
              "r9": sc(rl9, "net"), "r10": sc(rl10, "net"), "r11": sc(r11l, "net")},
}

for scenario in ("small", "large"):
    print(f"\n========== {scenario}500（seed3000-3499）==========")
    print("--- 规则分移（旧模型 新规则 − 旧规则）---")
    for m in ("v6", "r9", "r10"):
        if m in old[scenario]:
            fmt(f"rule_shift {m}", new[scenario][m], old[scenario][m])
    print("--- 学生改进（新规则下 r11 vs 旧模型）---")
    for m in ("v6", "r9", "r10"):
        fmt(f"r11 − {m} (new)", new[scenario]["r11"], new[scenario][m])
    print("--- 分解：r11_新 − v6_旧 = 学生改进 + 规则分移(v6) ---")
    total = fmt("r11_new − v6_old", new[scenario]["r11"], old[scenario]["v6"])
    gain = paired(new[scenario]["r11"], new[scenario]["v6"])[0]
    shift = paired(new[scenario]["v6"], old[scenario]["v6"])[0]
    print(f"    学生改进(r11−v6新)={gain:+.3f} + 规则分移(v6)={shift:+.3f} = {gain + shift:+.3f}（核对 total={total:+.3f}）")
    print("--- 绝对水位（新规则）---")
    for m in ("v1", "v6", "r9", "r10", "r11"):
        if m in new[scenario]:
            print(f"    {m:<5} {st.fmean(new[scenario][m]):.3f}")
