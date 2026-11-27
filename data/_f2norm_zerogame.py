import sys
sys.path.insert(0, r"D:\Games\gakumas-agent\data\bench_repo")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkbench.client import _client
c = _client()
runs = {"off": "28500a5be2bc", "clip2": "a4d68f4fe5fc", "clip3": "41258b594697",
        "clip4": "9b25b4f66cfa", "rescale": "c1b8a2b7ac52", "both": "fc9839dbb824"}
for mode, h in runs.items():
    run = f"template-hif-gkagent-ei-r13-norm-{mode}-xingkonghod-{h}"
    j = c.get(f"/api/runs/{run}").json()
    for e in j.get("episodes") or []:
        if e.get("id") == "AS-XPRY8BRF" and e.get("seed_index") == 1:
            sc = e.get("score")
            print(f"{mode:8s} score={sc:>8} dec={e.get('decisions')} secs={e.get('secs')}")
            print("   route:", e.get("route"))