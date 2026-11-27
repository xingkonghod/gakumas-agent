"""对照采集 traffic 的考试真实分 vs run record 读屏分（探针不提交）。"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
hits = []
for line in P.open(encoding="utf-8", errors="replace"):
    if "EndExamBattle" in line:
        hits.append(line)
print("EndExamBattle lines:", len(hits))
for line in hits[-8:]:
    j = json.loads(line)
    s = json.dumps(j, ensure_ascii=False)
    scores = re.findall(r'"score":\s*(\d+)', s)
    rank = re.findall(r'"rank":\s*(\d+)', s)
    ts = j.get("ts") or j.get("time") or j.get("timestamp")
    print(ts, "scores=", scores[:6], "ranks=", rank[:4])