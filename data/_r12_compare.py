"""r12 配对分析（降档 15→0）：同 seed 段（3000–3499）跨 JSON 配对 + 能量分解。

规则口径自 r11 后未变 → r12−r11 = 纯学生变化（零规则分移）；r12−v6/v1/r9/r10
全部用新规则参照（v6/v1 取 ei_r11_ref_* 的 teacher_net，r9/r10 取 ei_r11_ref_*
的 net 臂——阶段2 参照臂重评产物）。

能量分解（Σy² 代理，与 r11 文档同口径）：按训练管线重建——逐文件 std 归一化
（--norm-by-scenario）→ small ×2 上采样（--upsample-small 2）→ 无 demos
（--teacher-frac 0）。r11 参照：small 65.6% / large 28.9% / demos 5.5%。

用法：.venv\\Scripts\\python.exe data\\_r12_compare.py
一次性脚本，不提交。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_t4_b1 import _paired_ci

OUT = ROOT / "out"


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def scores(doc: dict, arm: str) -> list[float]:
    return doc["results"]["unknown"][arm]["scores"]


def delta(a: list[float], b: list[float]) -> tuple[float, float, float]:
    mean, half = _paired_ci([x - y for x, y in zip(a, b)])
    return mean, mean - half, mean + half


def report(label: str, a: list[float], b: list[float]) -> None:
    mean, lo, hi = delta(a, b)
    sig = "显著正" if lo > 0 else ("显著负" if hi < 0 else "中性")
    print(f"{label:<28} Δ={mean:+.3f} CI[{lo:+.3f},{hi:+.3f}] {sig}")


def energy() -> None:
    small = np.load(OUT / "ei_r11_selfplay_small.npz", allow_pickle=False)
    large = np.load(OUT / "ei_r11_selfplay_large.npz", allow_pickle=False)
    ys, yl = small["y"], large["y"]
    std_s, std_l = float(ys.std()), float(yl.std())
    ys_n, yl_n = ys / max(std_s, 1e-6), yl / max(std_l, 1e-6)
    # small ×2 上采样（重复行保持原值）
    y_mix = np.concatenate([ys_n, ys_n, yl_n])
    e_small = float(np.sum(ys_n**2) * 2)
    e_large = float(np.sum(yl_n**2))
    total = e_small + e_large
    print(
        f"能量分解（Σy² 代理）: small {e_small / total * 100:.1f}% / "
        f"large {e_large / total * 100:.1f}% / demos 0.0%"
        f"（r11: 65.6/28.9/5.5）"
    )
    print(
        f"行数: small {ys.shape[0]}×2={ys.shape[0] * 2} + large {yl.shape[0]}"
        f" = {y_mix.shape[0]}（r11: 467527 含 demos 48294）"
    )
    print(f"逐场景 std: small {std_s:.4f} / large {std_l:.4f}（r11: 12.1718/24.3013）")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r12s = load("ei_r12_eval_v12_small500.json")
    r12l = load("ei_r12_eval_v12_large500.json")
    r11s = load("ei_r11_eval_v11_small500.json")
    r11l = load("ei_r11_eval_v11_large500.json")
    ref_sv6 = load("ei_r11_ref_small_r9v6.json")   # teacher_net=v6, net=r9（新规则）
    ref_lv6 = load("ei_r11_ref_large_r9v6.json")
    ref_sv1 = load("ei_r11_ref_small_r10v1.json")  # teacher_net=v1, net=r10（新规则）
    ref_lv1 = load("ei_r11_ref_large_r10v1.json")

    print("=== small500（seed3000–3499，新规则） ===")
    report("r12−v6（本轮目的）", scores(r12s, "net"), scores(r12s, "teacher_net"))
    report("r12−v1（原门）", scores(r12s, "net"), scores(ref_sv1, "teacher_net"))
    report("r12−r11（纯学生变化）", scores(r12s, "net"), scores(r11s, "net"))
    report("r12−r9", scores(r12s, "net"), scores(ref_sv6, "net"))
    report("r12−r10", scores(r12s, "net"), scores(ref_sv1, "net"))
    report("r12−beam", scores(r12s, "net"), scores(r12s, "beam_analytic"))
    print("=== large500（seed3000–3499，新规则） ===")
    report("r12−v6（主门）", scores(r12l, "net"), scores(r12l, "teacher_net"))
    report("r12−r11（纯学生变化）", scores(r12l, "net"), scores(r11l, "net"))
    report("r12−r9", scores(r12l, "net"), scores(ref_lv6, "net"))
    report("r12−r10", scores(r12l, "net"), scores(ref_lv1, "net"))
    report("r12−beam", scores(r12l, "net"), scores(r12l, "beam_analytic"))

    print("=== 均值水位 ===")
    for name, doc in (("r12 small", r12s), ("r12 large", r12l)):
        for arm in ("net", "teacher_net", "beam_analytic", "greedy"):
            stat = doc["results"]["unknown"][arm]
            print(
                f"{name:<12} {arm:<14} mean={stat['mean']:.3f}"
                f" CLEAR={stat['clear_rate'] * 100:.1f}% PERFECT={stat['perfect_rate'] * 100:.1f}%"
            )

    print("=== 训练能量分解 ===")
    energy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
