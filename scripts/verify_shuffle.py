"""洗牌重放验证：examSeedValue + 考试牌堆 → 精确牌序（含支援强化掷点与弃牌堆重洗）。

整条考试随机数流（实现见 ``src/gkagent/sim/exam_shuffle.py``）：

  ① 开局：回合属性 ``turns-3`` 次 + NPC 分数 ``npc_count*turns`` 次
     → 洗牌前 K = (turns-3) + npc_count*turns（produce-002 プロ是 5 个 NPC，K = 6*turns-3）；
     这里的 turns 是**配置回合数**（中间考试到 forceEndScore 提前结束时，K 仍按配置回合算）。
  ② 洗初始牌堆 = Fisher-Yates 倒序洗「number 升序」牌堆；
  ③ 第 1 回合先 SetInitialCard（isInitial 卡），再补抽到 turnStartDistribute 张；
  ④ 每回合抽牌后：支援强化掷点（入手顺序 × 支援卡顺序，各掷 integer(0,1000)）；
  ⑤ 牌堆抽空：洗弃牌堆（进弃牌堆的先后顺序 = 出牌顺序 + 回合末剩余手牌顺序；Lost 卡不进）；
  ⑥ 洗完后继续从牌堆顶抽。

验证内容（四场实机采集）：
  * 初始发牌（牌堆抽空前）逐张对照；
  * 每回合支援强化增量对照（乘上掷点的 RNG 状态必须与实战一致，否则重洗对不上）；
  * 弃牌堆重洗后的手牌逐张对照：11-20 期中 T7（掷点 45 次）、
    11-21 期中 T6（29 次）、11-21 期末 T10（46 次）。

用法：python scripts/verify_shuffle.py [--file PATH] [--k N]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zlib
from itertools import permutations
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parent))
from dig_deck import body, parse, walk

from gkagent.sim.exam_shuffle import (
    DEFAULT_NPC_COUNT,
    generate_turn_types,
    k_before_shuffle,
    opening_deck_and_rng,
    replay_initial_deck,
    reshuffle_grave,
    support_upgrade,
)

MAX_CONFIG_TURNS = 30

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
MASTER_DIR = Path(__file__).resolve().parents[1] / "data/hiro/vendor/gakumas-player/data/master"

SUPPORT_LIST_FIELD = 256246388  # UserData.userProduceProgressSupportCardList
PARAMETER_TYPE = {
    "ProduceParameterType_Vocal": 1,
    "ProduceParameterType_Dance": 2,
    "ProduceParameterType_Visual": 3,
}

# 主数据 catalog（gakumasu-diff d31baf6，2026-11-20）之后游戏版本新增的卡：
# 采集里出现但 catalog 缺条目，用以下补充值（来源见 docs/MASTER_DATA.md 附录）：
#  * p_card-01-ido-3_292：较新的 gakumasu-diff ProduceCard.yaml 里 playMovePositionType=Lost、有 +0..+3；
#  * s_card-3-0115：SupportCard 缺条目，考试内强化 filter 由 11-21 两场掷点唯一确定 = Vocal。
SUPPLEMENT_CARD_MOVE = {"p_card-01-ido-3_292": "ProduceCardMovePositionType_Lost"}
SUPPLEMENT_SUPPORT_FILTER = {"s_card-3-0115": 1}


def fmap(nodes: list) -> dict:
    out: dict = {}
    for field, _wire, value, _offset in nodes:
        out.setdefault(field, []).append(value)
    return out


def inner(value):
    return value[1] if isinstance(value, tuple) and len(value) == 2 else None


def card_of(value) -> tuple[str, int] | None:
    """ExamCard / ProduceCard：field1=produceCardId, field2=upgradeCount。"""
    node = inner(value)
    if node is None:
        return None
    m = fmap(node)
    raw = (m.get(1) or [None])[0]
    if raw is None:
        return None
    cid = raw[0].decode("utf-8", "replace") if isinstance(raw, tuple) else raw.decode("utf-8", "replace")
    return cid, (m.get(2) or [0])[0]


def get_seed(resp: bytes) -> int | None:
    for _path, field, wire, value, _offset in walk(parse(resp)):
        if field == 600 and wire == 0 and 0 < value < 2**31:
            return value
    return None


def truth_turns(req: bytes) -> list[dict]:
    """StepAuditionEndExamBattle 请求：顶层 field3 = ExamTurnEndLog（field7=回合属性，field50=回合开始手牌）。"""
    top = fmap(parse(req))
    turns = []
    for turn_log in top.get(3, []):
        node = inner(turn_log)
        if node is None:
            continue
        m = fmap(node)
        hand = [c for c in (card_of(v) for v in m.get(50, [])) if c]
        played = []
        for cmd in m.get(100, []):
            cnode = inner(cmd)
            if cnode is None:
                continue
            cm = fmap(cnode)
            if 5 in cm:
                card = card_of(cm[5][0]) if isinstance(cm[5][0], tuple) else None
                if card:
                    played.append(card)
        turns.append(
            {
                "turn": (m.get(1) or [0])[0],
                "parameterType": (m.get(7) or [0])[0],
                "hand": hand,
                "played": played,
            }
        )
    return turns


def master_db() -> Path | None:
    current = MASTER_DIR / "current.json"
    if current.is_file():
        try:
            return MASTER_DIR / json.loads(current.read_text(encoding="utf-8"))["database"]
        except (KeyError, json.JSONDecodeError, OSError):
            pass
    candidates = sorted(MASTER_DIR.glob("*/catalog.sqlite"))
    return candidates[-1] if candidates else None


def load_master_info(db: Path | None) -> tuple[frozenset, int, dict, dict]:
    """返回（isInitial 卡集合, turnStartDistribute, 卡信息, 支援卡 filter）。

    卡信息：``(ProduceCard, upgradeCount) -> {"move": playMovePositionType, "end_lost": isEndTurnLost}``；
    支援卡 filter：``supportCardId -> ProduceParameterType(0=不限/1 Vo/2 Da/3 Vi)``。
    """
    if db is None or not db.is_file():
        print(f"⚠️ 主数据不可用（{db}），按空集处理")
        return frozenset(), 3, {}, {}
    initial: set[tuple[str, int]] = set()
    turn_start_distribute = 3
    card_info: dict[tuple[str, int], dict] = {}
    support_filter: dict[str, int] = {}
    con = sqlite3.connect(db)
    try:
        for row_id, variant, payload in con.execute(
            "select row_id, variant, payload from records where table_name='ProduceCard'"
        ):
            card = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
            card_info[(row_id, int(variant))] = {
                "move": card.get("playMovePositionType"),
                "end_lost": bool(card.get("isEndTurnLost")),
            }
            if card.get("isInitial"):
                initial.add((row_id, int(variant)))
        for row_id, _variant, payload in con.execute(
            "select row_id, variant, payload from records where table_name='SupportCard'"
        ):
            card = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
            support_filter[row_id] = PARAMETER_TYPE.get(
                card.get("produceCardUpgradeLessonParameterType"), 0
            )
        row = con.execute(
            "select payload from records where table_name='ExamSetting' order by row_id limit 1"
        ).fetchone()
        if row is not None:
            setting = json.loads(zlib.decompress(row[0]).decode("utf-8", "replace"))
            turn_start_distribute = int(setting.get("turnStartDistribute", 3))
    finally:
        con.close()
    return frozenset(initial), turn_start_distribute, card_info, support_filter


def load_supports(start_rec: dict, support_filter: dict) -> list[dict]:
    """从 StepAuditionStart 响应解析支援卡（按 number 升序；permil 是服务器算好的值）。"""
    resp = body(start_rec, "resp_plain_hex")
    if resp is None:
        return []
    out = []
    for _path, field, wire, value, _offset in walk(parse(resp)):
        if field != SUPPORT_LIST_FIELD or wire != 2:
            continue
        node = inner(value)
        if node is None:
            continue
        m = fmap(node)
        raw = (m.get(5) or [None])[0]
        if raw is None:
            continue
        sid = raw[0].decode("utf-8", "replace") if isinstance(raw, tuple) else raw.decode("utf-8", "replace")
        number = (m.get(2) or [0])[0]
        out.append(
            {
                "id": sid,
                "number": number,
                "permil": (m.get(16) or [0])[0],
                "filter": SUPPLEMENT_SUPPORT_FILTER.get(sid, support_filter.get(sid, 0)),
            }
        )
    out.sort(key=lambda s: s["number"])
    return out


def load_exams(path: Path, snap_path: Path, support_filter: dict) -> list[dict]:
    """把每场考试（StepAuditionEndExamBattle）配到它之前最近一次 StepAuditionStart。

    不能按 starts[i]/ends[i] 下标配对：采集里可能有「只有 Start、没打 End」的半场
    （2026-11-20 17:19 那局），一对错位后面全错。改按时间顺序取最近的前一个 Start。
    """
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    starts = [
        (i, r) for i, r in enumerate(records) if r.get("path", "").endswith("StepAuditionStart")
    ]
    ends = [
        (i, r) for i, r in enumerate(records) if r.get("path", "").endswith("StepAuditionEndExamBattle")
    ]
    snaps = json.loads(snap_path.read_text(encoding="utf-8"))
    snap_by_record = {snap["record"]: snap for snap in snaps}
    exams = []
    for i, (end_i, end) in enumerate(ends):
        candidates = [(start_i, r) for start_i, r in starts if start_i < end_i]
        if not candidates:
            print(f"⚠️ 考试{i} {end.get('ts')} 找不到对应的 StepAuditionStart，跳过")
            continue
        start_i, start = candidates[-1]
        snap = snap_by_record.get(start_i)
        if snap is None:
            print(f"⚠️ 考试{i} {end.get('ts')} 缺少考试时刻牌堆快照（start record {start_i}），跳过")
            continue
        req = body(end, "req_plain_hex")
        seed = get_seed(body(start, "resp_plain_hex"))
        turns = truth_turns(req) if req is not None else []
        top = fmap(parse(req)) if req is not None else {}
        deck = [(c["id"], c["upgrade"]) for c in sorted(snap["deck"], key=lambda c: c["number"])]
        exams.append(
            {
                "i": i,
                "seed": seed,
                "ts": end.get("ts"),
                "deck": deck,
                "turns": turns,
                "supports": load_supports(start, support_filter),
                "npc_count": len(top.get(5, [])) or DEFAULT_NPC_COUNT,
            }
        )
    return exams


def match_stats(predicted: list[list[tuple[str, int]]], truth: list[dict]) -> dict:
    """逐回合对照。返回 id 精确、强化不冲突（实战可能临时强化）、回合集合的命中统计。"""
    pred_cards = [c for hand in predicted for c in hand]
    obs_cards = [c for turn in truth for c in turn["hand"]]
    total = len(pred_cards)
    id_hits = sum(1 for pred, obs in zip(pred_cards, obs_cards) if pred[0] == obs[0])
    variant_hits = sum(
        1 for pred, obs in zip(pred_cards, obs_cards) if pred[0] == obs[0] and obs[1] >= pred[1]
    )
    set_hits = 0
    set_total = 0
    for hand, turn in zip(predicted, truth):
        if len(hand) != len(turn["hand"]):
            continue  # 牌堆抽空的那一回合只对上前几张，不按集合算
        set_total += 1
        if {c[0] for c in hand} == {c[0] for c in turn["hand"]}:
            set_hits += 1
    return {"total": total, "id": id_hits, "variant": variant_hits, "sets": (set_hits, set_total)}


def turn_type_check(
    seed: int, types: list[int], config_turns: int
) -> tuple[bool, list[int] | None, list[int] | None]:
    """校验回合属性顺序（支持「配置 N 回合但提前结束」的考试）。

    完整考试的属性序列 = 前 ``config_turns - 3`` 个随机 + 末 3 个静态（三种属性各一）。
    提前结束（forceEndScore）时只能观察到前缀：随机段的一部份 + 静态表的前几个。
    这里把「静态表顺序」当 6 种排列穷举，用观察到的随机段反推池并要求 offset 0 能复现。
    返回 ``(ok, pool, suffix)``。
    """
    played = len(types)
    random_count = config_turns - 3
    if random_count < 0 or played < random_count:
        # 观察不到完整的随机段，无法反推池（也不影响洗牌验证）
        return False, None, None
    prefix = types[:random_count]
    counts = {t: prefix.count(t) for t in (1, 2, 3)}
    for suffix in permutations((1, 2, 3)):
        order = list(reversed(suffix))
        pool = [t for t in order for _ in range(counts[t])]
        if generate_turn_types(seed, pool) != prefix:
            continue
        static_part = types[random_count:]
        if static_part and static_part != list(suffix)[: len(static_part)]:
            continue
        return True, pool, list(suffix)
    return False, None, None


# ---------------------------------------------------------------------- 弃牌堆重洗


def card_can_upgrade(card: tuple[str, int], card_info: dict) -> bool:
    """主数据里有没有 ``upgrade+1`` 变体（没有就不能再强化，支援强化整张跳过、不掷点）。

    catalog 缺条目的新卡按「可强化」处理（2026-11 新增的 ido-3_292 有 +0..+3）。
    """
    if card not in card_info:
        return True
    return (card[0], card[1] + 1) in card_info


def card_move_position(card: tuple[str, int], card_info: dict) -> str:
    info = card_info.get(card)
    if info is None:
        return SUPPLEMENT_CARD_MOVE.get(card[0], "ProduceCardMovePositionType_Grave")
    return info.get("move") or "ProduceCardMovePositionType_Grave"


def build_grave(
    hands: list[list[tuple[str, int]]], turns: list[dict], card_info: dict
) -> tuple[list[tuple[str, int]], list[str]]:
    """按实战出牌日志重建「重洗前弃牌堆」的卡顺序。

    规则：出牌后去 Grave 的牌按出牌顺序 append（Lost 不进），回合末剩余手牌按手牌顺序 append
    （isEndTurnLost 的不进）。手牌顺序 = 初始发牌顺序，抽出后未被移除的相对顺序不变。
    """
    grave: list[tuple[str, int]] = []
    warnings: list[str] = []
    for t, hand in enumerate(hands):
        hand = [tuple(c) for c in hand]
        remaining = list(range(len(hand)))
        for cid, up in turns[t]["played"]:
            cand = [i for i in remaining if hand[i][0] == cid and hand[i][1] <= up]
            if not cand:
                warnings.append(f"T{t + 1} 打出的卡不在起始手牌里：{cid}+{up}（考试内生成/移动的卡？）")
                continue
            exact = [i for i in cand if hand[i][1] == up]
            idx = (exact or cand)[0]
            remaining.remove(idx)
            base = hand[idx]
            if card_move_position(base, card_info) != "ProduceCardMovePositionType_Lost":
                grave.append(base)
        for i in remaining:
            base = hand[i]
            if (card_info.get(base) or {}).get("end_lost"):
                continue
            grave.append(base)
    return grave, warnings


def verify_reshuffle(
    exam: dict,
    hands: list[list[tuple[str, int]]],
    config_turns: int,
    turn_start_distribute: int,
    card_info: dict,
) -> dict | None:
    """重放「初始牌堆抽空之后」的支援强化掷点 + 弃牌堆重洗，对照实战手牌。

    返回 ``None``（没有重洗样本）或结果 dict；``skipped`` 非空表示样本不可验证。
    """
    turns = exam["turns"]
    total_turns = len(turns)
    last_hand_size = len(hands[-1])
    if last_hand_size < turn_start_distribute and len(hands) < total_turns:
        complete = len(hands) - 1  # 重洗发生在第 len(hands) 回合内
        kind = "回合内"
    elif last_hand_size == turn_start_distribute and len(hands) < total_turns:
        complete = len(hands)  # 重洗发生在下一回合开始抽牌时
        kind = "回合开始"
    else:
        return None

    # 从「初始洗牌后」的 RNG 状态开始，按实战手牌顺序补掷支援强化（每回合 used 清空）
    rng, _deck = opening_deck_and_rng(exam["seed"], exam["deck"], k_before_shuffle(config_turns, exam["npc_count"]))
    rolls = 0
    successes = 0
    bump_ok = True
    for t in range(complete):
        hand = [tuple(c) for c in hands[t]]
        used: list[str] = []
        planned, turn_rolls = support_upgrade(
            rng,
            hand,
            exam["supports"],
            turns[t]["parameterType"],
            used=used,
            upgradeable=lambda card: card_can_upgrade(card, card_info),
        )
        rolls += turn_rolls
        successes += len(planned)
        got_bumps = [0] * len(hand)
        for card, _sid in planned:
            got_bumps[hand.index(card)] += 1
        obs_bumps = [obs[1] - base[1] for base, obs in zip(hand, turns[t]["hand"])]
        if got_bumps != obs_bumps:
            bump_ok = False

    grave, warnings = build_grave(hands, turns, card_info)
    if warnings:
        return {
            "kind": kind,
            "turn": complete + 1,
            "skipped": "；".join(warnings),
            "rolls": rolls,
            "successes": successes,
            "bump_ok": bump_ok,
        }

    shuffled = reshuffle_grave(rng, grave)
    want = [c for turn in turns[complete:] for c in turn["hand"]]
    if kind == "回合内":
        first = [tuple(c) for c in hands[-1]]
        got = first + shuffled[: len(want) - len(first)]
    else:
        got = shuffled[: len(want)]
    ok = len(got) == len(want) and all(
        pred[0] == obs[0] and pred[1] <= obs[1] for pred, obs in zip(got, want)
    )
    return {
        "kind": kind,
        "turn": complete + 1,
        "grave": len(grave),
        "rolls": rolls,
        "successes": successes,
        "bump_ok": bump_ok,
        "ok": ok,
        "got": got,
        "want": want,
        "skipped": None,
    }


def report_exam(
    exam: dict, initial: frozenset, turn_start_distribute: int, card_info: dict, k: int | None
) -> bool:
    seed = exam["seed"]
    deck = exam["deck"]
    turns = exam["turns"]
    npc = exam["npc_count"]
    played = len(turns)
    if seed is None or not deck or not turns:
        print(f"\n=== 考试{exam['i']} {exam['ts']} 数据不全（seed={seed} 牌堆={len(deck)} 回合={played}）")
        return False

    deck_initial = {c for c in deck if c in initial}
    initial_keys = frozenset(deck_initial)

    def replay(turns_cfg: int) -> list[list[tuple[str, int]]]:
        return replay_initial_deck(
            seed,
            deck,
            k_before_shuffle(turns_cfg, npc),
            initial_keys=initial_keys,
            turn_start_distribute=turn_start_distribute,
        )

    # 1) 洗牌前消耗 K = (turns-3) + npc*turns，其中 turns 是「配置回合数」而不是实战回合数：
    #    期中考试到 forceEndScore 会提前结束，但回合属性/NPC 分数在开局仍按配置回合数生成。
    config_turns: int | None = None
    predicted: list[list[tuple[str, int]]] = []
    stats: dict | None = None
    if k is None:
        for candidate in [played, *range(played + 1, MAX_CONFIG_TURNS + 1)]:
            probe = replay(candidate)
            probe_stats = match_stats(probe, turns)
            if probe_stats["id"] == probe_stats["total"]:
                config_turns = candidate
                predicted = probe
                stats = probe_stats
                break
    else:
        config_turns = played
        predicted = replay_initial_deck(
            seed, deck, k, initial_keys=initial_keys, turn_start_distribute=turn_start_distribute
        )
        stats = match_stats(predicted, turns)

    print(f"\n=== 考试{exam['i']} {exam['ts']} seed=0x{seed:08X} 牌堆 {len(deck)} 张 / 实战 {played} 回合 ===")
    if config_turns is None:
        config_turns = played
        print(f"  ⚠️ 配置回合 {played}..{MAX_CONFIG_TURNS} 都复现不出，按实战回合 {played} 展示")
    k_formula = k_before_shuffle(config_turns, npc)
    print(f"  K = (turns-3) + npc*turns = {max(0, config_turns - 3)} + {npc}*{config_turns} = {k_formula}"
          + ("" if k is None or k == k_formula else f"（强制 --k {k}）"))
    if config_turns != played:
        print(f"  ℹ️ 配置 {config_turns} 回合、实战只打了 {played} 回合：到 forceEndScore 提前结束，"
              f"K 仍按配置回合算")

    # 2) 回合属性验证：前 config_turns-3 个在 RNG offset 0 复现
    types = [t["parameterType"] for t in turns]
    types_ok, pool, suffix = turn_type_check(seed, types, config_turns)
    if types_ok:
        extra = f"，静态末 3 回合 {suffix}" if suffix else ""
        print(f"  回合属性: ✅ offset 0 复现（池 {pool}{extra}）")
    elif len(types) < config_turns - 3:
        print(f"  回合属性: ⏭ 实战只到第 {played} 回合（配置随机段 {config_turns - 3} 个），跳过")
    else:
        print(f"  回合属性: ⚠️ 未复现（末 3 回合观察值 {types[-3:]}）")

    # 3) 洗牌重放结果
    assert stats is not None
    ok = stats["id"] == stats["total"]
    mark = "✅" if ok else "❌"
    print(f"  isInitial 卡: {sorted(deck_initial) or '无'}")
    print(f"  初始发牌重放: {mark} 整段 {stats['id']}/{stats['total']} 张 id 精确、"
          f"{stats['variant']}/{stats['total']} 张强化不冲突；回合集合 {stats['sets'][0]}/{stats['sets'][1]}")

    # 4) 支援强化掷点 + 弃牌堆重洗（整条随机数流的后半段）
    reshuffle_ok = True
    if ok and k is None:
        reshuffle_ok = _report_reshuffle(exam, predicted, config_turns, turn_start_distribute, card_info)

    if ok:
        return reshuffle_ok if k is None else True

    # 5) 公式不通时按 K 搜索（保留旧的调试能力）
    if k is None:
        hits = []
        for candidate in range(2001):
            pred = replay_initial_deck(
                seed,
                deck,
                candidate,
                initial_keys=initial_keys,
                turn_start_distribute=turn_start_distribute,
            )
            probe = match_stats(pred, turns)
            if probe["id"] == probe["total"]:
                hits.append(candidate)
        if hits:
            print(f"  ⚠️ 配置回合 3..{MAX_CONFIG_TURNS} 的公式 K 都不对，但 K={hits[:5]} 可整段复现"
                  f"（记录进 docs/TROUBLESHOOTING.md）")
        else:
            print("  ⚠️ K=0..2000 也复现不出（数据/模型需复查）")
    return False


def _report_reshuffle(
    exam: dict,
    hands: list[list[tuple[str, int]]],
    config_turns: int,
    turn_start_distribute: int,
    card_info: dict,
) -> bool:
    if not exam["supports"]:
        print("  支援强化/重洗: ⏭ 没解析到支援卡列表，跳过")
        return True
    result = verify_reshuffle(exam, hands, config_turns, turn_start_distribute, card_info)
    if result is None:
        print("  支援强化/重洗: ⏭ 牌堆没抽空（无重洗样本）")
        return True
    bump = "✅" if result.get("bump_ok") else "❌"
    if result.get("skipped"):
        print(f"  支援强化: 掷点 {result['rolls']} 次、成功 {result['successes']} 次，"
              f"逐回合强化增量 {bump}")
        print(f"  弃牌堆重洗（T{result['turn']} {result['kind']}）: ⏭ 跳过（{result['skipped']}）")
        return True
    ok = result["ok"]
    print(f"  支援强化: 掷点 {result['rolls']} 次、成功 {result['successes']} 次，"
          f"逐回合强化增量 {bump}")
    print(f"  弃牌堆重洗（T{result['turn']} {result['kind']}，grave {result['grave']} 张）: "
          f"{'✅' if ok else '❌'} {len(result['want'])}/{len(result['want'])} 张逐张对照"
          f"（掷点 {result['rolls']} 次后洗）")
    if not ok:
        print("   实战:", result["want"])
        print("   预测:", result["got"])
    return ok and bool(bump == "✅")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT))
    parser.add_argument("--snap", default=str(DEFAULT.parent / "deck_snapshots.json"))
    parser.add_argument("--k", type=int, default=None, help="强制指定洗牌前 RNG 消耗次数（调试用）")
    args = parser.parse_args(argv)

    path = Path(args.file)
    snap = Path(args.snap)
    if not path.is_file():
        print(f"❌ 采集文件不存在: {path}")
        return 1
    if not snap.is_file():
        print(f"❌ 牌堆快照不存在: {snap}（先跑 scripts/reconstruct_deck.py）")
        return 1

    initial, turn_start_distribute, card_info, support_filter = load_master_info(master_db())
    exams = load_exams(path, snap, support_filter)
    print(f"共 {len(exams)} 场考试；turnStartDistribute={turn_start_distribute}；"
          f"isInitial 卡 {len(initial)} 种变体；ProduceCard {len(card_info)} 行")
    results = [
        report_exam(exam, initial, turn_start_distribute, card_info, args.k) for exam in exams
    ]
    print(f"\n汇总: {sum(results)}/{len(results)} 场考试整段复现（含重洗）")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
