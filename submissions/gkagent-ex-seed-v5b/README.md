# gkagent-ex-seed-v5b（v5 同机制，多波次上限 2→3：每步 18 个独立起点）

**v5 的强度版**：机制与 v5 完全一致（v4 + 多波次并行 RoutePool + GNRPA 配置组合），唯一改动是
`waves=2 → 3`（每步从 12 个独立起点提到 18 个）。存在理由：v5 托管 240 槽 = **1,447,036**（v4 +5.46%），
但官方合并因 11 个槽来自早期候选配置而分成 3 行（同参数行 n=230 = 1,458,384）；v5b 用**统一配置全量重跑 240 槽**，
既验证「再加一档波次是否还有增益」，也拿到干净的 n=240 单行。

基础 = `gkagent-ex-seed-v5`（copy 后改，**v2/v3/v3g/v4/v5 原版零改动**；vendor DLL/exe MD5 与 v4/v5 全一致，不重编）。

`needs_gkms=True`、`sees_seed=False`（只读 ctx.obs / ctx.loadout）、**`about.sees="seed"` 如实声明看牌序**。
入口 `algo.py:ExSeedV5bAlgo`。

## 机制（同 v5）

| # | 机制 | 参数 |
|---|---|---|
| ① | 多波次：一波 `starts` 个起点跑完，`t_end`（0.7×预算）前还有时间就再发一波（新 sd `+104729×wave`） | **waves=3**（v5 是 2） |
| ② | 并行起点：每个起点在自己的 core 副本上并行搜（`session.search_tables()`，ctypes 释放 GIL） | threads=4 |
| ③ | 搜索配置组合：逐起点轮换 `(levels,iterations,stabilization)` | `2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8` |

其余与 v5 一致：`starts=4 / starts_hi=6(12 回合决赛) / lock_trans=2M / step_trans=500k / vote_sec_cap=0.8 /
rescan_open=1 / tail_turns=2 / forced_play=0 / prior=0 / root_scan=0 / mirror_vote=0`。
RoutePool 只采纳更高终局分 → 全机制**单调安全**；`waves=1 + threads=1 + portfolio 空` 可逐位复现 v4。

## 跑

     cd data\bench_repo
     ..\..\.venv\Scripts\python.exe -m gkbench eval --set hif --algo \Games\gakumas-agent\data\bench_repo\submissions\gkagent-ex-seed-v5b\algo.py:ExSeedV5bAlgo --seeds 2 --parallel 5 --budget 10

分块托管驱动 `data/_v4_hosted.py gkagent-ex-seed-v5b 6 60 5`（只补缺题，`done_slots` 走 `/api/runs`）。成绩见 `RESULTS.md`。

## 许可

AGPL-3.0-or-later（gkbench 生态；引擎/内核 AGPL 外部引用不拷 src；m1_graph clean-room 自写）。见 NOTICE。