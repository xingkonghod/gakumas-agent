"""M1 predictive replay 开发（不提交）：clean-room 消费图 + 牌区模型重放 rinami，
对照 oracle zones/consumption + 实机 rng。触发抽牌时机 oracle 锚定（sim 动力学，非 M1）。
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkagent.sim.rng_graph import (  # noqa: E402
    RngStream, ConsumptionGraph, reshuffle, support_rolls, create_deck_random,
    move_search_random, move_pick_random, panic_tick,
)

SUPPORTS = [
    {"id": "s_card-2-0007", "filter": 2, "permil": 56},
    {"id": "s_card-3-0030", "filter": 2, "permil": 64},
    {"id": "s_card-3-0070", "filter": 2, "permil": 61},
    {"id": "s_card-3-0025", "filter": 3, "permil": 74},
    {"id": "s_card-3-0064", "filter": 3, "permil": 67},
    {"id": "s_card-3-0069", "filter": 2, "permil": 74},
]
MAX_UPG = {
    "p_card-00-men-3_003": 3, "p_card-01-men-2_035": 3, "p_card-01-men-2_037": 3,
    "p_card-01-ido-3_200": 3, "p_card-01-men-2_036": 3, "p_card-01-act-2_001": 3,
    "p_card-01-men-3_036": 3, "p_card-00-men-3_012": 3, "p_card-01-men-2_043": 3,
    "p_card-01-men-3_034": 3, "p_card-01-ido-3_213": 3, "p_card-01-men-3_006": 3,
    "p_card-01-men-3_035": 3, "p_card-01-men-2_099": 3, "p_card-01-act-2_059": 3,
    "p_card-01-men-2_098": 3, "p_card-01-men-2_011": 3, "p_card-00-acc-0_002": 0,
    "p_card-01-act-3_049": 3, "p_card-01-men-3_033": 3, "p_card-01-men-2_038": 3,
    "p_card-01-act-3_010": 3,
}
GRAVE_CARDS = {"p_card-01-men-2_037", "p_card-01-act-2_001", "p_card-01-men-2_011"}
SSR = {"p_card-00-men-3_003", "p_card-01-men-3_036", "p_card-00-men-3_012",
       "p_card-01-men-3_034", "p_card-01-ido-3_213", "p_card-01-men-3_006",
       "p_card-01-men-3_035", "p_card-01-act-3_049", "p_card-01-men-3_033",
       "p_card-01-ido-3_200", "p_card-01-act-3_010"}
# pitem 312 interval 抽牌（0 RNG）时机：oracle 锚定（action index -> 抽 1 张）
PITEM_DRAW = {"W7": {9, 15, 20}, "W9": {11, 21, 28, 34}}
# owned-by-drinks：soda enchant 回合开始抽牌的支援强化（饮料独立 rng，exam 流 0 消费）。
DRINK_UPG = {"W9": {7: {"p_card-01-men-3_035": 1}}}


class Replay:
    def __init__(self, w, opening, oracle, turn_attrs):
        self.w = w
        self.stream = RngStream(opening["parameterScalars"]["currentRandom"]["state"])
        self.graph = ConsumptionGraph()
        self.hand = [(c["id"], c["upgradeCount"]) for c in opening["zones"]["hand"]]
        self.deck = [(c["id"], c["upgradeCount"]) for c in opening["zones"]["deck"]]
        self.grave, self.lost, self.hold = [], [], []
        self.turn = 1
        self.ta = turn_attrs
        self.used = []
        self.timers = []  # (fire_turn, draw_n)
        self.upgrade_timers = []  # fire_turn
        self.enc001_used = False
        self.enc043_used = False
        self.soda_turns = 0  # W9 soda enchant 剩余回合
        self.drinks_left = list(json.loads((ROOT / f"data/_rinami_live/{w}/gkms-loadout.json").read_text(encoding="utf-8"))["drink_ids"])
        self.oracle = oracle
        self.rows = oracle["rows"]
        self.cons_log = []
        lo = json.loads((ROOT / f"data/_rinami_live/{w}/gkms-loadout.json").read_text(encoding="utf-8"))
        self.base_upg = {c["produce_card_id"]: int(c.get("current_upgrade_count") or 0) for c in lo["deck_cards"]}
        self.base_upg["p_card-00-acc-0_002"] = 0

    @property
    def attr(self):
        return self.ta[self.turn - 1]

    def upgradeable(self, card):
        return card[1] < MAX_UPG.get(card[0], 3)

    def draw(self, n, roll):
        """抽 n 张（牌堆顶；抽空洗弃牌堆）。roll=True 掷支援。返回抽到的牌。"""
        drawn = []
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
            planned, _rolls = support_rolls(self.stream, drawn, SUPPORTS, self.attr,
                                            used=self.used, upgradeable=self.upgradeable, graph=self.graph)
            hits = {}
            for card, sid in planned:
                hits[card] = hits.get(card, 0) + 1
            drawn = [(c[0], c[1] + hits.get(c, 0)) for c in drawn]
        self.hand.extend(drawn)
        return drawn

    def run_action(self, k):
        r = self.rows[k]
        at = r["action"][0]
        cons_before = self.graph.total
        if at == "play":
            idx = r["action"][1]
            card = self.hand.pop(idx)
            pid = card[0]
            base = (pid, MAX_UPG.get(pid, 0) if False else card[1])
            # 出牌路由（支援强化剥离 → base upg；grave 卡用 base）
            routed = (pid, card[1])
            if pid in GRAVE_CARDS:
                self.grave.append((pid, self._base_upg(pid, card)))
            else:
                self.lost.append((pid, self._base_upg(pid, card)))
            self._play_effects(pid, k)
            self._play_triggers(pid, k)
        elif at == "drink":
            self._drink(k, r["action"][1])
        elif at == "end":
            # skipTurn / 考试结束：弃手牌（若随后回合转换，_end_turn 会再处理空手牌）
            for c in self.hand:
                self.grave.append((c[0], self._base_upg(c[0], c)))
            self.hand = []
        # 回合转换（oracle 锚定时机）
        if r["turn_after"] > r["turn_before"]:
            self._end_turn(k)
        cons = self.graph.total - cons_before
        self.cons_log.append(cons)
        return cons

    def _base_upg(self, pid, card):
        return self.base_upg.get(pid, card[1])

    def _play_effects(self, pid, k):
        if pid in ("p_card-01-men-2_099", "p_card-01-men-2_098"):
            self.draw(1, roll=True)
            idx = create_deck_random(self.stream, len(self.deck), 1, self.graph)[0]
            self.deck.insert(idx, ("p_card-00-acc-0_002", 0))
        elif pid == "p_card-01-men-3_034":
            cands = [c for c in self.deck + self.grave if c[0] in SSR]
            keys = move_search_random(self.stream, len(cands), playing=True, graph=self.graph)
            order = sorted(range(len(cands)), key=lambda i: keys[i])[:3]
            moved = [cands[i] for i in order]
            for c in moved:
                if c in self.deck: self.deck.remove(c)
                elif c in self.grave: self.grave.remove(c)
            for c in reversed(moved):
                self.deck.insert(0, c)
        elif pid == "p_card-01-men-2_011":
            self.timers.append((self.turn + 1, 2))
            self.timers.append((self.turn + 2, 1))
        elif pid == "p_card-00-men-3_003":
            self.upgrade_timers.append(self.turn + 1)

    def _play_triggers(self, pid, k):
        if pid == "p_card-01-act-2_001" and not self.enc001_used:
            acc = [c for c in self.deck + self.grave if c[0] == "p_card-00-acc-0_002"]
            if acc:
                move_pick_random(self.stream, len(acc), 1, 1, self.graph)
                self.deck.remove(acc[0]) if acc[0] in self.deck else self.grave.remove(acc[0])
                self.lost.append(acc[0])
            self.enc001_used = True
        if pid == "p_card-01-men-2_043" and not self.enc043_used:
            self.draw(1, roll=False)
            self.enc043_used = True
        if k in PITEM_DRAW[self.w]:
            self.draw(1, roll=False)

    def _drink(self, k, idx):
        # owned-by-drinks：_zone_ 副作用应用，消费跳过（rng 重同步）
        did = self.drinks_left.pop(idx)
        if did == "pdrink_00-2-010":
            self.draw(2, roll=True)  # soda draw 2（主阶段掷点）
            self.soda_turns = 5
        elif did == "pdrink_00-2-009":
            # 汉方：move idol-unique deck_grave->hand（random pick 1+nf）
            cands = [c for c in self.deck + self.grave if c[0] in ("p_card-01-ido-3_200", "p_card-01-ido-3_213")]
            move_search_random(self.stream, len(cands), playing=False, graph=self.graph)
            move_pick_random(self.stream, len(cands), 1, 1, self.graph)
            if cands:
                c = cands[0]
                self.deck.remove(c) if c in self.deck else self.grave.remove(c)
                self.hand.append(c)
        # protein: 0 zone

    def _end_turn(self, k):
        # 弃手牌（回合末剩余手牌全进弃牌堆，base upg；is_end_turn_lost 除外，rinami 无）
        for c in self.hand:
            self.grave.append((c[0], self._base_upg(c[0], c)))
        self.hand = []
        self.turn += 1
        self.used = []
        # 回合开始抽牌（turnStartDistribute，主阶段掷点）先于 trigger 抽牌
        self.draw(3, roll=True)
        # start-turn triggers（soda enchant 0 掷点；timer 掷点）
        if self.soda_turns > 0:
            soda_drawn = self.draw(2, roll=False)
            # owned-by-drinks：soda enchant 抽牌的支援强化走饮料独立 rng（exam rng 0），
            # 强化目标不可由 exam 流预测 → 显式锚点（unknown，如实记录）。
            for pid, delta in DRINK_UPG.get(self.w, {}).get(k, {}).items():
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


def main():
    for w in ("W7", "W9"):
        op = json.loads((ROOT / f"data/_rinami_live/{w}/opening.json").read_text(encoding="utf-8"))
        oracle = json.loads((ROOT / f"data/_m1_rinami_oracle_{w}.json").read_text(encoding="utf-8"))
        rp = Replay(w, op, oracle, op["turnAttributes"])
        print(f"===== {w} =====")
        mism = 0
        for k in range(len(rp.rows)):
            cons = rp.run_action(k)
            r = rp.rows[k]
            ok_cons = cons == r["consumption"]
            ok_rng = rp.stream.state == r["rng_after"]
            za = {zn: sorted(tuple(c) for c in r["zones_after"].get(zn, [])) for zn in ("hand", "deck", "grave", "lost")}
            zp = {"hand": sorted(rp.hand), "deck": sorted(rp.deck), "grave": sorted(rp.grave), "lost": sorted(rp.lost)}
            ok_zone = za == zp
            if not ok_cons or not ok_rng or not ok_zone:
                mism += 1
                print(f"  k={k} cons pred={cons} oracle={r['consumption']} rng={ok_rng} zone={ok_zone} card={r['live_card']}")
                if not ok_zone:
                    for zn in ("hand", "deck", "grave", "lost"):
                        if za[zn] != zp[zn]:
                            print(f"     {zn} pred={zp[zn]}")
                            print(f"     {zn} orac={za[zn]}")
                if mism >= 4:
                    break
        print(f"{w}: mismatches={mism}/{len(rp.rows)} final_rng={rp.stream.state}")


if __name__ == "__main__":
    main()
