"""Probe (not committed, OPENING_v6 ⑤): play one dev-seed FINAL with tail_turns=3 and look at tail steps.

tail_turns=3 = the exact tail starts 1 turn earlier. If its tail steps complete (status complete) in
a fraction of the 7s search budget, the +1-turn exact horizon is free; if they hit deadline, it is not.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
SUB_V6 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v6"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V6 = _load("algo_exv6", SUB_V6 / "algo.py")
from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
seeds_doc = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

TARGETS = [("AS-WDKWQYW5", 988313260), ("AS-5KZSXANK", 448199597), ("AS-3EW6E6HV", 153762096)]
tail_turns = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def play(pid, seed):
    lo = expand_loadout(saves[pid]["loadout"])
    algo = V6.ExSeedV6Algo(procs=16, report=0, tail_turns=tail_turns)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, 10.0, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    algo.begin(ctx)
    n, rows, t0 = 0, [], time.perf_counter()
    while not ref.finished and n < 400:
        ctx.obs = ref.obs()
        d = algo.decide(ctx)
        m = d.meta or {}
        if m.get("mode") == "tail" or m.get("tail_status") is not None:
            rows.append({"step": n, "ms": round(float(m.get("ms") or 0)),
                         "tail_status": m.get("tail_status"), "tail_why": m.get("tail_why"),
                         "searches": m.get("pool_searches")})
        ref.step(d.action)
        n += 1
    return {"pid": pid, "seed": seed, "tail_turns": tail_turns, "score": int(ref.score),
            "think_s": round(time.perf_counter() - t0, 1), "decisions": n, "tail_steps": rows}


def main():
    out = []
    for pid, seed in TARGETS:
        r = play(pid, seed)
        out.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    path = ROOT / "out" / f"_v6_tail_prod_{tail_turns}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", path)


if __name__ == "__main__":
    main()