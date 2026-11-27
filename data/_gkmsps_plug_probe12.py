"""plug 探针12（不提交）：v2/v3 memory_skill 解析 + 起始参数对比（定位 v3 反而弱的原因）。"""
import sys, json, hashlib
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
from GKMSPS.ps.sim import Sim
from GKMSPS.ps.data import data
d = data()
for fv in ('formation_v2.json', 'formation_v3.json'):
    f = json.load(open(f'data/_gkmsps_plug_data/{fv}', encoding='utf-8'))
    print('===', fv)
    for j, mem in enumerate(f.get('memories') or []):
        for ab in mem.get('abilities') or []:
            sk = d.M.memory_skill(ab['id'], ab.get('level'))
            print(f"  mem{j} phase={mem.get('produce_card_phase_type')} ab={ab['id'][:60]}... -> "
                  f"{'None' if sk is None else (sk.phase, sk.effect_type, sk.value)}")
    sim = Sim(f, timestamp_ms=0, root=hashlib.sha256(b'gkmsps-plug-v1:0').digest())
    print('  at_start params:', sim.s['at_start']['params'], 'max_stamina:', sim.s['max_stamina'],
          'deck:', len(sim._deck()), 'memory_cards:', {k: len(v) for k, v in sim.s['memory_cards'].items()})
