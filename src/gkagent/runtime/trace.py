"""C1 每步可复盘：结构化动作轨迹（JSONL）+ 离线复盘格式化。

现有日志已有 ``eng=… fallback=…``（决策可观测性）；这里补上**动作理由**与
**预算/互验结果**，让真机每一步都能回答四个问题（用户规则 4 的延伸）：

1. 这步点了哪里（screen/action/point）？
2. 为什么点（reason：弹窗确认/体力门/引擎决策注记/重试原因…）？
3. 点之前预算下一帧应该是什么（expect_kind/expect_words，hiro 原则 3）？
4. 预算兑现了没有（outcome：confirmed/retap/moved/lost/lesson-*）？

落盘 ``data/step_trace.jsonl``（每步一条，原子 append）；
``scripts/replay_steps.py`` 用它离线复盘任意一局（真机验收留阶段 E）。
纯数据 + 纯函数，不依赖游戏状态。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StepTrace:
    episode: str
    step: int
    screen: str
    action: str
    point: tuple[int, int] | None = None
    reason: str = ""
    engine_note: str = ""
    expect_kind: str = ""
    expect_words: tuple[str, ...] = ()
    outcome: str = ""
    tries: int = 0
    before_sig: str = ""
    after_sig: str = ""
    detail: str = ""
    ts: float = field(default_factory=time.time)


class TraceLog:
    """极简 JSONL 写入器（与 MetricsLog 同约定：只写文件，不依赖游戏状态）。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: Any) -> None:
        payload = asdict(record) if hasattr(record, "__dataclass_fields__") else record
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=list) + "\n")

    def read(self, limit: int | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        rows: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[-limit:] if limit else rows


def format_trace(row: dict) -> str:
    """一条轨迹 → 人类可读复盘行（每个字段缺失时自动省略）。"""
    step = row.get("step", 0)
    text = f"{int(step):03d} [{row.get('screen', '?')}] {row.get('action', '?')}"
    point = row.get("point")
    if point:
        text += f" at ({point[0]},{point[1]})"
    reason = row.get("reason") or ""
    if reason:
        text += f" | 理由: {reason}"
    engine_note = row.get("engine_note") or ""
    if engine_note:
        text += f" | {engine_note}"
    expect_kind = row.get("expect_kind") or ""
    if expect_kind:
        words = "/".join(row.get("expect_words") or ())
        text += f" | 预算: {expect_kind}" + (f"（{words}）" if words else "")
    outcome = row.get("outcome") or ""
    if outcome:
        text += f" → {outcome}"
        tries = int(row.get("tries") or 0)
        if tries:
            text += f"（重试 {tries}）"
    return text


def summarize_traces(rows: list[dict]) -> dict:
    """一局轨迹的复盘摘要：outcome 计数 + 异常步清单（lost/failed/blocked）。"""
    outcomes: dict[str, int] = {}
    anomalies: list[dict] = []
    for row in rows:
        outcome = row.get("outcome") or ""
        if outcome:
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if outcome in ("lost", "failed") or row.get("screen") in ("stuck",):
            anomalies.append(row)
    return {
        "steps": len(rows),
        "outcomes": outcomes,
        "anomalies": anomalies,
        "retaps": sum(1 for row in rows if row.get("outcome") == "retap"),
        "lost": sum(1 for row in rows if row.get("outcome") == "lost"),
    }
