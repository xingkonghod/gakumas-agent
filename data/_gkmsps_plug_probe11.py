"""plug 探针11（不提交）：選抜/本戦 NPC 分数带 + 过关线 + v2 实际抽到 NPC。"""
import sys, json, hashlib
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
from GKMSPS.ps.sim import Sim, SELECTION, MAIN, STEP_TAIL
from GKMSPS.ps import exam as X
f = json.load(open('data/_gkmsps_plug_data/formation_v2.json', encoding='utf-8'))
root = hashlib.sha256(b'gkmsps-plug-v1:0').digest()
sim = Sim(f, timestamp_ms=0, root=root)
d = sim.d
for pid, stages in ((SELECTION, ('mid1', 'mid2', 'final')), (MAIN, ('mid1', 'final'))):
    for stage in stages:
        row = d.difficulty(sim.s['idol'], pid, STEP_TAIL[stage])
        grp = sorted(d.npc_groups.get(row['produceExamBattleNpcGroupId'], ()), key=lambda r: r['number'])
        bands = [(int(r.get('scoreMin') or 0), int(r.get('scoreMax') or 0)) for r in grp]
        print(pid, stage, 'threshold=', row.get('rankThreshold'), 'npc_bands=', bands)
# 实际 root0 選抜 NPC（与 probe10 同流）
for stage in ('mid1', 'mid2', 'final'):
    npcs = X.npc_scores(sim, stage, sim.rng(f"exam/sel/{stage}/npc#t0"))
    print('sel', stage, 'npcs_t0=', [int(x) for x in npcs])
