"""一次性探针⑥：ProduceGrade / ProduceSetting 评价门槛 + 163783316.9 口径核对。不提交。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gkagent.data.exam_bonus import _load_table, default_db_path  # noqa: E402


def main() -> int:
    db = default_db_path()
    for tname in ("ProduceGrade", "ProduceSetting", "ProduceHighScore"):
        rows = _load_table(str(db), tname)
        print(f"\n== {tname}（{len(rows)} 行）==")
        for x in rows[:20]:
            print(" ", {k: v for k, v in x.items() if not isinstance(v, (list, dict))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())