# 最后一版 v7 开场白（2026-11-28 凌晨定稿）

> 用法：新会话第一句话发
> 「读 docs/INDEX.md → docs/HANDOVER_NEXT.md 顶部 2026-11-28 凌晨 v6 条 → docs/OPENING_v7.md →
> docs/GKBENCH.md §22 → docs/RELEASE_V5.md，然后按 OPENING_v7 §3 的顺序做最后一版 v7。」

## 1. 现状（全部已提交）

| 算法 | 我们自算 240 槽 | vs v5 | oracle 均值 | 对外 geo | over | 步数/起点 |
|---|---:|---:|---:|---:|---:|---:|
| **gkagent-ex-seed-v6**（v6 定稿） | **1,461,263** | **+14,226 / +0.98%** | **0.9698** | **0.9435** | 36 | 23.3 |
| gkagent-ex-seed-v5 | 1,447,036 | — | 0.9535 | 0.9232 | 8 | 10.8 |
| gkagent-ex-seed-v4 | 1,372,156 | −74,881 | 0.9227 | 0.9020 | 13 | ~6 |
| （参考）best-known | 1,486,205 / n=928；1,452,088 / n=960 | | | | | |

- **官方单行 n=240 = 1,461,263**（eval 661dffa3b25f + 2 次 resume，parallel 6，≈86min）：errors 0 /
  p50 3,846ms / p95 7,002 / max 76,341 / ep_think 124s。**站上 seed 赛道第 2（第 1 是 n=928 的 best-known）、
  hosted/外部投稿第 1**。
- 提交：主仓 **462a077**、bench_repo **cd35efa**（feat v6）+ **30884ef**（RESULTS）。（注意：主仓 2026-11-28
  做过**历史脱敏重写**，旧哈希全部失效，见 docs/ARCHIVE.md §6；bench_repo 是独立仓库不受影响。）
- 仓库：**GitHub 公开** https://github.com/xingkonghod/gakumas-agent （AGPL-3.0-or-later）；
  Gitee 私有存档同步。**新提交不得带 token / 保密种子 / 账号信息**；新探针先不入库、结果脱敏后再提交。
- 外部：`gakumas-engine-seedlock-v1`（huochai67，sees_seed）n=360 = 1,062,810 / 5s 预算 / over 12 —— 仍落后我们 ~37%。

## 2. v6 诊断（细节见 GKBENCH §22，必须读）

- **① 墙钟构成**（v5 240 局 8,000 步）：锁定后每步只用 **2.4s / 7s**（6,898 锁定步空转 35,359s = 2.9×）；
  v5 的 over 全在**锁定前候选管线**（12k 候选时单步 10.5–27s）；v5b 的 over=57 = 18 起点 × 4s deadline ÷ 4 线程的
  batch overshoot（注意 `core_search` 的 **status 0 = 无内部失败，撞 deadline 也是 0**）。
- **② v6 机制**：预算内自适应波次 = 流水线发起点 + 准入（剩余 ≥ 预期×1.25+0.10）+ 单次 deadline=min(4.0, 预期×1.5)
  + anytime 预算尾巴（deadline=剩余−0.15，不越界）+ `max_starts=24`；v5 逐位复现路径保留。
- **全量结果**：+0.98%（CI 跨 0）、**MID +58,861/槽 / FINAL −22,292/槽**、每步起点 23.3、总 think 29,755s（+66%）。
- **③ over 8→36 的根因（v7 主修）**：深局 24 起点时单步 12–21s，而 `pool_expect_ms` 只有 0.81–1.42s
  → **`session.clone()`/状态拷贝/线程排队没计入准入**（deadline 只约束 C 搜索）；另 4 步 >40s（最大 76.3s）
  是运行中一次 DNS 断链事故的伪影（已 `--resume` 补齐）。
- **⑤ tail_turns=3 已验证可行**：生产路径下 `turns_left=3` 的精确尾 **14–21ms 就 complete**
  （nodes ~800–1,300），随后 `pool.proven=True` 不再搜。
- **单槽完全不可比**（硬证据）：同算法同槽复跑（门 vs 全量同 30 槽）sd 1.77M、max|Δ| 6.14M
  ⇒ **只认 240 槽聚合 + oracle 比例 + over**，30 槽门只看方向。

## 3. v7 任务（顺序固定；做完就是最后一版）

### ① clone/prep 计入准入（主修，必须做）
- 先量：`session.clone()` 墙钟、`prep_seconds` 随局面深度/牌数的变化；把「提交→future 完成」的**总墙钟**
  （clone + prep + search）作为 expect 样本，准入改用它 ×1.25；deadline 仍只约束 C 搜索（预期×1.5，cap 4s）。
- 备选（按顺序试）：clone 移进 worker（并行拷贝）/ 按深局自适应降 `max_starts` / `pool_threads` 分档。
- **验收**：深局步 ≤8s、over ≤8（不高于 v5）、同墙钟有效搜索 +20–30%。

### ② tail_turns=3 采纳（近乎免费）
- 直接 `tail_turns=3`；跑 3–5 局 dev seed 确认 tail 步仍 `complete`、think 不明显增加。

### ③ FINAL 专项（132 槽 = 68% 分数，v6 在这层 −22,292）
- 先分析：FINAL vs MID 的 step 结构/起点效率/over；候选：FINAL `max_starts` 28–32、`pool_threads` 5–6、
  portfolio 权重向 i16/s5 倾斜、lock≥4 的 pre-lock（mirror_vote / 更多世界 / 更早锁定）。
- 门：与 v6 同槽配对（10–15 大决赛），只看方向；**最终判据仍是 240 聚合**。

### 流程
1. ①+② 实现 → 本地 1–2 局冒烟（确认无异常、步时/起点数正常）。
2. **30 槽小样门**（15 题 = 10 个大决赛 + 3 MID + 2 lock≥4；同槽对 v6 看 Δ/oracle 比例/over/每步起点）。
3. 过门后**一次性单 eval 全量 240**（不带 `--only`、parallel 6、budget 10，~90min），断了 `--resume`。
4. 判据：240 聚合 meanΔ、oracle 比例、over；**目标先 1.48M、摸 1.50M**（1.461M +39k）。
   1.6M 不写进承诺（需换维度：引擎吞吐/策略引导，现架构看不到证据）。

## 4. 命令 / 坑（沿用，别踩）

- v7 起点：`copy data/bench_repo/submissions/gkagent-ex-seed-v6 → gkagent-ex-seed-v7`，类名 `ExSeedV7Algo`、
  `name="gkagent-ex-seed-v7"`；**v6/v5/v4 原版零改动**。
- 评测：`python -m gkbench eval --set hif --algo \Games\gakumas-agent\data\bench_repo\submissions\gkagent-ex-seed-v7\algo.py:ExSeedV7Algo --seeds 2 --parallel 6 --budget 10`
  （最终版**不带 --only** → 单 run/n=240、行不拆；中途验证可用 `--only`）。
- **gkbench 的 `--resume` 会遍历全部 505 题** → 必须配 `--only <120 核心题>`（`out/_hif_core_ids.json` 或
  `/api/sets` 的 core）；params 必须与上次完全一致，否则站上按 params 拆行。
- 只补缺题（同题同种子「取最新」会覆盖旧分）；**跑托管时别开本地重探针**（污染步时）；
  服务器重启 eval 404 → 按缺槽重建（params 一致）。
- 内存 <700MB 先等；单次评测注册表在服务器内存。

## 5. 纪律（不变）

- **DLL 不重编**（改引擎只在外部 `data/GKMSMainWheel` 按路径 import/编译并注明 provenance，不拷 src）；
  AGPL 只外部引用；不碰 `D:\Games\Gakumas`、`C:\GakumasLocal` 只读。
- **仓库已公开**：不提交 token/保密种子/账号信息；新探针（`data/_v7_*`、`out/`）先不入库、结果脱敏后再提交；
  pathspec 提交（禁 reset/checkout -a）。
- 每阶段 feat+docs；结束更新 **HANDOVER_NEXT**（新交接条）+ **GKBENCH §23**（v7 结果/负结果）+ OPENING_v7 §7。
- pytest（只改 src 时）用 `--basetemp=out/_pytest_tmp_*`。

## 6. 一句话

**v6 已经把「每步空转」换成 23 个有准入保证的起点（+0.98%，over 反涨）。v7 最后一版要修的是
「深局的无效墙钟（clone/prep 未入准入）」+「免费的第 3 回合精确尾」+「FINAL 专项」，
把 1.461M 推到 1.48–1.50M；再往上就是换维度的事，不再是调度。**