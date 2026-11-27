"""Probe (not committed, OPENING_v6 ⑥): diagnose the 11 lock>=4 slots + 8 no-oracle produce-008 slots."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "out/_v6_v5steps.json").read_text(encoding="utf-8"))
slots = json.loads((ROOT / "out/_v5_slots.json").read_text(encoding="utf-8"))
v4 = {s["key"]: s for s in slots}
fin = json.loads((ROOT / "out/_v5_final.json").read_text(encoding="utf-8"))
v5 = fin["scores"]

KEYS = ["AS-ZHAN6GNN/0", "AS-ZHAN6GNN/1", "AS-R8ES22AB/0", "AS-R8ES22AB/1",
        "AS-VCCRY333/0", "AS-VCCRY333/1", "AS-N7X62HPS/0", "AS-N7X62HPS/1",
        "AS-VMDN884H/1", "AS-Y4K4R52T/1", "AS-663NKTY4/0", "AS-663NKTY4/1",
        "AS-QV6QCSN9/0", "AS-QV6QCSN9/1", "AS-X9GNYH3W/0", "AS-X9GNYH3W/1",
        "AS-VWAF2GDN/1", "AS-6SCJE43J/0", "AS-P8ZJTXNA/0"]


def main():
    hdr = (f"{'slot':18s} {'v4':>12s} {'v5':>12s} {'oracle':>10s} {'steps':>5s} {'lock':>4s} "
           f"{'scan':>5s} {'think':>6s} {'adopt':>5s} {'tailms':>6s} {'cand':>6s} modes")
    print(hdr)
    for k in KEYS:
        g = d.get(k)
        s = v4.get(k)
        if not g:
            print(k, "MISSING")
            continue
        st = g["steps"]
        scan = next((x.get("scan_s") for x in st if x.get("scan_s") is not None), None)
        think = sum(float(x.get("ms") or 0) for x in st) / 1000
        adopt = max((x.get("adopted") or 0) for x in st) if st else 0
        tail = [float(x.get("ms") or 0) for x in st if x.get("mode") == "tail"]
        cand = max((x.get("candidates") or 0) for x in st) if st else 0
        modes = dict(Counter(x.get("mode") for x in st))
        orc = (s or {}).get("oracle")
        print(f"{k:18s} {(s or {}).get('ours', 0):>12,} {v5.get(k, 0):>12,} "
              f"{(orc if orc else 0):>10,} {len(st):>5d} {str(g.get('lock_turn')):>4s} "
              f"{str(scan):>5s} {think:>6.0f} {adopt:>5d} "
              f"{(round(sum(tail)/max(1,len(tail))) if tail else 0):>6d} {cand:>6d} {modes}")


if __name__ == "__main__":
    main()