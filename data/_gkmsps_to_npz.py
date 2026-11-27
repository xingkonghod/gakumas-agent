"""gkmsps pilot 标签 → 137 维 npz 转换 glue（我们的代码，探针不提交）。

官方教师标签 {obs,q,a}（uinet.gen 输出）→ r13 提取器（submissions/gkagent-ei-r13/algo.py
的 _state()+decision_features()，**只读 import**）+ card_profiles.json → 137 维。

标签口径（scope §4.3，log 域优势，与 uinet.train:93 同族）：
    A(s,a) = log(max(mean_k q[a][k], 1)) − mean_b log(max(mean_k q[b][k], 1))
b 遍历**全部 legal**（含 drink/end/select）；仅 play 候选输出行；q 全 0 决策丢弃。
每决策一个 group，每局一个 seed（gen 自采样种子；9:1 seed 切分由训练脚本做）。

npz 严格对齐 scripts/train_ei_policy.py --selfplay：X/y/seed/group/meta_json。
cards_played_total 与生产同口径：只累计**记录在案的多选项决策**里教师选 play 的次数
（引擎强制出牌 gen 已跳过、生产也计不到，r13 docstring 同口径）。

特征提取不需要引擎/DLL/master（obs 已含全部画面字段）；v2 obs 的 r13 所读字段与 v1
逐位一致（v1_view 只丢 timers/costs/pcount 与 full_power_point_gain_permil，r13 均不读）。

用法（root）：
    .venv\\Scripts\\python.exe -B data\\_gkmsps_to_npz.py `
        --labels data\\_gkmsps_labels\\pilot1.jsonl.zst --out out\\gkmsps_pilot_selfplay.npz
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
R13 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ei-r13"
sys.path.insert(0, str(WHEEL / "GKMSUINet"))     # uinet.gen.read_episodes（zstd 帧读取，轻量）
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))   # gkbench.algos.base（r13 algo import 需要）


def load_r13_module():
    """只读 import r13 algo.py（注册 sys.modules，dataclass 需要；冒烟先例同法）。"""
    spec = importlib.util.spec_from_file_location("gkmsps_r13_algo", R13 / "algo.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gkmsps_r13_algo"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    labels = [p.resolve() for p in a.labels]
    out = a.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    from uinet import gen as G
    mod = load_r13_module()
    assert mod.INPUT_DIM == 137

    t0 = time.perf_counter()
    Xs, ys, seeds, groups = [], [], [], []
    stats = Counter()
    seed_seen: dict[int, int] = {}
    group = 0
    ep_metas = []
    for path in labels:
        rep = {}
        for ep in G.read_episodes(path, rep):
            stats["episodes"] += 1
            seed = int(ep["seed"])
            if seed in seed_seen:
                stats["seed_collisions"] += 1     # 同 seed 样本进同一 train/val 侧，不泄漏；如实计数
            seed_seen[seed] = ep["idx"]
            algo = mod.EiR13Algo()                # 只用作提取器容器（卡表+画像+状态映射）
            algo.begin(SimpleNamespace(loadout=ep["loadout"], meta=None))
            ep_rows = 0
            for d in ep["decisions"]:
                stats["decisions"] += 1
                obs, q, chosen = d["obs"], d["q"], int(d["a"])
                legal = [tuple(x) for x in obs.get("legal") or ()]
                if len(legal) != len(q) or not legal or chosen >= len(legal):
                    stats["bad_alignment"] += 1
                    continue
                if all(v == 0 for row in q for v in row):
                    stats["dropped_all_zero_q"] += 1
                    continue
                play_pos = [j for j, act in enumerate(legal) if act[0] == "play" and len(act) > 1]
                if play_pos:
                    state = algo._state(obs)
                    logmeans = [math.log(max(sum(row) / len(row), 1.0)) for row in q]
                    base = sum(logmeans) / len(logmeans)
                    emitted = 0
                    for j in play_pos:
                        hi = int(legal[j][1])
                        if not 0 <= hi < len(state.hand):
                            stats["bad_hand_index"] += 1
                            continue
                        x = mod.decision_features(state, state.hand[hi])
                        Xs.append(x)
                        ys.append(logmeans[j] - base)
                        seeds.append(seed)
                        groups.append(group)
                        emitted += 1
                    if emitted:
                        group += 1
                        ep_rows += emitted
                        stats["kept_decisions"] += 1
                    else:
                        stats["dropped_no_valid_play"] += 1
                else:
                    stats["non_play_decisions"] += 1   # select/end-only：不出行
                if legal[chosen][0] == "play":
                    algo._played_total += 1            # 生产同口径：只计 decide 返回的 play
            stats["fallbacks"] += int(ep.get("fallbacks") or 0)
            ep_metas.append({"idx": ep["idx"], "seed": seed, "final": ep["final"],
                             "rows": ep_rows, "origin": ep.get("origin")})
        stats["frames"] += rep.get("frames", 0)
        print(f"{path.name}: 累计 {stats['episodes']} 局 / {stats['kept_decisions']} 决策 / "
              f"{len(Xs)} 行（{time.perf_counter() - t0:.1f}s）", flush=True)

    X = np.asarray(Xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    seed_arr = np.asarray(seeds, dtype=np.int64)
    group_arr = np.asarray(groups, dtype=np.int64)
    if X.ndim != 2 or X.shape[1] != 137 or not np.isfinite(X).all() or not np.isfinite(y).all():
        raise SystemExit(f"特征/标签形状或有限性检查失败：X{X.shape}")
    meta = {
        "kind": "selfplay",
        "args": {"scenario": "gkmsps_pilot", "labels": [str(p) for p in labels]},
        "label": "log-advantage: log(max(mean_q(a),1)) - mean_b log(max(mean_q(b),1)); b=all legal; play rows only",
        "extractor": "submissions/gkagent-ei-r13/algo.py (read-only) + card_profiles.json",
        "n_rows": int(X.shape[0]), "n_groups": int(group), "n_seeds": int(len(seed_seen)),
        "stats": dict(stats),
    }
    np.savez(out, X=X, y=y, seed=seed_arr, group=group_arr, meta_json=np.array(json.dumps(meta, ensure_ascii=False)))
    summary = {
        **dict(stats),
        "rows": int(X.shape[0]), "groups": int(group), "unique_seeds": int(len(seed_seen)),
        "label_mean": float(y.mean()), "label_std": float(y.std()),
        "label_min": float(y.min()), "label_max": float(y.max()),
        "mean_final_teacher": float(np.mean([m["final"] for m in ep_metas])) if ep_metas else 0.0,
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "out": str(out),
    }
    out.with_suffix(".stats.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
