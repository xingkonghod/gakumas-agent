import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "out/_v6_threads.json").read_text(encoding="utf-8"))
for k, v in d.items():
    if "no_lock" in v:
        continue
    print(k, "turn", v["turn"], "lock", v["lock_turn"])
    print("  " + " | ".join(f"{r['conc']}:{r['per_elapsed_med']}s/{r['trans_per_s']/1e6:.1f}M"
                            for r in v["levels"]))
    print("  starve " + str([(r["conc"], r["per_med"], round(r["trans_per_s"] / 1e6, 1))
                             for r in v["starvation"]]))