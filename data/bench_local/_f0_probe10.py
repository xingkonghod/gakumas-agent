"""F0 probe 10: HIF master config — audition difficulty / npc group / initial deck."""
import gzip
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/hiro/vendor/gakumas-player/data/master/d31baf6608ee4553091f28446f628cd3ad66ff01/raw"


def load(name):
    raw = gzip.decompress((RAW / f"{name}.yaml.gz").read_bytes())
    return yaml.safe_load(raw)


for name in ("Produce", "ProduceStepAuditionDifficulty", "ProduceExamBattleConfig",
             "ExamInitialDeck", "ProduceInitialDeck", "ExamContestEmbedProduceCard"):
    try:
        data = load(name)
    except Exception as e:  # noqa: BLE001
        print(name, "ERR", e)
        continue
    print("\n" + "=" * 25, name, "=" * 25)
    print(json.dumps(data, ensure_ascii=False, default=str)[:3000])
