"""f2-sl2：等 gkbench 服务器恢复（hajime 评测中途服务器失联）。每 60s 探一次，恢复即退出。不提交。"""
import sys
import time

import httpx

deadline = time.time() + 45 * 60
attempt = 0
while time.time() < deadline:
    attempt += 1
    try:
        r = httpx.get("https://hiro.matto.top/gkbench/api/sets", timeout=20)
        if r.status_code == 200:
            print(f"server back after {attempt} attempts", flush=True)
            sys.exit(0)
    except Exception as e:
        print(f"attempt {attempt}: {type(e).__name__}", flush=True)
    time.sleep(60)
print("still down after 45 min", flush=True)
sys.exit(1)