"""T7③ 自动复盘页：每局一个自包含 HTML（逐回合 + 逐步轨迹 + 人工标注导出）。

- ``build_review_html``：**纯函数**渲染（同输入同输出，无时钟/无 I/O），
  数据全部 HTML 转义，内嵌 JSON 防 ``</script>`` 逃逸；离线打开即用，无外部资源。
- ``write_review_page``：原子写盘（tmp + os.replace，与 run_record 同约定）。
- 页面内容：周行动逐回合表 / 考试表 / 结算 / 重放一致性（T7② 三方对账）/
  观测事件日志 / C1 逐步轨迹表（lost/failed/stuck 高亮）/ 标注工具栏。
- 标注闭环：每行可打 verdict（ok/bad/unsure）+ 评论 + expected（``k=v;k=v``），
  localStorage 自动保存，「导出标注」下载 ``annotations_<ep>.json``，
  ``scripts/annotations_to_regression.py`` 转成回归用例（见 report.annotations）。

``trace_source``：``live`` = 真机 step_trace；``synthetic-demo`` = 合成演示轨迹
（页面显著标注，不当真机数据）；空轨迹显示空态说明。
"""

from __future__ import annotations

import html
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from gkagent.data.run_replay import (
    consistency_check,
    events_of,
    initial_state,
    replay,
    state_to_dict,
)
from gkagent.report.annotations import SCHEMA

_CSS = """
body{font-family:system-ui,'Segoe UI',sans-serif;margin:0;background:#f6f7f9;color:#1c2430}
header{background:#232f3e;color:#fff;padding:14px 22px}
header h1{margin:0;font-size:20px} header .sub{color:#b8c4d0;font-size:12px;margin-top:4px}
main{padding:16px 22px;max-width:1200px;margin:0 auto}
section{background:#fff;border:1px solid #dde3ea;border-radius:8px;padding:12px 16px;margin-bottom:14px}
h2{font-size:15px;margin:0 0 8px;border-bottom:1px solid #eef1f5;padding-bottom:6px}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{border:1px solid #e3e8ef;padding:4px 7px;text-align:left;vertical-align:top}
th{background:#f0f3f7}
tr.anom td{background:#fdecea} tr.dup td{background:#fff6e0} tr.bad td{background:#fde8e8}
.null{color:#9aa4b2} .ok{color:#1a7f37;font-weight:600} .bad{color:#c62828;font-weight:600}
.cards{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.card{background:#fff;border:1px solid #dde3ea;border-radius:8px;padding:8px 14px;min-width:120px}
.card .v{font-size:19px;font-weight:700} .card .k{font-size:11px;color:#66707c}
.banner{background:#fff8e1;border:1px solid #e0c060;border-radius:6px;padding:8px 12px;font-size:12.5px;margin-bottom:10px}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
button{background:#232f3e;color:#fff;border:0;border-radius:6px;padding:6px 14px;font-size:13px;cursor:pointer}
button.ghost{background:#fff;color:#232f3e;border:1px solid #b8c4d0}
select,input[type=text]{font-size:12px;padding:2px 4px;border:1px solid #cfd6df;border-radius:4px}
td.ann{min-width:250px} td.ann input[type=text]{width:96%}
.help{font-size:12px;color:#66707c;line-height:1.6}
code{background:#f0f3f7;padding:1px 4px;border-radius:3px;font-size:12px}
details summary{cursor:pointer;font-size:13px;color:#345}
footer{padding:10px 22px;font-size:11px;color:#8a94a2}
"""

_JS = """
const DATA = JSON.parse(document.getElementById('review-data').textContent);
const KEY = 'gkreview:' + DATA.episode + ':' + (DATA.fingerprint || '').slice(0, 8);
let anns = {};
try { anns = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { anns = {}; }
anns = Object.assign({}, DATA.annotations || {}, anns);
function save() { try { localStorage.setItem(KEY, JSON.stringify(anns)); } catch (e) {} }
function parseExpected(text) {
  const out = {};
  (text || '').split(';').forEach(function (part) {
    part = part.trim();
    if (!part || part.indexOf('=') < 0) return;
    const i = part.indexOf('=');
    const k = part.slice(0, i).trim(), raw = part.slice(i + 1).trim();
    if (!k) return;
    try { out[k] = JSON.parse(raw); } catch (e) { out[k] = raw; }
  });
  return out;
}
function expectedText(exp) {
  return Object.keys(exp || {}).map(function (k) {
    const v = exp[k];
    return k + '=' + (typeof v === 'string' ? v : JSON.stringify(v));
  }).join(';');
}
function renderControls() {
  document.querySelectorAll('tr[data-ann-id]').forEach(function (tr) {
    const id = tr.getAttribute('data-ann-id');
    const cell = tr.querySelector('td.ann');
    if (!cell || cell.dataset.wired) return;
    cell.dataset.wired = '1';
    const a = anns[id] || {};
    const sel = document.createElement('select');
    ['', 'ok', 'bad', 'unsure'].forEach(function (v) {
      const o = document.createElement('option');
      o.value = v; o.textContent = v || '—';
      if ((a.verdict || '') === v) o.selected = true;
      sel.appendChild(o);
    });
    const comment = document.createElement('input');
    comment.type = 'text'; comment.placeholder = '评论'; comment.value = a.comment || '';
    const exp = document.createElement('input');
    exp.type = 'text'; exp.placeholder = 'expected: k=v;k=v'; exp.value = expectedText(a.expected);
    function upd() {
      const e = parseExpected(exp.value);
      if (!sel.value && !comment.value && !Object.keys(e).length) { delete anns[id]; }
      else { anns[id] = { verdict: sel.value, comment: comment.value, expected: e }; }
      save();
      tr.classList.toggle('bad', sel.value === 'bad');
    }
    sel.addEventListener('change', upd);
    comment.addEventListener('input', upd);
    exp.addEventListener('input', upd);
    cell.appendChild(sel); cell.appendChild(comment); cell.appendChild(exp);
    if (a.verdict === 'bad') tr.classList.add('bad');
  });
}
function exportAnnotations() {
  const list = [];
  document.querySelectorAll('tr[data-ann-id]').forEach(function (tr) {
    const id = tr.getAttribute('data-ann-id');
    const a = anns[id];
    if (!a || !a.verdict) return;
    list.push({ id: id, target: tr.getAttribute('data-target'),
                key: isNaN(+tr.getAttribute('data-key')) ? tr.getAttribute('data-key') : +tr.getAttribute('data-key'),
                verdict: a.verdict, comment: a.comment || '', expected: a.expected || {} });
  });
  const payload = { schema: DATA.schema, episode: DATA.episode, fingerprint: DATA.fingerprint,
                    exported_at: new Date().toISOString(), annotations: list };
  const blob = new Blob([JSON.stringify(payload, null, 1)], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'annotations_' + DATA.episode + '.json';
  link.click();
  URL.revokeObjectURL(link.href);
}
function importAnnotations(file) {
  const reader = new FileReader();
  reader.onload = function () {
    try {
      const payload = JSON.parse(String(reader.result));
      if (payload.schema !== DATA.schema || payload.episode !== DATA.episode) {
        alert('schema/episode 不符，拒绝导入'); return;
      }
      (payload.annotations || []).forEach(function (a) {
        if (a && a.id && a.verdict) {
          anns[a.id] = { verdict: a.verdict, comment: a.comment || '', expected: a.expected || {} };
        }
      });
      save();
      document.querySelectorAll('td.ann').forEach(function (c) { c.innerHTML = ''; delete c.dataset.wired; });
      renderControls();
    } catch (e) { alert('导入失败: ' + e); }
  };
  reader.readAsText(file);
}
document.getElementById('btn-export').addEventListener('click', exportAnnotations);
document.getElementById('btn-import').addEventListener('click', function () {
  document.getElementById('file-import').click();
});
document.getElementById('file-import').addEventListener('change', function (ev) {
  if (ev.target.files && ev.target.files[0]) importAnnotations(ev.target.files[0]);
  ev.target.value = '';
});
document.getElementById('btn-clear').addEventListener('click', function () {
  if (!confirm('清除本局全部标注？')) return;
  anns = {}; save();
  document.querySelectorAll('td.ann').forEach(function (c) { c.innerHTML = ''; delete c.dataset.wired; });
  document.querySelectorAll('tr.bad').forEach(function (tr) { tr.classList.remove('bad'); });
  renderControls();
});
renderControls();
"""


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _cell(value: Any) -> str:
    if value is None:
        return '<td class="null">null</td>'
    if isinstance(value, (list, tuple)):
        return "<td>" + _esc("/".join(str(item) for item in value)) + "</td>"
    return "<td>" + _esc(value) + "</td>"


def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (list, tuple)):
        return "/".join(str(item) for item in value)
    return str(value)


def _ann_row_attrs(target: str, key: Any, ann_id: str) -> str:
    return f' data-ann-id="{_esc(ann_id)}" data-target="{_esc(target)}" data-key="{_esc(key)}"'


def _weeks_table(record: Mapping[str, Any]) -> str:
    weeks = record.get("weeks") or []
    rows: list[str] = []
    previous_key: tuple[Any, Any] | None = None
    for index, week in enumerate(weeks):
        if not isinstance(week, Mapping):
            continue
        key = (week.get("week"), week.get("action"))
        classes = []
        if previous_key is not None and key == previous_key and key != (None, None):
            classes.append("dup")
        previous_key = key
        cls = f' class="{" ".join(classes)}"' if classes else ""
        cells = "".join(
            _cell(week.get(name))
            for name in ("week", "action", "lesson_score", "attrs_after", "stamina")
        )
        note = week.get("note")
        rows.append(
            f"<tr{cls}{_ann_row_attrs('week', index, f'week-{index}')}>"
            f"{cells}<td>{_esc(note) if note else ''}</td><td class=\"ann\"></td></tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="7" class="null">无周记录</td></tr>')
    return (
        "<table><tr><th>周</th><th>行动</th><th>课程分</th><th>三维</th><th>体力</th>"
        "<th>note</th><th>标注</th></tr>" + "".join(rows) + "</table>"
    )


def _exams_table(record: Mapping[str, Any]) -> str:
    exams = record.get("exams") or []
    rows: list[str] = []
    for index, exam in enumerate(exams):
        if not isinstance(exam, Mapping):
            continue
        cells = "".join(_cell(exam.get(name)) for name in ("kind", "rank", "score", "others"))
        note = exam.get("note")
        rows.append(
            f"<tr{_ann_row_attrs('exam', index, f'exam-{index}')}>"
            f"{cells}<td>{_esc(note) if note else ''}</td><td class=\"ann\"></td></tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="6" class="null">无考试记录</td></tr>')
    return (
        "<table><tr><th>类型</th><th>名次</th><th>分数</th><th>全员分数</th>"
        "<th>note</th><th>标注</th></tr>" + "".join(rows) + "</table>"
    )


def _final_table(record: Mapping[str, Any]) -> str:
    final = record.get("final")
    if not isinstance(final, Mapping):
        return '<p class="null">final=null（未采集到结算）</p>'
    cells = "".join(
        _cell(final.get(name)) for name in ("attrs", "rank", "exam_score", "eval_points", "grade")
    )
    note = final.get("note")
    return (
        "<table><tr><th>三维</th><th>名次</th><th>终试分</th><th>评价点</th><th>评价</th>"
        "<th>note</th><th>标注</th></tr>"
        f"<tr{_ann_row_attrs('final', 'final', 'final')}>{cells}"
        f"<td>{_esc(note) if note else ''}</td><td class=\"ann\"></td></tr></table>"
    )


def _trace_table(trace_rows: Sequence[Mapping[str, Any]], trace_source: str) -> str:
    if not trace_rows:
        return (
            '<p class="null">无轨迹数据（data/step_trace.jsonl 里没有这一局；'
            "C1 之后的真机跑局每步自动落盘，跑完自动生成）。</p>"
        )
    banner = ""
    if trace_source == "synthetic-demo":
        banner = (
            '<div class="banner">⚠️ <b>演示轨迹（合成数据，仅演示排版与标注闭环）</b>：'
            "本局记录早于 C1 或无真机轨迹，下列步骤不是真机观测，勿当数据引用。</div>"
        )
    rows: list[str] = []
    for row in trace_rows:
        outcome = str(row.get("outcome") or "")
        anom = outcome in ("lost", "failed") or row.get("screen") == "stuck"
        cls = ' class="anom"' if anom else ""
        step = row.get("step")
        point = row.get("point")
        point_text = f"({point[0]},{point[1]})" if isinstance(point, (list, tuple)) and len(point) >= 2 else ""
        expect = str(row.get("expect_kind") or "")
        words = row.get("expect_words") or []
        if words:
            expect += "（" + "/".join(str(word) for word in words) + "）"
        rows.append(
            f"<tr{cls}{_ann_row_attrs('step', step, f'step-{step}')}>"
            f"<td>{_esc(step)}</td><td>{_esc(row.get('screen'))}</td><td>{_esc(row.get('action'))}</td>"
            f"<td>{_esc(point_text)}</td><td>{_esc(row.get('reason'))}</td>"
            f"<td>{_esc(row.get('engine_note'))}</td><td>{_esc(expect)}</td>"
            f"<td>{_esc(outcome)}</td><td>{_esc(row.get('tries') or 0)}</td>"
            '<td class="ann"></td></tr>'
        )
    return (
        banner
        + "<table><tr><th>步</th><th>屏幕</th><th>动作</th><th>坐标</th><th>理由</th>"
        "<th>引擎注记</th><th>预算</th><th>互验</th><th>重试</th><th>标注</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _events_table(record: Mapping[str, Any]) -> str:
    events, source = events_of(record)
    rows: list[str] = []
    for event in events:
        kind = str(event.get("kind"))
        if kind in ("action", "backfill"):
            detail = (
                f"week={_fmt(event.get('week'))} action={_fmt(event.get('action'))} "
                f"attrs={_fmt(event.get('attrs_after'))} stamina={_fmt(event.get('stamina'))}"
            )
        elif kind == "lesson":
            detail = f"score={_fmt(event.get('score'))}"
        elif kind == "exam":
            detail = (
                f"{_fmt(event.get('exam_kind'))} rank={_fmt(event.get('rank'))} "
                f"score={_fmt(event.get('score'))} others={_fmt(event.get('others'))}"
            )
        else:
            detail = (
                f"attrs={_fmt(event.get('attrs'))} rank={_fmt(event.get('rank'))} "
                f"exam_score={_fmt(event.get('exam_score'))} points={_fmt(event.get('eval_points'))} "
                f"grade={_fmt(event.get('grade'))}"
            )
        rows.append(
            f"<tr><td>{_esc(event.get('seq'))}</td><td>{_esc(kind)}</td><td>{_esc(detail)}</td></tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="3" class="null">无观测事件</td></tr>')
    return (
        f"<p class=\"help\">来源：{ _esc(source) }（events=跑局观测日志；legacy=旧格式汇总确定式重建）</p>"
        "<table><tr><th>seq</th><th>种类</th><th>观测</th></tr>" + "".join(rows) + "</table>"
    )


def build_review_html(
    record: Mapping[str, Any],
    trace_rows: Sequence[Mapping[str, Any]] = (),
    *,
    trace_source: str = "live",
    annotations: Mapping[str, Any] | None = None,
) -> str:
    """一局记录 + 逐步轨迹 → 自包含复盘页 HTML（纯函数，同输入同输出）。"""
    episode = str(record.get("episode") or "ep-unknown")
    check = consistency_check(record)
    events, _source = events_of(record)
    states = replay(events)
    final_state = state_to_dict(states[-1] if states else initial_state())
    final = record.get("final") if isinstance(record.get("final"), Mapping) else {}
    weeks = record.get("weeks") or []
    exams = record.get("exams") or []
    anomaly_count = sum(
        1
        for row in trace_rows
        if str(row.get("outcome") or "") in ("lost", "failed") or row.get("screen") == "stuck"
    )
    consistency_text = (
        '<span class="ok">一致</span>'
        if check["consistent"]
        else '<span class="bad">不一致（' + str(len(check["discrepancies"]) + len(check["record_diffs"])) + " 项）</span>"
    )
    discrepancy_rows = "".join(
        "<tr><td>" + _esc(item.get("field")) + "</td><td>" + _esc(json.dumps(item.get("events") if "events" in item else item.get("replay"), ensure_ascii=False)) + "</td><td>" + _esc(json.dumps(item.get("legacy") if "legacy" in item else item.get("record"), ensure_ascii=False)) + "</td></tr>"
        for item in [*check["discrepancies"], *check["record_diffs"]]
    )
    discrepancy_table = (
        "<table><tr><th>字段</th><th>重放</th><th>对照</th></tr>" + discrepancy_rows + "</table>"
        if discrepancy_rows
        else ""
    )
    payload = {
        "schema": SCHEMA,
        "episode": episode,
        "fingerprint": check["fingerprint"],
        "record": dict(record),
        "trace_rows": [dict(row) for row in trace_rows],
        "trace_source": trace_source,
        "replay": {
            "source": check["source"],
            "steps": check["steps"],
            "consistent": check["consistent"],
            "final_state": final_state,
        },
        "annotations": dict(annotations) if isinstance(annotations, Mapping) else None,
    }
    # < > 转 Unicode 转义：JSON 语义不变，内嵌块里绝不出现裸标签（防逃逸，双保险）
    embedded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=list)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    cards = [
        ("评价", _fmt(final.get("grade"))),
        ("评价点", _fmt(final.get("eval_points"))),
        ("周记录", str(len(weeks))),
        ("考试", str(len(exams))),
        ("轨迹步数", str(len(trace_rows))),
        ("轨迹异常", str(anomaly_count)),
        ("课程分合计", str(final_state.get("lesson_total"))),
        ("重放步数", str(check["steps"])),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="v">{_esc(value)}</div><div class="k">{_esc(name)}</div></div>'
        for name, value in cards
    )
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>复盘 {_esc(episode)}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
<h1>自动复盘页 · {_esc(episode)}</h1>
<div class="sub">开始 {_esc(record.get('started_at'))} · 观测来源 {_esc(check['source'])} ·
重放指纹 <code>{_esc(check['fingerprint'][:16])}…</code> · T7②③ 离线可靠性工程</div>
</header>
<main>
<div class="cards">{cards_html}</div>
<section>
<h2>① 周行动（逐回合）</h2>
{_weeks_table(record)}
<p class="help">黄底 = 与上一条同周同行动（重复观测，疑似卡屏/轮转）；null = 没读到（不编造）。</p>
</section>
<section>
<h2>② 考试</h2>
{_exams_table(record)}
</section>
<section>
<h2>③ 最终结算</h2>
{_final_table(record)}
</section>
<section>
<h2>④ 重放一致性（同观测序列 → 同状态）</h2>
<p>三方对账：{consistency_text} · 指纹 <code>{_esc(check['fingerprint'])}</code></p>
{discrepancy_table}
<details><summary>观测事件日志（{len(events)} 条，逐步重放输入）</summary>
{_events_table(record)}
</details>
</section>
<section>
<h2>⑤ 逐步轨迹（C1 step_trace）</h2>
{_trace_table(trace_rows, trace_source)}
<p class="help">红底 = lost/failed/stuck 异常步；「预算」= 点击前预算下一帧应读到什么；「互验」= 兑现结果。</p>
</section>
<section>
<h2>⑥ 人工标注 → 回归</h2>
<div class="toolbar">
<button id="btn-export">导出标注 JSON</button>
<button id="btn-import" class="ghost">导入标注</button>
<button id="btn-clear" class="ghost">清除本局标注</button>
<input type="file" id="file-import" accept=".json,application/json" style="display:none">
</div>
<p class="help">
每行右侧：verdict（ok/bad/unsure）+ 评论 + <code>expected: k=v;k=v</code>（修正值，值按 JSON 解析，
如 <code>lesson_score=152</code>、<code>outcome=moved</code>、<code>attrs_after=[210,90,95]</code>）。
标注自动存浏览器 localStorage（键含重放指纹前 8 位，记录变了不串局）。
导出 <code>annotations_{_esc(episode)}.json</code> 后跑
<code>scripts\\annotations_to_regression.py</code> 转成回归用例冻结进
<code>tests/fixtures/review_regressions.json</code>——verdict=bad 且带 expected 的标注才转用例。
</p>
</section>
</main>
<footer>gakumas-agent T7③ 自动复盘页 · 数据：data/runs/{_esc(episode)}.json + data/step_trace.jsonl ·
生成：scripts/review_page.py（auto_produce 局末自动生成）</footer>
<script type="application/json" id="review-data">{embedded}</script>
<script>{_JS}</script>
</body>
</html>
"""


def write_review_page(
    record: Mapping[str, Any],
    trace_rows: Sequence[Mapping[str, Any]] = (),
    *,
    out_dir: Path | str,
    trace_source: str = "live",
) -> Path:
    """渲染并原子写盘到 ``<out_dir>/<episode>.html``；返回路径。"""
    episode = str(record.get("episode") or "ep-unknown").strip() or "ep-unknown"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", episode).strip("._-") or "ep-unknown"
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{safe}.html"
    content = build_review_html(record, trace_rows, trace_source=trace_source)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return path
