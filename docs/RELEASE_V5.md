# v5 开源/发群前整理（2026-11-27 定稿）

> 用户口径：**达标后群里全部开源**；发群前把 **v5 复现脚本 + 成绩表**整理好。
> 本文件 = 发群清单 + 口径 + 禁止项。

## 1. 成绩表（对外口径，240 槽同口径）

| 算法 | 槽数 | 均分 | vs v4 | vs best-known 1,452,088 | oracle 比例 | over | errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| gkagent-ex-seed-v4 | 240 | 1,372,156 | — | 94.5% | 0.9227 | 13 | 0 |
| **gkagent-ex-seed-v5（waves=2）** | 240 | **1,447,036** | **+74,881 / +5.46%** | **99.65%** | **0.9535** | 8 | 0 |
| gkagent-ex-seed-v5b（waves=3，负结果） | 240 | 1,398,855 | +26,699 / +1.95% | 96.3% | 0.9440 | 57 | 0 |
| （参考）best-known | 960 | 1,452,088 | — | 100% | 1.0 | 1 | 0 |
| （参考）榜顶 best-known | 928 | 1,486,205 | — | — | — | 1 | 0 |

- v5 官方合并行（同参数 230 槽；另 11 槽来自早期候选配置）= **1,458,384**（n=230）。
- v5b 官方合并行（单配置干净）= **1,398,855**（n=240）。
- v5 vs v4 240 槽逐槽：**130 胜 / 88 负 / 22 平**；FINAL +5,808,820（132 槽）/ MID1 +12,162,517（108 槽）。
- **站上 vs_oracle 口径（我们自算；合并行在站上显示 null）**：对 best-known farm 逐槽 oracle（232 配对槽）
  v4 geo 0.9020 / win 34.9% / 中位 0.9387 → **v5 geo 0.9232 / win 45.7% / 中位 0.9841**（v5b geo 0.9176 / win 43.1%）。
  **中位 0.984 = 一半的槽已到 farm 逐槽最大 98.4%**；win 45.7% = 近一半槽已等于或超过 farm 最大。
- **托管口径注意**：站上的行是「按 params 分组合并」的——同算法不同 params 会拆成多行（v5 因 11 个早期候选配置槽被拆成
  n=230/5/6 三行，`vs_oracle` 也是 null）；**下一次全量跑要一次性单 eval 覆盖 240 槽**（同 params 单 run），
  这样行才是 n=240 单行、逐局分数公开（`/api/runs/<run>`）、相对上限才有机会被站上算出来。
  单 eval 的风险是服务器重启会清评测（404）；断了就用 `--resume <eval>`，或按缺槽重建（**params 必须一致**，合并才仍是一行）。

口径说明（要写进群消息，避免被误读）：
- 排行榜均分是**各算法自己的槽位集合**的均值（我们 120 题 × 2 保密种子 = 240 槽；best-known 是 120×8=960 槽），
  不是同槽配对；同槽配对只能自己算。
- **同 config 重跑同一槽 ±5–7%（大槽 ±20%）** → 单槽不可比、只看 240 槽聚合；v5 的 +5.46% 是点估计
  （逐槽 sd 585k → meanΔ 的 95%CI 仍跨 0），方向由 130:88 胜率 + oracle 比例 +3.1pt 支撑。
- `over` = 单步 > 12.05s 的步数（**只打标不扣分**）；v5 over=8。
- `sees_seed=False` + `about.sees="seed"`：不读裁判种子，种子从画面自反推；与「看牌序」类算法同组比较。

## 2. 开源范围（能开 / 不能开）

**开**（AGPL-3.0-or-later，保留 NOTICE）：
- `data/bench_repo/submissions/gkagent-ex-seed-v5/`、`.../gkagent-ex-seed-v5b/`（algo.py + README + RESULTS + NOTICE + vendor 清单）
- 我们自写的 **sim / docs / scripts**（按仓库既有许可）
- 复现脚本（探针转正版、脱敏后）：`_v5_lockscan` / `_v5_restart_curve` / `_v5_engine_grid` / `_v5_final` /
  `_v5b_compare` / `data/_v4_hosted.py`（分块托管驱动）

**不开 / 只引用**：
- matto 的 token（`~/.config/gkbench/token`）—— 永不进仓库
- 保密种子数据 / `data/bench_local/gkbench_dl/**`（下载物）
- 第三方 AGPL 源码拷贝（`data/GKMSMainWheel`、`data/hiro`、GKMSProject/GKMSUINet 等）—— **只按路径外部引用**，
  分发时说明「需自备 GKMS 客户端/引擎克隆，按 GKMS_ROOT 引用」
- `vendor/gkmscore.dll` / `seed_scan.exe`（第三方产物，随投稿按 AGPL 引用分发、MD5 标注、不重编）

## 3. 复现（发群消息给这几行）

    git clone <our-repo> && cd gakumas-agent
    # 依赖 GKMS 引擎（AGPL 外部引用）：把 GKMSMainWheel 克隆放到 data/GKMSMainWheel
    .venv\Scripts\python.exe data\_v4_hosted.py gkagent-ex-seed-v5 6 60 5    # 分块托管，只补缺题
    .venv\Scripts\python.exe data\_v5_final.py                              # 240 槽逐槽配对 + 官方合并行

要点：`--seeds 2 --parallel 5 --budget 10`；驱动靠 `/api/runs` 判断缺槽，**不要重跑已结算槽**
（同题同种子「取最新」会覆盖旧分）；服务器偶发 SYN 丢包（`WinError 10060`）会自动停、`--resume <eval>` 续跑。

## 4. 发群消息草稿

> 【gkbench seed 赛道】v4 1,372,156 → **v5 1,447,036（+5.46%，240 槽；best-known 1,452,088 的 99.65%）**，
> 同参数官方合并行 1,458,384。
> 不是调参，是三条**单调安全**的搜索调度改动：① 每步没用完的墙钟换成**多波次独立起点**（RoutePool 只采纳更高终局分）；
> ② 一波内每个起点在**独立 core 副本**上并行（ctypes 释放 GIL，同等墙钟 2× 起点）；
> ③ 逐起点轮换 GNRPA 的 (levels,iterations,stabilization)（同状态探针 s5 +31% / i16 +26%，但没有一组全胜 → 组合作策略）。
> 顺带把 v4 托管 240 局的逐步记录全拉下来做了归因：**238/240 局其实都锁上了**，缺口是锁定后的搜索质量，不是失锁。
> 负结果也一起放出来：waves=3（每步 18 起点）反而 −3.33%（over 8→57、被 10s deadline 截断的搜索白烧）；
> 根动作枚举/候选镜像投票/固定 i16s5/填满预算 都是中性或负。
> 代码/文档 AGPL-3.0（不含保密种子、不含第三方源码拷贝，只按路径引用引擎）。

## 5. 下一维度（v6 方向，本轮已留证据）

1. **每墙钟秒的搜索吞吐**（真正的差距）：v5b 的 over 57 证明「加量」已顶到 deadline 墙；
   要提高的是 native 路径效率/线程调度（外部 GKMSMainWheel 仓编译，注明 provenance，不拷 src 进本仓）。
2. **策略/价值引导**（导航而非叶子）：B11 policy/advantage 在 large 显著超 beam，可作 GNRPA 的 prior/剪枝
   （注意 L1/L3 prior 历史全负，要做 per-problem 门控或作多起点之一）。
3. **`lock≥4` 的 11 槽（均分 588k）+ 8 个无 oracle 的 produce-008 低分槽（400–870k）** 是独立可攻点。
4. **精确尾 horizon**：tail_turns=3 先证 3 回合能在 8s 内 complete（当前深局 2 回合已 deadline）。

## 6. 待办

- [x] v5 / v5b 240 槽跑完并回填成绩表
- [x] docs（GKBENCH §21 / HANDOVER_NEXT / 本文件）提交
- [ ] 探针脚本转正（脱敏：去 `out/` 路径与 token 读取）
- [ ] 检查 NOTICE/许可证（投稿目录 + 仓库根）
- [ ] 用户确认后再发群