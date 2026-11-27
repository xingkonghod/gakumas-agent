import json, re
from pathlib import Path
OUT = Path(r'D:\Games\gakumas-agent\data\GKMSMainWheel\GakumasCLI\ro\master\tables')
ENUM_RE = re.compile(r"^[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+$")
# 检查考试相关表里残留的字符串枚举
exam_tables = ["ProduceCard", "ProduceExamEffect", "ProduceExamTrigger", "ProduceExamStatusEnchant",
               "ProduceCardCustomize", "ProduceCardGrowEffect", "ProduceItem", "ProduceItemEffect",
               "ProduceDrink", "ProduceDrinkEffect", "ProduceCardSearch", "ProduceCardStatusEnchant",
               "IdolCard", "SupportCard", "ProduceStepAuditionDifficulty", "ProduceExamBattleConfig",
               "ProduceExamBattleNpcGroup", "ProduceExamBattleScoreConfig", "ExamInitialDeck",
               "ProduceInitialDeck", "ProduceExamGimmickEffectGroup", "MemoryAbility", "ExamSetting", "Setting"]
leftover = {}
def walk(x, path, tid):
    if isinstance(x, dict):
        if set(x) == {"name", "number"}:
            return
        for k, v in x.items():
            walk(v, path + "." + k, tid)
    elif isinstance(x, list):
        for v in x:
            walk(v, path + "[]", tid)
    elif isinstance(x, str) and ENUM_RE.match(x):
        leftover.setdefault((tid, path), set()).add(x)
for t in exam_tables:
    p = OUT / f"{t}.jsonl"
    if not p.exists():
        print("MISSING TABLE:", t); continue
    for line in p.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        walk(row["decoded"], "", t)
for (t, path), vals in sorted(leftover.items()):
    print(f"{t}{path}: {sorted(vals)[:4]}")
print("total leftover paths:", len(leftover))
# ProduceCard 样本
c = json.loads((OUT / "ProduceCard.jsonl").read_text(encoding="utf-8").splitlines()[100])
print("card sample:", json.dumps(c["decoded"], ensure_ascii=False)[:500])
