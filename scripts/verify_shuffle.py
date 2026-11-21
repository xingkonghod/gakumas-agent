"""洗牌重放验证：examSeedValue + 考试牌堆 → 精确牌序（2026-11-21 修正版）。

模型（实现见 ``src/gkagent/sim/exam_shuffle.py``）：

  · 考试开局先消耗随机数：回合属性 ``turns-3`` 次 + NPC 分数 ``npc_count*turns`` 次
    → 洗牌前 K = (turns-3) + npc_count*turns（produce-001 初 REGULAR 是 5 个 NPC，K = 6*turns-3）
  · 洗牌 = xorshift32(examSeedValue) advance K 次 → Fisher-Yates 倒序洗「Number 升序」牌堆
  · 第 1 回合先 SetInitialCard：把 isInitial 卡从牌堆抽入手，再补抽到 turnStartDistribute 张
  · 牌堆抽完前，洗后牌序 = 逐回合手牌依次拼接

旧版（2026-11-20）漏了 isInitial 卡，期末才会「复现不出」：期末牌堆里的
``p_card-02-men-2_054`` 是 isInitial，首回合它被抽人手牌，之后每一回合都错位。
修正后：期中 K=51 → 18/18，期末 K=63 → 26/26（两场都回合集合全中）。

用法：python scripts/verify_shuffle.py [--file PATH] [--k N] [--max-k N]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zlib
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parent))
from dig_deck import body, parse, walk

from gkagent.sim.exam_shuffle import (
    DEFAULT_NPC_COUNT,
    generate_turn_types,
    infer_turn_type_pool,
    k_before_shuffle,
    replay_initial_deck,
)

DEFAULT = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
MASTER_DIR = Path(__file__).resolve().parents[1] / "data/hiro/vendor/gakumas-player/data/master"


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
        turns.append({"turn": (m.get(1) or [0])[0], "parameterType": (m.get(7) or [0])[0], "hand": hand})
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


def load_master_info(db: Path | None) -> tuple[set[tuple[str, int]], int]:
    """返回（isInitial 的卡集合, turnStartDistribute）。主数据缺失时退回空集/3。"""
    if db is None or not db.is_file():
        print(f"⚠️ 主数据不可用（{db}），isInitial 按空集处理")
        return set(), 3
    initial: set[tuple[str, int]] = set()
    turn_start_distribute = 3
    con = sqlite3.connect(db)
    try:
        for row_id, variant, payload in con.execute(
            "select row_id, variant, payload from records where table_name='ProduceCard'"
        ):
            card = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
            if card.get("isInitial"):
                initial.add((row_id, int(variant)))
        row = con.execute(
            "select payload from records where table_name='ExamSetting' order by row_id limit 1"
        ).fetchone()
        if row is not None:
            setting = json.loads(zlib.decompress(row[0]).decode("utf-8", "replace"))
            turn_start_distribute = int(setting.get("turnStartDistribute", 3))
    finally:
        con.close()
    return initial, turn_start_distribute


def load_exams(path: Path, snap_path: Path) -> list[dict]:
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    starts = [r for r in records if r.get("path", "").endswith("StepAuditionStart")]
    ends = [r for r in records if r.get("path", "").endswith("StepAuditionEndExamBattle")]
    snaps = json.loads(snap_path.read_text(encoding="utf-8"))
    exams = []
    for i, end in enumerate(ends):
        req = body(end, "req_plain_hex")
        seed = get_seed(body(starts[i], "resp_plain_hex"))
        turns = truth_turns(req) if req is not None else []
        top = fmap(parse(req)) if req is not None else {}
        deck = [(c["id"], c["upgrade"]) for c in sorted(snaps[i]["deck"], key=lambda c: c["number"])]
        exams.append(
            {
                "i": i,
                "seed": seed,
                "ts": end.get("ts"),
                "deck": deck,
                "turns": turns,
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


def report_exam(exam: dict, initial: set[tuple[str, int]], turn_start_distribute: int, k: int | None) -> bool:
    seed = exam["seed"]
    deck = exam["deck"]
    turns = exam["turns"]
    npc = exam["npc_count"]
    n_turns = len(turns)
    if seed is None or not deck or not turns:
        print(f"\n=== 考试{exam['i']} {exam['ts']} 数据不全（seed={seed} 牌堆={len(deck)} 回合={n_turns}）")
        return False

    # 1) 回合属性验证：前 turns-3 个在 RNG offset 0 复现
    types = [t["parameterType"] for t in turns]
    pool = infer_turn_type_pool(types)
    types_ok = pool is not None and generate_turn_types(seed, pool) == types[:-3]
    print(f"\n=== 考试{exam['i']} {exam['ts']} seed=0x{seed:08X} 牌堆 {len(deck)} 张 / {n_turns} 回合 ===")
    print(f"  回合属性: {'✅ offset 0 复现' if types_ok else '⚠️ 未复现'}"
          f"（池 {pool}，末 3 回合固定 {types[-3:]}）")

    # 2) 洗牌前消耗：回合属性 + NPC
    k_formula = k_before_shuffle(n_turns, npc)
    k_use = k_formula if k is None else k
    print(f"  K = (turns-3) + npc*turns = {max(0, n_turns - 3)} + {npc}*{n_turns} = {k_formula}")
    if k is not None and k != k_formula:
        print(f"  使用 --k {k}")

    deck_initial = {c for c in deck if c in initial}
    predicted = replay_initial_deck(
        seed,
        deck,
        k_use,
        initial_keys=frozenset(deck_initial),
        turn_start_distribute=turn_start_distribute,
    )
    stats = match_stats(predicted, turns)
    ok = stats["id"] == stats["total"]
    mark = "✅" if ok else "❌"
    print(f"  isInitial 卡: {sorted(deck_initial) or '无'}")
    print(f"  洗牌重放: {mark} 整段 {stats['id']}/{stats['total']} 张 id 精确、"
          f"{stats['variant']}/{stats['total']} 张强化不冲突；回合集合 {stats['sets'][0]}/{stats['sets'][1]}")
    if ok:
        return True

    # 3) 公式不通时按 K 搜索（保留旧的调试能力）
    if k is None:
        hits = []
        for candidate in range(2001):
            pred = replay_initial_deck(
                seed,
                deck,
                candidate,
                initial_keys=frozenset(deck_initial),
                turn_start_distribute=turn_start_distribute,
            )
            probe = match_stats(pred, turns)
            if probe["id"] == probe["total"]:
                hits.append(candidate)
        if hits:
            print(f"  ⚠️ 公式 K={k_use} 不对，但 K={hits[:5]} 可整段复现（记录进 docs/TROUBLESHOOTING.md）")
        else:
            print("  ⚠️ K=0..2000 也复现不出（数据/模型需复查）")
    return False


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

    initial, turn_start_distribute = load_master_info(master_db())
    exams = load_exams(path, snap)
    print(f"共 {len(exams)} 场考试；turnStartDistribute={turn_start_distribute}；isInitial 卡 {len(initial)} 种变体")
    results = [report_exam(exam, initial, turn_start_distribute, args.k) for exam in exams]
    print(f"\n汇总: {sum(results)}/{len(results)} 场考试整段复现")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
