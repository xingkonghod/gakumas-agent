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

### 12.1 2026-11-26 hajime 修复（f2-hajime-tune）：v2h 离线门 vs seedlock 过 / vs v2 均分门负结果，托管 A/B 留下会话

- **根因实证（探针 data/_hajime_diag.py，48 题结构 + 样题扫描/整局）**：
  ① 初集 33/48 课程局（round=lesson，produce-001/006）**无属性池是引擎事实**（values=None / types=[] / k=0），
  非 v2 实现缺失——v2 opening.turn_pool 与 seedlock _turn_pool 同式，audition 15 题两者都有池过滤、v2 锁定正常。
  回退集中在课程局重牌小 deck 候选爆炸：GZP54V4T（10 卡 7 distinct，cap50）seen2→65.6M / seen8→94,660；
  WNAX63AN（28 卡 27 distinct）seen3→130,712 / seen6→30 / seen9→1（候选随抽牌指数塌缩）。
  v2 单扫 6 张起 + 只 FastCut（0.4ms×94k≈38s≫步预算）+ 短局打完未筛完 → 整局 worlds fp0 兜底（min 14）。
  ② **新发现：worlds 投票早期出牌触发 deck-modify 使抽牌模型丢真种子**（audition 也中招）：
  X8NXKZXW v2 scan 2 候选均 hand[0] 不符 → failed / s1 锁错种子 lost；DDCRRSTM scan 0 → failed 5,870
  vs seedlock 贪心早锁 21,734。**seedlock 不失锁真机制 = 课程局 3 张早扫 + 0.85 多等 + 抽牌 +3 重扫 +
  少量候选核对锁定 + 锁定前贪心 fp1**（clean-room 同语义自写）。
- **v2h（copy v2 后改，原版零改动；bench_repo feat 0fde532，sets=["hajime"]，sees_seed=False/needs_gkms=True/about.sees="seed"/prior=0 承 v2）**：
  short_greedy=1 锁定前贪心（保模型早锁）+ short_forced_play=1 锁定前有牌必出 + 课程局早扫 3 张/多等 0.85/
  重扫 rescan_above=8000（按 v2 FastCut 0.4ms 自调，seedlock 3ms 用 256）+ **锁定后承 v2 fp0**。
  short_exam 按 produce∈{001,002,003,006} 或无池判定（hif 也有 9–10 回合短局，不能按 turns 判）→ hif/nia 杠杆全关。
  **两个负结果回退**：fp1 锁定后反效（2AYFMJMR 250→135 / 35BS9YF4 166→114，强搜索路线 end 是最优蓄力，
  短考试 fp1 收益在锁定前不在锁定后）→ short_fp_locked=0；等价早锁 ≤8 锁错种子（2AYFMJMR turn3 锁错 → turn4 lost 160 vs 250，
  重牌 deck 等价种子未来分叉）→ lock_equiv_max=1 承 v2「恰剩 1 才锁」自然消歧。
- **离线门（data/_hajime_pair.py，48 题 ×2 生成种子 × 真裁判 rules69，同 seed 配对 + bootstrap 10000 CI，n=96）**：
  v2 145,652 / **v2h 147,095** / seedlock 103,716（budget 5 其缺省）。
  **v2h vs seedlock：Δ+43,379 CI[+6,490,+95,057]，53 胜 2 负 41 平，崩局 0 vs 13，lesson 层零负例（29 胜 0 负）→ 过**。
  **v2h vs v2 均分门：Δ+1,443（+1.0%）CI[−2,379,+5,661] 跨 0，17 胜 18 负 61 平 → 未过（负结果如实）**。
  根因：audition turn-1 出牌选择高分差硬币翻转（RBR82XW7 −116k / 5CRWDT5C −20k vs EEMMKQ5W +106k / HSAEP7SF +107k），
  n=96 欠功效；课程局贪心蓄力代价（B8CP3AG6 −213/−167 等）与小 cap 修复（NJS4FSVV min-14→50 等）相抵。
  **失锁率下降达成**：failed 4→0 / lost 1→0 / 锁定率 0.896→0.917 / min 10→18 / 墙钟 35.3→29.7s（−16%）；
  over_steps=0 / bad_routes=0 / errors=0。机制修复实证：X8NXKZXW failed/锁错→锁真种子、DDCRRSTM scan0→turn3 锁 +13,199、
  6S48T4EC scan0→锁、NJS4FSVV 14→50——正对托管 v2 回退机制（85/96 97,219 / min 14）。
- **hif core8 抽查（防误投）**：6/8 精确同分同路线，2/8 墙钟方差非负（Δ+397,494 CI[0,+1.17M]，2 胜 0 负 6 平），
  全 8 题 short_exam/fp_eff=false → **误投 hif 不回归**。
- **pytest**：全量 1705 passed exit 0（--basetemp=out/_pytest_tmp_hajime 绕 Temp ACL；排队友未提交 WIP
  tests/test_drinks_m6.py 6 败——M6 drinks 进行中工作，非本任务；src/gkagent 零改动；1681→1705 漂移来自队友近期提交）。
- **局限**：离线生成种子 ≠ 托管保密种子（离线 v2 145.7k vs 托管 97.2k，保密种子对 v2 失败更多；seedlock 离线 103.7k≈托管 110.6k）；
  deck-modify 真失锁未修（v3 杠杆④同局限，贪心只降触发概率）；课程局贪心中等局蓄力代价（崩局 v2h 4 vs v2 2，对 seedlock 0 vs 13）。
- **托管建议（留下会话，lead 统一调度）**：**值得投 hajime A/B**——v2h 离线严格优于 seedlock（CI>0/lesson 零负例/崩局 0），
  失败模式修复正对 v2 托管回退，墙钟 −16%（96 局 parallel 3 估 30–40min）；均分 vs v2 离线中性 → 托管保密种子才是判据。
  `cd data\bench_repo; ..\..\.venv\Scripts\python.exe -m gkbench eval --set hajime --algo \Games\gakumas-agent\data\bench_repo\submissions\gkagent-ex-seed-v2h\algo.py:ExSeedV2hAlgo --seeds 2 --parallel 3 --budget 10`
  （对照 v2 e5e96836f66e 97,219 / seedlock 110,613 / ex-seed 106,418）。
- **复现**：`data\_hajime_diag.py scan|game`、`data\_hajime_pair.py hajime v2,v2h,seedlock <shard> 2 1` / `hif v2,v2h` / `summary`
  （探针不提交；门数据 data/_hajime_pair_gate_s1.json / _hajime_pair_hif.json）。
  硬约束：DLL 不重编（MD5 与 v2/seedlock 一致）；原版零改动；AGPL 不拷 src；未碰 D:\Games\Gakumas；C:\GakumasLocal 只读；
  托管 40312fcb77a0 在跑期间离线 ≤2 局并行、free<0.6GB 暂停 90s 让托管（mem-guard 日志在探针输出）。

## 13. 2026-11-26 pilot r14 重启训练 + 离线门（ratio 2.33× PASS / z 尾部 FAIL）+ 饮料专项立项

- **pilot r14 训练重启成功**（昨晚卡住疑 OOM）：90,144 行 GKMS 尺度自对弈（教师均分 349,563），
  192×96/1200ep/4 线程限，682.6s；val 排序 0.510（≥0.50 擦线）；权重 out/ei_r14_gkmsps_pilot.json
  已入 submissions/gkagent-ei-r14/（bench_repo 提交）。
- **离线门 n=100 配对**：网均 **202,197** vs 贪心 86,804 = **2.33×（门 ≥1.3 PASS）**，85 胜 14 负 1 平，
  adapter 0 错 0 回退；**z 尾部门 FAIL**（max|z| 6.23/5.29/7.17 >3，p95 ≤2.32 全正常 = 极端局尾状态
  超训练分布）；候选修复 rescale/clamp 或补尾部训练分布，后续不静默忽略。详见投稿 RESULTS.md。
- **托管门完成（14:5x）**：240/240 均分 **≈205,614**（R0 175,668/R1 244,033/R2 204,556/R3 198,198，
  分块 4×60 抗重启清 eval）；≥150k 自设门 PASS 但距 screen 前沿 579.7k 差 ~374k → **确认非榜臂**
  （产品/真机 0.4ms 臂 + 训练管线验证）；冲榜靠 pimc-scale 扫参/native 工程。
- **饮料专项（用户指定重点投入）阶段1 完成**（drink-model 子智能体失败后 lead 接手收尾）：
  `scripts/build_drinks.py` + `data/knowledge/drinks.json` **29 瓶 / 51 效果段 / 33 实现**；
  `sim/drinks.py` 20 类效果分类 + `data/drinks_db.py` loadout 解析（不去重/未知显式上报）；
  DrinkSpec.effects 效果段列表（**默认空=旧行为逐位不变**）+ LessonSim/ExpectState 双镜
  （turn_start_draw 新字段进 canonical/rollout）+ expectimax 饮料剪枝扩到新 kind；
  `local_bench --drinks auto/off`（**默认 off**，greedy 3 题 auto/off 均分逐位同 1718.0）。
  **W9 全重放门绿**：终分 1,426,865 逐位 / 45 决策 0 mismatch / 逐决策 rng 含 4 饮料步 /
  喝一瓶前后增量 ↔ sim 逐效果配对；W7（0 饮料）655,198 回归绿。tests/test_drinks_m6.py 30 条。
  **RNG 口径**：蛋白粉 0 掷 / 苏打 4=抽牌触发支援强化掷点（归 m1-rng 图）/ 汉方 3=type9 搜索掷 /
  **青汁=create_random 未知显式 no-op**。
- **饮料专项阶段1.5 完成（drink-fix2，确定式增量批）**：4 种严选初星 ExamStatusEnchant 内层
  （回合结束集中/好印象/干劲 +1 = 玛奇朵/茶/拼配咖啡，回合开始全力值 +1 = 印度茶，effectTurn=-1
  永久）→ `turn_enchants` 新渠道（(kind,value,turns) 三元组）双镜；热绿茶 ExamCardMove
  deck_grave→hold（**pickRangeType=Select 玩家选牌，引擎 select_policy 不掷点**）+ ExamPreservation
  温存 2 段階直给（PItemDelta.stances 既有渠道）；焙茶温存变更（value1=1）side-effect 一并实现。
  **引擎 oracle 逐瓶配对全 PASS**（data/_drinks_probe5.py 不提交，6 瓶=5 批次+焙茶）：
  drink 步 rng_advances 全 0 / 附魔触发=好印象结算**前** + **endTurn 衰减 freshBuffs 保护**
  （当回合获得层本回合末不扣、下一回合末才扣；只对附魔渠道建模，卡/立即渠道沿用既有 sim 口径，
  旧行为逐位不变）/ 热绿茶 hold+1/deck-1/save2（greedy_select_policy 选牌事件）。
  catalog **40/51 段实现**（33→40，11 unknown）；hif 505 覆盖 **impl 2881→2984 段（+103）/
  78.7%→81.5%**（1629 槽位 / 3660 段）。tests/test_drinks_m6.py **49 条**（30 旧+19 新含 oracle 配对门）。
  批次实测槽位：玛奇朵 ×9 / 茶 ×7 / 拼配咖啡 ×42 / 印度茶 ×11 / 热绿茶 ×12 / 焙茶 ×10
  （立项背景"玛奇朵 ×38"系与黑醋汁 01-3-012 ×38 混淆，以实测为准）。
- **饮料阶段2 sim 侧完成（drink-fix2，batch2 + allow_drinks + 特征提取器）**：
  ① **batch2 catalog**（probe6 引擎 oracle 逐瓶全 PASS，rng=0）：ExamConcentration 强气直给
  1/2（姜汁汽水/超级苏打，stance 渠道复用 + concentration2 新分支）；黑醋汁 ExamCardMove
  deck_grave→hand（Select 玩家选牌）+ ExamSearchPlayCardStaminaConsumptionChange
  **cost0**（前 2 张正费牌整费归零、0 费牌不耗次数、第 3 张恢复，实测）；特制精华
  ExamCardSearchEffectPlayCountBuff **再发动**（纯分卡 1244=2×622 实测，1 次，喝回合+下一回合
  有效=effectTurn=1+fresh，过期正常；MentalSkill 不触发）。catalog **45/51 段实现**（40→45，
  6 unknown）；hif 覆盖 **impl 2984→3286（+302）/ 81.5%→89.8%**（特制精华 ×209 全实现是大头）。
  ② **生产 LessonPolicy allow_drinks opt-in**（默认 False 逐位不变；True 时搜索返回
  kind="drink" 动作）+ local_bench legal/loop 接通（旧版吞 drink 回退 greedy 的遗留修复，
  off 逐位不变）。**sim 配对门（SAFE 子集 39 题可映射 28 ×2 seed，cluster bootstrap 10000）**：
  greedy auto/off Δ=0（阴性对照，greedy 无 drink 启发式）；**expectimax-analytic Δ+43.1
  CI95[−97.6,+209.8] 跨 0 → 门未过（负结果如实）**，19 胜 9 负 28 平，崩局 0/0；
  归因：anytime fallback 30.6%（超时回 greedy 不喝）+ 28 平题搜索未选饮料（预算稀释，
  phase2 plan 预警命中）。SAFE 划分（drink_is_safe/SAFE_KINDS，纯数值段 22 kind）只约束
  sim 侧决策/特征——**引擎侧全饮料保留**（gnrpa-spec a86ffdc 实锤）。
  ③ **r14 饮料特征提取器**（src/gkagent/sim/drink_features.py，33 维定长 catalog 效果向量，
  **只写不激活**——重训分布漂移留 lead 排队；设计 out/_drinks_r14_features_design.md 不提交）。
  tests/test_drinks_m6.py **63 条**；全量 **1778 passed / 1 skipped / 0 failed**（drink3 basetemp）。
- **饮料阶段3① sim 搜索预算杠杆——四杠杆单变量门全阴性，sim 线收口（drink-fix2）**：
  机制=ExpectimaxConfig 三默认关旋钮（drink_root_only/drink_first/drink_top_k）+ local_bench
  `--drink-lever`（none 逐位不变已验证）。SAFE 28 题 ×2 seed=56 局配对基线 off，cluster
  bootstrap 10000，**CI 下界>0 才采纳**：
  | 杠杆 | Δ均值 | CI95 | 胜/负/平 | fallback | 喝瓶数 | 判定 |
  |---|---|---|---|---|---|---|
  | 基线 none | +43.1 | [−97.6,+209.8] | 19/9/28 | 30.6% | 51 | — |
  | ① root_only（递归不展开饮料） | **−70.2** | [−236.3,+45.8] | 15/7/34 | 31.6% | 28 | 否（严格更差） |
  | ② drink_first（根先评饮料 anytime 保留） | +16.4 | [−178.9,+208.8] | 20/9/27 | 30.2% | 51 | 否 |
  | ③ top2（候选 top-k） | +64.5 | [−80.9,+232.2] | 19/9/28 | 29.9% | 51 | 否（点估最佳但不显著） |
  | ③ top3 | +12.6 | [−183.6,+201.8] | 19/10/27 | 30.1% | 51 | 否 |
  **收口结论**：① fallback 率四杠杆不变（~30%）→ 预算稀释根因是**卡搜索子树本身**
  （0 费/抽牌链爆炸），非饮料展开——饮料侧预算重分配治不了；② root_only 喝瓶数 51→28
  且均分降 → 深层饮料规划（出牌序列后择机喝）有价值，不能砍；③ 饮料 sim 杠杆点估
  +43~+65 为正但 n=28 高方差下不显著 = **当前搜索预算/题规模下 sim 侧饮料杠杆天花板**；
  ④ 引擎侧 GNRPA 饮料杠杆实锤 +1.03M（gnrpa-spec）→ **饮料决策主线走引擎侧（v3 原生全饮料），
  sim 侧离线门欠功效**（anytime fallback 失真 + n 小）。后续若复探：加 n（全 SAFE 可映射题/
  更多 seed）或先修卡搜索 fallback（卡侧预算，非饮料 scope）。greedy 阴性对照 Δ=0 结构保持
  （杠杆只改 ExpectimaxPolicy）；off 逐位不变保持。tests 67 条（+4 杠杆回归）；
  全量 **1782 passed / 1 skipped / 0 failed**（drink4 basetemp）。
- **hif 505 题饮料覆盖实测（阶段2 杠杆真值）**：498/505 题带饮料；已实现大头=蛋白粉 extra_plays ×248 /
  苏打 ×235（4 段）/ 00-2-008 ×219（half_cost+score_buff）/ 02-3-010 ×209 / 03-3-011 extra_turn ×100；
  **最高频 pdrink_00-3-005 ×296 = 初星特制青汁**（ExamCardCreateSearch 随机生成，RNG 流未知，
  群线索"青汁会动rng"实锤；auto-gakumas 禁用规避）→ 保持 unknown，决策层保守不喝是免费杠杆
  （青汁X ×1 同保持 unknown）；batch2 后剩余 **6 unknown 段** = 青汁×2 + ExamCardUpgrade×2
  （新鲜果醋/初星强化能量）+ 混合果昔 ExamHandGraveCountCardDraw + 时尚草本茶依赖换算。
  SAFE 槽位 629/1629（38.6%）。阶段3=托管饮料决策（引擎侧全饮料）+ r14 重训门 +
  sim 搜索饮料预算优化（fallback 稀释是离线门未过主因）。
  样本吸收见 [RINAMI_LIVE.md](RINAMI_LIVE.md)；群情报 Bellman 上界/GakumasCLI 目标分早停见 QQ_GROUP_NOTES §12。
- **v3 托管 A/B（分块驱动 v2）**：服务器 **eval 注册表是内存 map（api.go `hosted map[string]*Hosted`），
  重启即清**——臂A 两次跑至 81+/240 局被 404 清掉实证；但**已上传 episodes 落盘且排行同 algo+同 rules
  合并、同题同种子取最新**（leaderboard_merge_test）→ **分块安全**。驱动 v2
  （data/_v3_hosted_ab2.ps1，不提交）：每臂 **4 块×30 题顺序**（单块 ~30min < 重启间隔），块内风暴
  --resume 续、404 本块重起；臂A vote0.8 → 臂B vote2.0；出分对标 1,267,591 / 1.3M 目标。
  旧驱动 v1（整 240 单评测）废弃：暴露窗 > 重启间隔必被清。
- **臂A（vote0.8）salvage 终果（n=238/240，被清评测 9ba9c00fb468 落盘 episodes）**：
  **1,329,581 vs v2 同局 1,273,137 = +56,445（+4.4%）**，CI95[−9,829, +124,551] 跨 0（怪物题方差），
  118 胜 81 负 39 平，**over_steps 7 vs 43**（scan_wait done 去墙钟实证）；点估已过 1.3M 目标但统计不显著。
  top+：3ZT8ZKB6#1 +3.0M / WDKWQYW5#0 +2.4M / AXME8QK2#1 +2.1M；top−：3EW6E6HV#1 −3.36M /
  F4FPT86S#1 −3.05M（同题 #0 +2.14M = 盆地硬币翻转）。缺 33JYSHDF#0/GN79HT4K#0 两局不补（边际小+
  补齐会墙钟重抽覆盖已落盘槽位）。探针 data/_v3_partial_cmp.py（不提交）。臂B vote2.0 分块跑中。
- **逐题相对上限拖尾（v3 salvage 230 oracle 配对，data/_v3_drag_analysis.py）**：v3 ratio mean
  **0.892**（v2 0.870，+2.2pp）；**58/230 局 >100% oracle**（前沿推进有效）；总缺口 28.77M，
  **top10 题占 71.8%**。拖尾 top：WDKWQYW5 5.27M（67.3%）/ 3EW6E6HV 4.52M（83.8% vs v2 95.8% **回退**）/
  QQ6J5S39 2.46M（68.5% vs 80.6% 回退）/ QV6QCSN9 1.78M（**24.9% vs 48.0% 回退=晚锁 vote0.8 丢回合**）/
  XPRY8BRF 1.67M（83.5% vs 96.9% 回退）/ 9VEFA9VH 0.92M（53.5% vs 81.5% 回退）——**拖尾里 5 题是 v3
  盆地硬币负侧/晚锁**，非信息缺口；失锁 deck-modify 托管残尾比预期小（5KZSXANK 95.1% / VWAF2GDN 73.7%）。
  反事实：top10 仅拉到 v2 均值比例 0.87 → 均分 +51k；拉到 oracle → +125k。**下一杠杆=per-problem
  自适应 starts/预算压方差 + 臂B vote2 治晚锁**；v3g 治失锁残尾。
- **M1 消费图阶段1 完成（m1-rng，feat 2daa7bb / docs d813d4d）**：rng_graph.py clean-room 366 行
  （create=1 次 range 首调用 / type9=2×nf signed_key / pick=1+nf / 重洗=n−1 / panic=每手牌 1 range /
  支援掷点门控公式 / type59/38/156/22=0）；**W7 27/27、W9 非饮料 41/41 逐决策匹配**；rules=69 引擎
  重放实机终分吻合**无版本漂移**；**静态扫 505：恢复全知 419 题（85%）**，仍风险 74 题全为
  type21 ExamCardCreateSearch 随机池（保守保留）；exam_risk opt-in 默认关逐位不变；pytest 1734/1。
  阶段2(a) predictive 牌区动力学完成（m1-fix2，feat 7e08a67）：card_zones.py 自写预测牌区演化，
  不再锚 oracle 消费事件。**已预测**（主数据驱动）：type9 选牌序 signed_key 带符号 int32 升序
  （阶段2 修正，探针①口径）/ enchant turn_start_draw（drinks.py 同口径）/ 回合开始主抽牌 /
  ExamCardDraw 立即+timer / ExamCardCreateId DECK_RANDOM / ExamCardMove search 2nf+pick 1+nf /
  reshuffle / support_rolls / encore 触发 move+draw。**W7 全 27 决策 predictive rng+牌区逐位匹配**；
  anchor_fallback 开关默认 predictive，fallback 与阶段1 逐位同（W7 27/W9 45）；W9 非饮料 41 rng 逐位
  （饮料步 owned-by-drinks）。**显式 unknown 不猜**（card_zones.UNKNOWN_TIMINGS）：① pitem 312 interval
  抽牌时机——主数据语义已推（card_play_interval interval=4 scope=exam / play_filter=好調组 / 条件好调≥8 /
  max_uses=5 / draw bundled ExamPlayableValueAdd），但精确 fire 含 DLL interval44_count 计数器+手牌上限
  跳过/复位交互，两局样本不足反推 → 留 (c) 探针；② 饮料侧 soda enchant 支援强化目标走独立饮料 rng
  （exam 流 0 消费，W9 k=7 rng_steps=12 实测）→ owned-by-drinks（M6）。另修：汉方 search_move=search 排序
  nf+pick 1+nf（nf=1→cons3）/ 饮料 idx 按剩余列表 pop / 弃牌→grave 强化路由口径。pytest 1762/1
  （test_drinks_m6 probe5 高负载偶发 ERROR，单跑 49 绿如实记）。
  阶段2 剩余：(b) v3g 接线离线门（失锁怪物重扫）→ (c) type21 探针（含 pitem 312 fire 口径逐场景刻画）。
  **饮料阶段2 设计**见 out/_drinks_phase2_plan.md（SAFE 纯数值段暴露进 v3d 动作空间、引擎原生核分；
  改牌堆/RNG/回合数饮料保守排除）。

## 14. 2026-11-26 任务⑥ expectimax-fast PIMC 超时优化（pimc-opt，bench_repo 6397bbb）

- **目标**：gkagent-expectimax（GKMS PIMC 无 seed，public-safe）托管 hif 531k（n=240）但
  **over_steps=492 超时多**，减 over 同时均分不降。新变体 `submissions/gkagent-expectimax-fast/`
  （**copy 后改，原版零改动**，MD5 核对一致）；缺省 worlds4/use0.70/anytime1/early_stop0。
- **超时根因实证（纠正「CPU 竞争」假设）**：① 本地真实裁判无网络原版 **over=0**、均 decide≈4.06s
  （data/_pimc_diag_local.py）；② **22 自旋子进程+3 局并发（>24vCPU）搜索墙钟仍 4.07s、over=0**
  （data/_pimc_stress.py）——C wall-deadline 帽住每搜索墙钟，竞争不拉伸；③ **服务器口径
  server/hosted.go:179 `serverMs=time.Since(obs_sent)−WorldsMs`**=搜索+overhead+(obs下载+action上传+
  worlds网络往返)，服务器只减自身 worlds 处理耗时、**不减网络往返**，算法补不到 obs/action 往返 →
  ~4.04s 搜索+~1.4s 不补偿 RTT=均步时 5.4s，RTT 尖峰推尾过 6.05s。**根因=网络 RTT，非竞争**。
  托管均步时 5406ms（中位 4164/p90 7454/max 28618），over 率随均步时升（≥5000ms 局 14.1%）；
  重灾题 K46XXQEY17/3EW6E6HV15/DS9H9NRD15/3BB4BWTR13/33JYSHDF12（data/_pimc_diag_eps.py）。
- **杠杆**（参数化单变量消融）：anytime 全局墙钟帽（每波按剩余全局时间重算 sec，总墙钟帽住）/
  use↓（降搜索墙钟给 RTT 留头寸=减 over 主杠杆）/ worlds6→4 / early_stop 共识早停 / step_trans（未门）。
- **离线 RTT 仿真配对门**（承 v3 先例，data/_pimc_pair.py 不提交；本地无网络 over=0 → 每步额外
  RTT overlay 仿真托管 serverMs，校准原版均步时 5176≈托管 5406；同 seed 背靠背+bootstrap 10000 CI
  种子 20261126；≤3 局并发 free>0.6GB）：**gate2 core8+重灾4 ×2seed=24 配对**（data/_pimc_gate2.json）：
  | 配置 | 均分 | meanΔ | CI95 | over | Δover |
  |---|---:|---:|---|---:|---:|
  | orig | 951,439 | — | — | 67 | — |
  | **u70w4 缺省** | 953,912 | +2,473 | [−233k,+236k] | **15** | **−78%** |
  | u70es | 970,053 | +18,615 | [−325k,+465k] | **1** | −98.5% |
- **门判定（如实负结果）**：over_steps 大降 **PASS**（−78%/−98.5% 逐题稳健）；**均分 CI 下界≥0 FAIL**
  （−233k/−325k）——均分点估计中性偏升但 CI 宽=**怪物题搜索盆地方差**（13胜11负，单题±1.5M：
  3EW6E6HV u70es+4.1M / K46XXQEY u70w4−1.58M / ADDTACFE u70es−1.8M）；原版 wall-clock anytime
  **负载非确定**（同题同种子 K46XXQEY 710k vs 2.01M，§10 f2-ex2 同款）基线漂移。严格非劣门在怪物题
  重子集+n=24 本质难达（原版自身复跑都过不了）。screen 6题消融 data/_pimc_screen.json（u70/u60/u70w4/u70es）。
- **关键澄清**：over_steps 是合规/公平指标，**服务器不因此扣分**（hosted.go over 仅打标，动作照常结算）
  → 减 over 不直接升均分；531k→UINet 578k 缺口是**搜索质量**问题，非超时问题（本优化不能逼近 578k）。
- **托管建议（留下会话，lead 排队）**：A/B fast 缺省（u70w4）vs 原版 `--seeds 2 --parallel 3 --budget 5`，
  预期 over 大降（合规价值）均分~531k 中性；激进 u70es（over≈0）有共识崩局风险保守 early_stop=0；
  全量 120×2 保密种子 CI 更紧是更强验证。**本次不跑托管**。
- **硬约束遵守**：未重编 DLL（rules69 外部 oracle）；原版 expectimax 零改动；未碰 D:\Games\Gakumas；
  探针 data/_pimc_*（diag_hosted/diag_eps/diag_local/stress/pair）不提交；pytest 绿（exit 0，
  --basetemp=out\_pytest_tmp_pimc；drinks test_drinks_m6 高负载偶发 flaky 单跑绿，drink-model 域，
  计数随他智能体新增至 ~1735，本任务未动 src/tests）。

## 15. 2026-11-26 GNRPA 特化 L1 domain prior + L4 SAFE drinks（gnrpa-spec，均负结果如实）

- **目标（用户指定特化 GKMSMainWheel 原生 C++ GNRPA，rules=69）**：只做 L1 domain prior + L4 SAFE drinks
  进 session 两杠杆有界离线实验；L2 rules timeline / L3 nesting 调度留后续。探针 data/_gnrpa_*（不提交）；
  先例 [data/knowledge/gnrpa_specialization.json](../data/knowledge/gnrpa_specialization.json)。
- **🔑 前提修正（探针1 实锤）**：任务书假设「v3 session.drinks 现状=空」**为误**。loadout `drink_ids` 直通
  `build_hif_loadout_session→SegmentConfig.drink_ids→NativeSession.drinks`（session 是 DLL native，
  `open_exam→native_session.open_loading`）；托管 core120 loadout **119/120 带 drink_ids**。故 **v3 原生 GNRPA
  已在搜全部饮料**（含青汁 00-3-005 create_random / 苏打 00-2-010 draw）——根节点 legal_drinks 全 4 瓶，
  current 短搜 path 含 drink 3=青汁。L4 真实杠杆不是「注入」而是「是否限制到 SAFE 子集」。
- **门方法**：低 oracle 12 ∪ monster 5 = **16 题 × 2 门种子**（s0 dev + s1 生成 exv3/1）= n=32 配对；
  搜索级（已知种子根 session，同 _f2exv3_pair bounds 口径）同 transitions=2M / seed=182 / stab=3，
  L1 prior 单变量（drinks=current）、L4 drinks 单变量（prior=None）；bootstrap 10000 CI 种子 20261126。
  自蒸馏教师种子 `pid/gnrpa-distill/{0,1}` 与门种子**不相交防泄漏**。管线确认 data/_gnrpa_probe3.py（真实 Referee）。
- **L1 domain prior（两路单变量，均 FAIL CI 下界>0 门）**：
  | 候选 | 构造口径 | overall meanΔ | CI95 | 正/负/零 | 判定 |
  |---|---|---:|---|---|---|
  | mech | cf0 特征=master 卡表 greedy 价值/费用效率，bonus∈[0,1.5] 只 boost 正分不压 setup（941 特征） | +49,074 | [−41,583, +189,168] | 7/13/12 | **FAIL**（下界<0；monster 下界=0 非>0） |
  | distill | `PS.learn_prior`(32 条 2M GNRPA 教师路线，回放核验 32/32)，1870 权重含饮料时机键 | **−184,442** | [−615,217, +191,459] | 16/16/0 | **FAIL**（均值负+2 次 status=2 早停退化） |
  - 分层：distill low12 CI[−34,326,+67,161] 跨 0、monster mean −620,172；mech low12 mean −31,799。
  - **机制（ anticipated 负结果实证）**：域知识进 bias 反而约束搜索——自蒸馏 prior 把 GNRPA 锁进教师盆地，
    高方差怪物题灾难负（WDKWQYW5 −4.4M / 5KZSXANK −2.9M / 3ZT8ZKB6 −1.4M），虽部分低 oracle 题正
    （3G6FFZZT +248k / AXME8QK2 +2.74M / VH8WYE6J +343k），16 正 16 负 wash。**prior=0 仍正确**；
    旧 prior 有害（§10/§11）rules=69 重建/蒸馏**未能翻案**。distill 2 次 status=2（WDKWQYW5/3601220 0.12s、
    WNK6ARRZ/1063386126 0.77s）= prior 诱发搜索早停病理。
- **L4 SAFE drinks（safe-vs-empty 过门，但 safe-vs-current 强负 → 不采纳限制）**：
  | 对比 | overall meanΔ | CI95 | 正/负/零 | 含义 |
  |---|---:|---|---|---|
  | safe vs empty | +135,292 | **[+23,612, +266,026]** | 21/5/6 | SAFE 饮料相对无饮料有价值（字面门 PASS） |
  | **safe vs current** | **−897,444** | **[−1,416,389, −451,108]** | 3/29/0 | **限制到 SAFE 纯丢分（强负）** |
  | current vs empty | +1,032,737 | [+533,212, +1,617,665] | 31/1/0 | 全饮料原生搜索价值巨大 |
  - 均分：current 2,157,172 / safe 1,259,727 / empty 1,124,435；喝频 current 3.69 / safe 1.25 / empty 0 瓶/局。
  - **管线确认（2 题×2 臂×1 dev 种子）**：3G6FFZZT current **1,285,228**（精确复现 §13 diag1 v3vote，喝青汁+苏打+008×2）
    锁定 T2 vs safe 444,204 锁定 T2；5KZSXANK current **8,631,520 锁定 T3**（dev 种子；托管失锁系保密种子牌堆改动非饮料）
    vs safe **2,510,455 失锁**（"no seed reproduces the screen"）。**锁定率 current 2/2 vs safe 1/2（safe 降锁定率）**；
    errors=0 / bad_routes=0；safe 两题均分<50% 配对 max（34.5%/29.1%）= 崩局。
  - **机制**：「RNG 未知/破坏 lock」排除理由适用于**我们 sim 侧抽牌模型（锁定前 scan）**，**不适用于引擎自身锁定后搜索**
    ——引擎用自己 RNG 确定式结算青汁 create_random/苏打 draw，post-lock 回放核分精确。限制饮料搜索空间=纯丢分，
    且改变早期打法路径可触发未建模牌堆改动→失锁（早期打法敏感，同 WDKWQYW5 现象）。**现状全饮料原生搜索保留**。
- **采纳**：**零代码改动 v3**（L1/L4 均负，prior=0 + 全饮料现状保留）；未创建 v3s 变体（无采纳杠杆）；
  先例文件 + 本节 + HANDOVER_NEXT 条。SAFE 划分（9 瓶，kind⊆SAFE_KINDS 且 rng 确定式）记先例文件供 sim 侧阶段2 复用。
- **L2/L3 建议**：① L2 失锁根因是 card-effect deck-modify（M1 消费图阶段2 predictive 牌区动力学 → v3g 重扫失锁怪物），
  非饮料；青汁/苏打 post-lock 引擎已最优无需 sim 建模 RNG。② L3 若后续用 prior 须 **per-problem 门控**（仅低 oracle 锁定题
  opt-in、怪物题禁用）或 prior 只作多起点之一（starts 中 1 路带 prior 其余 prior=0，RoutePool 单调采纳兜底），不可全局。
  ③ L4 免费杠杆=决策层锁定前 worlds 保守不喝青汁（避早期失锁）已有先例；post-lock 全饮料保留；饮料阶段2 重心在 sim 侧
  r14 特征/生产 allow_drinks 而非限制引擎搜索。
- **硬约束遵守**：未重编 DLL（vendor rules69 外部调用）；AGPL 不拷 src（探针 data/ 按路径 import 引擎）；未碰
  D:\Games\Gakumas / C:\GakumasLocal 只读；**未改 drinks.py/drinks_db.py（drink-fix2 owns）/rng_graph.py（m1-fix2 owns）/
  exam_risk.py**；v2/v3 原版零改动（v3s 骨架已移除）；data/_f2*/card_library.json/REPORT.md 及他智能体脏文件未提交；
  探针单进程顺序 ≤1 局、批次前查 free<0.9GB sleep60（门尾段 free 520–900MB 自动等待）；未起托管未杀进程。
  pytest **1763 collected / 106 文件，复跑 exit 0 全绿**（--basetemp=out\_pytest_tmp_gnrpa）；首跑
  test_challenge::test_runs_until_runout_then_returns_home 高负载墙钟 flake 1 例**单跑绿**如实记（HANDOVER §8 同款），本任务未动 src/tests。

## 16. 2026-11-26 M1 阶段2 (b) v3g 接线离线门 + (c) type21/pitem312 探针（m1-fix3）

- **(b) v3g 接线（bench_repo feat，copy v3 改，v2/v3 原版零改动，vendor DLL/exe MD5 与 v3 全一致不重编）**：
  新变体 `submissions/gkagent-ex-seed-v3g/`（入口 `ExSeedV3gAlgo`）= v3 全机制 + **杠杆④ deck-modify 失锁重扫**
  + **消费图 graph-clean opt-in 门**（`vendor/m1_graph.py` clean-room 自写，口径=`exam_risk.known_info_ok(use_graph=True)`，
  505 牌组 **0 mismatch**；`m1_rng_index.json` 预计算未刻画索引仅 2 卡，托管自包含无需 src）。
- **失锁根因实证**（`data/_m1b_monster_diag.json` 不提交）：B38CARVV/VWAF2GDN/HTNFZWKG/5KZSXANK 牌堆被卡效果改动后
  `Draws.open=False`，**冻结 seen/skip 被 deck-modify 污染**→seed_scan 内核排除真种子（B38CARVV/HTNFZWKG `frozen_match=False`）→
  "no seed reproduces the screen" 整局 worlds 兜底。**首 obs（turn1 开局抽牌，deck-modify 之前）opening_seen 可靠**
  （4 怪物 `opening_match` 全 True）→ 失锁时改用开局可靠抽牌重扫候选，FastCut 手牌回放（真引擎=完美 predictive 牌区）+
  整屏 `_same` 防假锁；只对 graph-clean 启用（type21 未刻画保守不重扫）。`rescan_open=1` 缺省，=0 复现 v3。
- **离线配对门**（`data/_m1b_pair.py` 不提交，承 `_f2exv3_pair` 真实裁判同 seed 背靠背 + bootstrap 10000 CI 种子 20261126）：
  **怪物 4×2 seed（n=8）PASS**——锁定率 **0.625→1.0**，均分 Δ **+80,278 CI95[+11,702,+183,976] 下界>0**，3 胜 5 平 0 负，
  崩局 v3g=0（v3=1）/ over 0 / bad_routes 0。**3 个 frozen_match=False 失锁局全恢复锁定**：B38CARVV s0 +93,616 /
  VWAF2GDN s0 +133,818 / HTNFZWKG s0 **+414,790**（锁定后 RoutePool 替代 worlds，墙钟反降 158.8→119.4s）；
  5KZSXANK 两 seed v3 已锁（dev 8.63M 锁T3，同 §15 gnrpa-spec）中性。
  **恢复集 graph-clean 12 题×1 seed 回归守卫 12/12 逐位中性**（重扫只失锁触发）。
  **合并门 n=20**：锁定率 0.85→1.0、均分 +32,111、3 胜 17 平 0 负、崩局 0、over 0；**overall CI95[0,+80,281] 下界=0**
  （17 中性例稀释 bootstrap，monster 子集下界+11,702>0；承 v3 diag1 零例稀释同款，如实记）。
  **重扫步 max_ms≈10.7s**（开局弱约束候选多，扫描 8s+FastCut）仍<12.05s 阈值 over=0，托管 3 并行 CPU 竞争需留意。
- **(c) 探针（≤6 局，data/_m1b_* 不提交）**：① **type21 ExamCardCreateSearch**（sup-3_024 ×3 题）cons≈**132/135/136**，
  生成卡**入手牌**（非牌堆无插入），消费与牌堆长无关（3/7/12 无相关）→ 随机池权重/signed_key 口径**未完全刻画**，
  保守保留 unmodeled，**静态扫 505 恢复维持 419/493（85%）**，74 题仍风险全 sup-3_024。
  ② **pitem 312 interval fire**（rinami W7/W9 重放 + DLL `trigger_effect_states` 捕获）：**核心规则已刻画**——rules=69
  计数器是 **`phase_count`**（`interval44_count` 未填充 has_interval44=False），好調 parameter_buff 效果组合格出牌 phase_count++
  （encore +2），**跨越 4 的倍数即 fire 抽 1**，`limit_count=5`（max_uses）用尽冻结，fire 抽牌 0 RNG（bundled ExamPlayableValueAdd）；
  W7 fire k=(9,15,20)/W9=(11,15,21,28,34) 与锚点逐位吻合。**仍 unknown**：「好调≥8」门确切语义（stance=None 样本）+
  手牌上限跳过交互（样本未触发）未泛化 → card_zones 保留 unknown 锚点（新增 `PITEM312_PROBE` 记录机制），不静默放宽 predictive。
- **src 改动（主仓 feat）**：`card_zones.py` unknown 锚点富化（pitem312 phase_count 机制 + type21 实测）+ 新增 `PITEM312_PROBE`；
  `rng_graph.py` type21 注释补实测；`tests/test_m1_predictive.py` +2 锚点测试（pitem312 机制/type21 仍 unmodeled）。
  **exam_risk 默认行为零改动**（opt-in 口径不变）；M1 41 + predictive 测试绿。
- **托管建议（留下会话）**：A/B v3g(rescan_open=1) vs v3(=0) `--seeds 2 --parallel 3 --budget 10` 盘符相对路径；
  预期 graph-clean 失锁题（deck-modify 子类）锁定率升+分数升、锁定题中性；重扫步墙钟接近阈值留意 over。本次不跑托管。
- **硬约束遵守**：未重编 DLL；v2/v3 原版零改动；AGPL 不拷 src（m1_graph clean-room）；未碰 D:\Games\Gakumas / C:\GakumasLocal 只读；
  **未改 drinks/expectimax/lesson.py 与 local_bench.py**（饮料域已提交，gnrpa-spec 在读）；探针 data/_m1b_* 不提交；
  引擎单局串行 free<0.9GB sleep60；未起托管未杀进程；path-limited git add（并发 index 纪律）。
  pytest --basetemp=out\_pytest_tmp_m1b **1793 passed / 1 skipped / 0 failed**（226.6s exit0，本跑无 flake）。

## 16.5 2026-11-26 GNRPA 特化 L3 下行有界 prior（gnrpa-spec 续派，均负结果如实，零采纳；撞号修复：M1 2b 占 §16）

- **目标（lead 续派窄 scope）**：prior 全局有害（§15）但**下行有界用法**候选——① multi-start prior（starts=4 恰 1 路带 prior，
  mech/distill 各单变量）其余 prior=0，RoutePool 单调采纳兜底；② per-problem 门控（仅低 oracle 锁定题 opt-in、怪物禁用）；
  ③ distill status=2 早停根因（廉价）。门同 §15：16 题×2 门种子 n=32 vs 全 prior=0，**CI 下界>0 才采纳**。
  探针 data/_gnrpa_probe4/5/5b/6/7.py（不提交）；先例 [gnrpa_specialization.json](../data/knowledge/gnrpa_specialization.json) L3 节。
- **① multi-start replace-i3**（sd_i=182+7919*i，i=3 带 prior；multi=max(p0_0,p0_1,p0_2,prior_3)，baseline=max(4×p0)；
  单步 max 代理=保守 worst-case，RoutePool 跨步累积未建模）：
  | 候选 | overall meanΔ | CI95 | 怪物 meanΔ | 正/负/零 | 判定 |
  |---|---:|---|---:|---|---|
  | multi_mech | −33,289 | [−87,472, +8,455] | −105,552 | 3/8/21 | **FAIL** |
  | multi_distill | −22,241 | [−100,386, +65,476] | −57,692 | 3/9/20 | **FAIL** |
  - **🔑 怪物灾难有界实证**：distill 怪物 mean **−57,692 vs §15 单搜全局怪物 −620,172**——下行被 max(前3 prior=0) 兜住，
    不再 −4.4M 灾难（lead 假设成立）。负因=i=3 恰为最佳起点时替换 forfeit 上行（3G6FFZZT p0_3=1.11M 最佳、mech_3=894k → −219k）。
- **① additive 单调口径**（prior 作第 5 路，multi=max(baseline,prior_3)≥baseline 恒成立=真单调零下行，「在手路线不降分」理想）：
  additive_distill overall **mean +36,111 CI[0, +103,246]**、怪物 +99,602（含 5KZSXANK **+996,017**）；additive_mech +8,694 CI[0,+22,472]；
  **0 负例**（构造性单调安全）但 **CI 下界=0**（29 平稀释仅 3 正）→ 严格 CI>0 门 **FAIL**。**near-miss**：可证不害但稀疏正例不足过门；
  更多种子或可收紧 CI（lead 决策是否放宽「可证不害」门）。
- **② per-problem 门控**（opt_in=LOW12−MONSTER5=11 题，WDKWQYW5 属怪物禁用；复用 §15 gate1 行单变量推导）：
  gated_distill overall mean +9,362 CI[−23,796, +46,443]（opt_in n22 +13,618 CI[−34,326,+67,161]）；
  gated_mech −21,862 CI[−54,845, +12,947]。**均 FAIL CI>0**（门控去掉怪物灾难但低 oracle 题 prior 增益本就不显著）。
- **③ status=2 根因（实锤，廉价）**：**=稳定化早停（stabilization=3），非 deadline/unsupported/预算耗尽**。
  distill 早停 top_level_calls 11/40 vs p0 282/240、curve 早平台、repetition_stops=0/unsup=0/incomplete=0；
  WDKWQYW5/3601220 distill **stab=3→status2 exp66,733 best3.56M / stab=1→status0 跑满 2M top_calls911 best3.99M**。
  机制=prior 过约束致策略快速收敛局部最优→3 稳定窗口即终止；即便 stab=1 消除早停，best3.99M 仍<<p0 7.96M=prior 本身有害（早停雪上加霜）。
  multi-start 亦见 status2（mech_3 AXME8QK2 exp5231 / distill_3 AXME8QK2 exp975379）。rc=2 精确语义需 core 源（不深究）。
- **采纳**：**L3 全候选未过严格 CI 下界>0 门 → 零采纳，无 v3s**（prior=0 仍缺省）。先例 json 更新 L3 负结果。
  正面发现存档：multi-start 兜住怪物下行（−57k vs −620k）；additive 单调零下行 near-miss（mean+36k/CI下界=0）。
- **硬约束遵守**：path-limited add+commit（禁 reset/checkout 共享 index）；未改 drinks/rng_graph/exam_risk/expectimax/lesson；
  free<0.9GB 自节流（本轮 free 4.2GB 充足）；探针单进程≤1 局；未起托管；v2/v3 原版零改动；探针 data/_gnrpa_* 不提交。
  pytest --basetemp=out\_pytest_tmp_gnrpa2：本任务 docs/knowledge 隔离**无 src/tests**；full **1779 collected** 中
  **test_drinks_m6.py（63）foreign 确定式失败**（drink-fix2 在跑域：src/drinks.py+drinks.json+test_drinks_m6.py 均其脏文件；
  stage15 classify select_move_hand vs unknown / catalog 45 vs 40 等，**单跑仍失败=非墙钟 flake**）；
  **--ignore=tests/test_drinks_m6.py 后 1716 全绿 exit 0**（含 m1 predictive）。未改 drinks/rng_graph/exam_risk/expectimax/lesson，foreign 失败不静默归本任务。
- **lead 裁决（2026-11-26 13:1x）**：① **additive 单调 prior 不放宽门、暂不采纳**——离线 transitions 口径的
  构造性单调**在托管墙钟预算下不成立**（第 5 路挤占其它路墙钟，或总预算 +25% 非免费）；mean +36k ≈ +1.7%
  杠杆小于 v3g deck-modify 失锁怪物缺口（WDKWQYW5 单题 7.2M）。若后续推：须**墙钟 overlay 门**
  （pimc gate2 RTT overlay 先例）+ 更多种子收紧 CI，且只作 opt-in 多起点之一、不进缺省。
  ② status=2=stab 早停已实锤：未来若用 prior 须 stab=1 + 全局墙钟帽（anytime 先例）。
  ③ drink-fix2 在跑域 test_drinks_m6 63 确定式败 = 其 batch2 中途 WIP 不一致（catalog 45 vs 40 /
  select_move_hand 分类），**lead 在其收尾时验收单跑修复**，非 gnrpa 域、不静默。
  ④ GNRPA 特化专项结论：**引擎原生 GNRPA + prior=0 + 全饮料 = 当前最优配置**；特化杠杆剩余空间在
  L2 rules timeline（待 M1 deck-modify 结论）与搜索预算调度，不在 prior。

## 17. 2026-11-26 ⑦ 全流程 sim 评估收尾（plug-fix 接手 gkmsps-plug 失败遗局；GKMSPS 外部 import，不拷 src）

- **目标（lead 窄 DoD）**：用前任 glue [scripts/gkmsps_plug.py](../scripts/gkmsps_plug.py) 跑 **N=100 配对培育局**
  （同 seed）plug 臂（r14 考试搜索 + 我们培育决策）vs GKMSPS 默认臂（`cli.auto(sensible=True)` smoke policy），
  最终考试均分 + 评价点 bootstrap CI + 分段归因（课程/考试/饮料）+ 青汁消融 ≤20。计划 [out/_gkmsps_plug_plan.md](../out/_gkmsps_plug_plan.md)、
  差距 [out/_engine_gap_report.md](../out/_engine_gap_report.md) M10。AGPL 引擎只外部 import、DLL 不重编、引擎工作树零写入。
- **前任已完成（ substantial 半成品）**：glue 全文（缺件①master 枚举重拼写 267 表/263955 枚举 ②master_ps.json
  ③master_extra.json 生成 + 进程内存 monkeypatch）；Values 卡估值（probe8 引擎列重权 v1.3）+ 饮料 SAFE 估值；
  PlugProduce 培育规则（课程审查基准加权补短板 / 体力门 8/12 / 积极买卡扩组 / 饮料保留 / 事件估值）；play_exam r14
  适配器（`uinet.uiobs.from_session` 与托管同口径）；run_arm（default/plug/plug-engine）+ attribute + boot_ci/paired_stats
  + aojiru_ablation + 内存自节流；formation_v2/v3；probe1–9；smoke(n=1)+pilot5(n=5) 已跑。
- **🔑 前任核心缺口（本任补齐）**：pilot5/smoke **全零**（completed 0/0）——真实選抜两臂全 `lost`。probe11 实测
  **選抜 NPC 墙**（idol 固定难度带，rank≤2）：mid1 双 **6035** / mid2 双 **49806** / final 双 **136347**；两臂培育上限
  远不及 mid2/final（probe10：v2 plug mid1 6151 过、mid2 8379 rank6 lost；v2/v3 default mid1 即 lost）。前任 probe9
  已用 `exam_assume` 强制選抜过关验证本戦链（rating 16772 SS），但 **run_arm/main 未接 assume**→无法产出非退化评估。
  本任补 `--sel-assume`（两臂選抜考试同值强制过关、選抜培育仍真实、**本戦全真实**）+ `--resume`（崩溃增量续跑）
  + `_default_drive`（`cli.auto(sensible=True)` 逐字镜像 + 選抜 assume 拦截，policy RNG 构造一致）。
- **formation 选型 v2（probe12 实证 v3 反而弱）**：v3「1500」能力实际仅 +25/attr（v2「450」+15），且 v3 全 phase1
  = 起始 **12 张**牌组稀释（v2 = 10 张，phase2 两张 mid1 后才到）→ v3 plug mid1 2500 < v2 6151。选 v2（probe9 验证 + 稀释小）。
- **N=100 配对结果**（sel-assume 300000、formation_v2、tag gkmsps-plug-v1、69.7s、**100/100 两臂全完成**；
  [out/_gkmsps_plug_report.json](../out/_gkmsps_plug_report.json) / games.jsonl；probe13 独立复核 CI 逐位一致）：
  | 指标 | plug | default | 配对差 mean | CI95 | 胜 P/D/T | 判定 |
  |---|---:|---:|---:|---|---|---|
  | **评价点 rating** | 16682.42 | 16514.77 | **+167.65** | **[+83.75, +249.10]** | 60/38/2 | **显著正（+1.0%）** |
  | **本戦终试 round2** | 25456.7 | 23924.98 | +1531.72 | [−2374.44, +5530.81] | 41/59/0 | **跨 0 不显著** |
  | 本戦 Round1 hon_mid1 | 20989.0 | 20839.4 | +149.65 | [−2416.98, +2624.11] | 50/50/0 | 跨 0 中性 |
  | **本戦末参数 params_total** | 5680.31 | 5634.46 | **+45.85** | **[+12.89, +78.26]** | 59/40/1 | **显著正** |
  | 選抜终试 sel_final | 300000 | 300000 | 0 | [0,0] | 0/0/100 | 设计置零（assume） |
  - grade 分布：plug **SS 99 / S+ 1** vs default SS 91 / S+ 9（plug 更稳 SS）。round2 std 20139（怪物方差，median 差 −2549，default 胜局反而多）。
- **分段归因（均值）**：rating 差 +167.65 = **param_term +91.70**（=2×params，params 差 +45.85）+ **star_term +75.95**；
  **round1_term = round2_term = 0**——本戦 mid1 分 <360k、final 分 <600k 远低于 `HIF_ROUND1/2` piecewise 阈值（probe11：
  本戦 final NPC 墙 ~618k，round2 全部 <<600k）→ **评价点公式在可达分段不奖励考试分**，rating ≈ 2×params + star_term（pre_round2_star capped 1110）。
  選抜课程 lesson_param plug 1004.4 vs default 919.5（**+84.9**，plug 偏 Vo）；選抜 param_gain_total 3713.6 vs 3655.3（+58.3）；
  本戦 exam_reward_param 两臂 0（本戦考试付星/PP 非参数）。饮料：plug gained 6.78 / discarded 2.21 / aojiru 0 / **drunk_exam 0**（r14 从不喝）；
  本戦末 drinks_left plug **3.61** vs default **2.15**（plug 保留多但考试不喝 = **未消费价值**）。⚠ default 臂 `stats` 全空（auto 无计数器），
  其 drinks_mean=0 是**口径假象非实测**（drinks_left 实测见上）。
- **青汁消融（考试级注入配对，n=20，drunk 20/20）**：本戦终试 loadout 注入 pdrink_00-3-005 + 强制首口喝 vs r14 不喝，同 seed：
  no_aojiru 21090.1 / aojiru 26993.2 / **差 +5903.1 CI[+159.2, +12192.0] 显著正但脆弱**（std_diff 13959，CI 下界仅 +159）。
  量化 unknown RNG 扰动代价：考试级喝青汁**净正**（保守 avoid 可能漏价值），但 n=20 + 巨方差 → 不轻易改 produce 决策。
- **瓶颈判定（如实）**：① **選抜 NPC 墙是根本瓶颈**——真实培育两臂都过不了 mid2/final，必须 assume 才能评估本戦（sim 保真/培育强度缺口）；
  ② **本戦 final 墙 ~618k** → round2 全 <<600k → r2_term=0，**考试搜索强度在此口径下无 rating 杠杆**（round2/hon_mid1 均跨 0，
  与 M10/臂A「怪物方差硬币翻转」一致；smoke root0 r14 mid1 34204 vs greedy 13868 的考试优势被 N=100 方差淹没）；
  ③ **培育决策（params）是 rating 的真实杠杆**（+45.85 显著 → rating +167.65 显著，+1.0%）——plug 培育（课程加权补短板 + 买卡扩组 + 饮料保留）
  比 default smoke 多 ~46 params；④ 饮料保留多但 r14 考试不喝 = 未消费价值（饮料→考试消费链是后续杠杆）。
  **结论：plug 全流程显著但微小优（+1.0% rating），增益主因培育段；考试段强但 rating 公式不奖励 → 培育是瓶颈杠杆，非考试搜索。**
- **硬约束遵守**：path-limited add+commit（禁 reset/checkout 共享 index）；**未改 src/gkagent/sim/* 与 policy/***（m8-fresh/m1-fix3 owns）；
  未碰 D:\Games\Gakumas、C:\GakumasLocal 只读；data/_f2*、card_library.json、REPORT.md 不提交；submissions 原版零改动；
  AGPL 不拷 src、DLL 不重编、引擎工作树零写入；free<0.9GB sleep60 自节流（本轮 free 4.0GB 充足）；引擎单进程≤1 局（未起托管未杀进程）；
  探针 data/_gkmsps_plug_probe10–13.py 不提交。本任务 glue+docs 隔离无 src/tests 改动。
- **前任完成/缺失清单 + 本任补齐**：见 [HANDOVER_NEXT §8 交接条](HANDOVER_NEXT.md)。glue 由本任首次提交（feat）+ docs 哈希条。

## 18. 2026-11-26 新竞争者 huochai67（gakumas-engine Pure-Rust）+ uinet 口径纠正

- **huochai67（新 ID，不在 QQ 群成员表；身份未确认，可能群潜水者拿到分享包）**今日投稿系列：
  | run | n | 均分 | max | over | 步预算 | rules | sees |
  |---|---:|---:|---:|---:|---|---:|---|
  | **gakumas-engine-gknet-v3** | 360 | **579,653** | 5.20M | 1 | **300ms/step**（内部 budget_ms=300，server cap 5s） | 67 | screen |
  | gakumas-engine-pimc-v2（盲打无 NN） | 360 | 557,127 | 6.01M | 3 | 300ms/step | 67 | screen |
  | gakumas-engine-pimc-dev（**seedlock** channel） | 4×3 run | 797k–1,015k | — | — | 300ms/step | 67 | screen（自锁） |
- **架构**：Pure-Rust 引擎 + **GKNet-v2 counterfactual advantage NN**（<0.1ms 推理，w_adv=0.2 /
  w_pol=0.02）+ **32 reshuffled-world 多线程 Rust GNRPA+PIMC hybrid**（threads=16, level=2,
  inner_iter=20）。**NN 思想与我们 B11 policy/advantage 独立收敛**；训练纪律干净：仅 non-core 题 +
  PLv≥60 榜单捕获，**零 Core-120 重叠**（防泄漏声明）。
- **效率警示**：300ms/step 搜索拿到 579.7k ≈ 我们 public-safe Python PIMC ~3.5s 搜索的 531k 之上
  → **native 速度+多线程是我们 public-safe 臂的工程差距**；NN hybrid 相对盲打仅 +22.5k（300ms 下
  NN 增益小，搜索主导）。
- **seed 赛道威胁**：pimc-dev seedlock 300ms/step 4 局样本 0.8–1.0M；若放大到 10s 预算将挑战我们
  1.27M/1.33M。**rules 67 与我们 v2 同排合并口径**（我们 v3 salvage 亦 67）；其全量 run 待观察。
- **看不看牌序（配对实证，lead 14:0x）**：**gknet-v3/pimc-v2 主投稿=盲打不看**（sees=screen +
  detail「UIObs v1 + opening loadout only」+ 32 reshuffled worlds determinization）；gknet vs pimc-v2
  同 360 配对 **+22,526（199胜156负）**= blind 内 NN 增益。**dev seedlock mode=试图自锁牌序**
  （同我们 ex-seed 路线）但锁不稳：P8ZJTXNA +150k（锁住增益）/ **WDKWQYW5 反比盲打低 1.7–2.7M**
  （失锁兜底或锁错，与我们 deck-modify 局限同构）/ A7TVEQAN、DE36RWPS 中性 → n=4 不定论。
  **申报口径问题**：其 dev about.sees 仍标 "screen"（我们 v2/v3 标 "seed"）——若 seedlock 真看牌序
  应按 seed 类申报，混排不公；观察/必要时向 matto 提出。结论：579.7k 是盲打真效率；seed 臂 dev
  试水未全量、锁稳定性存疑 → 短期威胁有限但需盯。
- **⚠️ uinet 口径二次纠正（screen 榜全 72 行核实 + 37 run 时间线）**：1.633M run finished
  **2026-11-11T18:32Z = 北京 11-12 02:32**（run 20261112-022847，n=480 fixed32）、1.109M =
  11-11T20:07Z = 北京 04:07（n=320）——matto 11-11 晚**密集扫参**（18:18–20:07Z 每 ~5min 一个 run，
  mean 216k–1.63M 剧烈跳动）→ **1M+ 是扫参尖峰非稳定水位**；排行同 algo 合并取最新 per-slot，
  该 run 虽在合并行 runs 列表里但同槽位被其后 17 个 run 覆盖 → 当前 uinet 行 469,890（n=960）/
  fixed32 15 题行 270,845；**screen 真前沿 = huochai67 gknet-v3 579,653（n=360 solid）/ UINet-Ver2.1 578,722
  （n=960 rules 59）/ uinet-ppo-r1 575,585**；榜顶 pimc-dev 791,138 仅 n=4（seedlock mode 却申报
  screen，口径问题实锤影响榜单）。**我们 screen 最强实测 = gkagent-expectimax 531,280（n=240、
  over 492）排第 9**，距 solid 榜首 ~48k。UIHorizon 636k 系 sees_seed=true 属 seed 组不计。
  我们 seed 行 v3 合并 1,322,681（n=240）/ v2 1,267,591 / best-known 1,486,205（rules 65）口径不变。
- **应对**：① r14 托管门优先级上调（GKMS 尺度 NN 是我们 public-safe 唯一接近对方 NN 路线的资产）；
  ② seed 行 per-problem 方差杠杆 + v3g 继续（拖尾 top10=71.8% 缺口）；③ 观察 huochai67 seedlock
  全量与身份（群/api.github.com 晚些补）；④ native 速度差距记工程债（Rust/多线程搜索不在本期 scope）。

## 19. 2026-11-26 public-safe 搜索规模杠杆扫参门（pscale，bench_repo 3d9b9aa）——w32t16 过门采纳，天花板=引擎吞吐非调度

- **目标（承 §18）**：531,280（n=240、worlds6/threads4/use0.85、over492）vs solid 榜首 huochai67
  gknet-v3 579,653（32w/16t/native Rust/300ms）差 ~48k，假设**部分来自世界数/线程/预算调度而非引擎速度**。
  新变体 `submissions/gkagent-expectimax-scale/`（**copy fast 改，原版/fast 零改动** git diff 空），
  单变量扫 **worlds{6,12,24,32}×threads{4,8,16}**（u70+anytime1 基）+ 原版 u85 无 anytime 分离臂 3 点。
- **门方法（承 §14 pimc-opt 实证口径，探针 data/_pscale_pair.py 不提交）**：screen6 ∪ 重灾4 = **7 题×2 seed
  = 14 配对**（种子同 gate2 派生）；真实裁判同 seed 背靠背 + **墙钟 overlay 仿真托管 5s cap**
  （每步 RTT 0.9+exp(0.45)≈1.35s **不补偿**，over 阈值 6050ms）+ bootstrap 10000 CI 种子 20261126；
  **门：均分 CI 下界>0 且 over 不恶化**。16 配置×14 对=**224 局 0 err**，≤2 局并发、free<0.9GB sleep60
  自节流（托管 v3 臂B+r14 parallel3 在跑，尾段 free 0.33GB 多次等待），墙钟 358.7min。
- **逐配置门表（n=14，基线 orig 均分 1,118,530 / over35 / step5195ms）**：
  | 配置 | 均分 | meanΔ | CI95 | over/Δover | decide均ms | sec/search | 门 |
  |---|---:|---:|---|---|---:|---:|---|
  | w6t4 | 1,231,577 | +113,048 | [−226k,+536k] | 9 / −26 | 3207 | 0.505 | over-only |
  | w6t8 | 1,237,378 | +118,848 | [−421k,+806k] | 11 / −24 | 3198 | 0.891 | over-only |
  | w6t16 | 1,034,216 | −84,314 | [−708k,+572k] | 11 / −24 | 3220 | 1.501 | over-only |
  | w12t4 | 1,479,513 | +360,983 | [−141k,+903k] | 9 / −26 | 3256 | 0.279 | over-only |
  | w12t8 | 1,461,290 | +342,761 | [−327k,+1111k] | 9 / −26 | 3256 | 0.468 | over-only |
  | w12t16 | 1,533,785 | +415,255 | [−206k,+1119k] | 9 / −26 | 3263 | 0.787 | over-only |
  | w24t4 | 1,386,124 | +267,594 | [−342k,+933k] | 9 / −26 | 3232 | 0.161 | over-only |
  | w24t8 | 1,373,478 | +254,949 | [−375k,+945k] | 10 / −25 | 3236 | 0.267 | over-only |
  | w24t16 | 1,449,525 | +330,996 | [−156k,+882k] | 12 / −23 | 3255 | 0.415 | over-only |
  | w32t4 | 1,399,718 | +281,189 | [−186k,+826k] | 9 / −26 | 3239 | 0.146 | over-only |
  | w32t8 | 1,106,106 | −12,423 | [−460k,+457k] | 9 / −26 | 3260 | 0.199 | over-only |
  | **w32t16 采纳** | **1,637,739** | **+519,210** | **[+4,054,+1,041,445]** | **14 / −21** | 3275 | 0.321 | **PASS** |
  | w12t4_o（u85 分离） | 1,355,185 | +236,656 | [−481k,+1062k] | 40 / **+5** | 3854 | 0.261 | FAIL |
  | w32t4_o（u85 分离） | 1,503,489 | +384,959 | [−50k,+841k] | 44 / **+9** | 3927 | 0.101 | FAIL |
  | w32t16_o（u85 分离） | 1,268,482 | +149,953 | [−526k,+897k] | 37 / **+2** | 3871 | 0.402 | FAIL |
- **采纳判定**：**w32t16（u70+anytime1）唯一过门 → scale 缺省 worlds32/threads16**。LOO 稳健性 **8/14**
  （_pscale_robust.py），增益跨 5 怪物题（ADDTACFE+1.52M / 3EW6E6HV+2.23M+1.98M / DS9H9NRD+1.60M /
  3BB4BWTR+852k / K46XXQEY+1.00M）**非单题驱动**；最大负例 K46XXQEY −1.08M / DS9H9NRD −966k（盆地硬币翻转）。
  **如实警示**：CI 下界仅 +4k **薄**（n=14 怪物重子集；换 bootstrap 序 +9.8k 仍>0）；w32t16 over14 高于
  其它 fast 点 9–12；子集 +46% **不能外推全量 120**（简单题稀释）；基线墙钟漂移实锤（orig ADDTACFE
  s1207168678 本跑 1.86M vs gate2 同种子 2.33M，§14 同款）。其余 11 点 over-only 不采纳；
  **u85 无 anytime 分离臂 over 恶化 → use0.70+anytime 是规模化前置杠杆**（原版调度下 32 世界 decide~3.9s 过帽）。
- **🔑 天花板结论（纠正任务假设）**：「Python 每世界成本太高 → worlds↑ 过帽」**不成立**——anytime 帽下
  decide 全网格平坦 **3.20–3.28s**、worlds_s≤0.047s（32 世界）、jobs_frac≈1.0，over 全降。真实约束 =
  **每搜索深度稀释**（sec/search orig 0.535s → w32t4 **0.146s** 浅搜噪声大，w32t8 均分 −12k）+ 怪物方差；
  threads↑ 恢复深度（w32t16 0.321s），但 **w6t16 最深 1.5s 却均分负**（6 世界期望方差太大）→
  甜点 = **多世界 × 足线程保 ~0.3s/搜索**。对 gknet-v3 同 32w/16t 调度我们需 ~3.28s 墙钟（其 300ms native+NN）
  → **剩余 ~48k 差距主体 = 每墙钟秒搜索吞吐（引擎速度+NN 引导）工程债（§18④），调度杠杆真实但有界**。
- **托管建议（留下会话，lead 排队，排 v3 臂B 后）**：A/B scale（w32t16）vs 原版 `--seeds 2 --parallel 3 --budget 5`，
  预期 over ~−60%、均分中性偏正（怪物增益/简单题中性）；16 线程×parallel3=48>24vCPU，native wall-deadline
  帽住搜索（§14 stress 实证），Python overhead/内存留意（离线尾段 free 0.33GB 自节流实证）；全量 120×2 保密种子
  CI 更紧是更强验证。**本次不跑托管**。
- **硬约束遵守**：未重编 DLL；原版/fast 零改动；AGPL 不拷 src；未碰 D:\Games\Gakumas / C:\GakumasLocal 只读；
  **未改 src/gkagent/sim/* 与 policy/***（M8 收口）；探针 data/_pscale_*（pair/table/robust/rows/gate/smoke）不提交；
  data/_f2*/card_library.json/REPORT.md 未提交；≤2 局并发 free<0.9GB sleep60 未起托管未杀进程；
  pathspec 限定 commit（bench_repo 3d9b9aa 仅 submissions/gkagent-expectimax-scale；主仓仅 docs/GKBENCH.md）；
  pytest bench_repo test_ctx+test_save **15 passed/9 skipped**（--basetemp=out\_pytest_tmp_pscale；
  test_bench_runner fcntl POSIX-only Windows 无法收集 pre-existing；主仓 src/tests 零改动）。

## 20. 2026-11-27 完结日 ex-seed-v4（规模自适应起点）——托管 1,372,156（+3.74% vs v3，best-known 94.5%）

- **结果**：`gkagent-ex-seed-v4` 托管 **240/240 = 1,372,156**（best-known 1,452,088 的 **94.5%**、榜顶
  1,486,205 的 92.3%；总榜第 3，hosted/外部投稿第 1）。errors=0 / **over=13**（v3 为 8）；30 个分块、
  总墙钟 **8757s ≈ 2.4h**（`--parallel 3`，`--seeds 2 --budget 10`）。v3 行 1,322,681 保留不变。
- **动机（v3 逐槽缺口分层，`data/_v3_gap240.py`）**：v3 配对 232 槽 ratio mean 0.892 / median 0.929，
  总缺口 28.8M；按 `step_type`：**AUDITION_FINAL 132 槽 218.5M 分、占缺口 77.7%**，MID1 98.9M/20.1%，
  MID2 10.7M/2.2%；三层 ratio 都是 ~0.89（无系统性弱项，**绝对值差 2–4×**）→ 决赛题单位比例增益最值钱。
- **先证伪「深度」杠杆**（`data/_v4_pair.py` b1，同题同 seed 配对）：AS-5KZSXANK `step_trans`
  500k→1M→2M 分数**逐位相同 8,631,520**，墙钟 1.72×/2.82× → transitions 帽不是瓶颈、10s 预算有 5–8× 余量。
- **杠杆⑤ 规模自适应起点（采纳）**：`starts_hi=6`（`limit_turn>=12` 才启用，其余 `starts=4`）。
  离线配对（`_v4_pair_s8a/_s6a`，5 题 × 1 seed，基线复用 diag1 v3 行）：12 回合决赛
  AS-5KZSXANK **+1,496,003**（6 与 8 同分，取 6）、AS-QV6QCSN9 +280,434、AS-P8ZJTXNA 0；
  9 回合中期 AS-3G6FFZZT **−224,133**（s6）/−210,772（s8）、VH8WYE6J 0 → **分档而非全局加**（同一杠杆
  在两类题方向相反：决赛盆地方差主导、中期每起点墙钟短→深度稀释）。
- **托管配对（v4 vs v3 同槽，latest-per-slot）**：逐槽 Δ 合计 **+11,874,028（+4.28%）**；
  **FINAL +11,145,429（+5.10%，132 槽，71 胜 43 负）**；MID1 +728,599（+0.74%，108 槽，43 胜 33 负，
  **配置未变 → 全部来自 v3g 失锁重扫**）。最大单槽：AS-3EW6E6HV/1 **+3,362,268（+31.1%）** /
  AS-YGF972ZK/1 +2,200,161（+25.7%）/ AS-5KZSXANK/0 **+1,566,827（+21.6%，与离线门 +1,496,003 同量级）** /
  AS-F4FPT86S/1 +1,277,706（+29.1%）/ AS-AXME8QK2/0 +926,143；最大负例 AS-QQ6J5S39/0 −912,557。
- **逐槽噪声口径实锤**：同 config 重跑的重复槽位分差 ±5–7%（AS-C3Y5EFGV/1 843,558→828,963、
  AS-D34KGR3N/0 762,344→817,710）→ **单槽不可比，只看 240 槽聚合**；聚合后「没变的 MID1」落回 +0.74%、
  「真变的 FINAL」稳定 +5.10%，方向可信。
- **v4 后的剩余缺口（`data/_v4_gap240.py`）**：配对 232 槽 **ratio mean 0.923 / median 0.939**、
  paired mean 1,397,897、总缺口 **17.24M**（v3 28.8M）。top：**AS-WDKWQYW5 70.4%（4.76M）** /
  **AS-QQ6J5S39 62.1%（2.95M）** / AS-AXME8QK2 83.6%（2.77M，MID） / AS-BZXB28YJ 81.8%（2.51M） /
  AS-YSNBNDV4 60.6%（1.27M，MID） / AS-QV6QCSN9 51.2%（1.15M） / B8ZWDS3J 73.3% / P8ZJTXNA 64.2% /
  VWAF2GDN 62.0% / PPHWPMPP 58.8%；3EW6E6HV 已到 **98.1%**（v4 基本收口）。
- **提交**：bench_repo **9228583**（feat，v4 = copy v3g 改，v2/v3/v3g 原版零改动、vendor DLL/exe MD5 全一致
  不重编）+ **3c12f20**（RESULTS 真机数）。主仓 docs 本条 + HANDOVER_NEXT 条。
- **纪律遵守**：未改 src/tests；探针 `data/_v4_*`（pair/hosted/groups/progress/gap240/ep_diag）、
  `data/_meta_probe.py`、`data/_alloc_analysis.py`、`data/_v3_slots.json`、`data/_lb_*.py` 均不提交；
  pathspec 限定 commit；DLL 不重编；未碰 D:\Games\Gakumas / C:\GakumasLocal 只读。
- **v5（未开跑，用户 16:19 叫停去开新会话）**：原候选 = v4 + `vote_sec_cap` 0.8→2.0（仅 12 回合决赛；
  依据 diag1 QV6QCSN9 +324k；门脚本 `data/_v4_pair.py` 已支持 `v5`/`v5b`/`v5t` 配置，跑了一半即停，零提交）。
- **下一阶段方向（用户指令）**：不再靠参数微调，**改引擎 + 搜索**，做 v5，目标**大幅超过 best-known**
  （1,452,088 / 1,486,205），达标后**群里全部开源**。剩余缺口集中在 ~10 道怪物题（搜索质量/方差），
  参考 §18/§19：native 吞吐是工程债（gknet-v3 300ms/step ≈ 我们 3.5s）、prior 类均负（§15/§16.5）、
  tail 目前 `tail_turns=2` 精确、`status=2`=stabilization 早停。

## 21. 2026-11-27 晚 ex-seed-v5「改引擎/搜索」阶段：预算饱和多波次并行 RoutePool + GNRPA 配置组合（bench_repo 3ef3f83）

- **用户指令**：不再靠参数微调，**改引擎 + 搜索**做 v5；目标先过 best-known 1,452,088、冲 1.5M+；达标后群里开源。
  本节记录**做了什么、证据、负结果、托管数字**（探针 `data/_v5_*` 不提交；投稿目录 `submissions/gkagent-ex-seed-v5/`）。
- **第一性分析（v4 托管 240 局逐步记录全量拉取，`data/_v5_lockscan.py`，240/240 槽）**：
  - **238/240 局锁定**（仅 2 局整局 worlds 兜底；QQ6J5S39/1 是唯一失锁怪物）→ **缺口不是「锁不住」而是锁定后的搜索质量**，
    这是本轮最重要的纠偏（此前假设 monster 题=失锁兜底问题）。
  - 锁定回合分布：lock 1–2 有 143 槽（均分 1,433,476）、lock 3 有 84 槽（1,368,202）、**lock≥4 有 11 槽（588,174）**。
  - **每步 10s 预算只用 2.3–4.3s**：GNRPA `transitions=500k`/起点 ≈0.5s 先到（v4 已证伪加 transitions 有效），剩余墙钟空转。
  - 最大单槽缺口：AXME8QK2/1 −3.28M（lock2）、WDKWQYW5/1 −3.00M（lock3）、BZXB28YJ/1 −2.92M（lock2）、
    QQ6J5S39/1 −1.80M（失锁）、QQ6J5S39/0 −1.15M；232 配对槽里 **68 槽（29.3%）我们已超 best-known farm 逐槽最大值**（+18.3M）。
- **🔑 天花板校准（`data/_v5_ceiling.py`，写报告的可行性基准）**：把 232 配对槽的缺口全抹平（低于 oracle 的补到
  oracle、已超的保留）→ 240 槽均分 **1,499,295**（≈1.5M）。所以「过 1,452,088」= 逐槽比例从 0.923 提到 **~0.986**
  （几乎逐槽追平 best-known 12 个 farm run 的逐槽最大）→ **1.50M 就是「逐槽逼近 farm 最大」的量级**，
  1.55M+ 需要全面反超 farm。这个校准说明该目标基本等于「把搜索打到 farm 上限」，本轮据此排优先级。
- **搜索质量探针（同状态、同 transitions 预算）**：
  - 多 sd 重启分布（`_v5_restart_curve.py`）：AS-AXME8QK2 turn4 12 个 sd → 6.11M/中位 7.23M/**max 9.70M**（1.6× 跨度）；
    AS-BZXB28YJ turn4 → 1.64M/2.74M/**5.37M**（3.3×）；但**深局会收敛**（AS-WDKWQYW5 turn8 全部 4.91M、QV6QCSN9 turn6 全部 340,811）。
  - GNRPA 配置网格（`_v5_engine_grid.py`：levels 2/3/4 × iterations 8/16 × stabilization 3/5）：同状态
    **`stabilization=5` 在 AS-5KZSXANK +31%**（7.30M→9.54M）、**`iterations=16` 在 AS-AXME8QK2 +26%**（7.50M→9.43M），
    但**没有一组全胜**（i16s5 在 5KZSXANK 反而 −6%）→ 做成逐起点轮换的**配置组合**。
  - **整局配对 A/B 中性**：固定换 i16/s5 后 AS-AXME8QK2 −0.8%、AS-WDKWQYW5 +0.07%。机制解释：
    末段 `core_tail` 精确尾 + 早期动作主导终局分，中途搜索的「终局分估计」变好不一定改变首动作。
- **v5 采纳（三条，全部只取更高终局分 → 单调安全；v4 逐位可复现：waves=1/threads=1/portfolio 空/root_scan=0）**：
  ① **多波次**：一波跑完只要 `t_end`（0.7×预算）前还有时间就再发一波（新 sd），缺省 `waves=2` 上限
  （**不用填满**：实测填满墙钟 ×2.6–3、240 槽要 ~7h）；
  ② **并行独立 core 副本**：一波内每起点在自己的 core 上并行搜（`session.search_tables()` 天然一份 core、ctypes 释放 GIL），
  `pool_threads=4` → 同等墙钟 2× 起点；
  ③ **搜索配置组合**：逐起点轮换 `(levels,iterations,stabilization)=2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8`（首项= v4 口径）。
- **负结果（都做了门，默认关，仅留对照臂；不得复用重复试）**：
  - `root_scan` 根动作枚举（每合法首动作先走一步再完整续搜）：离线 2 局 −9%/−1%、托管 5 槽中性 → 不采纳
    （GNRPA 的首动作已覆盖得不错）。
  - `mirror_vote` 锁定前候选镜像后验投票（代替 `ctx.worlds()` 随机世界）：候选管线在 worlds 投票前就锁定 → 实测几乎不触发；
    托管 5 槽 2 胜 3 负 CI 跨 0 → 默认关。
  - 固定 i16/s5：同状态 +10–25%，整局中性 → 只进组合臂。
  - 填满预算 `waves=0`：墙钟 ×2.6–3、离线中性 → 改上限 2 波。
  - transitions 500k→2M：与 v4 b1 同结论（同分，2.09–2.41s/搜索）→ 不加。
- **托管 240 槽（结果）**：`gkagent-ex-seed-v5` 缺省参数（waves=2 / threads=4 / portfolio 如上 / starts4+starts_hi6 /
  lock2M / step500k / vote0.8 / rescan1 / tail2 / fp0 / prior0），`--seeds 2 --parallel 5 --budget 10`，分块 6 题驱动：
  **240/240 = 1,447,036（v4 1,372,156 → +74,881 / +5.46%；best-known 1,452,088 的 99.65%、榜顶 1,486,205 的 97.4%）**，
  errors 0 / over 8 / 总墙钟 4,138s（69min）。逐槽 **130 胜 / 88 负 / 22 平**，相对 best-known farm 逐槽 oracle 的比例
  **0.9227 → 0.9535**（= 天花板 1,499,295 的 96.5%）。**分层：AUDITION_MID1 +12,162,517（108 槽，+112,616/槽，63胜33负）**
  —— v4 中期只有 starts=4、v5 给了同样的波次所以吃到最大增益；**AUDITION_FINAL +5,808,820（132 槽，+44,006/槽，67胜55负）**。
  最大单槽增益 AS-YGF972ZK/1 +3.80M / AS-BZXB28YJ/0 +3.60M / AS-5KZSXANK/0 +2.96M / AS-AXME8QK2/1 +2.62M；
  最大负例 AS-3EW6E6HV/1 −2.81M（其 v4 分 14.18M 高于 farm oracle 13.95M = 幸运抽样）/ AS-F4FPT86S/0 −1.70M /
  AS-WNK6ARRZ 两槽 −2.86M。**方差**：逐槽 Δ 的 sd = 585,504 → meanΔ 的 95%CI ≈ [−708, +150,469]，
  5.46% 点估计方向由 130:88 胜率 + oracle 比例 +3.1pt 支撑（240 槽仍不足以让 5.46% 统计显著）。
- **官方合并行**：同参数组 n=230 均分 **1,458,384**（> best-known 1,452,088）/ over 8 / p95 5.96s / p50 1.96s /
  ep_think 70.4s；另 11 个槽来自两个早期 v5 候选配置（\d943f444dfb0\ 5 槽 portfolio+mirror/waves=1、
  \d617abc6ed04\ 6 槽填满预算版），按纪律**不重跑已结算槽** → 官方出 3 行同 label；
  **我们自己的口径（每槽最新）= 1,447,036**。
- **v5b 对照臂（waves 2→3，负结果）**：同机制、每步 12→18 个起点，托管 240/240 = **1,398,855**
  （vs v4 +26,699 / +1.95%，但 **vs v5 −48,182 / −3.33%**；oracle 比例 0.9440 < v5 的 0.9535）。
  逐槽 vs v5：93 胜 / 99 负 / 48 平（meanΔ −48,182，sd 578,012，CI≈[−122,803,+26,440]）；分层 FINAL +22,817/槽、
  MID +31,444/槽（都低于 v5 的 +44,006 / +112,616）。**机制解释：over 8→57、p95 5.96→8.54s** —— 每步 18 起点顶到
  10s/12.05s deadline 上限，被截断的搜索（status≠0）RoutePool 不采纳 = 白烧；**v5 的 12 起点是留了余量的甜点**。
  结论：**加起点必须留 deadline 余量；下一维度要提「每墙钟秒搜索吞吐」而不是继续加起点**（bench_repo cc0a35e feat +
  `submissions/gkagent-ex-seed-v5b/RESULTS.md`）。
- **工程坑（本轮新增）**：
  - 服务器间歇 SYN 丢包（`WinError 10060` / "Server disconnected"）：eval 连续 10 局错就自动停 → 分块驱动按
    `/api/runs` 已完成槽位续跑；**评测注册表在服务器内存，重启即清**（`/api/evals/<id>` 404）。
  - 服务器慢时（RTT 0.8–2s）整局墙钟被 RTT 放大：每局 ~40 决策 × RTT ≈ +40–80s，长跑前先测 `/api/sets` 延迟。
  - 离线引擎（本机 rules=69 口径）与托管结算**不同源**：同一题离线 11.8M vs 托管 6.7M → 离线门只能看方向。
- **下一阶段建议（按性价比）**：① 若本轮 240 槽聚合 ≥ v4，把 waves/threads 上限与配置组合再扫一档
  （2→3 波、threads 4→6）；② 真正的大头仍是**每墙钟秒的搜索吞吐**（native/repo 外部编译，§18④ 工程债）与
  **状态价值/策略引导**（B11 学习叶子在 large 场景仍负，但 policy/advantage 路线在 large 显著超 beam，可做「导航」而非叶子）；
  ③ `lock≥4` 的 11 槽（均分 588k）与 8 个无 oracle 的 produce-008 低分槽（400–870k）是独立可攻点；
  ④ 精确尾 horizon（tail_turns=3）需先证明 3 回合能在 8s 内 complete（当前 2 回合在深局已 deadline）。

## 22. 2026-11-27 深夜 v6「先修引擎/搜索再全算力」阶段：每步墙钟构成 + 预算内自适应波次（准入控制）（bench_repo cd35efa）

- **用户指令（OPENING_v6 §3）**：先测量（①）→ 波次准入控制（②）→ 并行/线程配比（③）→ prior 引导（④）→
  tail 3 回合（⑤）→ 独立可攻点（⑥）；**①–③ 修完先跑 20–30 槽小样门，过门再一次性单 eval 全量 240**；
  纪律不变（DLL 不重编 / AGPL 只引用 / 探针不提交 / pathspec 提交 / 托管只补缺题 / 跑托管时不开本地重探针）。
- **① 每步墙钟构成（`data/_v6_stepscan.py` 拉 v5 240 局 8,000 步 → `_v6_analyze.py`）**：
  - 按步模式（ms）：`route` 4,770 步 mean 2,147 / `search` 664 步 mean 4,197（这两类=锁定后 pool 搜索）/
    `worlds` 1,043 步 mean 4,287 / `tail` 1,422 步 mean **94**（绝大多数锁定后早 proven）/ `fallback` 3 步
    mean 14,628 / `forced` 51 步 mean 637；**总 think 17,890s**（240 局）。
  - **锁定后每步只用了 2.4s / 7s**（`search_use`×budget）：6,898 个锁定步在 7s 内合计空转 **35,359s = 2.9×**
    —— 这是 v5 的「可换墙钟」，也是 ② 的动机（不是加预算，是把空转换成不会被截断的起点）。
  - `scan_s` mean 2s（p90 4 / max 8）；lock_turn：1–2 有 145 槽、3 有 78 槽、≥4 有 14 槽、失锁 3 槽。
  - **over（>12.05s）13 步（我们「每槽最新」口径；官方 v5 行 n=230 over=8）全部来自锁定前候选管线**：
    `worlds` 7 + `fallback` 2 + `search` 3 + `route` 1；机制=P8ZJTXNA 扫描出 **12,171 候选**时每步在
    FastCut/mirror 管线里烧 10.5–27s（`lock_pipe=1.05`×budget 的 deadline），叠加 `scan_wait_cap=0.95`（9.5s）
    + vote + RTT。**锁定后的 pool 搜索没有 status≠0**（0 次）——即 v5 的 over 不是 pool 波次造成的。
  - **v5b（waves=3）over=57 的机制复核**（`data/_v6_v5bsteps.json`）：每步 18 起点；`route` 步 mean
    4,260ms（v5 2,147）、`search` 步 mean 6,189（v5 4,197）、p95 8.5s、max 23.4s。**`pool_status` 依旧全 0**——
    注意 `core_search` 的 status 0 = 「内部无失败」，**撞 deadline 也是 0**（`R->status = s->failed==0?0:...`），
    所以「status≠0 才算截断」是错的；真实证据=单步 18 起点 × 4s deadline ÷ 4 线程 ≈ 18–23s 且 `elapsed` 撞满
    cap → 最后一波起点在 deadline 计时开始后才开跑、整步 overshoot。结论：**加起点必须同时做准入控制**。
- **② v6 机制（`submissions/gkagent-ex-seed-v6`，bench_repo cd35efa；v5 逐位复现路径保留）**：
  - **预算内自适应波次**：去掉「几波」概念，改流水线式发起点——每发一个先过**准入控制**：
    `剩余 ≥ 预期×admit_mult(1.25) + admit_pad(0.10)`；单次 `deadline = min(search_deadline_cap(4.0), 预期×dl_mult(1.5))`；
    **预期** = 该 transitions 预算下最近 6 次**完整**搜索的 `prep+elapsed`（中位/最新取大；撞 deadline 的样本 ×1.25
    上调 → 慢状态自动变保守）；预算尾巴用 **anytime 短搜**（deadline=剩余−0.15，绝不越界）；每步起点上限
    `max_starts=24`（v5=12）。RoutePool 只采纳更高终局分 ⇒ 仍单调安全。
  - **小样门（15 题 × 2 保密种子 = 30 槽，parallel 6；eval 51d7bda2d64c）**：**over 0（v5 同槽 5）**；
    每步 p50 3,964ms（v5 1,956）/ p95 6,123（5,964）/ **max 11,110（17,385）**；每步起点 **23.5（v5 10.8）**、
    完整搜索 19,656 / anytime 145；总 think 4,802s vs 3,330s（+44%）。
  - **小样门分数**：v5 均分 5,444,110 / v6 **5,281,200** → meanΔ −162,909，CI95 [−785k,+374k]
    （**统计不显著**）；逐槽 **17 胜 / 11 负 / 2 平**、**中位 Δ +165,536**、**oracle 比例 0.9185 → 0.9278**。
    负均值主要来自 3 个 **v5 幸运槽**（YGF972ZK/1 v5 14.56M vs oracle 7.96M = **+83%**、BZXB28YJ/0 +78%、
    AXME8QK2/0 +32%；v6 在这三槽仍 **≥ oracle**：8.55M / 5.14M / 6.97M）→ 判为「赢家诅咒 + 30 槽方差太大
    （逐槽 sd 1.66M）」，不据此判 v6 为负；1–2% 量级增益 30 槽测不出来（SE≈300k）。
  - **全量 240（单 eval 661dffa3b25f + 两次 resume，parallel 6，总墙钟 ≈86min）**：
    **240/240 = 1,461,263**（vs v5 1,447,036 → **+14,226 / +0.98%**；**新 PB**，同时超过 best-known
    1,452,088 与 v5 官方行 1,458,385）。逐槽 **105 胜 / 103 负 / 32 平**（meanΔ CI95 [−72,379,+108,085]，
    **仍不显著**）；**oracle 比例 0.9535 → 0.9698（+1.63pt）**；分层 **MID +58,861/槽（+6.36M）/
    FINAL −22,292/槽（−2.94M，在 132 槽 SE≈61k 内=噪声）**。官方单行 n=240：over 36 / errors 0 /
    p50 3,846ms / p95 7,002 / max 76,341 / ep_think 124s。每步起点 **23.3（p10=24，几乎每步顶到
    max_starts=24；v5 10.8）**，完整 124,264 / anytime 1,390；总 think **29,755s（v5 17,890s，+66%）**。
  - **over 8→36 的分解（诚实记录，「不增 over」这一条没做到）**：`worlds` 14 / `route` 11 / `search` 9 /
    `fallback` 2；其中 **4 步 >40s（最大 76.3s）** 出现在一次 DNS/断链事故期间（同一局 `worlds` 步
    12.6→39.3→76.3s；eval 因此 10 连错停机一次）→ 网络停摆伪影；其余 12–21s 的是深局 `route/search` 步
    （24 起点、`pool_status` 全 0、`pool_expect_ms` 只有 810–1,423ms）→ **说明 expect 模型只覆盖 C 搜索时长，
    没覆盖 `session.clone()`/状态拷贝/线程排队**；v7 修这个才能把深局步压回 ≤8s。
  - **⚠️ 单槽不可比的硬证据（v6 同算法同槽复跑：门 vs 全量同 30 槽）**：meanΔ −67,523、sd **1,767,371**、
    **max|Δ| = 6,143,529**（AS-YGF972ZK/0 门 6.90M → 全量 13.05M；3EW6E6HV/1 14.19M → 10.84M）。
    ⇒ 小样门 30 槽的 Δ 本身就有 ±65k 量级噪声，「v6 门 −162,909」不能当否证；**只看 240 槽聚合 +
    oracle 比例 + over 三项**。
  - **对外 vs_oracle 自算口径（232 个有 oracle 的配对槽）**：v4 geo 0.9020 / win(≥oracle) 34.9% / 中位 0.9387
    → v5 0.9232 / 45.7% / 0.9841 → **v6 geo 0.9435（+2.03pt）/ 43.1% / 0.9726** —— v6 把**大头拉高**
    （geo 明显涨）、中位与胜率略降 ⇒ 方差更大：大槽更能吃到、中位槽小回吐。
  - **结论**：v6 的调度修复按预期把「每步空转 2.4s/7s」换成了 23 个不被截断的起点（MID 明显受益 +58,861/槽），
    但 (a) 分数增益 +0.98% 仍在噪声内，(b) FINAL 没吃到（68% 的分数在 FINAL），(c) over 反而涨到 36。
    下一步优先级：**① 把 clone/prep 计入准入（修 12–21s 深局步）→ 同等墙钟更多有效搜索**；
    **② FINAL 专项**（132 槽 1.78M 均分）；**③ tail_turns=3**；**④ lock≥4 的 pre-lock 决策质量**。
- **③ 并行/线程配比（`data/_v6_threads.py`：真实锁定后深局快照，1–24 并发各搜 500k transitions）**：
  - native `policy_search` 每线程一份 core 副本 → 1/2/4/8/12/16/20/24 并发下单次耗时 0.45–0.72s（**24 并发只 +22–25%**），
    聚合吞吐近线性：**2.1M → 37M transitions/s**。16 个 CPU burner（模拟 scan procs=16）并发时单次 +7–31%（轻微饥饿）。
  - 结论：**parallel_games × threads_per_game ≈ 20–24**（本轮 6×4=24；v5 是 5×(4/2)）；scan procs=16 不必下调；
    真正的开销不在 native 吞吐，而在 server RTT 与 Python 侧调度。
- **④ prior 引导（结论：现有 native 接口表达不了 B11 网）**：native prior 是**静态**权重表
  （`engine.prior().weights` → `native_search.prior_table`：per-(phase, master card row) + drinks/end，按当前 session
  的牌组现算、但**与状态/动作无关**）；B11 policy/advantage 是**状态-动作相关**输出。要挂上去必须
  (a) 改引擎加 hook（**DLL 不重编红线**）或 (b) 每次搜索绑一个「当前 session 的动态 prior 对象」+ 把 native session
  桥回训练特征（工程量≥一个任务）→ **本轮不做，如实记录**。历史 prior（规则版）全负的结论不变。
- **⑤ tail_turns 2→3（可行性：通过，代价≈0）**：`data/_v6_tail_prod.py` 用**生产路径**（v6 algo、tail_turns=3）
  打决赛 dev seed：**turns_left=3 时 tail 14–21ms 就 complete**（AS-WDKWQYW5 21ms / AS-5KZSXANK 14ms，
  nodes ~800–1,300），随后 `pool.proven=True` 不再搜；整局 think 123.5s/101.2s（与 tail_turns=2 同量级）。
  ⇒ **+1 回合精确尾近乎免费，v7 直接采纳 tail_turns=3**（甚至可试 4；深局/大牌堆树更大的题还没覆盖，
  生产数据 tail 步 p99 0.7–0.9s）。注：第一版临时探针（直接 `TN.tail_exact`、没走生产 `_tail()` 的
  `_calibrate_tail` 时钟纪元校准）出现过 wall=0.01s + status=deadline 的伪影，结论以上面生产路径为准。
- **⑥ 独立可攻点（`data/_v6_diag6.py`）**：
  - **lock≥4 的 11 槽**：锁定前全部走 `ctx.worlds` 随机世界 PIMC（worlds 步 7–16），方差极大（QV6QCSN9/1 v4 0.52M →
    v5 1.20M；X9GNYH3W/1 v5 只有 0.18M；P8ZJTXNA 12k 候选）。⇒ **下一杠杆是晚锁题的 pre-lock 决策质量**
    （后验镜像投票 / 更多世界 / 更早锁定），不是锁定后的起点数。
  - **8 个无 oracle 的 produce-008 低分槽**：think 只有 38–75s、早锁、tail 很早 proven，**3 槽 v5 与 v4 逐位同分**
    （580,317 / 713,938 / 867,619）→ 已接近该题最优，**不值得再投**。上一行「独立可攻点」里这一半可以划掉。