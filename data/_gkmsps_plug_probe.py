"""plug 探针（不提交）：编成强度调查 + 强化编成构建。"""
import sys, json, hashlib, time
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
from GKMSPS.ps.data import data
d = data()

for tag, tier in (('450', '02'), ('1000', '03'), ('1500', '04')):
    a = f'ability-p_cd-memory-vocal-{tag}-001-p_memory_skill-common-p_trigger-produce_start-initial-vocal_addition-{tier}-001'
    sk = d.M.memory_skill(a, 1)
    print('vocal', tag, None if sk is None else sk.value)

c = 'p_card-01-ido-3_244'
row = d.card(c, 1)
print('card', c, 'maxCz', row.get('maxCustomizeCount'), 'cz', row.get('produceCardCustomizeIds'))
for cz in (row.get('produceCardCustomizeIds') or ())[:5]:
    lv = d.customize_levels.get(cz) or {}
    print('  ', cz, {k: (v.get('producePoint'), (v.get('description') or '')[:50]) for k, v in lv.items()})

# 看一张强 SSR 的定制 id 语法（r14 透明子集 g_effect-lesson_add-N）
for cid in ('p_card-01-act-3_031', 'p_card-01-ido-3_013', 'p_card-03-act-2_069'):
    r = d.card(cid, 1)
    print(cid, 'cz:', r.get('produceCardCustomizeIds'))