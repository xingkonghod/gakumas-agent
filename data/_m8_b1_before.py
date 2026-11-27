"""M8 B1 harness（eval_t4_b1）「改前」基线 runner（不提交）。monkeypatch 恢复 M8 前 fresh。"""
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_t4_b1 as b1  # noqa: E402
import gkagent.sim.lesson as L  # noqa: E402
import gkagent.sim.expectimax as E  # noqa: E402

_orig_end = L.LessonSim._end_turn
_orig_draw = L.LessonSim._draw_hand


def _end_turn_old(self, *, skipped):
    self._m8_old_enchant_fresh = sum(
        v for k, v, _t in self.turn_enchants if k == "turn_end_impression")
    self.condition_fresh = 0
    return _orig_end(self, skipped=skipped)


def _draw_hand_old(self, *, keep_extra_plays=False):
    self.review_fresh = getattr(self, "_m8_old_enchant_fresh", 0)
    return _orig_draw(self, keep_extra_plays=keep_extra_plays)


L.LessonSim._end_turn = _end_turn_old
L.LessonSim._draw_hand = _draw_hand_old
_orig_ets = E.end_turn_state
E.end_turn_state = lambda s: _orig_ets(replace(s, review_fresh=0, condition_fresh=0))

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "out/_m8_b1_before.json"
    sys.exit(b1.main(["--games", "60", "--scenario", "small", "--no-frontier", "--json", out]))