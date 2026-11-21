"""auto_produce 全局墙钟上限：卡住时主动停局，不能无限空转。

用户规则（2026-11-21）：一局见过卡两个多小时还跑到 C；真机整局目标 ≤20 分钟，
所以超过 ``--max-minutes``（默认 30）就写 ``episode-timeout`` failure 并停局。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _auto_produce():
    """按 scripts 目录导入 auto_produce（scripts 不是包，避免污染 sys.path 到顶层）。"""
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import auto_produce

    return auto_produce


def test_exceeds_timeout_before_and_after_limit() -> None:
    ap = _auto_produce()
    assert ap.exceeds_timeout(1000.0, 1000.0 + 29 * 60, 30.0) is False
    assert ap.exceeds_timeout(1000.0, 1000.0 + 30 * 60, 30.0) is True
    assert ap.exceeds_timeout(1000.0, 1000.0 + 31 * 60, 30.0) is True


def test_exceeds_timeout_zero_disables_limit() -> None:
    ap = _auto_produce()
    assert ap.exceeds_timeout(0.0, 10**9, 0.0) is False
    assert ap.exceeds_timeout(0.0, 10**9, -1.0) is False
