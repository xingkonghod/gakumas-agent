# submissions/ —— 投稿快照（本仓备份）

这里是 `data/bench_repo/submissions/<algo>/` 的**逐字节快照**。`data/bench_repo` 是官方 gkbench 仓库的本地克隆
（`.gitignore` 排除、无远端），所以把真正参赛的代码在这里再存一份，保证私有仓里有完整可复现的投稿。

| 目录 | 说明 | bench_repo 提交 |
|---|---|---|
| `gkagent-ex-seed-v5/` | v5（waves=2/threads=4/portfolio），240 槽 1,447,036；官方行 n=230 = 1,458,385 | `3ef3f83` + `4942f3d` + `f0a8144` |
| `gkagent-ex-seed-v5b/` | v5b（waves=3）负结果 1,398,855（vs v5 −3.33%，over 8→57） | `cc0a35e` |
| `gkagent-ex-seed-v6/` | **v6（预算内自适应波次/准入控制）240 槽 = 1,461,263 新 PB**（+0.98% vs v5，oracle 比例 0.9698） | `cd35efa` + `30884ef` |

- 许可证：算法代码 AGPL-3.0-or-later（见各目录 `NOTICE`）；`vendor/gkmscore.dll`、`vendor/seed_scan.exe`
  是第三方产物，按 AGPL 引用分发、**不重编**（MD5 与 v4 全一致）。
- 引擎按路径外部引用：`GKMS_ROOT` 指向 GKMSMainWheel 克隆（本仓不含其 src，见 `docs/RELEASE_V5.md §2`）。
- 托管复现：`python -m gkbench eval --set hif --algo <本目录>/algo.py:ExSeedV6Algo --seeds 2 --parallel 6 --budget 10`
  （断了用 `--resume <eval> --only <120 核心题>`；gkbench 的 `--resume` 会遍历全部 505 题，必须配 `--only`）。