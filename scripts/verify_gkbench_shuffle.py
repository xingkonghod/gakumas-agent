"""F0：gkbench 官方开发种子 check.hand 交叉验证洗牌模型 + 官方考试起点校准。

数据（gitignore，先跑 ``scripts/bench_download.py --sets hif`` 补下）::

    data/bench_local/gkbench_dl/hif/seeds.json    # 329 题 / 384 组 dev 种子 + check{turn,score,stamina,hand,rules,commit}
    data/bench_local/gkbench_dl/hif/saves.jsonl   # 505 题模板（loadout.deck_cards / 牌组 / support / 初始附魔 ...）

模型（``src/gkagent/sim/exam_shuffle.py``，与四场实机整段验证过的同一套）::

    K = (turns-3) + npc*turns          # turns = 模板 meta.turns（配置回合数）
    洗牌 = Fisher-Yates 倒序，再第 1 回合 SetInitialCard + 补抽到 turnStartDistribute
    initial = 主数据 isInitial（**按 base id，含 +1/+2 强化变体**）+ deck 里
              ``g_effect-initial_add`` 自定义卡（考试开始强制入手）

本脚本 2026-11-22 F0 收尾新增的两条口径修正：

1. **initial 按卡 id（不是变体）**：gkbench deck 写法 ``p_card-xx-...+1``，主数据 isInitial
   在 +0/+1 各变体上都有记录；旧口径用 ``(id, upgradeCount)`` 精确匹配，牌组用 +1 变体时
   漏判（286/384 的主因之一）。现按 base id 命中所有变体，再把 deck 里
   ``g_effect-initial_add`` 的卡并进 initial。
2. **npc 人数按 idol 卡**（不是 stage 常数）：官方 ``ProduceExamBattleNpcGroup`` 对每个
   idol/考试配置的 NPC 数不同——H.I.F 選抜 6 人制 = 5，本戦多数 3 人制 = 2，但
   **十王星南（jsna）等部分 idol 的本戦是 4 人制 = 3**。旧口径按 stage 写死 main=2，
   26 组因此对不上。现在按 ``IdolCard.produceStepAuditionDifficultyId`` →
   ``ProduceStepAuditionDifficulty`` → ``produceExamBattleNpcGroupId`` → NPC 行数取人数；
   steer 不到时退回 stage 常数（選抜 5 / 本戦 2）。

用法::

    .venv\\Scripts\\python.exe scripts\\verify_gkbench_shuffle.py
    .venv\\Scripts\\python.exe scripts\\verify_gkbench_shuffle.py --json data\\bench_local\\f0_gkbench.json
    .venv\\Scripts\\python.exe scripts\\verify_gkbench_shuffle.py --verbose   # 逐条不一致样本

选项 ``--stage-npc`` / ``--variant-initial`` 用于复现 F0 预检旧口径（286/384）和消融对照。
只读本地数据 + 主数据，不联网、不读令牌。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.sim.exam_shuffle import (  # noqa: E402
    DEFAULT_HAND_LIMIT,
    DEFAULT_TURN_START_DISTRIBUTE,
    k_before_shuffle,
    replay_initial_deck,
)

DL_DIR = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
MASTER_DIR = ROOT / "data/hiro/vendor/gakumas-player/data/master"

# stage → npc 常数（官方 check 交叉验证后，仅作 idol 信息缺失时的兜底）
STAGE_NPC = {"hif.sel1": 5, "hif.sel2": 5, "hif.sel3": 5, "hif.main1": 2, "hif.main2": 2}

STEP_TYPE_NAMES = {16: "AuditionMid1", 17: "AuditionMid2", 18: "AuditionFinal"}
STEP_ROWS = {
    "AuditionMid1": "ProduceStepType_AuditionMid1",
    "AuditionMid2": "ProduceStepType_AuditionMid2",
    "AuditionFinal": "ProduceStepType_AuditionFinal",
}
ROUND_STEP = {"mid1": "AuditionMid1", "mid2": "AuditionMid2", "final": "AuditionFinal"}


# --------------------------------------------------------------------------- 主数据
def master_db() -> Path | None:
    current = MASTER_DIR / "current.json"
    if current.is_file():
        try:
            return MASTER_DIR / json.loads(current.read_text(encoding="utf-8"))["database"]
        except (KeyError, json.JSONDecodeError, OSError):
            pass
    candidates = sorted(MASTER_DIR.glob("*/catalog.sqlite"))
    return candidates[-1] if candidates else None


def load_table(db: Path, table: str) -> list[dict]:
    """``records`` 表里一张主数据表（gzip JSON payload）→ 行列表。"""
    out: list[dict] = []
    con = sqlite3.connect(db)
    try:
        for _row_id, _variant, payload in con.execute(
            "select row_id, variant, payload from records where table_name=?", (table,)
        ):
            out.append(json.loads(zlib.decompress(payload).decode("utf-8", "replace")))
    finally:
        con.close()
    return out


class Master:
    """F0 需要的主数据索引：isInitial / idol→考试难度→NPC 人数 / ExamInitialDeck。"""

    def __init__(self, db: Path | None) -> None:
        self.available = db is not None and db.is_file()
        self.initial_exact: set[tuple[str, int]] = set()   # (id, upgrade)
        self.initial_bases: set[str] = set()               # id（所有变体共用）
        self.idols: dict[str, dict] = {}
        self.audition: dict[tuple[str, str, str], dict] = {}
        self.npc_rows: Counter = Counter()
        self.exam_decks: dict[str, list[str]] = {}
        self.produce_initial: dict[tuple[str, str], str] = {}
        if not self.available:
            return
        for card in load_table(db, "ProduceCard"):
            cid = str(card.get("id") or "")
            upgrade = int(card.get("upgradeCount") or 0)
            if card.get("isInitial"):
                self.initial_exact.add((cid, upgrade))
                self.initial_bases.add(cid)
        self.idols = {str(r["id"]): r for r in load_table(db, "IdolCard") if r.get("id")}
        self.audition = {
            (str(r["id"]), str(r.get("produceId") or ""), str(r.get("stepType") or "")): r
            for r in load_table(db, "ProduceStepAuditionDifficulty")
        }
        for row in load_table(db, "ProduceExamBattleNpcGroup"):
            self.npc_rows[str(row["id"])] += 1
        self.exam_decks = {
            str(r["id"]): [str(c) for c in (r.get("produceCardIds") or [])]
            for r in load_table(db, "ExamInitialDeck")
        }
        self.produce_initial = {
            (str(r.get("produceId") or ""), str(r.get("examEffectType") or "")): str(
                r.get("examInitialDeckId") or ""
            )
            for r in load_table(db, "ProduceInitialDeck")
        }

    # -------------------------------------------------------------- NPC 人数
    def npc_from_idol(self, loadout: dict, meta: dict) -> tuple[int | None, str]:
        """idol 卡 → 考试难度配置 → NPC 组 → NPC 行数。返回 (npc, npcGroupId)。"""
        idol = self.idols.get(str(loadout.get("idol_card_id") or ""))
        if not idol:
            return None, ""
        produce_id = str(loadout.get("produce_id") or "")
        step_name = self.step_name(loadout)
        if not produce_id or not step_name:
            return None, ""
        row = self.audition.get(
            (str(idol.get("produceStepAuditionDifficultyId") or ""), produce_id,
             STEP_ROWS.get(step_name, ""))
        )
        if not row:
            return None, ""
        group_id = str(row.get("produceExamBattleNpcGroupId") or "")
        count = self.npc_rows.get(group_id, 0)
        return (count or None), group_id

    @staticmethod
    def step_name(loadout: dict) -> str:
        """loadout 的考试步：``step_id``（AuditionMid1/…）优先，其次 ``step_type`` 16/17/18，
        最后按 ``round``（mid1/mid2/final）兜底——部分采集上传的 loadout 没有 step 字段。"""
        step_id = str(loadout.get("step_id") or "")
        if step_id in STEP_ROWS:
            return step_id
        try:
            name = STEP_TYPE_NAMES.get(int(loadout.get("step_type") or 0), "")
        except (TypeError, ValueError):
            name = ""
        if name:
            return name
        return ROUND_STEP.get(str(loadout.get("round") or ""), "")

    def initial_deck_cards(self, loadout: dict) -> tuple[set[str], str]:
        """该题「考试初始牌组」的卡（官方 ExamInitialDeck）：produceId+考试效果 → 初始牌组。"""
        idol = self.idols.get(str(loadout.get("idol_card_id") or ""))
        if not idol:
            return set(), ""
        deck_id = self.produce_initial.get(
            (str(loadout.get("produce_id") or ""), str(idol.get("examEffectType") or ""))
        )
        if not deck_id:
            deck_id = str(idol.get("examInitialDeckId") or "")
        return set(self.exam_decks.get(deck_id) or ()), deck_id


# --------------------------------------------------------------------------- 数据解析
def parse_deck(entries: list[str]) -> tuple[list[tuple[str, int]], set[int]]:
    """gkbench ``deck_cards`` 写法 → [(cardId, upgradeCount)] + initial_add 卡下标。

    一条 = ``卡 id[+强化次数][/定制编号*次数...]``；``g_effect-initial_add`` 出现在任一
    定制段里 = 这张卡考试开始强制入手。
    """
    cards: list[tuple[str, int]] = []
    initial_add: set[int] = set()
    for entry in entries:
        segments = str(entry).split("/")
        cid, _, upgrade = segments[0].partition("+")
        idx = len(cards)
        cards.append((cid, int(upgrade) if upgrade else 0))
        if any("g_effect-initial_add" in seg for seg in segments[1:]):
            initial_add.add(idx)
    return cards, initial_add


def load_bench(dl_dir: Path) -> tuple[dict, dict]:
    seeds_path = dl_dir / "seeds.json"
    saves_path = dl_dir / "saves.jsonl"
    missing = [str(p) for p in (seeds_path, saves_path) if not p.is_file()]
    if missing:
        raise SystemExit(
            "缺 gkbench 数据：" + "、".join(missing) + "\n"
            "先跑 .venv\\Scripts\\python.exe scripts\\bench_download.py --sets hif\n"
            "（data/bench_local/ 已 gitignore；seeds.json 需要令牌，见 docs/GKBENCH.md §3）"
        )
    seeds = json.loads(seeds_path.read_text(encoding="utf-8"))
    saves: dict[str, dict] = {}
    with saves_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            saves[str(row.get("id"))] = row
    return seeds, saves


# --------------------------------------------------------------------------- 模型
def predict_hand(
    seed: int,
    cards: list[tuple[str, int]],
    initial_add: set[int],
    npc: int,
    turns: int,
    master: Master,
    *,
    initial_mode: str = "base",
) -> list[str]:
    """按洗牌模型预测第 1 回合手牌（base 卡 id 列表）。"""
    if initial_mode == "exact":
        initial_keys = frozenset(c for c in cards if c in master.initial_exact)
    else:  # base：主数据 isInitial 按 base id（含强化变体）+ deck 里 initial_add 卡
        initial_keys = frozenset(
            card for idx, card in enumerate(cards)
            if card[0] in master.initial_bases or idx in initial_add
        )
    turns_hands = replay_initial_deck(
        seed,
        cards,
        k_before_shuffle(turns, npc),
        initial_keys=initial_keys,
        turn_start_distribute=DEFAULT_TURN_START_DISTRIBUTE,
        hand_limit=DEFAULT_HAND_LIMIT,
    )
    return [card[0] for card in (turns_hands[0] if turns_hands else [])]


def iter_groups(seeds: dict, saves: dict):
    """展开 384 组：(题 id, 组序号, seed, check, loadout, meta, 题模板)。"""
    for pid, rows in (seeds.get("problems") or {}).items():
        save = saves.get(pid)
        if save is None:
            continue
        loadout = save.get("loadout") or {}
        meta = save.get("meta") or {}
        for group in rows:
            yield pid, group, loadout, meta, save


# --------------------------------------------------------------------------- 单组核对
def evaluate(
    master: Master,
    pid: str,
    group: dict,
    loadout: dict,
    meta: dict,
    *,
    initial_mode: str = "base",
    npc_mode: str = "idol",
) -> dict:
    stage = str(meta.get("stage") or "")
    turns = int(meta.get("turns") or 0)
    i_npc = int(group.get("index") or 0)
    seed = int(group["seed"])
    actual = [str(c) for c in (group.get("check") or {}).get("hand") or []]
    deck_entries = [str(e) for e in (loadout.get("deck_cards") or [])]
    cards, initial_add = parse_deck(deck_entries)
    idol_npc, npc_group = master.npc_from_idol(loadout, meta)
    if npc_mode == "idol" and idol_npc is not None:
        npc, npc_source = idol_npc, npc_group
    else:
        npc, npc_source = STAGE_NPC.get(stage, 2), "stage"
    predicted = predict_hand(seed, cards, initial_add, npc, turns, master, initial_mode=initial_mode)

    deck_bases = {card[0] for card in cards}
    absent = [card for card in actual if card not in deck_bases]
    return {
        "pid": pid,
        "index": i_npc,
        "stage": stage,
        "turns": turns,
        "seed": seed,
        "npc": npc,
        "npc_source": npc_source,
        "npc_idol": idol_npc,
        "npc_idol_group": npc_group,
        "deck_size": len(cards),
        "initial_add": len(initial_add),
        "predicted": predicted,
        "actual": actual,
        "match": predicted == actual,
        "position_hits": sum(1 for a, b in zip(predicted, actual) if a == b),
        "absent": absent,
    }


def classify_miss(row: dict, master: Master, loadout: dict) -> dict:
    """给不一致样本分配根因（initial / turnStartDistribute / 牌序 / 其他）。"""
    predicted, actual = row["predicted"], row["actual"]
    deck_bases = set()
    cards, _add = parse_deck([str(e) for e in (loadout.get("deck_cards") or [])])
    deck_bases = {card[0] for card in cards}
    absent = row["absent"]
    init_deck_cards, init_deck_id = master.initial_deck_cards(loadout)

    if len(actual) != len(predicted):
        if predicted == actual[: len(predicted)]:
            return {
                "bucket": "其他",
                "detail": f"考试开始额外加牌：手牌 {len(actual)} > 预测 {len(predicted)}",
            }
        return {"bucket": "其他", "detail": f"手牌数不同（{len(actual)} vs {len(predicted)}）"}
    if absent:
        from_initial_deck = [c for c in absent if c in init_deck_cards]
        if from_initial_deck:
            return {
                "bucket": "其他",
                "detail": f"考试初始牌组（{init_deck_id}）未建模，实机手牌多出 {from_initial_deck}",
            }
        return {"bucket": "其他", "detail": f"考试开始时加卡（来源未建模）：{absent}"}
    if sorted(predicted) == sorted(actual):
        return {"bucket": "牌序", "detail": "同一组牌、顺序不同（initial 扫描/洗牌顺序）"}
    first_diff = next(
        (i for i, (a, b) in enumerate(zip(predicted, actual)) if a != b), 0
    )
    return {
        "bucket": "牌序",
        "detail": f"第 {first_diff + 1} 张起不同（洗牌输入/RNG 消耗与官方不一致）",
    }


# --------------------------------------------------------------------------- 统计
def summarize(rows: list[dict], master: Master, saves: dict) -> dict:
    groups = len(rows)
    hits = sum(1 for r in rows if r["match"])
    cards = sum(len(r["actual"]) for r in rows)
    card_hits = sum(r["position_hits"] for r in rows)

    by_stage: dict[str, dict] = {}
    for r in rows:
        st = by_stage.setdefault(
            r["stage"], {"groups": 0, "match": 0, "card_hits": 0, "cards": 0}
        )
        st["groups"] += 1
        st["match"] += int(r["match"])
        st["card_hits"] += r["position_hits"]
        st["cards"] += len(r["actual"])

    by_pid: dict[str, dict] = {}
    for r in rows:
        p = by_pid.setdefault(
            r["pid"],
            {"stage": r["stage"], "groups": 0, "match": 0, "card_hits": 0, "cards": 0,
             "hand_hits": Counter()},
        )
        p["groups"] += 1
        p["match"] += int(r["match"])
        p["card_hits"] += r["position_hits"]
        p["cards"] += len(r["actual"])
        p["hand_hits"][f"{r['position_hits']}/{len(r['actual'])}"] += 1

    per_problem = []
    for pid in sorted(by_pid):
        p = by_pid[pid]
        per_problem.append({
            "pid": pid,
            "stage": p["stage"],
            "groups": p["groups"],
            "exact": f"{p['match']}/{p['groups']}",
            "per_card": f"{p['card_hits']}/{p['cards']}",
            "hand_hits": dict(p["hand_hits"]),
        })

    misses = []
    for r in rows:
        if r["match"]:
            continue
        save = saves.get(r["pid"]) or {}
        classified = classify_miss(r, master, save.get("loadout") or {})
        misses.append({
            **{k: r[k] for k in ("pid", "index", "stage", "turns", "npc", "npc_source",
                                 "predicted", "actual", "absent")},
            **classified,
        })

    buckets = Counter(m["bucket"] for m in misses)
    all_buckets = {"initial": 0, "turnStartDistribute": 0, "牌序": 0, "其他": 0}
    all_buckets.update(buckets)
    details = Counter(m["detail"].split("，实机手牌多出")[0].split("：")[0] for m in misses)
    return {
        "groups": groups,
        "exact": hits,
        "exact_rate": hits / groups if groups else 0.0,
        "card_hits": card_hits,
        "cards": cards,
        "card_rate": card_hits / cards if cards else 0.0,
        "by_stage": by_stage,
        "per_problem": per_problem,
        "misses": misses,
        "bucket_counts": all_buckets,
        "detail_counts": dict(details),
    }


# --------------------------------------------------------------------------- 起点校准
def calibrate_start(seeds: dict, saves: dict) -> dict:
    """check.turn/score/stamina/rules/commit → 官方考试起点核对 + 与 loadout 的比较。"""
    turns = Counter()
    scores = Counter()
    rules = Counter()
    commits = Counter()
    labels = Counter()
    label_commit = Counter()
    stamina_equal = 0
    stamina_total = 0
    exceptions: list[dict] = []
    idol_delta: dict[str, Counter] = defaultdict(Counter)
    for pid, rows in (seeds.get("problems") or {}).items():
        save = saves.get(pid) or {}
        loadout = save.get("loadout") or {}
        start = int(loadout.get("starting_stamina") or 0)
        idol = str(loadout.get("idol_card_id") or "")
        for group in rows:
            check = group.get("check") or {}
            label = str(group.get("label") or "")
            labels[label] += 1
            label_commit[(label, str(check.get("commit") or ""))] += 1
            turns[int(check.get("turn") or 0)] += 1
            scores[int(check.get("score") or 0)] += 1
            rules[int(check.get("rules") or 0)] += 1
            commits[str(check.get("commit") or "")] += 1
            stamina = int(check.get("stamina") or 0)
            stamina_total += 1
            if stamina == start:
                stamina_equal += 1
            else:
                delta = stamina - start
                idol_delta[idol][delta] += 1
                exceptions.append({
                    "pid": pid,
                    "index": int(group.get("index") or 0),
                    "idol": idol,
                    "loadout_starting_stamina": start,
                    "check_stamina": stamina,
                    "delta": delta,
                })
    idol_table = [
        {"idol": idol, "delta": delta, "groups": count}
        for idol, deltas in idol_delta.items()
        for delta, count in deltas.items()
    ]
    return {
        "groups": stamina_total,
        "turn": dict(turns),
        "score": dict(scores),
        "rules": dict(rules),
        "commit": dict(commits),
        "labels": dict(labels),
        "label_commit": {f"{lab}|{commit or '(空)'}": n for (lab, commit), n in label_commit.items()},
        "stamina_equal": stamina_equal,
        "stamina_equal_rate": stamina_equal / stamina_total if stamina_total else 0.0,
        "exceptions": exceptions,
        "exception_by_idol": idol_table,
    }


# --------------------------------------------------------------------------- 入口
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="gkbench 官方种子核洗牌模型 + 起点校准（F0）")
    parser.add_argument("--dl-dir", type=Path, default=DL_DIR,
                        help="gkbench 题集下载目录（默认 data/bench_local/gkbench_dl/hif）")
    parser.add_argument("--json", type=Path, default=None, help="把完整结果写到 JSON")
    parser.add_argument("--verbose", action="store_true", help="打印逐条不一致样本")
    parser.add_argument("--stage-npc", action="store_true", help="复现旧口径：NPC 数按 stage 常数")
    parser.add_argument("--variant-initial", action="store_true", help="复现旧口径：initial 按 (id, 强化) 精确匹配")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    db = master_db()
    master = Master(db)
    if not master.available:
        raise SystemExit(f"主数据不可用：{db}（见 docs/MASTER_DATA.md）")
    seeds, saves = load_bench(args.dl_dir)
    groups = list(iter_groups(seeds, saves))
    if not groups:
        raise SystemExit("seeds.json / saves.jsonl 里没有可核对的题（数据不完整）")
    print(
        f"主数据: {db}\n"
        f"题: {len(seeds.get('problems') or {})} 题 / {len(groups)} 组开发种子；"
        f"isInitial 卡 {len(master.initial_bases)} 种（{len(master.initial_exact)} 个变体行）；"
        f"idol {len(master.idols)} 张"
    )

    # 口径消融：旧预检 286 → 只修 initial → 再加 idol npc
    configs = [
        ("旧口径（variant initial + stage npc）", "exact", "stage"),
        ("只修 initial（base initial + stage npc）", "base", "stage"),
        ("完整（base initial + idol npc）", "base", "idol"),
    ]
    if args.variant_initial or args.stage_npc:
        configs = [(
            "指定口径（--variant-initial / --stage-npc）",
            "exact" if args.variant_initial else "base",
            "stage" if args.stage_npc else "idol",
        )]
    ablation = {}
    final_summary: dict = {}
    for name, initial_mode, npc_mode in configs:
        rows = [
            evaluate(master, pid, group, loadout, meta,
                     initial_mode=initial_mode, npc_mode=npc_mode)
            for pid, group, loadout, meta, _save in groups
        ]
        summary = summarize(rows, master, saves)
        ablation[name] = {
            "exact": summary["exact"],
            "exact_rate": summary["exact_rate"],
            "card_hits": summary["card_hits"],
            "cards": summary["cards"],
        }
        print(
            f"\n[{name}] 精确命中 {summary['exact']}/{summary['groups']}"
            f" = {summary['exact_rate']:.1%}；逐张命中 {summary['card_hits']}/{summary['cards']}"
            f" = {summary['card_rate']:.1%}"
        )
        final_summary = summary

    # 逐 stage
    print("\n按 stage：")
    for stage in ("hif.sel1", "hif.sel2", "hif.sel3", "hif.main1", "hif.main2"):
        st = final_summary["by_stage"].get(stage)
        if not st:
            continue
        print(
            f"  {stage}: 精确 {st['match']}/{st['groups']} = {st['match'] / st['groups']:.1%}；"
            f"逐张 {st['card_hits']}/{st['cards']} = {st['card_hits'] / st['cards']:.1%}"
        )

    # 逐题逐张
    perfect = sum(1 for p in final_summary["per_problem"] if p["exact"] == f"{p['groups']}/{p['groups']}")
    print(
        f"\n逐题：{perfect}/{len(final_summary['per_problem'])} 题全部种子命中；"
        f"逐张（按位置）：{final_summary['card_hits']}/{final_summary['cards']} = "
        f"{final_summary['card_rate']:.1%}"
    )

    # 不一致根因
    if final_summary["misses"]:
        print(
            f"\n不一致样本 {len(final_summary['misses'])} 组（initial / turnStartDistribute "
            f"两类修正后已归零），根因分布："
        )
        for bucket in ("initial", "turnStartDistribute", "牌序", "其他"):
            print(f"  {bucket}: {final_summary['bucket_counts'][bucket]}")
        for detail, count in sorted(final_summary["detail_counts"].items(), key=lambda kv: -kv[1]):
            print(f"    · {detail}: {count}")
        if args.verbose:
            print("\n逐条不一致：")
            for miss in final_summary["misses"]:
                print(
                    f"  {miss['pid']}[{miss['index']}] {miss['stage']} npc={miss['npc']}"
                    f"（{miss['npc_source']}）"
                )
                print(f"    预测: {miss['predicted']}")
                print(f"    实机: {miss['actual']}")
                print(f"    根因: {miss['bucket']} — {miss['detail']}")
    else:
        print("\n全部命中 🎉")

    # 起点校准
    calibration = calibrate_start(seeds, saves)
    print("\n== 官方考试起点校准（check.turn/score/stamina/rules）==")
    print(f"  turn: {calibration['turn']}   score: {calibration['score']}")
    print(
        f"  rules: {calibration['rules']}   commit: {calibration['commit']}\n"
        f"  种子来源: {calibration['labels']}"
    )
    print(
        f"  stamina: {calibration['stamina_equal']}/{calibration['groups']}"
        f" = {calibration['stamina_equal_rate']:.1%} 与 loadout.starting_stamina 相同；"
        f"其余 {len(calibration['exceptions'])} 组差异（考试开始效果）："
    )
    for row in calibration["exception_by_idol"]:
        print(f"    {row['idol']}: {row['delta']:+d} × {row['groups']} 组")
    print(
        "  口径：turn 从 1 开始、score 从 0 开始；本战 NPC 人数按 idol（非 stage 常数）；"
        "起点体力以 check.stamina 为官方值（= starting_stamina + 偶像卡考试开始附魔），"
        "基准复算时应用 check.stamina 覆盖 loadout 值。"
    )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "schema": "gkbench.f0_check.v1",
                    "data": str(args.dl_dir),
                    "ablation": ablation,
                    "summary": {
                        "groups": final_summary["groups"],
                        "exact": final_summary["exact"],
                        "exact_rate": final_summary["exact_rate"],
                        "card_hits": final_summary["card_hits"],
                        "cards": final_summary["cards"],
                        "card_rate": final_summary["card_rate"],
                        "by_stage": final_summary["by_stage"],
                        "bucket_counts": final_summary["bucket_counts"],
                        "detail_counts": final_summary["detail_counts"],
                    },
                    "per_problem": final_summary["per_problem"],
                    "misses": final_summary["misses"],
                    "calibration": calibration,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"\n已写入 {args.json}")

    # 退出码只反映数据/模型是否可用；不一致是 F0 分析结果，不当作命令失败
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
