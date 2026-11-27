"""sim 提取版对拍 A+B 部分 + C 抽样（20 局）。探针不提交。全套 test_adapter 仍在后台跑。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TA = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax" / "sim_fallback" / "test_adapter.py"
src = TA.read_text(encoding="utf-8")
head = src.split('print("== C.')[0]
# C 抽样：只回放前 20 局
tail = '''
print("== C. 真实托管观测回放（抽样 20 局） ==")
probe = ROOT / "data" / "_f2_probe_obs.jsonl"
n_steps = n_err = 0
max_ms = 0.0
import json, time
if probe.is_file():
    a_rep = make_algo(max_nodes=20000)
    cur = None
    games = 0
    with probe.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("kind") == "begin":
                games += 1
                if games > 20:
                    break
                a_rep = make_algo(max_nodes=20000)
                a_rep.begin(ctx_for(row.get("obs") or {}, row.get("loadout"), row.get("meta")))
                cur = a_rep
                continue
            obs = row.get("obs")
            if not obs or cur is None:
                continue
            t0 = time.perf_counter()
            d = cur.decide(ctx_for(obs))
            el = (time.perf_counter() - t0) * 1000
            max_ms = max(max_ms, el)
            n_steps += 1
            legal = [tuple(x) for x in obs.get("legal") or ()]
            if tuple(d.action) not in legal:
                n_err += 1
            if "error" in d.meta:
                n_err += 1
            plays = [x for x in legal if x[0] == "play"]
            if plays and d.action[0] != "play":
                n_err += 1
    check(n_err == 0, f"C 抽样: {n_steps} 步违规 {n_err}")
    print(f"  C 抽样 {games-1} 局 {n_steps} 步，违规 {n_err}，最大 {max_ms:.0f}ms")
print()
print(f"检查 {CHECKS} 项，失败 {len(FAILURES)} 项")
for msg in FAILURES[:30]:
    print("  ✗", msg)
sys.exit(1 if FAILURES else 0)
'''
exec(compile(head + tail, str(TA), "exec"), {"__name__": "__main__", "__file__": str(TA)})