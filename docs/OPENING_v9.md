# OPENING_v9 —— 残差收口（55 槽 ≥90%）+ 自有 small sim（C++）/ 特化搜索（2026-11-28 晚）

> 新会话第一句话发：
> 「读 docs/INDEX.md → docs/OPENING_v9.md → docs/HANDOVER_NEXT.md 顶部 v9 条 → docs/GKBENCH.md §25，
> 然后按 OPENING_v9 §3 做 v9。」

## 1. 现状（v8 已定稿 = 当前 PB）

| 算法 | 全量 240 自算 | vs v7 | 锁定 | 备注 |
|---|---:|---:|---|---|
| **gkagent-ex-seed-v8**（定稿） | **1,507,935**（errors 0） | **+28,256 / +1.91%** | **239/240 锁上**（硬失败 1、重扫后锁上 11、软锁 0、掉线 0） | oracle 1.0002（geo 0.9753）、≥90% 槽 159→177、over 73；bench_repo **07ff69e** |
| gkagent-ex-seed-v7（上一版 PB） | 1,479,679 | — | 233/240 | 主仓 db1b2e8 / bench_repo d57c8ef |

- **v8 两件事都拿到了第一轮结果**（细节 [GKBENCH §25](GKBENCH.md) / `submissions/gkagent-ex-seed-v8/{README,RESULTS}.md`）：
  ① **真全锁**：失锁不判死 → rollback 重扫（`noskip`/`drop1..6`/回合快照/开局快照）→ 晚锁；掉线用锁定时刻快照
  一步重锁；锁前/失锁后 mirrors 后验信念 PIMC 替 `ctx.worlds(4)`；软核验/软锁白名单；M3 候选爆炸护栏；开局无抽牌预扫。
  **全量 239/240 锁上**（v7 的 6 个失锁槽 5 个正常锁上，F4FPT86S/0 572,891→**6.14M**）。
  ② **每槽 ≥90%**：s5 倾斜 portfolio + 起点 32 + 1M 深臂全层推广；**73 低槽 +14.60M（+23.1%，CI95 全正），35/73 修复**；
  **MID 从 −121,848/槽翻正到 +40,760/槽**；但**仍 55 槽 <90%**（73 里剩 38 + 17 个原达标槽掉回，其中 4 个兄弟槽）。
- **全量 240 定稿**（单 eval `12e5d319502b` + 2 次 resume 补网络断链）：**1,507,935** vs v7 +28,256/+1.91%；
  oracle 1.0002（geo 0.9753）；`over 14→73`（32 起点+1M 深臂用满预算，只打标不扣分）、p50 5,521 / p95 7,432ms。

## 2. v9 残差（55 槽 <90%；`data/_v8_residual.py` 可重跑）

| 组 | 槽（top） | 缺口量级 | 判据 |
|---|---|---:|---|
| **A 晚锁/重扫质量** | HTNFZWKG/0、QV6QCSN9/0-1、B38CARVV 两槽、3G6FFZZT/1、QQ6J5S39/1、VWAF2GDN/1 | ~3.3M | 锁 turn≥3 或重扫次数多；锁前决策走 worlds |
| **B 结构性弱** | WDKWQYW5 两槽（本轮大回退）、6SCJE43J/0、P8ZJTXNA/1、BNEERWGF/1、4JMD6HGX/1 | ~3.0M | 锁得早但终局低；P1 配方不够 |
| **C 已达标回退** | QQ6J5S39/0、YZESXMWW/1、YSNBNDV4/0、663NKTY4/1、ZT8WGCSW/1 | ~1.3M | 同锁回合；部分噪声，但 QQ6J5S39/0/YZESXMWW/1 两轮都低 |

## 3. v9 任务（顺序固定）

### W1 残差收口（bench_repo：v8 → v9，params 换新 tag，v8 原版零改动）
1. **P0′ 晚锁/重扫质量**：retry 两段化（`[0,2^31)`→补扫，减单次 3.4s→2×1.7s）；「最干净快照」排序（开局→上回合首步→drop-k）；
   锁前 `vote_sec_cap` 0.8→1.2（晚锁局多世界）；`_cut` 单独上限（`cut_use=0.55×budget`）+ retry 步 `wait≤0.45×budget` 压 over。
2. **P1′ 搜索配方**：1M 深臂固定用网格最优的 **`3/16/3`@1M**（不是轮换 500k 最优档）；MID 是否保留深臂做 A/B；
   起点 32 的准入实测（若 MID 步内起点 <20 → `admit_mult 1.25→1.15`）。
3. **P2 逐题预算表**：`pid_params.json`（loadout 哈希键，机制已接）——最差 15–20 题给 `step_trans=1M / deep_trans=2M /
   max_starts=40 / search_use=0.78 / portfolio`；定向 eval 迭代 **55 → 个位数**，再全量 240。
4. **验收**：定向 eval（55 题 110 槽）逐槽 ratio；已达标槽不退化；最终全量 240 单 eval（新 params tag）出官方单行。
   目标 240/240 ≥90% → 均值 ≥1,547,576；**不承诺 1.6M**（100% 天花板 1,597,934）。

### W2 自有 small sim（C++）+ 特化搜索（用户定调；与 W1 并行，先 S1）
> 战略在 GKBENCH §12：「自有引擎路线（不必成为 gkms、超越它）」「clean-room 自写、引擎当 oracle、不拷 AGPL 源码进 src」。
> 工具链已确认：VS2022 BuildTools + MSVC 14.44 + 自带 CMake/Ninja（无需装 Rust）。**官方 DLL 依然不重编**。

1. **S1（1–2 天）等价性/速度基准**：`data/_sim_equiv.py`——120 核心题 dev seed，逐步对比我们 `src/gkagent/sim` vs 官方引擎
   （legal/hand/deck/grave/hold/lost/score/stamina/multiplier）+ 终局分；同时测 Python sim 的 steps/s、rollout/s。
   门：合法动作 ≥99.9%、终局分 100%（或定位已知 gap）。
2. **S2（2–3 天）补 GMKS 改不了的**：按 S1 一致率排序补效果/RNG——P 道具（现 1181/1849）、hif 段（103/153）、
   随机生成卡、`ExamBuffConsumptionAdd`、fresh-buff 差一回合、塔 gimmick；每类跑 `sim_engine_ab` + 等价性。
   可对照 huochai67 的 `docs/reference` 六篇（MIT，只读参考，不拷代码）。
3. **S3（2–3 天）C++ 核心 + 特化搜索 v0**：C ABI 动态库（ctypes；POD 状态可 memcpy clone；f32 对齐官方口径）→
   beam/expectimax + 自写精确尾 + **ALNS（elite 切点续搜/局部修线）** + 锁前**浮点信念图/分层 PIMC**。
   部署方式：**sim 只提案，官方引擎锁 + 终局核分**。门：73/55 槽固定集 ≥ v8、假锁 0、over 不恶化。
4. **S4（长期）**：sim 转主决策引擎（官方退为锁/裁判对照），覆盖率扩到全 1849 段。

## 4. 命令 / 坑（沿用 v8）
- v9 起点：`copy submissions/gkagent-ex-seed-v8 → gkagent-ex-seed-v9`（类名/name 改 v9，`params` 变 → 站上新行；
  **v8/v7/v6/v5 原版零改动**）。
- 定向：`data/_v8_hosted.py low 6`（脚本里改 ALGO/ALGO_SPEC/类名）；分析 `_v8_final.py` / `_v8_sum.py` / `_v8_residual.py`。
- **`--resume` 必配 `--only <120 核心题>`**；只补缺题；**跑托管时不开本地重探针**；`10060` 断链 → eval 自动停 → `--resume`。
- 单槽不可比（同算法同槽 sd ~1M）→ 判据只用固定槽集合逐槽 ratio + 240 聚合 + over。
- 版本坑：改 `docs/*.md` 不要用 PowerShell `Set-Content`（会把 UTF-8 中文写坏/加 BOM）→ 用 edit/写入工具。

## 5. 纪律（不变）
- **DLL 不重编**（官方引擎只在外部 `data/GKMSMainWheel` 按路径引用）；不碰 `D:\Games\Gakumas`；`C:\GakumasLocal` 只读。
- **仓库已公开**：不提交 token / 保密种子 / 账号信息；`data/_v8_*` / `out/` / `submissions/_v7dbg/` 不入库；
  pathspec 提交（禁 `reset` / `checkout -a`）。
- 外部开源（huochai67 gakumas-engine，MIT）**只读参考/标尺，不引依赖、不拷代码**；`gakumas-launcher` 无 license 不可拷；
  `tls-roots-bridge.zip`（跳 TLS）不采用。
- 每阶段 feat+docs；结束更新 **HANDOVER_NEXT** + **GKBENCH §26** + 本文件 §7。
- 改 `src/` 才需要 pytest（`--basetemp=out/_pytest_tmp_*`）。

## 6. 一句话

**v8 把「失锁报废」变成「239/240 锁上、硬失败 1、假锁 0」，并把 MID 翻正（均值 1,507,935 新 PB）；
v9 两条腿：① 用 ALNS/逐题预算把剩 55 个 <90% 槽收口；② 把自有 sim 搬 C++、补 GMKS 改不了的消费图/RNG，
做「sim 宽搜提案 + 官方锁/核分」的特化搜索——这是从「调度维度」换到「引擎/搜索维度」的开始。**