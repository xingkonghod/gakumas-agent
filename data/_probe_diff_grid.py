"""一次性探针⑤：旧 master ProduceStepAuditionDifficulty 全量结构 ——
produceId/stepType → turn 分布（是否随偶像难度组变化）+ 现有偶像列表。不提交。
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gkagent.data.exam_bonus import _load_table, default_db_path  # noqa: E402


def main() -> int:
    db = default_db_path()
    rows = _load_table(str(db), "ProduceStepAuditionDifficulty")
    cfgs = {str(c.get("id")): c for c in _load_table(str(db), "ProduceExamBattleConfig")}
    idols = _load_table(str(db), "IdolCard")
    print(f"IdolCard {len(idols)} 张；样例 id:", [str(x.get("id")) for x in idols[:12]])
    print("含 kana/hk/kcna 的:", [str(x.get("id")) for x in idols if any(s in str(x.get("id")) for s in ("hkne", "kcna", "kana"))])

    # produceId × stepType → turn 集合
    grid = defaultdict(set)
    for x in rows:
        c = cfgs.get(str(x.get("produceExamBattleConfigId")), {})
        grid[(str(x.get("produceId")), str(x.get("stepType")))].add(int(c.get("turn") or 0))
    print("\n== produceId × stepType → turn 集合 ==")
    for k in sorted(grid):
        print(f"  produceId={k[0]:12s} stepType={k[1]:24s} turns={sorted(grid[k])}")

    # 抽一个偶像看完整难度组
    sample = idols[0]
    diff_id = str(sample.get("produceStepAuditionDifficultyId"))
    print(f"\n== 样例偶像 {sample.get('id')} 难度组 {diff_id} ==")
    for x in sorted([r for r in rows if str(r.get("id")) == diff_id],
                    key=lambda t: (str(t.get("produceId")), str(t.get("stepType")))):
        c = cfgs.get(str(x.get("produceExamBattleConfigId")), {})
        print(f"  produceId={x.get('produceId')} stepType={x.get('stepType')} turn={c.get('turn')} "
              f"Vo/Da/Vi={c.get('vocal')}/{c.get('dance')}/{c.get('visual')} forceEnd={x.get('forceEndScore')}")

    # Produce 相关表名
    import sqlite3
    con = sqlite3.connect(db)
    names = [r[0] for r in con.execute("select distinct table_name from records where table_name like '%Produce%' order by 1")]
    con.close()
    print("\nProduce* 表:", names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())