"""pimc-opt 探针②：看服务器 episode/eval 原始字段，找逐步计时数据入口。只读。"""
from __future__ import annotations
import json, sys
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERVER = "https://hiro.matto.top/gkbench"
TOK = (Path.home() / ".config/gkbench/token").read_text().strip()
C = httpx.Client(base_url=SERVER, headers={"Authorization": f"Bearer {TOK}"}, timeout=120)

j = C.get("/api/runs/template-hif-gkagent-expectimax-xingkonghod-3671171720ab").json()
eps = j.get("episodes") or []
print("run keys:", list(j.keys()))
print("episode[0] keys:", list(eps[0].keys()))
e0 = eps[0]
print(json.dumps({k: (v if not isinstance(v, list) or len(v) < 12 else f"<list n={len(v)}>") for k, v in e0.items()},
                 ensure_ascii=False)[:2000])
# 找 expectimax 的 evals（含进行中）
try:
    evs = C.get("/api/evals").json()
    for e in evs if isinstance(evs, list) else []:
        if "expectimax" in json.dumps(e):
            print("EVAL:", json.dumps(e, ensure_ascii=False)[:600])
except Exception as ex:
    print("evals list err:", ex)
# 单局详情接口尝试
eid = e0.get("episode") or e0.get("id")
for path in (f"/api/episodes/{eid}",):
    try:
        r = C.get(path)
        print(path, r.status_code, r.text[:400])
    except Exception as ex:
        print(path, "err", ex)