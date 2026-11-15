"""接线静态检查：auto_produce.py 里对 ProduceDriver 的每次方法调用都必须真实存在。

背景：2026-11-15 连续踩了三次同类坑——
  * policy.json 的 produce 段只保留默认键，attr_choice 被静默丢弃；
  * daemon 缓存旧窗口句柄，游戏重启后点空气；
  * auto_produce 调 `driver.clean_lesson_state(...)`，而它其实是模块级函数，
    真机一启动就 AttributeError（ep-cplus8 只跑 2 步）。
pytest 只覆盖 src/tests，scripts/ 的接线错误抓不到，所以用 AST 静态检查兜底。
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _driver_method_calls() -> dict[str, int]:
    """从 auto_produce.py 的 AST 里收集所有 `driver.<name>()` 调用。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        value = node.func.value
        if isinstance(value, ast.Name) and value.id == "driver":
            calls[node.func.attr] = calls.get(node.func.attr, 0) + 1
    return calls


def test_every_driver_call_exists_on_produce_driver() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from gkagent.tasks.produce_ui import ProduceDriver

    driver = ProduceDriver(ocr=None)
    missing = [name for name in _driver_method_calls() if not hasattr(driver, name)]
    assert not missing, f"auto_produce 调用了 ProduceDriver 上不存在的方法: {missing}"


def test_script_imports_resolve() -> None:
    """auto_produce 从 produce_ui 导入的名字都必须存在（防止把模块级函数写成方法）。"""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from gkagent.tasks import produce_ui

    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    missing: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "gkagent.tasks.produce_ui":
            continue
        for alias in node.names:
            if not hasattr(produce_ui, alias.name):
                missing.append(alias.name)
    assert not missing, f"auto_produce 从 produce_ui 导入了不存在的名字: {missing}"
