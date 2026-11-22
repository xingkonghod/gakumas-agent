"""F#42 回归：课程"硬打必须得分"（ep-t3-4 真机课程帧回放）。

真机现象（2026-11-22 ep-t3-3/4 舞蹈课）：最后一回合、本课 0 分（圆环「CLEAR截止 30」
= 还差 30 分）、手牌 魅力的基础(29) / 表情的基础(buff) / 轻快步伐(23)，bot 选了 buff
→ 本课 0 分 FAILED。用户现场："训练舞蹈时一直选 buff 牌，一分没得，failed 了"。

根因（见 docs/FAILURES.md #42）：
1. 课程 HUD 读错：右上角是培育属性值（不是课程分），圆环「CLEAR截止 N」是**还差 N 分**；
   旧代码当成"分数 90 ≥ CLEAR 线 30，已经 PERFECT"→ expectimax 建议 SKIP →
   禁跳规则按动作价值硬打，buff 牌排在前面；
2. 每回合出牌上限写死 3（实际默认 1 张，额外次数来自卡效果/P 道具）→ 搜索以为
   一回合能"buff + 两刀"，于是每回合都先铺 buff。

本文件用真机帧跑生产链路（``LessonReader`` → ``LessonPolicy(engine="expectimax")``）：
必须打正分牌，不能选 buff、不能 SKIP。fixture 是 ep-t3-4 step1 的课程帧
（与 ep-t3-3 step286 是同一屏——当时两个进程重叠，日志记录在 ep-t3-3 step290 FAILED）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ocr_jp.example.yaml"
MODEL_DIR = ROOT / "data" / "models" / "ocr_jp"
FRAME = ROOT / "tests" / "fixtures" / "lesson_ep_t3_4_step001.png"

pytestmark = [
    pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml"),
    pytest.mark.skipif(
        not all((MODEL_DIR / name).is_file() for name in ("det.onnx", "rec.onnx", "keys.txt")),
        reason="缺少日文 OCR 模型（先跑 scripts/download_ocr_models.py）",
    ),
    pytest.mark.skipif(not FRAME.is_file(), reason="缺少 F#42 课程帧 fixture"),
]


@pytest.fixture(scope="module")
def reader():
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2  # noqa: F401 - 确认 cv2 可用

    from gkagent.vision.lesson import LessonReader
    from gkagent.vision.ocr import OcrEngine

    return LessonReader(OcrEngine(config_path=CONFIG))


@pytest.fixture(scope="module")
def frame_state(reader):
    import cv2

    image = cv2.imread(str(FRAME))
    assert image is not None
    reader.reset_lesson()
    return reader.read(image, kind="lesson")


def _policy(tmp_path: Path):
    from gkagent.policy.lesson import LessonPolicy

    # 走代码默认参数（不受仓库 policy.json 后续调参影响），显式开 expectimax。
    return LessonPolicy(params_path=tmp_path / "missing.json", engine="expectimax")


def test_ep_t3_4_frame_maps_hud_to_relative_score(frame_state) -> None:
    """HUD 换算：属性值 90 / 「CLEAR截止 30」→ 课程分 0、过关线 30、满分线 60。"""
    state = frame_state
    assert state.turns_left == 1
    assert state.goal == "clear"
    assert state.attr == 90  # 右上角：培育属性值（不是课程分）
    assert state.score == 0  # 本课一分没得
    assert (state.gauge, state.perfect) == (30, 60)  # 还差 30 过关，满分 60
    names = {card.name: card for card in state.cards}
    assert {"魅力的基础", "表情的基础", "轻快步伐"} <= set(names)
    assert names["魅力的基础"].total_score == 29
    assert names["轻快步伐"].total_score == 23


def test_ep_t3_4_final_turn_plays_scoring_card_not_buff(reader, frame_state, tmp_path) -> None:
    """DoD：同一帧回放不再选 buff——硬打要打屏幕分最高的正分牌（魅力的基础 29）。"""
    action = _policy(tmp_path).decide(frame_state)
    assert action.kind == "card", action.reason
    assert action.card is not None
    assert action.card.name == "魅力的基础"
    assert action.card.total_score > 0
    # 反例白名单：绝不能选 buff 牌（表情的基础）——它不产生课程分。
    assert action.card.name != "表情的基础"


def test_buff_heavy_low_score_prefers_scoring_card(tmp_path) -> None:
    """DoD：单测覆盖"buff 多 / 分数少"——2 张 buff 在手也要先打分牌。"""
    from gkagent.policy.lesson import LessonPolicy
    from gkagent.vision.lesson import LessonCard, LessonState

    def card(index: int, name: str, score: int, cost: int, *, buff=False, text="") -> LessonCard:
        return LessonCard(
            index=index,
            box=(index * 200, 900, 190, 232),
            point=(index * 200 + 95, 1000),
            name=name,
            score=score,
            cost=cost,
            buff=buff,
            text=text,
        )

    state = LessonState(
        kind="lesson",
        turns_left=2,
        total_turns=6,
        score=0,
        gauge=30,
        perfect=60,
        stamina=36,
        cards=(
            card(0, "表情的基础", 0, 1, buff=True, text="元气+1 集中+2"),
            card(1, "表现的基础", 0, 0, buff=True, text="元气+4"),
            card(2, "魅力的基础", 9, 4, text="打分+9"),
            card(3, "击掌", 23, 4, text="打分+23"),
        ),
    )
    policy = LessonPolicy(params_path=tmp_path / "missing.json", engine="expectimax")
    action = policy.decide(state)
    assert action.kind == "card", action.reason
    assert action.card is not None
    assert not action.card.buff
    assert action.card.total_score > 0
