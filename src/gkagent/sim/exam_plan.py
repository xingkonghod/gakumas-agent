"""考试牌序生产接线：``ExamSetup``（采集数据）+ ``ExamDrawPlan``（边打边核对 + 喂全知搜索）。

数据来源
--------
``scripts/build_exam_setup.py`` 把一次实机采集（``traffic.jsonl`` + ``deck_snapshots.json``
+ 主数据 catalog）整理成 ``out/exam_setup.json``：

* ``seed``：``StepAuditionStart`` 响应里的 ``examSeedValue``（field 600）；
* ``deck``：考试时刻牌堆（``userProduceProgressProduceCardList``，按 number 升序）；
* ``supports``：支援卡列表（服务器已算好的 ``produceCardUpgradePermil`` + filter）；
* ``config_turns``：**配置回合数**（中间考试 forceEndScore 提前结束时也按配置回合算 K）；
* ``card_variants`` / ``lost_keys`` / ``end_lost_keys``：主数据里「还能不能强化」与
  「打出/回合末是否进弃牌堆」，用于支援强化掷点与弃牌堆顺序重建；
* ``truth``：这一场采集到的逐回合真相（手牌/出牌/属性/分数/体力），用于离线核对。

本模块做两件事
--------------
1. :class:`ExamSetup` —— 上面那份 JSON 的类型化视图（``from_dict`` / ``to_dict``）；
2. :class:`ExamDrawPlan` —— 一场考试的**在线牌序计划**：

   * 每回合 ``begin_turn``：用 :class:`~gkagent.sim.exam_oracle.ExamDrawOracle` 预测
     本回合真实手牌（seed + 牌堆 + 支援编成 + 配置回合 → 支援强化掷点后的牌序），
     并与**实机读屏手牌逐张核对**（id 多重集一致即可，升级次数允许实机更高）；
   * 核对通过 → ``expect_state_kwargs()`` 给出 ``deck`` / ``known_draw`` /
     ``discard`` / ``discard_order``，配合 ``reshuffle_hook()`` 让搜索用上全知牌序
     （含弃牌堆重洗后段）；
   * 核对失败 → 计划就地停用（``status="mismatch"``），往后再也不喂牌序数据；
     搜索退回「只知多重集」的期望模型——**宁可不用信息，也不能用错信息**。

生产接线（``scripts/auto_produce.py``）：
进入考试时用下一场 ``ExamSetup`` 建 ``ExamDrawPlan`` 挂到 ``LessonPolicy``；
每帧把读屏手牌喂给 ``observe_hand``；策略打完牌调 ``note_play``；回合末
``end_turn(leftover)`` 把本回合真实弃牌顺序并进 grave。拿不到采集数据（或 item④
「采集进程 ↔ 决策进程」还没打通）时计划不激活，策略行为和现在完全一致。

离线核对：``scripts/verify_exam_wiring.py`` 用 ``truth`` 驱动同一套
``begin_turn / note_play / end_turn``，逐回合对照真实手牌与后续牌序。
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exam_oracle import ExamDrawOracle
from .exam_shuffle import (
    DEFAULT_HAND_LIMIT,
    DEFAULT_NPC_COUNT,
    DEFAULT_TURN_START_DISTRIBUTE,
    Card,
)
from .expectimax import ReshuffleFn

# 屏幕左上角属性字（``vision.lesson._ATTRIBUTES``）→ ProduceParameterType
PARAMETER_TYPES: dict[str, int] = {"歌唱": 1, "舞蹈": 2, "视觉": 3}
# 计划状态
STATUS_PENDING = "pending"  # 还没开始（等待进入考试）
STATUS_ACTIVE = "active"  # 牌序已知且每回合核对通过
STATUS_MISMATCH = "mismatch"  # 与实机不符 → 已停用（退回期望搜索）
STATUS_DONE = "done"  # 考试结束


def _as_card(value: Any) -> Card | None:
    """把 ``[id, upgrade]`` / ``(id, upgrade)`` 转成 ``Card``；坏值返回 None。"""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        card_id, upgrade = value
        if isinstance(card_id, str) and card_id:
            try:
                return (card_id, int(upgrade))
            except (TypeError, ValueError):
                return None
    return None


@dataclass(frozen=True)
class ExamSetup:
    """一场考试的牌序数据（``out/exam_setup.json`` 里的一条 ``exams[i]``）。"""

    seed: int
    deck: tuple[Card, ...]
    config_turns: int
    supports: tuple[dict, ...] = ()
    initial_keys: frozenset[Card] = frozenset()
    # ProduceCardId -> 主数据里的最大 upgrade variant（判断还能不能再强化）
    card_variants: Mapping[str, int] = field(default_factory=dict)
    lost_keys: frozenset[Card] = frozenset()
    end_lost_keys: frozenset[Card] = frozenset()
    npc_count: int = DEFAULT_NPC_COUNT
    turn_start_distribute: int = DEFAULT_TURN_START_DISTRIBUTE
    hand_limit: int = DEFAULT_HAND_LIMIT
    index: int = 0
    ts: str = ""
    truth: tuple[dict, ...] = ()

    # ------------------------------------------------------------------ 构造
    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ExamSetup:
        """从 ``build_exam_setup.py`` 写出的 JSON 记录构造（坏条目抛 ValueError）。"""
        deck = tuple(
            card for card in (_as_card(item) for item in raw.get("deck") or ()) if card
        )
        if not deck:
            raise ValueError("exam_setup 缺 deck")
        seed = raw.get("seed")
        if not isinstance(seed, int) or seed <= 0:
            raise ValueError(f"exam_setup seed 非法：{seed!r}")
        variants: dict[str, int] = {}
        for card_id, max_upgrade in (raw.get("card_variants") or {}).items():
            try:
                variants[str(card_id)] = int(max_upgrade)
            except (TypeError, ValueError):
                continue
        return cls(
            seed=int(seed),
            deck=deck,
            config_turns=max(int(raw.get("config_turns") or 1), 1),
            supports=tuple(
                {
                    "id": str(item.get("id")),
                    "number": int(item.get("number") or 0),
                    "permil": int(item.get("permil") or 0),
                    "filter": int(item.get("filter") or 0),
                }
                for item in raw.get("supports") or ()
                if isinstance(item, Mapping) and item.get("id")
            ),
            initial_keys=frozenset(
                card
                for card in (_as_card(item) for item in raw.get("initial_keys") or ())
                if card
            ),
            card_variants=variants,
            lost_keys=frozenset(
                card
                for card in (_as_card(item) for item in raw.get("lost_keys") or ())
                if card
            ),
            end_lost_keys=frozenset(
                card
                for card in (_as_card(item) for item in raw.get("end_lost_keys") or ())
                if card
            ),
            npc_count=max(int(raw.get("npc_count") or DEFAULT_NPC_COUNT), 0),
            turn_start_distribute=max(
                int(raw.get("turn_start_distribute") or DEFAULT_TURN_START_DISTRIBUTE),
                1,
            ),
            hand_limit=max(int(raw.get("hand_limit") or DEFAULT_HAND_LIMIT), 1),
            index=int(raw.get("index") or 0),
            ts=str(raw.get("ts") or ""),
            truth=tuple(dict(item) for item in raw.get("truth") or ()),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化回 ``build_exam_setup.py`` 的字段（测试/调试用）。"""
        return {
            "index": self.index,
            "ts": self.ts,
            "seed": self.seed,
            "config_turns": self.config_turns,
            "played_turns": len(self.truth),
            "npc_count": self.npc_count,
            "turn_start_distribute": self.turn_start_distribute,
            "hand_limit": self.hand_limit,
            "deck": [list(card) for card in self.deck],
            "supports": [dict(item) for item in self.supports],
            "initial_keys": [list(card) for card in sorted(self.initial_keys)],
            "card_variants": dict(self.card_variants),
            "lost_keys": [list(card) for card in sorted(self.lost_keys)],
            "end_lost_keys": [list(card) for card in sorted(self.end_lost_keys)],
            "truth": [dict(item) for item in self.truth],
        }

    # ------------------------------------------------------------------ 派生
    def can_upgrade(self, card: Card) -> bool:
        """主数据里还有下一级变体才能掷支援强化（没有 → 整张跳过、不消耗随机数）。"""
        max_upgrade = self.card_variants.get(card[0])
        if max_upgrade is None:
            return True  # catalog 缺条目的新卡按可强化处理（与 verify_shuffle 同口径）
        return int(card[1]) < int(max_upgrade)

    def new_oracle(self) -> ExamDrawOracle:
        """按这份 setup 建一个开局就绪的 :class:`ExamDrawOracle`。"""
        return ExamDrawOracle(
            self.seed,
            list(self.deck),
            self.config_turns,
            npc_count=self.npc_count,
            supports=[dict(item) for item in self.supports],
            initial_keys=self.initial_keys,
            turn_start_distribute=self.turn_start_distribute,
            hand_limit=self.hand_limit,
            upgradeable=self.can_upgrade,
        )


def load_exam_setups(path: str | Path) -> list[ExamSetup]:
    """读 ``out/exam_setup.json``（坏条目跳过并告警，不抛异常给生产）。"""
    import json
    import logging

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logging.getLogger(__name__).warning("exam_setup 读取失败（%s）：%s", path, exc)
        return []
    if not isinstance(raw, dict):
        return []
    setups: list[ExamSetup] = []
    for item in raw.get("exams") or ():
        if not isinstance(item, dict):
            continue
        try:
            setups.append(ExamSetup.from_dict(item))
        except (TypeError, ValueError) as exc:
            logging.getLogger(__name__).warning("exam_setup 第 %s 条不可用：%s", item.get("index"), exc)
    return setups


class ExamDrawPlan:
    """一场考试的牌序计划：预测手牌 → 与实机核对 → 给搜索喂 ``known_draw``。

    失败兜底：任何一步对不上（卡表查不到 / 手牌不符 / oracle 缺 grave）都把计划
    置为 ``mismatch`` 并停用，之后 ``expect_state_kwargs()`` 恒为空 dict，
    搜索退回期望模型。``summary()`` 里能看到停用原因，便于复盘。
    """

    def __init__(self, setup: ExamSetup, *, card_table=None) -> None:
        self.setup = setup
        self.status = STATUS_PENDING
        self.reason = ""
        self.turn = 0
        self._card_table = card_table
        self._oracle: ExamDrawOracle | None = None
        # 真实弃牌堆顺序（进弃牌堆先后，旧 → 新）
        self._grave: list[Card] = []
        # 本回合已知牌堆顺序（下标 0 = 下一张）；回合内抽牌会从头部消费
        self._known: list[Card] = []
        self._observed: list[Card] = []
        self._expected_hand = 0
        self._played_cards: list[Card] = []
        self._turn_ok = False
        self.stats: dict[str, int] = {
            "turns": 0,
            "verified": 0,
            "reshuffles": 0,
            "in_turn_draws": 0,
        }

    # ------------------------------------------------------------------ 状态
    @property
    def active(self) -> bool:
        """计划是否仍在用（牌序已知且核对通过）。"""
        return self.status == STATUS_ACTIVE

    @property
    def known_draw(self) -> tuple[Card, ...]:
        """当前搜索可用的已知牌序（下标 0 = 下一张）；计划未激活时为空。"""
        return tuple(self._known) if self.active and self._turn_ok else ()

    @property
    def cards(self) -> tuple[Card, ...]:
        """本回合预测（并已核对）的手牌。"""
        return tuple(self._observed)

    def reshuffle_hook(self) -> ReshuffleFn | None:
        """确定性重洗钩子（纯函数，用考试 RNG 当前状态的副本）。"""
        if self._oracle is None:
            return None
        return self._oracle.reshuffle

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        """创建 oracle（可重复调用，已激活时不动）。"""
        if self._oracle is None:
            self._oracle = self.setup.new_oracle()
        if self.status == STATUS_PENDING:
            self.status = STATUS_ACTIVE

    def begin_turn(
        self, observed: Sequence[Any], parameter_type: int | None = None
    ) -> bool:
        """新回合：oracle 预测手牌 vs 实机手牌核对。

        ``observed`` 可以是 ``Card`` 元组（离线真值）或卡名（真机读屏）。
        返回计划是否仍然可用；核对失败会就地停用（``status="mismatch"``）。
        """
        if self.status in (STATUS_MISMATCH, STATUS_DONE):
            return False
        self.start()
        assert self._oracle is not None
        self.turn += 1
        observed_cards = self._resolve(observed)
        if observed_cards is None:
            self._fail(f"T{self.turn} 手牌里有卡表查不到的卡：{list(observed)}")
            return False
        before = self._oracle.reshuffles
        try:
            predicted = self._oracle.draw_next_turn(
                int(parameter_type or 0), grave=list(self._grave) if self._grave else None
            )
        except ValueError as exc:  # 缺 grave 等：不该发生，但绝不让出牌崩
            self._fail(f"T{self.turn} oracle 抽牌失败：{exc}")
            return False
        if self._oracle.reshuffles != before:
            # 弃牌堆洗回牌堆：grave 清空（牌已经在牌堆里了）
            self.stats["reshuffles"] += 1
            self._grave.clear()
        if not _same_ids(predicted, observed_cards):
            self._fail(
                f"T{self.turn} 手牌核对失败：预测 {_ids(predicted)} / 实机 {_ids(observed_cards)}"
            )
            return False
        self._observed = list(observed_cards)
        self._expected_hand = len(observed_cards)
        self._played_cards = []
        self._known = list(self._oracle.remaining)
        self._turn_ok = True
        self.stats["turns"] += 1
        self.stats["verified"] += 1
        return True

    def observe_hand(self, observed: Sequence[Any]) -> bool:
        """回合内再读一次手牌：跟踪「抽牌卡多抽的牌」并核对其是否来自已知牌序。

        回合内抽牌会让牌堆前移；不跟踪的话搜索会把已经抽到的牌再抽一遍。这里用
        手牌张数差推断抽了几张，并核对它们确实是 ``known_draw`` 的前几张；
        对不上就把本回合的全知关掉（下回合重新核对）。
        """
        if not self.active or not self._turn_ok:
            return False
        cards = self._resolve(observed)
        if cards is None:
            self._turn_ok = False
            return False
        delta = len(cards) - self._expected_hand
        self._observed = list(cards)
        self._expected_hand = len(cards)
        if delta < 0:
            # 手牌变少但没经过 note_play（被效果移除？）：本回合牌序不再可信
            self._turn_ok = False
            return False
        if delta > 0:
            drawn = self._known[:delta]
            if not _contains(drawn, cards):
                # 实机手牌里找不到「按已知牌序应该抽到」的牌 → 本回合牌序不可信
                self._turn_ok = False
                return False
            del self._known[:delta]
            self.stats["in_turn_draws"] += delta
        return True

    def note_play(self, card: Any) -> None:
        """策略真正打出一张牌：记账（回合末按出牌顺序进弃牌堆）。"""
        if not self.active:
            return
        resolved = self._resolve([card])
        if not resolved:
            return
        played = resolved[0]
        self._played_cards.append(played)
        self._expected_hand = max(self._expected_hand - 1, 0)

    def end_turn(self, leftover: Sequence[Any] = ()) -> None:
        """回合末：把「打出的牌（按顺序）+ 剩余手牌（按手牌顺序）」并进弃牌堆。"""
        if self.status in (STATUS_MISMATCH, STATUS_DONE):
            return
        leftover_cards = self._resolve(leftover) if leftover else []
        if leftover_cards is None:
            self._fail("回合末剩余手牌里有卡表查不到的卡")
            return
        for card in self._played_cards:
            if card not in self.setup.lost_keys:
                self._grave.append(card)
        for card in leftover_cards:
            if card not in self.setup.end_lost_keys:
                self._grave.append(card)
        self._played_cards = []
        self._turn_ok = False  # 下一回合 begin_turn 重新核对后才恢复

    def finish(self) -> None:
        """考试结束（保留统计，不再喂数据）。"""
        if self.status == STATUS_ACTIVE:
            self.status = STATUS_DONE
        self._turn_ok = False

    def reset(self) -> None:
        """把计划清回「开局前」状态（候选切换/重试时用，oracle 重建）。"""
        self.status = STATUS_PENDING
        self.reason = ""
        self.turn = 0
        self._oracle = None
        self._grave.clear()
        self._known.clear()
        self._observed.clear()
        self._expected_hand = 0
        self._played_cards.clear()
        self._turn_ok = False

    # ------------------------------------------------------------------ 搜索接口
    def expect_state_kwargs(self, to_specs=None) -> dict[str, Any]:
        """给 ``ExpectState`` 的全知字段（计划不可用 / 没给转换器时返回空 dict）。

        ``to_specs``：把 ``(produceCardId, upgrade)`` 转成搜索用的 ``CardSpec``
        （生产由 ``LessonPolicy`` 用卡表转；plan 只持有 id/upgrade，不猜卡面数值）。
        不给转换器就不喂数据，保证 ``ExpectState`` 里永远是合法类型。
        """
        if not self.active or not self._turn_ok or to_specs is None:
            return {}
        known = tuple(self._known)
        grave = tuple(self._grave)
        return {
            "deck": tuple(to_specs(known)),
            "known_draw": tuple(to_specs(known)),
            "discard": tuple(to_specs(grave)),
            "discard_order": tuple(to_specs(grave)),
        }

    def summary(self) -> dict[str, Any]:
        """日志/复盘用的状态摘要。"""
        return {
            "status": self.status,
            "reason": self.reason,
            "exam": self.setup.index,
            "seed": f"0x{self.setup.seed:08X}",
            "config_turns": self.setup.config_turns,
            "turn": self.turn,
            **self.stats,
        }

    # ------------------------------------------------------------------ 内部
    def _fail(self, reason: str) -> None:
        self.status = STATUS_MISMATCH
        self.reason = reason
        self._turn_ok = False

    def _table(self):
        if self._card_table is None:
            from gkagent.data.card_table import CardTable

            self._card_table = CardTable()
        return self._card_table

    def _resolve(self, observed: Sequence[Any]) -> list[Card] | None:
        """把观察值统一成 ``Card``：``(id, upgrade)`` 直接用，卡名查卡表。"""
        out: list[Card] = []
        for item in observed:
            if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(
                item[0], str
            ):
                card = _as_card(item)
                if card is None:
                    return None
                out.append(card)
                continue
            if not isinstance(item, str) or not item.strip():
                return None
            card = self._card_from_name(item)
            if card is None:
                return None
            out.append(card)
        return out

    def _card_from_name(self, name: str) -> Card | None:
        row = self._table().get(name)
        if row is None:
            return None
        card_id = row.get("id")
        if not isinstance(card_id, str) or not card_id:
            return None
        upgrade = int(row.get("upgrade") or 0)
        # OCR 常见只丢末尾 '+'：名字里有 '+' 但查表落到基础版时补上强化次数
        plus = name.count("+") + name.count("＋")
        if plus and upgrade == 0:
            upgrade = min(plus, 3)
        return (card_id, upgrade)


def _ids(cards: Sequence[Card]) -> list[str]:
    return [card[0] for card in cards]


def _same_ids(left: Sequence[Card], right: Sequence[Card]) -> bool:
    """两张手牌「同一批牌」：id 多重集相同（升级次数允许实机更高）。"""
    if len(left) != len(right):
        return False
    return Counter(_ids(left)) == Counter(_ids(right))


def _contains(subset: Sequence[Card], cards: Sequence[Card]) -> bool:
    """``subset`` 的 id 多重集是否是 ``cards`` 的子集（抽到的牌应当还在手牌里）。"""
    return not (Counter(_ids(subset)) - Counter(_ids(cards)))


# ---------------------------------------------------------------------- 候选选择
class ExamPlanSelector:
    """同一场考试的多个候选计划：逐回合用实机手牌收窄，唯一剩下即「锁定」。

    生产场景：

    * ``build_exam_setup.py --current`` 不知道「当前这场」的配置回合数（考试还没
      结束、拿不到 EndExamBattle），于是同一 seed/牌堆输出多个 ``config_turns`` 候选；
    * ``out/exam_setup.json`` 里也可能同时躺着多场历史数据。

    做法：每回合把**同一份读屏手牌**喂给所有仍然存活的候选，核对失败的淘汰；
    只剩一个时锁定（从这一回合起给搜索喂 known_draw）。第 1 回合往往分不出来
    （例如 isInitial 卡都是同一张），第 2–3 回合自然收敛——和 QQ 群「2–3 回合
    锁定 seed」是同一个道理。全部候选被淘汰 = 数据不匹配，返回 ``False``（调用方
    退回期望搜索）；给 ``max_attempts`` 次重来机会，避免过期数据无限重试烧 CPU。
    """

    def __init__(self, plans, *, max_attempts: int = 40) -> None:
        self.plans = list(plans)
        self.max_attempts = max(int(max_attempts), 1)
        self._chosen: ExamDrawPlan | None = None
        self._alive: list[ExamDrawPlan] = list(self.plans)
        self._attempts = 0
        self._retries = 0
        self._locked_at = 0
        self.reset_count = 0

    # ------------------------------------------------------------------ 状态
    @property
    def chosen(self) -> ExamDrawPlan | None:
        return self._chosen

    @property
    def candidates(self) -> int:
        return len(self.plans)

    @property
    def alive(self) -> int:
        return len(self._alive)

    @property
    def locked_turn(self) -> int:
        """锁定发生在第几回合（0 = 还没锁定）。"""
        return self._locked_at

    @property
    def active(self) -> bool:
        if self._chosen is not None:
            return self._chosen.active
        return bool(self._alive) and self._retries < self.max_attempts

    @property
    def setup(self):
        plan = self._chosen or (self._alive[0] if self._alive else None)
        if plan is None and self.plans:
            plan = self.plans[0]
        return plan.setup if plan is not None else None

    @property
    def status(self) -> str:
        if self._chosen is not None:
            return self._chosen.status
        if not self._alive or self._retries >= self.max_attempts:
            return STATUS_MISMATCH
        return STATUS_PENDING

    @property
    def reason(self) -> str:
        if self._chosen is not None:
            return self._chosen.reason
        if len(self._alive) > 1:
            return f"候选未收敛（{len(self._alive)} 个仍在核对）"
        reasons = [plan.reason for plan in self.plans if plan.reason]
        if reasons:
            return "候选都不匹配：" + "；".join(reasons[:3])
        return ""

    @property
    def cards(self):
        return self._chosen.cards if self._chosen is not None else ()

    def __getattr__(self, name):
        """其余只读属性（known_draw/turn/stats/turn_ok…）代理给选中的计划。"""
        if name.startswith("_"):
            raise AttributeError(name)
        chosen = self.__dict__.get("_chosen")
        if chosen is None:
            raise AttributeError(name)
        return getattr(chosen, name)

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        for plan in self.plans:
            plan.start()
        self._alive = list(self.plans)

    def _targets(self) -> list[ExamDrawPlan]:
        """note_play / end_turn / observe_hand 要同步的计划：锁定后只喂选中的。"""
        if self._chosen is not None:
            return [self._chosen]
        return list(self._alive)

    def begin_turn(self, observed, parameter_type: int | None = None) -> bool:
        if self._chosen is not None:
            return self._chosen.begin_turn(observed, parameter_type)
        if not self._alive or self._retries >= self.max_attempts:
            return False
        survivors: list[ExamDrawPlan] = []
        for plan in self._alive:
            try:
                if plan.begin_turn(observed, parameter_type):
                    survivors.append(plan)
            except Exception as exc:  # noqa: BLE001 - 单个候选坏了不影响其它候选
                logging.getLogger(__name__).warning("候选计划 begin_turn 失败：%s", exc)
        self._attempts += 1
        self._alive = survivors
        if not survivors:
            # 一个都对不上：可能是读屏偶发/数据过期 → 全部重置，下次重来（有次数上限）
            self._retries += 1
            for plan in self.plans:
                plan.reset()
                self.reset_count += 1
            self._alive = list(self.plans)
            return False
        if len(survivors) == 1:
            self._chosen = survivors[0]
            self._locked_at = self._chosen.turn
        return self._chosen is not None

    def observe_hand(self, observed) -> bool:
        ok = True
        for plan in self._targets():
            try:
                ok = plan.observe_hand(observed) and ok
            except Exception as exc:  # noqa: BLE001 - 台账失败不影响出牌
                logging.getLogger(__name__).warning("候选计划 observe_hand 失败：%s", exc)
                ok = False
        return ok

    def note_play(self, card) -> None:
        for plan in self._targets():
            plan.note_play(card)

    def end_turn(self, leftover=()) -> None:
        for plan in self._targets():
            plan.end_turn(leftover)

    def finish(self) -> None:
        for plan in self.plans:
            plan.finish()
        self._chosen = None
        self._alive = []
        self._locked_at = 0

    # ------------------------------------------------------------------ 搜索接口
    def expect_state_kwargs(self, to_specs=None) -> dict:
        if self._chosen is None:
            return {}
        return self._chosen.expect_state_kwargs(to_specs=to_specs)

    def reshuffle_hook(self):
        if self._chosen is None:
            return None
        return self._chosen.reshuffle_hook()

    def summary(self) -> dict:
        info: dict = {
            "status": self.status,
            "candidates": len(self.plans),
            "alive": len(self._alive),
            "attempts": self._attempts,
            "retries": self._retries,
            "resets": self.reset_count,
            "locked_turn": self.locked_turn,
        }
        if self._chosen is not None:
            info.update(self._chosen.summary())
        else:
            info["reason"] = self.reason
        return info
