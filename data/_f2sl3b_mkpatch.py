"""f2-sl3b：把 forced_play 参数化改动重建为补丁（探针侧，不提交）。

A/B 跑完后 seedlock 投稿目录已按 lead 指令恢复 git 基线；本脚本从基线 algo.py 重建
参数化副本 data/_f2sl3b_algo_param.py 与补丁 data/_f2sl3b_forced_play.patch。
复现 A/B：git -C data\\bench_repo apply data\\_f2sl3b_forced_play.patch（跑完 git checkout 恢复）。
"""
from __future__ import annotations

import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-seedlock" / "algo.py"
src = BASE.read_text(encoding="utf-8")

EDITS = [
    ("#   4. 锁定前/丢失后：引擎卡表贪心兜底。硬规矩：legal 里有 play 绝不 end。",
     "#   4. 锁定前/丢失后：引擎卡表贪心兜底。硬规矩 forced_play（缺省 1 开）：legal 里有 play 绝不 end；\n"
     "#      托管评测 obs 完美，可 forced_play=0 关掉（允许 GNRPA 为蓄体力主动 end）。"),
    ('                   "锁定前/丢失后引擎卡表贪心兜底；硬规矩：有可出牌绝不 end",',
     '                   "锁定前/丢失后引擎卡表贪心兜底；硬规矩 forced_play（缺省开）：有可出牌绝不 end",'),
    ("                 stabilization=3, prior=0, rescan_above=256, report=1, **kw):",
     "                 stabilization=3, prior=0, rescan_above=256, forced_play=1, report=1, **kw):"),
    ("                         rescan_above=int(rescan_above), **kw)",
     "                         rescan_above=int(rescan_above), forced_play=int(forced_play), **kw)"),
    ("        self.rescan_above = int(rescan_above)\n        self.report,",
     "        self.rescan_above = int(rescan_above)\n"
     "        # forced_play=1（缺省）：硬规矩「有可出牌绝不 end」（真机 bot 防 OCR 盲打的历史约束）。\n"
     "        # forced_play=0：托管评测 obs 完美，允许 GNRPA 为蓄体力主动 end，不丢在手路线。\n"
     "        self.forced_play = bool(int(forced_play))\n        self.report,"),
    ('                       "stabilization": self.stabilization, "prior": int(self.use_prior)}',
     '                       "stabilization": self.stabilization, "prior": int(self.use_prior),\n'
     '                       "forced_play": int(self.forced_play)}'),
    ("        if action[0] == \"end\" and any(a[0] == \"play\" for a in legal):\n"
     "            action, mode = self._best_play(obs, legal), \"forced_play\"   # 硬规矩：有可出牌绝不 end",
     "        if self.forced_play and action[0] == \"end\" and any(a[0] == \"play\" for a in legal):\n"
     "            action, mode = self._best_play(obs, legal), \"forced_play\"   # 硬规矩（forced_play=1 缺省）：有可出牌绝不 end"),
]
out = src
for old, new in EDITS:
    assert out.count(old) == 1, f"match count {out.count(old)} for {old[:50]!r}"
    out = out.replace(old, new)

param = ROOT / "data" / "_f2sl3b_algo_param.py"
param.write_text(out, encoding="utf-8", newline="\n")
diff = difflib.unified_diff(src.splitlines(keepends=True), out.splitlines(keepends=True),
                            fromfile="a/submissions/gkagent-seedlock/algo.py",
                            tofile="b/submissions/gkagent-seedlock/algo.py", n=3)
patch = "diff --git a/submissions/gkagent-seedlock/algo.py b/submissions/gkagent-seedlock/algo.py\n" + "".join(diff)
pp = ROOT / "data" / "_f2sl3b_forced_play.patch"
pp.write_text(patch, encoding="utf-8", newline="\n")
print("wrote", param, "and", pp)
