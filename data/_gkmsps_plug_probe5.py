"""plug 探针5（不提交）：扫描各偶像 H.I.F 难度曲线，找可玩编成。"""
import sys, json
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
from GKMSPS.ps.data import data, name
d = data()
rows = []
for iid, card in d.idols.cards.items():
    try:
        out = {'id': iid, 'plan': d.plan_of(iid), 'mech': d.exam_effect_type(iid)}
        for stage, tail in (('mid1', 'AUDITION_MID1'), ('mid2', 'AUDITION_MID2'), ('final', 'AUDITION_FINAL')):
            r = d.difficulty(iid, 'produce-007', tail)
            npcs = d.npc_groups.get(r['produceExamBattleNpcGroupId'], ())
            top = sorted((int(x.get('scoreMin') or 0) for x in npcs), reverse=True)
            out[stage] = (r.get('rankThreshold'), top[:2])
        rows.append(out)
    except KeyError:
        continue
rows.sort(key=lambda r: r['mid2'][1][0] if r['mid2'][1] else 1e9)
for r in rows[:14]:
    print(r['id'], r['plan'], r['mech'].replace('PRODUCE_EXAM_EFFECT_TYPE_EXAM_', ''),
          'mid1', r['mid1'], 'mid2', r['mid2'], 'final', r['final'])
print('total idols:', len(rows))