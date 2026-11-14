"""跑几局培育模拟，生成一个可在浏览器里单步回放的前端。

用法：
    python scripts/sim_trace.py                # 生成 docs/sim_viewer.html
    python scripts/sim_trace.py --runs 8

产物是**单文件 HTML**（数据直接内嵌，双击即可打开，不依赖服务器）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "docs" / "sim_viewer.html"


def build_runs(count: int) -> list[dict]:
    import sim_produce as sp

    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import STRATEGIES, ProduceConfig, ProduceSim

    deck_raw = sp.build_deck()
    pool_raw = sp.build_pool()
    deck = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in deck_raw]
    pool = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in pool_raw]

    strategies = ["searched", "lesson_heavy", "train_best", "smart", "random"]
    runs = []
    for index in range(count):
        name = strategies[index % len(strategies)]
        config = ProduceConfig(reward_pick="best", support_bonus=1.15)
        sim = ProduceSim(deck, config=config, rng_seed=1000 + index)
        sim.reward_pool = pool
        if name == "searched":
            import json as _json

            from gkagent.sim.produce import StrategyParams, strategy_from_params

            best = _json.loads((ROOT / "data" / "knowledge" / "policy_sim.json").read_text(encoding="utf-8"))["produce"]
            strategy = strategy_from_params(StrategyParams(**best))
        elif name == "random":
            from gkagent.sim.produce import random_strategy

            strategy = random_strategy(1000 + index)
        else:
            strategy = STRATEGIES[name]
        result = sim.run(strategy)
        runs.append(
            {
                "id": index + 1,
                "label": f"#{index + 1} {name} (seed {1000 + index})",
                "strategy": name,
                "seed": 1000 + index,
                "weeks": sim.trace,
                "result": {
                    "attrs": list(result.attrs),
                    "total": result.total,
                    "fans": result.fans,
                    "grade": result.grade,
                    "lessons": result.lessons,
                    "cleared": result.cleared,
                    "exams_passed": result.exams_passed,
                },
                "deck_size": len(sim.deck),
            }
        )
    return runs


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>学偶培育模拟 · 单局回放</title>
<style>
  :root{--bg:#10131a;--panel:#171b24;--line:#242a36;--text:#e8ecf3;--muted:#8b94a7;
        --vo:#ff5c8a;--da:#4fc3f7;--vi:#ffd54f;--ok:#67d391;--warn:#ff8a65;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
  header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
  h1{font-size:16px;margin:0;font-weight:600}
  select,button{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 10px;font:inherit}
  button:hover{border-color:#3a4356}
  main{display:grid;grid-template-columns:320px 1fr;gap:0;height:calc(100vh - 60px)}
  aside{border-right:1px solid var(--line);padding:16px;overflow:auto}
  section{padding:16px 20px;overflow:auto}
  .bar{height:10px;background:#0c0f15;border-radius:5px;overflow:hidden;margin:4px 0 10px}
  .bar>i{display:block;height:100%;width:0;transition:width .25s}
  .row{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
  .stat{font-size:22px;font-weight:600}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:12px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
  th{color:var(--muted);font-weight:500}
  tr.lesson td{background:#141a24}
  tr.exam td{background:#1d1720;color:#ffb4a2}
  .tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;background:#202634;color:#a9b4c8;margin-right:6px}
  .tag.lesson{background:#1b2a33;color:#7fd3f5}
  .tag.exam{background:#331c24;color:#ffa0b4}
  .tag.train{background:#1c2a1f;color:#8fe0a5}
  .tag.rest{background:#2a2318;color:#ffd479}
  .delta{color:var(--ok);font-weight:600}
  .neg{color:var(--warn)}
  footer{padding:10px 18px;border-top:1px solid var(--line);display:flex;gap:10px;align-items:center}
  input[type=range]{flex:1}
  .grade{font-size:26px;font-weight:700}
  .muted{color:var(--muted)}
  .plays{margin:8px 0 0 0;padding:0;list-style:none;font-size:12px}
  .plays li{padding:3px 0;border-bottom:1px dashed #222a38;display:flex;gap:8px}
  .plays .c{color:#9ecbff;min-width:110px}
</style>
</head>
<body>
<header>
  <h1>学偶培育模拟 · 单局回放</h1>
  <label class="muted">选择一局</label>
  <select id="runSel"></select>
  <span id="runMeta" class="muted"></span>
</header>
<main>
  <aside>
    <div class="card">
      <div class="row"><span>周</span><span id="weekLabel" class="stat">1</span></div>
      <div class="row"><span>剩余/总周</span><span id="weekOf"></span></div>
    </div>
    <div class="card">
      <div class="row"><span>歌唱 Vo</span><span id="voVal">0</span></div>
      <div class="bar"><i id="voBar" style="background:var(--vo)"></i></div>
      <div class="row"><span>舞蹈 Da</span><span id="daVal">0</span></div>
      <div class="bar"><i id="daBar" style="background:var(--da)"></i></div>
      <div class="row"><span>视觉 Vi</span><span id="viVal">0</span></div>
      <div class="bar"><i id="viBar" style="background:var(--vi)"></i></div>
      <div class="row"><span>体力</span><span id="stamVal">0</span></div>
      <div class="bar"><i id="stamBar" style="background:var(--ok)"></i></div>
    </div>
    <div class="card">
      <div class="row"><span>本周行动</span><span id="actionNow">—</span></div>
      <div class="row"><span>本局结果</span><span id="resultNow" class="grade">—</span></div>
      <div class="row"><span>上课/过关</span><span id="lessonNow">0 / 0</span></div>
    </div>
  </aside>
  <section>
    <table>
      <thead><tr><th style="width:56px">周</th><th style="width:110px">行动</th><th>变化</th><th>课程明细</th></tr></thead>
      <tbody id="tbody"></tbody>
    </table>
  </section>
</main>
<footer>
  <button id="first">⏮</button>
  <button id="prev">◀</button>
  <button id="play">播放</button>
  <button id="next">▶</button>
  <button id="last">⏭</button>
  <input id="slider" type="range" min="0" max="0" value="0">
  <span id="counter" class="muted"></span>
</footer>
<script>
const RUNS = __DATA__;
const $ = (id) => document.getElementById(id);
const ATTR = ["vo","da","vi"];
let run = RUNS[0], step = 0, timer = null;

function actionLabel(a){
  return {train:"训练",train_low:"补短板",lesson:"上课",rest:"休息",outing:"外出",remove:"删卡",exam:"考试"}[a] || a;
}
function actionClass(a){ return a==="lesson"?"lesson":(a==="lesson"?"lesson":(a.startsWith("train")?"train":"rest")); }
function fmtDelta(before, after){
  const out=[];
  const names=["Vo","Da","Vi"];
  for(let i=0;i<3;i++){ const d=after[i]-before[i]; if(d) out.push(`<span class="delta">${names[i]}+${d}</span>`); }
  return out.join(" ") || '<span class="muted">—</span>';
}
function renderRunList(){
  $("runSel").innerHTML = RUNS.map((r,i)=>`<option value="${i}">${r.label}</option>`).join("");
  $("runSel").onchange = (e)=>{ run = RUNS[+e.target.value]; step = 0; build(); };
}
function build(){
  const weeks = run.weeks;
  $("slider").max = weeks.length;
  $("slider").value = step;
  $("runMeta").textContent = `策略 ${run.strategy} · 卡组 ${run.deck_size} 张 · 结果 ${run.result.grade}（总和 ${run.result.total}）`;
  $("resultNow").textContent = run.result.grade;
  $("resultNow").style.color = run.result.grade==="E" ? "#ff8a65" : "#67d391";
  $("lessonNow").textContent = `${run.result.lessons} / ${run.result.cleared}`;
  $("weekOf").textContent = weeks.length;
  // 表格：只显示到当前步
  const rows = [];
  for(let i=0;i<=step && i<weeks.length;i++){
    const w = weeks[i];
    const cls = w.action==="lesson"?"lesson":"";
    let detail = "";
    if(w.lesson){
      const L = w.lesson;
      const plays = (L.plays||[]).map(p=> p.skip
        ? `<li><span class="c">SKIP</span><span class="muted">剩余 ${p.turn} 回合</span></li>`
        : `<li><span class="c">${p.card}</span><span class="muted">费用 ${p.cost} · 卡面 ${p.base}${p.focus?` +集中${p.focus}`:""}${p.condition?" · 好调×1.5":""}</span></li>`).join("");
      detail = `<div><span class="tag lesson">课程</span>审查 ${L.target} · 得分 <b>${L.score}</b> · <b style="color:${L.grade==="FAILED"?"#ff8a65":"#67d391"}">${L.grade}</b></div><ul class="plays">${plays}</ul>`;
    }
    rows.push(`<tr class="${cls}"><td>W${w.week}</td><td><span class="tag ${actionClass(w.action)}">${actionLabel(w.action)}</span></td>
      <td>${fmtDelta(w.attrs_before,w.attrs_after)} <span class="muted">体力 ${w.stamina_before}→${w.stamina_after}</span></td>
      <td>${detail}</td></tr>`);
  }
  $("tbody").innerHTML = rows.join("");
  // 侧栏
  const cur = step>0 ? weeks[Math.min(step,weeks.length)-1] : null;
  const attrs = cur ? cur.attrs_after : [0,0,0];
  const stamina = cur ? cur.stamina_after : 35;
  ATTR.forEach((key,i)=>{ $("voVal").textContent=attrs[0]; $("daVal").textContent=attrs[1]; $("viVal").textContent=attrs[2]; });
  $("voVal").textContent = attrs[0]; $("daVal").textContent = attrs[1]; $("viVal").textContent = attrs[2];
  const maxAttr = Math.max(400, ...attrs);
  $("voBar").style.width = (attrs[0]/maxAttr*100)+"%";
  $("daBar").style.width = (attrs[1]/maxAttr*100)+"%";
  $("viBar").style.width = (attrs[2]/maxAttr*100)+"%";
  $("stamVal").textContent = Math.round(stamina)+" / 35";
  $("stamBar").style.width = Math.min(100, stamina/35*100)+"%";
  $("weekLabel").textContent = cur ? cur.week : "—";
  $("actionNow").textContent = cur ? actionLabel(cur.action) : "—";
  $("counter").textContent = `${step} / ${weeks.length}`;
  $("slider").value = step;
}
function go(n){ step = Math.max(0, Math.min(run.weeks.length, n)); build(); }
$("first").onclick=()=>go(0);
$("prev").onclick=()=>go(step-1);
$("next").onclick=()=>go(step+1);
$("last").onclick=()=>go(run.weeks.length);
$("slider").oninput=(e)=>go(+e.target.value);
$("play").onclick=()=>{
  if(timer){ clearInterval(timer); timer=null; $("play").textContent="播放"; return; }
  $("play").textContent="暂停";
  timer=setInterval(()=>{ if(step>=run.weeks.length){ clearInterval(timer); timer=null; $("play").textContent="播放"; return;} go(step+1); }, 550);
};
renderRunList(); build();
</script>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=6)
    args = parser.parse_args(argv)

    runs = build_runs(args.runs)
    payload = json.dumps(runs, ensure_ascii=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA__", payload), encoding="utf-8")
    print(f"生成 {OUT}（{len(runs)} 局，{OUT.stat().st_size/1024:.0f} KB）")
    for r in runs:
        print(f"  {r['label']:32s} 总和={r['result']['total']:4d} 评价={r['result']['grade']:2s} 上课={r['result']['lessons']} 过关={r['result']['cleared']} 卡组={r['deck_size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
