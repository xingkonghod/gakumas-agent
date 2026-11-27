"""r13 过门入库（完整渐退协议：教师←r11，占比渐退 0.15→0.075）：把
out/ei_r13_v13_mix.json 逐权重拷进入库位 data/knowledge/ei_policy_v6.json，
meta.production 补 r13 溯源。**程序化门校验**：任一条件不满足直接退出、不动入库
文件（生产保持 r11）。

r13 = 渐退式专家迭代完整一步（用户选定 A）：教师←最新入库学生 r11，采 r11 argmax
新自对弈（small 1400000+ / large 1500000+）+ r11 示范（1600000+），占比渐退
0.15→0.075，配方保持 --norm-by-scenario --upsample-small 2。**门基线换 r11**
（学生要超最新老师，而非 v6）。

前置（参照臂逐位校验）：
0a. r13 small500/large500 的 teacher_net(r11) 臂 == ei_r11_eval_v11_{small,large}500
    的 net 臂（r11 net 确定性，跨 run 逐位一致）；
0b. r13 beam/greedy 臂 == ei_r11_ref_{small,large}_r9v6 同臂（idle 确定性）。

门（composite，500 局 seed3000–3499，基线=r11）：
1. large500 r13−r11 配对 CI 下界 > 0（large 主门：显著超最新老师 r11）；
2. small500 r13−r11 CI 上界 >= 0（small 不回退）；
3. small500 r13−v1 CI 下界 > 0（原门保持，v1 取 ei_r11_ref_small_r10v1 teacher_net）。
目的（报告不门）：small500 r13−r11 CI 下界 > 0（small 显著超最新老师）。

用法：.venv\\Scripts\\python.exe data\\_r13_promote.py
一次性脚本，不提交。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_t4_b1 import _paired_ci
from gkagent.sim.policy_mlp import PolicyMLP

OUT = ROOT / "out"
TRACKED = ROOT / "data" / "knowledge" / "ei_policy_v6.json"


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def scores(doc: dict, arm: str) -> list[float]:
    return doc["results"]["unknown"][arm]["scores"]


def delta(a: list[float], b: list[float]) -> tuple[float, float, float]:
    mean, half = _paired_ci([x - y for x, y in zip(a, b)])
    return mean, mean - half, mean + half


def check_refs(r13_small: dict, r13_large: dict) -> bool:
    r11_small = load("ei_r11_eval_v11_small500.json")
    r11_large = load("ei_r11_eval_v11_large500.json")
    ref_small = load("ei_r11_ref_small_r9v6.json")
    ref_large = load("ei_r11_ref_large_r9v6.json")
    ok = True
    # teacher_net(r11) == r11 eval net
    for tag, r13, r11 in (("small", r13_small, r11_small), ("large", r13_large, r11_large)):
        a, b = scores(r13, "teacher_net"), scores(r11, "net")
        same = a == b
        ok &= same
        print(f"参照 {tag}500 teacher_net(r11)==r11 net: {'逐位一致 ✅' if same else '不一致 ❌'}（{len(a)} 局）")
    # beam/greedy == r11 ref
    for tag, r13, ref in (("small", r13_small, ref_small), ("large", r13_large, ref_large)):
        for arm in ("beam_analytic", "greedy"):
            a, b = scores(r13, arm), scores(ref, arm)
            same = a == b
            ok &= same
            print(f"参照 {tag}500 {arm}: {'逐位一致 ✅' if same else '不一致 ❌'}（{len(a)} 局）")
    return ok


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r13_small = load("ei_r13_eval_v13_small500.json")
    r13_large = load("ei_r13_eval_v13_large500.json")
    ref_small_v1 = load("ei_r11_ref_small_r10v1.json")  # teacher_net = v1（新规则）
    ref_small_v6 = load("ei_r11_ref_small_r9v6.json")   # teacher_net = v6（新规则）
    ref_large_v6 = load("ei_r11_ref_large_r9v6.json")

    if not check_refs(r13_small, r13_large):
        print("❌ 参照臂逐位校验未过 → 数字不可信，不入库（先查 harness/负载，idle 复跑）")
        return 1

    lg_mean, lg_lo, lg_hi = delta(scores(r13_large, "net"), scores(r13_large, "teacher_net"))
    sm_mean, sm_lo, sm_hi = delta(scores(r13_small, "net"), scores(r13_small, "teacher_net"))
    v1_mean, v1_lo, v1_hi = delta(scores(r13_small, "net"), scores(ref_small_v1, "teacher_net"))
    v6s_mean, v6s_lo, v6s_hi = delta(scores(r13_small, "net"), scores(ref_small_v6, "teacher_net"))
    v6l_mean, v6l_lo, v6l_hi = delta(scores(r13_large, "net"), scores(ref_large_v6, "teacher_net"))

    print(f"large500 r13−r11: Δ={lg_mean:+.3f} CI[{lg_lo:+.3f},{lg_hi:+.3f}]（主门：下界>0）")
    print(f"small500 r13−r11: Δ={sm_mean:+.3f} CI[{sm_lo:+.3f},{sm_hi:+.3f}]（护栏：上界>=0；目的：下界>0）")
    print(f"small500 r13−v1:  Δ={v1_mean:+.3f} CI[{v1_lo:+.3f},{v1_hi:+.3f}]（原门保持：下界>0）")
    print(f"small500 r13−v6:  Δ={v6s_mean:+.3f} CI[{v6s_lo:+.3f},{v6s_hi:+.3f}]（绝对水位，报告）")
    print(f"large500 r13−v6:  Δ={v6l_mean:+.3f} CI[{v6l_lo:+.3f},{v6l_hi:+.3f}]（绝对水位，报告）")

    if not lg_lo > 0:
        print("❌ large 主门（r13−r11 下界>0）未过 → 不入库（如实记录，生产保持 r11）")
        return 1
    if sm_hi < 0:
        print("❌ small 显著回退（r13−r11 上界<0）→ 不入库")
        return 1
    if not v1_lo > 0:
        print("❌ small 原门（vs v1）未保持 → 不入库")
        return 1

    src = OUT / "ei_r13_v13_mix.json"
    model = PolicyMLP.load(src)
    doc = json.loads(src.read_text(encoding="utf-8"))
    lg_net = r13_large["results"]["unknown"]["net"]
    lg_base = r13_large["results"]["unknown"]["teacher_net"]
    lg_beam = r13_large["results"]["unknown"]["beam_analytic"]
    sm_net = r13_small["results"]["unknown"]["net"]
    sm_base = r13_small["results"]["unknown"]["teacher_net"]
    doc["meta"]["production"] = {
        "name": "ei_policy_v6",
        "revision": "r13-teacher-r11-gradual-fade (2026-11-24)",
        "tracked_path": "data/knowledge/ei_policy_v6.json",
        "source": "out/ei_r13_v13_mix.json",
        "gate": (
            f"large500 seed3000-3499 (baseline=r11): r13 {lg_net['mean']:.1f} vs r11 {lg_base['mean']:.1f}, "
            f"{lg_mean:+.2f} CI[{lg_lo:+.2f},{lg_hi:+.2f}] PASS; "
            f"small500 r13 {sm_net['mean']:.1f} vs r11 {sm_base['mean']:.1f}, {sm_mean:+.2f} CI[{sm_lo:+.2f},{sm_hi:+.2f}] no-regression; "
            f"small500 vs v1 {v1_mean:+.2f} CI[{v1_lo:+.2f},{v1_hi:+.2f}] gate-held"
        ),
        "large_vs_beam": (
            f"r13 {lg_net['mean']:.1f} vs beam {lg_beam['mean']:.1f} "
            f"({lg_net['mean'] - lg_beam['mean']:+.1f}) on large500 (new rules)"
        ),
        "supersedes": (
            "r11 weights (small+large double-pass vs v6: large +26.10, small +0.008 no-regression); "
            "r13 full fading-iteration step teacher<-r11, large significantly exceeds r11"
        ),
        "change": (
            "full fading expert-iteration step (teacher<-latest student r11): fresh r11 argmax selfplay "
            "small 10000 games seed1400000+ / large 5000 games seed1500000+ + r11 demos 3600 games seed1600000+; "
            "teacher-frac gradual fade 0.15->0.075; gate baseline switched v6->r11; "
            "192x96 / 1200ep / --norm-by-scenario --upsample-small 2 (r11 recipe kept)"
        ),
        "rule_calibration": (
            "rules unchanged since r11; reference arms r11(net)/beam/greedy bit-identical to "
            "ei_r11_eval_v11_*/ei_r11_ref_* (6/6); r13-r11 = pure student change, zero rule shift"
        ),
        "wired": "2026-11-23 engine=net (opt-in; default engines unchanged); file swap, pipeline model-agnostic",
    }
    TRACKED.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    check = PolicyMLP.load(TRACKED)
    import numpy as np
    assert np.array_equal(check.w1, model.w1)
    assert np.array_equal(check.out_w, model.out_w)
    print(f"✅ 入库 {TRACKED}（{TRACKED.stat().st_size} 字节，权重逐位一致）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
