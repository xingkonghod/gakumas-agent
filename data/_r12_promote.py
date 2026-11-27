"""r12 过门入库（降档 15→0，单变量=去掉 v1 示范）：把 out/ei_r12_v12_mix.json
逐权重拷进入库位 data/knowledge/ei_policy_v6.json（engine=net 管道模型无关，
换文件即生效），meta.production 补 r12 溯源。**程序化门校验**：任一条件不满足
直接退出、不动入库文件（生产保持 r11）。

r12 目的（用户选定 A）：small 显著超 v6（r11 small 学生改进中性 +0.008，恢复到
v6 而非超越）。**预注册门（比 r11 复合门更严：small 要显著正，不是「不回退」）**：

前置（参照臂逐位校验，先信数字再谈门）：
0. r12 small500/large500 的 teacher_net(v6)/beam_analytic/greedy 臂 ==
   ei_r11_ref_{small,large}_r9v6.json 同臂（v6 net 确定性 + idle 负载下
   beam/greedy 确定性 → 排除 harness 漂移）。

门（500 局 seed3000–3499，B1 修正 harness 配对，--no-within）：
1. large500 r12−v6 配对 CI 下界 > 0（large 主门保持）；
2. small500 r12−v6 CI **下界 > 0**（**显著超 v6——本轮目的**；r11 护栏是上界≥0，
   r12 若只是中性则相对 r11 无增益，不入库）；
3. small500 r12−v1 CI 下界 > 0（原 500 局门保持，v1 取 ei_r11_ref_small_r10v1
   的 teacher_net，新规则参照）；
4. large500 r12−r11 CI **上界 ≥ 0**（不显著回退当前生产 r11；r11 取
   ei_r11_eval_v11_large500 的 net 臂，同 seed 跨 JSON 配对）。

另报（不门）：small500 r12−r11（相对当前生产的学生改进）。
规则口径自 r11 后未变（本会话无规则改动）→ r12−r11 = 纯学生变化，无规则分移。

用法：.venv\\Scripts\\python.exe data\\_r12_promote.py
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


def check_refs(r12_small: dict, r12_large: dict) -> bool:
    """参照臂逐位校验（新规则参照 ei_r11_ref_*_r9v6，v6 net 确定性）。"""
    ref_small = load("ei_r11_ref_small_r9v6.json")
    ref_large = load("ei_r11_ref_large_r9v6.json")
    ok = True
    for arm in ("teacher_net", "beam_analytic", "greedy"):
        a, b = scores(r12_small, arm), scores(ref_small, arm)
        same = a == b
        ok &= same
        print(f"参照 small500 {arm}: {'逐位一致 ✅' if same else '不一致 ❌'}（{len(a)} 局）")
    for arm in ("teacher_net", "beam_analytic", "greedy"):
        a, b = scores(r12_large, arm), scores(ref_large, arm)
        same = a == b
        ok &= same
        print(f"参照 large500 {arm}: {'逐位一致 ✅' if same else '不一致 ❌'}（{len(a)} 局）")
    return ok


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r12_small = load("ei_r12_eval_v12_small500.json")
    r12_large = load("ei_r12_eval_v12_large500.json")
    ref_small_v1 = load("ei_r11_ref_small_r10v1.json")  # teacher_net = v1（新规则）
    r11_small = load("ei_r11_eval_v11_small500.json")   # net = r11（当前生产）
    r11_large = load("ei_r11_eval_v11_large500.json")

    if not check_refs(r12_small, r12_large):
        print("❌ 参照臂逐位校验未过 → 数字不可信，不入库（先查 harness/负载，idle 复跑）")
        return 1

    lg_mean, lg_lo, lg_hi = delta(scores(r12_large, "net"), scores(r12_large, "teacher_net"))
    sm_mean, sm_lo, sm_hi = delta(scores(r12_small, "net"), scores(r12_small, "teacher_net"))
    v1_mean, v1_lo, v1_hi = delta(scores(r12_small, "net"), scores(ref_small_v1, "teacher_net"))
    lgr11_mean, lgr11_lo, lgr11_hi = delta(scores(r12_large, "net"), scores(r11_large, "net"))
    smr11_mean, smr11_lo, smr11_hi = delta(scores(r12_small, "net"), scores(r11_small, "net"))

    print(f"large500 r12−v6:  Δ={lg_mean:+.3f} CI[{lg_lo:+.3f},{lg_hi:+.3f}]（主门：下界>0）")
    print(f"small500 r12−v6:  Δ={sm_mean:+.3f} CI[{sm_lo:+.3f},{sm_hi:+.3f}]（本轮目的：下界>0 显著超 v6）")
    print(f"small500 r12−v1:  Δ={v1_mean:+.3f} CI[{v1_lo:+.3f},{v1_hi:+.3f}]（原门保持：下界>0）")
    print(f"large500 r12−r11: Δ={lgr11_mean:+.3f} CI[{lgr11_lo:+.3f},{lgr11_hi:+.3f}]（生产护栏：上界>=0）")
    print(f"small500 r12−r11: Δ={smr11_mean:+.3f} CI[{smr11_lo:+.3f},{smr11_hi:+.3f}]（参考，不门）")

    if not lg_lo > 0:
        print("❌ large 主门未过 → 不入库（如实记录负结果，生产保持 r11）")
        return 1
    if not sm_lo > 0:
        print("❌ small 未显著超 v6（本轮目的未达）→ 不入库（中性/负结果如实记录，生产保持 r11）")
        return 1
    if not v1_lo > 0:
        print("❌ small 原门（vs v1）未保持 → 不入库")
        return 1
    if lgr11_hi < 0:
        print("❌ large 相对当前生产 r11 显著回退 → 不入库（不拿 large 换 small）")
        return 1

    src = OUT / "ei_r12_v12_mix.json"
    model = PolicyMLP.load(src)  # 格式/维度/隐层校验
    doc = json.loads(src.read_text(encoding="utf-8"))
    lg_net = r12_large["results"]["unknown"]["net"]
    lg_base = r12_large["results"]["unknown"]["teacher_net"]
    lg_beam = r12_large["results"]["unknown"]["beam_analytic"]
    sm_net = r12_small["results"]["unknown"]["net"]
    sm_base = r12_small["results"]["unknown"]["teacher_net"]
    doc["meta"]["production"] = {
        "name": "ei_policy_v6",
        "revision": "r12-teacher-free (2026-11-24)",
        "tracked_path": "data/knowledge/ei_policy_v6.json",
        "source": "out/ei_r12_v12_mix.json",
        "gate": (
            f"large500 seed3000-3499 (new-rule baseline): r12 {lg_net['mean']:.1f} vs v6 {lg_base['mean']:.1f}, "
            f"{lg_mean:+.2f} CI[{lg_lo:+.2f},{lg_hi:+.2f}] PASS; "
            f"small500 r12 {sm_net['mean']:.1f} vs v6 {sm_base['mean']:.1f}, {sm_mean:+.2f} CI[{sm_lo:+.2f},{sm_hi:+.2f}] significant-positive; "
            f"small500 vs v1 {v1_mean:+.2f} CI[{v1_lo:+.2f},{v1_hi:+.2f}] gate-held; "
            f"large500 vs r11 {lgr11_mean:+.2f} CI[{lgr11_lo:+.2f},{lgr11_hi:+.2f}] no-regression"
        ),
        "large_vs_beam": (
            f"r12 {lg_net['mean']:.1f} vs beam {lg_beam['mean']:.1f} "
            f"({lg_net['mean'] - lg_beam['mean']:+.1f}) on large500 (new rules)"
        ),
        "supersedes": (
            "r11 weights (small+large double-pass: large +26.10 CI[+23.06,+29.14], small +0.008 no-regression); "
            "r12 small significantly exceeds v6 (purpose of round)"
        ),
        "change": (
            "single variable vs r11: teacher-frac 0.15->0 (drop v1 demos, pure selfplay); "
            "same stage-2 new-rule data (v6 selfplay small 10000 games seed1100000+ / large 5000 games seed1200000+); "
            "192x96 / 1200ep / --norm-by-scenario --upsample-small 2; small energy 65.6%->~69.4%"
        ),
        "rule_calibration": (
            "rules unchanged since r11 (no rule edits this session); reference arms v6/beam/greedy "
            "bit-identical to ei_r11_ref_* (6/6); r12-r11 = pure student change, zero rule shift"
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
