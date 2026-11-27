"""plug 探针6（不提交）：mid2 考试上界——强卡组+达标参数能否到 50k。"""
import sys, json
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
from GKMSPS.ps.data import data, name
from GKMSPS.ps import exam as X
d = data()
r14 = m.load_r14()
idol = 'i_card-hmsz-3-016'
row = d.difficulty(idol, 'produce-007', 'AUDITION_MID2')
from GakumasCLI.produce import audition_eval as AE, produce_effects as pe
params = {'1': 900, '2': 700, '3': 700}
permils = AE.permils(X.master().audition_catalog, row['produceExamBattleConfigId'], params, 500, pe.star_bonus('sel2', 255))
print('permils', permils)
# 强卡组：12 张 SSR+（r14 profile score 前列，排除偶像专属/麻烦）
prof = json.loads((r14.HERE / 'card_profiles.json').read_text(encoding='utf-8'))['cards']
cands = []
for k, v in prof.items():
    cid, _, up = k.partition('|')
    if up != '1': continue
    if (cid, 1) not in d.cards: continue
    rowc = d.card(cid, 1)
    if name(rowc.get('category'), 'PRODUCE_CARD_CATEGORY_') == 'TROUBLE': continue
    if rowc.get('originIdolCardId'): continue
    cands.append((v['p'][0], cid))
cands.sort(reverse=True)
deck = [{'produce_card_id': cid, 'current_upgrade_count': 1} for _, cid in cands[:12]]
print('deck top:', cands[:12])
lo = {'schema': 'gkms.hif_loadout.v1', 'idol_card_id': idol, 'round': 'mid2', 'produce_id': 'produce-007',
      'parameters': params, 'score_bonus_permils': permils, 'deck_cards': deck, 'include_produce_default': False,
      'produce_item_ids': [], 'drink_ids': [], 'support_cards': [],
      'max_stamina': 44, 'starting_stamina': 44, 'lesson_start_enchant_ids': [], 'main_item_enchant_ids': [],
      'research_card_ids': []}
for seed in (12345, 67890, 11111):
    s = X.open_session(lo, seed)
    st = {}
    m._play_session(s, r14.EiR14Algo(), st, drink_aojiru=False)
    print('r14 seed', seed, 'score', int(s.observe()['score']))
for seed in (12345, 67890):
    s = X.open_session(lo, seed)
    from GKMSPS.ps import exam as X2
    line = X2.plan(s, budget=2.0)
    for a in line:
        if s.finished: break
        X2.step(s, a)
    print('engine seed', seed, 'score', int(s.observe()['score']))