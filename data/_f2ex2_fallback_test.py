"""版本A 兜底路径验证：worlds 抛错 → sim fallback 出牌。探针不提交。"""
from __future__ import annotations
import importlib.util, json, os, random, sys
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(r"D:\Games\gakumas-agent")
os.environ["GKMS_ROOT"] = str(ROOT / "data" / "GKMSMainWheel")
os.environ["GKMSCLIGPU_LIB"] = str(ROOT / "data" / "GKMSMainWheel" / "GakumasCLI" / "native" / "build" / "gkmscore.dll")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkbench import engine
engine.setup()
HERE = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax"
spec = importlib.util.spec_from_file_location("algo_a", HERE / "algo.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

obs = json.loads((ROOT / "data" / "_f2ex_state113.json").read_text(encoding="utf-8"))  # 只是借个形状
# 用真实托管观测第一局
probe = ROOT / "data" / "_f2_probe_obs.jsonl"
begin = None; first = None
with probe.open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("kind") == "begin":
            begin = r; continue
        if begin and r.get("obs"):
            first = r["obs"]; break

class BadCtx:
    def __init__(self, obs, loadout, meta):
        self.obs, self.loadout, self.meta, self.budget = obs, loadout, meta, 5.0
        self.rng = random.Random(1)
    def worlds(self, k):
        raise RuntimeError("模拟：要世界失败 503")

a = m.ExpectimaxAlgo(worlds=6, mode="eval", threads=4)
ctx = BadCtx(first, begin.get("loadout") or {}, begin.get("meta") or {})
a.begin(ctx)
d = a.decide(ctx)
legal = [tuple(x) for x in first["legal"]]
print("action:", d.action, "in legal:", tuple(d.action) in legal)
print("meta:", json.dumps(d.meta, ensure_ascii=False)[:500])
assert tuple(d.action) in legal and d.meta.get("mode") == "fallback"
plays = [x for x in legal if x[0] == "play"]
assert not plays or d.action[0] == "play"
print("FALLBACK OK")