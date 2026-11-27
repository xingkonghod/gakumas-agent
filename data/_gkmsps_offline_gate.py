"""gkmsps pilot 离线门 glue（我们的代码，探针不提交；import AGPL 引擎，纪律同 _f2sl 探针）。

held-out 模板 × 自采样种子：r14 网打 N 局 vs 引擎贪心 N 局（**同题同种子**配对）。
贪心 = GakumasCLI.scenario.exam_session.greedy_policy（teacher._greedy_value 同口径）。
网臂走真实投稿适配器 decide()（含硬规矩/异常回退），强制决策自动步（gen/托管同口径）。

门（scope §5.3）：网均分 ≥1.3× 贪心；特征 |z| 抽查 score/vitality/card_block_scale ≤3
（z 相对训练 mean/scale）；val 排序 ≥0.50 由训练输出另行核对。

用法（root）：
    .venv\\Scripts\\python.exe -B data\\_gkmsps_offline_gate.py --n 100 `
        --algo-dir data\\bench_repo\\submissions\\gkagent-ei-r14 --out out\\_gkmsps_offline_gate.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
DLL = WHEEL / "GakumasCLI" / "native" / "build" / "gkmscore.dll"
sys.path.insert(0, str(WHEEL))
sys.path.insert(0, str(WHEEL / "GKMSUINet"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
os.environ.setdefault("UINET_NATIVE_LIB", str(DLL))


def load_algo_module(algo_dir: Path):
    spec = importlib.util.spec_from_file_location("gkmsps_gate_algo", algo_dir / "algo.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gkmsps_gate_algo"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=Path, default=ROOT / "data" / "_gkmsps_pool" / "pool.bench.v1.jsonl")
    ap.add_argument("--algo-dir", type=Path, default=ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ei-r14")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed-tag", default="gkmsps-gate-v1")
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "_gkmsps_offline_gate.json")
    a = ap.parse_args()
    pool_path, algo_dir, out = a.pool.resolve(), a.algo_dir.resolve(), a.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    from uinet import engine, loadouts
    from uinet.env import Battle
    from GakumasCLI.scenario.exam_session import greedy_policy

    mod = load_algo_module(algo_dir)
    cls = getattr(mod, "EiR14Algo", None) or getattr(mod, "EiR13Algo")
    pool = loadouts.load(pool_path)
    held = [it for it in pool if it["held_out"]]
    rng = random.Random(a.seed_tag)
    if not held:
        raise SystemExit("池里没有 held-out 行")
    picks = rng.sample(held, a.n) if a.n <= len(held) else [rng.choice(held) for _ in range(a.n)]
    battles = [(it, dict(it["loadout"], seed=rng.randrange(1, 2 ** 31 - 1))) for it in picks]

    z_idx = {
        "score": mod.FEATURE_NAMES.index("score"),
        "vitality": mod.FEATURE_NAMES.index("vitality"),
        "card_block_scale": mod.LEAF_DIM + mod.ACTION_FEATURE_NAMES.index("card_block_scale"),
    }
    z_rows: list[np.ndarray] = []
    net_scores, greedy_scores, errors, fallbacks = [], [], 0, 0
    t0 = time.perf_counter()
    for k, (it, lo) in enumerate(battles):
        # ---- 网臂（真实适配器 decide）----
        algo = cls()
        ctx = SimpleNamespace(loadout=lo, meta=None, budget=5.0, obs=None, rng=random.Random(0))
        algo.begin(ctx)
        b = Battle(lo)
        while not b.finished:
            legal = b.legal()
            if len(legal) == 1:
                b.step(legal[0])
                continue
            obs = b.obs()
            if len(z_rows) < 4000:
                st = algo._state(obs)
                for act in obs.get("legal") or ():
                    if act[0] == "play" and 0 <= int(act[1]) < len(st.hand):
                        z_rows.append(mod.decision_features(st, st.hand[int(act[1])]))
            ctx.obs = obs
            d = algo.decide(ctx)
            if d.meta.get("error"):
                errors += 1
            if "退回" in str(d.meta.get("why", "")):
                fallbacks += 1
            b.step(d.action)
        net_scores.append(int(b.score))
        # ---- 贪心臂（同题同种子）----
        s, _meta = engine.build(lo)
        while not s.finished:
            choice = greedy_policy(s, list(s.deck.hand))
            s.step(("end",) if choice is None else ("play", int(choice)), observe=False)
        greedy_scores.append(int(s.state.score))
        if (k + 1) % 20 == 0 or k + 1 == len(battles):
            print(f"{k + 1}/{len(battles)} 网均 {np.mean(net_scores):,.0f} vs 贪心均 {np.mean(greedy_scores):,.0f}"
                  f"（{time.perf_counter() - t0:.0f}s）", flush=True)

    net = np.asarray(net_scores, dtype=np.float64)
    gre = np.asarray(greedy_scores, dtype=np.float64)
    ratio = float(net.mean() / gre.mean()) if gre.mean() > 0 else 0.0
    zsample = np.asarray(z_rows, dtype=np.float64)
    zstats = {}
    if zsample.size:
        z = (zsample - algo.net.mean) / algo.net.scale
        for name, j in z_idx.items():
            col = np.abs(z[:, j])
            zstats[name] = {"mean_abs_z": float(col.mean()), "p95_abs_z": float(np.percentile(col, 95)),
                            "max_abs_z": float(col.max())}
    report = {
        "n": len(battles), "seed_tag": a.seed_tag,
        "held_pool_rows": len(held),
        "net_mean": float(net.mean()), "greedy_mean": float(gre.mean()),
        "ratio_net_over_greedy": ratio,
        "net_median": float(np.median(net)), "greedy_median": float(np.median(gre)),
        "paired_wins_net": int((net > gre).sum()), "paired_wins_greedy": int((net < gre).sum()),
        "ties": int((net == gre).sum()),
        "net_min": int(net.min()), "net_max": int(net.max()),
        "adapter_errors": errors, "adapter_fallbacks": fallbacks,
        "z_check": zstats, "z_rows": int(zsample.shape[0]),
        "gate_ratio_1.3": ratio >= 1.3,
        "gate_z_le_3": all(v["max_abs_z"] <= 3.0 for v in zstats.values()) if zstats else False,
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "per_battle": [{"key": it["key"], "seed": lo["seed"], "net": int(nv), "greedy": int(gv)}
                       for (it, lo), nv, gv in zip(battles, net_scores, greedy_scores)],
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    slim = {k: v for k, v in report.items() if k != "per_battle"}
    print(json.dumps(slim, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
