"""卡牌体力费用缓存：界面上的爱心小字 OCR 不稳，就靠"出牌确认帧"学。

出牌是两段式：第一次点卡只是**选中**，此时右上角会显示 ``体力 25 / -6`` 的预览。
这个数字很大、位置固定，识别率远高于卡面爱心里那个 12px 的小字。
把这帧读到的 ``卡名 → 费用`` 存下来，下一局同类卡直接查表。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "card_costs.json"


class CardCosts:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._costs: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        table = raw.get("costs") if isinstance(raw, dict) and "costs" in raw else raw
        if not isinstance(table, dict):
            return
        for name, value in table.items():
            if isinstance(value, int) and 0 <= value <= 99:
                self._costs[str(name)] = value

    def get(self, name: str) -> int | None:
        return self._costs.get(name.strip()) if name else None

    def record(self, name: str, cost: int) -> bool:
        """记录并落盘；返回是否是新知识/有变化。"""
        cleaned = (name or "").strip()
        if not cleaned or not 0 <= cost <= 99:
            return False
        if self._costs.get(cleaned) == cost:
            return False
        self._costs[cleaned] = cost
        self.save()
        return True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"updated": time.strftime("%Y-%m-%d %H:%M:%S"), "costs": self._costs}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )

    def __len__(self) -> int:
        return len(self._costs)
