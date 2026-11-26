"""M1 阶段2(a) predictive 牌区动力学（clean-room 自写）。

在阶段1 消费图（:mod:`gkagent.sim.rng_graph`）之上，自写**预测**牌区演化与抽牌时机，
不再锚定 oracle 消费事件。覆盖（详见 docs/GKBENCH.md §13 M1 / HANDOVER）：

已预测（主数据驱动）
--------------------
* **type9 随机选取选牌序**：``signed_key`` 带符号 int32 升序（探针①口径，阶段2 修正）。
* **enchant / turn_start_draw 抽牌时机**：与 :mod:`gkagent.sim.drinks` 同口径
  （``ExamStatusEnchant`` 内层 ``ExamCardDraw`` + ``start_play`` → 回合开始后抽 N）。
  回合开始主抽牌（turnStartDistribute）先于 enchant 抽牌；主抽牌掷支援、enchant 抽牌
  支援走饮料侧（见 unknown）。
* **卡效果牌区动力学**：``ExamCardDraw``（立即/timer）、``ExamCardCreateId``
  （DECK_RANDOM 每卡 1 range）、``ExamCardMove``（search random 2nf / pick 1+nf）、
  ``ExamEffectTimer``（延迟抽牌）——效果规格来自主数据 ``card_table``。
* **消费次数**：reshuffle / support_rolls / create_deck_random / move_* / panic 全由
  消费图按预测牌区计算（不读 oracle 事件）。

显式 unknown（不猜，如实留锚点清单）
------------------------------------
* **pitem 312 interval 抽牌时机**：主数据语义已推得（``card_play_interval`` interval=4
  scope=exam、play_filter=好調效果组、条件「好调≥8」、max_uses=5、draw  bundled 在
  ``ExamPlayableValueAdd``），但**精确 fire 口径**含 DLL 内部计数器（``interval44_count``）
  与手牌上限跳过/计数器复位交互，两局实机样本不足以可靠反推 → 显式 unknown 锚点
  ``pitem_draw_unknown``，留 (c) type21 类探针逐场景刻画。
* **饮料侧 soda enchant 支援强化目标**：soda 回合开始抽牌的支援强化走**独立饮料 rng**
  （exam 流 0 消费，W9 k=7 实测 rng_steps=12 不含），强化目标不可由 exam 流预测 →
  显式 unknown 锚点 ``drink_upg_unknown``（owned-by-drinks，M6）。

anchor_fallback
---------------
``anchor_fallback=True`` 退回阶段1 口径：按 oracle 消费次数推进 rng（不声称预测），
回归证明与阶段1 逐位同。默认 ``False``（predictive）。

铁律：不拷 AGPL/参考源码；引擎只作 oracle；不改 drinks.py / exam_risk 默认行为。
"""
from __future__ import annotations

from typing import Any, Mapping

from .rng_graph import (
    RngStream, ConsumptionGraph, support_rolls, create_deck_random,
    move_search_random, move_pick_random,
)

__all__ = ["PredictiveReplay", "PREDICTIVE_COVERAGE", "UNKNOWN_TIMINGS"]

#: predictive 覆盖表（报告用）：timing → "predicted" / "unknown"。
PREDICTIVE_COVERAGE: dict[str, str] = {
    "type9_random_pick_order": "predicted",       # signed_key 带符号升序
    "enchant_turn_start_draw": "predicted",        # drinks.py 同口径
    "turn_start_main_draw": "predicted",           # turnStartDistribute 抽 3 掷支援
    "card_draw_immediate": "predicted",            # ExamCardDraw 立即
    "card_draw_timer": "predicted",                # ExamEffectTimer 延迟抽牌
    "card_create_deck_random": "predicted",        # ExamCardCreateId DECK_RANDOM
    "card_move_search_random": "predicted",        # ExamCardMove search 2nf
    "card_move_pick_random": "predicted",          # ExamCardMove pick 1+nf
    "reshuffle": "predicted",
    "support_rolls": "predicted",
    "encore_trigger_move": "predicted",            # act-2_001 enc 触发 move pick
    "encore_trigger_draw": "predicted",            # men-2_043 enc 触发 draw 1
    "pitem_312_interval_draw": "unknown",          # DLL 计数器+手牌上限交互
    "drink_soda_support_upgrade": "unknown",       # 独立饮料 rng（owned-by-drinks）
}

#: 显式 unknown 时机清单（不静默）。
UNKNOWN_TIMINGS: tuple[str, ...] = (
    "pitem_312_interval_draw",
    "drink_soda_support_upgrade",
)


class PredictiveReplay:
    """从 opening + loadout + 主数据效果规格预测牌区演化与 rng 消费。

    ``config`` 为 fixture 单局字段（opening_zones / turn_attrs / supports / base_upg /
    max_upg / grave_cards / ssr / drinks / card_effects / pitem_draw_unknown /
    drink_upg_unknown / actions）。``anchor_fallback=True`` 时按 oracle_cons 推进 rng。
    """

    def __init__(self, config: Mapping[str, Any], *, anchor_fallback: bool = False) -> None:
        self.cfg = config
        self.anchor_fallback = anchor_fallback
        self.stream = RngStream(config["opening_rng"])
        self.graph = ConsumptionGraph()
        self.hand = [tuple(c) for c in config["opening_zones"]["hand"]]
        self.deck = [tuple(c) for c in config["opening_zones"]["deck"]]
        self.grave: list[tuple] = [tuple(c) for c in config["opening_zones"]["grave"]]
        self.lost: list[tuple] = [tuple(c) for c in config["opening_zones"]["lost"]]
        self.turn = 1
        self.ta = config["turn_attrs"]
        self.used: list[Any] = []
        self.timers: list[tuple[int, int]] = []
        self.soda_turns = 0
        self.drinks_left = list(config["drinks"])
        self.base_upg = dict(config["base_upg"])
        self.max_upg = config["max_upg"]
        self.grave_cards = set(config["grave_cards"])
        self.ssr = set(config["ssr"])
        self.supports = config["supports"]
        self.card_effects = config["card_effects"]
        self.pitem_draw = set(config["pitem_draw_unknown"])
        self.drink_upg = {int(k): v for k, v in config["drink_upg_unknown"].items()}
        self.enc001_used = False
        self.enc043_used = False
        self.rows = config["actions"]

    @property
    def attr(self) -> int:
        return self.ta[self.turn - 1]

    def _upgradeable(self, card: tuple) -> bool:
        return card[1] < self.max_upg.get(card[0], 3)

    def _base_upg(self, pid: str, card: tuple) -> int:
        return self.base_upg.get(pid, card[1])

    def draw(self, n: int, roll: bool) -> list[tuple]:
        """抽 n 张（牌堆顶；抽空洗弃牌堆）。roll=True 掷支援。返回抽到的牌。"""
        drawn: list[tuple] = []
        for _ in range(n):
            if len(self.hand) >= 5:
                break
            if not self.deck:
                if not self.grave:
                    break
                g = list(self.grave)
                self.grave = []
                for nn in range(len(g), 1, -1):
                    j = self.stream.range(0, nn)
                    g[j], g[nn - 1] = g[nn - 1], g[j]
                self.graph.record("reshuffle", max(0, len(g) - 1), grave_count=len(g))
                self.deck = g
            drawn.append(self.deck.pop(0))
        if roll and drawn:
            planned, _rolls = support_rolls(
                self.stream, drawn, self.supports, self.attr,
                used=self.used, upgradeable=self._upgradeable, graph=self.graph,
            )
            hits: dict[tuple, int] = {}
            for card, sid in planned:
                hits[card] = hits.get(card, 0) + 1
            drawn = [(c[0], c[1] + hits.get(c, 0)) for c in drawn]
        self.hand.extend(drawn)
        return drawn

    def run_action(self, k: int) -> int:
        r = self.rows[k]
        at = r["action"][0]
        cons_before = self.graph.total
        if self.anchor_fallback:
            # 阶段1 口径：按 oracle 消费次数推进 rng（不声称预测）。
            for _ in range(r["oracle_cons"]):
                self.stream.advance()
            self.graph.record("oracle_anchor", r["oracle_cons"])
            return self.graph.total - cons_before
        if at == "play":
            idx = r["action"][1]
            card = self.hand.pop(idx)
            pid = card[0]
            if pid in self.grave_cards:
                self.grave.append((pid, self._base_upg(pid, card)))
            else:
                self.lost.append((pid, self._base_upg(pid, card)))
            self._play_effects(pid, k)
            self._play_triggers(pid, k)
        elif at == "drink":
            self._drink(k, r["action"][1])
        elif at == "end":
            for c in self.hand:
                self.grave.append((c[0], self._base_upg(c[0], c)))
            self.hand = []
        if r["turn_after"] > r["turn_before"]:
            self._end_turn(k)
        return self.graph.total - cons_before

    def _play_effects(self, pid: str, k: int) -> None:
        effs = self.card_effects.get(pid, [])
        types = [e["type"] for e in effs]
        # 一决胜负/刺激（men-2_099/098）：立即抽 1 + 确定式生成 acc-0_002 入牌堆随机位。
        if pid in ("p_card-01-men-2_099", "p_card-01-men-2_098"):
            self.draw(1, roll=True)
            idx = create_deck_random(self.stream, len(self.deck), 1, self.graph)[0]
            self.deck.insert(idx, ("p_card-00-acc-0_002", 0))
        # 天赋才能（men-3_034）：search random 把牌堆/弃牌中 SSR 前 3 移牌堆顶。
        elif pid == "p_card-01-men-3_034":
            cands = [c for c in self.deck + self.grave if c[0] in self.ssr]
            keys = move_search_random(self.stream, len(cands), playing=True, graph=self.graph)
            order = sorted(range(len(cands)), key=lambda i: keys[i])[:3]
            moved = [cands[i] for i in order]
            for c in moved:
                if c in self.deck:
                    self.deck.remove(c)
                elif c in self.grave:
                    self.grave.remove(c)
            for c in reversed(moved):
                self.deck.insert(0, c)
        # 聚光灯（men-2_011）：timer 延迟抽牌（turn+1 抽 2 / turn+2 抽 1）。
        elif pid == "p_card-01-men-2_011":
            self.timers.append((self.turn + 1, 2))
            self.timers.append((self.turn + 2, 1))

    def _play_triggers(self, pid: str, k: int) -> None:
        # 齐声应援 enc 触发（一次性）：pick random 把 acc-0_002 移 lost。
        if pid == "p_card-01-act-2_001" and not self.enc001_used:
            acc = [c for c in self.deck + self.grave if c[0] == "p_card-00-acc-0_002"]
            if acc:
                move_pick_random(self.stream, len(acc), 1, 1, self.graph)
                if acc[0] in self.deck:
                    self.deck.remove(acc[0])
                else:
                    self.grave.remove(acc[0])
                self.lost.append(acc[0])
            self.enc001_used = True
        # 大声应援 enc 触发（一次性）：抽 1（不掷支援）。
        if pid == "p_card-01-men-2_043" and not self.enc043_used:
            self.draw(1, roll=False)
            self.enc043_used = True
        # pitem 312 interval 抽牌：显式 unknown 锚点（DLL 计数器口径未刻画）。
        if k in self.pitem_draw:
            self.draw(1, roll=False)

    def _drink(self, k: int, idx: int) -> None:
        # owned-by-drinks：zone 副作用应用，饮料本体消费跳过（M6）。
        did = self.drinks_left.pop(idx)
        if did == "pdrink_00-2-010":
            self.draw(2, roll=True)  # soda 立即抽 2（主阶段掷点）
            self.soda_turns = 5
        elif did == "pdrink_00-2-009":
            # 汉方：search move 偶像固有 deck_grave→hand（search 排序 nf + pick 1+nf）。
            cands = [c for c in self.deck + self.grave
                     if c[0] in ("p_card-01-ido-3_200", "p_card-01-ido-3_213")]
            move_search_random(self.stream, len(cands), playing=False, graph=self.graph)
            move_pick_random(self.stream, len(cands), 1, 1, self.graph)
            if cands:
                c = cands[0]
                if c in self.deck:
                    self.deck.remove(c)
                else:
                    self.grave.remove(c)
                self.hand.append(c)

    def _end_turn(self, k: int) -> None:
        for c in self.hand:
            self.grave.append((c[0], self._base_upg(c[0], c)))
        self.hand = []
        self.turn += 1
        self.used = []
        # 回合开始主抽牌（turnStartDistribute）先于 enchant 抽牌，掷支援。
        self.draw(3, roll=True)
        # soda enchant 回合开始抽牌（drinks.py turn_start_draw 同口径，每瓶抽 1）。
        if self.soda_turns > 0:
            self.draw(2, roll=False)
            # 饮料侧支援强化（独立饮料 rng，exam 流 0 消费）→ 显式 unknown 锚点。
            for pid, delta in self.drink_upg.get(k, {}).items():
                self.base_upg[pid] = self.base_upg.get(pid, 0) + delta
                for i, c in enumerate(self.hand):
                    if c[0] == pid:
                        self.hand[i] = (pid, self.base_upg[pid])
                        break
            self.soda_turns -= 1
        for t, n in list(self.timers):
            if t == self.turn:
                self.draw(n, roll=True)
                self.timers.remove((t, n))

    def zones(self) -> dict[str, list]:
        return {
            "hand": sorted(self.hand), "deck": sorted(self.deck),
            "grave": sorted(self.grave), "lost": sorted(self.lost),
        }