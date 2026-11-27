# 本地 gkbench 对比报告：「初」（hajime）48 题

> **2026-11-19 更新（UINet 接入后）**：`scripts/local_bench.py` 已接入 `uinet`，并把方案从
> `mechanic` 猜测改为 `scene.plan` 权威值（46/48 题是 PLAN3=logic）；本文件的三组数字是**旧基线**，
> 不能与本次重跑逐项对齐。新结果（greedy / uinet / expectimax-ensemble，48×3）见
> `data/bench_local/REPORT_UINET.md`，数据在 `data/bench_local/leaderboard_uinet.json`。

- 生成时间：20261119T120517Z（UTC，机器本地 20:05 +08:00）
- 裁判：**LessonSim（我们自己的模拟器）**，不是 gkbench 的 GKMS 引擎
- 题数：48（lesson 33 / mid 8 / final 7）；种子：3 个/题（1000、1001、1002，自选）
- 每算法局数：48 × 3 = **144 局**；同题同种子配对
- 产物：`data/bench_local/leaderboard.json`（全部逐局数据）、`data/bench_local/problems_hajime.json`

## 结论（先看这里）

1. **裁判 = 我们的 LessonSim，不是 gkbench 的 GKMS 引擎。** 这是任务里的 fallback。
   gakumas-tools 的 `gakumas-engine` 能在本机 Node v24.20.0 下完整跑一局（自测分数与其官方
   suite 完全一致），但它只实现 contest 舞台，没有 produce 考试模式，不能当「初」这套题的裁判。
2. **分数与 gkbench 排行榜不可比。** 裁判不同（GKMS native rules 59 vs LessonSim）、种子不同
   （hajime 的 `public_seeds=false`，`/api/sets/hajime/seeds` 返回 401，题目接口不含种子值；
   本报告用自选 1000–1002）、机制覆盖不同（效果级建模率 93.14%；52 条卡牌定制、饮料、
   P 道具、审查基准/属性回合未建模）。
3. **排名取决于口径：**
   - 按**算术均值**：greedy **705.5** > expectimax(ensemble) **683.0** > expectimax(analytic) **633.8**；
   - 按 **gkbench 自己的配对几何均值比值**（同题同种子，vs greedy）：
     expectimax(analytic) **1.480×**（95% CI 1.345–1.624）>
     expectimax(ensemble) **1.195×**（95% CI 1.053–1.355）> greedy 1.000；
   - 两者不矛盾：算术均值被 2 道 audition 题（AS-DDCRRSTM final、AS-X8NXKZXW mid）的离群局
     主导。这两题按 48 题摊，把 analytic 的均值
     拉低约 **148 分/题**；其余 46 题 analytic 平均 **+79.8 分/题**，逐题胜率 **42/48**。

## 一、题目：真实接口结构（只 GET，不上传）

- `GET https://hiro.matto.top/gkbench/api/sets/hajime/problems` → **48 题**，115,474 字节，
  `sha256 f664fc6492a7ddbc…`；落盘 `data/bench_local/problems_hajime.json`。
- 场景分布：**lesson 33 / mid 8 / final 7**；题集元数据：`public_seeds=false`、
  `template_seeds=32`、`seeds={dev:46,test:0}`。
- 46/48 题带一条固定种子元数据（`exam_sha`、`fixed_id`，如 `AS-986M49WS → fixed_id AS-ZSTEKG6Z`），
  **但没有任何种子值**；AS-DDCRRSTM（final）与 AS-X8NXKZXW（mid）连元数据行都没有。
- `GET /api/sets/hajime/seeds` → **HTTP 401 Unauthorized**（`public_seeds=false`）。
- `?fixed=1&answers=1` 等查询参数对 `/problems` 无影响（返回字节数完全相同）；当前接口没有下发
  种子。因此本报告用本地自选种子 **1000、1001、1002**，三个算法完全共用。

## 二、裁判：先试 JS 引擎（BSD-3 的 gakumas-engine）

- 代码：`data/dl/gt/gakumas-tools-master/packages/gakumas-engine`；**没有执行 npm install**。
- 它自带 `scripts/extensionless-loader.mjs`（解析 workspace 包、`.csv` 导入），所以直接在 Node
  下可跑；不需要浏览器、不需要 node_modules。
- 自测：`node --loader ./scripts/extensionless-loader.mjs tools/referee_cli.mjs --self-test` →
  stage 95，seed 610397104，**score 13257**（gakumas-tools 官方 `tests/suite.jsonl` 记录值
  13257，**完全一致**），10 回合 / 18 决策 / 5.67 ms。证据：`data/bench_local/referee_selftest.json`。
- **但它不能当「初」的裁判**：`IdolConfig` 只接受 contest 编成（`params`、`skillCardIdGroups`、
  `stageId`），`Stages` 的 CSV 只有 `contest`/`linkContest` 舞台；「初」的编成是
  `gkms.exam_loadout.v1`（`deck_cards`、`parameters`、`score_bonus_permils`、`step_type`…），
  引擎没有 produce 考试模式。
- `tools/referee_cli.mjs` 对这类输入明确返回
  `{"status":"unsupported","error":"unsupported_loadout",…}`，不猜映射；对 contest 编成支持
  heuristic 与 manual（route）两种策略，stdout 固定回 `{score, finished, turns, …}`。

## 三、fallback 裁判：LessonSim 的接入口径

- 每道题的 `deck_cards` 按 `(卡号, 强化次数)` 查 `data/knowledge/card_table.json`，经
  `scripts/sim_produce.py` 的 effects→CardSpec 映射建牌组：**883/883 条解析成功**（0 条未解析；
  52 条带定制的按基础卡处理）。
- 效果覆盖：**2091/2245 = 93.14%** 的效果类型在 `lesson.py` 有建模；未建模的 12 类见
  `leaderboard.json.deck_modeling.unmodeled_types`（ExamCardUpgrade、StanceLock、
  ExamStaminaConsumptionDown、ExamFullPowerPointAdditive 等）。
- 回合数取 `scene.turns`；体力取 `starting_stamina`/`max_stamina`；方案按 mechanic 映射
  （aggressive→sense、full_power→logic、stance→anomaly）；`attribute_coefficient=1.0`。
- **未建模**：卡牌定制（52 条）、饮料、P 道具、审查基准/属性回合/暴击、gimmick、追加回合；
  这是简化裁判，只能做相对比较。
- 每个决策点构造 UIObs v1 并交给算法（`decide(obs, sim)`）；当前实现里 greedy/expectimax 读
  同一局面的 sim 快照（与 UIObs 暴露的信息等价：手牌/山札组成/弃牌/体力/分数/回合/合法动作），
  UIObs 同时用于合法动作校验，缺口见 `sim_to_uiobs` 的 docstring。greedy 用 `greedy_policy`；
  expectimax 用 `expectimax_with_stats`，每步预算 300 ms；搜索未完成（约 22% 的步）时**回退
  greedy**，并计入 `fallback`。
- expectimax 的叶子：analytic/ensemble 只提供 `predict` 的 μ，效用 = **当前分 + μ**。原因：
  gkbench 只按原始分排名，没有 CLEAR/PERFECT 线；直接用档位概率效用会退化成常数。ensemble =
  `EnsembleLeafValue(AnalyticLeafValue(), LinearLeafValue.load(data/knowledge/v_leaf.json), weight=0.5)`。

## 四、结果（同题同种子，144 局/算法）

| 算法 | 局数 | 均值 | P50 | P90 | 每步均值 ms | 每步 P50 | 每步 P90 | fallback | 总耗时 s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| greedy | 144 | 705.5 | 129 | 331 | 0.01 | 0.00 | 0.01 | 0.0% | 0.1 |
| expectimax(analytic) | 144 | 633.8 | 186 | 538 | 78.01 | 1.52 | 302.85 | 22.4% | 308.1 |
| expectimax(ensemble) | 144 | 683.0 | 163 | 460 | 77.13 | 1.90 | 303.23 | 22.2% | 301.4 |

说明：greedy 的每步耗时是纯策略计算（0.005 ms）；expectimax 的「每步均值 78 ms」包含 22% 的
300 ms 超时步，所以 P50 只有 1.5–1.9 ms、P90 约 303 ms。三组 `finished_rate` 都是 100%，
平均 9.56 回合；每局决策数 greedy 28.4 / analytic 27.4 / ensemble 27.1。

### 配对比较（同题同种子，vs greedy）

| 算法 | 逐局胜/负/平 | 逐题胜/负 | 逐局中位比值 | 逐题几何均值比值 [95% CI] |
|---|---:|---:|---:|---:|
| expectimax(analytic) | 113/28/3 | 42/6 | 1.451× | **1.480× [1.345, 1.624]** |
| expectimax(ensemble) | 84/58/2 | 32/16 | 1.195× | **1.195× [1.053, 1.355]** |

95% CI 是按题（48 个 cluster）重采样的 bootstrap（5000 次）。逐题几何均值比值 = 先对每题 3 个
种子取均值，再对 48 题取几何平均。

### 分场景均值（局数 / 均值 / 中位数）

| 场景 | greedy | expectimax(analytic) | expectimax(ensemble) |
|---|---:|---:|---:|
| lesson | 99 局 / 138.0 / 112.0 | 99 局 / 203.8 / 163.0 | 99 局 / 173.5 / 139.0 |
| mid | 24 局 / 934.5 / 150.5 | 24 局 / 853.3 / 222.5 | 24 局 / 888.8 / 174.0 |
| final | 21 局 / 3118.7 / 201.0 | 21 局 / 2410.1 / 320.0 | 21 局 / 2849.6 / 323.0 |

**离群说明**：算术均值里，AS-DDCRRSTM（final）greedy 平均 20,580 vs analytic 14,642、
ensemble 17,827；AS-X8NXKZXW（mid）6,298 vs 5,125 / 5,674。两题合计把 analytic 的 48 题均值
拉低约 148 分/题；其余 46 题 analytic 平均 **+79.8 分/题**。去掉这两题后，analytic 对 greedy 的
逐题几何均值比值是 **1.524×**（比 1.480× 还略高），说明均值差异不是普遍劣势，而是两道题的
极端局。

## 五、能不能和他们的排行榜比？

**不能。** 明确结论：

1. **裁判不同**：gkbench 的 runs 写着 `engine: gkms-native, rules_version: 59`；这个引擎不在本机，
   gkumas-tools 的 `gakumas-engine` 又只支持 contest。本报告是 LessonSim 的简化规则，
   分数尺度/公式与 GKMS 不同。
2. **种子不同**：hajime 的 32 个模板种子是保密种子，`public_seeds=false`，
   `/api/sets/hajime/seeds` 401；`/problems` 只给 `exam_sha`/`fixed_id`，不给种子值。本报告用
   自选 1000–1002，和官方排行榜不是同一批牌序。
3. **机制覆盖不同**：93.14% 效果级建模；卡牌定制、饮料、P 道具、审查基准/属性回合/暴击、
   gimmick 未建模。即使同一批种子，分数也不能对齐。

**可以比的**：本报告内部三组算法在**完全相同的 48 题 × 3 种子**下的相对表现，以及每步耗时的
相对量级（greedy ≈ 0 ms；expectimax 300 ms 预算、22% 回退）。

## 六、复现

```powershell
cd D:\Games\gakumas-agent

# 3 种子 × 3 算法（本报告的数据；实测约 10 分钟）
.venv\Scripts\python.exe scripts\local_bench.py --episodes 3

# 快速冒烟（2 题）
.venv\Scripts\python.exe scripts\local_bench.py --episodes 1 --limit 2

# JS 裁判自测（在 gakumas-tools-master 下用它的 loader）
cd data\dl\gt\gakumas-tools-master
node --loader ./scripts/extensionless-loader.mjs D:\Games\gakumas-agent\tools\referee_cli.mjs --self-test
```

产物：

- `data/bench_local/problems_hajime.json`：48 题原始落盘；
- `data/bench_local/leaderboard.json`：本报告全部数据（含 432 条逐局 score/turns/step_ms/route）；
- `data/bench_local/referee_selftest.json`：JS 引擎自测证据；
- `scripts/local_bench.py`、`tools/referee_cli.mjs`、`tests/test_local_bench.py`。

## 七、限制与下一步

- 种子只有 3 个/题；要收紧 CI 可跑 `--episodes 8` 或 32（与官方同量级）。
- 22% 的步搜索未完成；`incomplete == fallback`（没有出现「模型/手牌映射失败」的回退）。
  想降低回退率可加大 `--budget-ms` 或减少 0 费过牌造成的分支。
- LessonSim 对 audition 的属性类型/审查基准/回合倍率没有建模；7 道 final 的均值噪声最大。
- 未建模项见 `leaderboard.json.deck_modeling`；要更接近官方，下一步是接 GKMS native
  （本机没有）或补齐定制/饮料/P 道具/属性回合。

## 八、验收

- `pytest tests/ -q --basetemp=data/pytest-tmp`：**exit 0**；同一套测试用默认 addopts 跑到
  **770 passed in 180.79s**（原有 766 条 + 新增 `tests/test_local_bench.py` 4 条）。
- `ruff check src tests scripts/local_bench.py`：**All checks passed!**
- `node --check tools/referee_cli.mjs`：exit 0；`--self-test` 的 score 13257 与 gakumas-tools
  官方 suite 记录值一致。
- 全程只对 gkbench 做 GET（problems / sets / runs / saves；`/seeds` 401），没有上传任何成绩；
  没有执行 `npm install`，`data/dl/gt/gakumas-tools-master/node_modules` 仍不存在；
  没有改动 `src/gkagent/tasks/produce_ui.py` 或 `data/knowledge/` 下的现有文件。
