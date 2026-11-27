"""r10 评测离线分析：跨 JSON 配对（同 seed 段确定性 harness）+ 参照臂逐位校验。

用法（训练+评测跑完后）：
    .venv\\Scripts\\python.exe data\\_r10_eval_analysis.py

口径同 data/_r9_eval_analysis.py：eval_ei JSON 的 results.unknown.<arm>.scores
是逐局分数（seed 升序），同 deck/config/seed/policy → 逐位相同。本脚本：
1. 校验 r10 run 的 v6/beam/greedy 臂与 r9 参照 JSON 逐位一致（r9 会话已验
   r9 臂与 r6 JSON 一致 → 传递排除 harness 漂移）；
2. r10−v6 / r10−v1（跨 JSON）/ r10−beam 的 Δ+95%CI+W/T/L；
3. 池化段（small 580 = 500+80、large 620 = 500+120）；
4. r10 vs r9 同 seed 直接对比（修 small 回退 / 保 large 增益的实测）；
5. large 前 120 参照水位对文档数字。
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
        f"{label:<30} {ma:8.2f} vs {mb:8.2f}  Δ={mean:+7.3f} "
        f"CI[{mean - half:+7.3f},{mean + half:+7.3f}]  W/T/L {wins}/{ties}/{losses}"
    )


def check_same(a: list[float], b: list[float], label: str) -> None:
    n = min(len(a), len(b))
    same = a[:n] == b[:n]
    print(f"[逐位校验] {label}: 前 {n} 局 {'✅ 一致' if same else '❌ 不一致'}")
    if not same:
        diff = [i for i in range(n) if a[i] != b[i]]
        print(f"  不一致索引: {diff[:10]}")


def rates(doc: dict, arm: str) -> str:
    r = doc["results"]["unknown"][arm]
    return f"CLEAR {r['clear_rate'] * 100:.1f}% / PERFECT {r['perfect_rate'] * 100:.1f}%"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r10_small = load("ei_r10_eval_v10_small500.json")
    r10_large = load("ei_r10_eval_v10_large500.json")
    r10_select = load("ei_r10_eval_v10_small_select.json")
    r10_fresh = load("ei_r10_eval_v10_large_fresh6000.json")
    r9_small = load("ei_r9_eval_v9_small500.json")
    r9_large = load("ei_r9_eval_v9_large500.json")
    r6_small = load("ei_r6_eval_v6_confirm500.json")
    r6_large = load("ei_r6_eval_v6_large_confirm.json")

    print("=== 参照臂逐位校验（确定性 harness，传递 r9→r6 校验） ===")
    check_same(scores(r10_small, "teacher_net"), scores(r9_small, "teacher_net"), "small500 v6 臂 vs r9")
    check_same(scores(r10_small, "beam_analytic"), scores(r9_small, "beam_analytic"), "small500 beam 臂 vs r9")
    check_same(scores(r10_large, "teacher_net"), scores(r9_large, "teacher_net"), "large500 v6 臂 vs r9")
    check_same(scores(r10_large, "beam_analytic"), scores(r9_large, "beam_analytic"), "large500 beam 臂 vs r9")
    check_same(scores(r10_large, "greedy"), scores(r9_large, "greedy"), "large500 greedy 臂 vs r9")
    check_same(scores(r10_small, "teacher_net"), scores(r6_small, "net"), "small500 v6 臂 vs r6 confirm500")
    check_same(scores(r10_large, "teacher_net"), scores(r6_large, "net"), "large500 前120 v6 臂 vs r6 large_confirm")

    print("\n=== small 500 局（3000–3499，护栏） ===")
    pair(scores(r10_small, "net"), scores(r10_small, "teacher_net"), "r10 − v6（不回退门）")
    pair(scores(r10_small, "net"), scores(r6_small, "teacher_net"), "r10 − v1（跨 JSON，原门保持）")
    pair(scores(r10_small, "net"), scores(r10_small, "beam_analytic"), "r10 − beam（绝对水位）")
    print("  " + rates(r10_small, "net") + "（r10） vs " + rates(r10_small, "teacher_net") + "（v6）")

    print("\n=== small 选择 80（2000–2079） ===")
    pair(scores(r10_select, "net"), scores(r10_select, "teacher_net"), "r10 − v6")

    print("\n=== small 池化 580（500+80） ===")
    pair(
        scores(r10_small, "net") + scores(r10_select, "net"),
        scores(r10_small, "teacher_net") + scores(r10_select, "teacher_net"),
        "r10 − v6 池化",
    )

    print("\n=== large 500 局（3000–3499，主门） ===")
    pair(scores(r10_large, "net"), scores(r10_large, "teacher_net"), "r10 − v6（large 门）")
    pair(scores(r10_large, "net"), scores(r10_large, "beam_analytic"), "r10 − beam（缺口/超出）")
    pair(scores(r10_large, "net")[:120], scores(r6_large, "teacher_net"), "r10 − v1（跨 JSON，前120）")
    print("  " + rates(r10_large, "net") + "（r10） vs " + rates(r10_large, "beam_analytic") + "（beam）")

    print("\n=== large 新鲜块 120（6000–6119） ===")
    pair(scores(r10_fresh, "net"), scores(r10_fresh, "teacher_net"), "r10 − v6")
    pair(scores(r10_fresh, "net"), scores(r10_fresh, "beam_analytic"), "r10 − beam")

    print("\n=== large 池化 620（500+120） ===")
    pair(
        scores(r10_large, "net") + scores(r10_fresh, "net"),
        scores(r10_large, "teacher_net") + scores(r10_fresh, "teacher_net"),
        "r10 − v6 池化",
    )
    pair(
        scores(r10_large, "net") + scores(r10_fresh, "net"),
        scores(r10_large, "beam_analytic") + scores(r10_fresh, "beam_analytic"),
        "r10 − beam 池化",
    )

    print("\n=== r10 vs r9（同 seed 直接对比：修 small / 保 large） ===")
    pair(scores(r10_small, "net"), scores(r9_small, "net"), "small500 r10 − r9")
    pair(scores(r10_large, "net"), scores(r9_large, "net"), "large500 r10 − r9")

    print("\n=== large 前 120 局参照水位（对文档） ===")
    for arm, ref in (("teacher_net", "v6=291.61"), ("beam_analytic", "beam=305.34"), ("greedy", "greedy=212.41")):
        s = scores(r10_large, arm)[:120]
        print(f"{arm:<16} mean={sum(s) / len(s):8.4f}  （参照 {ref}）")
    s = scores(r6_large, "teacher_net")
    print(f"{'v1(r6 JSON)':<16} mean={sum(s) / len(s):8.4f}  （参照 v1=277.24）")


if __name__ == "__main__":
    main()
