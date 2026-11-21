"""卡牌属性表：来自 gakumasu-diff 的 ProduceCard.yaml（和游戏 master 同一套 ID）。

作用：出牌时**不用 OCR 猜体力费用**——卡面爱心小字 12px、确认帧预览会错位，
而这张表是按 ID 对出来的真值（1817 张全中）。

字段：cost（体力费用）、rarity、plan、category、effects（examEffectType 列表）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "card_table.json"

# 中文卡面里表示"有前提条件才能打"的说法
CONDITION_WORDS = ("状态的时候", "的情况下", "情况下，可以使用", "以上时", "低于", "训练中仅限")


@dataclass(frozen=True)
class CardMeta:
    name: str
    cost: int
    rarity: str
    plan: str
    category: str
    effects: tuple[str, ...]

    @property
    def conditional(self) -> bool:
        return False


class CardTable:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._cards: dict[str, dict] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._cards = dict(raw.get("cards") or {})
            except (OSError, json.JSONDecodeError):
                self._cards = {}

    def __len__(self) -> int:
        return len(self._cards)

    def get(self, name: str) -> dict | None:
        if not name:
            return None
        row = self._cards.get(name.strip())
        if row is not None:
            return row
        # OCR 常丢末尾的 "+"：退回未强化版本
        base = name.strip().rstrip("+＋")
        return self._cards.get(base)

    def cost(self, name: str) -> int | None:
        row = self.get(name)
        if row is None:
            return None
        value = row.get("cost")
        return int(value) if isinstance(value, int) else None

    def name_of(self, card_id: str, upgrade: int = 0) -> str | None:
        """``(ProduceCardId, upgrade)`` → 卡名；查不到返回 None。

        考试牌序（``ExamDrawPlan``）里全是 id/upgrade，把它转成搜索用的
        ``CardSpec`` 需要先找卡名（卡表按名字索引）。索引懒建一次。
        """
        index = getattr(self, "_reverse_index", None)
        if index is None:
            index = {}
            for name, row in self._cards.items():
                row_id = row.get("id")
                if isinstance(row_id, str) and row_id:
                    index.setdefault((row_id, int(row.get("upgrade") or 0)), name)
            self._reverse_index = index
        return index.get((str(card_id), int(upgrade)))

    def meta(self, name: str) -> CardMeta | None:
        row = self.get(name)
        if row is None:
            return None
        return CardMeta(
            name=name,
            cost=int(row.get("cost") or 0),
            rarity=str(row.get("rarity") or ""),
            plan=str(row.get("plan") or ""),
            category=str(row.get("category") or ""),
            effects=tuple(str(effect.get("type", "")) for effect in row.get("effects") or ()),
        )

    def score_of(self, name: str) -> int | None:
        """卡面打分数值（ExamLesson 的 v1）；查不到返回 None。"""
        row = self.get(name)
        if row is None:
            return None
        for effect in row.get("effects") or []:
            if effect.get("type") == "ExamLesson":
                values = [v for v in effect.get("values") or [] if v]
                if values:
                    return int(values[0])
        return 0

    # 能滚雪球的 buff 类效果（打法知识库：感性先铺集中/好调）
    COMBO_EFFECTS = ("ExamLessonBuff", "ExamConcentration", "ExamParameterBuff")

    # ---- 奖励选卡估值 ------------------------------------------------------
    # 先按效果类型定档（不看稀有度），稀有度只在最后加成：
    #   层数类（集中/好调/温存/全力/印象…）：12-15
    #   功能类（抽牌/可出牌次数/参数上升…）：10-13
    #   生存类（元气/回体力…）：8-10
    #   纯白值：score / cost
    # 旧公式对 SSR 只 +3，9 分/3 费的 SSR 技能卡只有 6.0，输给所有纯 buff 卡。
    STACK_EFFECT_VALUES: ClassVar[dict[str, float]] = {
        "ExamConcentration": 15.0,  # 集中（強気変更）
        "ExamPreservation": 15.0,  # 温存
        "ExamOverPreservation": 15.0,
        "ExamLessonBuff": 14.0,  # 好调
        "ExamLessonBuffAdditive": 14.0,
        "ExamLessonBuffAdditiveFix": 14.0,
        "ExamLessonBuffDependParameterBuff": 14.0,
        "ExamLessonBuffMultiple": 14.0,
        "ExamMultipleLessonBuffLesson": 14.0,
        "ExamLessonAddMultipleLessonBuff": 14.0,
        "ExamPrerequisite": 14.0,  # 前提：攒够层数才解锁强效果
        "ExamFullPowerPoint": 13.0,  # 全力
        "ExamFullPowerPointAdditive": 13.0,
        "ExamReview": 13.0,  # 好印象
        "ExamReviewAdditive": 13.0,
        "ExamReviewCountAdd": 13.0,
        "ExamReviewDependReviewConsumptionSum": 13.0,
        "ExamReviewMultiple": 13.0,
        "ExamReviewPerSearchCount": 13.0,
        "ExamReviewValueMultiple": 13.0,
        "ExamEnthusiasticAdditive": 13.0,
        "ExamEnthusiasticMultiple": 13.0,
        "ExamCardPlayAggressive": 13.0,  # 干劲（出牌叠层）
        "ExamAggressiveAdditive": 13.0,
        "ExamAggressiveAdditiveFix": 13.0,
        "ExamAggressiveValueMultiple": 13.0,
        "ExamAddGrowEffect": 13.0,  # 成长
        "ExamLessonFullPowerPoint": 13.0,  # 全力值累计折算打分
        "ExamFullPowerLessonMultipleAdditive": 13.0,  # 全力强化
        "ExamEnthusiasticTurnAdd": 13.0,  # 热意延长（多一回合倍率）
        "ExamStatusEnchant": 12.0,  # 状态附魔（效果在内层）
        "ExamStatusEnchantEncore": 12.0,
    }
    FUNCTION_EFFECT_VALUES: ClassVar[dict[str, float]] = {
        "ExamParameterBuff": 13.0,  # 参数上升
        "ExamParameterBuffAdditive": 13.0,
        "ExamParameterBuffMultiplePerTurn": 13.0,
        "ExamExtraTurn": 13.0,  # 额外回合（多打一轮）
        "ExamCardDraw": 12.0,  # 抽牌
        "ExamHandGraveCountCardDraw": 12.0,
        "ExamCardSearchEffectPlayCountBuff": 12.0,
        "ExamPlayableValueAdd": 12.0,  # 可出牌次数 +1
        "ExamCardCreateId": 11.0,  # 生成/检索卡（手牌资源）
        "ExamCardCreateSearch": 11.0,
        "ExamForcePlayCardSearch": 11.0,
        "ExamForcePlayCardSearchWithCost": 11.0,
        "ExamLessonAddMultipleParameterBuff": 12.0,  # 打点 + 参数上升
        "ExamCardMove": 10.0,  # 手牌/弃牌移动（资源调度）
        "ExamEffectTimer": 9.0,  # 延迟触发
        "ExamEffectTimerEndTurn": 9.0,  # 回合结束延迟触发
    }
    SUSTAIN_EFFECT_VALUES: ClassVar[dict[str, float]] = {
        "ExamBlock": 9.0,  # 元气（保命，不加分）
        "ExamBlockAddMultipleAggressive": 9.0,
        "ExamBlockDependBlockConsumptionSum": 9.0,
        "ExamBlockFix": 9.0,
        "ExamBlockPerUseCardCount": 9.0,
        "ExamBlockRestriction": 8.0,
        "ExamStaminaRecoverFix": 9.0,  # 回体力
        "ExamStaminaRecoverMultiple": 9.0,
        "ExamStaminaConsumptionDown": 8.0,
        "ExamStaminaConsumptionDownFix": 8.0,
        "ExamStaminaReduce": 8.0,
        "ExamAntiDebuff": 9.0,
        "ExamDebuffRecover": 9.0,
    }
    # 各档上限：层数 15 / 功能 13 / 生存 10；多种效果每种 +0.5，封顶当前档位
    STACK_TIER_CAP = 15.0
    FUNCTION_TIER_CAP = 13.0
    SUSTAIN_TIER_CAP = 10.0
    # 稀有度加成：SSR/Legend +5，SR +2，R/N 0。SSR 技能卡的强效果常写在
    # 卡表建模不到的地方（条件追加打点/连携），固定 +3 会把它压到所有 buff 卡下面。
    RARITY_BONUS: ClassVar[dict[str, float]] = {"ssr": 5.0, "legend": 5.0, "sr": 2.0}
    COMBO_BONUS = 2.0  # 滚雪球价值：约等于多 2 点性价比
    SCORE_CHAIN_BONUS = 1.0  # 多段/条件追加打点：不是纯白值，额外给 1.0

    @classmethod
    def _effect_base(cls, effects: set[str]) -> float:
        """按效果类型定档；没有可估的 buff/功能/生存效果时返回 0。"""
        tiers = (
            (cls.STACK_EFFECT_VALUES, cls.STACK_TIER_CAP),
            (cls.FUNCTION_EFFECT_VALUES, cls.FUNCTION_TIER_CAP),
            (cls.SUSTAIN_EFFECT_VALUES, cls.SUSTAIN_TIER_CAP),
        )
        matched = [
            (values[effect], cap)
            for values, cap in tiers
            for effect in effects
            if effect in values
        ]
        if not matched:
            return 0.0
        best, cap = max(matched)
        # 多个效果有协同（如好调 + 抽牌 + 出牌次数），但等效值不超过当前档位上限
        return min(cap, best + 0.5 * (len(matched) - 1))

    @staticmethod
    def _has_score_chain(row: dict) -> bool:
        """同一张卡有多段/条件追加打点（count>1 或多个 ExamLesson 效果）。"""
        lessons = [e for e in row.get("effects") or [] if e.get("type") == "ExamLesson"]
        return len(lessons) > 1 or any(int(e.get("count") or 1) > 1 for e in lessons)

    def value(self, name: str) -> float | None:
        """奖励选卡估值（只用于排序，不要求精确）。

        分档：
        - 先按效果类型定档（不看稀有度）：层数类 12-15、功能类 10-13、
          生存类 8-10；纯白值卡走 ``score / cost``；
        - 多种效果取最高档并小幅叠加；
        - 已有 combo 加分保留（+2）；多段打点再 +1；
        - 最后加稀有度：SSR/Legend +5、SR +2、R/N 0。
        """
        score = self.score_of(name)
        if score is None:
            return None
        row = self.get(name) or {}
        effects = {str(effect.get("type", "")) for effect in row.get("effects") or []}
        cost = self.cost(name)
        white = score / max(cost if cost is not None else 1, 1)
        effect_base = self._effect_base(effects)
        base = max(white, effect_base) if score > 0 else effect_base
        if effects & set(self.COMBO_EFFECTS):
            base += self.COMBO_BONUS
        if score > 0 and self._has_score_chain(row):
            base += self.SCORE_CHAIN_BONUS
        rarity = str(row.get("rarity") or "").strip().lower()
        return base + self.RARITY_BONUS.get(rarity, 0.0)

    @staticmethod
    def looks_conditional(text: str) -> bool:
        return any(word in (text or "") for word in CONDITION_WORDS)
