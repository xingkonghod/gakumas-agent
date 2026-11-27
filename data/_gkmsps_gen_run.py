"""gkmsps pilot 教师打标运行 glue（我们的代码，探针不提交；引擎文件零改动）。

包装 uinet.gen.main：--prior off 时在**每个 spawn worker 内**运行时 monkeypatch
`uinet.engine.prior` 返回 None（native_search.prior_table 对 prior=None 走 has_prior=0
干净路径，native_search.py:178）。patch 只发生在 glue/worker 进程内存里，不改引擎文件。

用法（root；Windows 必须 UINET_NATIVE_LIB 指到已编通的 dll，脚本已 setdefault）：
    .venv\\Scripts\\python.exe -B data\\_gkmsps_gen_run.py --out data\\_gkmsps_labels `
        --shard pilot1 --episodes 1000 --workers 12 --worlds 8 --transitions 5000 `
        --pool data\\_gkmsps_pool\\pool.bench.v1.jsonl --prior off
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
DLL = WHEEL / "GakumasCLI" / "native" / "build" / "gkmscore.dll"
sys.path.insert(0, str(WHEEL))
sys.path.insert(0, str(WHEEL / "GKMSUINet"))
os.environ.setdefault("UINET_NATIVE_LIB", str(DLL))

from uinet import engine as E          # noqa: E402
from uinet import gen as G             # noqa: E402

_orig_init = G._init                   # 原始 worker 初始化（spawn 子进程里重新捕获，仍是原函数）

# 本 checkout 缺 GakumasCLI/produce/master_extra.json（master-bootstrap 生成件，仓库不含）。
# deck_value.Space.__init__ 无条件读它（support_event_cards）。不往引擎工作树写文件（硬约束），
# 运行时在 worker 里 monkeypatch support_event_cards → {}：影响仅限**生成编成的换卡池**少了
# 支援卡事件授予卡（grants=∅）；模板原样局与引擎建局/搜索路径不受影响（冒烟已证）。如实记录。
_EXTRA_FILE = WHEEL / "GakumasCLI" / "produce" / "master_extra.json"


def _patch_missing_extra():
    E.setup(chdir=False)               # 只加 sys.path，不 chdir
    if not _EXTRA_FILE.is_file():
        from GakumasCLI.produce import deck_value as DV
        DV.support_event_cards = lambda: {}


def _init_glue(args):
    """worker 初始化 = 缺件 patch + 原样（prior 默认开）。"""
    _patch_missing_extra()
    _orig_init(args)


def _init_prior_off(args):
    """worker 初始化 = 缺件 patch + 原样 + prior 关闭（只在 glue 进程内存里替换 engine.prior）。"""
    _patch_missing_extra()
    _orig_init(args)
    E.prior = lambda: None


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shard", required=True)
    ap.add_argument("--episodes", type=int, required=True)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--worlds", type=int, default=8)
    ap.add_argument("--transitions", type=int, default=5000)
    ap.add_argument("--pool", type=Path, required=True)
    ap.add_argument("--prior", choices=("on", "off"), default="on")
    ap.add_argument("--progress", type=Path, default=None)
    ap.add_argument("--generated", type=float, default=None, help="缺省 = uinet.gen 默认 0.5")
    ap.add_argument("--max-hours", type=float, default=None, help="安全阀：超时 terminate 并退出（可续跑）")
    a = ap.parse_args(argv)

    out = a.out.resolve()
    pool = a.pool.resolve()
    progress = (a.progress or out / f"{a.shard}.progress.jsonl").resolve()
    out.mkdir(parents=True, exist_ok=True)

    G._init = _init_prior_off if a.prior == "off" else _init_glue
    gen_argv = [str(out), "--shard", a.shard, "--episodes", str(a.episodes),
                "--workers", str(a.workers), "--worlds", str(a.worlds),
                "--transitions", str(a.transitions), "--pool", str(pool),
                "--progress", str(progress)]
    if a.generated is not None:
        gen_argv += ["--generated", str(a.generated)]
    if a.max_hours is not None:
        gen_argv += ["--max-hours", str(a.max_hours)]
    print(f"gen_run: prior={a.prior} shard={a.shard} episodes={a.episodes} workers={a.workers} "
          f"w{a.worlds}/t{a.transitions}", flush=True)
    try:
        return G.main(gen_argv) or 0
    finally:
        G._init = _orig_init


if __name__ == "__main__":
    raise SystemExit(main())
