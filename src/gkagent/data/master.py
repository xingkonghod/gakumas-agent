"""本地 Master 数据（从游戏 masterTrans 导出）加载器。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MasterEntry:
    id: str
    name: str
    text: str
    tags: tuple[str, ...]


class MasterData:
    def __init__(self, root: str | Path = "data/master") -> None:
        self.root = Path(root)
        self.produce_cards = self._load("produce_cards")
        self.support_cards = self._load("support_cards")
        self.events = self._load("events")
        self.event_suggestions = self._load("event_suggestions")
        self.items = self._load("items")
        self.drinks = self._load("drinks")
        self.skills = self._load("skills")
        self.idol_cards = self._load("idol_cards")
        self._by_id = {
            entry.id: entry
            for group in (
                self.produce_cards,
                self.support_cards,
                self.events,
                self.event_suggestions,
                self.items,
                self.drinks,
                self.skills,
                self.idol_cards,
            )
            for entry in group
        }

    def _load(self, name: str) -> list[MasterEntry]:
        path = self.root / f"{name}.json"
        if not path.exists():
            return []
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [
            MasterEntry(
                id=row.get("id", ""),
                name=row.get("name", ""),
                text=row.get("text", ""),
                tags=tuple(row.get("tags", [])),
            )
            for row in rows
        ]

    def get(self, entry_id: str) -> MasterEntry | None:
        return self._by_id.get(entry_id)

    def search(self, keyword: str, limit: int = 20) -> list[MasterEntry]:
        found = [e for e in self.produce_cards if keyword in e.name or keyword in e.text]
        found += [e for e in self.support_cards if keyword in e.name or keyword in e.text]
        return found[:limit]

    def counts(self) -> dict[str, int]:
        return {
            "produce_cards": len(self.produce_cards),
            "support_cards": len(self.support_cards),
            "events": len(self.events),
            "event_suggestions": len(self.event_suggestions),
            "items": len(self.items),
            "drinks": len(self.drinks),
            "skills": len(self.skills),
            "idol_cards": len(self.idol_cards),
        }
