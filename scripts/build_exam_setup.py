"""考试牌序数据管线：实机采集 + 主数据 → ``out/exam_setup.json``（生产接线 ExamDrawPlan 的数据源）。

**数据来源（全部只读）**

* ``traffic.jsonl``（默认 ``C:\\GakumasLocal\\GakumasUnlock\\out\\traffic.jsonl``）：
  ``StepAuditionStart`` 响应里的 ``examSeedValue``（考试随机数种子）、支援卡列表；
  ``StepAuditionEndExamBattle`` 请求里的 ``ExamTurnEndLog``（每回合属性/手牌/出牌）。
* ``deck_snapshots.json``（默认与 traffic 同目录）：每个 Start 时刻的牌组快照（按 number 升序）。
* 主数据 ``catalog.sqlite``（``verify_shuffle.master_db()``）：``ProduceCard`` 的 ``isInitial`` /
  ``playMovePositionType`` / ``isEndTurnLost`` / 变体集合，``SupportCard`` 的强化 filter，
  ``ExamSetting.turnStartDistribute``。
* ``exam_truth.json``（可选，默认同目录）：逐回合的 score/stamina 增强；存在则按考试发起 ``ts``
  匹配（匹配不上按顺序），匹配不到的回合 score/stamina 留 ``None``，不报错。

**输出字段（``exams[]``，供生产接线直接构造 ``gkagent.sim.exam_oracle.ExamDrawOracle``）**

* ``index`` / ``ts`` / ``seed``（uint32）/ ``config_turns``（配置回合数，中间考试提前结束时
  > ``played_turns``）/ ``played_turns`` / ``npc_count`` / ``turn_start_distribute`` / ``hand_limit``；
* ``deck``：``[[produceCardId, upgradeCount], ...]``，按牌组快照 number 升序（客户端洗牌输入顺序）；
* ``supports``：``[{"id","number","permil","filter"}]``，number 升序（支援强化掷点顺序）；
* ``initial_keys``：``deck`` 里主数据 ``isInitial`` 的卡（第 1 回合 SetInitialCard 用）；
* ``card_variants``：``{produceCardId: 主数据最大 upgrade 变体}``，用于 ``upgradeable`` 回调
  （``card[1] < max_variant`` 才可继续强化；主数据缺条目的新卡用 ``MISSING_MAX_VARIANT`` 兜底）；
* ``lost_keys``：``playMovePositionType == Lost`` 的牌（出牌后不进弃牌堆）；
* ``end_lost_keys``：``isEndTurnLost`` 的牌（回合末剩余手牌不进弃牌堆）；
* ``truth``：``[{turn, parameterType, hand, played, score, stamina}]``，实机逐回合真值。

**怎么用**：读 JSON 后对每场考试
``ExamDrawOracle(seed, deck, config_turns, npc_count=..., supports=...,
initial_keys=frozenset(initial_keys), turn_start_distribute=..., hand_limit=...,
upgradeable=lambda card: variants.get(card[0]) is None or card[1] < variants[card[0]])``，
逐回合 ``draw_next_turn(parameterType, grave=...)``。

**--check（默认执行，``--no-check`` 跳过）**

用生成的 setup 数据重建 ``ExamDrawOracle``，逐回合 ``draw_next_turn`` 与 truth 手牌逐张对照 id：

* **初始牌堆段**（牌堆抽空前，每场张数 = ``len(deck)``）：严格校验，必须全中；
  四场合计 18+26+15+27 = 86 张，即 ``exam_seed`` 整段复现；
* **弃牌堆重洗段**（牌堆抽空后）：用 ``verify_shuffle.build_grave`` 按 truth 的出牌/剩余手牌重建
  grave 再继续抽。没有「考试内生成的卡进 grave」时严格要求全中（考试 0/2/3）；
  考试 1 在第 8 回合打出考试内生成的 ``p_card-00-men-3_003+1``，grave 无法从实机日志唯一重建
  （与 ``verify_shuffle`` 的跳过判定一致），该场重洗段只报告不清算。

任一段（该清算时）不中则非零退出并打印逐张差异明细。

用法::

    .venv\\Scripts\\python.exe scripts/build_exam_setup.py            # 生成 + 校验
    .venv\\Scripts\\python.exe scripts/build_exam_setup.py --no-check # 只生成
    .venv\\Scripts\\python.exe scripts/build_exam_setup.py --file X --snap Y --out Z
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import verify_shuffle as vs

from gkagent.sim.exam_oracle import ExamDrawOracle
from gkagent.sim.exam_shuffle import (
    DEFAULT_HAND_LIMIT,
    k_before_shuffle,
    replay_initial_deck,
)

MAX_CONFIG_TURNS = 30

DEFAULT_TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
DEFAULT_SNAPS = DEFAULT_TRAFFIC.parent / "deck_snapshots.json"
DEFAULT_TRUTH = DEFAULT_TRAFFIC.parent / "exam_truth.json"
DEFAULT_OUT = ROOT / "out" / "exam_setup.json"

# catalog 缺条目的新卡（见 verify_shuffle.SUPPLEMENT_CARD_MOVE）：
# p_card-01-ido-3_292 在较新的 gakumasu-diff 里有 +0..+3，主数据 catalog 没有该 id。
MISSING_MAX_VARIANT = {"p_card-01-ido-3_292": 3}


def card_key(card) -> list:
    """``(produceCardId, upgradeCount)`` → JSON 友好的 ``[id, upgrade]``。"""
    return [str(card[0]), int(card[1])]


def build_card_variants(
    deck: list[tuple[str, int]], card_info: dict
) -> tuple[dict[str, int], list[str]]:
    """``produceCardId -> 主数据最大 upgrade 变体``；deck 里出现的 id 都要有。

    主数据缺条目的 id 用 ``MISSING_MAX_VARIANT`` 兜底，再不行用 deck 里出现过的最大强化值。
    返回 ``(variants, 缺主数据的 id 列表)``。
    """
    max_variant: dict[str, int] = dict(MISSING_MAX_VARIANT)
    for cid, upgrade in card_info:
        max_variant[cid] = max(max_variant.get(cid, -1), upgrade)
    deck_max: dict[str, int] = {}
    for cid, upgrade in deck:
        deck_max[cid] = max(deck_max.get(cid, 0), upgrade)
    missing: list[str] = []
    for cid, upgrade in deck_max.items():
        if cid not in max_variant:
            missing.append(cid)
            max_variant[cid] = upgrade
    return max_variant, missing


def detect_config_turns(
    seed: int,
    deck: list[tuple[str, int]],
    truth: list[dict],
    npc_count: int,
    initial_keys: frozenset,
    turn_start_distribute: int,
) -> tuple[int, bool]:
    """照 ``verify_shuffle.report_exam``：从实战回合数起试配置回合数，truth 手牌 id 全中即采用。"""
    played = len(truth)
    for candidate in [played, *range(played + 1, MAX_CONFIG_TURNS + 1)]:
        predicted = replay_initial_deck(
            seed,
            deck,
            k_before_shuffle(candidate, npc_count),
            initial_keys=initial_keys,
            turn_start_distribute=turn_start_distribute,
        )
        stats = vs.match_stats(predicted, truth)
        if stats["total"] and stats["id"] == stats["total"]:
            return candidate, True
    return played, False


def load_exam_truth_enhancements(path: Path) -> list[dict]:
    """读可选的 ``exam_truth.json``（score/stamina 增强）；不存在或坏文件返回空列表。"""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - 坏文件兜底
        print(f"⚠️ 可选真值增强文件不可用（{path}）：{exc}，score/stamina 全部留 None")
        return []
    if not isinstance(data, list):
        print(f"⚠️ 可选真值增强文件格式不对（{path}）：应为 list，忽略")
        return []
    return [item for item in data if isinstance(item, dict)]


def match_truth_entry(enhancements: list[dict], index: int, ts: str | None) -> dict | None:
    """按考试 ``ts`` 匹配，匹配不上按顺序取第 ``index`` 条；都没有返回 None。"""
    for entry in enhancements:
        if ts is not None and entry.get("ts") == ts:
            return entry
    if index < len(enhancements):
        return enhancements[index]
    return None


def merge_truth_scores(truth: list[dict], entry: dict | None) -> None:
    """把增强文件里同回合的 score/stamina 合并进 truth（缺失留 None）。"""
    by_turn: dict[int, dict] = {}
    if entry is not None:
        for i, turn in enumerate(entry.get("turns") or []):
            if not isinstance(turn, dict):
                continue
            turn_no = turn.get("turn", i + 1)
            by_turn[int(turn_no)] = turn
    for turn in truth:
        extra = by_turn.get(int(turn["turn"]))
        turn["score"] = (extra or {}).get("score")
        turn["stamina"] = (extra or {}).get("stamina")


def build_setup(
    traffic: Path, snap: Path, truth_path: Path
) -> tuple[dict, dict]:
    """读采集 + 主数据，生成 setup dict；同时返回 check 需要的内部上下文。"""
    db = vs.master_db()
    initial, turn_start_distribute, card_info, support_filter = vs.load_master_info(db)
    exams = vs.load_exams(traffic, snap, support_filter)
    enhancements = load_exam_truth_enhancements(truth_path)

    records = []
    for index, raw in enumerate(exams):
        seed = raw["seed"]
        if seed is None:
            raise SystemExit(f"❌ 考试{index} {raw['ts']} 缺少 examSeedValue，无法生成")
        deck = [tuple(card) for card in raw["deck"]]
        truth = [dict(turn) for turn in raw["turns"]]
        npc_count = int(raw["npc_count"])
        played_turns = len(truth)
        initial_keys = frozenset(card for card in deck if card in initial)
        config_turns, config_turns_ok = detect_config_turns(
            seed, deck, truth, npc_count, initial_keys, turn_start_distribute
        )
        card_variants, missing = build_card_variants(deck, card_info)
        if missing:
            print(f"⚠️ 考试{index} 主数据缺卡（card_variants 用 deck 强化值兜底）：{missing}")
        lost_keys = [card for card in deck if vs.card_move_position(card, card_info).endswith("Lost")]
        end_lost_keys = [
            card for card in deck if (card_info.get(card) or {}).get("end_lost")
        ]
        merge_truth_scores(truth, match_truth_entry(enhancements, index, raw["ts"]))
        records.append(
            {
                "index": index,
                "ts": raw["ts"],
                "seed": int(seed),
                "config_turns": int(config_turns),
                "config_turns_ok": bool(config_turns_ok),
                "played_turns": int(played_turns),
                "npc_count": npc_count,
                "turn_start_distribute": int(turn_start_distribute),
                "hand_limit": DEFAULT_HAND_LIMIT,
                "deck": [card_key(card) for card in deck],
                "supports": [
                    {
                        "id": support["id"],
                        "number": int(support["number"]),
                        "permil": int(support["permil"]),
                        "filter": int(support["filter"]),
                    }
                    for support in raw["supports"]
                ],
                "initial_keys": [card_key(card) for card in deck if card in initial],
                "card_variants": card_variants,
                "lost_keys": [card_key(card) for card in lost_keys],
                "end_lost_keys": [card_key(card) for card in end_lost_keys],
                "truth": [
                    {
                        "turn": int(turn["turn"]),
                        "parameterType": int(turn["parameterType"]),
                        "hand": [card_key(card) for card in turn["hand"]],
                        "played": [card_key(card) for card in turn["played"]],
                        "score": turn.get("score"),
                        "stamina": turn.get("stamina"),
                    }
                    for turn in truth
                ],
            }
        )
    setup = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "traffic": str(traffic),
            "snapshots": str(snap),
            "master": str(db) if db is not None else "",
        },
        "exams": records,
    }
    context = {
        "turn_start_distribute": turn_start_distribute,
        "card_info": card_info,
    }
    return setup, context


# --------------------------------------------------------------------------- --check


def _upgradeable(card: tuple[str, int], card_variants: dict[str, int]) -> bool:
    """主数据里还有更高变体才可继续强化（id 不在 map 里按可强化）。"""
    max_upgrade = card_variants.get(card[0])
    return True if max_upgrade is None else card[1] < max_upgrade


def check_exam(record: dict, card_info: dict, turn_start_distribute: int) -> dict:
    """单场考试：用 setup 重建 oracle 逐回合对照 truth 手牌 id。

    返回 ``{ok, initial_hits, initial_total, reshuffle_hits, reshuffle_total, skipped, diffs, ...}``。
    """
    seed = record["seed"]
    deck = [tuple(card) for card in record["deck"]]
    truth = record["truth"]
    npc_count = record["npc_count"]
    config_turns = record["config_turns"]
    initial_keys = frozenset(tuple(card) for card in record["initial_keys"])
    supports = record["supports"]
    variants = record["card_variants"]

    predicted_hands = replay_initial_deck(
        seed,
        deck,
        k_before_shuffle(config_turns, npc_count),
        initial_keys=initial_keys,
        turn_start_distribute=turn_start_distribute,
    )
    grave, warnings = vs.build_grave(predicted_hands, truth, card_info)
    oracle = ExamDrawOracle(
        seed,
        deck,
        config_turns,
        npc_count=npc_count,
        supports=supports,
        initial_keys=initial_keys,
        turn_start_distribute=turn_start_distribute,
        hand_limit=DEFAULT_HAND_LIMIT,
        upgradeable=lambda card: _upgradeable(card, variants),
    )
    pred_cards: list[tuple[str, int]] = []
    obs_cards: list[tuple[str, int]] = []
    error: str | None = None
    try:
        for turn in truth:
            hand = oracle.draw_next_turn(turn["parameterType"], grave=grave)
            pred_cards.extend(hand)
            obs_cards.extend(tuple(card) for card in turn["hand"])
    except (ValueError, RuntimeError) as exc:  # pragma: no cover - 数据异常兜底
        error = str(exc)

    initial_total = len(deck)
    diffs: list[dict] = []
    pairs = list(zip(pred_cards, obs_cards))
    initial_hits = sum(1 for pred, obs in pairs[:initial_total] if pred[0] == obs[0])
    for i, (pred, obs) in enumerate(pairs[:initial_total]):
        if pred[0] != obs[0]:
            diffs.append({"pos": i + 1, "segment": "initial", "pred": card_key(pred),
                          "truth": card_key(obs)})
    reshuffle_pairs = pairs[initial_total:]
    reshuffle_hits = sum(1 for pred, obs in reshuffle_pairs if pred[0] == obs[0])
    reshuffle_total = len(reshuffle_pairs)
    skipped = "；".join(warnings) if warnings else None
    if skipped:
        # 考试内生成/移动的卡进了 grave，无法从实机日志唯一重建：只报告不清算
        for i, (pred, obs) in enumerate(reshuffle_pairs):
            if pred[0] != obs[0]:
                diffs.append({"pos": initial_total + i + 1, "segment": "reshuffle",
                              "pred": card_key(pred), "truth": card_key(obs)})
    initial_ok = initial_hits == initial_total
    reshuffle_ok = skipped is not None or reshuffle_hits == reshuffle_total
    ok = error is None and initial_ok and reshuffle_ok
    return {
        "ok": ok,
        "error": error,
        "initial_hits": initial_hits,
        "initial_total": initial_total,
        "reshuffle_hits": reshuffle_hits,
        "reshuffle_total": reshuffle_total,
        "skipped": skipped,
        "diffs": diffs,
    }


def run_check(setup: dict, context: dict) -> bool:
    """对 setup 每场考试跑 check；打印摘要 + 差异明细。返回整体是否通过。"""
    card_info = context["card_info"]
    turn_start_distribute = context["turn_start_distribute"]
    print("\n== --check：用 setup 重建 ExamDrawOracle，逐回合对照 truth 手牌 ==")
    results = []
    for record in setup["exams"]:
        result = check_exam(record, card_info, turn_start_distribute)
        results.append(result)
        seed_hex = f"0x{record['seed']:08X}"
        mark = "✅" if result["ok"] else "❌"
        line = (
            f"考试{record['index']} seed={seed_hex} config_turns={record['config_turns']}"
            f" 牌堆={result['initial_total']} 支援={len(record['supports'])}"
            f" truth回合={record['played_turns']}"
            f" | 初始段 {result['initial_hits']}/{result['initial_total']} 张"
        )
        if result["reshuffle_total"]:
            if result["skipped"]:
                line += (
                    f" | 重洗段 ⏭ 跳过 {result['reshuffle_total']} 张"
                    "（考试内生成卡进 grave，无法唯一重建）"
                )
            else:
                line += f" | 重洗段 {result['reshuffle_hits']}/{result['reshuffle_total']} 张"
        else:
            line += " | 重洗段 无（牌堆没抽空）"
        if result["error"]:
            line += f" | ⚠️ 异常：{result['error']}"
        print(f"{mark} {line}")
        if not result["ok"]:
            if result["skipped"]:
                print(f"    ℹ️ 重洗段不计入判定（{result['skipped']}）")
            for diff in result["diffs"][:20]:
                print(
                    f"    ❌ 第 {diff['pos']} 张（{diff['segment']}）："
                    f"预测 {diff['pred']} ≠ 真值 {diff['truth']}"
                )
            if len(result["diffs"]) > 20:
                print(f"    …… 另有 {len(result['diffs']) - 20} 张差异")

    initial_hits = sum(item["initial_hits"] for item in results)
    initial_total = sum(item["initial_total"] for item in results)
    reshuffle_hits = sum(item["reshuffle_hits"] for item in results)
    reshuffle_total = sum(
        item["reshuffle_total"] for item in results if item["skipped"] is None
    )
    passed = sum(1 for item in results if item["ok"])
    skipped_cards = sum(item["reshuffle_total"] for item in results if item["skipped"])
    warning = ""
    skipped_exams = [item for item in results if item["skipped"]]
    if skipped_exams:
        warning = f"；{len(skipped_exams)} 场重洗段按规则跳过（{skipped_cards} 张）"
    print(
        f"\n[check] 汇总: {passed}/{len(results)} 场通过；初始牌堆段 {initial_hits}/{initial_total} 张；"
        f"重洗段 {reshuffle_hits}/{reshuffle_total} 张{warning}"
    )
    if passed == len(results):
        print("[check] ✅ 全部通过")
    else:
        print("[check] ❌ 存在不一致（见上方差异明细）")
    return passed == len(results)


# ---------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从实机采集生成 out/exam_setup.json（考试牌序数据源）")
    parser.add_argument("--file", default=str(DEFAULT_TRAFFIC), help="traffic.jsonl 路径")
    parser.add_argument("--snap", default=str(DEFAULT_SNAPS), help="deck_snapshots.json 路径")
    parser.add_argument("--truth", default=str(DEFAULT_TRUTH), help="可选 exam_truth.json 路径")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出 exam_setup.json 路径")
    parser.add_argument("--no-check", action="store_true", help="跳过落盘后的 --check 校验")
    args = parser.parse_args(argv)

    traffic = Path(args.file)
    snap = Path(args.snap)
    out = Path(args.out)
    if not traffic.is_file():
        print(f"❌ 采集文件不存在: {traffic}")
        return 1
    if not snap.is_file():
        print(f"❌ 牌堆快照不存在: {snap}（先跑 scripts/reconstruct_deck.py）")
        return 1

    setup, context = build_setup(traffic, snap, Path(args.truth))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(setup, ensure_ascii=False, indent=2), encoding="utf-8")
    size = out.stat().st_size
    print(
        f"✅ 已写入 {out}（{size} 字节，{len(setup['exams'])} 场考试；"
        f"seed/config_turns: "
        + "，".join(
            f"0x{exam['seed']:08X}/{exam['config_turns']}" for exam in setup["exams"]
        )
        + "）"
    )
    if not all(exam["config_turns_ok"] for exam in setup["exams"]):
        bad = [exam["index"] for exam in setup["exams"] if not exam["config_turns_ok"]]
        print(f"⚠️ 配置回合数检测失败（按实战回合数写入）：考试 {bad}")
    if args.no_check:
        print("（--no-check：跳过校验）")
        return 0
    return 0 if run_check(setup, context) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
