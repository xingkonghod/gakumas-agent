import json, pathlib, sys
sys.path.insert(0, 'scripts')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from eval_t4_b1 import _paired_ci

def L(n):
    return json.loads(pathlib.Path('out/' + n).read_text(encoding='utf-8'))

def sc(d, a):
    return d['results']['unknown'][a]['scores']

def dl(a, b):
    m, h = _paired_ci([x - y for x, y in zip(a, b)])
    return m, m - h, m + h

for n in ['ei_r13_eval_v13_large_fresh6000.json', 'ei_r13_eval_v13_small_select.json']:
    d = L(n)
    print(n)
    for arm in ['net', 'teacher_net', 'beam_analytic']:
        s = d['results']['unknown'][arm]
        print('  %s: mean=%.3f clear=%.1f%% perfect=%.1f%%' % (arm, s['mean'], s['clear_rate']*100, s['perfect_rate']*100))
    m, lo, hi = dl(sc(d, 'net'), sc(d, 'teacher_net'))
    print('  net-r11: %+.3f CI[%+.3f,%+.3f]' % (m, lo, hi))
