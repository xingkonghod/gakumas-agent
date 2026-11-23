"""C1 接线静态检查：提权检查/tap 互验/饮料重试/轨迹落盘必须真的接在 auto_produce 上。

与 test_auto_produce_wiring.py 同约定：pytest 只覆盖 src/tests，scripts/ 的接线
错误抓不到，用源码/AST 静态检查兜底（真机 ep-cplus8 的 AttributeError 教训）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")


def test_privilege_check_wired_before_agent_and_blocks() -> None:
    source = _source()
    assert "from gkagent.device.privilege import check_tap_privilege" in source
    assert "priv = check_tap_privilege(hwnd)" in source
    # 先查提权再建设备/跑局：blocked 时点击全落空，不能起跑
    assert source.index("priv = check_tap_privilege(hwnd)") < source.index(
        "agent = Agent(Win32Device(hwnd).connect()"
    )
    assert 'priv.status == "blocked"' in source
    assert '"elevation-blocked"' in source
    assert "[priv]" in source
    assert source.index('priv.status == "blocked"') < source.index("for step in range(1, steps + 1)")


def test_tap_guard_wired_observe_before_decide_and_budget_after() -> None:
    source = _source()
    assert "tap_guard = TapGuard()" in source
    assert "tap_verdict = tap_guard.observe(text, frame_sig)" in source
    assert "tap_guard.budget(tick.action, tick.point, tick.expect, screen=tick.screen)" in source
    # 互验在重新决策之前（先判上一击，再决定这一步）
    assert source.index("tap_verdict = tap_guard.observe(") < source.index(
        "tick = driver.decide(agent, lines, image)"
    )
    # retap = 同坐标重试，不重新识别
    assert 'tap_verdict.outcome == "retap"' in source
    assert "agent.device.click_force(*tap_verdict.point)" in source
    assert '"tap-retap"' in source


def test_tap_lost_logged_and_streak_stops_episode() -> None:
    source = _source()
    assert "[tap][LOST]" in source
    assert '"tap-lost"' in source
    assert "TAP_LOST_STREAK_LIMIT" in source
    assert "tap_lost_streak >= TAP_LOST_STREAK_LIMIT" in source
    # 连续 tap 丢失 = 停局修 root cause，不是静默 SKIP/空转到超时
    idx = source.index("tap_lost_streak >= TAP_LOST_STREAK_LIMIT")
    tail = source[idx : idx + 400]
    assert "stuck_exit = True" in tail and "break" in tail


def test_tap_guard_cancelled_in_lesson_and_postponed_on_loading_pause() -> None:
    source = _source()
    assert "tap_guard.cancel()" in source  # 课程分支交给 LessonPlayGuard
    assert "tap_guard.postpone()" in source  # 加载/空白/暂停帧不判
    assert source.count("tap_guard.postpone()") >= 2


def test_end_turn_yes_budgets_dialog_gone() -> None:
    source = _source()
    assert 'tap_guard.budget("end-turn-yes", TURN_END_YES, step_expect, screen="lesson")' in source
    assert 'expect_dialog_gone(("结束回合",), driver._frame_signature(text))' in source


def test_drink_attempt_wired_with_failure_log() -> None:
    source = _source()
    assert "def attempt_drink(" in source
    assert "drink_ok, drink_reason = attempt_drink(agent, driver)" in source
    assert '"drink-dialog-lost"' in source
    # 旧「点一下就当已喝」的裸点击不能再出现在饮料分支
    assert "agent.device.click_force(75, 1182)" not in source


def test_trace_written_per_step_and_summary_at_end() -> None:
    source = _source()
    assert "trace_log = TraceLog(" in source
    assert "trace_log.write(" in source
    assert "click_guard.last_point = None" in source  # 每步清零落点
    assert "self.last_point = (int(x), int(y))" in source  # 点击门记录落点
    assert 'log_lines.append(f"[tap] {tap_guard.summary()}")' in source
    assert '"tap": tap_guard.summary()' in source


def test_tick_result_has_c1_fields() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from gkagent.tasks.produce_ui import ProduceDriver, TickResult

    tick = TickResult("dialog", "confirm")
    assert hasattr(tick, "point") and hasattr(tick, "reason") and hasattr(tick, "expect")
    driver = ProduceDriver(ocr=None)
    assert hasattr(driver, "reward_picker")


def test_replay_script_exists_and_uses_trace_helpers() -> None:
    source = (ROOT / "scripts" / "replay_steps.py").read_text(encoding="utf-8")
    assert "from gkagent.runtime.trace import" in source
    assert "format_trace" in source and "summarize_traces" in source
    assert "--episode" in source and "--anomalies" in source


def test_skip_rules_unchanged_by_c1() -> None:
    """C1 不新增 SKIP 出口：考试禁跳/体力门/同屏兜底的既有红线保持原样。"""
    source = _source()
    assert 'force_skip = stall_action == "force-skip" and not exam_mode' in source
    assert "allow_skip=not exam_mode" in source
    assert "skip_done(turn_signature)" in source
    # TapGuard 的 lost 不接 SKIP：lost 分支只有日志/failure/止损
    idx = source.index('tap_verdict.outcome == "lost"')
    block = source[idx : source.index("elif tap_verdict", idx)]
    assert "SKIP" not in block and "click_force" not in block
