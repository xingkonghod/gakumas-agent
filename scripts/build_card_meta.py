"""构建 ``data/knowledge/card_meta.json``：卡名 → 偶像固有 / 效果组 / (id, upgrade) + 日文别名。

B10（T5 剩余机制②）：P 道具触发里的「偶像固有技能卡使用时」「X效果的技能卡使用时」
需要每张卡的 **idol-unique 标记** 与 **效果组归属**。这两样 ``card_table.json`` 没有，
但主数据 ``ProduceCard`` 有权威字段：

* ``originIdolCardId`` / ``originCharacterId``：偶像固有卡（含角色固有）的来源标记；
* ``effectGroupIds``：卡面「可见效果组」归属（``effect_group-visible-exam_*-000``），
  与触发 id 里的 ``p_card_search-playing-effect_group-visible-…`` 限定**同一套 id**
  （``EffectGroup`` 表定义组 → 效果类型集合；这里直接存卡→组，结算时按组 id 命中）。

**idol-unique 判据**（与 BSD-3 参考引擎 gakumas-tools ``skill_cards.csv`` 的
``sourceType=="pIdol"`` 交叉验证，只按语义重写、不拷代码）：

    idol_unique = originIdolCardId 非空 or originCharacterId 非空

快照内 342 个参考 pIdol 变体命中 340、**0 误报**（一番星系列是
``originPrimaStellaIdolCardId``，参考里 sourceType=produce，不算偶像固有）；
``微熱ノスタルジー♡``（p_card-02-ido-3_232）快照里没有任何 origin 字段 →
保守不计（宁可少触发，不猜）。参考 csv 在 ``data/dl/``（gitignore），缺失时跳过交叉验证。

数据来源（全部本地只读）：
  * 主数据 ``catalog.sqlite`` 的 ``ProduceCard``（gzip JSON payload，records 通用表）；
  * ``data/knowledge/card_table.json``（中文卡名 → id/upgrade 的连接键）。

用法::

    .venv\\Scripts\\python.exe scripts/build_card_meta.py            # 生成 + 打印统计
    .venv\\Scripts\\python.exe scripts/build_card_meta.py --check    # 只打印统计，不写文件
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import zlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER_DIR = ROOT / "data/hiro/vendor/gakumas-player/data/master"
CARD_TABLE = ROOT / "data" / "knowledge" / "card_table.json"
OUT = ROOT / "data" / "knowledge" / "card_meta.json"
REF_SKILL_CARDS = (
    ROOT / "data/dl/gt/gakumas-tools-master/packages/gakumas-data/csv/skill_cards.csv"
)


def master_db() -> Path | None:
    current = MASTER_DIR / "current.json"
    if current.is_file():
        try:
            return MASTER_DIR / json.loads(current.read_text(encoding="utf-8"))["database"]
        except (KeyError, json.JSONDecodeError, OSError):
            pass
    candidates = sorted(MASTER_DIR.glob("*/catalog.sqlite"))
    return candidates[-1] if candidates else None


def load_table(db: Path, table: str) -> list[dict]:
    con = sqlite3.connect(db)
    try:
        return [
            json.loads(zlib.decompress(payload).decode("utf-8", "replace"))
            for _row_id, _variant, payload in con.execute(
                "select row_id, variant, payload from records where table_name=?", (table,)
            )
        ]
    finally:
        con.close()


def idol_unique(card: dict) -> bool:
    """偶像固有判据（见模块 docstring 的交叉验证口径）。"""
    return bool(card.get("originIdolCardId") or card.get("originCharacterId"))


def cross_check_reference(cards: list[dict]) -> dict | None:
    """与参考引擎 pIdol 集合按 (日文名, upgrade) 交叉验证（参考缺失返回 None）。"""
    if not REF_SKILL_CARDS.is_file():
        return None
    with REF_SKILL_CARDS.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    pidol = {
        (r["name"], 1 if r.get("upgraded") == "TRUE" else 0)
        for r in rows
        if r.get("sourceType") == "pIdol"
    }
    by_key = {(c["name"], int(c.get("upgradeCount") or 0)): c for c in cards}
    in_snapshot = matched = 0
    missing: list[str] = []
    for key in sorted(pidol):
        card = by_key.get(key)
        if card is None:
            continue
        in_snapshot += 1
        if idol_unique(card):
            matched += 1
        else:
            missing.append(f"{key[0]}+{key[1]}({card['id']})")
    ref_all = {
        (r["name"], 1 if r.get("upgraded") == "TRUE" else 0): r.get("sourceType")
        for r in rows
    }
    false_pos = [
        f"{c['name']}+{c.get('upgradeCount')}({c['id']})"
        for c in cards
        if idol_unique(c)
        and ref_all.get((c["name"], int(c.get("upgradeCount") or 0))) not in (None, "pIdol")
    ]
    return {
        "pidol_variants": len(pidol),
        "in_snapshot": in_snapshot,
        "matched": matched,
        "missing": missing,
        "false_positives": false_pos,
    }


def build() -> dict:
    db = master_db()
    if db is None or not db.is_file():
        raise SystemExit(f"主数据 catalog.sqlite 不在 {MASTER_DIR}（先补主数据快照）")
    cards = load_table(db, "ProduceCard")
    by_key = {(c["id"], int(c.get("upgradeCount") or 0)): c for c in cards}

    table = json.loads(CARD_TABLE.read_text(encoding="utf-8"))
    rows = table.get("cards") or {}

    meta: dict[str, dict] = {}
    ja_aliases: dict[str, str] = {}
    unmatched: list[str] = []
    for name, row in rows.items():
        key = (str(row.get("id") or ""), int(row.get("upgrade") or 0))
        card = by_key.get(key)
        if card is None:
            unmatched.append(name)
            continue
        meta[name] = {
            "id": key[0],
            "upgrade": key[1],
            "idol_unique": idol_unique(card),
            "effect_groups": tuple(card.get("effectGroupIds") or ()),
        }
        ja = str(card.get("name") or "")
        if ja and ja != name:
            ja_aliases.setdefault(ja, name)

    groups = Counter(g for m in meta.values() for g in m["effect_groups"])
    stats = {
        "card_table_rows": len(rows),
        "matched": len(meta),
        "unmatched": len(unmatched),
        "unmatched_names": unmatched[:20],
        "idol_unique": sum(1 for m in meta.values() if m["idol_unique"]),
        "idol_unique_bases": len({m["id"] for m in meta.values() if m["idol_unique"]}),
        "effect_group_kinds": len(groups),
        "ja_aliases": len(ja_aliases),
        "master_cards": len(cards),
        "master_db": db.parent.name,
    }
    ref = cross_check_reference(cards)
    if ref is not None:
        stats["reference_cross_check"] = ref
    return {
        "source": "catalog.sqlite ProduceCard (originIdolCardId/originCharacterId/effectGroupIds) + card_table.json",
        "stats": stats,
        "cards": meta,
        "ja_aliases": ja_aliases,
    }


def report(payload: dict) -> None:
    stats = payload["stats"]
    print(f"card_meta: {stats['matched']}/{stats['card_table_rows']} 卡名命中主数据")
    print(f"  偶像固有: {stats['idol_unique']} 变体 / {stats['idol_unique_bases']} base")
    print(f"  效果组: {stats['effect_group_kinds']} 种；日文别名 {stats['ja_aliases']}")
    if stats["unmatched"]:
        print(f"  未命中 {stats['unmatched']}（card_table 有、主数据快照无）: {stats['unmatched_names']}")
    ref = stats.get("reference_cross_check")
    if ref:
        print(
            f"  参考 pIdol 交叉验证: {ref['matched']}/{ref['in_snapshot']} 命中"
            f"（参考 {ref['pidol_variants']} 变体），误报 {len(ref['false_positives'])}"
        )
        if ref["missing"]:
            print(f"  参考有、判据未覆盖（保守不计）: {ref['missing']}")
    else:
        print("  参考 csv 不在 data/dl/（gitignore）→ 跳过交叉验证")


def main(argv: list[str]) -> int:
    # 卡名含 ♡ 等非 GBK 字符：控制台输出统一 UTF-8（替换不可编码字符），避免 Windows 崩。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只打印统计，不写文件")
    args = parser.parse_args(argv)
    payload = build()
    report(payload)
    if not args.check:
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"✅ 已写入 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))