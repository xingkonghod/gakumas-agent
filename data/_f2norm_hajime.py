import sys, re
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, r"D:\Games\gakumas-agent\data\bench_repo")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkbench.client import _client
c = _client()
ROOT = Path(r"D:\Games\gakumas-agent")
RUN_RE = re.compile(r"template-hajime-gkagent-ei-r13-norm-[a-z0-9]+-xingkonghod-[0-9a-f]{12}")

def analyze(logname):
    p = ROOT / "data" / logname
    if not p.is_file():
        print(logname, "missing"); return
    txt = p.read_text(encoding="utf-16", errors="replace")
    m = RUN_RE.search(txt)
    if not m:
        print(logname, "no run name"); return
    run = m.group(0)
    j = c.get(f"/api/runs/{run}").json()
    eps = j.get("episodes") or []
    groups = defaultdict(list)
    stages = defaultdict(int)
    for e in eps:
        sc = e.get("score")
        tags = e.get("tags") or {}
        stage = tags.get("stage", "")
        stages[stage] += 1
        kind = "exam" if "audition" in stage else ("lesson" if stage else "unknown")
        if isinstance(sc, (int, float)):
            groups[kind].append(sc); groups["all"].append(sc)
    print(f"== {logname} run={run} n={len(eps)}")
    print("   stages:", dict(stages))
    for k, v in sorted(groups.items()):
        if v:
            print(f"   {k:8s} n={len(v):3d} mean={sum(v)/len(v):10.1f} min={min(v):8.0f} max={max(v):9.0f}")

for ln in sys.argv[1:] or ["_f2norm_run_rescale_hajime.log", "_f2norm_run_rescalebuffs_hajime.log"]:
    analyze(ln)