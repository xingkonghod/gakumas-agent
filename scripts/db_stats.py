"""查看回放库统计。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(r"D:\Games\gakumas-agent\data\replays\produce.sqlite3")


def main() -> None:
    connection = sqlite3.connect(DB)
    cursor = connection.cursor()
    tables = [row[0] for row in cursor.execute("select name from sqlite_master where type='table'")]
    print("tables:", tables)
    for table in tables:
        count = cursor.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"  {table}: {count}")
    if "episodes" in tables:
        for row in cursor.execute("select * from episodes limit 5"):
            print("episode:", row)
    connection.close()


if __name__ == "__main__":
    main()
