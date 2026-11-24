"""F#46 回归：v3.6.1 技能卡强化屏无分支 → story/tap 空转（真机 ep-t31-b）。

现象：培育中弹出技能卡强化屏（「未选择技能卡」×2 + 卡片网格 + 底部「强化」），
旧 decide 无对应分支 → 落 story/tap 点中央 (360,1000) 空转 100+ 步（traffic 4 分钟无新 API）。

交互链（2026-11-24 实证）：
① 状态1「未选择技能卡」→ 点网格第一张卡 (140,755) 选中；
② 状态2 出现「强化确认」（预览）+ 底部大「强化」变亮 → 点底部「强化」(360,1160) 执行；
③ 「技能卡强化后详情」弹窗 →「关闭」（既有按钮分支）→ 卡牌展示对白「X已强化。」（story/tap）。

修复（produce_ui 4.46）：状态2 点底部「强化」；状态1 点网格第一张卡。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrLine

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ocr_jp.example.yaml"
MODEL_DIR = ROOT / "data" / "models" / "ocr_jp"
FIXTURES = ROOT / "tests" / "fixtures"
STATE2_FRAME = FIXTURES / "enhance_state2_ep_t31_b.png"


@dataclass
class FakeDevice:
    clicks: list[tuple[int, int]] = field(default_factory=list)

    def click_force(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))

    def click(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)


def _driver() -> ProduceDriver:
    return ProduceDriver(sleep=lambda _seconds: None)


def test_enhance_state1_picks_first_grid_card() -> None:
    """状态1：未选择技能卡 + 网格 → 点第一张卡选中，不落 story/tap。"""
    lines = [
        OcrLine("强化", 0.95, (60, 40, 120, 40)),
        OcrLine("未选择技能卡", 0.95, (280, 230, 200, 36)),
        OcrLine("未选择技能卡", 0.95, (280, 530, 200, 36)),
        OcrLine("9", 0.9, (80, 700, 30, 30)),
        OcrLine("强化", 0.95, (320, 1140, 120, 44)),
        OcrLine("本日もお願いします。", 0.9, (78, 1019, 250, 27)),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines)
    assert (tick.screen, tick.action) == ("enhance", "pick-card"), tick.describe()
    assert agent.device.clicks[-1] == (140, 755)


def test_enhance_state2_clicks_big_go_button() -> None:
    """状态2：强化确认（预览）在场 → 点底部大「强化」执行，不是点预览/中央。"""
    lines = [
        OcrLine("强化", 0.95, (60, 40, 120, 40)),
        OcrLine("魅力的基础", 0.95, (200, 110, 200, 36)),
        OcrLine("打分+9", 0.95, (230, 160, 120, 30)),
        OcrLine("强化确认", 0.95, (60, 270, 130, 36)),
        OcrLine("魅力的基础+", 0.95, (200, 420, 220, 36)),
        OcrLine("打分+14", 0.95, (230, 470, 130, 30)),
        OcrLine("强化", 0.95, (320, 1140, 120, 44)),
        OcrLine("本日もお願いします。", 0.9, (78, 1019, 250, 27)),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines)
    assert (tick.screen, tick.action) == ("enhance", "go"), tick.describe()
    assert agent.device.clicks[-1] == (360, 1160)


def test_drink_detail_popup_closes_not_center() -> None:
    """F#47：P饮料详情模态弹窗（元气+7 + 关闭）→ 点关闭，不是点中央空白（tap-lost）。"""
    lines = [
        OcrLine("P饮料详情", 0.95, (60, 140, 200, 40)),
        OcrLine("乌龙茶", 0.95, (210, 230, 120, 36)),
        OcrLine("元气+7", 0.95, (230, 270, 120, 30)),
        OcrLine("元气", 0.95, (110, 440, 80, 36)),
        OcrLine("由于技能卡或者干扰导致体力减少时，作为体力的替代进行消耗", 0.9, (75, 490, 500, 60)),
        OcrLine("关闭", 0.95, (320, 1140, 120, 44)),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines)
    assert (tick.screen, tick.action) == ("toast", "close-detail"), tick.describe()
    assert agent.device.clicks[-1][1] > 1000, "应点底部关闭按钮"


def test_drink_use_dialog_cancels() -> None:
    """F#47：饮料使用/丢弃确认态（取消/使用，无关闭）→ 点取消收起。"""
    lines = [
        OcrLine("P饮料详情", 0.95, (60, 850, 200, 40)),
        OcrLine("乌龙茶", 0.95, (190, 930, 120, 36)),
        OcrLine("元气+7", 0.95, (210, 980, 120, 30)),
        OcrLine("丢弃", 0.95, (560, 920, 80, 36)),
        OcrLine("取消", 0.95, (160, 1140, 120, 44)),
        OcrLine("使用", 0.95, (460, 1140, 120, 44)),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines)
    assert (tick.screen, tick.action) == ("toast", "cancel-drink"), tick.describe()
    assert agent.device.clicks[-1][1] > 1000


def test_enhance_state3_detail_closes_via_button_branch() -> None:
    """状态3：技能卡强化后详情 + 关闭 → 走既有按钮分支点关闭。"""
    lines = [
        OcrLine("强化", 0.95, (60, 40, 120, 40)),
        OcrLine("技能卡强化后详情", 0.95, (60, 140, 300, 40)),
        OcrLine("魅力的基础+", 0.95, (210, 230, 220, 36)),
        OcrLine("打分+14", 0.95, (230, 280, 130, 30)),
        OcrLine("关闭", 0.95, (320, 1140, 120, 44)),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines)
    assert (tick.screen, tick.action) == ("enhance", "close-detail"), tick.describe()
    assert agent.device.clicks[-1][1] > 1000


@pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml")
@pytest.mark.skipif(
    not all((MODEL_DIR / n).is_file() for n in ("det.onnx", "rec.onnx", "keys.txt")),
    reason="缺少日文 OCR 模型",
)
def test_enhance_state2_real_frame() -> None:
    """真机 ep-t31-b 强化状态2 帧：read_fast → decide 必须 enhance/go。"""
    import cv2

    pytest.importorskip("rapidocr_onnxruntime")
    from gkagent.vision.ocr import OcrEngine

    if not STATE2_FRAME.is_file():
        pytest.skip("缺少 fixture enhance_state2_ep_t31_b.png")
    image = cv2.imread(str(STATE2_FRAME))
    ocr = OcrEngine(config_path=CONFIG)
    lines = _driver().read_fast(image)
    agent = FakeAgent()
    tick = _driver().decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("enhance", "go"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert y > 1000, f"应点底部强化按钮，实际 ({x},{y})"