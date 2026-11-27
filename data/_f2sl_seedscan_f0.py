"""F2 seed-lock 第一步：seed_scan.c（UIHorizon 参考实现，gcc 编译）对 F0 已知种子的找回验证。

模型链（与 scripts/verify_gkbench_shuffle.py 同口径）：
  pre  = loadout.deck_cards 列表序（base id → 小整数）
  k    = (turns-3) + npc*turns（turns=meta.turns 配置回合；npc 按 idol 难度→NPC 组行数）
  skip = 第 1 回合 SetInitialCard 放入手牌的 initial 卡（主数据 isInitial base id + initial_add）
  obs  = 第 1 回合补抽的牌（check.hand 去掉 initial 部分，按抽牌序）
  pool/turns 过滤 = ProduceExamBattleConfig 权重 → f32 池（UIHorizon turn_pool 同式）→ 种子生成前 turns-3 属性

窄窗扫描：每个种子 ±window，验证已知 seed 是否被找回 + 窗内假阳性数。
全量扫描：[0, 2^31) 多进程，看候选数（锁定可行性）。
探针不提交。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from gkagent.sim.exam_shuffle import (
    DEFAULT_HAND_LIMIT,
    DEFAULT_TURN_START_DISTRIBUTE,
    NativeRandom,
    generate_turn_types,
    infer_turn_type_pool,
    k_before_shuffle,
    opening_deck_and_rng,
)
from verify_gkbench_shuffle import (
    STAGE_NPC,
    Master,
    iter_groups,
    load_bench,
    master_db,
    parse_deck,
)

EXE = ROOT / "data" / "_f2sl_tools" / "kernel" / "seed_scan.exe"
DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"


def f32(x: float) -> float:
    return float(np.float32(x))


def turn_pool_from_weights(weights: dict[int, int], limit: int) -> tuple[list[int], int]:
    """UIHorizon vendor/bench/opening.py turn_pool 同式（f32 舍入）。"""
    import math
    (t0, p0), (t1, p1), (t2, p2) = sorted(weights.items(), key=lambda kv: -kv[1])
    mutable = limit - 3
    if mutable <= 0:
        return [], 0
    c0 = math.ceil(f32(f32(f32(mutable) * f32(p0)) / f32(p0 + p1 + p2)))
    remaining = mutable - c0
    c1 = round(f32(f32(f32(remaining) * f32(p1)) / f32(p1 + p2)))
    return [t0] * c0 + [t1] * c1 + [t2] * (remaining - c1), mutable


def opening_split(seed, cards, initial_keys, k):
    """第 1 回合 (initial_batch, drawn_batch)：SetInitialCard 底→顶扫 + 补抽。"""
    _rng, remaining = opening_deck_and_rng(seed, list(cards), k)
    initial_batch, overflow = [], []
    for card in reversed(list(remaining)):
        if card not in initial_keys:
            continue
        remaining.remove(card)
        if len(initial_batch) < DEFAULT_HAND_LIMIT:
            initial_batch.append(card)
        else:
            overflow.append(card)
    remaining.extend(overflow)
    need = max(0, DEFAULT_TURN_START_DISTRIBUTE - len(initial_batch))
    drawn = [remaining.pop(0) for _ in range(need) if remaining]
    return initial_batch, drawn


def build_case(master: Master, pid, group, loadout, meta, saves_row):
    cards, initial_add = parse_deck([str(e) for e in loadout.get("deck_cards") or []])
    turns = int(meta.get("turns") or 0)
    seed = int(group["seed"])
    actual = [str(c) for c in (group.get("check") or {}).get("hand") or []]
    idol_npc, _g = master.npc_from_idol(loadout, meta)
    npc = idol_npc if idol_npc is not None else STAGE_NPC.get(str(meta.get("stage") or ""), 2)
    k = k_before_shuffle(turns, npc)
    initial_keys = frozenset(
        card for idx, card in enumerate(cards)
        if card[0] in master.initial_bases or idx in initial_add
    )
    initial_batch, drawn = opening_split(seed, cards, initial_keys, k)
    predicted = [c[0] for c in initial_batch + drawn]
    names = {v: i for i, v in enumerate(sorted({c[0] for c in cards}))}
    pre = [names[c[0]] for c in cards]
    obs = [names[c[0]] for c in drawn]
    skip = [names[c[0]] for c in initial_batch]
    # 属性池（主数据权重）→ 种子生成头 turns-3 属性
    pool, types_head, weights_src = [], [], ""
    idol = master.idols.get(str(loadout.get("idol_card_id") or ""))
    if idol and turns >= 4:
        from verify_gkbench_shuffle import STEP_ROWS
        step_name = Master.step_name(loadout)
        row = master.audition.get(
            (str(idol.get("produceStepAuditionDifficultyId") or ""),
             str(loadout.get("produce_id") or ""), STEP_ROWS.get(step_name, "")))
        cfg = None
        if row:
            cfg_id = str(row.get("produceExamBattleConfigId") or "")
            cfg = master.exam_configs.get(cfg_id)
        if cfg:
            weights = {1: int(cfg.get("vocal") or 0), 2: int(cfg.get("dance") or 0),
                       3: int(cfg.get("visual") or 0)}
            if all(v > 0 for v in weights.values()):
                pool, mutable = turn_pool_from_weights(weights, turns)
                types_head = generate_turn_types(seed, pool)
                weights_src = cfg_id
    return {
        "pid": pid, "index": int(group.get("index") or 0), "seed": seed, "turns": turns,
        "npc": npc, "k": k, "deck_size": len(cards),
        "model_match": predicted == actual, "predicted": predicted, "actual": actual,
        "pre": pre, "obs": obs, "skip": skip, "pool": pool, "types_head": types_head,
        "weights_src": weights_src,
        "pool_roundtrip": (infer_turn_type_pool(types_head + list(reversed(list(dict.fromkeys(pool))))) == pool) if pool else None,
    }


def run_scan(case, lo, hi, use_attr, exe=EXE):
    ints = lambda xs: ",".join(str(x) for x in xs) or "-"
    args = [str(exe), str(case["k"]), ints(case["pre"]), ints(case["obs"]),
            ints(case["skip"]), str(lo), str(hi)]
    if use_attr and case["pool"] and case["types_head"]:
        args += [ints(case["pool"]), ints(case["types_head"])]
    t0 = time.perf_counter()
    p = subprocess.run(args, capture_output=True, text=True, timeout=1800)
    dt = time.perf_counter() - t0
    if p.returncode != 0:
        return {"error": p.stderr.strip()[:200], "seeds": [], "secs": dt}
    seeds = [int(line) for line in p.stdout.splitlines()
             if line.strip() and not line.startswith("#")]
    return {"seeds": seeds, "secs": dt}


def _full_worker(args):
    case, lo, hi, use_attr = args
    return run_scan(case, lo, hi, use_attr)


def full_scan(case, procs, use_attr, hi=1 << 31):
    step = -(-hi // procs)
    jobs = [(case, i * step, min(hi, (i + 1) * step), use_attr) for i in range(procs)]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=procs) as ex:
        results = list(ex.map(_full_worker, jobs))
    seeds = sorted(s for r in results for s in r["seeds"])
    errs = [r["error"] for r in results if r.get("error")]
    return {"seeds": seeds, "secs": time.perf_counter() - t0, "errors": errs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=100_000)
    ap.add_argument("--limit", type=int, default=0, help="窄窗扫描组数上限（0=全部 384）")
    ap.add_argument("--full", type=int, default=0, help="全量扫描的组数")
    ap.add_argument("--full-attr", action="store_true", help="全量扫描带属性过滤")
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "_f2sl_seedscan_f0.json")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    master = Master(master_db())
    # 补 exam_configs 索引（build_case 用）
    from verify_gkbench_shuffle import load_table
    master.exam_configs = {str(r["id"]): r for r in load_table(master_db(), "ProduceExamBattleConfig")}
    seeds, saves = load_bench(DL)
    groups = list(iter_groups(seeds, saves))
    print(f"组数: {len(groups)}；seed_scan: {EXE}")

    cases = [build_case(master, pid, g, lo, me, saves.get(pid)) for pid, g, lo, me, _s in groups]
    mm = [c for c in cases if not c["model_match"]]
    no_obs = [c for c in cases if not c["obs"]]
    print(f"模型预判命中: {len(cases) - len(mm)}/{len(cases)}；obs 为空（initial 占满手牌）: {len(no_obs)}")
    print(f"属性池可用: {sum(1 for c in cases if c['pool'])}/{len(cases)}")

    narrow = []
    todo = [c for c in cases if c["obs"]][: args.limit or None]
    t0 = time.perf_counter()
    for i, c in enumerate(todo):
        lo = max(0, c["seed"] - args.window)
        hi = c["seed"] + args.window
        r = run_scan(c, lo, hi, use_attr=False)
        found = c["seed"] in r["seeds"]
        narrow.append({**{k: c[k] for k in ("pid", "index", "seed", "model_match", "turns", "npc", "k")},
                       "found": found, "hits": len(r["seeds"]), "secs": round(r["secs"], 3),
                       "error": r.get("error")})
        if (i + 1) % 50 == 0:
            print(f"  窄窗 {i + 1}/{len(todo)} 已回收 {sum(1 for x in narrow if x['found'])} 用时 {time.perf_counter() - t0:.1f}s")
    found = sum(1 for x in narrow if x["found"])
    found_mm = sum(1 for x in narrow if x["found"] and x["model_match"])
    print(f"\n窄窗 ±{args.window}: 找回 {found}/{len(narrow)}"
          f"（模型命中组 {found_mm}/{sum(1 for x in narrow if x['model_match'])}）"
          f"用时 {time.perf_counter() - t0:.1f}s")
    hits = Counter(x["hits"] for x in narrow)
    print(f"窗内命中数分布: {dict(sorted(hits.items()))}")
    for x in narrow:
        if not x["found"] and x["model_match"]:
            print(f"  !! 模型命中但 seed_scan 未找回: {x['pid']}[{x['index']}] seed={x['seed']} err={x.get('error')}")

    fulls = []
    if args.full:
        sel = [c for c in cases if c["model_match"] and c["obs"]][: args.full]
        for c in sel:
            r = full_scan(c, args.procs, args.full_attr)
            row = {**{k: c[k] for k in ("pid", "index", "seed", "turns", "npc", "k", "deck_size")},
                   "attr": args.full_attr, "candidates": len(r["seeds"]),
                   "found": c["seed"] in r["seeds"], "secs": round(r["secs"], 1),
                   "errors": r["errors"], "seeds_head": r["seeds"][:20]}
            fulls.append(row)
            print(f"全量[{c['pid']}#{c['index']}] attr={args.full_attr}: 候选 {row['candidates']} "
                  f"找回={row['found']} 用时 {row['secs']}s errs={r['errors'][:2]}")

    out = {"window": args.window, "narrow": narrow, "full": fulls,
           "model_mismatch": [{k: c[k] for k in ("pid", "index", "seed", "predicted", "actual")} for c in mm],
           "no_obs": [{k: c[k] for k in ("pid", "index", "seed")} for c in no_obs]}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n写入 {args.out}")


if __name__ == "__main__":
    main()
