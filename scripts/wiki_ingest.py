"""把 学マスwiki 抓成本地知识库。

用法（在项目根目录）：

    python scripts/wiki_ingest.py            # 命中缓存就用缓存（TTL 24h）
    python scripts/wiki_ingest.py --refresh  # 强制重新抓
    python scripts/wiki_ingest.py --dry-run  # 只打印统计，不写文件

产物：

- ``data/cache/wiki/<key>.html``   原始页面（已按页面 charset 解码成 UTF-8）
- ``data/cache/wiki/<key>.json``   抓取元数据（url/charset/fetched_at）
- ``data/knowledge/buffs.json``    合并日文条目（人工中文名不覆盖）
- ``data/knowledge/wiki/<key>.txt`` 页面正文（人工/LLM 复盘用）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.knowledge.wiki import (  # noqa: E402
    WIKI_SOURCES,
    WikiClient,
    describe_sources,
    extract_buffs,
    merge_buffs,
    parse_sections,
)

KNOWLEDGE = ROOT / "data" / "knowledge"
WIKI_OUT = KNOWLEDGE / "wiki"


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    refresh = "--refresh" in argv
    dry_run = "--dry-run" in argv
    client = WikiClient()
    WIKI_OUT.mkdir(parents=True, exist_ok=True)

    results = {}
    for key, source in WIKI_SOURCES.items():
        try:
            fetched = client.fetch(key, refresh=refresh)
        except Exception as exc:  # noqa: BLE001 - 抓不到就报错继续下一个源
            print(f"[wiki] {key} 抓取失败: {type(exc).__name__}: {exc}")
            continue
        age = "cache" if fetched.cached else "network"
        print(f"[wiki] {key} {source['title']} {len(fetched.html)} chars ({age})")
        results[key] = fetched
        if not dry_run:
            sections = parse_sections(fetched.html)
            body = "\n".join(
                f"{'#' * section.level} {section.heading}\n{section.text}"
                for section in sections
                if section.heading
            )
            (WIKI_OUT / f"{key}.txt").write_text(body, encoding="utf-8")

    buffs_page = results.get("buffs")
    if buffs_page is not None:
        wiki_buffs = extract_buffs(buffs_page.html)
        print(f"[wiki] 抽出 buff 条目 {len(wiki_buffs)} 个")
        path = KNOWLEDGE / "buffs.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"buffs": []}
        data = merge_buffs(data, wiki_buffs, source_url=WIKI_SOURCES["buffs"]["url"])
        meta = data.get("wiki_meta", {})
        print(
            f"[wiki] buffs.json: 新增 {meta.get('added')} / 更新 {meta.get('updated')} "
            f"/ 合计 {meta.get('total')}"
        )
        if not dry_run:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    if not dry_run:
        (WIKI_OUT / "sources.json").write_text(
            json.dumps(describe_sources(), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        snapshot = KNOWLEDGE / "wiki_snapshot.json"
        snapshot.write_text(
            json.dumps(
                {
                    "synced": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
                    "pages": {
                        key: {
                            "title": WIKI_SOURCES[key]["title"],
                            "chars": len(result.html),
                            "cached": result.cached,
                        }
                        for key, result in results.items()
                    },
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    print("[wiki] 完成" + ("（dry-run，未写文件）" if dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
