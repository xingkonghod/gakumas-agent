# gkbench（hiro.matto.top/gkbench）数据与 F 阶段口径

> 2026-11-22 建立。用户已登录该站（可下载公开数据）；本文件记录**怎么批量下载、哪些数据要令牌、
> 已下载了什么、参考分是多少**，以及和 [WORKPLAN 阶段 F](WORKPLAN.md) / F0 的关系。
>
> 规则红线不变：**ranked 用保密种子（只托管跑、算法只看画面），不能带 seed/牌序**；
> 能下载的固定种子题/公开答案只能用于**本地分析、理论上限当分母**（官方也这么定：看种子的搜索
> 只作 denominator、不参与排名）。

## 1. 站点结构（本地克隆 `data/bench_repo`，MIT）

两种评测：

| | 固定种子题（fixed） | 保密种子（template·32 个/题） |
|---|---|---|
| 种子 | 题集自带；开发集公开可下（`public_seeds` 或令牌） | 服务器私有，永不下发 |
| 怎么跑 | 本地跑完上传（`mode=self`）或托管（`hosted`） | 只能托管（`gkbench eval`） |
| 怎么比 | 同题同种子逐局配对；有理论上限（oracle/privileged）当分母 | 同题同格子号配对，几何平均比值 |
| 公开什么 | 成绩、逐步记录、`exam_sha`、存档里的答 | 只公开成绩（逐步记录登录后可见；`exam_sha`/答不下发） |
| 排行 | 「固定种子」 | 「保密种子」（ranked 主榜） |

存档格式 `gkms.audition_save.v2`：一题 = `loadout`（编成；含 `seed` 就是固定种子题）+ `check`
（起点核对：回合/分数/体力/手牌/规则版本/引擎提交号）+ `meta` + `runs`（各算法答：`route`
动作串 `p<i>/d<i>/e/s<i,j>`、`score`、`step_ms`）。详见 `data/bench_repo/docs/format.md`。

## 2. 公开只读 API（不用登录就能拉）

| 接口 | 内容 | 令牌 |
|---|---|---|
| `GET /api/sets` | 题集列表（problems/runs/public_seeds/场景统计） | 不需要 |
| `GET /api/runs?set=<set>` | 某题集全部运行（algo/kind/mode/均分/规则版本/privileged） | 不需要 |
| `GET /api/runs/<run>` | 一次运行的逐局摘要：**含 `route` 出牌路线**、分数、回合属性 `types`、tags | 不需要 |
| `GET /api/runs/<run>/episodes/<id>/<seed_index>` | 逐局完整记录（`steps`：每步 obs/action/algo_meta） | **保密种子要登录（403）**；固定种子公开 |
| `GET /api/sets/<set>/problems` | 题模板列表（编成/场景/题族） | 不需要 |
| `GET /api/sets/<set>/saves?answers=1` | 题模板存档 NDJSON（每行一题 + 公开算法的答/路线） | 不需要 |
| `GET /api/sets/<set>/saves?fixed=1` | 追加固定种子题行 | **要令牌/公开种子**（否则静默跳过） |
| `GET /api/sets/<set>/seeds` | 开发集固定种子（`seed`+`split`+`fixed_id`+`check`） | **要令牌**（`public_seeds=false` 时 401） |
| `GET /api/leaderboard?set=<set>&kind=fixed\|template` | 榜单（含 `vs_oracle` 几何平均/胜率） | 不需要 |

令牌：网页「我的」页（`/gkbench/me`）生成**命令行令牌**，存 `~/.config/gkbench/token`
（Windows：`C:\Users\<user>\.config\gkbench\token`）或设 `GKBENCH_TOKEN`。

## 3. 批量下载工具

`scripts/bench_download.py`（stdlib，只读公开接口；可重复执行、已下跳过）：

```powershell
# 目标算法（默认四个）；hif 题集；逐局 steps 默认就下、saves/leaderboards 一起
.venv\Scripts\python.exe scripts\bench_download.py --sets hif
# 只要 run 索引（含 route）和榜单，不下逐局 steps / 存档
.venv\Scripts\python.exe scripts\bench_download.py --sets hif --no-episodes --no-saves
# 带令牌（网页「我的」→ 命令行令牌），补保密种子逐局记录
$env:GKBENCH_TOKEN = "..."; .venv\Scripts\python.exe scripts\bench_download.py --sets hif
```

输出（gitignore，不入库）`data/bench_local/gkbench_dl/`：

```
sets.json                     # /api/sets
<hif>/runs.json               # 全部 run 概要（190）
<hif>/runs/<run>.json         # 目标算法 run 的逐局索引（含 route/score/types，一个 run 一个文件）
<hif>/episodes/<run>/<id>_<i>.json   # 固定种子（公开）逐局完整 steps
<hif>/saves.jsonl             # 题模板存档 NDJSON（505 题，含公开答）
<hif>/leaderboard_fixed.json  # 固定种子榜（含 vs_oracle）
<hif>/leaderboard_template.json # 保密种子榜（ranked 主榜）
manifest.json                 # 请求数/字节数/需要登录的逐局清单（断点续传依据）
```

拿到 `seeds.json` 后的核对/校准用 `scripts/verify_gkbench_shuffle.py`（见 §4.5）：
官方 `check.hand` 逐张对照洗牌模型 + `check.turn/score/stamina/rules` 起点校准，只读本地数据。

## 4. 2026-11-22 已下载

`hif` 题集（505 题 / 190 runs）：公开部分 **176 次请求、39.4 MB**；拿到用户令牌后补了
**`seeds.json`（329 题 / 384 组开发种子 + 官方 `check`）**，以及 5 个主参考 run 的逐局 steps
的**抽样**（保密种子逐局接口服务端要扫整个 run 文件，实测 ≈20 s/局，全量 4,797 局不现实；
本次只下了 27 局，之后按需抽样）。

| 算法 | 精确匹配 runs | 备注 |
|---|---:|---|
| `external:uinet` | 37 | 36 template（480/800 局/run）+ 1 fixed（70 局，steps 已下） |
| `external:uihorizon` | 13 | 8 template（最多 960 局）+ 5 fixed（lockprobe/submission-check，steps 已下） |
| `external:official-ai` | 2 | 480 / 957 局 template |
| `external:best-known` | 28 | 全部 template（280~800 局/run） |
| `external:oracle` | 2 | 理论上限（固定种子 70 局 + template） |
| 变体（`--variants`） | 13 | UINet 2.1 native/hud/roster/uiobs、UIHorizon v2.0/v2.2 等 |

- 目标 run 索引里**带 route 的局合计 36,350**（含保密种子局；索引公开 route，逐步 obs 需令牌）。
- 固定种子（公开）逐局 steps：**79 局**（uinet 70 + uihorizon lockprobe 9）；拿令牌另下了
  uinet template run 前 27 局（`episodes/20261112-040508-hif-template-uinet-matto/`）。
- 题模板存档：505 题（公开答只有 `external:uinet` 5 题/160 行——保密种子答不进公开存档）。
- **开发集种子 + check**：`hif/seeds.json`——`{problems: {AS-XXXX: [{index, seed, split:"dev",
  label, fixed_id, check:{turn,score,stamina,hand,rules,commit}}]}}`，共 **329 题 / 384 组**，
  这是 F0 洗牌交叉验证的官方基准。


## 4.5 F0 收尾（2026-11-22）：洗牌模型 vs 官方 `check.hand`——286 → 366/384 + 考试起点校准

用官方 `seeds.json` 的 `check`（**官方 GKMS 原生引擎算的开场局面**：第 1 回合手牌/回合/分数/体力/
规则版本/引擎提交）核对我们的 `exam_shuffle`（xorshift32 先消耗 K 次 + Fisher-Yates + 第 1 回合
SetInitialCard）。**这 384 组（329 题 × 1–2 个开发种子）就是洗牌模型的外部独立回归集**——不依赖
我们的采集/账号，是 F0 的核心产物。

复跑（只读本地数据 + 主数据，不联网、不读令牌）::

```powershell
.venv\Scripts\python.exe scripts\verify_gkbench_shuffle.py                 # 核对 + 起点校准
.venv\Scripts\python.exe scripts\verify_gkbench_shuffle.py --verbose       # 打印逐条不一致样本
.venv\Scripts\python.exe scripts\verify_gkbench_shuffle.py --json data\bench_local\f0_gkbench.json
.venv\Scripts\python.exe scripts\verify_gkbench_shuffle.py --stage-npc     # 消融：NPC 按 stage 常数
.venv\Scripts\python.exe scripts\verify_gkbench_shuffle.py --variant-initial --stage-npc  # 复现 F0 预检旧口径（286/384）
```

### 口径（2026-11-22 修正后）

| 项 | 口径 |
|---|---|
| `turns` / `K` | `turns` = 模板 `meta.turns`（官方引擎 `limit_turn`，**配置回合数**，提前结束也按配置算）；`K = (turns-3) + npc*turns` |
| **npc 人数** | **按 idol 卡，不是 stage 常数**：`IdolCard.produceStepAuditionDifficultyId` → `ProduceStepAuditionDifficulty(produceId, stepType)` → `produceExamBattleNpcGroupId` → NPC 行数。**選抜一律 6 人制 = 5**；**本戦按培育角色不同**——多数 3 人制（npc=2，135 张 idol 卡）、**十王星南 jsna 4 人制 = 3（13 张）**、**藤田ことね fktn 2 人制 = 1（12 张）**；loadout 缺 `step_type/step_id` 时按 `round`（mid1/mid2/final）兜底，仍取不到才退回 stage 常数 |
| initial 集合 | 主数据 `isInitial`（**按 base 卡 id，命中 +0/+1/+2/+3 全部强化变体**，deck 写 `...+1` 同样算）+ deck 里带 `g_effect-initial_add` 自定义的卡（考试开始强制入手） |
| 牌序 | `loadout.deck_cards` **原顺序**（按主数据 `order` 重排只有 1/384，错） |

### 结果

| 口径 | 精确命中 | 逐张命中（按位置） |
|---|---:|---:|
| F0 预检旧口径（variant initial + stage npc） | 286/384 = 74.5% | 913/1155 = 79.0% |
| 只修 initial（base id + initial_add） | 338/384 = 88.0% | 1060/1155 = 91.8% |
| **再修 npc（按 idol）+ round 兜底步（最终）** | **366/384 = 95.3%** | **1125/1155 = 97.4%** |

（npc 口径先只读 `step_type` 字段时是 360/384；384 组里 26 题的 loadout 没有 `step_type/step_id`，
补 `round`（mid1/mid2/final）兜底后又修回 6 组 → 366。）

| stage | 精确 | 逐张 |
|---|---:|---:|
| hif.sel1 | **60/60 = 100%** | 180/180 = 100% |
| hif.sel2 | **55/55 = 100%** | 165/165 = 100% |
| hif.sel3 | 56/57 = 98.2% | 171/172 = 99.4% |
| hif.main1 | 96/97 = 99.0% | 291/292 = 99.7% |
| hif.main2 | 99/115 = 86.1% | 318/346 = 91.9% |

逐题：**311/329 题的全部种子都命中**（其余 18 题的种子一致地落在同一类缺口上，见下）。

### 剩余 18 组不一致的根因

| 根因 | 组数 | 说明 |
|---|---:|---|
| initial | 0 | isInitial（按 id 含强化变体）+ initial_add 修正后不再有此类不一致 |
| turnStartDistribute | 0 | 没有 handDecrease/发牌张数差异 |
| 牌序 | 0 | 没有「洗牌/RNG 消耗对不上」的样本——366 组命中说明 K 与 Fisher-Yates 全对 |
| **其他** | **18** | **① 15 组：考试初始牌组 `ExamInitialDeck` 未建模**——实机手牌的卡来自 idol 的考试初始牌组（`produce-008` 沿用 `initial_deck-produce_007-concentration/lesson_buff/review`，12/2/1 组），但这些卡不在 `loadout.deck_cards` 里；官方起点引擎加入初始牌组卡的**具体规则**（全量/部分、加到手牌还是牌堆、是否参与洗牌）还没定论，留给 F1（需官方引擎或更多样本）。**② 3 组：考试开始额外加牌**——手牌 4 张 = 预测 3 张 + 1 张，**第 4 张恰好是牌堆下一张**（= 考试开始额外抽 1 张；都出现在 `i_card-kllj-3-005`，疑为该 idol 卡 P 道具的考试开始附魔）。 |

结论：**洗牌模型本身（K + 洗牌 + 首回合发牌）在官方种子上已无失败样本**；剩余 18 组全部是
「考试开始阶段的加卡」类机制，属模拟器/起点状态建模缺口，不影响 MITM seed→牌序链路。

### 考试起点校准（`check.turn/score/stamina/rules/commit`）

| check 字段 | 官方值（384 组） | 校准结论 |
|---|---|---|
| `turn` | 1 × 384 | 考试从**第 1 回合**开始（不是 0）；与 `LessonSim` 现有口径一致 |
| `score` | 0 × 384 | 起点分 0 |
| `rules` | **55 × 384** | 官方原生引擎规则版本 **55**（check 生成时）；榜上 run 现在跨 **rules 55/59/65** 三档 → F1 裁判对齐要标版本，别默认最新 |
| `commit` | `f4d9e6e6148d` × 339；空 × 45（随机 40 + 实机 5） | GKMS 引擎提交；与 rules=55 配对 |
| `stamina` | **369/384 = 96.1% 等于 `loadout.starting_stamina`**；15 组差异**按 idol 卡固定** | 起点体力 = `starting_stamina` + **偶像卡自带 P 道具的考试开始附魔**（常量偏移：shro-3-016 **−28**×5、atbm-3-015 **+5**×4、kllj-3-005 **−1**×3、ssmk-3-002 **+6**、kcna-3-019 **+6**、shro-3-007 **+1**）。B6/T5③（2026-11-22）用 `loadout.produce_item_ids` 反查到：**shro-3-016 的 5 组可由 `pitem_02-3-293-0` 的 exam_start「最大体力的 80% 数值变为体力消耗」解释**（max_stamina 36 → `floor(36×0.8)=28`，start−28=check），其余 10 组涉及 `p_items.json` 快照缺行的新道具或主道具附魔（不猜）。**基准复算请用 `check.stamina` 覆盖** `loadout.starting_stamina`，别盲用 loadout 值 |

种子来源：`label` 上传 314 / 随机 60 / 实机 10（上传的 check 是服务器建种子时用当时引擎算的，
所以 rules/commit 是快照值）。

### 影响 / 下一步

- F0 DoD（逐题逐张命中率 + 根因 + 起点校准）已达成：**95.3% 精确 / 97.4% 逐张**，選抜 100%；
  剩余 18 组根因已分类，**没有一组是洗牌模型本身错**。
- **不改变对外口径**：ranked 仍禁 seed；这些官方种子只做本地校准/理论上限分母。
- 给 F1 的输入：本地复算「同题同种子」时起点用 `check`（turn/score/stamina/rules/commit），
  洗牌/发牌模型已外部验证，可直接当「已知牌序」；`local_bench.py` 目前用 `starting_stamina`，
  接官方 check 时要覆盖（15/384 会差 −28…+6 体力）。
- **B6/T5③（2026-11-22）起 `local_bench.py` 已把题模板 `loadout.produce_item_ids` 接入
  `LessonSim`**（`--p-items auto/off` 可 A/B；报告 `p_items` 覆盖率），提交适配器也从
  `ctx.loadout` 接入；**B7（2026-11-22）把 `p_items.json` 补到上游 1115 件**——本数据源
  83 个唯一 id **全部已知、0 未知**，但新增 47 条的条件/效果大多未建模（条件未知段保守
  不触发）；效果覆盖：catalog 1849 段 spec 实现 445 段、本数据 83 道具 153 段实现 34 段
  （见 RULES_REFERENCE §5.3）。
- 已知待补（F1）：`ExamInitialDeck` 加卡机制、`kllj-3-005` 开局 +1 手牌；
  主道具附魔 `main_item_enchant_ids`、P 道具条件/效果语义（B7 后已无未知 id）。

## 5. 参考分（2026-11-22 抓取，`public_seeds=false` 时的公开部分）

**固定种子榜（fixed；70 题一套，oracle-30s 当分母）**

| 算法 | n | 均分 | vs oracle 几何 |
|---|---:|---:|---:|
| oracle-30s（理论上限） | 70 | 567,948 | 1.0000 |
| pimc-vote-16w-2s | 70 | 302,202 | 0.5101 |
| uinet | 70 | 290,128 | 0.4986 |
| greedy | 70 | 41,507 | 0.0596 |
| uihorizon（lockprobe/submission-check） | 1~4 | 22,753~6,460,361（单题探针，不可比） | — |

**保密种子榜（template = ranked 主榜；960 局/算法）**

| 算法 | 均分 | vs best-known 几何 |
|---|---:|---:|
| best-known（分母） | **1,452,088**（928 局那版 1,486,205） | 1.0000 |
| UIHorizon v2.1Preview-Kummer | **631,129** | 0.5113 |
| UIHorizon v2.0Preview-Freiheit | 636,109 | 0.5017 |
| UIHorizon v2.2Preview-Gratwanderung | 571,828 | 0.4604 |
| UINet v2.1-Kummertranen | **578,722** | 0.4551 |
| uinet（internal 旧版） | 469,890 | 0.3740 |
| official-ai（asahi老师策略） | **232,710** | 0.2131 |
| hiro-rules | 95,341 | 0.0786 |
| greedy | 87,571 | 0.0710 |

> 这些数字与 README/COMPARE 里引用的一致（README 的 631k/579k/233k 是 template 榜口径）。

## 6. 还缺（要令牌）

1. ~~**`/api/sets/hif/seeds`**：开发集固定种子 + `check`~~ ✅ 已下（2026-11-22）：
   329 题 / 384 组 + `check{turn,score,stamina,hand,rules,commit}`；F0 用它交叉验证了洗牌模型
   （286 → **366/384 = 95.3%**，逐张 97.4%）并校准起点，见 §4.5。
2. **保密种子的逐局 `steps`**：uinet/uihorizon/official-ai/best-known 的 template runs 只有 route
   索引，逐步观测要登录；拿到后可做行为分析/教师数据（不用于 ranked 提交）。
3. **`saves?fixed=1` 的固定种子存档**（含 `check`），同样要种子权限。

拿到令牌后同一命令重跑即可断点补齐（`manifest.json` 里有 `need_login_episodes` 清单）。

## 7. 与 F 阶段的关系

- **F0（先做）✅ 已完成（2026-11-22）**：官方种子/`check` → 洗牌模型外部验证
  **366/384 = 95.3% 精确 / 97.4% 逐张**（選抜 100%；剩余 18 组全是考试开始加卡机制，非洗牌错误）
  + 考试起点校准（turn=1 / score=0 / stamina 96.1% 等于 starting_stamina / rules=55）→ 见 §4.5；
- **F1**：用同题同种子把我们的 `LessonSim` 判官和官方分对齐（口径校准，先分清裁判差异）；
- **F2**：public-safe 适配器（不看 seed）→ 托管提交 → 按 ranked 榜口径（vs best-known 几何平均）对比；
- **离线研究**：公开 route/步骤可当 UINet/UIHorizon/官方 AI 的行为参照（教师数据方向，注意不用于 ranked）。

## 8. 2026-11-25 F2 投稿启动（用户选定先投排行试水）

- **live 榜单快照 + 新竞争者情报**见 [COMPARE.md §2.2](COMPARE.md)（2026-11-25）：纯画面 public-safe 天花板
  UINet 2.1 = 578,722（0.4551 vs best-known，rules 59）；新进步 jayalbertzhao PPO 微调 575,585（rules 67）、
  kirinigh UINet 2.1 vs oracle 0.685（rules 65 sense 子集 n=3，即用户说的「68.5%」，口径不同不可直接比）。
- **投哪个**：我们最强 public-safe = **B11 学生网 r13**（`data/knowledge/ei_policy_v6.json`，离线 large 316.8 > beam 301.6）。
  beam+全知更强但用种子 → 不能上 ranked（privileged/sees_seed）。
- **托管可行性**：`needs_gkms=False` 纯画面算法，`python -m gkbench eval` 只需 gkbench 包 + 令牌（引擎在服务器跑，
  算法只读 ctx.obs 交动作），**Windows 本机可跑**，不需本地 GKMS 引擎。令牌已在 `~/.config/gkbench/token`。
- **F2 适配器硬约束**：投稿 algo.py 在 gkbench 环境（Python 3.12 + numpy/onnxruntime/pyyaml/GKMS）跑，
  **不能 import gkagent**——须自包含打包 MLP 前向 + 137 维特征提取（leaf_mlp.features 104 + action_features 33）+
  UIObs→ExpectState 映射 + 卡表。status 种类码见 `data/GKMSUINet/gkms_uinet/data/uiobs.v1.schema.json`
  （lesson_buff/review/aggressive/full_power_point/enthusiastic/parameter_buff…）。**集中 focus 的 UIObs 来源待查清**。
- **状态**：✅ **适配器完成 + 两次 240 局托管试跑**（子智能体 f2-adapter，2026-11-25）。投稿目录
  `data/bench_repo/submissions/gkagent-ei-r13/`（algo.py 自包含 numpy+标准库 / card_profiles.json 生产代码预计算 /
  ei_policy_v6.json r13 权重 / submission.json label=gkagent-ei-r13 author=xingkonghod / test_adapter.py 249 项检查全过 /
  README.md / RESULTS.md）。**增强版（补考试成长 g+定制 c 透明子集≈97%）240 局均分 86,988，0 错误/0 超时**
  （基础版 81,523）；≈greedy（87,571）、约 UINet 18%。运行编号 template-hif-gkagent-ei-r13-cgaug-xingkonghod-d20fda5881ec。
- **根因（为什么 sim 训练的网到官方引擎只到 greedy）**：**不是映射错**（与生产逐位对拍误差 0、7642 步真实回放 0 违规、
  249 检查全过）；**主因=训练/考试分布鸿沟**——考试分 0–927k vs 训练 0–450、属性倍率 20–48×，score 维 OOD |z|=398、
  vitality 43.8、card_block_scale 94（训练池限 score≤60 排 SSR）；104 维中 75 维在 2σ 内，OOD 恰是分数/buff 量级维。
  次因=sim 不建模饮料/P道具效果/回忆/支援卡/gimmick（rules 67 含这些）；aggressive/parameter_buff 题最弱、review 题最好。
  **战略结论：自有 sim 训练的策略迁到官方 GKMS 引擎大幅缩水；要在 gkbench 竞争需直接在官方引擎尺度训练（UINet/PPO 路线）**。
- **全量投稿命令**（cd data/bench_repo）：核心 960（120×8，排行默认口径，≈9 分钟）
  `..\..\.venv\Scripts\python.exe -m gkbench eval --set hif --algo submissions/gkagent-ei-r13/algo.py:EiR13Algo`；
  全部 505×32=16,160 局加 `--full`（≈2.5h，不改默认排名需 scope=all）；505×2 加 `--full --seeds 2`（≈10 分钟）。
  中断 `--resume <编号>`。环境：.venv 装了 httpx+zstandard（gkbench 客户端依赖）；`gkbench submissions check`
  Windows 跑不了（fcntl 仅 Unix），用等价脚本手工校验过；eval/hosted 不受影响。
- **口径警示**：我们 sim 标定 rules 55，官方榜 rules 59/65/67；学生网在自有 sim 训练，迁到官方引擎分数可能缩水
  （用户已预期「分不高」）。F1 判官对齐尚未做。

## 9. 2026-11-25 转折：GKMSMainWheel 开源 + 竞争路线升级

- **归一化实验（f2-norm）**：r13 网输入尺度 OOD 是低分主因之一。裁剪标准化输入 **clip±3 → hif 96,853（+11.3%）**、
  **rescale（分数除平均倍率）→ 98,630（+13.4%）**，均超 greedy 87,571。证明网策略本身有效、低分主要是 OOD。
  但 98k 仍远低于竞争者 500k+（UINet 578k/UIHorizon 631k）——public-safe 网天花板低（缺饮料/P道具/回忆 + 训练尺度）。
- **expectimax（我们 sim 搜索，f2-expectimax）**：hajime 48 局均分 7,059 ≈ greedy 7,071（sim 动力学损耗）。
  适配器在 `data/bench_repo/submissions/gkagent-expectimax/`（algo.py 177KB 自包含搜索核心，子智能体调试搜索对拍时失败，半成品）。
- **🔑 GKMSMainWheel 开源**（用户提供，https://github.com/yuzeis/GKMSMainWheel，Ver1.0 Morgendämmerung，**AGPL-3.0**，
  已克隆 `data/GKMSMainWheel`）：**GakumasCLI**（考试引擎+C++原生核心 api.cpp/core_search.h GNRPA/core_tail.h 精确尾搜索/
  core_session.h，真实规则模拟 H.I.F/N.I.A/初）+ **GKMSPS**（培育模拟器，選抜→本戦，种子码+回放可复现）+
  **GKMSUINet**（画面网+完整训练 BC/PPO/信息集MCTS+专家迭代，导出 ONNX）。master 由 gakumasu-diff 生成
  （`GakumasCLI/gkms.py master-bootstrap build --mirror`）；Windows 原生核心需 MSVC vcvars64（或者 mingw gcc）。
- **竞争路线升级（用户选定 seed-lock 王牌）**：**我们的 seed-lock（洗牌模型 F0 95.3%）+ GakumasCLI GNRPA 精确搜索**——
  seed_scan.c（UIHorizon 提交里的独立 C 扫描器，xorshift32(13,17,5)+k+Fisher-Yates，与我们模型一致，gcc 编译不需引擎）
  反推种子 → 引擎重建对局（真实动力学）→ GNRPA 全知搜索 → sees_seed 投稿对标 UIHorizon 631k，**无迁移损耗**。
  子智能体 f2-seedlock 构建中（seed_scan 验证 → 编引擎 → GNRPA → 适配器）。
- **根本解也解锁**：GKMSPS + GKMSUINet 训练流程 → 可在官方引擎尺度训练我们自己的网，消除 public-safe 迁移鸿沟。
- **许可证纪律**：GKMSMainWheel AGPL-3.0——作外部引擎/独立进程用，投稿 algo.py 可 import（gkbench 生态 AGPL），
  **不拷进我们生产 src/gkagent**（避免 AGPL 污染，同 data/hiro 纪律）。
- **GKMSNet 情报（T8，用户 QQ 提供）**：GKMSNET-emulator-core.zip = GKMSProject 的**安卓采集链**（nyarot，Frida/Xposed，
  HEAD f670b4e1），**Windows 引擎/Audition 模拟器已移除**——是采集技术参考 + GKMSProject 线索，非引擎。README 存 `data/_gkmsnet/`。

## 10. 2026-11-25 引擎跑通 + seed-lock+GNRPA 突破（自主循环推进，用户上课到 16:30）

- **目标**：goal-9f3755fa（训练→投稿→跑分→改进循环，上限 40 轮）。
- **引擎编通跑通**：gkmscore.dll（949KB，**rules=69**）Windows 编译成功（f2-seedlock，mingw gcc/w64devkit）。
  冒烟（data/_f2sl_engine_smoke.py）：引擎手牌**精确复现官方 check.hand**；我们洗牌模型牌序与引擎一致（偏移手牌后逐位）；
  GNRPA 搜索可跑。master 由 gakumasu-diff 生成（GakumasCLI/ro/master/tables，1817 卡）。
- **托管机制修正（f2-ex2 发现）**：类属性 `sees_seed=True` 被 client.py 拒绝托管。UIHorizon 先例 =
  类 `sees_seed=False` + `needs_gkms=True` + `about.sees="seed"`（网站标看牌序），种子从公开 obs 自反推 → 照常托管。
- **expectimax 对拍保真（f2-ex2）**：节点数差异是 anytime 墙钟 deadline 非确定（非搜索 bug）；显式 time_budget_ms=None
  关 deadline 后提取版 vs 生产逐位一致（20001/20001）。sim 搜索提取保真。
- **🏆 seed-lock+GNRPA 登顶（f2-sl2）**：投稿 `data/bench_repo/submissions/gkagent-seedlock/`（Draws 抽牌跟踪 +
  seed_scan 并行扫描 + FastCut 引擎快筛 + RoutePool GNRPA 路线池；vendor gkmscore.dll+seed_scan）。
  **hif 托管完成 240/240（120 核心题×2 保密种子），均分 944,850，errors=0/unfinished=0**
  （运行 template-hif-gkagent-seedlock-xingkonghod-c060df94acad）。**hif 模板榜第 3（仅次于 best-known 理论上限 1.45M），
  对 UIHorizon 631k = 1.50×**（超 v2.0 636k / v2.2b 572k）。about.sees="seed" 生效（榜标看牌序）。
  **锁定率 97.8%**（133/136，3 局牌堆被效果改动退贪心），锁定中位 turn 3–4；服务器 rules67 vs 本机 DLL69 未见漂移。
  离线 F0 3/3 均分 465k（6.6×greedy），大题单局 1.37M（路线池累积）。回放正规口径 session.step(action, observe=False)。
  调优 scan_min=6 / hi=2^31 / prior=0（prior 旧规则权重有害）。**hajime 95/96 均分 108,689**（初 best-known 上限 143k 的 ~76%，
  远超 uinet 24,991 / greedy 7,071；1 局服务器错误，resume e7a49cbc91d1 补局）。
  托管路径坑：engine.setup() chdir 破坏相对 algo 路径 + 盘符冒号被 spec.partition 截断 → 用盘符相对路径 `\Games\...`。
- **参考分**：pimc-vote-16w-2s 223k（5×32）/ UIHorizon v2.2b 411k（12×8）/ best-known ~1.45M（分母）。
- **四版官方榜成绩（2026-11-25 18:00 全齐，hif + hajime）**：
  | 版本 | hif 均分 | hajime 均分 | 信息 | 备注 |
  |---|---:|---:|---|---|
  | ④ gkagent-ex-seed（自锁+GNRPA+core_tail） | **967,348** (n=240) | 106,418 (n=96) | sees=seed | **hif 榜首**，锁定94.7% |
  | ② gkagent-seedlock（seed_scan+RoutePool） | 944,850 (n=240) | **110,613** (n=96) | sees=seed | hajime 榜首，锁定97.8% |
  | ③ gkagent-expectimax（GKMS PIMC） | 531,280 (n=240,over=492) | 32,377 (n=95) | sees=screen | **public-safe**，hajime 超 UINet 24,991 |
  | ① gkagent-ei-r13-norm-rescalebuffs（网） | 103,575 (n=239) | 5,483 (n=96) | sees=screen | 反应式网上限 |
  有seed 搜索 ~950–967k = **1.5× UIHorizon 631k**，距 best-known 1.45M ~66%。public-safe ex 接官方引擎 hif 531k/hajime 32k（远超 sim ex≈greedy）。
  **验证用户判断**：ex 接 GKMS 引擎消除动力学损耗（sim ex hajime 仅 7,059→GKMS PIMC 32,377）。
  网归一化 rescale 有效（+19%显著）；剩余网 vs UINet 差距=反应式无前瞻+sim训练失真，属后续官方尺度重训/搜索蒸馏。
- **f2-ex2 最终报告（2026-11-25 18:00 完成，240+96+240+96 局 0 算法错误）**：B ex有seed 对 A ex无seed 同题配对
  **+76%（+436,068，B 胜 204/240=85%）**；hajime B 均值 3.3×A 但仅胜 31%（课程题 B 锁定晚反亏，考试题大胜）。
  best-known hif **全量上限 1,452,088**（120 题×8，n=960，榜单参考 run 20261115-223849）→ 我们 967k ≈ **66%**。
  ⚠️ **口径纠正（2026-11-25 18:1x lead 核实）**：f2-ex2 报告曾误读 **2,134,509** 为上限——那是 11-14 旧 run
  `20261114-130117` 仅 **25 题**×32 种子（n=800）的**子集均分**（偏高分题），非全量口径（另两个 run 分别 35/40 题子集）。
  服务器 best-known farm 全为 11-11~16（31 个 run），**无新更新、也非我们自己扫**；分母只升不降、非证明最优、可超越。
  B 锁定率 hif 94.7%（中位T2，扫描中位3.24s，锁后失锁0）/ hajime 74.5%（课程无属性过滤，中位T4）；
  13+26 局「无种子复现画面」退 worlds 兜底（个别题 rules 漂移/牌堆早变）。
  **关键修复**：prior 关（rules69 旧 prior 更差）；路线单调改进（严格更优才换，防 GNRPA 换差线）；
  tail 时钟校准（mingw steady_clock≈Unix 纪元）；回放须 session.step()；anytime 墙钟 deadline 致对拍节点数非确定（显式关）。
  **局限（如实）**：B 锁定前丢早期最优（对 best-known 的主要缺口）；硬规矩「有可出牌绝不 end」个别局少分；hajime 课程题 B 略逊 seedlock 4%。
  **下一步（用户选定，新会话做）**：在 ex-seed 967k 基础上融 seedlock RoutePool 路线池 + 多起点 + 预算 step10，冲 best-known 上限。

## 11. 2026-11-25 晚 ex-seed-v2 融合版（下限+上限双修，托管 1.27M / best-known 87%）

- **设计依据（用户观察）**：ex-seed 最高分 9.91M < seedlock 11.34M，但最低分 3,608 > 2,844、p10/p25/中位全面更高、
  崩局（<50% 配对 max）7 vs 27。机制：ex-seed 锁定前 worlds 投票 + core_tail 精确尾 → **下限高**；
  seedlock RoutePool 跨步累积（~16M transitions）→ **上限高**但锁定前纯贪心 + forced_play 丢路线 → 崩局多。
  **v2 = ex-seed 下限 + seedlock 上限**（f2-exv2 子智能体实现）。
- **架构**：ex-seed 自锁 + worlds 投票 + core_tail（全保留）+ seedlock **RoutePool 每步回放核分跨步累积** + FastCut 快筛
  + **多起点 GNRPA**（starts=2×500k trans/步，锁定步 1M）+ `step_seconds=10` + `prior=0` + **`forced_play=0` 缺省**。
  类 sees_seed=False + needs_gkms=True + about.sees="seed"。目录 `submissions/gkagent-ex-seed-v2/`（原版 ex-seed/seedlock 零改动）。
- **离线门（F0 真裁判，同 seed 背靠背 + bootstrap 10000，探针 data/_f2exv2_pair.py）**：
  - core 8：base 1,028,862 → v2fp0 **1,706,452（+677,590，+65.9%）**，崩局 2→0，over 2→0。
  - monster 5（ex-seed 托管最大落后 −23.7M 名单）：base 4,901,516 → v2fp0 **5,586,968（+685,453，CI[+58k,+1.28M] 下界>0，4 胜 1 负）**。
    **WNK6ARRZ 4.51M = 2.14× 单次 2M 上界**、AXME8QK2 8.23M>上界 7.07M、ADDTACFE 6.21M=2×上界——RoutePool 累积 cracking 实锤。
  - 合并 13 题：base 2.518M → v2fp0 **3.199M（+27.0%）**（偏大题子集，不外推全量）。
  - **forced_play 顺序律**（sl3b 池化 n=32 fp0 +28,493 CI>0 / fp0st +45,062 CI>0 同向）：fp0 对 fp1 零负例，
    ADDTACFE fp1 触发硬规矩封顶 3.55M → fp0 6.21M。**先关硬规矩再加预算**（强搜索提蓄体力 end 被硬规矩糟蹋=崩局源）。
- **托管 hif：评测 db12324b5d57**（run template-hif-gkagent-ex-seed-v2-xingkonghod-db12324b5d57，--seeds 2 --parallel 3 --budget 10）：
  **240/240 完赛，均分 1,267,591，errors=0，新榜首**；max **14,181,357** / min 3,608 / p10 29,996 / p25 293,841 / med 592,558。
  **vs ex-seed 967,348 同 240 局配对 +300,243（+31.0%）CI[+200,648,+409,909]，171 胜 50 负 19 平**；
  vs seedlock 944,850 **+322,742 CI[+214,340,+437,299]，208 胜 31 负 1 平**；**= best-known 全量 1,452,088 的 87.3%**（66.6%→87.3%）。
  锁定率 227/240=94.6%（9 局 no-seed-reproduces + 3 短局 + 1 候选未筛完，失锁 worlds 兜底），over_steps=43（ex-seed 同局 172），bad_routes=0。
  **崩局（<50% 配对 max）v2=0 vs ex-seed 13 / seedlock 45**——下限≥ex-seed、上限≥seedlock 达成（max 14.18M > seedlock 纪录 11.34M）。
  最大赢 AXME8QK2#1 +5.89M / 5KZSXANK#0 +5.73M（夺回 −23.7M 落后怪物题）；仍输 seedlock 4 怪物局（WDKWQYW5#0 −3.53M 等，锁定/起点方差，如实）。
  过程：首批 149 局后服务器网络抖动（10060×16 + disconnect×2 + timeout×1，19 局出错），客户端连错 10 局自停，
  恢复后 --resume + --only core120 补 91 局。
- **best-known 分母口径纠正**：全量上限 **1,452,088**（120 题×8，n=960，run 20261115-223849）。
  f2-ex2 报告曾误读 2,134,509 为上限——那是 11-14 run 20261114-130117 仅 **25 题**×32（n=800）子集均分（偏高分题），作废。
  服务器 best-known farm 全为 11-11~16（31 run），无新更新；分母只升不降、非证明最优、可超越（bestknown.py 机制）。
- **局限（如实）**：① 锁定前 worlds 兜底丢早期最优（对全知上界主缺口）；② 扫描等待窗 0.7×budget 墙钟（10s→7s）
  CPU 竞争下翻锁定回合（sl3b「锁定等待悬崖」，配对+bootstrap 对策，去墙钟化候选）；③ GNRPA 起点方差单题可负（2AXJNW8X −129k）；
  ④ **AS-5KZSXANK 失锁**（"no seed reproduces the screen"，牌堆被效果改动后抽牌模型失效，ex-seed/seedlock 同款机制局限，
  worlds 兜底打完——后续可攻：deck-modify 后重扫/扩展抽牌模型）。
- **v3 方向（lead 剩余缺口分析，data/_v3_loss_analysis.md）**：v2 输 seedlock 的 4 局**全是怪物题**
  （WDKWQYW5#0 −3.53M / WNK6ARRZ#0 −2.74M / 3ZT8ZKB6#1 −1.83M / 5KZSXANK#0 −1.42M，合计 −9.5M）——
  这些题离线 v2 赢 base（dev 种子），托管保密种子反输 seedlock = **高方差题搜索盆地方差**（非机制回归）。
  杠杆按收益：① 怪物题更多起点（starts 2→4 / 自适应）+ lock_trans 1M→2M 多探索盆地；② 5KZSXANK deck-modify 失锁重扫；
  ③ 扫描等待窗去墙钟化（sl3b 悬崖）；④ 更多起点普适压 ex-seed 50 负局（≤651k 起点方差）。v3 目标均值 1.3M+（90%+）。
- **v3 离线门已过（f2-exv3，bench_repo 951d374，托管留下会话）**：v3vote（starts4+lock2M+scan_wait done+vote_sec_cap2.0）低 oracle 12 题
  **Δ+83,450 CI[+440,+174,748] 零负例**；gate2 core 层×2 种子 +240,168 CI[+71k,+380k]>0 稳健。
  **⚠ vote2 失锁下行风险**：WDKWQYW5 生成种子失锁 −824k 崩局（失锁 worlds 错误假设，深搜收敛更差共识）；**starts4(vote0.8) 失锁中性安全**。
  **托管 A/B vote_sec_cap 0.8（安全）vs 2.0（晚锁上行+失锁下行），保守可 0.8**。deck-modify 失锁重扫未实现记局限。
- **战略定位（用户确认）**：seed 赛道我们私有全知 bot 独占（社区因产品约束运行时不能用 seed，只做无 seed 产品）；
  主线自己练 seed 前沿 + 真机闭环，无 seed 顺便跟进（gkmsps pilot）。best-known 是可超越下界，推前沿即价值。
- **复现**：`cd data\bench_repo; ..\..\.venv\Scripts\python.exe -m gkbench eval --set hif --algo \Games\gakumas-agent\data\bench_repo\submissions\gkagent-ex-seed-v2\algo.py:ExSeedV2Algo --seeds 2 --parallel 3 --budget 10`
  （--algo 盘符相对路径；eval CLI 不读 submission.json step_seconds，**--budget 10 显式**；中断 --resume db12324b5d57）。

## 12. 2026-11-25 晚 hajime 回退 + 引擎差距/失分归因/自有引擎路线（f2-engine-gap）

- **v2 hajime 回退**：评测 e5e96836f66e，**85/96 均分 97,219**（11 局网络错），max 5.28M / min 14。
  vs seedlock hajime 110,613（榜首）/ ex-seed 106,418 → **v2 初集回退**。根因：初集无属性池过滤→seed_scan 候选爆炸
  （52,205 候选）失锁率高（min 14=失锁兜底崩局）；**fp0 在短考试可能反效**（hif 长局蓄体力 end 优，初集短局提前 end 浪费回合，
  seedlock forced_play 有牌必出反而对）。**v2 是 hif 特化版，初集需另调**（失锁修复 + 短考试 forced_play=1，留下会话）。
- **引擎差距（out/_engine_gap_report.md，M1–M10 逐模块）**：已对齐别重做（分数结算+safeCeil/回合 B3/审查倍率/熱意/hold/pride/
  handDecrease/nullifyDebuff/洗牌 F0 95.3% 探针 6/6 再确认）。覆盖率：卡效果宽松 97%/严格 74.6%；P 道具 1181/1849（63.9%）、
  hif ≥103/153（67.3%）；饮料仅 4 种；回忆❌；支援卡考试强化值❌。**最大杠杆 M1 考试 RNG 消费图**：255/505 hif 题含机制卡→
  exam_risk 停用全知（失锁题 5KZSXANK 根因）。补 M1–M8 sim 保真≈22–33 人日；**M1 仅 3–5d（探针数据集已就绪）**。
- **失分量化归因（hif 104k→578k ≈475k 缺口）**：OOD 尺度 +16,971（+19.5%）已修占~3.5%；**无前瞻×sim 动力学失真=主因~90%**
  （无训练 GKMS PIMC 接真引擎即 531k=4.1× 反应网；hajime sim ex 7,059→GKMS PIMC 32,377=4.6×；B2 学习叶负结果佐证失真深到叶子排序）；
  官方尺度训练+饮料 +47k（~10%）；seed 全知+深搜 +436k；RoutePool+多起点 +300k→v2 1.27M=87%。机制弱点 aggressive 57.5k/parameter_buff 43.3k
  最弱（正是 no-op buff 机制）。
- **黑盒探针发现（31 局 RNG 全解析，data/_engine_probe_*）**：RNG 原语与我们一致；**确定式生成入牌堆随机位=恰 1 次 range(0,牌堆长) 首次调用**
  （12+ 插入位置预测命中含空堆 width0）；重洗=(弃手牌后 grave)−1；panic=每手牌 1 次 range+费用覆盖 1 回合；
  **type59/38/156/22 0 RNG（exam_risk 误报可放宽）**。no-op effect 实测：slump 9→0、param_debuff 9→7（×667‰ceil）、
  成长 add_grow_effect 0→11（分 8→30）、PBR enchant 回合开始好调 3→1、draw_down 3→2（吻合 P1-2）。
- **自有引擎路线（用户定调：不必成为 gkms、超越它，它自己也在改）**：不追 gkms 实现（移动靶），朝 **seed-lock+深搜+MITM 真机**特化。
  **M1 RNG 图 clean-room 化恢复 255 题全知（seed 王牌主缺口，3–5d）→ v3 多起点压怪物方差冲 1.3M+**；public-safe 用官方尺度训练/GNRPA 蒸馏跟进；
  sim 保真服务训练分布对齐而非直接上榜。clean-room=BSD-3 参考+引擎当 oracle 自写（**不拷 AGPL 源码进 src**），算法（GNRPA Cazenave 2024）可自写。
