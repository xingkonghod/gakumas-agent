"""离线验收：sim 实时出牌在三张真机审查手牌上的期望分与最终选择。

用法（venv，任何 cwd）：
    .venv\\Scripts\\python.exe scripts\\check_play_choice_offline.py

手牌来自 lead 的最终审查（ep-aud3）：
  在我发现的世界（cost 4，纯 buff）/ 试行错误+（84 分 / 5 费）/ 轻快步伐（25 分 / 4 费）。
卡片数值走真实 ``data/knowledge/card_table.json``（cost/效果），屏幕宝石分数优先。
退出码 0 = 三张牌都算出期望分且能给出选择。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.policy.lesson import LessonPolicy  # noqa: E402
from gkagent.sim.lesson import LessonSim  # noqa: E402
from gkagent.sim.play_choice import (  # noqa: E402
    choose_card_via_sim,
    estimate_hand,
    specs_from_hand,
)
from gkagent.vision.lesson import LessonCard, LessonState  # noqa: E402

TURNS_LEFT = 3
# 真机审查那回合体力吃紧：只够打一张大牌（84/5 与 25/4 不能同时打）
STAMINA = 8
EPISODES = 8


def _card(
    index: int,
    name: str,
    *,
    cost: int,
    score: int | None = None,
    hits: int | None = None,
) -> LessonCard:
    return LessonCard(
        index=index,
        box=(40 + index * 200, 890, 180, 220),
        point=(140 + index * 200, 1000),
        name=name,
        score=score,
        hits=hits,
        cost=cost,
    )


HAND = [
    _card(0, "在我发现的世界", cost=4),
    _card(1, "试行错误+", cost=5, score=42, hits=2),
    _card(2, "轻快步伐", cost=4, score=25, hits=1),
]


def main() -> int:
    play_cards = specs_from_hand(HAND)
    deck = [item.spec for item in play_cards]
    print(f"局面：剩余 {TURNS_LEFT} 回合，体力 {STAMINA}，episodes={EPISODES}")
    print("手牌 → CardSpec（cost 用卡表真值，分数优先屏幕宝石）：")
    for item in play_cards:
        print(
            f"  [{item.index}] {item.name}: cost={item.cost} "
            f"score={item.spec.score:.0f} buff={item.spec.condition}/"
            f"focus={item.spec.focus}/draw={item.spec.draw} "
            f"estimated={item.estimated}"
        )

    estimates = estimate_hand(
        HAND, turns_left=TURNS_LEFT, stamina=STAMINA, deck=deck, episodes=EPISODES
    )
    if not estimates:
        print("FAIL：一张牌都没算出期望分")
        return 1
    print("\nrollout 期望分（打这张 + 剩余回合 greedy 打完，8 次平均）：")
    for item in estimates:
        print(f"  [{item.index}] {item}")

    chosen = choose_card_via_sim(
        HAND, turns_left=TURNS_LEFT, stamina=STAMINA, deck=deck, episodes=EPISODES
    )
    if chosen is None:
        print("FAIL：模拟器没有给出选择")
        return 1
    best = next(item for item in estimates if item.index == chosen)
    print(f"\n最终选择：[{chosen}] {best.name} 期望 {best.expected:.1f}")

    # 规则基线（LessonPolicy）对比：sim 只是在它之上做前瞻
    state = LessonState(
        kind="audition",
        turns_left=TURNS_LEFT,
        stamina=STAMINA,
        cards=tuple(HAND),
    )
    rule = LessonPolicy().decide(state)
    print(f"规则 LessonPolicy 会选：{rule.kind} {rule.card.name if rule.card else rule.reason}")

    # 真实截图（有就顺手验一遍 OCR 读数 → 期望分，没有不影响验收）
    frame = ROOT / "data" / "exam_card_overlay.png"
    if frame.exists():
        import cv2

        from gkagent.vision.lesson import LessonReader
        from gkagent.vision.ocr import OcrEngine

        image = cv2.imread(str(frame))
        if image is not None:
            reader = LessonReader(OcrEngine())
            real_state = reader.read(image, kind="audition")
            if real_state.cards:
                print(f"\n真机截图 {frame.name} 读到 {len(real_state.cards)} 张手牌：")
                for item in real_state.cards:
                    print(
                        f"  [{item.index}] {item.name} score={item.score} hits={item.hits} "
                        f"cost={item.cost}"
                    )
                real_pick = choose_card_via_sim(
                    list(real_state.cards),
                    turns_left=max(int(real_state.turns_left or TURNS_LEFT), 1),
                    stamina=int(real_state.stamina or STAMINA),
                    episodes=EPISODES,
                )
                print(f"  截图 → 模拟器选择：{real_pick}")
            else:
                print(f"\n真机截图 {frame.name} 手牌读不到（OCR 掉帧），跳过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
