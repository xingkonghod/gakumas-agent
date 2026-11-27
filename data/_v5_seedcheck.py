"""Probe (not committed): do diag1 hidden seeds reproduce the hosted v3 slot-0 scores exactly?"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "data/_f2exv3_diag1.json").read_text(encoding="utf-8"))
v3slots = json.loads((ROOT / "data/_v3_slots.json").read_text(encoding="utf-8"))["v3"]
for r in d["rows"]:
    if r["cfg"] != "v3":
        continue
    hosted = v3slots.get(f"{r['pid']}/0")
    print(f"{r['pid']:<14} seed={r['seed']:>12} offline_v3={r['score']:>12,} state={r['state']:<7} "
          f"hosted_slot0={hosted!s:>12} match={hosted == r['score']}")