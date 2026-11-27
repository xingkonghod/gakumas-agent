"""把本地 catalog.sqlite（gakumas-player 解码主数据，F0 同版 d31baf66）转成 GakumasCLI 的 jsonl 表。

GakumasCLI Master.load 要 {"decode_status":"decoded","outer":{...},"decoded":{...}}，
decoded 里枚举是 {"name","number"}（engine/data/exam_enums.json 给编号）；sqlite payload 是
扁平 decoded 行、枚举为字符串。这里做枚举转换 + 包装，写到 GKMSMainWheel/GakumasCLI/ro/master/tables。
探针不提交。
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/hiro/vendor/gakumas-player/data/master/d31baf6608ee4553091f28446f628cd3ad66ff01/catalog.sqlite"
ENUMS = ROOT / "data/GKMSMainWheel/GakumasCLI/engine/data/exam_enums.json"
OUT = ROOT / "data/GKMSMainWheel/GakumasCLI/ro/master/tables"
ENUM_RE = re.compile(r"^[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+$")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ed = json.loads(ENUMS.read_text(encoding="utf-8"))
    print("enum kinds:", len(ed), "sample:", list(ed)[:5])
    enums = {}
    for kind, values in ed.items():
        for number, name in values.items():
            enums.setdefault(norm(name), (name, int(number)))
    # 社区完整枚举表（gakumas_exam/enums.json，Kind_Member → number），补 exam_enums 缺的 kind
    community = json.loads((ROOT / "data/hiro/vendor/gakumas-player/gakumas_exam/enums.json").read_text(encoding="utf-8"))
    added = 0
    for kind, members in community.items():
        for member, number in members.items():
            key = norm(f"{kind}_{member}")
            if key not in enums:
                enums[key] = (f"{kind}_{member}", int(number))
                added += 1
    print("enum names:", len(enums), "(community added", added, ")")

    con = sqlite3.connect(DB)
    tables = [r[0] for r in con.execute("select distinct table_name from records order by 1")]
    OUT.mkdir(parents=True, exist_ok=True)
    converted = unknown = 0
    unknown_samples = []
    per_table = {}

    def conv(x):
        nonlocal converted, unknown
        if isinstance(x, dict):
            out = {}
            for k, v in x.items():
                c = conv(v)
                if c not in (None, "", False, 0, [], {}):
                    out[k] = c
            return out
        if isinstance(x, list):
            return [conv(v) for v in x]
        if isinstance(x, str) and ENUM_RE.match(x):
            e = enums.get(norm(x))
            if e is not None:
                converted += 1
                return None if e[1] == 0 else {"name": e[0], "number": e[1]}
            unknown += 1
            if len(unknown_samples) < 20:
                unknown_samples.append(x)
        return x

    for t in tables:
        rows = []
        for row_id, variant, payload in con.execute(
                "select row_id, variant, payload from records where table_name=? order by ordinal", (t,)):
            p = json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
            d = conv(p)
            outer = {"Id": row_id}
            if t == "ProduceCard":
                outer["UpgradeCount"] = int(p.get("upgradeCount") or 0)
            rows.append({"decode_status": "decoded", "outer": outer, "decoded": d})
        with (OUT / f"{t}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        per_table[t] = len(rows)
    print(f"tables: {len(tables)} → {OUT}")
    print(f"enum converted: {converted}, unknown enum-like strings kept: {unknown}")
    print("unknown samples:", unknown_samples)
    for t in ("ProduceCard", "ProduceExamEffect", "ProduceExamTrigger", "IdolCard",
              "ProduceStepAuditionDifficulty", "ProduceExamBattleConfig", "SupportCard", "ExamSetting"):
        print(f"  {t}: {per_table.get(t)}")
    # 抽查一个 effect 行
    eff = json.loads((OUT / "ProduceExamEffect.jsonl").read_text(encoding="utf-8").splitlines()[0])
    print("effect sample:", json.dumps(eff, ensure_ascii=False)[:400])


if __name__ == "__main__":
    main()
