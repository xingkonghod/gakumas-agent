"""Wiki 接入：抓 学マスwiki → 本地结构化缓存。

设计取舍：

- **离线吸收，不在线查询**。出牌是 2-7 秒一步的实时循环，不能等网页；
  抓一次落盘，之后全部读本地缓存（TTL 24h，``--refresh`` 强制刷新）。
- **编码**：seesaawiki 是 EUC-JP，按响应头 ``charset`` 解码，不要硬写 UTF-8。
- **只取结构**：``<h3>`` = 分类（プラン：センス/ロジック/アノマリー/共通効果），
  ``<h4>`` = buff 名，紧跟的正文 = 效果说明；表格单独解析成行列。
- 中文 UI 名（好调/集中/干劲…）是人工维护的 ``buffs.json`` 的职责，
  wiki 只提供**日文原名 + 说明 + 出处**，合并时按日文名对齐，不覆盖人工值。
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CACHE = Path(__file__).resolve().parents[3] / "data" / "cache" / "wiki"

# key -> (url, 本页标题, 说明)
WIKI_SOURCES: dict[str, dict[str, str]] = {
    "buffs": {
        "url": "https://seesaawiki.jp/gakumasu/d/"
        "%b8%fa%b2%cc%a1%f5%b6%af%b2%bd/%c4%e3%b2%bc%be%f5%c2%d6%28%a5%d0%a5%d5/%a5%c7%a5%d0%a5%d5%29%b0%ec%cd%f7",
        "title": "効果＆強化/低下状態(バフ/デバフ)一覧",
        "use": "buff 词典（名称/效果/倍率）",
    },
    "mechanics": {
        "url": "https://seesaawiki.jp/gakumasu/dp/"
        "%a5%ec%a5%c3%a5%b9%a5%f3%a1%a6%bb%ee%b8%b3%be%dc%ba%d9",
        "title": "レッスン・試験詳細",
        "use": "计算式/发动顺序",
    },
    "hajime": {
        "url": "https://seesaawiki.jp/gakumasu/dp/"
        "%c4%ea%b4%fc%b8%f8%b1%e9%a1%d8%bd%e9%a1%d9",
        "title": "定期公演『初』",
        "use": "考试回合分配/合格线",
    },
    # leafierlemon 的育成模拟器是 UTF-8 静态页；表格是 div.table/div.tr，
    # 用 parse_schedule_rows() 读逐周行动和「上昇量ベース」。
    "schedule": {
        "url": "https://leafierlemon.github.io/idolmaster_gakuen_score_calculator/simulator.html",
        "title": "学マス育成シミュレーター（プロ）",
        "use": "逐周排期/课程基础值（CLEAR/PERFECT 的公开来源）",
        "charset": "utf-8",
    },
}

USER_AGENT = "Mozilla/5.0 (compatible; gde-wiki-ingest/1.0)"


def _response_charset(headers, default: str = "euc-jp") -> str:
    """响应头 → charset。兼容 http.client.HTTPMessage 和测试用的 dict。"""
    getter = getattr(headers, "get_content_charset", None)
    if callable(getter):
        charset = getter()
        if charset:
            return str(charset)
    content_type = ""
    if hasattr(headers, "get"):
        content_type = str(headers.get("Content-Type") or "")
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else default


@dataclass(frozen=True)
class Section:
    level: int
    heading: str
    text: str
    tables: tuple[tuple[tuple[str, ...], ...], ...] = ()


@dataclass
class FetchResult:
    html: str
    cached: bool
    fetched_at: float


class WikiClient:
    """带磁盘缓存的 wiki 抓取器。"""

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        ttl_hours: float = 24.0,
        opener=None,
        timeout: float = 20.0,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE
        self.ttl_s = ttl_hours * 3600
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    # ------------------------------------------------------------------ 抓取
    def fetch(self, key: str, *, refresh: bool = False) -> FetchResult:
        source = WIKI_SOURCES.get(key)
        if source is None:
            raise KeyError(f"未知 wiki 源: {key}")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        html_path = self.cache_dir / f"{key}.html"
        meta_path = self.cache_dir / f"{key}.json"
        if not refresh and html_path.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
            age = time.time() - float(meta.get("fetched_at") or 0)
            if 0 <= age < self.ttl_s:
                return FetchResult(
                    html=html_path.read_text(encoding="utf-8"),
                    cached=True,
                    fetched_at=float(meta.get("fetched_at") or 0),
                )
        request = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
        with self.opener(request, timeout=self.timeout) as response:
            raw = response.read()
            charset = _response_charset(response.headers, source.get("charset", "euc-jp"))
        text = raw.decode(charset, "replace")
        html_path.write_text(text, encoding="utf-8")
        meta = {
            "url": source["url"],
            "charset": charset,
            "bytes": len(raw),
            "fetched_at": time.time(),
            "fetched_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return FetchResult(html=text, cached=False, fetched_at=meta["fetched_at"])

    def html(self, key: str, *, refresh: bool = False) -> str:
        return self.fetch(key, refresh=refresh).html


# ---------------------------------------------------------------------- 解析
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_BLOCK_END = re.compile(r"</(p|div|li|tr|h[1-6]|dt|dd|table)>", re.IGNORECASE)
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_HEADING = re.compile(r"<h([2-6])[^>]*>(.*?)</h\1>", re.DOTALL | re.IGNORECASE)


def clean_body(html: str) -> str:
    """去掉注释/脚本，只留 body 正文。"""
    text = _COMMENT.sub("", html)
    text = _SCRIPT.sub("", text)
    start = text.lower().find("<body")
    return text[start:] if start >= 0 else text


def plain_text(fragment: str) -> str:
    """HTML 片段 → 单行纯文本（``<br>`` 变空格，压缩空白）。"""
    text = _BR.sub(" ", fragment)
    text = _BLOCK_END.sub(" ", text)
    text = _TAG.sub("", text)
    text = html_lib.unescape(text)
    text = text.replace("\u3000", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def content_html(html: str) -> str:
    """只留正文：seesaawiki 在正文后面还有 ``Menu`` 站点导航（同为 h2）。

    正文 = 第一个 h2（页面标题）到第二个 h2 之间；单页模板没有 h2 时退回整个 body。
    """
    body = clean_body(html)
    headings = list(re.finditer(r"<h2\b[^>]*>.*?</h2>", body, re.DOTALL | re.IGNORECASE))
    if len(headings) >= 2:
        return body[headings[0].start() : headings[1].start()]
    return body


def parse_sections(html: str) -> list[Section]:
    """按标题切段：返回每个标题下的正文和表格。

    ``<h3>`` 是分类，``<h4>`` 是条目名；每段正文取到下一个标题为止。
    """
    body = content_html(html)
    matches = list(_HEADING.finditer(body))
    sections: list[Section] = []
    for index, match in enumerate(matches):
        level = int(match.group(1))
        heading = plain_text(match.group(2))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        chunk = body[match.end() : end]
        sections.append(
            Section(
                level=level,
                heading=heading,
                text=plain_text(chunk),
                tables=tuple(parse_tables(chunk)),
            )
        )
    return sections


def parse_tables(fragment: str) -> list[tuple[tuple[str, ...], ...]]:
    """极简表格解析：``<table>`` → 行 → 单元格纯文本。够读 wiki 的对照表。"""
    tables: list[tuple[tuple[str, ...], ...]] = []
    for table_html in re.findall(r"<table\b.*?</table>", fragment, re.DOTALL | re.IGNORECASE):
        rows: list[tuple[str, ...]] = []
        for row_html in re.findall(r"<tr\b.*?</tr>", table_html, re.DOTALL | re.IGNORECASE):
            cells = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row_html, re.DOTALL | re.IGNORECASE)
            if cells:
                rows.append(tuple(plain_text(cell) for cell in cells))
        if rows:
            tables.append(tuple(rows))
    return tables


def _schedule_action(label: str) -> str:
    """排期表「内容」列 → 模拟器动作名。

    ``授業`` 是知识课（模拟器的 lesson），``レッスン``/``追い込み`` 是训练
    （模拟器的 train）；考试/空周只是占位，给策略留出休息周。
    """
    if label.startswith("授業"):
        return "lesson"
    if "追い込み" in label or "レッスン" in label:
        return "train"
    if "試験" in label:
        return "exam"
    return "free"


def parse_schedule_rows(html: str) -> list[dict]:
    """解析 leafierlemon 育成模拟器的逐周排期（div.table/div.tr，不是 ``<table>``）。

    返回 ``[{"week": 1, "label": "レッスン", "action": "train", "base": [60],
    "special": False}, ...]``。``base`` 是页面「上昇量ベース」列里的原始数字：
    レッスン行是 SP/通常的上限，授業行是三个可选属性值，追い込み行是 CLEAR/PERFECT。
    具体口径由调用方（``scripts/wiki_formula_ingest.py``）按官方公式解释。
    """
    marker = 'id="schedule"'
    start = html.find(marker)
    if start < 0:
        return []
    open_start = html.rfind("<div", 0, start)
    next_table = html.find('<div class="table"', start + len(marker))
    chunk = html[open_start : next_table if next_table > 0 else len(html)]
    rows: list[dict] = []
    for raw in re.split(r'<div class="tr">', chunk)[1:]:
        week_match = re.search(r'<div class="td week">\s*(\d+)\s*</div>', raw)
        if week_match is None:
            week_match = re.search(r'<div class="td">\s*(\d+)\s*</div>', raw)
        if week_match is None:
            continue
        tail = raw[week_match.end() :]
        content_match = re.search(r'<div class="td">(.*?)</div>', tail, re.DOTALL)
        label = plain_text(content_match.group(1)) if content_match else ""
        base_match = re.search(
            r'<div class="td base">(.*?)(?=<div class="td inc")', raw, re.DOTALL
        )
        base: list[int] = []
        if base_match is not None:
            for match in re.finditer(
                r'(?:value="(\d+)"|class="radio[^"]*"[^>]*>\s*(\d+)\s*<)',
                base_match.group(1),
            ):
                base.append(int(match.group(1) or match.group(2)))
        rows.append(
            {
                "week": int(week_match.group(1)),
                "label": label,
                "action": _schedule_action(label),
                "base": base,
                "special": "追い込み" in label,
            }
        )
    return rows


# ---------------------------------------------------------------------- 抽取
_PLAN_MAP = {
    "プラン：センス": "sense",
    "プラン：ロジック": "logic",
    "プラン：アノマリー": "anomaly",
    "共通効果": "common",
}

_NUMBER_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*[%％]")


@dataclass
class WikiBuff:
    jp: str
    scope: str
    description: str
    parent: str = ""
    variants: list[str] = field(default_factory=list)
    tables: tuple[tuple[tuple[str, ...], ...], ...] = ()

    def category(self) -> str:
        text = f"{self.jp} {self.description}"
        if "ターン終了時" in text and any(word in text for word in ("上昇", "増加")):
            return "dot"
        if "コスト" in text or "消費体力" in text:
            return "resource"
        if "元気" in text:
            return "defense"
        if "%" in text and any(word in text for word in ("上昇量", "スコア")):
            return "multiplier"
        if "増加量" in text or "ごとに" in text:
            return "flat_stack"
        return "utility"

    def score_multiplier(self) -> float:
        """从"50％増加"这类描述里取倍率；取不到返回 1.0。"""
        for match in _NUMBER_PCT.finditer(self.description):
            pct = float(match.group(1))
            if 5 <= pct <= 300:
                return round(1.0 + pct / 100.0, 3)
        return 1.0


def extract_buffs(html: str) -> list[WikiBuff]:
    """从 buff 一页抽出条目：h4 为条目，h3 为所属 plan，h5 为变体。"""
    sections = parse_sections(html)
    scope = "common"
    buffs: list[WikiBuff] = []
    current: WikiBuff | None = None
    for section in sections:
        if section.level == 3:
            scope = _PLAN_MAP.get(section.heading, scope)
            current = None
            continue
        if section.level == 4:
            current = WikiBuff(
                jp=section.heading,
                scope=scope,
                description=section.text,
                tables=section.tables,
            )
            buffs.append(current)
            continue
        if section.level == 5 and current is not None:
            current.variants.append(section.heading)
            if section.text:
                current.description = f"{current.description} {section.heading}: {section.text}".strip()
    return buffs


def describe_sources() -> dict[str, dict[str, str]]:
    return {
        key: {"title": source["title"], "use": source["use"], "url": source["url"]}
        for key, source in WIKI_SOURCES.items()
    }


# ---------------------------------------------------------------------- 合并
_NEGATIVE_WORDS = ("減少", "低下", "スランプ", "不安", "弱気", "使用不可", "増加しない", "デバフ")
# 这些词出现在名字里时，即使是"負の効果を打ち消す"也是好事
_POSITIVE_OVERRIDES = ("回復", "無効", "耐性", "解除")


def _is_debuff(name: str, description: str) -> bool:
    if any(word in name for word in _POSITIVE_OVERRIDES):
        return False
    probe = f"{name} {description[:120]}"
    return any(word in probe for word in _NEGATIVE_WORDS)
# 这些标题是"说明章节"，不是 buff 条目
_SKIP_HEADINGS = (
    "成長効果",
    "本ページの概要",
    "効果の分類",
    "発動タイミング",
    "体力(",
    "指針・全力値",
)


def _slug(name: str) -> str:
    """稳定 id：ASCII 部分优先，纯日文名用内容哈希（同一名字永远同一 id）。"""
    ascii_part = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    if ascii_part:
        return ascii_part
    return "jp_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def merge_buffs(data: dict, wiki_buffs: list[WikiBuff], *, source_url: str = "") -> dict:
    """把 wiki 条目合并进人工维护的 buffs.json。

    规则：日文名对上的条目**只补描述和出处**，不覆盖人工校订的 cn/权重/顺序；
    新条目追加为 ``cn: []`` 的日文条目，权重按描述关键词粗估。
    """
    existing = list(data.get("buffs") or [])
    by_jp: dict[str, dict] = {}
    for entry in existing:
        for name in entry.get("jp") or ():
            by_jp[name] = entry
    added = 0
    updated = 0
    for wiki_buff in wiki_buffs:
        if any(word in wiki_buff.jp for word in _SKIP_HEADINGS):
            continue
        entry = by_jp.get(wiki_buff.jp)
        if entry is None:
            negative = _is_debuff(wiki_buff.jp, wiki_buff.description)
            entry = {
                "id": _slug(wiki_buff.jp),
                "cn": [],
                "jp": [wiki_buff.jp],
                "kind": "debuff" if negative else "buff",
                "scope": wiki_buff.scope,
                "category": wiki_buff.category(),
                "duration": "",
                "score_flat": 0.0,
                "score_mult": wiki_buff.score_multiplier(),
                "play_order": 60 if negative else 25,
                "effect": "",
                "notes": "",
            }
            existing.append(entry)
            by_jp[wiki_buff.jp] = entry
            added += 1
        description = wiki_buff.description.strip()
        if description and entry.get("jp_desc") != description[:600]:
            entry["jp_desc"] = description[:600]
            entry["wiki"] = source_url
            if not entry.get("effect"):
                entry["effect"] = description[:200]
            updated += 1
        if wiki_buff.variants:
            entry["wiki_variants"] = wiki_buff.variants[:12]
    data["buffs"] = existing
    data["wiki_meta"] = {
        "source": source_url,
        "synced": time.strftime("%Y-%m-%d %H:%M:%S"),
        "added": added,
        "updated": updated,
        "total": len(existing),
    }
    return data
