"""f2-norm 离线 sanity（不提交）：验证 gkagent-ei-r13-norm 归一化开关。

1. 合成 obs：各模式 137 维有限 / 动作合法 / 硬规矩 / clip 后标准化输入有界 / rescale 正确。
2. off 与 r13 逐位一致（合成 + 真实探针回放，score_vector / argmax / decide 动作）。
3. 真实探针回放（data/_f2_probe_obs.jsonl）：各模式合法性 + 硬规矩 + 无推理异常。
4. OOD 收敛证据：score / 全体 mean|z| 在 off / rescale / clip / both 下的变化。

    .venv\\Scripts\\python.exe data\\_f2norm_sanity.py
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp); sys.modules[name] = m; sp.loader.exec_module(m)
    return m


r13 = load("r13_algo", ROOT / "data/bench_repo/submissions/gkagent-ei-r13/algo.py")
norm = load("norm_algo", ROOT / "data/bench_repo/submissions/gkagent-ei-r13-norm/algo.py")

CHECKS = 0; FAILURES = []
def check(cond, msg):
    global CHECKS; CHECKS += 1
    if not cond:
        FAILURES.append(msg); print("  X", msg)

def ctx(obs, loadout=None, meta=None):
    return SimpleNamespace(obs=obs, budget=5.0, loadout=loadout or {}, meta=meta or {})

PROFILES = json.loads((ROOT / "data/bench_repo/submissions/gkagent-ei-r13-norm/card_profiles.json").read_text(encoding="utf-8"))["cards"]
_levels = {}
for k in PROFILES:
    cid, _, lv = k.partition("|"); _levels.setdefault(cid, set()).add(int(lv))
MULTI = sorted(cid for cid, lvs in _levels.items() if {0, 1, 2} <= lvs)
CID_A, CID_B, CID_C = MULTI[0], MULTI[len(MULTI) // 2], MULTI[-1]

def base_obs(**over):
    obs = {
        "v": "uiobs.v1",
        "exam": {"produce": "produce-008", "step": "AUDITION_MID1", "plan": 3,
                 "turn": 3, "limit": 9, "types": [1] * 9, "permil": [20000, 30000, 25000],
                 "crit": [1871, 1392, 1088]},
        "num": {"score": 12345, "stamina": 20, "max_stamina": 36, "block": 5, "playable": 1, "plays": 0},
        "stance": [None, 0],
        "status": [["lesson_buff", 3, -1], ["review", 2, -1], ["aggressive", 4, -1],
                   ["full_power_point", 7, -1], ["parameter_buff", 2, 2]],
        "ench": [],
        "hand": [{"id": CID_A, "u": 0, "p": 1}, {"id": CID_B, "u": 1, "p": 1}, {"id": CID_C, "u": 0, "p": 0}],
        "deck": [{"id": CID_A, "u": 1}, {"id": CID_B, "u": 0}, {"id": CID_C, "u": 2}],
        "grave": [{"id": CID_B, "u": 1}], "hold": [], "lost": [{"id": CID_C, "u": 0}], "played": [],
        "drinks": ["pdrink_00-3-005"], "legal": [["play", 0], ["play", 1], ["drink", 0], ["end"]],
    }
    obs.update(over); return obs

FI = {n: i for i, n in enumerate(norm.FEATURE_NAMES)}
MODES = {
    "off": dict(norm_mode="off"),
    "clip2": dict(norm_mode="clip", clip_k=2),
    "clip3": dict(norm_mode="clip", clip_k=3),
    "clip4": dict(norm_mode="clip", clip_k=4),
    "rescale": dict(norm_mode="rescale"),
    "rescale_buffs": dict(norm_mode="rescale", rescale_buffs=1),
    "both": dict(norm_mode="both", clip_k=3),
    "both_buffs": dict(norm_mode="both", clip_k=3, rescale_buffs=1),
}

print("== 1. 合成 obs：各模式有限 / 合法 / 硬规矩 / 有界 / rescale 正确 ==")
# 高 OOD 合成 obs：大分数 + 大 buff + 高倍率
ood_obs = base_obs(num={"score": 500000, "stamina": 20, "max_stamina": 36, "block": 60, "playable": 1, "plays": 0},
                   status=[["lesson_buff", 3, -1], ["review", 40, -1], ["aggressive", 30, -1],
                           ["review_multiple", 1.5, 2], ["full_power_point", 7, -1]],
                   exam={"turn": 3, "limit": 9, "types": [1] * 9, "permil": [40000, 45000, 35000], "crit": [0, 0, 0]})
for name, params in MODES.items():
    a = norm.EiR13NormAlgo(**params); a.begin(ctx(base_obs()))
    for tag, obs in [("base", base_obs()), ("ood", ood_obs),
                     ("nopermil", base_obs(exam={"turn": 3, "limit": 9, "types": [1] * 9, "permil": [0, 0, 0]})),
                     ("noexam", base_obs(exam={}))]:
        st = a._state(obs)
        X = np.asarray([norm.decision_features(st, st.hand[i]) for i in range(len(obs["hand"]))])
        check(X.shape[1] == 137 and bool(np.all(np.isfinite(X))), f"1/{name}/{tag}: 137 维有限")
        d = a.decide(ctx(obs))
        legal = [tuple(x) for x in obs["legal"]]
        check(tuple(d.action) in legal, f"1/{name}/{tag}: 动作合法 {d.action}")
        check(d.action[0] == "play", f"1/{name}/{tag}: 硬规矩（有可出牌必 play）")
        check("error" not in d.meta, f"1/{name}/{tag}: 无推理异常 {d.meta.get('error')}")
        # clip 有界：标准化后裁剪到 ±K
        if params.get("norm_mode") in ("clip", "both"):
            K = params.get("clip_k", 3)
            Z = (X - a.net.mean) / a.net.scale
            Zc = np.clip(Z, -K, K)
            check(float(np.abs(Zc).max()) <= K + 1e-12, f"1/{name}/{tag}: clip 后有界 <= {K}")
    # rescale 正确性：score 列除以 scale；buffs 开关
    a2 = norm.EiR13NormAlgo(**params); a2.begin(ctx(ood_obs))
    st = a2._state(ood_obs); scale = a2._exam_scale(ood_obs)
    Xraw = np.asarray([norm.decision_features(st, st.hand[i]) for i in range(len(ood_obs["hand"]))])
    Xr = a2._rescale_features(Xraw, scale) if params.get("norm_mode") in ("rescale", "both") else Xraw
    check(abs(scale - 40.0) < 1e-9, f"1/{name}: exam_scale=mean(40000,45000,35000)/1000=40, got {scale}")
    if params.get("norm_mode") in ("rescale", "both"):
        check(np.allclose(Xr[:, FI["score"]], Xraw[:, FI["score"]] / scale), f"1/{name}: score 列除以 scale")
        # 动作特征（104:）不动
        check(np.array_equal(Xr[:, 104:], Xraw[:, 104:]), f"1/{name}: 动作特征不动")
        if params.get("rescale_buffs"):
            check(np.allclose(Xr[:, FI["vitality"]], Xraw[:, FI["vitality"]] / scale), f"1/{name}: buffs vitality 除以 scale")
        else:
            check(np.array_equal(Xr[:, FI["vitality"]], Xraw[:, FI["vitality"]]), f"1/{name}: rescale_buffs=0 时 vitality 不动")
    else:
        check(np.array_equal(Xr, Xraw), f"1/{name}: off/clip 不改原始特征")
print(f"1 完成：{CHECKS} 检查，{len(FAILURES)} 失败")

print("\n== 2. off 与 r13 逐位一致（合成） ==")
a_off = norm.EiR13NormAlgo(norm_mode="off"); a_ref = r13.EiR13Algo()
a_off.begin(ctx(base_obs())); a_ref.begin(ctx(base_obs()))
for obs in [base_obs(), ood_obs, base_obs(stance=["OverPreservation", 2]),
            base_obs(num={"score": 0, "stamina": 0, "max_stamina": 36, "block": 0, "playable": 0, "plays": 1}, legal=[["end"]])]:
    so, sr = a_off._state(obs), a_ref._state(obs)
    Xo = np.asarray([norm.decision_features(so, so.hand[i]) for i in range(len(obs["hand"]))]) if obs["hand"] else np.zeros((0, 137))
    Xr = np.asarray([r13.decision_features(sr, sr.hand[i]) for i in range(len(obs["hand"]))]) if obs["hand"] else np.zeros((0, 137))
    check(np.array_equal(Xo, Xr), "2: off 决策特征与 r13 逐位一致")
    if Xo.shape[0]:
        check(np.array_equal(a_off.net.score_vector(Xo), a_ref.net.score_vector(Xr)), "2: off score_vector 与 r13 逐位一致")
    do, dr = a_off.decide(ctx(obs)), a_ref.decide(ctx(obs))
    check(tuple(do.action) == tuple(dr.action), "2: off decide 动作与 r13 一致")
print(f"2 完成：{CHECKS} 检查，{len(FAILURES)} 失败")

print("\n== 3. 真实探针回放：各模式合法 + 硬规矩 + 无异常；off≡r13 ==")
probe = ROOT / "data" / "_f2_probe_obs.jsonl"
rows = [json.loads(l) for l in probe.read_text(encoding="utf-8").splitlines()]
print(f"  探针 {len(rows)} 行")
# 每模式一个实例；off 与 r13 并跑比对
inst = {name: norm.EiR13NormAlgo(**p) for name, p in MODES.items()}
ref = r13.EiR13Algo()
begun = {name: False for name in MODES}; ref_begun = False
stats = {name: dict(steps=0, play=0, end=0, other=0, err=0) for name in MODES}
off_mismatch = 0
# OOD 统计（off / rescale / both）：score 与全体 |z|
ood = {m: dict(score_absz=0.0, all_absz=0.0, n=0, maxz=0.0, clipped=0, entries=0) for m in ("off", "rescale", "both")}
for row in rows:
    obs = row["obs"]
    if row["kind"] == "begin":
        for name, a in inst.items():
            a.begin(ctx(obs, loadout=row.get("loadout"), meta=row.get("meta"))); begun[name] = True
        ref.begin(ctx(obs, loadout=row.get("loadout"), meta=row.get("meta"))); ref_begun = True
        continue
    if not ref_begun:
        ref.begin(ctx(obs)); ref_begun = True
    for name, a in inst.items():
        if not begun[name]:
            a.begin(ctx(obs)); begun[name] = True
    legal = [tuple(x) for x in obs.get("legal") or []]
    has_play = any(x[0] == "play" for x in legal)
    dref = ref.decide(ctx(obs))
    for name, a in inst.items():
        d = a.decide(ctx(obs)); s = stats[name]; s["steps"] += 1
        if tuple(d.action) not in legal: s["err"] += 1
        if has_play and d.action[0] != "play": s["err"] += 1
        if "error" in d.meta: s["err"] += 1
        s[d.action[0] if d.action[0] in ("play", "end") else "other"] += 1
        if name == "off" and tuple(d.action) != tuple(dref.action): off_mismatch += 1
    # OOD 统计：用 off 实例的特征（原始），分别模拟 off/rescale/both 的标准化输入
    a = inst["off"]; st = a._state(obs)
    pi = [int(x[1]) for x in legal if x[0] == "play" and len(x) > 1 and 0 <= int(x[1]) < len(obs.get("hand") or [])]
    if pi:
        X = np.asarray([norm.decision_features(st, st.hand[i]) for i in pi])
        scale = a._exam_scale(obs)
        for m in ("off", "rescale", "both"):
            Xm = X.copy()
            if m in ("rescale", "both") and scale > 0 and scale != 1.0:
                Xm = a._rescale_features(Xm, scale)
            Z = (Xm - a.net.mean) / a.net.scale
            o = ood[m]; o["n"] += 1
            o["score_absz"] += float(np.abs(Z[:, FI["score"]]).sum())
            o["all_absz"] += float(np.abs(Z).sum()); o["entries"] += Z.size
            o["maxz"] = max(o["maxz"], float(np.abs(Z).max()))
            if m == "both":
                o["clipped"] += int((np.abs(Z) > 3).sum())
for name, s in stats.items():
    check(s["err"] == 0, f"3/{name}: 回放违规 {s['err']}")
    print(f"  {name:14s} steps={s['steps']} play={s['play']} end={s['end']} other={s['other']} err={s['err']}")
check(off_mismatch == 0, f"3: off 与 r13 动作不一致 {off_mismatch} 步")
print(f"  off≡r13 动作不一致步数 = {off_mismatch}")
print("  OOD 收敛（真实探针，决策步聚合）：")
for m, o in ood.items():
    if o["n"]:
        print(f"    {m:8s} score mean|z|={o['score_absz']/o['n']:8.2f}  全体 mean|z|={o['all_absz']/o['entries']:6.3f}  max|z|={o['maxz']:9.1f}"
              + (f"  clip3 裁剪占比={o['clipped']/o['entries']*100:.2f}%" if m == "both" else ""))
print(f"3 完成：{CHECKS} 检查，{len(FAILURES)} 失败")

print(f"\n总计 {CHECKS} 项检查，{len(FAILURES)} 失败")
if FAILURES:
    for f in FAILURES[:30]: print("  -", f)
    sys.exit(1)
print("全部通过 ✓")