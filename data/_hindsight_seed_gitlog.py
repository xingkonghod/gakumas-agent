"""一次性修复：重注入 gitlog 种子文档（19:02 的 retain 因 qwen-plus max_tokens bug 失败，
daemon 修复后未自动 recover）。等价于插件 session-start 的 gitlog seed 动作：
最近 300 条 commit message（oldest first）→ strategy=gitlog，tags 带 gitlog-head:<HEAD>
以便后续会话按插件逻辑 append。不提交（data/_probe* 同口径的一次性脚本）。"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

BANK = "coding-agent::gakumas-agent"
API = "http://127.0.0.1:9077"

head = subprocess.run(
    ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
).stdout.strip()
log = subprocess.run(
    ["git", "log", "--reverse", "--date=short", "--format=%h %ad %s", "-300"],
    capture_output=True, text=True, check=True, encoding="utf-8",
).stdout.strip()
n = len(log.splitlines())
content = (
    f"Git commit message history for repository gakumas-agent (last {n} commits, "
    f"oldest first, HEAD={head[:7]}):\n\n{log}"
)
item = {
    "content": content,
    "document_id": f"gitlog:gakumas-agent",
    "strategy": "gitlog",
    "context": "git commit message seed for repository gakumas-agent",
    "tags": ["source:git", "source:git-log", f"gitlog-head:{head}"],
    "metadata": {"ref_id": "gitlog:gakumas-agent", "source": "git-log"},
    "timestamp": "unset",
    "observation_scopes": "shared",
    "update_mode": "replace",
}
req = urllib.request.Request(
    f"{API}/v1/default/banks/{BANK}/memories",
    data=json.dumps({"items": [item], "async": True}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    body = json.loads(resp.read().decode("utf-8"))
print(f"commits={n} head={head[:7]} chars={len(content)}")
print(json.dumps(body, ensure_ascii=False)[:600])