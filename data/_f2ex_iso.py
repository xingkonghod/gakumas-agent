"""一次性：隔离节点数差异来源（哈希种子 / memo / 遍历顺序）。不提交。"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from dataclasses import fields
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(ROOT / "src"))
HERE = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax"
spec = importlib.util.spec_from_file_location("expectimax_algo", HERE / "algo.py")
algo = importlib.util.module_from_spec(spec)
sys.modules["expectimax_algo"] = algo
spec.loader.exec_module(algo)
from gkagent.sim import expectimax as prod  # noqa: E402
from gkagent.sim.lesson import CardSpec as ProdCardSpec  # noqa: E402

doc = json.loads(Path(r"D:\Games\gakumas-agent\data\_f2ex_state113.json").read_text(encoding="utf-8"))


def deep_tuple(v):
    if isinstance(v, list):
        return tuple(deep_tuple(x) for x in v)
    return v


def build(mod, cardspec):
    kw = {k: deep_tuple(v) for k, v in doc["kw"].items()}
    zones = {}
    for z in ("hand", "deck", "discard", "excluded", "held"):
        zones[z] = tuple(cardspec(**{f.name: c[f.name] for f in fields(cardspec) if f.name in c})
                         for c in doc[z])
    return mod.ExpectState(**zones, **kw)


def run(mod, state, label):
    cfg = mod.ExpectimaxConfig(time_budget_ms=None, max_nodes=20000, allow_drinks=False)
    leaf = mod.AnalyticLeafValue(sigma=80.0)
    s = mod._Search(leaf, cfg, clock=time.perf_counter, deadline=None)
    try:
        s.root(state)
    except mod._Deadline:
        pass
    print(f"{label}: nodes={s.nodes} memo={len(s.memo)} aborted={s.aborted}")
    return s.nodes


for rep in range(2):
    se = build(algo, algo.CardSpec)
    sp = build(prod, ProdCardSpec)
    run(algo, se, f"ext rep{rep}")
    run(prod, sp, f"prod rep{rep}")

# 同进程内 ext 两次是否一致（memo 键稳定性）
se1 = build(algo, algo.CardSpec)
se2 = build(algo, algo.CardSpec)
print("canonical same-process equal:", se1.canonical() == se2.canonical())
print("hand card eq:", se1.hand[0] == se2.hand[0], "hash eq:", hash(se1.hand[0]) == hash(se2.hand[0]))
