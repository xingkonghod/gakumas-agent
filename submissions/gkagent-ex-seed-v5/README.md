# gkagent-ex-seed-v5（v4 + 预算饱和多波次并行 RoutePool：把每步空转的墙钟换成更多独立起点/搜索配置）

**承 v4 全部机制**（自锁种子 + 失锁重扫 + 消费图 graph-clean 门 + 规模自适应起点 starts_hi=6 +
core_tail 精确尾 + 去墙钟扫描等待 + `vote_sec_cap=0.8`），**改的是搜索调度/搜索质量**。
基础 = `gkagent-ex-seed-v4`（copy 后改，**v2/v3/v3g/v4 原版零改动**，vendor DLL/exe MD5 与 v4 全一致，不重编）。

`needs_gkms=True`、类属性 `sees_seed=False`（不拿裁判的 ctx.seed / ctx.true_session）、
**`about.sees="seed"` 如实声明看牌序**。入口 `algo.py:ExSeedV5Algo`。

## 动机（v4 托管 240 局逐步记录实测，`data/_v5_lockscan.py`）

- 每步 10s 预算**只用了 2.3–4.3s**：GNRPA 的 transitions 帽（500k/起点）≈0.5s 先到，剩余墙钟空转。
  240 局里 238 局都锁上了（只有 2 局失锁）→ **缺口不是「锁不住」，是锁定后的搜索质量**。
- 「深度」已证伪（v4 门 b1：500k→1M→2M 同分；v5 复测 2M 也不改变终局分），**独立起点/不同搜索配置**才有用。
- 同状态多 sd 重启的终局分分布（`data/_v5_restart_curve.py`）：AS-AXME8QK2 turn4 12 个起点
  6.11M–9.70M（1.6× 跨度）、AS-BZXB28YJ turn4 1.64M–5.37M（3.3×）→ 值得多撒起点，但**多数 sd 会收敛到同一条路线**。

## v5 改了什么（三条，全部单调安全）

| # | 机制 | 说明 |
|---|---|---|
| ① | **多波次填满预算**（`waves=0`） | 一波 `starts` 个起点跑完后，只要 `t_end`（0.7×预算）前还有时间就再发一波（新 sd `+104729×wave`）。**wave 0 与 v4 逐位同口径**（6 起点 × base 配置），额外波次才是新增搜索；RoutePool 只采纳更高终局分 → 机制上单调不减 |
| ② | **并行起点**（`pool_threads`/`pool_threads_hi`） | 一波内每个起点在自己的 **core 副本**上并行搜（`native session.search_tables()` 本就给每会话一份自己的 core；ctypes 调用释放 GIL）→ 同等墙钟起点数 ×2（中期）/×4（`limit_turn>=12` 决赛） |
| ③ | **搜索配置组合**（`portfolio`） | 额外波次逐起点轮换 GNRPA 的 `(levels,iterations,stabilization)`。固定状态探针（`data/_v5_engine_grid.py`）：同一状态 `s=5` 在 AS-5KZSXANK **+31%**、`iterations=16` 在 AS-AXME8QK2 **+26%**，但**没有一组全胜** → 组合取 max 单调安全 |

尾部不变：剩 ≤2 回合时整段剩余时间跑 `core_tail`（node_cap 20M，complete 即证最优，证完不再搜）。

## 负结果（都做过探针/门，默认关，只留在门里当对照臂）

- **root_scan（根动作枚举）**：每个合法首动作先走一步再完整续搜——离线 2 局 −9% / −1%（AS-WDKWQYW5 / AS-AXME8QK2），
  托管 5 槽中性 → **不采纳**（说明 GNRPA 的首动作选择本身已经覆盖得不错）。
- **mirror_vote（锁定前用候选镜像后验投票）**：机制在实测里几乎不触发（候选管线在 worlds 投票前就已锁定）；
  托管 5 槽 2 胜 3 负 CI 跨 0 → 默认关。
- **固定搜索配置 i16/s5**：同状态 +10–25%，但**整局配对 A/B 中性**（AS-AXME8QK2 −0.8%、AS-WDKWQYW5 +0.07%）
  —— 因为终局分大头由精确尾+早期动作决定，中途搜索的「终局分估计」变好不一定改变动作 → 只进组合臂，不做缺省。
- **并行+填满但无 portfolio**：离线 2 局中性（−9% / −1%，在 root_scan 那双局里同批）。

## 目录

| 文件 | 内容 |
|---|---|
| `algo.py` | 入口 `ExSeedV5Algo`：v4 状态机 + ①②③（`waves`/`pool_threads`/`portfolio`，全参数化，可逐位复现 v4） |
| `vendor/m1_graph.py` + `m1_rng_index.json` | clean-room 消费图 graph-clean 门（承 v3g） |
| `vendor/{draws,fastcut,opening,seedscan}.py` + `seed_scan.c/.exe` | 复制自 v4（exe 不重编） |
| `vendor/gkmscore.dll` + `NOTICE.txt` | 复制自 v4（MD5 659942B2…，不重编） |
| `submission.json` | label=gkagent-ex-seed-v5，sets=hif/hajime，step_seconds=10 |

## 跑

     cd data\bench_repo
     ..\..\.venv\Scripts\python.exe -m gkbench eval --set hif --algo \Games\gakumas-agent\data\bench_repo\submissions\gkagent-ex-seed-v5\algo.py:ExSeedV5Algo --seeds 2 --parallel 3 --budget 10

缺省参数：`waves=0 / pool_threads=2 / pool_threads_hi=4 / portfolio=2/8/5,2/16/3,2/16/5,3/8/5,2/4/8,3/16/5 /
root_scan=0 / tail_turns=2 / starts4+starts_hi6 / vote_sec_cap=0.8 / rescan_open=1`。
**逐位复现 v4**：`waves=1, pool_threads=1, pool_threads_hi=1, portfolio="", root_scan=0`。
分块托管驱动 `data/_v4_hosted.py`（不提交）。成绩见 `RESULTS.md`。

## 许可

AGPL-3.0-or-later（gkbench 生态；引擎与内核 AGPL 外部引用，不拷入 src/gkagent；m1_graph 为 clean-room 自写）。见 NOTICE。