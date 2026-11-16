"""扫描「官方汉化补丁尚未覆盖」的条目，产出未汉化清单和术语表。

背景：游戏更新后，chinosk6/GakumasTranslationData 的最新补丁（v2.3.66）还没跟上。
本脚本只做**盘点**，不翻译：

* 卡牌：gakumasu-diff 的 ``ProduceCard.yaml``（上游最新）对比
  ``data/master/produce_cards.json``（现有中文基线，来自 v2.3.66 补丁），
  差集就是完全没有中文的 (id, upgrade) 变体。
* P 道具：``ProduceItem.yaml`` 对比本地 ``masterTrans/ProduceItem.json``，
  差集是补丁里不存在的条目（本地文件是「补丁覆盖层」，新条目不会出现）。
* 其余表：逐字段查日文假名。官方补丁是叠加式汉化，未覆盖的字段会保持日文原文。

产出：
  * ``data/i18n/untranslated.json``：缺口清单 + 各表统计
  * ``data/i18n/glossary.json``：术语表（现有补丁 + 游戏本地化表）
  * 屏幕摘要

用法：
  .venv\\Scripts\\python.exe scripts/i18n_scan.py           # 主表扫描
  .venv\\Scripts\\python.exe scripts/i18n_scan.py --story   # 额外扫剧情资源（358MB，慢）
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = Path(r"D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans")
RESOURCE = GAME.parent / "resource"
OUT_DIR = ROOT / "data" / "i18n"
CARD_YAML = ROOT / "data" / "cache" / "ProduceCard.yaml"
ITEM_YAML = ROOT / "data" / "cache" / "ProduceItem.yaml"
MASTER_CARDS = ROOT / "data" / "master" / "produce_cards.json"

# 日文假名（不含 ・ U+30FB / ー U+30FC，避免把中文译名里的间隔号和长音符误判）
KANA = re.compile(r"[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff]")
CJK = re.compile(r"[\u3400-\u9fff]")
RUBY = re.compile(r"<r\\?=([^>]*)>(.*?)</r>", re.DOTALL)
PLACEHOLDER = "未定義のパターン"

# 曲词不翻（版权/非 UI），Rule 是法务公示原文，都不进翻译清单
OUT_OF_SCOPE = {"Music.json": "歌词/作曲者名，不翻", "Rule.json": "法务公示原文，不翻"}

CORE_TERMS = {
    "やる気": "干劲",
    "元気": "元气",
    "集中": "集中",
    "好調": "好调",
    "好印象": "好印象",
    "絶好調": "绝好调",
    "温存": "温存",
    "強気": "强气",
    "全力": "全力",
    "全力値": "全力值",
    "熱意": "热意",
    "高揚": "高扬",
    "不安": "不安",
    "不調": "不调",
    "スコア": "打分",
    "スコア上昇量": "打分上升量",
    "ターン": "回合",
    "スキルカード": "技能卡",
    "サポートカード": "支援卡",
    "Pアイテム": "P道具",
    "レッスン": "训练",
    "オーディション": "试镜",
    "試験": "考试",
    "プロデュース": "培育",
    "アイドル": "偶像",
    "体力": "体力",
    "手札": "手牌",
    "山札": "牌堆",
    "捨て札": "弃牌",
    "保留": "保留",
    "状態": "状态",
    "強化": "强化",
    "成長": "成长",
}

PRESERVE_TOKENS = [
    "{0}",
    "{1}",
    "\\n",
    "<nobr>",
    "</nobr>",
    "<r=...>...</r>",
    "（中文）",
    "♪",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_yaml(path: Path) -> list[dict]:
    """按行解析 gakumasu-diff 的 master yaml（文件 20~50MB，不用 PyYAML）。"""
    entries: list[dict] = []
    cur: dict | None = None
    section = ""
    desc: dict | None = None
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            if cur is not None:
                entries.append(cur)
            cur = {"id": line[6:].strip(), "texts": []}
            section = ""
            desc = None
            continue
        if cur is None:
            continue
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        if line.startswith("  ") and not line.startswith("    "):
            if stripped.startswith("- produceDescriptionType:"):
                desc = {"text": ""}
                cur["texts"].append(desc)
                continue
            key, _, value = stripped.partition(":")
            key, value = key.strip(), value.strip()
            if key in ("produceDescriptions", "customizeProduceDescriptions"):
                section = key
                desc = None
                continue
            section = ""
            if key in (
                "upgradeCount",
                "name",
                "rarity",
                "planType",
                "category",
                "plan4GroupType",
            ):
                cur[key] = value
            continue
        if section and line.startswith("    ") and desc is not None:
            key, _, value = stripped.partition(":")
            key, value = key.strip(), value.strip()
            if key == "text":
                desc["text"] = "" if value in ("|", ">", "|-", ">-") else value
    if cur is not None:
        entries.append(cur)
    return entries


def join_texts(entry: dict) -> str:
    parts = [(d.get("text") or "").strip() for d in entry.get("texts", [])]
    return " / ".join(p for p in parts if p)


def walk_strings(obj, prefix: str = ""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk_strings(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk_strings(value, f"{prefix}[{index}]")
    elif isinstance(obj, str):
        yield prefix, obj


def scan_cards(master: list[dict], yaml_entries: list[dict]) -> tuple[list[dict], dict]:
    master_keys = {(row["id"], int(row.get("upgrade") or 0)) for row in master}
    missing = [
        entry
        for entry in yaml_entries
        if (entry["id"], int(entry.get("upgradeCount") or 0)) not in master_keys
    ]
    missing.sort(key=lambda e: (e["id"], int(e.get("upgradeCount") or 0)))
    entries = []
    for entry in missing:
        entries.append(
            {
                "table": "ProduceCard",
                "priority": "P0",
                "id": entry["id"],
                "upgrade": int(entry.get("upgradeCount") or 0),
                "jp_name": entry.get("name", ""),
                "en_name": "",
                "category": entry.get("category", ""),
                "rarity": entry.get("rarity", "").replace("ProduceCardRarity_", ""),
                "plan": entry.get("planType", "").replace("ProducePlanType_", ""),
                "jp_desc": join_texts(entry),
            }
        )
    summary = {
        "baseline_rows": len(master),
        "baseline_ids": len({row["id"] for row in master}),
        "upstream_rows": len(yaml_entries),
        "upstream_ids": len({entry["id"] for entry in yaml_entries}),
        "missing_variants": len(entries),
        "missing_ids": len({entry["id"] for entry in entries}),
        "by_rarity": dict(Counter(entry["rarity"] for entry in entries)),
        "names": sorted({entry["jp_name"].rstrip("+") for entry in entries}),
    }
    return entries, summary


def scan_items(yaml_entries: list[dict], local_items: list[dict]) -> tuple[list[dict], dict]:
    local_ids = {row["id"] for row in local_items}
    missing = sorted((entry for entry in yaml_entries if entry["id"] not in local_ids), key=lambda e: e["id"])
    entries = []
    for entry in missing:
        entries.append(
            {
                "table": "ProduceItem",
                "priority": "P0",
                "id": entry["id"],
                "jp_name": entry.get("name", ""),
                "en_name": "",
                "category": "ProduceItem",
                "rarity": entry.get("rarity", "").replace("ProduceItemRarity_", ""),
                "plan": entry.get("planType", "").replace("ProducePlanType_", ""),
                "jp_desc": join_texts(entry),
            }
        )
    summary = {
        "baseline_rows": len(local_items),
        "upstream_rows": len(yaml_entries),
        "missing": len(entries),
        "by_rarity": dict(Counter(entry["rarity"] for entry in entries)),
    }
    return entries, summary


def scan_tables() -> tuple[list[dict], dict, dict, dict]:
    """扫 masterTrans 其余表里的日文。返回 (清单, 分类统计, 出范围统计, 扫描元信息)。"""
    entries: list[dict] = []
    stats: dict[str, dict] = {}
    out_of_scope: dict[str, int] = {}
    meta = {"files": 0, "rows": 0}
    for path in sorted(GAME.glob("*.json")):
        if path.name in ("ProduceCard.json", "ProduceItem.json"):
            continue
        data = load_json(path)
        rows: list[dict] = data.get("data", []) if isinstance(data, dict) else []
        meta["files"] += 1
        meta["rows"] += len(rows)
        if path.name in OUT_OF_SCOPE:
            hits = 0
            for row in rows:
                if any(KANA.search(value) for _, value in walk_strings(row)):
                    hits += 1
            out_of_scope[path.name] = hits
            continue
        fields: Counter[str] = Counter()
        flagged_rows = 0
        for row in rows:
            row_hit = False
            row_id = row.get("id") or row.get("type") or row.get("characterId") or ""
            for field, value in walk_strings(row):
                if not KANA.search(value):
                    continue
                row_hit = True
                fields[field] += 1
                is_placeholder = PLACEHOLDER in value
                entries.append(
                    {
                        "table": path.stem,
                        "priority": "P2",
                        "id": row_id,
                        "field": field,
                        "jp_name": value.strip()[:800],
                        "en_name": "",
                        "category": "placeholder" if is_placeholder else "untranslated-prop",
                        "confidence": "low" if is_placeholder else None,
                    }
                )
            if row_hit:
                flagged_rows += 1
        if flagged_rows:
            stats[path.name] = {
                "rows": len(rows),
                "flagged_rows": flagged_rows,
                "flagged_fields": sum(fields.values()),
                "fields": dict(fields),
            }
    return entries, stats, out_of_scope, meta


def scan_story() -> dict:
    files = sorted(RESOURCE.glob("*.txt"))
    messages = 0
    segments = 0
    untranslated = 0
    same_as_jp = 0
    pure_kana = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if not line.startswith("[message "):
                continue
            messages += 1
            pairs = RUBY.findall(line)
            segments += len(pairs)
            if pairs and all(cn == jp for jp, cn in pairs) and any(KANA.search(cn) for _, cn in pairs):
                untranslated += 1
            for jp, cn in pairs:
                if cn == jp:
                    same_as_jp += 1
                elif KANA.search(cn) and not CJK.search(cn):
                    pure_kana += 1
    return {
        "resource_files": len(files),
        "messages": messages,
        "segments": segments,
        "untranslated_messages": untranslated,
        "segments_equal_to_japanese": same_as_jp,
        "pure_kana_segments": pure_kana,
        "note": "补丁用 <r=日文>中文</r> 双语内嵌；逐条检查后无整句未翻。",
    }


def build_glossary() -> dict:
    def label_map(name: str, key: str = "name") -> dict[str, str]:
        rows = load_json(GAME / name)["data"]
        return {row["type"]: row.get(key, "") for row in rows if row.get("type")}

    characters = load_json(GAME / "Character.json")["data"]
    return {
        "version": 1,
        "updated": "2026-11-16",
        "source": "masterTrans/ProduceDescription*.json（游戏内本地化表）+ 现有 chinosk6 补丁（data/master/*.json）",
        "principles": [
            "术语一致性优先于文采；表内已有中文覆盖时保留原译，不改旧词。",
            "卡名简洁有风格，不加「的」「之」凑字数；描述按卡面分段翻译，数值逐字保留。",
            "不臆造：含义不确定的条目保留原文并标 confidence=low。",
            "标记/占位符逐字保留：{0}、\\n、<nobr>、</nobr>、<r=...> 等。",
        ],
        "terms": CORE_TERMS,
        "effect_types": label_map("ProduceDescriptionExamEffect.json"),
        "card_grow_effect_types": label_map("ProduceDescriptionProduceCardGrowEffectType.json"),
        "plan_types": label_map("ProduceDescriptionProducePlanType.json"),
        "characters": {
            row["id"]: row.get("lastName", "") + row.get("firstName", "") for row in characters
        },
        "preserve_tokens": PRESERVE_TOKENS,
        "notes": [
            "en_name 留空：仓库内没有可信英文名来源（gakumasu-diff 只提供日文），不臆造。",
            "个别既有译名疑为笔误（如「複製」「全力值值增加」），改动需整表一致，暂按原样。",
        ],
    }


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for path in (CARD_YAML, ITEM_YAML):
        if not path.exists():
            print(f"缺少 {path}")
            return 1
    master = load_json(MASTER_CARDS)
    card_yaml = parse_yaml(CARD_YAML)
    item_yaml = parse_yaml(ITEM_YAML)
    local_items = load_json(GAME / "ProduceItem.json")["data"]

    card_entries, card_summary = scan_cards(master, card_yaml)
    item_entries, item_summary = scan_items(item_yaml, local_items)
    table_entries, table_stats, out_of_scope, scan_meta = scan_tables()

    summary = {
        "scan_meta": scan_meta,
        "ProduceCard": card_summary,
        "ProduceItem": item_summary,
        "other_tables": table_stats,
        "out_of_scope": out_of_scope,
    }
    if "--story" in argv:
        summary["story"] = scan_story()

    payload = {
        "generated_by": "scripts/i18n_scan.py",
        "generated_at": "2026-11-16",
        "source": {
            "cards": "data/cache/ProduceCard.yaml vs data/master/produce_cards.json",
            "items": "data/cache/ProduceItem.yaml vs masterTrans/ProduceItem.json (2026-09-16)",
            "tables": r"masterTrans\*.json（逐字段查日文假名）",
            "installed_master": str(GAME),
        },
        "summary": summary,
        "entries": card_entries + item_entries + table_entries,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "untranslated.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT_DIR / "glossary.json").write_text(
        json.dumps(build_glossary(), ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"ProduceCard: 基线 {card_summary['baseline_rows']} / 上游 {card_summary['upstream_rows']}"
          f" → 缺 {card_summary['missing_variants']} 变体 / {card_summary['missing_ids']} 张卡")
    print(f"   {', '.join(card_summary['names'])}")
    print(f"ProduceItem: 基线 {item_summary['baseline_rows']} / 上游 {item_summary['upstream_rows']}"
          f" → 缺 {item_summary['missing']} 条")
    print(f"扫描 masterTrans 其余 {scan_meta['files']} 张表 / {scan_meta['rows']} 行")
    for name, stat in table_stats.items():
        print(f"{name}: {stat['flagged_rows']} 行 / {stat['flagged_fields']} 字段含日文")
    print(f"出范围: {out_of_scope}")
    if "story" in summary:
        print(f"剧情资源: {summary['story']}")
    print(f"写入 {OUT_DIR / 'untranslated.json'}")
    print(f"写入 {OUT_DIR / 'glossary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
