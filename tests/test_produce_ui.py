"""ProduceDriver：只验证「这一屏点哪里」的规则，不碰真机。"""

from __future__ import annotations

from dataclasses import dataclass, field

from gkagent.tasks import produce_ui
from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrLine


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
    lines = _lines("请选择行动", "10/35", "休息", "授课")
    result = _driver().decide(agent, lines)
    assert result.screen == "action"
    assert result.action == "rest"


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


def test_retry_confirm_cancels_to_save_stamina() -> None:
    agent = FakeAgent()
    lines = _lines("再挑战确认", "基础研修", "取消", "再次挑战")
    result = _driver().decide(agent, lines)
    assert result.screen == "dialog"
    assert result.action == "cancel-retry"
    assert agent.device.clicks[-1] == _center(2)


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
