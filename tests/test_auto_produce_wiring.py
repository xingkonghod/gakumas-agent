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


def test_auto_produce_reads_attrs_via_fixed_roi() -> None:
    """三维必须每步走 driver.read_attrs(image)（固定小框），别再整屏正则找 X/1000。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "driver"
        and node.func.attr == "read_attrs"
    ]
    assert calls, "auto_produce 每步必须调用 driver.read_attrs(image) 记录三维"
    assert any(
        call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "image"
        for call in calls
    ), "read_attrs 必须用当步截图 image，而不是旧的 OCR 文本"
    assert 're.findall(r"(\\d{1,4})\\s*/\\s*1000"' not in source


def test_lesson_stall_guard_wired() -> None:
    """同一屏 5 步强制 SKIP / 10 步 [stuck] 退出必须真的接在课程分支上。

    真机 ep-cplus10：SKIP 点空后同一画面连拍 169 步直到 25 分钟超时；
    像素 digest 每帧都变，只有 lesson_turn_signature 语义签名能判"没推进"。
    """
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    assert "SameScreenGuard()" in source, "没接同屏兜底状态机"
    assert "same_screen.observe(" in source, "每步没喂同屏状态"
    assert "lesson_turn_signature(" in source, "同屏签名必须用语义状态而不是像素 digest"
    assert '== "force-skip"' in source, "5 步无变化没走强制 SKIP"
    assert '== "stuck"' in source and "[stuck]" in source, "10 步无变化没记 [stuck]"
    assert "stuck_exit = True" in source and "return 1 if stuck_exit" in source, (
        "卡死退出必须返回失败（不能算 done）"
    )


def test_lesson_stamina_gate_gets_last_stamina_fallback() -> None:
    """体力门必须拿到 last_stamina 兜底：本帧读不到体力时不能假设充足。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "lesson_stamina_gate"
    ]
    assert calls, "auto_produce 必须在课程分支调用 lesson_stamina_gate"
    keywords = {keyword.arg for call in calls for keyword in call.keywords}
    assert "last_stamina" in keywords, "体力门没传上一帧体力兜底（会退化成假设体力充足）"


def test_lesson_skip_uses_guard_once_per_turn() -> None:
    """体力门点 SKIP 前必须查 skip_done/点后 skip_sent：同回合不能每步重复点。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    assert "skip_done(turn_signature)" in source, "SKIP 前没查本回合是否已点过"
    assert "skip_sent(turn_signature)" in source, "SKIP 后没记本回合签名"


def test_window_precheck_wired_before_every_step() -> None:
    """F#9：每步决策/截图之前必须 ensure_window，且日志串固定（真机复盘靠它）。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    assert "def ensure_window(" in source, "没实现窗口前置检查"
    assert "window_state = ensure_window(hwnd)" in source, "主循环没调用 ensure_window"
    assert "[window] 已恢复（之前最小化/尺寸不对）" in source, "窗口恢复没打固定日志"
    assert 'window_state == "failed"' in source, "恢复失败没走等待/退出分支"
    assert "WINDOW_RESTORE_FAIL_LIMIT" in source, "恢复失败没有止损上限（会无限等待）"
    # 先恢复窗口再截图：不能等 capture 抛错后才补救（那时已经空转很多步）
    assert source.index("window_state = ensure_window(hwnd)") < source.index("image = agent.shot()")


def test_pause_gate_same_digest_fallback_wired() -> None:
    """F#11：暂停门触发时，画面 digest 与上一步相同必须直接放行。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    assert "pause_gate.observe(digest)" in source, "每步没喂画面 digest"
    assert "click_guard.force = force_continue" in source, "放行标记没传到点击门"
    assert "画面与上一步相同（bot 自身输入/卡住），直接放行" in source, "没打放行日志"
    assert "device.swipe = self.swipe" in source, "swipe 没接进暂停门（会移动光标误判用户操作）"
    assert "device.click = self.click" in source, "device.click 没接进暂停门"


def test_scenario_stuck_tick_exits_episode_as_failure() -> None:
    """F#15：兜底分支返回 stuck 时主循环必须记 [stuck] 并返回失败，不能空转到超时。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    assert 'tick.screen == "stuck"' in source, "主循环没处理 driver 的 stuck 结论"
    assert "[stuck]" in source, "stuck 时没记 [stuck] 日志"
    assert '"scenario-stall"' in source, "stuck 时没写失败记录"
    assert "stuck_exit = True" in source and "return 1 if stuck_exit" in source


def test_exam_mode_wired_and_disables_every_skip() -> None:
    """F#17：考试模式必须先识别排名条，再禁掉体力门/同屏/策略/浮层四处 SKIP。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    assert "driver.exam_mode(image, lines)" in source, "没识别考试模式（顶部排名条）"
    assert "[exam-mode]" in source, "考试模式没打 [exam-mode] 日志标记"
    assert 'kind="audition" if exam_mode' in source, "考试页没用试镜布局读剩余回合/体力"
    assert "exam=exam_mode" in source, "体力门没传考试标记"
    assert "allow_skip=not exam_mode" in source, "策略/浮层状态机没禁 SKIP"
    assert "and not exam_mode" in source, "「剩余牌打不出去」的 SKIP 没被考试模式拦住"
    assert "force_skip = stall_action == \"force-skip\" and not exam_mode" in source, (
        "同屏兜底强制 SKIP 没被考试模式拦住"
    )
