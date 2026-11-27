"""plug 探针9（不提交）：honsen 全链 glue 验证（選抜考试 assume 强制过关 → 本戦真实考试）。"""
import sys, json, hashlib
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
r14 = m.load_r14(); v = m.Values(r14, m.ROOT / 'data/knowledge/drinks.json')
from GKMSPS.ps.sim import Sim
f = json.load(open('data/_gkmsps_plug_data/formation_v2.json', encoding='utf-8'))
root = hashlib.sha256(b'gkmsps-plug-v1:0').digest()
sel = Sim(f, timestamp_ms=0, root=root)
pol = m.PlugProduce(v); n = 0
while not sel.s['done'] and n < 400:
    dec = sel.decision()
    if dec is None: break
    if dec['kind'] == 'exam':
        sel.exam_assume(300000, [100000, 100000, 100000])   # 强制过关（glue 验证用）
    else:
        sel.act(pol.pick(sel, dec))
    n += 1
res = sel.s['result'] or {}
print('selection outcome:', res.get('outcome'))
if res.get('outcome') == 'selection_memory':
    hon = Sim.honsen(res['selection_memory'], timestamp_ms=1, root=hashlib.sha256(root + b':hon').digest())
    pol2 = m.PlugProduce(v); algo = r14.EiR14Algo(); n = 0; exams = []
    while not hon.s['done'] and n < 400:
        dec = hon.decision()
        if dec is None: break
        if dec['kind'] == 'exam':
            t = hon.exam_task()
            m.play_exam(hon, algo, pol2.stats)
            exams.append((t['stage'], (hon.s['auditions'].get(t['stage']) or hon.s['auditions'].get(t['stage'] + '_lost') or {}).get('score')))
        else:
            hon.act(pol2.pick(hon, dec))
        n += 1
    r2 = hon.s['result'] or {}
    print('honsen outcome:', r2.get('outcome'), 'rating:', r2.get('rating'), 'grade:', r2.get('grade'),
          'round1:', r2.get('round1_point'), 'round2:', r2.get('round2'))
    print('honsen exams:', exams, 'params:', hon.s['params'])
    print('attribution:', json.dumps(m.attribute({'arm': 'plug', 'sel': m._summarize(sel), 'hon': m._summarize(hon), 'stats': pol2.stats}), ensure_ascii=False)[:600])