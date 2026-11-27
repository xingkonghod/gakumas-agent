"""gkmsps pilot 建池 glue（我们的代码，探针不提交）：gkbench 公开 505 题模板 → uinet 池 jsonl。

读 data/bench_local/gkbench_dl/hif/saves.jsonl（公开题模板，不含保密种子）
→ gkbench.save.expand_loadout（MIT）→ 逐条 engine.build 验证可建局（单进程）
→ 池行格式对齐 uinet/loadouts.py:137-139/232-233（Generator 只吃 idol/plan/loadout/key）。
held-out：按 group（meta.family）sha1，每 plan 前 ceil(20%) 组（uinet.loadouts.held_groups 同式）。
训练种子由 uinet.gen 自采样；公开 dev 种子（hif/seeds.json）不进池。

用法（root，-B 防 __pycache__ 污染引擎工作树）：
    .venv\\Scripts\\python.exe -B data\\_gkmsps_build_pool.py --out data\\_gkmsps_pool\\pool.bench.v1.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "data" / "GKMSMainWheel"
SAVES = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif" / "saves.jsonl"
DLL = WHEEL / "GakumasCLI" / "native" / "build" / "gkmscore.dll"

sys.path.insert(0, str(WHEEL))
sys.path.insert(0, str(WHEEL / "GKMSUINet"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
os.environ.setdefault("UINET_NATIVE_LIB", str(DLL))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "_gkmsps_pool" / "pool.bench.v1.jsonl")
    ap.add_argument("--verify-seed", type=int, default=1, help="建局验证用的固定种子（不进池；gen 自采样）")
    a = ap.parse_args()
    out = a.out.resolve()                      # engine.setup() 会 chdir，先 resolve
    out.parent.mkdir(parents=True, exist_ok=True)

    from gkbench.save import expand_loadout
    from uinet import engine, loadouts

    t0 = time.perf_counter()
    rows = [json.loads(l) for l in SAVES.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"saves: {len(rows)} 行", flush=True)

    items, bad = [], Counter()
    for r in rows:
        pid = str(r.get("id"))
        meta_t = r.get("meta") or {}
        try:
            lo = expand_loadout(r["loadout"])
            s, meta = engine.build(lo, seed=a.verify_seed)
            if not any((s.config.audition_permils or {}).values()):
                bad["permils all 0"] += 1
                continue
            step = str(lo.get("step_type") or "AUDITION_FINAL")
            item = {
                "key": f"bench:{pid}_{step}",
                "source": "bench",
                "group": str(meta_t.get("family") or pid),
                "idol": lo["idol_card_id"],
                "loadout": lo,
                "plan": int(meta["plan_type"]),
                "step": step,
                "produce": lo.get("produce_id") or "produce-008",
                "limit_turn": int(meta["limit_turn"]),
                "stage": meta_t.get("stage"),
                "recorded_score": None,
                "actions": None,
            }
            if s.state.unresolved_effects:
                item["unresolved"] = [str(x)[:120] for x in s.state.unresolved_effects]
            items.append(item)
        except Exception as exc:                                   # noqa: BLE001
            bad[f"{type(exc).__name__}: {str(exc)[:80]}"] += 1
            print(f"  不可建局 {pid}: {type(exc).__name__}: {str(exc)[:120]}", flush=True)

    held = loadouts.held_groups(items)         # 每 plan 按 group sha1 前 ceil(20%)
    for it in items:
        it["held_out"] = it["group"] in held
    with out.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False, separators=(",", ":")) + "\n")

    n_held = sum(it["held_out"] for it in items)
    stats = {
        "saves_rows": len(rows),
        "pool_rows": len(items),
        "held_out_rows": n_held,
        "train_rows": len(items) - n_held,
        "held_groups": len(held),
        "groups": len({it["group"] for it in items}),
        "by_plan": dict(Counter(it["plan"] for it in items)),
        "by_plan_held": dict(Counter(it["plan"] for it in items if it["held_out"])),
        "by_step": dict(Counter(it["step"] for it in items)),
        "not_buildable": dict(bad),
        "unresolved_rows": sum("unresolved" in it for it in items),
        "verify_seed": a.verify_seed,
        "rules": engine.exam_rules_version(),
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "out": str(out),
    }
    out.with_suffix(".stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
