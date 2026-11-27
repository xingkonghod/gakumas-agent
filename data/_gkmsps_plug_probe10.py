"""plug 探针10（不提交）：選抜真实过关可行性——formation v2/v3 × plug/default 臂，不 assume。"""
import sys, json, hashlib, time
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
r14 = m.load_r14(); v = m.Values(r14, m.ROOT / 'data/knowledge/drinks.json')
from GKMSPS.ps.sim import Sim
from GKMSPS.ps.cli import auto

for fv in ('formation_v2.json', 'formation_v3.json'):
    f = json.load(open(f'data/_gkmsps_plug_data/{fv}', encoding='utf-8'))
    for arm in ('default', 'plug'):
        root = hashlib.sha256(b'gkmsps-plug-v1:0').digest()
        t0 = time.perf_counter()
        if arm == 'default':
            sel = Sim(f, timestamp_ms=0, root=root)
            auto(sel, 0, engine=False, sensible=True)
            stats = {}
        else:
            sel = Sim(f, timestamp_ms=0, root=root)
            pol = m.PlugProduce(v); algo = r14.EiR14Algo(); n = 0
            while not sel.s['done'] and n < 20000:
                dec = sel.decision()
                if dec is None: break
                if dec['kind'] == 'exam':
                    m.play_exam(sel, algo, pol.stats)
                else:
                    sel.act(pol.pick(sel, dec))
                n += 1
            stats = pol.stats
        res = sel.s['result'] or {}
        aud = {k: (r.get('score'), r.get('rank')) for k, r in sel.s['auditions'].items()}
        print(f"{fv} {arm}: outcome={res.get('outcome')} aud={aud} "
              f"params={dict(sel.s['params'])} star={sel.s['star']} "
              f"elapsed={time.perf_counter()-t0:.1f}s stats={stats}", flush=True)
