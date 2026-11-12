"""每步/每局指标：JSONL 落盘，用于统计时延、点击回执与准确率。

设计原则：
- 只写文件，不依赖任何游戏状态；
- 每步一条 StepRecord，每局一条 EpisodeRecord；
- 字段保持 JSON 可序列化，方便 jq / pandas 直接读。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StepRecord:
    episode: str
    step: int
    screen: str
    action: str
    capture_ms: float = 0.0
    ocr_ms: float = 0.0
    decide_ms: float = 0.0
    click_ms: float = 0.0
    total_ms: float = 0.0
    changed: bool | None = None
    clicked: bool | None = None
    note: str = ""
    ts: float = field(default_factory=time.time)


@dataclass
class EpisodeRecord:
    episode: str
    started_at: float
    ended_at: float
    steps: int
    done: bool
    progress_markers: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def duration_s(self) -> float:
        return self.ended_at - self.started_at


class MetricsLog:
    """极简 JSONL 写入器。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: Any) -> None:
        payload = asdict(record) if hasattr(record, "__dataclass_fields__") else record
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def read_steps(self, limit: int | None = None) -> list[dict]:
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

    def summary(self) -> dict:
        rows = [row for row in self.read_steps() if "step" in row]
        if not rows:
            return {"steps": 0}
        totals = [row.get("total_ms", 0.0) for row in rows]
        changed = [row for row in rows if row.get("changed") is not None]
        return {
            "steps": len(rows),
            "avg_total_ms": round(sum(totals) / len(totals), 1),
            "p95_total_ms": round(sorted(totals)[max(0, int(len(totals) * 0.95) - 1)], 1),
            "clicked_steps": sum(1 for row in rows if row.get("clicked")),
            "changed_rate": (
                round(sum(1 for row in changed if row.get("changed")) / len(changed), 3)
                if changed
                else None
            ),
        }
