"""Wiki 接入的离线解析/合并测试（不联网，用内联 HTML 片段）。"""

from __future__ import annotations

from typing import ClassVar

from gkagent.knowledge.wiki import (
    WIKI_SOURCES,
    WikiClient,
    describe_sources,
    extract_buffs,
    merge_buffs,
    parse_sections,
    parse_tables,
    plain_text,
)

FIXTURE = """
<html><body>
<h2>効果一覧</h2>
<p>本ページの概要です。</p>
<h3>プラン：センス</h3>
<h4>集中</h4>
<p>集中が1増加するごとに、パラメータ上昇量を1増加</p>
<h5>集中強化N%</h5>
<p>集中による上昇量を増加。</p>
<h4>好調</h4>
<p>パラメータ上昇量を50％増加。<br />ターン開始時に1減少する。</p>
<h3>共通効果</h3>
<h4>元気</h4>
<p>体力のかわりに消費される値です。</p>
<table><tbody>
<tr><th>段階</th><th>倍率</th></tr>
<tr><td>全力</td><td>3</td></tr>
</tbody></table>
<h4>体力(レッスン)</h4>
<p>スキルカード使用時に消費します。</p>
</body></html>
"""


def test_plain_text_strips_tags_and_entities() -> None:
    assert plain_text("<p>好調&amp;集中<br />次</p>") == "好調&集中 次"


def test_parse_sections_groups_by_heading() -> None:
    sections = parse_sections(FIXTURE)
    headings = [(section.level, section.heading) for section in sections]
    assert (3, "プラン：センス") in headings
    assert (4, "好調") in headings
    hajime = next(section for section in sections if section.heading == "好調")
    assert "50％増加" in hajime.text
    assert "ターン開始時に1減少" in hajime.text


def test_parse_tables_reads_rows() -> None:
    tables = parse_tables(FIXTURE)
    assert tables, "应该解析出表格"
    rows = list(tables[0])
    assert ("段階", "倍率") in rows
    assert ("全力", "3") in rows


def test_extract_buffs_maps_scope_and_variants() -> None:
    buffs = extract_buffs(FIXTURE)
    names = {buff.jp for buff in buffs}
    assert {"集中", "好調", "元気", "体力(レッスン)"} <= names
    kyou = next(buff for buff in buffs if buff.jp == "集中")
    assert kyou.scope == "sense"
    assert "集中強化N%" in kyou.variants
    assert "集中強化N%" in kyou.description
    genki = next(buff for buff in buffs if buff.jp == "元気")
    assert genki.scope == "common"
    assert genki.category() == "defense"


def test_merge_buffs_keeps_curated_values() -> None:
    curated = {
        "buffs": [
            {
                "id": "condition",
                "cn": ["好调"],
                "jp": ["好調"],
                "kind": "buff",
                "scope": "sense",
                "category": "multiplier",
                "duration": "turns",
                "score_flat": 0.0,
                "score_mult": 1.5,
                "play_order": 10,
                "effect": "人工写入的效果",
                "notes": "",
                "cn_note": "不要被覆盖",
            }
        ]
    }
    merged = merge_buffs(curated, extract_buffs(FIXTURE), source_url="https://example/wiki")
    by_jp = {name: entry for entry in merged["buffs"] for name in entry["jp"]}
    condition = by_jp["好調"]
    assert condition["score_mult"] == 1.5  # 人工校订值不覆盖
    assert condition["cn"] == ["好调"]
    assert condition["effect"] == "人工写入的效果"
    assert "jp_desc" in condition  # wiki 描述补进来了
    # 新条目：只有日文名，权重按描述粗估
    assert "元気" in by_jp
    assert by_jp["元気"]["cn"] == []
    # 说明章节被过滤
    assert not any("体力(" in entry["jp"][0] for entry in merged["buffs"])
    meta = merged["wiki_meta"]
    assert meta["total"] == len(merged["buffs"])
    assert meta["added"] >= 1


def test_merge_is_idempotent() -> None:
    merged = merge_buffs({"buffs": []}, extract_buffs(FIXTURE), source_url="u")
    count = len(merged["buffs"])
    again = merge_buffs(merged, extract_buffs(FIXTURE), source_url="u")
    assert len(again["buffs"]) == count
    assert set(again["wiki_meta"]) >= {"added", "updated", "total"}


def test_sources_are_https_and_described() -> None:
    for key in ("buffs", "mechanics", "hajime"):
        assert WIKI_SOURCES[key]["url"].startswith("https://seesaawiki.jp/")
    described = describe_sources()
    assert set(described) == set(WIKI_SOURCES)
    assert all(item["title"] and item["use"] for item in described.values())


def test_fetch_uses_cache(tmp_path) -> None:
    """第二次 fetch 必须命中磁盘缓存，不再打开网络。"""
    calls = {"n": 0}

    class FakeResponse:
        headers: ClassVar[dict[str, str]] = {"Content-Type": "text/html; charset=euc-jp"}

        def read(self) -> bytes:
            return "<html><body><h3>プラン：センス</h3></body></html>".encode("euc-jp")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def opener(_request, timeout=20):
        calls["n"] += 1
        return FakeResponse()

    client = WikiClient(tmp_path, opener=opener)
    first = client.fetch("buffs")
    assert first.cached is False
    assert "プラン：センス" in first.html
    second = client.fetch("buffs")
    assert second.cached is True
    assert calls["n"] == 1
