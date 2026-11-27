"""一次性探针：托管跑 hif-live，把每步真实 UIObs/meta/loadout 落盘，验证映射口径。

不提交。打法 = 第一张能打的牌（与 _example 相同），只为采集观测。
    cd data/bench_repo
    ..\\..\\.venv\\Scripts\\python.exe -m gkbench hosted --set hif-live \
        --algo D:\\Games\\gakumas-agent\\data\\_f2_probe_algo.py:ObsProbe --seeds 0
"""
from __future__ import annotations

import json
from pathlib import Path

from gkbench.algos.base import Algorithm, Decision

OUT = Path(r"D:\Games\gakumas-agent\data\_f2_probe_obs.jsonl")


class ObsProbe(Algorithm):
    name = "f2-obs-probe"
    needs_gkms = False
    sees_seed = False
    privileged = False

    def begin(self, ctx):
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "kind": "begin",
                "meta": getattr(ctx, "meta", None),
                "loadout": getattr(ctx, "loadout", None),
                "obs": ctx.obs,
            }, ensure_ascii=False) + "\n")

    def decide(self, ctx):
        obs = ctx.obs
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "step", "obs": obs}, ensure_ascii=False) + "\n")
        legal = [tuple(a) for a in obs["legal"]]
        plays = [a for a in legal if a[0] == "play"]
        if plays:
            return Decision(plays[0], {"why": "probe"})
        if ("end",) in legal:
            return Decision(("end",), {"why": "probe"})
        return Decision(legal[0], {"why": "probe"})