"""真机 ``LessonState`` → GKMS UIObs v1（GKMSUINet 的输入，MIT）。

格式来源：``data/bench_repo/docs/format.md`` 第 5 节，schema 在
``GKMSUINet/gkms_uinet/data/uiobs.v1.schema.json``。本模块只做"读屏结果 → 观测"
的格式转换，不做推理；推理与模型加载见 :mod:`gkagent.sim.uinet`。

真机 OCR 的已知缺口（读不到的字段一律给保守默认值，绝不抛异常）：

- **山札/弃牌/保留/除外**：屏幕只显示手牌，没有山札顺序（也没有成员表），
  这四个区一律给空列表。UINet 训练时看得到这些牌，真机这里信息更少。
- **元气(block)**：课程/试镜界面不显示元气，默认 ``0``。
- **指針/段数(stance)**：没有读屏来源，默认 ``[None, 0]``。
- **状态图标(status)、持久效果(ench)、饮料(drinks)**：没有读屏来源，默认空。
- **体力上限(max_stamina)**：屏幕只显示"当前/上限"里的当前值；课程实拍开局是
  ``35/35``，所以默认 ``35``（且不小于当前体力）。
- **每回合属性(types)、三项倍率(permil)、审查基准(crit)**：界面不显示逐回合
  属性序列/千分比，``types`` 默认全 1（Vo），``permil`` 默认 ``[1000,1000,1000]``，
  ``crit`` 默认 ``[0,0,0]``。
- **卡牌自定义(c)、考试中成长(g)**：读不到，省略；强化次数 ``u`` 取卡表的
  ``upgrade`` 字段。
- **本回合已出牌(plays)**：屏幕没有计数，由调用方（策略）把
  ``LessonPolicy._plays_this_turn`` 传进来；``playable`` 默认按"每回合 3 张"减。
- **exam.produce / exam.step**：这是 H.I.F 考试的信息，课程界面没有；按
  ``state.kind`` 选保守默认（课程→produce-007/MID1，试镜→produce-008/FINAL），
  调用方可以显式覆盖。
- **exam.plan**：由策略当前的方案（sense/logic/anomaly）映射成 2/3/4。

``p``（能否打出）是**推断值**：卡面费用（OCR）或卡表费用 ≤ 当前体力时为 1；
费用/体力未知时乐观地给 1，由调用方在真正点击前再核对一次。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from gkagent.data.card_table import CardTable
from gkagent.vision.lesson import LessonCard, LessonState

__all__ = [
    "DEFAULT_MAX_STAMINA",
    "DEFAULT_PLAY_LIMIT",
    "PLAN_CODES",
    "card_obs",
    "legal_actions",
    "resolve_card",
    "to_uiobs",
]

#: 屏幕方案名 → ProducePlanType 数值（2 感性 / 3 理性 / 4 非凡）。
PLAN_CODES: dict[str, int] = {"sense": 2, "logic": 3, "anomaly": 4}
DEFAULT_PLAN_CODE = 2  # sense

#: 课程实拍开局体力 35/35；读不到上限时用它兜底。
DEFAULT_MAX_STAMINA = 35
#: 与 ``sim.lesson.GameConfig.plays_per_turn`` 一致：真机每回合基础 1 张
#: （B3 2026-11-22 按 gakumas-tools TurnManager cardUsesRemaining=1 核实；
#: 额外出牌来自卡效果 ExamPlayableValueAdd / P 道具）。
DEFAULT_PLAY_LIMIT = 1

PRODUCE_LESSON = "produce-007"  # 選抜試験
PRODUCE_AUDITION = "produce-008"  # 本戦
STEP_LESSON = "AUDITION_MID1"
STEP_AUDITION = "AUDITION_FINAL"

# 试镜界面的属性名（LessonReader 只读这三种），用于把 types 填得比全 Vo 更接近屏幕。
_ATTRIBUTE_CODES = {"歌唱": 1, "舞蹈": 2, "视觉": 3}

_UI_LABELS = ("SELECT", "SEECT", "SELCET")


def _as_int(value: object, default: int = 0) -> int:
    """把读屏数字/数字字符串转成 int；None/坏值用 ``default``。"""
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_name(name: str | None) -> str:
    """查表用卡名：去掉 OCR 混进来的 SELECT/SEECT 标签和多余空白。"""
    text = str(name or "")
    for label in _UI_LABELS:
        text = text.replace(label, " ")
    return " ".join(text.split())


def _table_row(name: str, table: CardTable | None) -> dict | None:
    if table is None:
        return None
    cleaned = _clean_name(name)
    for candidate in (cleaned, str(name or "").strip()):
        if candidate:
            row = table.get(candidate)
            if row is not None:
                return row
    return None


def resolve_card(
    name: str,
    *,
    table: CardTable | None = None,
    cards: object | None = None,
) -> tuple[str, int]:
    """卡名 → ``(ProduceCard id, 强化次数)``。

    优先查卡表（``data/knowledge/card_table.json``，带 id/upgrade）；卡表查不到
    时用 ``CardLibrary``（只有 id，强化次数按名字末尾的 ``+`` 数）。都查不到时
    返回 ``("", 0)``——保留这张牌的序号，别让 ``legal`` 的 index 错位。
    """
    row = _table_row(name, table)
    if row is not None and row.get("id"):
        upgrade = _as_int(row.get("upgrade"), 0)
        return str(row["id"]), max(0, upgrade)
    if cards is not None:
        lookup = getattr(cards, "lookup", None) or getattr(cards, "find", None)
        info = lookup(_clean_name(name)) if lookup else None
        if info is not None and getattr(info, "id", ""):
            return str(info.id), 0
    cleaned = _clean_name(name)
    return "", max(0, cleaned.count("+") + cleaned.count("＋"))


def _card_cost(card: LessonCard, table: CardTable | None) -> int | None:
    if card.cost is not None:
        return max(0, _as_int(card.cost))
    if table is not None:
        cost = table.cost(_clean_name(card.name))
        if cost is not None:
            return max(0, int(cost))
    return None


def card_obs(
    card: LessonCard,
    *,
    table: CardTable | None = None,
    cards: object | None = None,
    stamina: int | None = None,
) -> dict[str, Any]:
    """一张手牌 → UIObs 的 ``{id, u, p}``；``c``/``g`` 读不到，省略。"""
    card_id, upgrade = resolve_card(card.name, table=table, cards=cards)
    cost = _card_cost(card, table)
    playable = cost is None or stamina is None or cost <= stamina
    return {"id": card_id, "u": upgrade, "p": 1 if playable else 0}


def _zone_cards(
    entries: Iterable[LessonCard | dict[str, Any]] | None,
    *,
    table: CardTable | None,
    cards: object | None,
) -> list[dict[str, Any]]:
    """山札/弃牌/保留/除外/已出牌：只要 id 和强化次数，没有顺序、没有 p。"""
    out: list[dict[str, Any]] = []
    for entry in entries or ():
        if isinstance(entry, LessonCard):
            card_id, upgrade = resolve_card(entry.name, table=table, cards=cards)
        elif isinstance(entry, dict):
            card_id = str(entry.get("id") or "")
            upgrade = max(0, _as_int(entry.get("u"), 0))
        else:
            continue
        if card_id:
            out.append({"id": card_id, "u": upgrade})
    return out


def legal_actions(hand: Sequence[dict[str, Any]], *, allow_skip: bool) -> list[list[Any]]:
    """合法动作：``p=1`` 的手牌 + （允许时）结束回合。"""
    legal: list[list[Any]] = [["play", i] for i, card in enumerate(hand) if card.get("p")]
    if allow_skip:
        legal.append(["end"])
    return legal


def _triple(value: Sequence[int] | None, default: int) -> list[int]:
    if value is None:
        return [default, default, default]
    items = [_as_int(item, default) for item in value]
    if len(items) != 3:
        return [default, default, default]
    return items


def _types(value: Sequence[int] | None, limit: int, attribute: str | None) -> list[int]:
    if value is not None and len(value) == limit:
        parsed = [_as_int(item, 0) for item in value]
        if all(item in (1, 2, 3) for item in parsed):
            return parsed
    code = _ATTRIBUTE_CODES.get((attribute or "").strip(), 1)
    return [code] * max(1, limit)


def to_uiobs(
    state: LessonState,
    *,
    table: CardTable | None = None,
    cards: object | None = None,
    plan: str | None = None,
    allow_skip: bool = True,
    plays: int = 0,
    playable: int | None = None,
    max_stamina: int | None = None,
    produce: str | None = None,
    step: str | None = None,
    types: Sequence[int] | None = None,
    permil: Sequence[int] | None = None,
    crit: Sequence[int] | None = None,
    block: int = 0,
    status: Iterable[Sequence[Any]] | None = None,
    ench: Iterable[Sequence[Any]] | None = None,
    deck: Iterable[LessonCard | dict[str, Any]] | None = None,
    grave: Iterable[LessonCard | dict[str, Any]] | None = None,
    hold: Iterable[LessonCard | dict[str, Any]] | None = None,
    lost: Iterable[LessonCard | dict[str, Any]] | None = None,
    played: Iterable[LessonCard | dict[str, Any]] | None = None,
    drinks: Iterable[str] | None = None,
) -> dict[str, Any]:
    """把一帧 ``LessonState`` 转成 UIObs v1（字段含义见模块 docstring）。

    任何字段缺失/类型不对都用默认值，不抛异常；``cards`` 是 ``CardLibrary``
    之类带 ``lookup``/``find`` 的卡库，卡表查不到时兜底。
    """
    stamina_value = state.stamina
    stamina = max(0, _as_int(stamina_value, 0)) if stamina_value is not None else 0
    if max_stamina is not None:
        max_stamina_value = max(stamina, 1, _as_int(max_stamina, DEFAULT_MAX_STAMINA))
    else:
        max_stamina_value = max(DEFAULT_MAX_STAMINA, stamina)

    cards_list = list(state.cards or ())
    hand = [
        card_obs(card, table=table, cards=cards, stamina=stamina if stamina_value is not None else None)
        for card in cards_list
    ]

    plays_value = max(0, _as_int(plays, 0))
    if playable is None:
        playable = max(0, DEFAULT_PLAY_LIMIT - plays_value)
    playable_value = max(0, _as_int(playable, 0))

    kind = state.kind if state.kind in {"lesson", "audition"} else "lesson"
    produce_value = produce or (
        PRODUCE_AUDITION if kind == "audition" else PRODUCE_LESSON
    )
    step_value = step or (STEP_AUDITION if kind == "audition" else STEP_LESSON)

    turns_left = state.turns_left
    total_turns = state.total_turns
    limit = max(1, _as_int(total_turns if total_turns is not None else turns_left, 1))
    current_turn = state.current_turn
    if current_turn is None:
        current_turn = limit - _as_int(turns_left, limit) + 1
    turn = min(max(1, _as_int(current_turn, 1)), limit)

    plan_code = PLAN_CODES.get(str(plan or "").strip().lower(), DEFAULT_PLAN_CODE)

    status_out = [list(item) for item in status or ()]
    ench_out = [list(item) for item in ench or ()]

    return {
        "v": "uiobs.v1",
        "exam": {
            "produce": produce_value,
            "step": step_value,
            "plan": plan_code,
            "turn": turn,
            "limit": limit,
            "types": _types(types, limit, state.attribute),
            "permil": _triple(permil, 1000),
            "crit": _triple(crit, 0),
        },
        "num": {
            "score": max(0, _as_int(state.score, 0)),
            "stamina": stamina,
            "max_stamina": max_stamina_value,
            "block": max(0, _as_int(block, 0)),
            "playable": playable_value,
            "plays": plays_value,
        },
        "stance": [None, 0],
        "status": status_out,
        "ench": ench_out,
        "hand": hand,
        "deck": _zone_cards(deck, table=table, cards=cards),
        "grave": _zone_cards(grave, table=table, cards=cards),
        "hold": _zone_cards(hold, table=table, cards=cards),
        "lost": _zone_cards(lost, table=table, cards=cards),
        "played": _zone_cards(played, table=table, cards=cards),
        "drinks": [str(item) for item in drinks or ()],
        "legal": legal_actions(hand, allow_skip=allow_skip),
    }
