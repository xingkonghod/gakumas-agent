"""plug 探针13（不提交）：独立复核 N=100 CI + default 饮料口径 + 分段归因证据。"""
import json
import numpy as np

rows = [json.loads(l) for l in open('out/_gkmsps_plug_games.jsonl', encoding='utf-8') if l.strip()]
print('pairs:', len(rows))
P = [r['plug'] for r in rows]; D = [r['default'] for r in rows]

def ci(x, seed=7, nb=10000):
    x = np.asarray(x, float); rng = np.random.default_rng(seed)
    m = x[rng.integers(0, x.size, size=(nb, x.size))].mean(1)
    return round(x.mean(), 2), round(np.percentile(m, 2.5), 2), round(np.percentile(m, 97.5), 2)

for key, fn in [('rating', lambda r: (r.get('hon') or {}).get('rating') or 0),
                ('round2', lambda r: (r.get('hon') or {}).get('round2') or 0),
                ('hon_mid1', lambda r: ((r.get('hon') or {}).get('auditions') or {}).get('mid1', {}).get('score') or 0),
                ('params_total', lambda r: sum(((r.get('hon') or {}).get('params') or {}).values()))]:
    p = [fn(r) for r in P]; d = [fn(r) for r in D]; diff = [a - b for a, b in zip(p, d)]
    print(f"{key}: plug {ci(p)} default {ci(d)} diff {ci(diff)} wins P/D/T "
          f"{sum(x>0 for x in diff)}/{sum(x<0 for x in diff)}/{sum(x==0 for x in diff)}")

# default 臂饮料口径：stats 是否空 + 实际 drinks_left
print('default stats empty count:', sum(1 for r in D if not r.get('stats')))
print('plug sel drinks_left mean:', round(np.mean([len((r.get('sel') or {}).get('drinks_left') or []) for r in P]), 2),
      'default sel drinks_left mean:', round(np.mean([len((r.get('sel') or {}).get('drinks_left') or []) for r in D]), 2))
print('plug hon drinks_left mean:', round(np.mean([len((r.get('hon') or {}).get('drinks_left') or []) for r in P]), 2),
      'default hon drinks_left mean:', round(np.mean([len((r.get('hon') or {}).get('drinks_left') or []) for r in D]), 2))
# 選抜真实培育差异（课程）
for arm, runs in (('plug', P), ('default', D)):
    les = [sum(r['attr']['sel']['lesson_param'].values()) for r in runs if 'sel' in r['attr']]
    tot = [sum(r['attr']['sel']['param_gain_total'].values()) for r in runs if 'sel' in r['attr']]
    print(f"{arm} sel lesson_total mean {round(np.mean(les),1)} / sel param_gain_total mean {round(np.mean(tot),1)}")
# grade 分布
from collections import Counter
print('plug grade:', Counter((r.get('hon') or {}).get('grade') for r in P))
print('default grade:', Counter((r.get('hon') or {}).get('grade') for r in D))
