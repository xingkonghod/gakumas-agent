import sys, re
from pathlib import Path
import numpy as np
sys.path.insert(0, r"D:\Games\gakumas-agent\data\bench_repo")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkbench.client import _client
c = _client()
ROOT = Path(r"D:\Games\gakumas-agent")
RUN_RE = re.compile(r"template-[a-z]+-gkagent-ei-r13-norm-[a-z0-9]+-xingkonghod-[0-9a-f]{12}")

def run_from_log(mode):
    txt = (ROOT / "data" / f"_f2norm_run_{mode}.log").read_text(encoding="utf-16", errors="replace")
    return RUN_RE.search(txt).group(0)

def scores(run):
    j = c.get(f"/api/runs/{run}").json()
    return {(e.get("id"), e.get("seed_index")): e.get("score") for e in j.get("episodes") or []
            if isinstance(e.get("score"), (int, float))}

off = scores(run_from_log("off"))
rescale = scores(run_from_log("rescale"))
rsb = scores(run_from_log("rescalebuffs"))
rng = np.random.default_rng(42)

def paired(a, b, la, lb):
    common = sorted(set(a) & set(b))
    d = np.array([a[k] - b[k] for k in common], float)
    n = len(d); mean = d.mean(); sd = d.std(ddof=1)
    t = mean / (sd / np.sqrt(n)) if sd > 0 else 0
    boots = rng.choice(d, size=(4000, n), replace=True).mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"{la} vs {lb}: n={n} meanΔ={mean:.0f} win={(d>0).sum()} loss={(d<0).sum()} tie={(d==0).sum()} t={t:.2f} CI=[{lo:.0f},{hi:.0f}]")

paired(rsb, off, "rescalebuffs", "off")
paired(rsb, rescale, "rescalebuffs", "rescale")
print("means: off=%.0f rescale=%.0f rescalebuffs=%.0f" % (np.mean(list(off.values())), np.mean(list(rescale.values())), np.mean(list(rsb.values()))))