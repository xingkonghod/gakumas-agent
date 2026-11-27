"""M8 sim_engine_ab「改前」基线 runner（不提交）。

用 monkeypatch 精确恢复 M8 前的 fresh 口径（仅附魔渠道好印象 fresh、好调无 fresh），
其余代码与改后完全相同 → 单变量隔离 M8 通用 fresh 对齐的评测影响。
  * condition_fresh 恒 0（旧：好调回合末直接 -1）；
  * review_fresh 衰减时只取附魔 turn_end_impression 渠道（旧 review_enchant_fresh 口径），
    卡/立即饮料/P 道具渠道获得量按旧口径当回合末即扣。
用法：python data/_m8_ab_before.py <seed> <out_json>
"""
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sim_engine_ab as ab  # noqa: E402
import gkagent.sim.lesson as L  # noqa: E402
import gkagent.sim.expectimax as E  # noqa: E402

_orig_end = L.LessonSim._end_turn
_orig_draw = L.LessonSim._draw_hand


def _end_turn_old(self, *, skipped):
    ench = sum(v for k, v, _t in self.turn_enchants if k == "turn_end_impression")
    self._m8_old_enchant_fresh = ench
    self.condition_fresh = 0  # 旧：好调无 fresh
    return _orig_end(self, skipped=skipped)


def _draw_hand_old(self, *, keep_extra_plays=False):
    self.review_fresh = getattr(self, "_m8_old_enchant_fresh", 0)  # 旧：仅附魔
    return _orig_draw(self, keep_extra_plays=keep_extra_plays)


L.LessonSim._end_turn = _end_turn_old
L.LessonSim._draw_hand = _draw_hand_old

_orig_ets = E.end_turn_state


def _end_turn_state_old(state):
    state = replace(state, review_fresh=0, condition_fresh=0)
    return _orig_ets(state)


E.end_turn_state = _end_turn_state_old

if __name__ == "__main__":
    seed = sys.argv[1] if len(sys.argv) > 1 else "9000"
    out = sys.argv[2] if len(sys.argv) > 2 else f"out/_m8_ab_before_{seed}.json"
    sys.exit(ab.main(["--episodes", "16", "--seed", seed, "--out", out]))