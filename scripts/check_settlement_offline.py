"""离线验证结算页识别（F#15）：不碰游戏窗口，只用真实截图跑 ``driver.decide()``。

用法（venv，任何 cwd）：
    .venv\\Scripts\\python.exe scripts\\check_settlement_offline.py
    .venv\\Scripts\\python.exe scripts\\check_settlement_offline.py 某张截图.png

覆盖两张真机 720x1280 截图：
- ``data/settlement_photo_select.png``：培育结束后的「回忆照片选择」页
  （请选择要作为回忆的照片 / 保存到本地 / 保存到相册）。这是 data/new_account.png
  在 16:22 时的内容，16:26 被别的截图覆盖，故另存一份做 golden。
- ``data/auto/step_055.png``：培育记录详情弹窗（标题含「定期公演『初』 Regular」），
  ep-cplus13 最后 11 步 ``[scenario] regular`` 就停在这屏。

退出码 0 = 全部识别为结算/收尾画面，且不再走 ``[scenario]``；1 = 仍有误判。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2

from gkagent.tasks import produce_ui
from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrEngine

# (相对路径, 允许的识别结果, 期望动作)
CASES: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    ("data/settlement_photo_select.png", ("settlement",), "save-memory"),
    ("data/auto/step_055.png", ("record", "settlement"), "close"),
)


@dataclass
class FakeDevice:
    """只记录点击落点，不碰 Win32。"""

    clicks: list[tuple[int, int]] = field(default_factory=list)

    def click_force(self, x: int, y: int, delay: float = 0.4) -> bool:
        self.clicks.append((int(x), int(y)))
        return True


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)


def _check(path: Path, allowed: tuple[str, ...], action: str | None, engine: OcrEngine) -> bool:
    image = cv2.imread(str(path))
    if image is None:
        print(f"[SKIP] 读不到图片：{path}")
        return False
    driver = ProduceDriver(ocr=engine, sleep=lambda _seconds: None)
    # 与真机同一条取词路径：底部 ROI（按钮区）+ 左上角状态条 + 按需顶部
    lines = driver.read(image)
    text = driver.text_of(lines)
    agent = FakeAgent()
    tick = driver.decide(agent, lines, image)

    print(f"=== {path.relative_to(ROOT)}  shape={image.shape} ===")
    print("OCR 行：")
    for line in lines:
        print(f"  {tuple(int(v) for v in line.box)}  {line.text}")
    print(f"OCR 全文：{text}")
    print(f"识别结果：{tick.describe()}")
    print(f"点击落点：{agent.device.clicks}")
    print(
        "常量核对：回忆照片第一张 "
        f"{produce_ui.MEMORY_FIRST_PHOTO} / 保存到相册 {produce_ui.MEMORY_SAVE_ALBUM} / "
        f"培育记录关闭 {produce_ui.PRODUCE_RECORD_CLOSE}"
    )

    ok = tick.screen in allowed and tick.screen != "scenario"
    if action is not None:
        ok = ok and tick.action == action
    print(f"结论：{'PASS' if ok else 'FAIL'}（screen={tick.screen}, action={tick.action}）\n")
    return ok


def main(argv: list[str]) -> int:
    engine = OcrEngine()
    if argv:
        cases = tuple(
            (arg, ("settlement", "record", "dialog"), None) for arg in argv
        )
    else:
        cases = CASES
    results: list[bool] = []
    for rel, allowed, action in cases:
        path = Path(rel)
        if not path.is_absolute():
            path = ROOT / path
        results.append(_check(path, allowed, action, engine))
    print(f"汇总：{sum(results)}/{len(results)} 张截图按预期识别，且没有一张走 [scenario]")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
