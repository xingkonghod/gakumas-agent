"""初评价公式的回归测试：用已知的真实结算逐分核对。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gkagent.sim.hajime_eval import hajime_evaluation, reverse_final_score  # noqa: E402


def test_regular_9973():
    """2026-11-17 初 REGULAR 篠澤広：履历 995/996/478、最終 14314、第 1 名 → 9973。

    履历上的属性已含 +30，所以传进去要先减 30。
    """
    params = {"Vo": 995 - 30, "Da": 996 - 30, "Vi": 478 - 30}
    assert hajime_evaluation(params, 14314, 1, cap=1000) == 9973


def test_regular_10428():
    """2026-11-18 初 REGULAR：履历 914/1000/529、最終 21519、第 1 → 10428（属性已含 +30）。"""
    params = {"Vo": 914 - 30, "Da": 1000 - 30, "Vi": 529 - 30}
    assert hajime_evaluation(params, 21519, 1, cap=1000) == 10428


def test_pro_8790():
    """2026-11-18 初 PRO：履历 860/1250/657、最終 5175、第 2 → 8790（第 2 名不加 +30）。"""
    params = {"Vo": 860, "Da": 1250, "Vi": 657}
    assert hajime_evaluation(params, 5175, 2, cap=1500) == 8790


def test_master_12903():
    """2026-11-18 初 MASTER：履历 932/1600/734、最終 44250、第 1 → 12903。"""
    params = {"Vo": 932 - 30, "Da": 1600 - 30, "Vi": 734 - 30}
    assert hajime_evaluation(params, 44250, 1, cap=1800) == 12903


def test_reverse_matches():
    """反推一致性：反推出的分数代回去应得到目标评价。"""
    params = {"Vo": 860, "Da": 1250, "Vi": 657}
    target = hajime_evaluation(params, 5175, 2, cap=1500)
    got = reverse_final_score(params, target, 2, cap=1500)
    assert hajime_evaluation(params, got, 2, cap=1500) == target
