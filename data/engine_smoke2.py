import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

from gkagent.policy.lesson import LessonPolicy
from gkagent.vision.lesson import LessonCard, LessonState

cards = [
    LessonCard(index=0, box=(0, 0, 0, 0), point=(0, 0), name="在我发现的世界", score=0, cost=4, buff=True, text="好调"),
    LessonCard(index=1, box=(0, 0, 0, 0), point=(0, 0), name="试行错误+", score=84, cost=5, buff=False, text=""),
    LessonCard(index=2, box=(0, 0, 0, 0), point=(0, 0), name="轻快步伐", score=25, cost=4, buff=False, text=""),
]
state = LessonState(kind="lesson", cards=cards, stamina=8, turns_left=3, score=100, total_turns=5, gauge=250)

policy = LessonPolicy(engine="expectimax")
print("engine =", policy.engine)
try:
    override = policy._try_expectimax(state, allow_skip=True)
    print("override =", override)
except Exception:
    traceback.print_exc()

# 直接调 expectimax，看构造哪里缺
from gkagent.sim import expectimax as ex

print("ExpectState 字段:", list(ex.ExpectState.__dataclass_fields__))
