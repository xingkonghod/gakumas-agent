"""一次性构建脚本：用生产训练代码预计算卡表 (id,upgrade) → 23 维静态画像。

r13 学生网的动作特征前 23 维 = leaf_mlp._card_profile(CardSpec)，训练时 CardSpec
由 scripts/sim_produce._effect_fields + _spec_from_row 建（once 由 eval_expectimax
._with_once 按主数据卡面文本标）。这里直接调这条生产链，保证投稿画像与训练逐位一致，
避免手抄 _effect_fields 出偏差。输出写入投稿目录 card_profiles.json（数据文件，随投稿提交）。

    .venv\\Scripts\\python.exe data\\_f2_build_card_profiles.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sim_produce as sp  # noqa: E402
from eval_expectimax import _master_texts, _with_once  # noqa: E402
from gkagent.sim.leaf_mlp import _card_profile  # noqa: E402
from gkagent.sim.policy_mlp import ACTION_FEATURE_NAMES  # noqa: E402

PROFILE_NAMES = tuple(n[len("card_"):] for n in ACTION_FEATURE_NAMES[:23])
OUT = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ei-r13" / "card_profiles.json"


def main() -> None:
    table = json.loads((ROOT / "data" / "knowledge" / "card_table.json").read_text(encoding="utf-8"))["cards"]
    texts = _master_texts()
    cards: dict[str, dict] = {}
    once_count = 0
    for name, row in table.items():
        cid = str(row.get("id") or "")
        if not cid:
            continue
        upgrade = int(row.get("upgrade") or 0)
        cost = int(row.get("cost") or 0)
        fields = sp._effect_fields(row)
        spec = sp._spec_from_row(sp.CardRow(name, cost, *fields))
        spec = _with_once(spec, texts)
        profile = _card_profile(spec)
        assert len(profile) == 23
        cards[f"{cid}|{upgrade}"] = {"name": name, "p": [float(v) for v in profile]}
        once_count += int(spec.once)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "gkagent.ei_r13_card_profiles.v1",
        "source": "data/knowledge/card_table.json via scripts/sim_produce._effect_fields + "
                  "_spec_from_row + eval_expectimax._with_once (master text once flags)",
        "profile_names": list(PROFILE_NAMES),
        "cards": cards,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB): {len(cards)} (id,u) rows, once={once_count}")


if __name__ == "__main__":
    main()