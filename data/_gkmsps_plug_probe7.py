"""plug 探针7（不提交）：dump mid2 loadout + 大预算引擎考试。"""
import sys, json, hashlib
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
r14 = m.load_r14(); v = m.Values(r14, m.ROOT / 'data/knowledge/drinks.json')
from GKMSPS.ps.sim import Sim
from GKMSPS.ps import exam as X
f = json.load(open('data/_gkmsps_plug_data/formation_v2.json', encoding='utf-8'))
root = hashlib.sha256(b'gkmsps-plug-v1:0').digest()
sel = Sim(f, timestamp_ms=0, root=root)
pol = m.PlugProduce(v); algo = r14.EiR14Algo(); n = 0
captured = {}
while not sel.s['done'] and n < 400:
    dec = sel.decision()
    if dec is None: break
    if dec['kind'] == 'exam':
        t = sel.exam_task()
        if t['stage'] == 'mid2':
            captured = {'loadout': t['loadout'], 'seed': t['seed'], 'params': dict(sel.s['params']),
                        'deck': [(c['id'], c['up']) for c in sel._deck()]}
        m.play_exam(sel, algo, pol.stats)
    else:
        sel.act(pol.pick(sel, dec))
    n += 1
print('stats:', pol.stats)
print('mid2 params:', captured.get('params'))
lo = captured['loadout']
print('deck size:', len(lo['deck_cards']), 'items:', lo['produce_item_ids'], 'drinks:', lo['drink_ids'])
print('supports:', [(s['support_card_id'], s['permil']) for s in lo['support_cards']])
print('permils:', lo['score_bonus_permils'], 'stamina:', lo['starting_stamina'], '/', lo['max_stamina'])
print('deck:', [(c['produce_card_id'], c['current_upgrade_count']) for c in lo['deck_cards']])
for budget in (2.0, 8.0):
    s = X.open_session(lo, captured['seed'])
    line = X.plan(s, budget=budget)
    for a in line:
        if s.finished: break
        X.step(s, a)
    print('engine budget', budget, 'score', int(s.observe()['score']), 'turns', s.observe().get('turn'))
s = X.open_session(lo, captured['seed'])
st = {}
m._play_session(s, r14.EiR14Algo(), st, drink_aojiru=False)
print('r14 score', int(s.observe()['score']))