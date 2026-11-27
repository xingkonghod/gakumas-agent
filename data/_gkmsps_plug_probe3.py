"""plug 探针3（不提交）：v2 编成 + v1.1 规则测试。"""
import sys, json, hashlib, time
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
r14 = m.load_r14(); v = m.Values(r14, m.ROOT / 'data/knowledge/drinks.json')
from GKMSPS.ps.sim import Sim
f = json.load(open('data/_gkmsps_plug_data/formation_v2.json', encoding='utf-8'))
mode = sys.argv[1] if len(sys.argv) > 1 else 'r14'
for i in range(4):
    root = hashlib.sha256(f'gkmsps-plug-v1:{i}'.encode()).digest()
    sel = Sim(f, timestamp_ms=0, root=root)
    pol = m.PlugProduce(v); algo = r14.EiR14Algo(); n = 0; t = time.perf_counter()
    while not sel.s['done'] and n < 400:
        dec = sel.decision()
        if dec is None: break
        if dec['kind'] == 'exam':
            if mode == 'engine': sel.exam_auto(budget=1.0)
            else: m.play_exam(sel, algo, pol.stats)
        else:
            sel.act(pol.pick(sel, dec))
        n += 1
    res = sel.s['result'] or {}
    aud = {k: v2['score'] for k, v2 in sel.s['auditions'].items() if not k.endswith('_lost')}
    print(i, mode, res.get('outcome'), aud, 'params', sel.s['params'],
          'L/R', pol.stats['lessons'], pol.stats['rests'], round(time.perf_counter() - t, 1), 's')
    if res.get('outcome') == 'selection_memory':
        hon = Sim.honsen(res['selection_memory'], timestamp_ms=1, root=hashlib.sha256(root + b':hon').digest())
        pol2 = m.PlugProduce(v); algo2 = r14.EiR14Algo(); n = 0
        while not hon.s['done'] and n < 400:
            dec = hon.decision()
            if dec is None: break
            if dec['kind'] == 'exam':
                if mode == 'engine': hon.exam_auto(budget=1.0)
                else: m.play_exam(hon, algo2, pol2.stats)
            else:
                hon.act(pol2.pick(hon, dec))
            n += 1
        r2 = hon.s['result'] or {}
        print('   hon:', r2.get('outcome'), 'rating', r2.get('rating'), 'grade', r2.get('grade'),
              'round2', r2.get('round2'), 'params', hon.s['params'])