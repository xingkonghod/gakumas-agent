"""r9 评测离线分析：跨 JSON 配对（同 seed 段确定性 harness）+ 参照臂逐位校验。

用法（训练+评测跑完后）：
    .venv\\Scripts\\python.exe data\\_r9_eval_analysis.py

口径：eval_ei JSON 的 results.unknown.<arm>.scores 是逐局分数（seed 升序）。
同 deck/config/seed/policy → 逐位相同（B11 确定性纪律），所以不同 run 的
同段臂可以跨 JSON 配对。本脚本：
1. 校验新 run 的 v6/beam/greedy 臂与 r6 参照 JSON 在重叠 seed 上逐位一致；
2. r9−v6（新 JSON 内配对）/ r9−v1（跨 JSON）/ r9−beam 的 Δ+95%CI+W/T/L；
3. large 参照水位（前 120 局）与 r3–r8 文档数字核对。
一次性脚本，不提交。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from eval_t4_b1 import _paired_ci

OUT = ROOT / "out"


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def scores(doc: dict, arm: str) -> list[float]:
    return doc["results"]["unknown"][arm]["scores"]


def pair(a: list[float], b: list[float], label: str) -> None:
    assert len(a) == len(b), f"{label}: 长度不等 {len(a)} vs {len(b)}"
    deltas = [x - y for x, y in zip(a, b)]
    mean, half = _paired_ci(deltas)
    wins = sum(1 for d in deltas if d > 0)
    ties = sum(1 for d in deltas if d == 0)
    losses = sum(1 for d in deltas if d < 0)
    ma = sum(a) / len(a)
    mb = sum(b) / len(b)
    print(
        f"{label:<28} {ma:8.2f} vs {mb:8.2f}  Δ={mean:+7.3f} "
        f"CI[{mean - half:+7.3f},{mean + half:+7.3f}]  W/T/L {wins}/{ties}/{losses}"
    )


def check_same(a: list[float], b: list[float], label: str) -> None:
    n = min(len(a), len(b))
    same = a[:n] == b[:n]
    print(f"[逐位校验] {label}: 前 {n} 局 {'✅ 一致' if same else '❌ 不一致'}")
    if not same:
        diff = [i for i in range(n) if a[i] != b[i]]
        print(f"  不一致索引: {diff[:10]}")


def main() -> None:
    r9_small = load("ei_r9_eval_v9_small500.json")
    r9_large = load("ei_r9_eval_v9_large500.json")
    r6_small = load("ei_r6_eval_v6_confirm500.json")
    r6_large = load("ei_r6_eval_v6_large_confirm.json")

    print("=== 参照臂逐位校验（确定性 harness） ===")
    check_same(scores(r9_small, "teacher_net"), scores(r6_small, "net"), "small500 v6 臂 vs r6 confirm500")
    check_same(scores(r9_small, "beam_analytic"), scores(r6_small, "beam_analytic"), "small500 beam 臂 vs r6 confirm500")
    check_same(scores(r9_large, "teacher_net"), scores(r6_large, "net"), "large500 前120 v6 臂 vs r6 large_confirm")
    check_same(scores(r9_large, "beam_analytic"), scores(r6_large, "beam_analytic"), "large500 前120 beam 臂 vs r6 large_confirm")
    if "greedy" in r9_large["results"]["unknown"]:
        check_same(scores(r9_large, "greedy"), scores(r6_large, "greedy"), "large500 前120 greedy 臂 vs r6 large_confirm")

    print("\n=== small 500 局（3000–3499） ===")
    pair(scores(r9_small, "net"), scores(r9_small, "teacher_net"), "r9 − v6（不回退门）")
    pair(scores(r9_small, "net"), scores(r6_small, "teacher_net"), "r9 − v1（跨 JSON，原门保持）")
    pair(scores(r9_small, "net"), scores(r9_small, "beam_analytic"), "r9 − beam（绝对水位）")

    print("\n=== large 500 局（3000–3499） ===")
    pair(scores(r9_large, "net"), scores(r9_large, "teacher_net"), "r9 − v6（large 门）")
    pair(scores(r9_large, "net")[:120], scores(r6_large, "teacher_net"), "r9 − v1（跨 JSON，前120）")
    pair(scores(r9_large, "net"), scores(r9_large, "beam_analytic"), "r9 − beam（缺口）")

    print("\n=== large 前 120 局参照水位（对 r3–r8 文档） ===")
    for arm, ref in (("net", "r9"), ("teacher_net", "v6=291.6"), ("beam_analytic", "beam=305.3")):
        s = scores(r9_large, arm)[:120]
        print(f"{arm:<16} mean={sum(s) / len(s):8.2f}  （参照 {ref}）")
    s = scores(r6_large, "teacher_net")
    print(f"{'v1(r6 JSON)':<16} mean={sum(s) / len(s):8.2f}  （参照 v1=277.2）")
    if "greedy" in r6_large["results"]["unknown"]:
        s = scores(r6_large, "greedy")
        print(f"{'greedy(r6 JSON)':<16} mean={sum(s) / len(s):8.2f}  （参照 greedy=212.4）")


if __name__ == "__main__":
    main()
