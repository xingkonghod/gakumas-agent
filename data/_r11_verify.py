"""P2 一次性：r11 入库完整性 + 能量份额实测。不提交。"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkagent.sim.policy_mlp import PolicyMLP

# 1. 入库完整性
tracked = ROOT / "data/knowledge/ei_policy_v6.json"
src = ROOT / "out/ei_r11_v11_mix.json"
m_track = PolicyMLP.load(tracked)
m_src = PolicyMLP.load(src)
for attr in ("mean", "scale", "w1", "b1", "w2", "b2", "out_w", "out_b"):
    assert np.array_equal(getattr(m_track, attr), getattr(m_src, attr)), attr
print("入库权重 == out/ei_r11_v11_mix.json 逐位一致 ✅")
prod = m_track.meta.get("production", {})
print("production.revision:", prod.get("revision"))
print("production.source:", prod.get("source"))
print("val_metrics:", m_track.meta.get("val_metrics"))
print("mix.upsample_small:", m_track.meta["mix"].get("upsample_small"))
print("mix.scenario_std:", m_track.meta["mix"].get("scenario_std"))

# 2. 能量份额实测（Σy² 代理，R9_ANALYSIS §2 口径）
def load(name):
    d = np.load(ROOT / "out" / name, allow_pickle=False)
    return d["X"], d["y"], json.loads(str(d["meta_json"]))

_, ys, ms = load("ei_r11_selfplay_small.npz")
_, yl, ml = load("ei_r11_selfplay_large.npz")
_, yd, md = load("ei_r11_demos.npz")
small_std = float(ys.std()); large_std = float(yl.std())
# norm-by-scenario：各除自身 std
ys_n = ys / max(small_std, 1e-6)
yl_n = yl / max(large_std, 1e-6)
# 行数（训练实际：small ×2 = 291130 / large 128103 / demos 下采样 48294）
mix = m_track.meta["mix"]
n_small = mix["upsample_small"]["post_small_rows"]
n_large = mix["upsample_small"]["post_large_rows"]
n_demos = mix["demo_rows"]
e_small = float(np.mean(ys_n ** 2)) * n_small
e_large = float(np.mean(yl_n ** 2)) * n_large
e_demos = float(np.mean(yd ** 2)) * n_demos
total = e_small + e_large + e_demos
print(f"\n能量份额实测（norm-by-scenario + small ×2）:")
print(f"  small std={small_std:.4f} large std={large_std:.4f}")
print(f"  small {n_small} 行 energy={e_small:.0f} share={e_small/total*100:.1f}%")
print(f"  large {n_large} 行 energy={e_large:.0f} share={e_large/total*100:.1f}%")
print(f"  demos {n_demos} 行 energy={e_demos:.0f} share={e_demos/total*100:.1f}%")
print(f"  （R9_ANALYSIS §6 候选② 预测 small →~66%）")
