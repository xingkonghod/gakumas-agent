"""plug 探针4（不提交）：v3 编成（4 回忆全 phase1 + 定制）测试。"""
import sys, json, hashlib, time
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
from GKMSPS.ps.data import data
d = data()
r14 = m.load_r14(); v = m.Values(r14, m.ROOT / 'data/knowledge/drinks.json')
from GKMSPS.ps.sim import Sim

f = json.loads((m.WHEEL / 'GKMSPS/examples/formation.json').read_text(encoding='utf-8'))
for sc in f['supports']: sc['level'] = 60

def ab(a): return {'id': a, 'level': 1}
V = 'ability-p_cd-memory-vocal-1500-001-p_memory_skill-common-p_trigger-produce_start-initial-vocal_addition-04-001'
D = 'ability-p_cd-memory-dance-1500-001-p_memory_skill-common-p_trigger-produce_start-initial-dance_addition-04-001'
I = 'ability-p_cd-memory-visual-1500-001-p_memory_skill-common-p_trigger-produce_start-initial-visual_addition-04-001'
P3L = 'ability-p_cd-memory-plan3-001-p_memory_skill-plan3-p_trigger-start_lesson-lesson_dance-exam_status_enchant-exam_turn_timer-exam_lesson_buff-03-001'
P3P = 'ability-p_cd-memory-plan3-001-p_memory_skill-plan3-p_trigger-start_lesson-lesson_dance-exam_status_enchant-exam_turn_timer-exam_preservation-03-001'
# (card, customizes, abilities)
mem = [
    ('p_card-01-ido-3_244', [], [V, P3L]),
    ('p_card-01-act-3_031', [{'id': 'p_card_custom-070-g_effect-lesson_add-12', 'customize_count': 1}], [D, P3P]),
    ('p_card-01-ido-3_013', [], [I, P3L]),
    ('p_card-03-act-2_069', [{'id': 'p_card_custom-040_070-g_effect-lesson_add-6-g_effect-lesson_add-22', 'customize_count': 2}], [V, P3P]),
]
f['memories'] = [{'produce_card': {'id': c, 'upgrade_count': 1, 'customizes': cz},
                  'produce_card_phase_type': 1, 'abilities': [ab(x) for x in abs_]} for c, cz, abs_ in mem]
json.dump(f, open('data/_gkmsps_plug_data/formation_v3.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

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
    print(i, mode, res.get('outcome'), aud, 'params', sum(sel.s['params'].values()),
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
              'round2', r2.get('round2'))