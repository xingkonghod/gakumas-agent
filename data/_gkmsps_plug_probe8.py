"""plug 探针8（不提交）：真实强牌组画像分析。"""
import sys, json
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
r14 = m.load_r14()
prof = json.loads((r14.HERE / 'card_profiles.json').read_text(encoding='utf-8'))['cards']
pool = [json.loads(l) for l in open('data/_gkmsps_pool/pool.bench.v1.jsonl', encoding='utf-8') if l.strip()]
sel2 = [it for it in pool if it['loadout'].get('round') == 'mid2' and it['loadout'].get('produce_id') == 'produce-007']
lo = sel2[2]['loadout']
cols = ['score', 'cost', 'vitality', 'condition', 'focus', 'motivation', 'impression', 'draw',
        'imp_scale', 'preservation', 'fpp', 'extra_play', 'block_scale', 'param_buff', 'strong',
        'stam_rec', 'fp_scale', 'review_mult', 'cond_add', 'fp_lesson', 'grow', 'encore', 'once']
print('cols:', cols)
for c in lo['deck_cards']:
    k = c['produce_card_id'] + '|' + str(c['current_upgrade_count'])
    p = prof.get(k)
    if p:
        print(c['produce_card_id'], c['current_upgrade_count'], [round(x, 1) for x in p['p']])
    else:
        print(c['produce_card_id'], c['current_upgrade_count'], 'NO PROFILE')