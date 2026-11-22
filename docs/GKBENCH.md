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
  `ctx.loadout` 接入；但 `p_items.json` 快照（2026-09-16）缺 11 个新 id、效果覆盖
  72 个已知道具里 131 段 spec 只实现 31 段（见 RULES_REFERENCE §5.3）。
- 已知待补（F1）：`ExamInitialDeck` 加卡机制、`kllj-3-005` 开局 +1 手牌；
  `loadout.produce_item_ids` 的 11 个快照外新道具与主道具附魔 `main_item_enchant_ids`。

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
