"""ProduceDriver：只验证「这一屏点哪里」的规则，不碰真机。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from gkagent.tasks import produce_ui
from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrLine

DATA = Path(__file__).resolve().parents[1] / "data"


@dataclass
class FakeDevice:
    clicks: list[tuple[int, int]] = field(default_factory=list)

    def click_force(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)


def _lines(*texts: str) -> list[OcrLine]:
    """每行一个 200x40 的框，纵向排列；中心 y = 60 + 60*index。"""
    return [OcrLine(text, 0.95, (40, 40 + index * 60, 200, 40)) for index, text in enumerate(texts)]


def _driver() -> ProduceDriver:
    return ProduceDriver(sleep=lambda _seconds: None)


def _center(index: int) -> tuple[int, int]:
    return 140, 60 + 60 * index


def test_dialog_confirm_clicks_ok_text() -> None:
    agent = FakeAgent()
    lines = _lines("跳过确认", "未读的交流", "取消", "确定")
    result = _driver().decide(agent, lines)
    assert result.screen == "dialog"
    assert agent.device.clicks[-1] == _center(3)


def test_net_error_dialog_clicks_retry_before_loading() -> None:
    """F#27 真机 ep-t1-d：通信错误弹窗（获取资产失败 E203）含「通信」，不能被当成 loading 空等。"""
    agent = FakeAgent()
    lines = _lines("通信错误", "获取资产失败", "请在网络环境好的地方再试", "(E203)", "返回标题", "重试")
    result = _driver().decide(agent, lines)
    assert result.screen == "net-error"
    assert result.action == "retry"
    assert agent.device.clicks[-1] == _center(5)


def test_asset_error_without_retry_uses_fixed_point() -> None:
    agent = FakeAgent()
    lines = _lines("通信错误", "获取资产失败", "请在网络环境好的地方再试")
    result = _driver().decide(agent, lines)
    assert result.screen == "net-error"
    assert agent.device.clicks[-1] == produce_ui.NET_RETRY


def test_loading_still_waits_without_error_keywords() -> None:
    agent = FakeAgent()
    lines = _lines("NOW LOADING...")
    result = _driver().decide(agent, lines)
    assert result.screen == "loading"
    assert not agent.device.clicks


def test_outing_action_page_is_not_event_choice() -> None:
    """外出/授课行动页的描述框含「选项」长句，不能被当成事件选项（ep-t1-g 原地循环 10+ 周）。"""
    agent = FakeAgent()
    lines = _lines(
        "外出",
        "授课",
        "根据选项会发生各种效果。",
        "主要为消耗P点数来回复体力。",
    )
    result = _driver().decide(agent, lines)
    assert result.screen == "action"
    assert result.action == "go-out"
    assert agent.device.clicks[-1] == (268, 1010)


def test_event_choice_still_works_without_action_buttons() -> None:
    agent = FakeAgent()
    lines = [
        OcrLine("外出", 0.9, (40, 60, 200, 40)),
        OcrLine("戏剧", 0.9, (60, 650, 300, 40)),
        OcrLine("体育", 0.9, (60, 750, 300, 40)),
        OcrLine("露营", 0.9, (60, 850, 300, 40)),
    ]
    result = _driver().decide(agent, lines)
    assert result.screen == "event-choice"


def test_event_choice_degraded_uses_cost_labels() -> None:
    """ep-t1-h 真机：选项按钮文字 OCR 只剩 1 个字时，用 P 费标签定位最后一个（免费）选项。"""
    agent = FakeAgent()
    lines = [
        OcrLine("外出", 0.9, (90, 51, 45, 26)),
        OcrLine("-100", 0.9, (598, 648, 64, 28)),
        OcrLine("-50", 0.9, (612, 750, 49, 26)),
        OcrLine("気持", 0.9, (97, 683, 276, 30)),
        OcrLine("快进", 0.9, (584, 1187, 81, 28)),
    ]
    result = _driver().decide(agent, lines)
    assert result.screen == "event-choice"
    assert result.action == "last-row"
    # 最后一个 P 费标签中心 y=763 → 免费选项 y≈901
    assert agent.device.clicks[-1] == (360, 901)


def test_event_choice_without_header_or_fast_forward_still_works() -> None:
    """ep-t1-h：事件屏标题「外出」/「快进」都漏读时，靠选项行 + P 费/问句兜底识别。"""
    agent = FakeAgent()
    lines = [
        OcrLine("気持ちよかったです", 0.9, (70, 690, 590, 90)),
        OcrLine("-100", 0.9, (598, 648, 64, 28)),
        OcrLine("お断りしました", 0.9, (70, 790, 590, 90)),
        OcrLine("-50", 0.9, (612, 750, 49, 26)),
        OcrLine("……本当、ですか?", 0.9, (96, 980, 207, 30)),
    ]
    result = _driver().decide(agent, lines)
    assert result.screen == "event-choice"


def test_event_choice_confirm_click_after_selection() -> None:
    """ep-t1-i：选中态那一帧选项文字只剩 1 个字（option_rows=0），仍要能点第二次确认。"""
    driver = _driver()
    agent = FakeAgent()
    driver.event_pending_y = 901
    lines = [
        OcrLine("外出", 0.9, (90, 51, 45, 26)),
        OcrLine("100", 0.9, (608, 650, 53, 25)),
        OcrLine("-50", 0.9, (614, 750, 46, 26)),
        OcrLine("気", 0.9, (97, 682, 278, 33)),
        OcrLine("……本当、ですか?", 0.9, (95, 980, 208, 30)),
    ]
    result = driver.decide(agent, lines)
    assert result.screen == "event-choice"
    assert result.action == "confirm"
    assert agent.device.clicks[-1] == (360, 901)
    assert driver.event_pending_y is None


def test_voice_dialog_picks_silent_option() -> None:
    agent = FakeAgent()
    lines = _lines("语音播放确认", "播放语音", "不播放语音", "取消", "确定")
    result = _driver().decide(agent, lines)
    assert result.screen == "dialog"
    assert result.action == "voice-off"
    assert agent.device.clicks[-1] == _center(4)


def test_setup_support_prefers_auto_button() -> None:
    agent = FakeAgent()
    lines = _lines("2.选择支援卡", "自动", "重置", "下一步")
    result = _driver().decide(agent, lines)
    assert result.screen == "setup-support"
    assert result.action == "auto"
    assert agent.device.clicks[-1] == _center(1)


def test_setup_idol_clicks_next_point() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("1.选择偶像", "下一步"))
    assert result.screen == "setup-idol"
    assert agent.device.clicks[-1] == produce_ui.NEXT_BUTTON


def test_setup_support_auto_only_once_then_next() -> None:
    driver = _driver()
    agent = FakeAgent()
    lines = _lines("2.选择支援卡", "自动", "重置", "下一步")
    first = driver.decide(agent, lines)
    second = driver.decide(agent, lines)
    assert first.action == "auto"
    assert second.action == "next"
    assert agent.device.clicks[-1] == produce_ui.NEXT_BUTTON


def test_action_screen_follows_recommendation() -> None:
    agent = FakeAgent()
    lines = _lines(
        "请选择行动", "视觉好像有点不足呢", "推荐视觉训练", "Vo.训练", "Da.训练", "Vi.训练"
    )
    result = _driver().decide(agent, lines)
    assert result.screen == "action"
    assert result.action == "train-Vi"
    # 现在按 OCR 文本行定位：点「Vi.训练」文字行中心（第 6 行）
    assert agent.device.clicks[-1] == _center(5)


def test_action_screen_tolerates_garbled_training_labels() -> None:
    agent = FakeAgent()
    lines = _lines("Vo.训练", "Da.训", "审查基准", "训练")
    result = _driver().decide(agent, lines)
    assert result.screen == "action"


def test_p_point_toast_waits() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("获得P点数", "舞蹈SP训练"))
    assert result.screen == "toast"
    assert result.action == "wait"
    assert agent.device.clicks == []


def test_p_drink_popup_taps_to_advance() -> None:
    agent = FakeAgent()
    lines = _lines("蓬松又柔软", "获得随机P饮料2瓶")
    result = _driver().decide(agent, lines)
    assert result.screen == "toast"
    assert result.action == "advance"
    assert agent.device.clicks == [(360, 1000)]


def test_unknown_text_falls_back_to_tap() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("某个从未见过的提示文字"))
    assert result.screen == "unknown-tap"
    assert agent.device.clicks == [(360, 1000)]


def test_drink_capacity_dialog_clicks_keep() -> None:
    agent = FakeAgent()
    lines = _lines("P饮料持有上限", "请选择保留的3瓶饮料。", "获得的饮料", "保留")
    result = _driver().decide(agent, lines)
    assert result.screen == "drink-keep"
    assert result.action == "keep"
    assert agent.device.clicks[-1] == _center(3)


def test_lesson_choice_follows_recommended_training() -> None:
    agent = FakeAgent()
    lines = _lines(
        "实力足够了呢。想要争取好成绩的话 推荐舞蹈训练!",
        "重点练习歌唱",
        "重点练习舞蹈",
        "重点练习视觉效果",
    )
    result = _driver().decide(agent, lines)
    assert result.screen == "lesson-choice"
    assert result.action == "pick-舞蹈"
    assert agent.device.clicks[-1] == (360, 798)


def test_event_choice_picks_bottom_then_confirms() -> None:
    lines = [
        OcrLine("外出", 0.9, (90, 50, 40, 20)),
        OcrLine("戏剧", 0.9, (90, 680, 60, 30)),
        OcrLine("体育", 0.9, (90, 780, 60, 30)),
        OcrLine("露营", 0.9, (90, 880, 60, 30)),
        OcrLine("-100", 0.9, (600, 650, 60, 24)),
        OcrLine("-50", 0.9, (600, 750, 60, 24)),
        OcrLine("快进", 0.9, (600, 1180, 80, 30)),
    ]
    driver = _driver()
    agent = FakeAgent()
    first = driver.decide(agent, lines)
    second = driver.decide(agent, lines)
    assert first.screen == "event-choice"
    assert first.action == "last-row"
    assert second.action == "confirm"
    assert agent.device.clicks == [(360, 895), (360, 895)]


def test_lesson_defers_to_card_policy() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("剩余回合数", "CLEAR截止", "SKIP"))
    assert result.screen == "lesson"
    assert result.action == "card-policy"
    assert agent.device.clicks == []


def test_home_enters_produce() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("亲密度", "活动经费", "主页", "商店"))
    assert result.screen == "home"
    assert agent.device.clicks[-1] == produce_ui.PRODUCE_ENTRY


def test_scenario_page_clicks_regular() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("培育", "定期公演「初」", "研修"))
    assert result.screen == "scenario"
    assert agent.device.clicks[-1] == produce_ui.REGULAR_DIFFICULTY


def test_produce_record_popup_closes_with_x() -> None:
    """F#15：培育记录详情弹窗同样含「定期公演」，必须先识别并点底部 X 关闭。

    真机 ep-cplus13：这屏被当成培育页，每步点一次难度按钮、画面不动，12 次停机。
    """
    agent = FakeAgent()
    lines = _lines("培育记录", "定期公演「初」", "编成支援卡", "最终持有P道具")
    result = _driver().decide(agent, lines)
    assert result.screen == "record"
    assert result.action == "close"
    assert agent.device.clicks[-1] == produce_ui.PRODUCE_RECORD_CLOSE


def test_scenario_branch_falls_back_to_close_after_three_stalls() -> None:
    """F#15 兜底：没有「培育记录」字样但同段文本连续 3 次命中 scenario → 点 X 降级。"""
    agent = FakeAgent()
    driver = _driver()
    lines = _lines("定期公演「初」", "Regular", "2026/11/15")
    for _ in range(2):
        assert driver.decide(agent, lines).screen == "scenario"
    result = driver.decide(agent, lines)
    assert result.screen == "record"
    assert result.action == "close-fallback"
    assert agent.device.clicks[-1] == produce_ui.PRODUCE_RECORD_CLOSE


def test_retry_confirm_dialog_clicks_ok() -> None:
    """考试不合格 → 点「再挑战」→ 第二段「再挑战确认」只有 取消/确定，必须点确定。

    真机 ep-sup1 step 179-188：这屏没有「再挑战」按钮，旧逻辑落到 end-produce 点
    (355,1148) 空点，10 次后停机（把一局可以直接重打的考试白白判负）。
    """
    agent = FakeAgent()
    lines = _lines("再挑战确认", "消耗再挑战道具，重新挑战考试吗？", "今天免费剩余1次", "取消", "确定")
    result = _driver().decide(agent, lines)
    assert result.screen == "dialog"
    assert result.action == "retry-confirm"
    assert agent.device.clicks[-1] == _center(4)


def test_action_screen_needs_all_three_training_buttons() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("推荐", "Da.训练", "审查基准"))
    assert result.screen != "action"


def test_card_reward_picks_recommended_then_claims() -> None:
    agent = FakeAgent()
    lines = _lines("请选择要领取的技能卡。", "推荐", "领取")
    result = _driver().decide(agent, lines)
    assert result.screen == "card-reward"
    # 「推荐」标签在卡牌下缘，实际点卡身（向上 60px）
    assert agent.device.clicks[0] == (_center(1)[0], _center(1)[1] - 60)
    assert agent.device.clicks[-1] == _center(2)


def test_reward_recommend_marker_beats_card_table_value() -> None:
    """奖励界面：游戏标「推荐」的卡优先级最高，哪怕它的白值不如另一张。"""
    from gkagent.tasks.produce_ui import ProduceDriver

    high_value = OcrLine("聊天时间", 0.95, (40, 850, 120, 30))
    low_value = OcrLine("魅力的基础", 0.95, (300, 850, 120, 30))
    recommend = OcrLine("推荐", 0.95, (330, 960, 60, 28))
    picked = ProduceDriver._best_reward_card([high_value, low_value, recommend])
    assert picked is not None
    # 点第二张（推荐卡）的卡身，而不是白值更高的第一张
    assert picked[0] >= 300
    # 没有推荐标记时才按估值：白值更高的「聊天时间」(4.5) 胜过「魅力的基础」(2.25)
    fallback = ProduceDriver._best_reward_card([high_value, low_value])
    assert fallback is not None
    assert fallback[0] < 300


def test_reward_gold_card_frame_detected_as_fallback() -> None:
    """OCR 读不到「推荐」时，用金色卡框（闪黄光）兜底选卡。"""
    import cv2
    import numpy as np

    from gkagent.tasks.produce_ui import ProduceDriver

    image = np.zeros((1280, 720, 3), dtype=np.uint8)
    cv2.rectangle(image, (430, 850), (560, 960), (0, 200, 255), 3)  # BGR 金色卡框
    point = ProduceDriver._gold_reward_point(image)
    assert point is not None
    assert 430 < point[0] < 560
    assert 830 < point[1] < 980


def test_blank_transition_is_wait_not_stuck() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, [])
    assert result.screen == "blank"
    assert result.ok
    assert agent.device.clicks == []


def test_action_screen_lesson_variant_clicks_lesson() -> None:
    agent = FakeAgent()
    lines = _lines("请选择行动", "授课", "活动奖励")
    result = _driver().decide(agent, lines)
    assert result.screen == "action"
    assert result.action == "lesson"
    # 按「授课」文本行中心点，而不是写死坐标
    assert agent.device.clicks[-1] == _center(1)


def test_action_screen_rests_when_stamina_low() -> None:
    agent = FakeAgent()
    # 阈值 8：体力 5 才休息（10 以上继续练，多练才涨属性）
    lines = _lines("请选择行动", "5/35", "休息", "授课")
    result = _driver().decide(agent, lines)
    assert result.screen == "action"
    assert result.action == "rest"


def test_action_screen_never_lessons_below_lesson_threshold() -> None:
    """体力 10 < 12：有「授课」也不进课程，优先休息（0 体力进课只会连按 SKIP）。"""
    agent = FakeAgent()
    lines = _lines("请选择行动", "10/35", "授课", "活动奖励", "休息")
    result = _driver().decide(agent, lines)
    assert result.screen == "action"
    assert result.action == "rest"
    # 点的是「休息」（索引 4），不是「授课」（索引 2）
    assert agent.device.clicks[-1] == _center(4)


def test_action_screen_below_train_threshold_never_trains() -> None:
    """体力 6 < 8 且没有休息按钮：训练/授课都不点，等恢复（只休息）。"""
    agent = FakeAgent()
    lines = _lines("请选择行动", "6/35", "授课", "Vo.训练", "Da.训练", "Vi.训练")
    result = _driver().decide(agent, lines)
    assert result.screen == "action"
    assert result.action == "stamina-wait"
    assert agent.device.clicks == []


def test_lesson_with_stamina_below_lowest_cost_skips_at_once() -> None:
    """课程中体力 0 < 最低手牌费用 1：立刻 SKIP，不要一回合一点地磨。"""
    from gkagent.tasks.produce_ui import LESSON_SKIP_POINT, lesson_stamina_gate
    from gkagent.vision.lesson import LessonCard, LessonState

    cards = (
        LessonCard(
            index=0,
            box=(55, 895, 160, 185),
            point=(135, 987),
            name="聊天时间",
            score=39,
            cost=1,
        ),
        LessonCard(
            index=1,
            box=(280, 895, 160, 185),
            point=(360, 987),
            name="魅力的基础",
            score=9,
            cost=2,
        ),
    )
    gate = lesson_stamina_gate(LessonState(stamina=0, turns_left=6, cards=cards))
    assert gate is not None
    point, reason = gate
    assert point == LESSON_SKIP_POINT == (657, 800)
    assert "体力 0" in reason and "最低手牌费用 1" in reason
    # 体力够最低费用就不 SKIP（能打得出牌）
    assert lesson_stamina_gate(LessonState(stamina=2, turns_left=6, cards=cards)) is None


def _gate_cards(*costs: int | None):
    from gkagent.vision.lesson import LessonCard

    return tuple(
        LessonCard(
            index=index,
            box=(55 + index * 180, 895, 160, 185),
            point=(135 + index * 180, 987),
            name=f"卡{index}",
            score=10 + index,
            cost=cost,
        )
        for index, cost in enumerate(costs)
    )


def test_zero_stamina_lesson_skips_even_without_hand() -> None:
    """体力 0 + 手牌一张都没读到：也必须 SKIP（之前 lowest=None → 体力门不触发）。"""
    from gkagent.tasks.produce_ui import LESSON_SKIP_POINT, lesson_stamina_gate
    from gkagent.vision.lesson import LessonState

    gate = lesson_stamina_gate(LessonState(stamina=0, turns_left=6, cards=()))
    assert gate is not None
    assert gate[0] == LESSON_SKIP_POINT
    assert "体力 0" in gate[1]


def test_zero_stamina_lesson_skips_when_all_costs_unread() -> None:
    """体力 0 + 手牌费用全读不到（cost=None）：照样 SKIP，不能等 OCR 读出费用。"""
    from gkagent.tasks.produce_ui import LESSON_SKIP_POINT, lesson_stamina_gate
    from gkagent.vision.lesson import LessonState

    cards = _gate_cards(None, None, None)
    gate = lesson_stamina_gate(LessonState(stamina=0, turns_left=6, cards=cards))
    assert gate is not None
    assert gate[0] == LESSON_SKIP_POINT
    # 本帧体力没读到，但上一帧读到 0：同样必须 SKIP（不能把"没读到"当充足）
    gate = lesson_stamina_gate(
        LessonState(stamina=None, turns_left=6, cards=cards), last_stamina=0
    )
    assert gate is not None
    assert gate[0] == LESSON_SKIP_POINT


def test_lesson_gate_never_assumes_unknown_stamina_is_enough() -> None:
    """体力三处都读不到：不假设充足——费用也读不到就 SKIP；全是 0 费牌才放行。"""
    from gkagent.tasks.produce_ui import LESSON_SKIP_POINT, lesson_stamina_gate
    from gkagent.vision.lesson import LessonState

    unknown = lesson_stamina_gate(
        LessonState(stamina=None, turns_left=6, cards=_gate_cards(4, 1, 4)),
        stamina=None,
        last_stamina=None,
    )
    assert unknown is not None
    assert unknown[0] == LESSON_SKIP_POINT
    assert "不假设充足" in unknown[1]

    # 0 费牌 0 体力也能打：体力未知但费用明确为 0 时不白送回合
    free = lesson_stamina_gate(
        LessonState(stamina=None, turns_left=6, cards=_gate_cards(0, 0)),
        last_stamina=None,
    )
    assert free is None


def test_lesson_skip_is_once_per_turn() -> None:
    """体力门 SKIP 每回合只点一次：签名为 (剩余回合/分数/体力/手牌) 的语义状态。"""
    from gkagent.tasks.produce_ui import LessonPlayGuard

    guard = LessonPlayGuard()
    sig = (6, 473, 0, (6, 473, ((0, 29), (1, 0), (2, 24))))
    assert guard.skip_done(sig) is False
    guard.skip_sent(sig)
    assert guard.skip_done(sig) is True
    assert guard.skip_clicks == 1
    # 回合推进后签名变化：允许下一回合再 SKIP
    assert guard.skip_done((5, 473, 2, (5, 473, ((0, 19), (1, 24), (2, 12))))) is False
    guard.reset()
    assert guard.skip_done(sig) is False
    assert guard.skip_clicks == 0


def test_same_screen_guard_forces_skip_at_five() -> None:
    """同一屏连续 5 步无变化 → 强制 SKIP；之后不重复强制，交给退出兜底。"""
    from gkagent.tasks.produce_ui import SameScreenGuard

    guard = SameScreenGuard()
    digest = (6, 473, 0, (6, 473, ((0, 29), (1, 0), (2, 24))))
    assert [guard.observe(digest) for _ in range(4)] == [None, None, None, None]
    assert guard.observe(digest) == "force-skip"
    assert guard.forced_skips == 1
    # 第 6~9 步仍然同屏：不再重复强制（避免每步都点），只等第 10 步退出
    assert [guard.observe(digest) for _ in range(4)] == [None, None, None, None]
    assert guard.forced_skips == 1


def test_same_screen_guard_exits_at_ten() -> None:
    """同一屏连续 10 步无变化 → ``stuck``，调用方记 [stuck] 退出本局（返回失败）。"""
    from gkagent.tasks.produce_ui import SameScreenGuard

    guard = SameScreenGuard()
    digest = (6, 473, 0, (6, 473, ((0, 29), (1, 0), (2, 24))))
    results = [guard.observe(digest) for _ in range(10)]
    assert results[4] == "force-skip"
    assert results[:9].count("stuck") == 0
    assert results[9] == "stuck"
    assert guard.stuck_exits == 1
    # 画面变化（新回合/新分数）会重置计数，不会把正常出牌误判成卡死
    guard.observe(("new", 5, 480, 2, ()))
    assert guard.repeats == 1
    assert guard.observe(("new", 5, 480, 2, ())) is None


def test_stuck_lesson_ten_ticks_skips_once_then_forces_then_exits() -> None:
    """复刻 auto_produce 课程分支：0 体力同屏连喂 10 步。

    期望：第 1 步体力门点一次 SKIP；同回合不再重复点；第 5 步强制再点一次；
    第 10 步 ``stuck``（调用方记 [stuck] 退出本局，不再空转到超时）。
    """
    from gkagent.tasks.produce_ui import (
        LessonPlayGuard,
        SameScreenGuard,
        lesson_stamina_gate,
        lesson_turn_signature,
    )
    from gkagent.vision.lesson import LessonState

    state = LessonState(stamina=0, turns_left=6, score=473, cards=_gate_cards(4, 1, 4))
    same = SameScreenGuard()
    guard = LessonPlayGuard()
    skip_steps: list[int] = []
    outcome: str | None = None
    for step in range(1, 11):
        signature = lesson_turn_signature(state)
        outcome = same.observe(signature)
        if outcome == "stuck":
            break
        gate = lesson_stamina_gate(state, last_stamina=0)
        if gate is not None and (outcome == "force-skip" or not guard.skip_done(signature)):
            skip_steps.append(step)
            guard.skip_sent(signature)
    assert skip_steps == [1, 5], "每回合只点一次，只有同屏 5 步兜底才允许补一次"
    assert outcome == "stuck"
    assert same.stuck_exits == 1


def test_turn_end_dialog_uses_fixed_yes_point() -> None:
    """回合结束确认框固定点「是」的坐标。

    2026-11-16 真机 ep-exp4 step 85：旧实现用 find_button(("是",)) 在整屏 OCR 里
    找含「是」的文本，会点到卡名/问句上导致确认框不消失、课程卡死。改为固定坐标。
    """
    agent = FakeAgent()
    lines = _lines(
        "回合结束",
        "尚可使用技能卡",
        "确定要结束回合吗",
        "下次起不再显示",
        "否",
        "是",
    )
    result = _driver().decide(agent, lines)
    assert result.screen == "dialog"
    assert result.action == "end-turn-yes"
    from gkagent.tasks.produce_ui import TURN_END_YES

    assert agent.device.clicks[-1] == TURN_END_YES

def test_action_preview_confirms_at_last_point() -> None:
    driver = _driver()
    agent = FakeAgent()
    driver.decide(agent, _lines("请选择行动", "授课", "活动奖励"))
    result = driver.decide(agent, _lines("根据选项会发生各种效果。", "SELECT"))
    assert result.screen == "action-confirm"
    assert agent.device.clicks[-1] == _center(1)


def test_gain_overlay_taps_to_continue() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("活动奖励", "P+45", "审查基准 100"))
    assert result.screen == "result-tap"
    assert agent.device.clicks == [(360, 1000)]


def test_dialogue_taps_to_advance() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("美铃", "哎呀……这可真是麻烦了呢。"))
    assert result.screen == "story"
    assert agent.device.clicks == [(360, 1000)]


def test_activity_reward_settle_screen_taps() -> None:
    agent = FakeAgent()
    result = _driver().decide(agent, _lines("活动奖励", "P 59", "审查基准 100", "35/35"))
    assert result.screen == "result-tap"
    assert result.action == "settle"
    assert agent.device.clicks == [(360, 1000)]


def test_reward_dialog_with_activity_header_is_not_settle() -> None:
    agent = FakeAgent()
    lines = _lines("活动奖励", "请选择要领取的技能卡。", "推荐", "领取")
    result = _driver().decide(agent, lines)
    assert result.screen == "card-reward"


@dataclass
class FakeOcr:
    bottom_lines: list[OcrLine] = field(default_factory=list)
    top_lines: list[OcrLine] = field(default_factory=list)
    calls: list[tuple | None] = field(default_factory=list)

    def read(self, image, roi=None):
        self.calls.append(roi)
        driver = ProduceDriver(ocr=None)
        if roi == driver.bottom_roi:
            return self.bottom_lines
        if roi == driver.top_roi:
            return self.top_lines
        return []


def test_read_uses_bottom_roi_then_top_when_setup_text() -> None:
    bottom = OcrLine("下一步", 0.9, (40, 1100, 100, 40))
    top = OcrLine("选择支援卡", 0.9, (40, 30, 200, 40))
    ocr = FakeOcr(bottom_lines=[bottom], top_lines=[top])
    driver = ProduceDriver(ocr=ocr, sleep=lambda _s: None)
    lines = driver.read(None)
    assert ocr.calls[0] == driver.bottom_roi
    assert driver.top_roi in ocr.calls
    assert driver.text_of(lines) == "下一步 选择支援卡"


def test_read_skips_top_roi_without_setup_text() -> None:
    ocr = FakeOcr(
        bottom_lines=[
            OcrLine("确定", 0.9, (40, 1100, 100, 40)),
            OcrLine("继续", 0.9, (40, 1150, 100, 40)),
            OcrLine("关闭", 0.9, (40, 1200, 100, 40)),
        ]
    )
    driver = ProduceDriver(ocr=ocr, sleep=lambda _s: None)
    driver.read(None)
    assert ocr.calls == [driver.bottom_roi, driver.corner_roi]


def test_read_adds_top_roi_when_bottom_text_is_short() -> None:
    ocr = FakeOcr(bottom_lines=[OcrLine("确定", 0.9, (40, 1100, 100, 40))])
    driver = ProduceDriver(ocr=ocr, sleep=lambda _s: None)
    driver.read(None)
    assert driver.top_roi in ocr.calls


def test_retry_dialog_uses_free_retry() -> None:
    agent = FakeAgent()
    lines = _lines("再挑战确认", "不合格", "今天免费剩余1次", "剩余3次", "再挑战", "结束培育")
    result = _driver().decide(agent, lines)
    assert result.screen == "dialog"
    assert result.action == "retry"
    assert agent.device.clicks[-1] == _center(4)


def test_passed_result_continues_instead_of_retrying() -> None:
    agent = FakeAgent()
    lines = _lines("再挑战", "剩余3次", "下一步", "2nd", "442Pt")
    result = _driver().decide(agent, lines)
    assert result.screen == "dialog"
    assert result.action == "end-produce"
    assert agent.device.clicks[-1] == _center(2)


def test_retry_dialog_ends_when_no_attempts_left() -> None:
    agent = FakeAgent()
    lines = _lines("再挑战确认", "今天免费剩余0次", "剩余0次", "再挑战", "结束培育")
    result = _driver().decide(agent, lines)
    assert result.screen == "dialog"
    assert result.action == "end-produce"


@dataclass
class BusyDevice:
    def click_force(self, x: int, y: int) -> bool:
        return False


def test_user_busy_pauses_without_clicking() -> None:
    agent = FakeAgent(device=BusyDevice())
    result = _driver().decide(agent, _lines("请选择行动", "授课", "活动奖励"))
    assert result.screen == "pause"
    assert result.action == "user-active"
    assert result.ok


def _driver_attr_values(lines):
    from gkagent.tasks.produce_ui import ProduceDriver
    return ProduceDriver._attr_values(lines)


def test_attr_values_parsed_left_to_right() -> None:
    from gkagent.vision.ocr import OcrLine

    lines = [
        OcrLine("130/1000", 0.9, (120, 700, 80, 24)),
        OcrLine("100/1000", 0.9, (330, 700, 80, 24)),
        OcrLine("131/1000", 0.9, (520, 700, 80, 24)),
    ]
    assert _driver_attr_values(lines) == (130, 100, 131)
    assert _driver_attr_values(lines[:2]) is None


def test_choose_training_lowest_attribute(tmp_path, monkeypatch) -> None:
    from gkagent.vision.ocr import OcrLine

    driver = _driver()
    lines = [
        OcrLine("130/1000", 0.9, (120, 700, 80, 24)),
        OcrLine("100/1000", 0.9, (330, 700, 80, 24)),
        OcrLine("131/1000", 0.9, (520, 700, 80, 24)),
    ]
    monkeypatch.setattr(driver, "_produce_params", lambda: {"attr_choice": "lowest"})
    point, label = driver.choose_training("请选择行动 歌唱 舞蹈 视觉", lines)
    assert label == "Da"  # 100 最低
    from gkagent.tasks.produce_ui import TRAIN_DA

    assert point == TRAIN_DA


def test_produce_params_reads_all_keys(monkeypatch) -> None:
    """policy.json 里的 produce 段必须整段读进来（曾因只保留默认键而丢掉 attr_choice）。"""
    import json

    driver = _driver()
    params = driver._produce_params()
    raw = json.loads((DATA / "knowledge" / "policy.json").read_text(encoding="utf-8"))
    produce = raw["produce"]
    assert params["prefer_lesson"] is True
    assert "attr_choice" in params
    assert "lesson_every" in params
    # 值必须来自 policy.json，而不是代码默认值（校准后 rest_threshold 已从 8 调到 10）
    assert params["rest_threshold"] == produce["rest_threshold"]
    assert params["lesson_min_stamina"] == produce["lesson_min_stamina"]
    # 考试属性倍率（411%）也随 produce 段整段读入
    assert params["audition_coefficient"] == produce["audition_coefficient"] == 4.11
    assert set(produce) - {"source", "support_levels"} <= set(params)


# ---- 卡片详情浮层死循环 / SELECT 标签污染卡名 --------------------------------
def test_clean_card_name_strips_ui_labels() -> None:
    from gkagent.tasks.produce_ui import clean_card_name

    # OCR 把卡面左下角「SELECT」标签粘进卡名；单独标签行也要清成空名
    assert clean_card_name("流行词SELECT") == "流行词"
    assert clean_card_name("流行词 SELECT") == "流行词"
    assert clean_card_name("流行词  SEECT") == "流行词"
    for label in ("SELECT", "SEECT", "S", "A", "M", "select"):
        assert clean_card_name(label) == ""
    # 正常卡名 / 含字母但不是 UI 标签的名字不能被误伤
    assert clean_card_name("即兴表演") == "即兴表演"
    assert clean_card_name("SSR") == "SSR"


def test_real_detail_ocr_card_name_is_not_select() -> None:
    from gkagent.tasks.produce_ui import (
        clean_card_name,
        has_card_detail_overlay,
        overlay_card_name,
    )
    from gkagent.vision.ocr import OcrLine

    # 真机截图（step_030）同一帧的 OCR：浮层 + 卡名 + SELECT 标签
    lines = [
        OcrLine("流行词", 0.99, (316, 597, 87, 32)),
        OcrLine("好调状态的时候，可以使用", 1.0, (164, 669, 281, 24)),
        OcrLine("打分+38", 1.0, (163, 705, 92, 24)),
        OcrLine("SELECT", 1.0, (101, 1108, 84, 22)),
    ]
    assert has_card_detail_overlay(lines)
    assert overlay_card_name(lines) == "流行词"
    # 即使 OCR 把标签和卡名连成一行，也不能留下 SELECT
    assert clean_card_name("流行词SELECT") == "流行词"


def test_detail_overlay_does_not_repeat_same_card_point() -> None:
    from gkagent.tasks.produce_ui import CARD_DETAIL_BLANK, LessonPlayGuard

    guard = LessonPlayGuard()
    card_point = (123, 1008)
    guard.picked(card_point, "流行词")
    # 浮层刚弹出：允许点同一点确认一次
    assert guard.observe(True) == ("confirm", card_point)
    guard.confirm_clicked()
    # 确认后浮层还在：不能再点同一坐标，改点浮层外空白关闭、下一帧重新选牌
    action, point = guard.observe(True)
    assert action == "close"
    assert point == CARD_DETAIL_BLANK
    assert point != card_point
    guard.close_sent()
    assert guard.observe(False) == ("pick", None)


def test_three_same_point_failures_click_skip() -> None:
    from gkagent.tasks.produce_ui import LESSON_SKIP_POINT, LessonPlayGuard

    guard = LessonPlayGuard()
    point = (123, 1008)
    actions = []
    for _ in range(3):
        guard.picked(point, "流行词")
        assert guard.observe(True) == ("confirm", point)
        guard.confirm_clicked()
        actions.append(guard.observe(True))
    assert [action for action, _point in actions] == ["close", "close", "skip"]
    assert actions[-1][1] == LESSON_SKIP_POINT == (657, 800)
    assert point in guard.failed_points
    assert "流行词" in guard.failed_names


def test_dirty_card_name_falls_back_to_score_and_cost() -> None:
    from gkagent.tasks.produce_ui import clean_lesson_state, pick_lesson_card
    from gkagent.vision.lesson import LessonCard, LessonState

    cards = (
        LessonCard(
            index=0,
            box=(55, 895, 160, 185),
            point=(135, 987),
            name="SELECT",
            score=39,
            cost=3,
        ),
        LessonCard(
            index=1,
            box=(280, 895, 160, 185),
            point=(360, 987),
            name="即兴表演",
            score=6,
            cost=3,
        ),
    )
    state = LessonState(cards=cards)
    cleaned = clean_lesson_state(state)
    assert cleaned.cards[0].name == ""  # 脏名清洗后为空，不再沿用 SELECT
    assert cleaned.cards[1].name == "即兴表演"
    # 空名不等于没牌：按分数/费用重新选（39/3 > 6/3），不按脏名字
    pick = pick_lesson_card(cleaned.cards, stamina=19)
    assert pick is not None
    assert pick.point == (135, 987)
    assert pick.name == ""
    # 这张已确认打不出去 → 按分数/费用换下一张
    pick = pick_lesson_card(cleaned.cards, stamina=19, exclude_points={(135, 987)})
    assert pick is not None
    assert pick.point == (360, 987)
    assert pick.name == "即兴表演"


def test_selected_card_ui_label_detected_without_popup_ocr() -> None:
    from gkagent.tasks.produce_ui import has_selected_ui
    from gkagent.vision.lesson import LessonCard

    def _card(name: str) -> LessonCard:
        return LessonCard(index=0, box=(55, 895, 160, 185), point=(135, 987), name=name)

    assert has_selected_ui((_card("SELECT"),))
    assert has_selected_ui((_card("流行词SEECT"),))
    assert not has_selected_ui((_card("流行词"), _card("即兴表演")))


def test_confirm_click_without_hand_change_is_not_progress() -> None:
    from gkagent.tasks.produce_ui import LessonPlayGuard

    guard = LessonPlayGuard()
    point = (123, 1008)
    guard.picked(point, "流行词")
    assert guard.observe(True) == ("confirm", point)
    guard.confirm_clicked()
    # 第二击只把浮层关掉、分数/手牌没变：不能当成推进，也不许再点同一坐标
    action, next_point = guard.observe(False, progressed=False)
    assert action == "pick"
    assert next_point is None
    assert point in guard.failed_points
    assert "流行词" in guard.failed_names


def test_driver_card_detail_probe_and_name() -> None:
    import numpy as np

    from gkagent.tasks.produce_ui import CARD_DETAIL_NAME_BOX, ProduceDriver
    from gkagent.vision.ocr import OcrLine

    class FakeLineOcr:
        def line(self, image, roi, *, digits_only=False):
            if roi == CARD_DETAIL_NAME_BOX:
                return OcrLine("流行词SELECT", 0.95, roi)
            return OcrLine("打分+38", 0.95, roi)

    image = np.zeros((1280, 720, 3), dtype=np.uint8)
    driver = ProduceDriver(ocr=FakeLineOcr(), sleep=lambda _seconds: None)
    assert driver.card_detail_open(image) is True
    assert driver.card_detail_name(image) == "流行词"


def test_card_detail_text_recognises_exam_wording() -> None:
    """考试（audition）浮层用「得分+23」「考试·舞台中仅限1次」，旧规则只认「打分+」（ep-t1-e 死循环）。"""
    from gkagent.tasks.produce_ui import is_card_detail_text

    assert is_card_detail_text("得分+23（集中效果会2倍生效）")
    assert is_card_detail_text("考试·舞台中仅限1次")
    assert is_card_detail_text("Active")
    assert is_card_detail_text("好调状态的时候，可以使用")
    assert not is_card_detail_text("")
    assert not is_card_detail_text("剩余回合 5")


def test_lesson_hand_signature_ignores_select_label_and_raise() -> None:
    from gkagent.tasks.produce_ui import lesson_hand_signature
    from gkagent.vision.lesson import LessonCard, LessonState

    def _card(name: str, point: tuple[int, int]) -> LessonCard:
        return LessonCard(
            index=0,
            box=(point[0] - 80, point[1] - 90, 160, 185),
            point=point,
            name=name,
            score=39,
            cost=3,
        )

    before = LessonState(score=120, turns_left=4, cards=(_card("流行词", (135, 1013)),))
    # 选中态：卡被抬高 + 卡名框读到 SELECT；这不算出牌推进
    selected = LessonState(score=120, turns_left=4, cards=(_card("SELECT", (135, 988)),))
    assert lesson_hand_signature(before) == lesson_hand_signature(selected)
    # 真正出牌后总分/手牌至少变一项
    played = LessonState(score=159, turns_left=4, cards=(_card("即兴表演", (360, 1013)),))
    assert lesson_hand_signature(played) != lesson_hand_signature(before)


# ------------------------------------------------------- 三维专用 ROI（read_attrs）
class _StubAttrOcr:
    """只实现 read_attrs 用到的 line()/read()：按小框返回预置文本，可记调用。"""

    def __init__(
        self,
        texts: dict[tuple[int, int, int, int], str] | None = None,
        *,
        full_lines: list[OcrLine] | None = None,
    ) -> None:
        self.texts = {tuple(roi): text for roi, text in (texts or {}).items()}
        self.full_lines = list(full_lines or [])
        self.line_calls: list[tuple[int, int, int, int]] = []
        self.read_calls = 0

    def line(self, image, roi, **_kwargs) -> OcrLine | None:
        self.line_calls.append(tuple(roi))
        text = self.texts.get(tuple(roi))
        return None if text is None else OcrLine(text, 0.99, tuple(roi))

    def read(self, image, roi=None) -> list[OcrLine]:
        self.read_calls += 1
        return list(self.full_lines)


def _attr_image():
    import numpy as np

    return np.zeros((1280, 720, 3), dtype=np.uint8)


def _attr_ocr(values: tuple[str | None, str | None, str | None], **kwargs) -> _StubAttrOcr:
    texts = {
        roi: text
        for roi, text in zip(produce_ui.ATTR_ROIS, values)
        if text is not None
    }
    return _StubAttrOcr(texts, **kwargs)


def test_read_attrs_reads_three_fixed_boxes() -> None:
    ocr = _attr_ocr(("312", "215", "351"))
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    assert driver.read_attrs(_attr_image()) == (312, 215, 351)
    assert ocr.line_calls == list(produce_ui.ATTR_ROIS)
    assert ocr.read_calls == 0


def test_read_attrs_returns_none_when_a_box_is_missing() -> None:
    ocr = _attr_ocr(("312", None, "351"))
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    assert driver.read_attrs(_attr_image()) is None
    # 只缺一个框不跑整图兜底（全图 OCR ~5s，不能每步都跑）
    assert ocr.read_calls == 0


def test_read_attrs_prefers_value_over_1000_denominator() -> None:
    # 真机小框里常同时读到「312」和分母「1000」（OCR 可能连斜杠一起丢）
    ocr = _attr_ocr(("312 1000", "215/1000", "/1000 351"))
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    assert driver.read_attrs(_attr_image()) == (312, 215, 351)


def test_read_attrs_rejects_out_of_range_number() -> None:
    ocr = _attr_ocr(("2500", "215", "351"))
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    assert driver.read_attrs(_attr_image()) is None
    assert ocr.read_calls == 0


def test_read_attrs_falls_back_to_full_ocr_when_two_boxes_miss() -> None:
    full_lines = [
        OcrLine("473", 0.99, (606, 44, 74, 37)),  # 顶部分数：不在属性行
        OcrLine("130", 0.99, (192, 683, 77, 36)),
        OcrLine("1000", 0.99, (188, 718, 67, 26)),  # 分母：字高比大数字矮
        OcrLine("100", 0.99, (333, 682, 78, 36)),
        OcrLine("131", 0.99, (478, 680, 79, 39)),
        OcrLine("19.5%", 0.90, (455, 751, 87, 23)),
        OcrLine("16.4%", 0.90, (311, 754, 86, 20)),
    ]
    ocr = _attr_ocr(("130", None, None), full_lines=full_lines)
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    assert driver.read_attrs(_attr_image(), allow_full=True) == (130, 100, 131)
    assert ocr.read_calls == 1


def test_read_attrs_skips_full_ocr_when_all_boxes_blank() -> None:
    full_lines = [OcrLine("130", 0.99, (192, 683, 77, 36))]
    ocr = _attr_ocr((None, None, None), full_lines=full_lines)
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    assert driver.read_attrs(_attr_image()) is None
    # 非行动页每步都会失败：这里绝不能触发整图 OCR
    assert ocr.read_calls == 0


def test_read_attrs_full_fallback_when_all_boxes_blank_on_action_page() -> None:
    """UI 彻底漂移（三个固定框全空）时，用「请选择行动」确认是行动页再整图兜底。"""
    full_lines = [
        OcrLine("130", 0.99, (192, 683, 77, 36)),
        OcrLine("1000", 0.99, (188, 718, 67, 26)),
        OcrLine("100", 0.99, (333, 682, 78, 36)),
        OcrLine("131", 0.99, (478, 680, 79, 39)),
        OcrLine("19.5%", 0.90, (455, 751, 87, 23)),
    ]
    ocr = _StubAttrOcr(
        {produce_ui.ATTR_ACTION_TITLE_BOX: "请选择行动"},
        full_lines=full_lines,
    )
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    assert driver.read_attrs(_attr_image(), allow_full=True) == (130, 100, 131)
    assert ocr.read_calls == 1


def test_read_attrs_debug_reports_each_box_text() -> None:
    ocr = _attr_ocr(("312", None, "351/1000"))
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    report = driver.read_attrs_debug(_attr_image())
    assert report["attrs"] is None
    assert [box["attr"] for box in report["boxes"]] == ["vo", "da", "vi"]
    assert [box["roi"] for box in report["boxes"]] == list(produce_ui.ATTR_ROIS)
    assert [box["text"] for box in report["boxes"]] == ["312", "", "351/1000"]
    assert [box["value"] for box in report["boxes"]] == [312, None, 351]
    assert ocr.read_calls == 0


def test_read_attrs_reads_drawn_attribute_numbers() -> None:
    """构图：三块大数字画进三个 ROI，真 OCR 应读出 (312, 215, 351)。"""
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2
    import numpy as np

    image = np.full((1280, 720, 3), 40, dtype=np.uint8)
    for roi, value in zip(produce_ui.ATTR_ROIS, ("312", "215", "351")):
        x, y, width, height = roi
        size = cv2.getTextSize(value, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 4)[0]
        org = (x + (width - size[0]) // 2, y + (height + size[1]) // 2)
        cv2.putText(
            image, value, org, cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 4, cv2.LINE_AA
        )
    assert ProduceDriver(sleep=lambda _seconds: None).read_attrs(image) == (312, 215, 351)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("produce_actions.png", (130, 100, 131)),
        ("g5.png", (178, 215, 280)),
    ],
)
def test_read_attrs_on_real_action_frame(name: str, expected: tuple[int, int, int]) -> None:
    """实拍回归：真机行动页的三个大属性数字（/1000 小字上方）。"""
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2

    path = DATA / name
    if not path.exists():
        pytest.skip(f"缺少实拍帧 {path}")
    image = cv2.imread(str(path))
    assert image is not None
    assert ProduceDriver(sleep=lambda _seconds: None).read_attrs(image) == expected


def test_read_attrs_step_047_real_frame_when_action_page() -> None:
    """step_NNN.png 每个 episode 都从 001 重写，可能已被课程页覆盖。

    能读出三维就校验范围；读不到（不是行动页/被真机运行覆写）就 skip。
    不在测试里硬编码某次真机的 312/215/351——那张图没有留底。
    """
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2

    path = DATA / "auto" / "step_047.png"
    if not path.exists():
        pytest.skip("缺少实拍帧 data/auto/step_047.png")
    image = cv2.imread(str(path))
    assert image is not None
    attrs = ProduceDriver(sleep=lambda _seconds: None).read_attrs(image)
    if attrs is None:
        pytest.skip("step_047 当前不是行动页（data/auto 正被真机运行持续覆写）")
    assert all(0 <= value <= produce_ui.ATTR_MAX for value in attrs)

# ---- F#15：结算/收尾画面（评价 → 回忆照片选择 → 培育记录 → 主页） ----------
def test_settlement_keywords_recognised() -> None:
    """结算类关键词必须命中；行动页的「请选择行动」不能被误判成结算页。"""
    assert produce_ui.is_memory_photo_screen("请选择要作为回忆的照片")
    assert produce_ui.is_memory_photo_screen("保存到本地 保存到相册")
    assert produce_ui.is_settlement_screen("请选择要作为回忆的照片")
    assert produce_ui.is_settlement_screen("保存到本地 保存到相册")
    assert produce_ui.is_settlement_screen("评价 下一步")
    assert produce_ui.is_settlement_screen("培育结算 确定")
    assert produce_ui.is_settlement_screen("SNS 投稿")
    assert produce_ui.is_record_screen("培育记录 编成支援卡/回忆 最终持有P道具")

    # 行动页/编成页/空文本都不是结算页（「请选择」单独出现不算）
    assert not produce_ui.is_settlement_screen("请选择行动 授课 活动奖励 休息")
    assert not produce_ui.is_settlement_screen("请选择偶像 下一步")
    assert not produce_ui.is_settlement_screen("")
    assert not produce_ui.is_memory_photo_screen("请选择行动 授课")
    assert not produce_ui.is_record_screen("选择支援卡 自动 下一步")
    # 支援卡页「自动」弹出的确认框含「编成支援卡」子串，但不是培育记录页（ep-t1-c 空转 12 次）
    assert not produce_ui.is_record_screen(
        "自动编成 将自动编成支援卡 ※当前编成未保存 取消 确定"
    )
    assert produce_ui.is_record_screen("培育记录 编成支援卡/回忆 最终持有P道具")


def test_memory_photo_screen_selects_first_photo_then_saves() -> None:
    """回忆照片选择页：先选第一张照片，再点「保存到相册」（不点顶部说明文字）。"""
    agent = FakeAgent()
    lines = _lines("请选择要作为回忆的照片", "自动拍摄", "保存到本地", "保存到相册")
    result = _driver().decide(agent, lines)
    assert result.screen == "settlement"
    assert result.action == "save-memory"
    assert agent.device.clicks == [
        produce_ui.MEMORY_FIRST_PHOTO,
        _center(3),  # 「保存到相册」文字行中心
    ]


def test_memory_photo_page_is_not_unknown_tap() -> None:
    """真机 OCR（data/settlement_photo_select.png）只有按钮文字也要认出来，不能走 unknown-tap。"""
    agent = FakeAgent()
    lines = _lines("取消", "日", "回忆", "保存到本地", "保存到相册")
    result = _driver().decide(agent, lines)
    assert result.screen == "settlement"
    assert result.action == "save-memory"
    assert result.screen != "unknown-tap"


def test_real_record_ocr_text_never_enters_scenario() -> None:
    """真机 step_055 的 OCR 文本（含「定期公演」）必须以 record/close 收尾，绝不走 scenario。"""
    agent = FakeAgent()
    lines = _lines(
        "支援卡",
        "编成支援卡/回忆",
        "最终持有P道具",
        "培育记录",
        "定期公演『初』",
        "Regular",
    )
    result = _driver().decide(agent, lines)
    assert result.screen == "record"
    assert result.action == "close"
    assert agent.device.clicks[-1] == produce_ui.PRODUCE_RECORD_CLOSE
    assert result.screen != "scenario"


def test_scenario_stalls_degrade_to_center_then_stuck() -> None:
    """F#15：同屏 5 次 → 改点 (360,1000)；再 5 次 → 返回 stuck 退出（不再空转到超时）。"""
    agent = FakeAgent()
    driver = _driver()
    lines = _lines("培育", "定期公演「初」", "研修")
    for _ in range(driver.scenario_degrade_after):
        result = driver.decide(agent, lines)
        assert result.screen == "scenario"
        assert agent.device.clicks[-1] == produce_ui.REGULAR_DIFFICULTY
    for _ in range(driver.scenario_exit_after - driver.scenario_degrade_after):
        result = driver.decide(agent, lines)
        assert result.screen == "scenario-fallback"
        assert agent.device.clicks[-1] == (360, 1000)
    stuck = driver.decide(agent, lines)
    assert stuck.screen == "stuck"
    assert stuck.ok is False
    assert "scenario-loop" in stuck.describe()


def test_scenario_streak_resets_when_leaving_produce_page() -> None:
    """离开培育页（主页/剧情）后计数必须清零，避免几十分钟后误判 stuck。"""
    agent = FakeAgent()
    driver = _driver()
    lines = _lines("培育", "定期公演「初」", "研修")
    for _ in range(3):
        driver.decide(agent, lines)
    driver.decide(agent, _lines("亲密度", "活动经费", "主页", "商店"))  # 回主页
    assert driver.scenario_streak == 0
    result = driver.decide(agent, lines)
    assert result.screen == "scenario"  # 重新从第 1 次算起


def test_settlement_streak_degrades_then_exits() -> None:
    """结算页连续点不动也要有退出条件（F#15 教训：进入模式必须有退出）。"""
    agent = FakeAgent()
    driver = _driver()
    lines = _lines("请选择要作为回忆的照片", "保存到本地", "保存到相册")
    for _ in range(driver.settlement_degrade_after):
        result = driver.decide(agent, lines)
        assert result.screen == "settlement"
        assert result.action == "save-memory"
    for _ in range(driver.settlement_exit_after - driver.settlement_degrade_after):
        result = driver.decide(agent, lines)
        assert result.action == "tap-center"
        assert agent.device.clicks[-1] == (360, 1000)
    stuck = driver.decide(agent, lines)
    assert stuck.screen == "stuck"
    assert stuck.ok is False


# ---------------------------------------------------------------- 授课答题屏


def test_class_quiz_chooses_answer_row_not_fast_forward() -> None:
    """初模式「授课」答题屏：三个属性答案 + 審査基準 + 右下「快进」。

    真机 ep-finish1：旧逻辑看到「快进」就点快进 → 弹「是否快进」→ 回来 → 无限循环；
    这里必须点答案行（默认第一行 Vo），不能点快进。
    """
    agent = FakeAgent()
    lines = _lines(
        "授课",
        "審査基準",
        "快进",
        "言葉を届ける力",
        "きれいな姿勢と所作",
        "清楚なたたずまい",
    )
    result = _driver().decide(agent, lines)
    assert result.screen == "class-quiz"
    assert result.action == "choose-Vo"
    assert agent.device.clicks[-1] == produce_ui.CLASS_QUIZ_ROWS[0]


def test_class_quiz_follows_selected_attribute() -> None:
    """课程类型选择里选过 Vi（视觉）时，答题屏点第三行。"""
    agent = FakeAgent()
    driver = _driver()
    driver.lesson_attribute = "Vi"
    lines = _lines("授课", "審査基準", "快进", "A", "B", "C")
    result = driver.decide(agent, lines)
    assert result.screen == "class-quiz"
    assert agent.device.clicks[-1] == produce_ui.CLASS_QUIZ_ROWS[2]


def test_class_quiz_detection_ignores_reward_popup() -> None:
    """答题屏背后的课程 HUD（審査基準/授课）在领奖弹窗上仍然可见，不能误判成答题屏。

    真机 ep-finish2：点完答案弹出「请选择要领取的技能卡」，每步仍被当成 class-quiz
    点 (360,730) 空白 → 13 步卡死。
    """
    agent = FakeAgent()
    lines = _lines(
        "授课",
        "審査基準",
        "请选择要领取的技能卡。",
        "领取",
        "再抽选",
    )
    result = _driver().decide(agent, lines)
    assert result.screen != "class-quiz"
