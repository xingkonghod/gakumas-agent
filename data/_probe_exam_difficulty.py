"""一次性探针④：旧 master 考试难度表 —— 氷渡香名江 REGULAR/PRO 期中/期末回合数与基准，
+ produce id 114 是什么。判断 ep-t31 期末 12 回合 = PRO 还是 v3.6.1 改了 REGULAR。不提交。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gkagent.data.exam_bonus import ExamBonusResolver, _load_table, default_db_path  # noqa: E402


def main() -> int:
    db = default_db_path()
    print("master:", db)
    r = ExamBonusResolver(db)

    idols = _load_table(str(db), "IdolCard")
    hk = [x for x in idols if "hkne" in str(x.get("id"))]
    print(f"\nIdolCard 含 hkne 的卡（{len(hk)}）:")
    for x in hk:
        print(f"  {x.get('id')} name={x.get('name')} diffId={x.get('produceStepAuditionDifficultyId')}")
    idol = r._idol("i_card-hkne-3-000") if any(str(x.get('id')) == 'i_card-hkne-3-000' for x in idols) else hk[-1]
    diff_id = str(idol.get("produceStepAuditionDifficultyId"))
    print(f"\n选用 {idol.get('id')} → difficultyId={diff_id}")
    print("  idol 关键字段:", {k: idol.get(k) for k in ("id", "name", "produceStepAuditionDifficultyId", "parameterBaseLine") if k in idol})

    rows = _load_table(str(db), "ProduceStepAuditionDifficulty")
    print(f"\nProduceStepAuditionDifficulty 共 {len(rows)} 行；produceId 分布:",
          sorted({str(x.get('produceId')) for x in rows}))
    mine = [x for x in rows if str(x.get("id")) == diff_id]
    print(f"\n== 氷渡香名江难度组 {diff_id}（{len(mine)} 行）==")
    cfgs = {str(c.get("id")): c for c in _load_table(str(db), "ProduceExamBattleConfig")}
    for x in sorted(mine, key=lambda t: (str(t.get("produceId")), str(t.get("stepType")))):
        cid = str(x.get("produceExamBattleConfigId"))
        c = cfgs.get(cid, {})
        print(f"  produceId={x.get('produceId')} stepType={x.get('stepType')} "
              f"config={cid} turn={c.get('turn')} "
              f"Vo/Da/Vi基准={c.get('vocal')}/{c.get('dance')}/{c.get('visual')} "
              f"forceEndScore={x.get('forceEndScore')} rankThreshold={x.get('rankThreshold')}")

    # produce 表：114 是什么
    for tname in ("Produce", "ProduceScenario", "ProducePlan"):
        try:
            prows = _load_table(str(db), tname)
        except Exception:
            continue
        if not prows:
            continue
        print(f"\n== {tname}（{len(prows)} 行）==")
        for p in prows[:30]:
            pid = p.get("id")
            print(f"  id={pid} name={p.get('name')} type={p.get('type')} "
                  f"difficulty={p.get('difficulty')} keys={list(p.keys())[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())