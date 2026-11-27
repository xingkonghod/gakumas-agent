"""plug 探针2（不提交）：mid2 分数尺度 + 强化编成 v3 测试。"""
import sys, json, hashlib, time
import importlib.util
spec = importlib.util.spec_from_file_location('plug', 'scripts/gkmsps_plug.py')
m = importlib.util.module_from_spec(spec); sys.modules['plug'] = m; spec.loader.exec_module(m)
m.ensure_ps_data()
from GKMSPS.ps.data import data
from GakumasCLI.engine.audition import AuditionCatalog
from GakumasCLI.produce import produce_effects as pe
d = data()
cat = AuditionCatalog.load(pe.MASTER_DIR)
idol = 'i_card-hmsz-3-016'
for stage, tail in (('mid1', 'AUDITION_MID1'), ('mid2', 'AUDITION_MID2'), ('final', 'AUDITION_FINAL')):
    row = d.difficulty(idol, 'produce-007', tail)
    cfg = row['produceExamBattleConfigId']
    print(stage, 'criteria', cat.criteria(cfg))
    for params in ({1: 500, 2: 400, 3: 400}, {1: 900, 2: 700, 3: 700}, {1: 1500, 2: 1200, 3: 1200}, {1: 2500, 2: 2000, 3: 2000}):
        bp = cat.base_permils(cfg, params)
        print('   params', params, 'base_permils', bp, 'penalty', cat.penalty_permil(cfg, params))