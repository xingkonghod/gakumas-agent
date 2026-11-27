# f2-sl3b 离线 A/B 最终报告（2026-11-25）

**状态**：离线 A/B 完成（两轮，144 局）。**托管验证未做**——lead 优先级变更（用户指定）：
ex-seed 已反超 seedlock（954,652 vs 944,850），主任务改为 ex-seed + seedlock RoutePool 融合
（gkagent-ex-seed-v2，另派智能体）。本报告结论供 ex-seed-v2 直接参考。

**投稿目录状态**：seedlock 已恢复 git 基线 `4391bef`（algo.py / README.md 的 forced_play 参数化
改动已 `git checkout` 还原；RESULTS.md 从未改动）。f2-sl3b 无 bench_repo 提交。
参数化改动以补丁保存在探针侧：`data/_f2sl3b_forced_play.patch`（`git apply --check` 通过）。

## 方法

- harness：`data/_f2sl3b_ab.py`。16 个固定 F0 dev 种子（gkbench.referee 真实 obs 管线，离线无服务器/令牌）：
  大题 AS-2AXJNW8X / AS-323ADZVK / AS-8MY3XH4R / AS-ADDTACFE + 小题 AS-227HBGHS / AS-23D5RE8A
  + 10 核心题（AS-33JYSHDF / 499M4D9B / 663NKTY4 / 93WKA9BK / C3Y5EFGV / E8M2YFR2 / K2ER4ZRJ / P8NM4YAA / VBZG5R3W / Z4VBZFDZ）。
- 每题同一负载窗口内背靠背跑 base + 各变体（配对），bootstrap 10000 次重采样 95% CI（RNG 种子 20261125 可复现）。
- 轮1 `ab1`（16:38–17:03）：base / fp0 / scan4 / scan3 / st500k；轮2 `ab2`（17:05–17:24）：base / fp0 / fp0st / fp0s4。
- 背景负载：ex-seed 托管评测（PID 22296）全程在跑，24 核；与托管验证当时的竞争条件类似。
- 基线复现核对：AS-2AXJNW8X base 两轮均 1,374,348（lock 3）、AS-227HBGHS 冒烟 4,219（lock 4），与 f2-sl2 探针一致。

## 变体表（Δ = 变体 − base，逐题配对）

### 轮1（ab1，base 均分 870,274）

| 变体 | 参数 | 均分 | mean Δ | bootstrap 95% CI | 正/负/零 | 锁定率 | 结论 |
|---|---|---|---|---|---|---|---|
| fp0 | forced_play=0 | 901,873 | **+31,598** | [−2,933, +79,855] | 5/3/8 | 16/16 | 贴零正（轮2+池化后过门） |
| scan4 | scan_min=4 | 779,330 | −90,944 | [−248,736, +15,568] | 3/5/8 | 16/16 | 拒绝 |
| scan3 | scan_min=3 | 822,023 | −48,252 | **[−105,915, −2,680]** | 3/9/4 | **15/16** | 显著负，拒绝 |
| st500k | step_trans=500000 | 792,698 | −77,576 | [−221,002, +3,911] | 5/5/6 | 16/16 | 单独负（硬规矩交互） |

### 轮2（ab2，base 均分 881,319）

| 变体 | 参数 | 均分 | mean Δ | bootstrap 95% CI | 正/负/零 | 锁定率 | 结论 |
|---|---|---|---|---|---|---|---|
| fp0 | forced_play=0 | 906,707 | +25,388 | [−642, +66,700] | 6/3/7 | 16/16 | 贴零正 |
| **fp0st** | **forced_play=0 + step_trans=500000** | **926,381** | **+45,062** | **[+4,879, +95,723]** | 6/3/7 | 16/16 | **过采纳门（CI 下界>0）** |
| fp0s4 | forced_play=0 + scan_min=4 | 889,276 | +7,957 | [−47,661, +79,339] | 4/7/5 | 16/16 | 中性，拒绝 |

### 跨轮池化（data/_f2sl3b_pool.py ab1 ab2）

| 变体 | n | mean Δ | 95% CI | 正/负/零 |
|---|---|---|---|---|
| **fp0** | 32 | **+28,493** | **[+4,056, +59,962]** | 11/6/15 |
| fp0st | 16 | +45,062 | [+4,879, +95,723] | 6/3/7 |

**离线赢家 = fp0st（forced_play=0, step_trans=500000）**：16 题样本均分 926,381 vs base 881,319（+5.1%）。
**未做托管验证**，不能声称托管均分 >944,850；托管基线（run c060df94acad，944,850）未被触碰。

## 机制分析（数字可复现，见 ab1/ab2 JSON 逐题行）

1. **forced_play 硬规矩确认丢分**：轮1 fp0 的全部 5 个正 Δ 题恰是 base 触发硬规矩的题
   （323ADZVK hard2 +303,721；P8NM4YAA hard6 +182,403；8MY3XH4R hard1 +58,387；33JYSHDF hard1 +19,852；23D5RE8A hard1 +3,307；合计 +567,670）。
   fp0 的负 Δ 题 base hard_rule=0，是扫描时序噪声（见第 4 点），不是关规矩的因果损失。
2. **st500k 单独负的主因是硬规矩交互**：搜索更强 → GNRPA 提出更多蓄体力 end → 被强制改出牌丢路线。
   ADDTACFE −1,070,755（1 次 forced_play）、P8NM4YAA −179,270（9 次 vs base 6 次）、8MY3XH4R −43,923（2 次 vs 1 次）。
   关掉硬规矩后同一预算变正：fp0st 在 E8M2YFR2 +140,039、93WKA9BK +27,818（这两题 base hard=0、fp0 单独 Δ=0，是纯搜索预算收益）。
3. **scan_min 早锁定不是免费午餐**：scan3（第 1 回合 3 张起扫）候选爆炸 → FastCut/重扫拖慢锁定：
   AS-23D5RE8A 整局未锁定（candidates 态，18 步贪心，6,394 分）；499M4D9B 锁到 turn 7；C3Y5EFGV scan 8.11s+重扫。CI 全负。
   scan4 混合（早锁个别题 +93k~+99k，但 ADDTACFE/2AXJNW8X/E8M2YFR2 因 forced_play 交互大负）；配 fp0 后中性（4 正 7 负）。**scan_min=6 的现调参是对的。**
4. **锁定回合时序悬崖（重要方法论发现）**：步内等扫描窗口 = 0.7×5s = 3.5s；scan 3.43s vs 3.68s 之差就翻 1 个锁定回合。
   499M4D9B 早锁 1 回合 = +15,279；大题上 ±1 回合可达 ±1M（ADDTACFE base 1,785,918 vs 晚锁变体 715,163）。
   同配置 base 两轮均分自己就漂 870,274↔881,319。**单 run 逐题 Δ 不可靠，必须配对 + bootstrap/池化。**
   fp0st 的 3 个负 Δ 全部是此类噪声（499M4D9B scan 11.12s→lock7；C3Y5EFGV scan 3.63 vs 3.28→lock3 vs 2；VBZG5R3W −2,356 路线方差）。

## 墙钟 / 托管可行性（若 v2 采用 500k 预算）

- 全部 144 离线局：**over5=0、over6=0**（阈值 5s / 6.05s），max 步 ≈3.5s（=扫描等待步上限 0.7×budget）。
- 平均思考/局：base 16.5s → fp0st 23.7s（+44%）；托管 240 局 ×3 并行估算 ~55–60 分钟（基线 ~45 分钟）。
- fp0st 锁定率 16/16，平均锁定回合 4.06（base 3.94），无锁定退化。

## 可迁移到 ex-seed-v2 的结论（逐条）

1. **no-end 硬规矩应当参数化并默认关掉（最高优先）**。ex-seed 同款规矩在 algo.py L13、L372–373、L417、L472
   （`meta["hard_rule"]="no-end"`，搜索选 end 时逐 play 补搜）。它比 seedlock 的「改出最大即时分牌+丢路线」温和，
   但同样禁止蓄体力 end。seedlock 证据：凡是规矩触发的题关掉后全部改善（池化 +28,493，CI>0；托管基线 136 局中 21 局触发、确认丢分）。
   托管 obs 完美，规矩源于真机防 OCR 盲打，不适用。→ v2 先做这个单变量 A/B，预期正收益。
2. **先关规矩，再加搜索预算**。带规矩加预算可能负收益（st500k 单独 −77,576：更强的搜索提出更多 end 被规矩糟蹋）；
   关规矩后 500k 过门（+45,062，CI>0）。v2 融合 RoutePool 每步重搜时，预算 300k→500k 墙钟安全（离线零超 5s 步）。
3. **scan_min 保持现值（6 或 ex-seed 现行触发）**。3 显著负+锁定失败，4 中性。ex-seed 锁定前已是候选多数投票搜索
   （比 seedlock 纯贪心强），早锁定的边际收益更小，候选爆炸代价不变。
4. **锁定等待悬崖值得修**：0.7×budget 等扫描窗口造成 ±1 锁定回合噪声（大题 ±1M）。v2 可考虑加大等待分数、
   或扫描完成判定去墙钟化；评测方法必须配对 + bootstrap（本 harness 可直接复用，换 algo 路径即可）。
5. **RoutePool 移植要点**（seedlock 已验证的实现细节，RESULTS.md/探针有记录）：
   每步搜索前 `ns._cache = None` 强制重导入当前状态；路线在副本上用 `session.step(action, observe=False)` 回放核分
   （直调 play()/end_turn() 会踩可出性缓存过期 bug）；终局分更高者替换在手路线（target 单调，短搜不丢分）；
   实际打出动作与路线首动作不一致则丢路线（`played()`）。

## 局限（如实）

- 16 题离线样本 ≠ 托管 120 核心题×2 保密种子；fp0st 的托管增益未验证（lead 取消）。
- 离线 Δ 含扫描时序噪声；fp0 单轮 CI 贴零，靠 32 样本池化才过门；fp0st 仅 16 样本，CI 下界 +4,879 不算宽裕。
- scan3 的锁定失败在离线竞争负载下出现；托管更空闲时未必失败，但 CI 全负足以拒绝。
- 未试杠杆4（锁定前短 GNRPA 代替贪心）：fp0st 已过门且 lead 变更优先级，按时间盒放弃。

## 复现

    cd D:\Games\gakumas-agent
    git -C data\bench_repo apply data\_f2sl3b_forced_play.patch   # 参数化（跑完 git checkout 恢复）
    .venv\Scripts\python.exe data\_f2sl3b_ab.py base,fp0,scan4,scan3,st500k ab1
    .venv\Scripts\python.exe data\_f2sl3b_ab.py base,fp0,fp0st,fp0s4 ab2
    .venv\Scripts\python.exe data\_f2sl3b_pool.py ab1 ab2

## 产物（全部探针侧，不提交）

- `data/_f2sl3b_ab.py`（harness）、`data/_f2sl3b_pool.py`（池化）、`data/_f2sl3b_mkpatch.py`（补丁重建）
- `data/_f2sl3b_ab1.json` / `.log`、`data/_f2sl3b_ab2.json` / `.log`、`data/_f2sl3b_smoke.json`
- `data/_f2sl3b_forced_play.patch`（git apply --check 通过）、`data/_f2sl3b_algo_param.py`（参数化副本）
- 本报告 `data/_f2sl3b_report.md`

硬约束遵守：未重编 DLL；未杀任何 python 进程（PID 22296/19476/11732/29076 全程存活）；
未动其他投稿目录（ex-seed 只读）；未碰 D:\Games\Gakumas；seedlock 目录已还原基线。
