"""r11 过门入库：把 out/ei_r11_v11_mix.json 逐权重拷进入库位
data/knowledge/ei_policy_v6.json（engine=net 管道模型无关，换文件即生效），
meta.production 补 r11 溯源。**程序化门校验**：任一条件不满足直接退出、不动入库文件。

阶段2 新规则口径（P1-1…P1-8 后，HEAD 13ee719）：旧 98.6/98.1/305.3 是旧规则口径，
门基线改用**新规则重评值**（data/_r11_ref_summary.py）：
  small500 v6=98.640 / v1=98.062（规则零分移）；large500 v6=287.818 / beam=301.612。

前置（参照臂逐位校验，先信数字再谈门）：
0a. r11 small500/large500 的 teacher_net(v6) 臂 == 新规则参照 ref_*_r9v6 的 teacher_net
    （v6 net 确定性，跨 run 逐位一致 → 排除 harness 漂移）；
0b. r11 small500/large500 的 beam/greedy 臂 == 新规则参照同臂（idle 负载下确定性）。

门（r3–r8 修正口径，500 局；同 data/_r10_promote.py，基线换新规则值）：
1. large500（3000–3499）r11−v6 配对 CI 下界 > 0（large 显著改善，主门）；
2. small500（3000–3499）r11−v6 CI 上界 >= 0（不显著回退）；
3. small500 r11−v1 CI 下界 > 0（原 500 局门保持，跨 JSON 同 seed 配对，
   v1 取新规则参照 ref_small_r10v1 的 teacher_net）。

用法：.venv\\Scripts\\python.exe data\\_r11_promote.py
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


def check_refs(r11_small: dict, r11_large: dict) -> bool:
    """参照臂逐位校验（新规则参照 ref_*_r9v6，v6 net 确定性）。"""
    ref_small = load("ei_r11_ref_small_r9v6.json")
    ref_large = load("ei_r11_ref_large_r9v6.json")
    ok = True
    for arm in ("teacher_net", "beam_analytic", "greedy"):
        a, b = scores(r11_small, arm), scores(ref_small, arm)
        same = a == b
        ok &= same
        print(f"参照 small500 {arm}: {'逐位一致 ✅' if same else '不一致 ❌'}（{len(a)} 局）")
    for arm in ("teacher_net", "beam_analytic", "greedy"):
        a, b = scores(r11_large, arm), scores(ref_large, arm)
        same = a == b
        ok &= same
        print(f"参照 large500 {arm}: {'逐位一致 ✅' if same else '不一致 ❌'}（{len(a)} 局）")
    return ok


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r11_small = load("ei_r11_eval_v11_small500.json")
    r11_large = load("ei_r11_eval_v11_large500.json")
    ref_small_v1 = load("ei_r11_ref_small_r10v1.json")  # teacher_net = v1（新规则）

    if not check_refs(r11_small, r11_large):
        print("❌ 参照臂逐位校验未过 → 数字不可信，不入库（先查 harness/负载）")
        return 1

    lg_mean, lg_lo, lg_hi = delta(scores(r11_large, "net"), scores(r11_large, "teacher_net"))
    sm_mean, sm_lo, sm_hi = delta(scores(r11_small, "net"), scores(r11_small, "teacher_net"))
    v1_mean, v1_lo, v1_hi = delta(scores(r11_small, "net"), scores(ref_small_v1, "teacher_net"))

    print(f"large500 r11−v6: Δ={lg_mean:+.3f} CI[{lg_lo:+.3f},{lg_hi:+.3f}]（主门：下界>0）")
    print(f"small500 r11−v6: Δ={sm_mean:+.3f} CI[{sm_lo:+.3f},{sm_hi:+.3f}]（护栏：上界>=0）")
    print(f"small500 r11−v1: Δ={v1_mean:+.3f} CI[{v1_lo:+.3f},{v1_hi:+.3f}]（原门保持：下界>0）")

    if not lg_lo > 0:
        print("❌ large 主门未过 → 不入库（如实记录负结果）")
        return 1
    if sm_hi < 0:
        print("❌ small 显著回退 → 不入库")
        return 1
    if not v1_lo > 0:
        print("❌ small 原门（vs v1）未保持 → 不入库")
        return 1

    src = OUT / "ei_r11_v11_mix.json"
    model = PolicyMLP.load(src)  # 格式/维度/隐层校验
    doc = json.loads(src.read_text(encoding="utf-8"))
    lg_net = r11_large["results"]["unknown"]["net"]
    lg_base = r11_large["results"]["unknown"]["teacher_net"]
    lg_beam = r11_large["results"]["unknown"]["beam_analytic"]
    sm_net = r11_small["results"]["unknown"]["net"]
    sm_base = r11_small["results"]["unknown"]["teacher_net"]
    doc["meta"]["production"] = {
        "name": "ei_policy_v6",
        "revision": "r11-new-rules-upsample-small (2026-11-24)",
        "tracked_path": "data/knowledge/ei_policy_v6.json",
        "source": "out/ei_r11_v11_mix.json",
        "gate": (
            f"large500 seed3000-3499 (new-rule baseline): r11 {lg_net['mean']:.1f} vs v6 {lg_base['mean']:.1f}, "
            f"{lg_mean:+.2f} CI[{lg_lo:+.2f},{lg_hi:+.2f}] PASS; "
            f"small500 r11 {sm_net['mean']:.1f} vs v6 {sm_base['mean']:.1f}, {sm_mean:+.2f} CI[{sm_lo:+.2f},{sm_hi:+.2f}] no-regression; "
            f"small500 vs v1 {v1_mean:+.2f} CI[{v1_lo:+.2f},{v1_hi:+.2f}] gate-held"
        ),
        "large_vs_beam": (
            f"r11 {lg_net['mean']:.1f} vs beam {lg_beam['mean']:.1f} "
            f"({lg_net['mean'] - lg_beam['mean']:+.1f}) on large500 (new rules)"
        ),
        "supersedes": (
            "r6 weights (old-rule small gate v6 98.6 vs v1 98.1 +0.6 CI[+0.2,+0.9]; large120 291.6); "
            "r9/r10 not promoted (small regression under old rules)"
        ),
        "change": (
            "stage-2 new-rule resample (P1-1..P1-8): v6 selfplay small 10000 games seed1100000+ "
            "+ large 5000 games seed1200000+ + v1 demos 3600 games seed1300000+; "
            "single variable vs r10 recipe: --upsample-small 2 (small energy ->~66%) "
            "+ --norm-by-scenario; 192x96 / 1200ep / teacher v1@0.15 (base pool)"
        ),
        "rule_calibration": (
            "sim_engine_ab seed9000/9100 bit-identical to P1-8 (expectimax-rules +372.2/+219.1); "
            "reference re-eval: small rule-shift 0.000 (all arms), large v6 +1.982 / r9 -1.978 / "
            "r10 -1.278 / beam +0.344; gate baselines re-set to new-rule values"
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
