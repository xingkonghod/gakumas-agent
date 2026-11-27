"""P1-1 探针：master 附魔定义 / のんびり卡 / 全力相关（一次性，不提交）。"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
DB = ROOT / "data/hiro/vendor/gakumas-player/data/master/d31baf6608ee4553091f28446f628cd3ad66ff01/catalog.sqlite"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("enchant-like tables:", [t for t in tables if "enchant" in t.lower()])
print("stance-like tables:", [t for t in tables if "stance" in t.lower()])

for t in tables:
    if "enchant" in t.lower():
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
        print(f"\n== {t} cols: {cols}")
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print("rows:", n)
        for row in cur.execute(f"SELECT * FROM {t} LIMIT 3"):
            print(dict(row))
        # のんびり卡的附魔
        for row in cur.execute(
            f"SELECT * FROM {t} WHERE id LIKE '%p_card-03-ido-1_054%' OR id LIKE '%p_card-03-ido-3_077%' OR id LIKE '%p_card-03-ido-1_055%' OR id LIKE '%p_card-03-ido-3_078%'"
        ):
            print("HIT:", dict(row))
con.close()
