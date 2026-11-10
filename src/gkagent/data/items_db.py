"""道具/饮料价值库：从本地 master 的 ProduceItem / ProduceDrink 构建。"""

from __future__ import annotations

from gkagent.data.cards_db import CardInfo, score_text
from gkagent.data.master import MasterData


class ItemLibrary:
    def __init__(self, master: MasterData | None = None) -> None:
        self.master = master or MasterData()
        self.by_name: dict[str, CardInfo] = {}
        self.by_id: dict[str, CardInfo] = {}
        for entry in (*self.master.items, *self.master.drinks):
            info = CardInfo(
                id=entry.id,
                name=entry.name,
                text=entry.text,
                value=score_text(entry.text),
            )
            self.by_id[info.id] = info
            if info.name:
                self.by_name.setdefault(info.name, info)

    def find(self, name: str) -> CardInfo | None:
        if not name:
            return None
        if name in self.by_name:
            return self.by_name[name]
        for item_name, info in self.by_name.items():
            if name in item_name or item_name in name:
                return info
        return None

    def __len__(self) -> int:
        return len(self.by_name)
