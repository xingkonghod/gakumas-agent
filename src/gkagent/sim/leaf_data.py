"""B2 数据采集：叶子状态样本（叶子形态 ``ExpectState`` + 后续实际得分标签）。

为什么需要专门记录：

* 搜索里的叶子估值只发生在 ``_Search.leaf``：输入是 ``end_turn_state(state)``
  —— 手牌已并入弃牌堆、好印象已结算并 -1、好调/持续 buff 已倒计时、回合数 -1。
* 如果像旧 ``fit_v_leaf.py`` 那样在**回合开始**（手牌还在手上）取特征，训练
  分布和推理分布不一致（``hand_*`` 训练时非零、推理恒为零），模型学歪。
* ``LessonSim._end_turn`` 在回合结束结算后立刻 ``_draw_hand()`` 抽下一手，因此
  “叶子状态”是个瞬时点。``RecordingLessonSim`` 在 ``_draw_hand`` 入口记录快照
  （此时手牌已清空、好印象还没 -1、本回合出牌数还没清零），再换算成与
  ``end_turn_state`` 等价的状态。

标签：一局跑完后 ``y = 最终分 - 叶子状态分数``，即从该叶子继续执行当前策略的
**实际后续得分**（on-policy return）。配合 B1 修正后的执行器，这是 B2 的
teacher 数据来源（``scripts/build_b2_dataset.py``）。
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from gkagent.sim.expectimax import ExpectState, state_from_sim
from gkagent.sim.leaf_mlp import DIM, features
from gkagent.sim.lesson import LessonSim


def leaf_state_at_draw(sim: LessonSim) -> ExpectState:
    """把「回合结束、下一手还没抽」的模拟器瞬时点换算成叶子 ``ExpectState``。

    与 ``expectimax.end_turn_state`` 对齐：好印象已加分但在这里还没 -1（``LessonSim``
    在下一回合抽手牌时才 -1）、本回合出牌数/额外次数/饮料计数已归零。
    """
    state = state_from_sim(sim)
    return replace(
        state,
        hand=(),
        impression=max(int(state.impression) - 1, 0),
        plays_used=0,
        extra_plays=0,
        drinks_used_this_turn=0,
    )


def terminal_leaf_state(sim: LessonSim) -> ExpectState:
    """终局叶子（``turns_left=0``，后续得分为 0）；只在自然打完全部回合时使用。"""
    state = state_from_sim(sim)
    return replace(
        state,
        hand=(),
        turns_left=0,
        plays_used=0,
        extra_plays=0,
        drinks_used_this_turn=0,
    )


class RecordingLessonSim(LessonSim):
    """``LessonSim`` + 记录每次换手牌前的叶子快照（即 ``end_turn_state`` 形态）。"""

    def __init__(self, *args, **kwargs) -> None:
        self.leaf_states: list[ExpectState] = []
        self._record_enabled = False
        super().__init__(*args, **kwargs)
        # __init__ 里的首发手牌不是叶子，打开开关后才开始记录回合间快照。
        self._record_enabled = True

    def _draw_hand(self, *, keep_extra_plays: bool = False) -> None:
        if self._record_enabled and int(self.turns_left) > 0:
            self.leaf_states.append(leaf_state_at_draw(self))
        super()._draw_hand(keep_extra_plays=keep_extra_plays)


def episode_samples(
    sim: RecordingLessonSim, *, include_terminal: bool = True
) -> tuple[np.ndarray, np.ndarray, dict]:
    """一局结束后把叶子快照变成 (X, y, meta)。

    ``y = 最终分 - 快照分数``。自然打满回合时额外补一个 ``turns_left=0`` 的
    终局样本（y=0）给模型锚定终局价值；提前因体力不足结束的局不补
    （它的“后续 0 分”不是真实规则，而是模拟器提前截断）。
    """
    final_score = float(sim.score)
    states = list(sim.leaf_states)
    y = [final_score - float(state.score) for state in states]
    if include_terminal and int(sim.turns_left) == 0:
        states.append(terminal_leaf_state(sim))
        y.append(0.0)
    if not states:
        return np.zeros((0, DIM), dtype=np.float64), np.zeros(0, dtype=np.float64), {
            "final_score": final_score,
            "turns_left": int(sim.turns_left),
        }
    X = np.asarray([features(state) for state in states], dtype=np.float64)
    meta = {
        "final_score": final_score,
        "turns_left": int(sim.turns_left),
        "n_samples": len(states),
        "leaf_scores": [float(state.score) for state in states],
        "scores": y,
    }
    return X, np.asarray(y, dtype=np.float64), meta
