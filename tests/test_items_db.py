from __future__ import annotations

from gkagent.data.items_db import ItemLibrary


def test_items_library() -> None:
    lib = ItemLibrary()
    assert len(lib) >= 500
    name = next(iter(lib.by_name))
    info = lib.find(name)
    assert info is not None
    assert info.efficiency(3) >= 0 or info.value < 0
