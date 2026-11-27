import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

from gkagent.policy.lesson import LessonPolicy
from gkagent.sim.lesson import CardSpec
from gkagent.vision.lesson import LessonCard, LessonState

cards = [
    LessonCard(index=0, box=(0, 0, 0, 0), point=(0, 0), name="在我发现的世界", score=0, cost=4, buff=True, text="好调"),
    LessonCard(index=1, box=(0, 0, 0, 0), point=(0, 0), name="试行错误+", score=84, cost=5, buff=False, text=""),
    LessonCard(index=2, box=(0, 0, 0, 0), point=(0, 0), name="轻快步伐", score=25, cost=4, buff=False, text=""),
]
state = LessonState(kind="lesson", cards=cards, stamina=8, turns_left=3, score=100, total_turns=5)

for engine in ("rules", "expectimax"):
    policy = LessonPolicy(engine=engine)
    try:
        choice = policy.decide(state)
        print(f"{engine:11s} -> {choice}")
    except Exception as exc:  # noqa: BLE001
        print(f"{engine:11s} -> 异常 {type(exc).__name__}: {exc}")

print("手牌字段检查:", [f for f in ("name", "score", "cost", "buff") if hasattr(cards[0], f)])
print("CardSpec 是否有 once:", "once" in CardSpec.__dataclass_fields__)
