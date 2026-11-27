import json
import sys

sys.path.insert(0, "scripts")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from eval_t4_b1 import _paired_ci


def load(n):
    return json.load(open("out/" + n + ".json", encoding="utf-8"))


for f, scn in [("ei_r11_eval_v11_large500", "large"), ("ei_r11_eval_v11_small500", "small")]:
    d = load(f)
    print("===", scn, "===")
    for arm in ["net", "teacher_net", "beam_analytic", "greedy"]:
        s = d["results"]["unknown"][arm]
        print(f"  {arm:<14} mean={s['mean']:.3f} CLEAR={s['clear_rate']*100:.1f}% PERFECT={s['perfect_rate']*100:.1f}%")
    net = d["results"]["unknown"]["net"]["scores"]
    beam = d["results"]["unknown"]["beam_analytic"]["scores"]
    m, h = _paired_ci([a - b for a, b in zip(net, beam)])
    print(f"  r11-beam: {m:+.3f} CI[{m-h:+.3f},{m+h:+.3f}]")

d = load("ei_r11_eval_v11_large_fresh6000")
print("=== large fresh6000 ===")
for arm in ["net", "teacher_net", "beam_analytic"]:
    s = d["results"]["unknown"][arm]
    print(f"  {arm:<14} mean={s['mean']:.3f} CLEAR={s['clear_rate']*100:.1f}%")
net = d["results"]["unknown"]["net"]["scores"]
base = d["results"]["unknown"]["teacher_net"]["scores"]
m, h = _paired_ci([a - b for a, b in zip(net, base)])
print(f"  r11-v6 fresh: {m:+.3f} CI[{m-h:+.3f},{m+h:+.3f}]")
