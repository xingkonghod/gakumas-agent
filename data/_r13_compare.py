"""r13 配对分析（完整渐退：教师←r11，占比 0.15→0.075）：同 seed 段跨 JSON 配对 + 能量分解。

门基线 = r11（最新老师）。r13−r11 = 纯学生变化（规则自 r11 后未变，零规则分移）；
r13−v6/v1 用新规则参照（ei_r11_ref_* teacher_net）。另报 r13−r12（r12 是 v6 数据去示范 ablation）。

能量分解（Σy² 代理）：按训练管线重建——逐文件 std 归一化 → 教师占比下采样（rng seed0）
→ small ×2 上采样。r11 参照：small 65.6% / large 28.9% / demos 5.5%（@0.15）；
r12：69.4/30.6/0（@0）；r13 @0.075 预期 demos 份额减半。

用法：.venv\\Scripts\\python.exe data\\_r13_compare.py
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


def energy(teacher_frac: float = 0.075) -> None:
    small = np.load(OUT / "ei_r13_selfplay_small.npz", allow_pickle=False)
    large = np.load(OUT / "ei_r13_selfplay_large.npz", allow_pickle=False)
    demos = np.load(OUT / "ei_r13_demos.npz", allow_pickle=False)
    ys, yl, yd = small["y"], large["y"], demos["y"]
    std_s, std_l = float(ys.std()), float(yl.std())
    ys_n, yl_n = ys / max(std_s, 1e-6), yl / max(std_l, 1e-6)
    n_s = ys.shape[0] + yl.shape[0]
    n_d = yd.shape[0]
    max_d = int(n_s * teacher_frac / (1.0 - teacher_frac))
    rng = np.random.default_rng(0)
    if n_d > max_d:
        idx = np.sort(rng.choice(n_d, size=max_d, replace=False))
        yd_sub = yd[idx]
    else:
        yd_sub = yd
    e_small = float(np.sum(ys_n**2) * 2)
    e_large = float(np.sum(yl_n**2))
    e_demos = float(np.sum(yd_sub**2))
    total = e_small + e_large + e_demos
    print(
        f"能量分解（Σy² 代理 @{teacher_frac}）: small {e_small / total * 100:.1f}% / "
        f"large {e_large / total * 100:.1f}% / demos {e_demos / total * 100:.1f}%"
        f"（r11@0.15: 65.6/28.9/5.5；r12@0: 69.4/30.6/0）"
    )
    print(
        f"行数: small {ys.shape[0]}×2 + large {yl.shape[0]} + demos {yd_sub.shape[0]}"
        f"（下采样 {n_d}→{yd_sub.shape[0]}）= {ys.shape[0]*2 + yl.shape[0] + yd_sub.shape[0]}"
    )
    print(f"逐场景 std: small {std_s:.4f} / large {std_l:.4f}")
    print(f"示范标签 std: {float(yd.std()):.4f}（软目标 ±1 口径）")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r13s = load("ei_r13_eval_v13_small500.json")
    r13l = load("ei_r13_eval_v13_large500.json")
    r11s = load("ei_r11_eval_v11_small500.json")
    r11l = load("ei_r11_eval_v11_large500.json")
    r12s = load("ei_r12_eval_v12_small500.json")
    r12l = load("ei_r12_eval_v12_large500.json")
    ref_sv6 = load("ei_r11_ref_small_r9v6.json")
    ref_lv6 = load("ei_r11_ref_large_r9v6.json")
    ref_sv1 = load("ei_r11_ref_small_r10v1.json")

    print("=== small500（seed3000–3499，新规则，基线=r11） ===")
    report("r13−r11（主门/目的）", scores(r13s, "net"), scores(r13s, "teacher_net"))
    report("r13−v6（绝对水位）", scores(r13s, "net"), scores(ref_sv6, "teacher_net"))
    report("r13−v1（原门）", scores(r13s, "net"), scores(ref_sv1, "teacher_net"))
    report("r13−r12", scores(r13s, "net"), scores(r12s, "net"))
    report("r13−beam", scores(r13s, "net"), scores(r13s, "beam_analytic"))
    print("=== large500（seed3000–3499，新规则，基线=r11） ===")
    report("r13−r11（主门）", scores(r13l, "net"), scores(r13l, "teacher_net"))
    report("r13−v6（绝对水位）", scores(r13l, "net"), scores(ref_lv6, "teacher_net"))
    report("r13−r12", scores(r13l, "net"), scores(r12l, "net"))
    report("r13−beam", scores(r13l, "net"), scores(r13l, "beam_analytic"))

    print("=== 均值水位 ===")
    for name, doc in (("r13 small", r13s), ("r13 large", r13l)):
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
