"""考试牌组的 known-info 风险扫描。

背景（2026-11-22 情报）：考试的 xorshift32 推进次数（我们洗牌模型里的 ``K``）在**纯牌组**下
= ``open_turn_types`` + ``session_start_turn`` + 初始洗牌 + 弃牌堆重洗 + 支援强化掷点，
已被四场实战逐张验证。但卡表里还有一类效果会在考试内**额外消耗随机数**：

- ``ExamCardCreateId`` / ``ExamCardCreateSearch``：随机卡池生成卡牌（消耗次数远多于生成数）；
- ``ExamCardMove``：效果把卡移动到牌库随机位置；
- ``ExamForcePlayCardSearch`` / ``ExamCardSearchEffectPlayCountBuff`` /
  ``ExamReviewPerSearchCount``：卡牌搜索（随机排序/随机选取）；
- ``ExamSearchPlayCardStaminaConsumptionChange``：搜索相关的费用变化；
- 恐慌类（命中时对每张手牌随机判定）等。

只要牌组里出现这些效果的卡，**K 就无法精确计数**，``known_draw`` 只能用到第一个此类事件。
本模块在 ``build_exam_setup`` 生成记录时做**事前检测**，把风险写进 ``rng_risk`` 字段；
``ExamSetup.known_info_ok`` 为 False 时 ``ExamDrawPlan`` 直接停用（不启用全知），
避免"核对失败才事后停用"和错误计划。

数据来源：``data/knowledge/card_table.json``（主数据/gakumasu-diff 口径，含 ``effects`` 列表）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CARD_TABLE_PATH = ROOT / "data" / "knowledge" / "card_table.json"

# 会额外消耗考试 RNG 的效果类型（来自 gkbench 官方 AI 文档 + 群公开的"考试 RNG 消费入口"清单）
EXTRA_RNG_EFFECT_TYPES: frozenset[str] = frozenset(
    {
        "ExamCardCreateId",  # 随机卡池生成卡牌
        "ExamCardCreateSearch",  # 随机卡池生成（搜索变体，消耗次数远多于生成数）
        "ExamCardMove",  # 效果移动卡到牌库随机位置
        "ExamForcePlayCardSearch",  # 强制打"搜索到的牌"
        "ExamCardSearchEffectPlayCountBuff",  # 搜索计数 buff（搜索随机排序的触发者）
        "ExamReviewPerSearchCount",  # 按搜索次数给好印象（搜索相关）
        "ExamSearchPlayCardStaminaConsumptionChange",  # 搜索牌的费用变化
        "ExamPanic",  # 恐慌（不同版本命名，保守纳入）
        "ExamPanicCommand",
    }
)


def load_extra_rng_index(path: str | Path | None = None) -> dict[str, frozenset[str]]:
    """读卡表，返回 ``card_id -> 命中的额外 RNG 效果类型集合``。"""
    table_path = Path(path) if path is not None else DEFAULT_CARD_TABLE_PATH
    if not table_path.exists():
        return {}
    raw = json.loads(table_path.read_text(encoding="utf-8"))
    cards = raw.get("cards", raw)
    items: Iterable[Any] = cards.values() if isinstance(cards, Mapping) else cards
    index: dict[str, frozenset[str]] = {}
    for row in items:
        if not isinstance(row, Mapping):
            continue
        card_id = row.get("id")
        if not card_id:
            continue
        hits = frozenset(
            str(effect.get("type"))
            for effect in (row.get("effects") or ())
            if isinstance(effect, Mapping)
            and str(effect.get("type")) in EXTRA_RNG_EFFECT_TYPES
        )
        if hits:
            index[str(card_id)] = hits
    return index


@lru_cache(maxsize=1)
def default_extra_rng_index() -> dict[str, frozenset[str]]:
    return load_extra_rng_index()


def _card_id_of(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, Sequence) and item:
        first = item[0]
        return str(first) if first is not None else None
    return None


def deck_rng_risks(
    deck: Iterable[Any], *, index: Mapping[str, frozenset[str]] | None = None
) -> list[dict[str, Any]]:
    """扫描牌组里的额外 RNG 机制卡。

    ``deck`` 接受 ``["p_card-...", upgrade]`` / ``("p_card-...", upgrade)`` / 纯 id 三种形式
    （``build_exam_setup`` 的 ``deck`` 是前者，``ExamSetup.deck`` 也是前者）。
    返回 ``[{"card_id": ..., "effects": [类型...]}, ...]``（按字典序、去重）。
    """
    rng_index = index if index is not None else default_extra_rng_index()
    risks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in deck:
        card_id = _card_id_of(item)
        if not card_id or card_id in seen:
            continue
        hits = rng_index.get(card_id)
        if not hits:
            continue
        seen.add(card_id)
        risks.append({"card_id": card_id, "effects": sorted(hits)})
    risks.sort(key=lambda risk: str(risk["card_id"]))
    return risks


def known_info_ok(deck: Iterable[Any], *, index: Mapping[str, frozenset[str]] | None = None) -> bool:
    """牌组是否适合启用 ``known_draw``（无额外 RNG 机制卡）。"""
    return not deck_rng_risks(deck, index=index)


def format_rng_risks(risks: Iterable[Mapping[str, Any]], limit: int = 3) -> str:
    """人类可读摘要（日志/错误信息用）。"""
    items = [f"{risk.get('card_id')}({'+'.join(risk.get('effects') or [])})" for risk in risks]
    if not items:
        return "无"
    shown = items[: max(int(limit), 1)]
    suffix = f" 等 {len(items)} 张" if len(items) > len(shown) else ""
    return "、".join(shown) + suffix
