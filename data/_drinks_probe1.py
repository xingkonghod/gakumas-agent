"""M6 探针 1：W9 battle-log 动作序列 + opening 结构 dump。不提交。"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
W9 = ROOT / "data/_rinami_live/W9"

d = json.load(open(W9 / "battle-log.json", encoding="utf-8"))
acts = d["result"]["examActions"]
print("actions:", len(acts))
for i, a in enumerate(acts):
    print(i, a["actionType"].replace("ExamActionType_", ""), a.get("indexes"),
          {k: v for k, v in a.items() if k not in ("actionType", "indexes")})
print("score", d["result"]["score"], "stamina", d["result"]["stamina"])
print("turnEndLogs n=", len(d["turnEndLogs"]))
print("log0 keys:", list(d["turnEndLogs"][0].keys()))

op = json.load(open(W9 / "opening.json", encoding="utf-8"))
print("\nopening keys:", list(op.keys()))
ps = op.get("parameterScalars", {})
print("parameterScalars keys:", list(ps.keys()))
print("currentRandom:", ps.get("currentRandom"))
vals = ps.get("values", {})
print("values:", json.dumps(vals, ensure_ascii=False))
zones = op.get("zones", {})
print("zones keys:", list(zones.keys()) if isinstance(zones, dict) else type(zones))
if isinstance(zones, dict):
    for k, v in zones.items():
        print("zone", k, "n=", len(v) if isinstance(v, list) else v)
        if isinstance(v, list) and v:
            print("  sample:", json.dumps(v[0], ensure_ascii=False))
print("phase:", op.get("phase"), "decisionReady:", op.get("decisionReady"))
for k in op:
    if k not in ("parameterScalars", "zones"):
        v = op[k]
        print("other", k, ":", json.dumps(v, ensure_ascii=False)[:300])
