"""r9 过门入库：把 out/ei_r9_v9_mix.json 逐权重拷进入库位
data/knowledge/ei_policy_v6.json（engine=net 管道模型无关，换文件即生效），
meta.production 补 r9 溯源。**程序化门校验**：任一条件不满足直接退出、不动入库文件。

门（r3–r8 修正口径，500 局）：
1. large500（3000–3499）r9−v6 配对 CI 下界 > 0（large 显著改善，主门）；
2. small500（3000–3499）r9−v6 CI 上界 >= 0（不显著回退）；
3. small500 r9−v1 CI 下界 > 0（原 500 局门保持，跨 JSON 同 seed 配对）。

用法：.venv\\Scripts\\python.exe data\\_r9_promote.py
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


def main() -> int:
    r9_small = load("ei_r9_eval_v9_small500.json")
    r9_large = load("ei_r9_eval_v9_large500.json")
    r6_small = load("ei_r6_eval_v6_confirm500.json")

    lg_mean, lg_lo, lg_hi = delta(scores(r9_large, "net"), scores(r9_large, "teacher_net"))
    sm_mean, sm_lo, sm_hi = delta(scores(r9_small, "net"), scores(r9_small, "teacher_net"))
    v1_mean, v1_lo, v1_hi = delta(scores(r9_small, "net"), scores(r6_small, "teacher_net"))

    print(f"large500 r9−v6: Δ={lg_mean:+.3f} CI[{lg_lo:+.3f},{lg_hi:+.3f}]（主门：下界>0）")
    print(f"small500 r9−v6: Δ={sm_mean:+.3f} CI[{sm_lo:+.3f},{sm_hi:+.3f}]（护栏：上界>=0）")
    print(f"small500 r9−v1: Δ={v1_mean:+.3f} CI[{v1_lo:+.3f},{v1_hi:+.3f}]（原门保持：下界>0）")

    if not lg_lo > 0:
        print("❌ large 主门未过 → 不入库（如实记录负结果）")
        return 1
    if sm_hi < 0:
        print("❌ small 显著回退 → 不入库")
        return 1
    if not v1_lo > 0:
        print("❌ small 原门（vs v1）未保持 → 不入库")
        return 1

    src = OUT / "ei_r9_v9_mix.json"
    model = PolicyMLP.load(src)  # 格式/维度/隐层校验
    doc = json.loads(src.read_text(encoding="utf-8"))
    lg_net = r9_large["results"]["unknown"]["net"]
    lg_base = r9_large["results"]["unknown"]["teacher_net"]
    lg_beam = r9_large["results"]["unknown"]["beam_analytic"]
    sm_net = r9_small["results"]["unknown"]["net"]
    doc["meta"]["production"] = {
        "name": "ei_policy_v6",
        "revision": "r9-large (2026-11-23)",
        "tracked_path": "data/knowledge/ei_policy_v6.json",
        "source": "out/ei_r9_v9_mix.json",
        "gate": (
            f"large500 seed3000-3499: r9 {lg_net['mean']:.1f} vs v6 {lg_base['mean']:.1f}, "
            f"{lg_mean:+.2f} CI[{lg_lo:+.2f},{lg_hi:+.2f}] PASS; "
            f"small500 r9 {sm_net['mean']:.1f} vs v6, {sm_mean:+.2f} CI[{sm_lo:+.2f},{sm_hi:+.2f}] no-regression; "
            f"small500 vs v1 {v1_mean:+.2f} CI[{v1_lo:+.2f},{v1_hi:+.2f}] gate-held"
        ),
        "large_vs_beam": (
            f"r9 {lg_net['mean']:.1f} vs beam {lg_beam['mean']:.1f} "
            f"({lg_net['mean'] - lg_beam['mean']:+.1f}); v6 was 291.6 vs 305.3 (-13.7) on confirm120"
        ),
        "supersedes": "r6 weights (small gate v6 98.6 vs v1 98.1 +0.6 CI[+0.2,+0.9]; large120 291.6)",
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
