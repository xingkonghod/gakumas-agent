# 回合内 expectimax + 跨回合 beam（实现与实测）

> 规格来源：`gakumas-ai-architecture-review.md` §2.3 / §2.4；机制口径见
> `data/knowledge/mechanics.md`。本文件只记**实测**，不写未验证的估计。

## 1. 实现范围

| 模块 | 内容 |
|---|---|
| `src/gkagent/sim/expectimax.py` | `ExpectState`、回合内精确 `expectimax`、`AnalyticLeafValue`、`search_beam`、抽牌机会节点 |
| `src/gkagent/policy/lesson.py` | `engine: "rules" \| "expectimax"`（默认 rules，`policy.json` 可切；异常一律退回 rules） |
| `src/gkagent/sim/lesson.py` | `CardSpec.once`（除外）、`PItemSpec`（复用 `sim/p_items.py`）、`total_turns/current_turn` |
| `src/gkagent/vision/lesson.py` | `LessonState.total_turns/current_turn` |
| `scripts/eval_expectimax.py` | L3 配对评测（2000 局）+ beam 宽度扫描 |
| `tests/test_expectimax.py` | L1 机制测试 |
| `tests/test_policy_engine.py` | engine 开关 / 异常回退测试 |

### 决策语义

- 动作 = 打一张手牌或 SKIP；**枚举本回合所有合法有序序列**，不是单张牌集合。
- 可行性 = `stamina + vitality >= cost` 且 `plays_used < play_limit + extra_plays`。
- 抽牌：剩余牌多重集精确超几何机会节点；小牌库枚举组合，大牌库逐张按
  `count/remain` 分支；牌库空时捨札洗回（中途抽空也处理）。
- 目标 = `a·P(score ≥ CLEAR) + b·P(score ≥ PERFECT)`，不是 E[分数]。
- 同名牌去重；状态按多重集/分数/buff/指針/回合/牌库做规范化记忆化。
- anytime：超时返回当前最优；beam 默认 deadline 500ms。
- 再动卡（`ExamPlayableValueAdd`）只加 `extra_plays`，不写死优先级；搜索会
  比较“多打一张”与“把体力留给大牌”的档位效用。
- 打平（E[u] 相同）时用通用 tie-break：多保留出牌次数 > 多保留体力/元气 > 低费，
  不认牌名；再动卡因此不会因为“名字/类别”被写死优先或写死排除。

## 2. 建模状态清单（精确 / 近似 / 未建模）

### 精确

- 体力/元气付牌费（元气先扣、不足再扣体力）、体力回复封顶；
- 卡面分 + 集中 + 好调 ×1.5 + 指針倍率；好印象/元气依赖分；好调/好印象/集中/
  干劲层数；抽牌；再动；审查基准加成；好印象强化；好调加算；全力值/全力强化；
  再演；成长计数器（接口；真实卡表 GrowEffect 数据为空时恒 0）；
- 回合末：好印象按当前层数加分；**下一回合开始才 -1**（最终回合不再扣）；好调
  回合 -1、持续 buff 倒计时、弃手牌；
- 山札/捨札/除外多重集；抽空洗回；`CardSpec.once` 用掉后进除外区（牌库压缩）；
- 三框饮料：`drinks` / `drink_uses` / `drinks_used_this_turn` / `drinks_per_turn`
  进 `ExpectState`，`use_drink_state()` 与 `LessonSim.use_drink` 同语义；
  **喝饮料不占本回合出牌次数**（`plays_used` 不变）。
- 好印象（impression）跨回合保留；やる気（motivation）只放大每次元气获得量，
  与元气（vitality）分开存，二者都跨回合保留。
- 指針体力代价：温存 1段 ×0.5 / 2段 ×0.25，強気 ×2、2段穿透 1 点元气；温存
  解除给热意（近似好调回合）。`LessonSim` 与 `ExpectState.effective_cost` 同式。
- 考试名次按局内得分与 NPC 分数档比；期中 9 回合、期末 Sense/Anomaly 12、
  Logic 11 回合；训练用当前体力、无固定入场费；休息回复最大体力 70%；PERFECT
  返还剩余回合×2 体力；支援卡训练加成 `×(1+sum bonus%)`。
- P 道具：7 个触发时机（turn_start/card_played/card_play/status_gain/turn_end/
  card_play_interval/exam_start）在 `LessonSim` 与 `ExpectState` 都触发；未实现类型 no-op。
  （**T5③ 2026-11-22**：exam_start 由 `LessonSim` 构造时先于 turn_start 结算一次；
  `ExamPlayableValueAdd` 映射到 `extra_plays`；真实对局列表来自
  `gkagent.data.p_items_db` 解析 loadout `produce_item_ids`，见 §2.3.1 与 RULES_REFERENCE §5.3。）
- 饮料作为 expectimax 动作：可喝饮料并继续出牌，不占出牌次数，受库存/每回合上限。

### 近似

- `AnalyticLeafValue`：解析未训练 V_leaf。`μ = n·集中 + 好印象年金 + 均值牌面×n`
  （n 用体力/费用模型封顶），`σ=60`；CLEAR/PERFECT 用 `math.erf` 正态 CDF。
- `ExamLessonBuffDependParameterBuff`（好调数值依赖审查基准加成，缺 parameter buff
  状态）：按**至少 1 回合好调**记——不虚构跨回合收益，但避免把真 buff 牌当空白牌。
- `LessonSim` 原有近似（延迟效果时机、检索/生成/移动→抽 1、附魔展开等）不改变；
  见 `sim/lesson.py` 模块 docstring。

### 未建模（接口/状态就位，等数据）

- 考试对手/追击/干扰、饮料槽获得流程、强化后数值等：沿用原模拟器缺口。
- 真机 OCR 读不到 buff 层数/牌库/总回合数：`LessonPolicy` 的 expectimax 模式用
  已知手牌/体力/剩余回合/分数/CLEAR 构造状态；牌库空、buff 默认 0，异常退回 rules。

## 2.3 2026-11-16 第三批：P 道具真接入 + 饮料作为搜索动作

### P 道具（`LessonConfig.p_items` → `LessonSim.step`）

- 触发时机：`turn_start`（抽完手牌后）、`card_play`/`card_played`/`card_play_interval`
  （每次出牌后一次，含刚出的第 N 张）、`status_gain`（获得层数时逐项）、`turn_end`
  （好印象/好调结算后、弃手牌前）；
- 结算：`apply_passive` 的 `score` / `stamina` / `stacks` 映射到分、体力、
  vitality/impression/focus/aggressive(motivation)/full_power_point/parameter_buff；
  `max_uses` 按 `p_item_uses` 记录（修了 p_items 对空 `item_id` 的计数键）；
- `ExpectState` 带 `p_items/p_item_uses/cards_played_total`，`apply_card` 触发
  card/status 事件，`end_turn_state` 触发 turn_end；beam 抽完下一手后调用
  `start_turn_state` 触发 turn_start；
- 未实现 `effect_type` / 认不出的条件 → no-op，不抛异常；
- 时序近似：`p_items.py` 的 `card_play` 与 `card_played` 共用同一 event kind，
  为不双触发，统一在**出牌结算后**触发一次（card_play 类效果因此不会作用于
  本牌自身，属保守近似）。
- 测试：`tests/test_p_items_integration.py` 9 条（6 个时机 + max_uses + 未实现 no-op +
  ExpectState 同步）。

### 2.3.1 T5③ 2026-11-22：P 道具数据接入（loadout → `PItemSpec`）

- 数据层：`src/gkagent/data/p_items_db.py`——对局 loadout 的 `produce_item_ids` 精确匹配
  `data/knowledge/p_items.json`（B7 起 **1115 件**：本地中文 master 1068 + gakumasu-diff yaml
  新增 47，后者的中文描述缺失处保留日文并显式标记）；未知/重复 id 显式上报，
  缺文件抛 `PItemDataUnavailable`（**不静默当没有 P 道具**）。
- 新触发/效果：`exam_start`（288 段素材；训练/考试开始时，`LessonSim` 构造时结算一次，
  顺序先于 turn_start、额外出牌次数保第 1 回合）；`ExamPlayableValueAdd → extra_plays`
  （51 段，N 在 `values.count` 列——旧 `record_to_specs` 只取 `value1` 会退化成 0 值 no-op）。
  `PItemDelta` 增 `extra_plays`；`ExpectState.fire_p_items` 同步。
- 消费方：`scripts/local_bench.py`（gkbench 题模板 loadout → `LessonConfig.p_items`；
  `--p-items auto/off` A/B；报告 `p_items` 覆盖率）+ `submissions/expectimax/algo.py`
  （`ctx.loadout`，base.py 明说「开局配置（不含种子）」）。
- 覆盖（B7 后，如实）：catalog **1115 件 → 1849 段 spec 已实现 445 段**；gkbench
  **83 个已知道具 → 153 段 spec 已实现 34 段**（新增 47 条里条件未解析的 22 件/46 段记
  `condition_known=False` 保守不触发）；gkbench 未知 id **0**（B6 时 11 个）。
  离线 A/B（B7 重跑，hif 30 题×2 seed 配对）：greedy 3840.7→**3969.7（+128.9，+3.36%，
  CI[+9.5,+248.4]）**（与 B6 逐位相同——新道具目前 0 分贡献）、expectimax 3732.0→3953.6
  （+221.5，CI[−71.4,+514.4]，受墙钟预算抖动）。
- 测试：`tests/test_p_items_db.py` 11 条 + `test_gkbench_submission_p_items.py` 6 条 +
  `test_p_items*.py` 增 11 条 + `test_local_bench.py` 增 4 条；细节见 RULES_REFERENCE §5.3 /
  HANDOVER 二·补二十七（B6）/ 二·补二十九（B7）。

### 饮料作为搜索动作

- `ExpectimaxConfig.allow_drinks=True`（默认）；`_Search.search`/`root` 同时枚举
  「打牌」与「喝饮料」，返回 `ExpectimaxResult.drink`；新增 `expectimax_action()`
  返回 `(card, drink)`；只出牌的旧 API `expectimax()` 保持返回 card；
- 喝饮料不占 `plays_used`，受库存 `drink_uses` 和 `drinks_per_turn` 限制；
- **剪枝理由**：饮料不占次数，但每个节点 × 库存瓶数会指数膨胀；只在
  「本回合后续能得分」时展开（score 饮料总展开；focus/condition 要求还有出牌位
  且有正分牌；stamina 要求有正分牌当前付不起），且每个状态只展开**优先级最高
  的 1 瓶**（stamina 解锁 > focus/condition > score）。因此分支通常 0–1 个，
  而不是 3 瓶全开；
- 测试：`tests/test_drink_search.py` 6 条（搜索选择/体力够时不喝/每回合1瓶/库存空/
  不占次数后继续出牌/耗时 <10ms）。

### 两项的 300 局 ablation（固定 seed/牌组/策略）

| 项 | before | after | 差异 |
|---|---:|---:|---:|
| P 道具（全部 1764 spec，upper bound；B6 口径）P50 | 5096 | 11270 | **+6174** |
| P 道具（同上）均值 | 5055.0 | 11267.1 | +6212.1 |
| 饮料可搜索（带 3 瓶×3 次）P50 | 151 | 239 | **+88** |
| 饮料可搜索 均值 | 138.2 | 254.8 | +116.6 |
| 饮料可搜索 PERFECT 局数 | 4/300 | 290/300 | +286 |
| 饮料搜索单次决策耗时 | — | 7.67ms 均值 / 46.5ms p95 | 原 1.6ms → <10ms 目标内 |

> P 道具的 +6174 是**全部** P 道具（含大量高数值/重复触发）的 upper bound，
> 不是真实 3 槽配装；接入正确性由 9 条时机测试保证，数值请按实际持有道具重跑
> `scripts/ablate_p_items_drinks.py`。脚本：`scripts/ablate_p_items_drinks.py`。

## 2.1 2026-11-16 机制核对（Gemini + wiki）

| # | 结论 | 实现 | 测试 |
|---|---|---|---|
| ① | 喝饮料**不占**出牌次数 | `use_drink` / `use_drink_state` 都不动 `plays_used`；先喝 2 瓶仍能打 3 张 | `test_drinking_does_not_consume_play_slots` |
| ② | CLEAR/PERFECT 是**连续进度**，不是三档 | `LessonSim.reward_gain = min(score, clear) + min(max(score-clear,0), perfect)`；`ProduceSim._official_training_gain(score)` 同式 | `test_lesson_reward_gain_is_continuous` / `test_produce_training_gain_uses_continuous_progress` |
| ③ | 好印象回合末加分、**下一回合开始** -1；最终回合不扣 | `_end_turn` 只加分；`_draw_hand`（下一回合开始）才 -1 | `test_impression_decrements_at_next_turn_start_not_final_turn` |
| ④ | やる気 ≠ 元气：干劲只放大元气获得量，二者都跨回合保留 | `Buffs.focus`/`LessonSim.motivation`/`vitality` 分开存；`vitality += card.vitality + motivation` | `test_motivation_and_vitality_are_separate_and_persist` |

> ② 的 `gain = min(score, clear)` 口径：wiki（note.com「学マスのレッスンにおける
> パラメータ上昇量の計算式」）明确 CLEAR 是"还差多少分 CLEAR"、PERFECT 是达标后
> "还差多少分 PERFECT"，参数按**已达成**的数值计；因此未到 CLEAR 时给 `score`
> 本身（不是整档 0）。如果后续查到"失败课程 0 属性"的更强证据，只需把
> `reward_gain` 的 `min(score, clear)` 改成 `0 if score < clear else clear`，
> 测试同步改一处即可。

## 2.2 2026-11-16 第二批 wiki 核实（考试/体力/回合/指針/支援）

| # | 改动 | 实现 | 测试 |
|---|---|---|---|
| 1 | **考试名次按局内考试得分**，不再按属性加权 | `ProduceSim.exam()` 先跑考试模拟器拿 `exam_score`，`rank = 1 + count(npc_score > exam_score)`；NPC 默认 603/387/206/205 | `test_exam_rank_uses_exam_score`、`test_exam_rank_uses_exam_score_not_attributes` |
| 2 | 训练**没有固定入场耗体**，体力只在局内按牌扣 | `training_cost=0`；训练用**当前体力**开局，局内消耗写回；进训练门 = 体力 ≥ 最低牌费 | `test_training_has_no_entry_stamina_cost`、`test_stamina_never_goes_negative_on_failed_lesson` |
| 3 | 休息回复**最大体力 70%**（向下取整），满体力不可选 | `rest_gain_ratio=0.7`；`rest()` 满体力返回 False | `test_rest_recovers_70_percent_and_is_unavailable_at_full` |
| 4 | 体力上限可配（不写死 35） | `ProduceConfig.stamina_max` / `start_stamina` 字段；训练/考试都读配置 | 覆盖在 `test_rest...` / 现有配置测试 |
| 5 | PERFECT 返还**剩余回合 ×2 体力** | `training()` 内 `sim.turns_left × 2`，封顶 `stamina_max` | `test_training_has_no_entry_stamina_cost`（0 费牌场景） |
| 6 | 考试回合数：期中 9；期末 Sense/Anomaly 12、Logic 11 | `exam_turns_mid/final/final_logic`，`exam()` 按 plan 选 | `test_exam_turn_counts_mid_and_final_by_plan` |
| 7 | 指針体力代价：温存 1段 ×0.5 / 2段 ×0.25；強気 ×2，2段穿透 1 点元气；温存解除给热意（近似好调回合） | `stance.stamina_cost_multiplier/stamina_pierce`；`LessonSim._pay_card_cost` + `ExpectState.effective_cost` 同步 | `test_stance_cost_modifiers_and_strong_pierce`、`test_save_release_gives_heat_turns` |
| 8 | 支援卡训练加成：`(CLEAR+PERFECT) × (1+sum レッスンボーナス%)`，向下取整 | `ProduceConfig.support_lesson_bonus`（默认 0.2）；`_official_training_gain` 乘算 | `test_produce_training_gain_uses_continuous_progress` |

### 300 局 produce ablation（固定 seed/牌组/策略，评价点 P50）

| 配置 | P50 | vs old_all |
|---|---:|---:|
| old_all（改前） | 4590 | — |
| new_all（全部修正） | 5096 | **+506** |
| 只改考试名次→分数 | 5790 | +1200 |
| 只改训练无入场费/当前体力 | 3663 | **-927** |
| 只改休息 70% | 4590 | +0（stamina_max=35 时 floor(35×0.7)=24，与旧常数相同） |
| 只改 PERFECT 返体力 | 4590 | +0（300 局里触发少/被体力门掩盖） |
| 只改考试回合数 9/12/11 | 4590 | +0（该牌组在更少回合内仍能超过 NPC 分数档） |
| 只改指針体力代价 | 4537 | -53 |
| 只改支援卡训练加成 | 5040 | +450 |

> 训练「当前体力」单项为负是**预期**：旧模拟每次训练都送满 35 体力，属于模型
> 高估；修正后训练受真实体力约束，P50 下降，但考试名次/支援加成等修正把整体
> 拉回并超过旧口径（new_all +506）。这些是机制修正，不是策略调参。
> 复现脚本：`scripts/ablate_mechanics.py`（300 局，运行约 1-2 分钟）。

## 3. 再动卡 L1 实测（搜索分支，不是写死优先级）

手牌 `[再动(cost1, 0分, extra_play=1), 大分(cost5, 60分)]`：

| 体力 | 引擎选择 | 动作价值（再动 / 大分） | 原因 |
|---:|---|---|---|
| 6 | 再动 | 1.0 / 1.0 | 再动(1)+大牌(5)=6，打完 60 分；打平时 tie-break 保留更多动作次数 |
| 5 | 大分 | 0.0 / 1.0 | 再动后剩 4 < 5，大牌打不出 → 本回合 0 分 |

另测：盾牌体力 2 + 大牌 6 费 → 先盾再大（解锁）；体力 2 + 大牌 7 费 → 打盾也
不够，SKIP；体力 0/1 时 buff/再动/盾三类 0 分牌都不硬打。

## 4. L1 测试清单

`tests/test_expectimax.py`（27 条）+ `tests/test_mechanism_corrections.py`（11 条）+
`tests/test_p_items_integration.py`（9 条）+ `tests/test_drink_search.py`（6 条）：

- 背包（10 vs 3+6=9）、元气抵费、集中先手（18 > 16）、阈值风险（A=+5 vs B=30%+100/70%-20）、
  空放 buff、可复现、可行性、再动 6/5 体力、再动不吃体力截断、抽牌+再动；
- 动作敏感、机会节点 32 种牌序 ≥28 后继、超几何 P(A)=0.4/P(B)=0.6、状态转换与
  `LessonSim` 对齐；
- buff vs 再动、盾 vs 大牌、体力不足 SKIP；
- 除外/牌库、buff 剩余回合/总回合/饮料、P 道具接口、beam 投资线/deadline/可复现；
- 机制核对：饮料不占出牌次数、CLEAR/PERFECT 连续收益、好印象下回合开始扣层、
  やる気/元气分离、考试分数名次、训练体力、休息 70%、考试回合、指針代价、支援加成
  （见 §2.1 / §2.2）；
- P 道具 6 个时机 / max_uses / 未实现 no-op / ExpectState 同步；饮料搜索选择、
  不占次数、每回合 1 瓶、库存空、喝后继续出牌、耗时上限（见 §2.3）。

## 5. L3 配对评测

脚本：`scripts/eval_expectimax.py`（同牌组同 seed 配对）。主场景大牌组
31 张 / 9 回合 / 体力 60 / CLEAR 300 / PERFECT 450；小牌组 14 张 / 5 回合 /
体力 34 / CLEAR 120 / PERFECT 170（阈值按当前 wiki 修正后的分数分布取，
使 PERFECT 率有区分度）。指标按用户 2026-11-16 新口径：评价点
P10/P50/P90/均值 + PERFECT 率；**不报 C+率/B率**。

<!-- RESULTS_START -->
最近一次完整运行（见 `data/bench/expectimax_eval.json`；输入数据哈希也记在 JSON 的
`inputs` 里）：

### 主场景（large，2000 局）

| 策略 | 均值 | P10 | P50 | P90 | PERFECT |
|---|---:|---:|---:|---:|---:|
| rules（固定优先级） | 333.4 | 235.0 | 335.0 | 432.0 | 5.9% |
| expectimax（回合内） | 418.0 | 334.9 | 422.0 | 490.0 | 39.6% |
| beam（width=4，跨回合） | 416.5 | 332.9 | 420.0 | 487.0 | 41.2% |

- expectimax vs rules：均值 +84.5（+25.4%，95%CI [+81.5, +87.5]）；
  P50 +87.0（+26.0%，CI [+24.5%, +27.8%]）；PERFECT +33.7pp（CI [+31.6, +35.7]pp）。
- beam vs rules：均值 +83.1（+24.9%，CI [+80.1, +86.1]）；
  P50 +85.0（+25.4%，CI [+23.9%, +27.2%]）；PERFECT +35.2pp（CI [+33.1, +37.4]pp）。
- beam vs expectimax：均值 **-1.4（-0.3%，CI [-3.4, +0.6]）**；
  P50 **-2.0（-0.5%，CI [-1.7%, +0.5%]）**；PERFECT +1.6pp（CI [-0.4, +3.6]pp）。
- 门槛（beam vs rules）：P50 +25.4%、CI 下界 +23.9% → PASS；PERFECT +35.2pp → PASS。
- **如实结论**：大牌组上 beam 没有赢过回合内 expectimax（均值 -1.4），只在小牌组
  上赢了（见下）；多拍预算主要花在剪枝，V_leaf 的准确度是瓶颈。

### 小场景（small，500 局）

| 策略 | 均值 | P10 | P50 | P90 | PERFECT |
|---|---:|---:|---:|---:|---:|
| rules | 133.3 | 97.0 | 132.0 | 171.1 | 10.8% |
| expectimax | 144.5 | 122.0 | 139.0 | 178.0 | 23.2% |
| beam（width=4） | 149.0 | 122.0 | 143.0 | 180.0 | 33.0% |

- beam vs rules：均值 +15.7（+11.8%，CI [+13.2, +18.2]）；
  P50 +11.0（+8.3%，CI [+5.3%, +10.2%]）；PERFECT +22.2pp（CI [+18.2, +26.2]pp）。
- beam vs expectimax：均值 +4.5（+3.1%，CI [+2.4, +6.6]）；
  P50 +4.0（+2.9%，CI [+0.0%, +4.3%]）；PERFECT +9.8pp（CI [+5.6, +14.0]pp）。

### beam 宽度扫描（主场景，200 局/宽度，deadline 500ms）

| width | 均值 | P50 | P90 | PERFECT | 决策均值 | 决策 p95 | complete |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 414.0 | 408.0 | 486.2 | 36.5% | 103.5ms | 308.5ms | 100.0% |
| 8 | 412.7 | 414.5 | 487.1 | 39.5% | 207.0ms | 501.4ms | 25.0% |
| 16 | 396.5 | 391.0 | 486.1 | 26.5% | 269.3ms | 503.6ms | 0.0% |
| 32 | 393.1 | 387.5 | 481.5 | 28.0% | 301.6ms | 505.1ms | 0.0% |
| 64 | 388.9 | 382.0 | 480.5 | 25.5% | 321.6ms | 511.5ms | 0.0% |

饱和点：P50/均值在 width=4–8 附近饱和；width=8 的 P50 略高（+6.5）但均值/PERFECT
受 deadline 截断影响，且 500ms 内只有 25% 回合跑满；width≥16 反而退化。线上推荐
width=4（均值 103.5ms，p95 308.5ms，100% 回合完成）。

### 决策耗时

- 回合内 expectimax：均值 1.6ms，p95 2.1ms（每张牌决策）。
- 跨回合 beam（width=4）：均值 109.3ms、p95 328.7ms（每回合一次）；deadline 500ms。
- 异常回退 rules：expectimax 0 次、beam 0 次（2000 局）。
<!-- RESULTS_END -->

## 6. 已知限制

- beam 的跨回合价值完全取决于解析 V_leaf；V 偏乐观/保守会把 beam 带偏。实测大牌组
  上 beam 均值落后回合内 expectimax -1.4（P50 -2.0），小牌组上 +4.5；多拍预算主要
  花在剪枝，V 的准确度才是瓶颈。
- 真机牌库不可见，在线 expectimax 只搜当前手牌；跨回合 beam 默认用于离线/已知牌库。
- 解析 V_leaf 的 σ 是常数（60），没有按牌组/课程长度标定；这是后续换学习 V 的接口。
- 饮料已进状态但未作为搜索动作（动作定义仍是 play/SKIP）；真机饮料仍走现有
  `use_drink` 流程。


## 拟合 V_leaf 的实验结果（2026-11-19，负面结果）

按评审第 2 步做的拟合值函数，**实测比解析式差很多**，如实记录。

### 做法
- 训练数据：`LessonSim` 跑 8000 局 × 3 轮（56k 样本），回合边界采 `(特征, 剩余得分)`
- 特征：36 维（状态 12 / buff 9 / 手牌聚合 8 / 交互 6）
- 拟合：ridge 最小二乘（numpy），σ 用残差 RMS
- 结果：**r² = 0.805，σ = 22.2**（拟合本身没问题）

### 配对评测（120 局，同牌组同种子，6 回合 / CLEAR 200）

| 策略 | 均值 | P10 | P50 | P90 | vs greedy |
|---|---:|---:|---:|---:|---:|
| greedy | 125.0 | 87 | 125 | 154 | — |
| **analytic（手写公式）** | **143.3** | 103 | 137 | 205 | **+14.6%** |
| learned（拟合） | 76.9 | 51 | 69 | 108 | **−38.5%** |

### 为什么差（诊断）

看拟合出的权重：

```
turns_left    +14.24      ← 唯一强正权重
turn_ratio    −67.80      ← 与 turns_left 共线
hand_max_score  0.17      ← 手牌质量几乎没权重
focus             ~0      ← 集中没进模型
```

**模型学成了"剩余回合 × 每回合均分"**——因为训练数据是用**固定贪心策略**跑的，
标签里没有"不同选择的差异"。于是 expectimax 用它对所有动作打分几乎一样，
搜索退化成随机。

### 结论与下一步

**解析式赢了，但不是因为解析式更好，而是因为"用贪心策略的轨迹训练出的 V" 只反映贪心策略的价值。**

要让它真的有用，必须做**真正的专家迭代**：

1. 用 **expectimax 自己的策略**采样（不是贪心）
2. 每轮训练后用它重新跑搜索采样，形成自我改进循环
3. 或者直接模仿"知道牌序的搜索"轨迹（UINet 的做法）

在完成这一步之前，**默认保持 `leaf="analytic"`**。


## 真专家迭代也失败（2026-11-19，第二次负面结果）

按上面的诊断做了真·专家迭代：第 1 轮用解析式采样，第 2/3 轮用上一轮的 V 采样
（`scripts/fit_v_leaf_iter.py`）。

| 轮 | 样本 | σ | r² |
|---|---:|---:|---:|
| 1 | 4,207 | 24.2 | 0.811 |
| 2 | 4,140 | 24.6 | 0.785 |
| 3 | 4,192 | 23.7 | 0.804 |

L3 配对（150 局）：

| 策略 | 均值 | P10 | P50 | P90 | vs greedy |
|---|---:|---:|---:|---:|---:|
| greedy | 123.5 | 85 | 123 | 154 | — |
| **analytic** | **142.2** | 103 | 135 | 207 | **+15.1%** |
| learned | 63.1 | 24 | 55 | 105 | **−48.9%** |

**迭代没救回来，反而更差。**

### 根因（更清楚了）

1. **expectimax 在采样循环里大量返回 None**——用 `LessonSim` 构造的 `ExpectState`
   与搜索内部的合法性判定不一致（指針费用修正），每次都要退回贪心；
   所以"专家轨迹"其实还是贪心轨迹。
2. **learned V 给搜索的梯度是错的**：线性模型学到的主项是 `turns_left`，
   对手牌质量权重只有 0.17，搜索无法区分好坏动作，最终选出的牌比贪心更差。

### 结论

**在这套模拟器和特征下，线性拟合 V 不可用。** 要用学习型评估，需要满足：
1. 搜索与模拟器的状态/合法性完全一致（否则采样和决策两个世界）
2. 训练信号来自"知道自己牌序的全信息搜索"（UINet 的做法），而不是在线策略
3. 或者不用线性模型，用结构化特征网络（他们 1300 维）

当前生产默认保持 `leaf="analytic"`。


## 修完规则后再试：仍然失败（2026-11-19，第三次）

按参考引擎（gakumas-tools，BSD-3）修正了 `LessonSim` 的三处结算：
绝好调下好调倍率随回合增长、メタモルフォーゼ（披露 +25% / 支度 ×0.75）、不调 ×0.67。

重训 V_leaf（3 轮专家迭代）后：

| 策略 | 均值 | P10 | P50 | P90 | vs greedy |
|---|---:|---:|---:|---:|---:|
| greedy | 123.5 | 85 | 123 | 154 | — |
| **analytic** | **142.2** | 103 | 135 | 207 | **+15.1%** |
| learned | 59.5 | 24 | 55 | 102 | **−51.8%** |

**规则修对了，learned 还是不行。** 结论稳定：

1. 线性模型在这套特征下权重塌缩到 `turns_left`，学不出动作差异
2. `ExpectState` 与 `LessonSim` 的合法性判定不同源，搜索选出的牌经常在模拟器里打不出
3. 真正的出路是 UINet 那条：**结构化特征（1300 维）+ 模仿全信息搜索**

`leaf="analytic"` 保持生产默认。规则修正是独立收益（课程分数更真实），已单独测试覆盖。

## 完全信息搜索：known_draw 接入（2026-11-21，第一步）

洗牌/支援强化/弃牌堆重洗破解后（见 `MASTER_DATA.md` 附录），整场考试牌序可以从 seed 推出来。
本步把「知道牌序」接进搜索，并如实量了信息本身值多少分。

### 数据链路

| 模块 | 作用 |
|---|---|
| `src/gkagent/sim/exam_oracle.py` | `initial_shuffled_deck(seed, deck, config_turns)` = 开局真实牌堆顺序；`ExamDrawOracle` 边打边推：每回合 `draw_next_turn(param)` 返回真实手牌并结算支援强化掷点，牌堆空时用调用方给的真实 grave 顺序重洗 |
| `src/gkagent/sim/expectimax.py` → `ExpectState.known_draw` | 已知的后续抽牌顺序（下标 0 = 下一张）。非空时抽牌机会节点退化成**确定分支**（`_draw_distribution` / `sample_draws`）；与 `deck` 长度不一致（牌被效果移动过）时自动退回多重集期望 |
| `state_from_sim(sim, known_deck_order=True)` | 离线评测入口：把 `LessonSim` 的真实剩余牌序写成 `known_draw`（`LessonSim` 从列表尾部 pop，所以顺序 = `reversed(deck)`） |

### 测试

- `tests/test_expectimax_known_draw.py`（8 条）：确定分支、按已知顺序入手、知道「下一张是大牌」时效用 = 确定结果、
  长度不一致退回期望、已知段抽完退回洗牌期望、`sample_draws` 按顺序、`state_from_sim` 顺序；
- `tests/test_exam_oracle.py`（6 条）：开局顺序、`peek` 不消耗、逐回合手牌与 `replay_initial_deck` 一致、
  isInitial 首回合、支援强化推进 RNG 与 `support_upgrade` 一致、重洗用给定 grave 顺序、缺 grave 报错。

### 配对评测（`scripts/eval_known_draw.py`，同牌组同 seed，unknown vs known）

| 场景 | 策略 | unknown 均值 | known 均值 | known − unknown |
|---|---|---:|---:|---:|
| 真实牌组 small（14 张/5 回合，无抽牌卡） | 回合内 expectimax | 138.6 | 138.6 | **+0.0** |
| 真实牌组 large（31 张/9 回合，1 张抽牌卡） | 回合内 expectimax | 356.5 | 356.6 | +0.1 |
| 真实牌组 small | 跨回合 beam（width 4） | 87.9 | 90.9 | **+3.0**（P50 +4.0，CLEAR 22.5%→30.0%） |
| 抽牌多构造牌组（7 张抽 1，14 张/5 回合） | 回合内 expectimax | 402.0 | 404.5 | +2.5 |
| 抽牌多构造牌组 | 跨回合 beam（width 4） | 265.8 | 310.4 | **+44.6**（P50 +55，均值 +16.8%） |

命令：`python scripts/eval_known_draw.py --games 40 --scenario small --policy beam --width 4 --budget-ms 100`

**如实解读**：

- 回合内 expectimax 用不到「未来回合」的信息，只有本回合抽牌卡的抽牌结果能用上——真实牌组里抽牌卡极少，
  所以增益 ≈0；抽牌多的牌组 +2.5。
- 跨回合 beam 用已知牌序做规划（为了后面几张真实好牌保留体力/出牌位），收益明显（构造牌组 +16.8%）；
  真实 small 牌组只有 +3.0，且 beam 本身还不如回合内 expectimax（见上文的 V_leaf 限制）。
- 结论：**信息本身是真实的（构造牌组验证），但要变成分数需要跨回合规划 + 更好的叶子估值**，这是下一步。

### 还没接的（下一步）

1. ~~**生产接线**：`auto_produce` 拿采集到的 seed/牌组/支援编成/配置回合建 `ExamDrawOracle`，每回合
   `draw_next_turn(param)` 与实机抽牌核对后把 `known_draw` 写进 `ExpectState`~~ → **已接，见下一节**；
2. ~~**重洗后段全知**：`ExpectState.discard` 现在是多重集，丢掉进弃牌堆顺序 → 第一次重洗后只能退回期望。
   要全知需要把 `discard_order` 带进状态（搜索/模拟器同步改），再配合 oracle 的 `reshuffle(grave)`~~
   → **已接，见下一节**；
3. ~~**生产策略**：把 beam/全信息规划接成 `lesson.engine` 的一个选项~~ → **已接 `engine="beam"`，见下一节**；
4. 真机 `LessonState` 读不到牌库/回合属性之外的隐藏状态——seed 数据来自 MITM 采集，需要把采集进程和
   bot 决策进程的数据打通（traffic.jsonl → policy 进程）。**仍未接**：现在用离线生成的
   `out/exam_setup.json` 喂 bot（见下节），实时打通是下一步。

## 完全信息搜索：第二段（生产接线 + 重洗后段全知 + beam 选项，2026-11-21 晚）

### ② 重洗后段全知：`ExpectState.discard_order` + 确定性重洗钩子

| 模块 | 作用 |
|---|---|
| `ExpectState.discard_order` | 已知**弃牌堆顺序**（进弃牌堆先后，旧 → 新）。`None` = 未知（默认，行为不变）；`()` = 已知为空。`apply_card` / `end_turn_state` 全程维护；`canonical()` 按原样入键（顺序影响重洗结果） |
| 搜索入口 `reshuffle=` | `expectimax_with_stats` / `expectimax` / `best_turn_sequence` / `search_beam` 都接受 `ReshuffleFn`（`Callable[[grave], list[CardSpec]]`，返回重洗后的**抽牌顺序**）。牌堆抽空时：`_draw_distribution` / `sample_draws` 用 `reshuffle(discard_order)` 走**确定分支**；多重集对不上（搜索模拟的弃牌堆和真实线不同）自动退回期望模型 |
| `ExamDrawOracle.reshuffle(grave)` | 纯预览：用考试 RNG **当前状态的副本**做 Fisher-Yates，不推进全局 RNG（搜索每个分支都能复现） |
| `reshuffle_from_sim(sim)` | `LessonSim` 适配：它的抽牌是 `deck.pop()`（尾部），所以重洗后的抽牌顺序 = `reversed(shuffled_discard)` |

测试：`tests/test_expectimax_discard_order.py`（17 条，含顺序维护、确定分支、多重集不符/钩子返回坏值退回期望、
`oracle.reshuffle` 纯函数、`reshuffle_from_sim` 与 `LessonSim` 真实重洗逐张一致）。
`scripts/eval_known_draw.py --full-info` 增加 full 行（known_draw + discard_order + 重洗钩子）：
构造抽牌牌组 beam 评测里 **计划执行回退 4 → 0**（决策与真实模拟器一致），分数上限场景无额外增益。

### ① 生产接线：采集数据 → `ExamSetup` → `ExamDrawPlan` → `LessonPolicy`

```
scripts/build_exam_setup.py      traffic.jsonl + deck_snapshots.json + 主数据 catalog
                                 → out/exam_setup.json（每场：seed / deck / supports / config_turns /
                                   initial_keys / card_variants / lost_keys / 逐回合 truth）
                                 --check 用 ExamDrawOracle 逐回合重放：4/4 场、86/86 张（+ 重洗段 24/24）
src/gkagent/sim/exam_plan.py     ExamSetup（类型化视图）+ ExamDrawPlan（在线牌序计划）
scripts/verify_exam_wiring.py    端到端核对（生产同一套 ExamDrawPlan）
```

`ExamDrawPlan` 的语义：

1. 每回合 `begin_turn(手牌, 属性)`：`ExamDrawOracle` 预测本回合真实手牌（含支援强化掷点），
   与实机读屏手牌**逐张核对**（id 多重集一致即可；升级次数允许实机更高）；
2. 核对通过 → `expect_state_kwargs()` 给 `deck` / `known_draw` / `discard` / `discard_order`，
   `reshuffle_hook()` 给纯重洗钩子；
3. 核对失败（卡表查不到 / 手牌不符 / 牌堆空缺 grave）→ **就地停用**（`status="mismatch"`，记原因），
   搜索退回「只知多重集」。**宁可不用信息，也不能用错信息**；
4. `note_play` / `end_turn(leftover)` 维护真实弃牌堆顺序（[`scripts/auto_produce.py`] 里由策略的
   `note_play` 与回合切换驱动）。

`LessonPolicy` 侧：`LessonPolicy(draw_plan=plan)` / `attach_draw_plan(plan)`。`_sync_exam_plan` 在每次
`decide` 前把当前手牌喂给计划（新回合做核对、回合内抽牌跟踪手牌张数差），`_search_state` 把
计划给的全知字段并进 `ExpectState`。`auto_produce` 新增 `--exam-setup`（默认 `out/exam_setup.json`，
文件不存在 = 不启用，行为与旧版完全一致）。

**端到端结果**（`scripts/verify_exam_wiring.py`，4 场采集全量核对）：

| 项 | 结果 |
|---|---|
| 逐回合手牌核对 | **36/36 回合** 逐张命中（4 场） |
| 弃牌堆重洗样本（T7 / T6 / T10） | **3/3** 组经生产链路核对通过（等价 verify_shuffle 的三组重洗样本） |
| `known_draw` 覆盖下一手 | **29/29**（下一回合没有回合内抽牌时，已知牌序前几张 = 实机下一手） |
| 真 `LessonPolicy(engine="beam")` 链路 | 计划核对 28 回合、beam 出牌 28 次；离线回放里策略打出的牌与实机不同，重洗前 grave 对不上时计划自动停用（安全回退，符合设计） |

数据限制：11-20 期末 T8 打出**考试内生成卡**（`p_card-00-men-3_003`），grave 无法从日志唯一重建 →
该场核对到 T8；11-21 期末 T12 同样（但 12 回合已核完）。回合内重洗（T9）仍未建模。

### ② 生产状态映射（2026-11-22 A2 修正：课程 HUD + 每回合 1 张）

真机 `LessonState` 进搜索前还有一层「屏幕语义 → 模型」的映射，2026-11-22 修掉两个错误假设
（细节见 [FAILURES #42](FAILURES.md#L323)、[HANDOVER 二·补十五](HANDOVER.md)）：

- **课程 HUD**：右上角是**培育属性值**，不是课程分（课程分 = 属性值 − 开课属性值）；正中圆环
  「CLEAR截止 / PERFECT截止 N」是**还差 N 分**，不是过关线。`LessonReader.read()` 现在直接给出
  `score`（本课已得分）/**`gauge`**（过关线 = 已得分 + 还差分）/**`perfect`**（满分线：档位表反推，
  普通/SP = 2×，追い込み 90→360、165→600）/ `goal`；`auto_produce` 每课调 `reset_lesson()`
  重置属性基线。旧读法把「属性 90 / CLEAR截止 30」当成"已 PERFECT"，档位效用封顶 → 每步 SKIP。
- **每回合出牌上限 = 1**：游戏默认每回合只能出 1 张牌（额外出牌来自卡效果 `ExamPlayableValueAdd` /
  P 道具；四场采集考试 39 回合里 32 回合 1 张、7 回合 2 张）。生产 `_search_state` 因此
  `play_limit=1` 且每次决策只建模"现在打 1 张"（`plays_used=0`，下一帧重新读屏再决策）；
  旧实现写死 3 会让搜索偏好"buff + 补刀"组合，实际游戏做不到（每回合先铺 buff → 课程 0 分）。
- **硬打保分**：搜索建议 SKIP（被禁跳规则拦截）时，先筛「屏幕分数预览 > 0」的牌（buff 记 0）再按
  （搜索价值, 屏幕分）硬打——搜索在"反正到不了 CLEAR"的回合会把动作打成平手，旧排序会挑中 buff。

### ③ `lesson.engine = "beam"`：跨回合 beam 接进生产策略

```
policy.json  {"lesson": {"engine": "beam", "beam_width": 4, "beam_deadline_ms": 250}}
```

- `_try_beam`：`LessonPolicy` → `ExpectState`（含计划给的全知字段）→ `search_beam`（V_leaf 排序），
  出计划首牌；`beam_width` / `beam_deadline_ms` 从 `policy.json` 读（默认 4 / 250ms）。
- **没有 known_draw 时自动退回回合内 expectimax**（beam 跨回合没有信息优势，不做无谓预算消耗）；
  `search_beam` 异常退回 `rules`，绝不退化。
- 测试：`tests/test_policy_beam_engine.py`（7 条：policy.json 开关 / 参数解析、known_draw 注入
  `ExpectState`、无牌序退回 expectimax、异常退回 rules、SKIP 在考试模式不输出、计划驱动
  `begin_turn/end_turn`）。

### ④ T3 离线预演：`--current` 候选 → `ExamPlanSelector`（2026-11-22，WORKPLAN A5）

真机 T3 的离线替身：考试还没结束、拿不到 `EndExamBattle` 时，`build_exam_setup.py --current
--allow-finished` 对**最近一场** `StepAuditionStart` 输出多个 `config_turns` 候选（默认 9/11/12，
每个候选一份完整 setup 记录），由 `ExamPlanSelector` 用每回合实机手牌逐回合淘汰，唯一剩下即锁定。
本项用**已结束采集的 truth** 把这条链路离线跑通（不碰真机）：

```powershell
.venv\Scripts\python.exe scripts\build_exam_setup.py --current --allow-finished --out out\exam_setup_current_test.json
.venv\Scripts\python.exe scripts\verify_exam_plan_offline.py   # 一条命令：current 路径 + 四场 sweep
```

| 路径 | 场（seed / 牌堆） | 候选 | 锁定时机 | 选中 config_turns（真值） | 锁定后手牌核对 | known_draw 覆盖下一手 |
|---|---|---:|---|---|---:|---:|
| `--current`（最新一场） | 0x1E1A740D / 27 张 | 9/11/12 | T2（3→1） | **12（真值 12）** | 11/11（T2–T12） | 9/9 |
| sweep | 考试0 0x504C4509 | 9/11/12 | T1 | 9（真值 9） | 9/9 | 7/7 |
| sweep | 考试1 0x7ECD7553 | 9/11/12 | T1 | 11（真值 11） | 8/8（T8 数据限制） | 7/7 |
| sweep | 考试2 0x47E1B2A5 | 9/11/12 | T1 | 9（真值 9） | 7/7（forceEnd 提前结束） | 5/5 |
| sweep | 考试3 0x1E1A740D | 9/11/12 | T2 | 12（真值 12） | 11/11（T12 数据限制） | 9/9 |

- **DoD 达成**：候选全部收敛到 1、`locked_turn` ∈ {1,2}（≤3）、选中 `config_turns` == 全量检测出的
  真值、锁定后逐回合手牌核对全中。第 1 回合分不出的场（isInitial 卡相同）在第 2 回合收敛，
  与 QQ 群「2–3 回合锁定 seed」口径一致。
- 数据限制与 `verify_exam_wiring` 同口径：打出**考试内生成的卡**（11-20 期末 T8 / 11-21 期末 T12）
  时 grave 不可重建，核对到该回合为止，不算失败。
- 测试：`tests/test_exam_plan_offline.py`（8 条：候选复制、truth 驱动统计、真实/错误候选、
  生成卡提前停止、`evaluate_row` DoD 判定、CLI 全链路）。
- **仍未做的**：真机考试进行中跑 `--current` + bot 运行时重载 + `[exam-plan] summary` 验收
  （阶段 E / T3 剩余项）。

### 仍未接/已知限制

- **采集进程 ↔ 决策进程真机验收**（item④）：代码已接（`build_exam_setup.py --current` +
  `ExamPlanSelector` + `auto_produce` 运行时重载），离线预演已用采集 truth 跑通（见 ④）；
  剩真机：考试进行中跑 `--current`，验收 `[exam-plan] 挂上` 与 `summary` 的 `locked_turn` 2–3、
  `verified == 实战回合数`（阶段 E / T3）。
- `ExamDrawPlan` 依赖**真实打出顺序**记 grave：策略选牌与实机点击必须一致（生产里本来就是同一进程；
  离线回放会因策略与实机出牌不同而在重洗处停用，属预期安全行为）。
- 同一局两次弃牌重洗时，`oracle.reshuffle` 用同一个 RNG 快照（第二次起可能偏）；现有四场最多重洗一次。
- 考试内生成的卡（重洗/抽牌效果产生）不在 oracle 牌堆里：出现即核对失败 → 停用（安全）。
- **模拟器口径待对齐**（2026-11-22 A2 发现）：`sim/lesson.py` 的 `plays_per_turn` 默认 3，与真机
  「默认每回合 1 张 + 额外出牌」不一致；生产搜索已改 1，`sim_engine_ab` 的整局 A/B 与模拟器评分
  需要重新标定（见 [WORKPLAN](WORKPLAN.md) T5/B3 与 FAILURES #42 遗留）。

## T4 修正（B1，2026-11-22）：评测执行器 bug + beam 实际强于 within

> ⚠️ **本节数字是 B3（2026-11-22 回合规则对齐）之前的口径**：当时 `LessonSim` 默认
> 每回合 3 张、不建模跳过回体力。B3 后同 harness 重测数字见文末
> 「B3 规则修正与重标定」——结论（beam > within）不变，绝对值不可与本表混用。

**结论先行**：T4 之前「beam 仍比 within 低 22.3%」的结论是**评测 bug**，不是 V_leaf 的能力
上限。修掉 bug 后，同牌组 / 同 seed 的 60 局配对：beam **164.0（unknown）/ 165.5（known）**
vs within **143.1**，配对差 **+20.9 / +22.4**（95% CI 全正），**B1 决策门 PASS**
（beam/within = 114.6% / 115.7%，门槛 90%）。

### 根因：`eval_known_draw._execute_plan` 白丢一整回合

`LessonSim.step` 在「手牌打空」时会**自动结束本回合**（`lesson.py`：「手牌打空：本回合自然
结束」）。beam 的根回合计划通常就是把 3 张手牌打光；旧评测执行器在按计划出完牌后，又按
「如果还能出牌就 SKIP 结束回合」补了一刀 `sim.step(None)`——此时已经进入下一回合，这一
SKIP 把**下一整个回合**白丢。于是每个 beam 决策都少打一回合，分数被系统性拉低（旧表 beam
≈ 111）；within 走的是逐张决策，不经过该执行器，所以数字不受影响——旧实验把「执行器
bug」误读成了「V_leaf 的 μ 不准」。

修法（`scripts/eval_known_draw.py`）：执行计划前记 `start_turns_left`；计划把当前手牌打空时
循环后**不再**补 SKIP，短计划才在同一回合补一次。回归测试
`tests/test_beam_frontier.py::test_execute_plan_does_not_skip_next_turn_when_hand_empties`
与 `test_execute_plan_ends_turn_once_for_short_plan`。

### 修正后的配对评测（`scripts/eval_t4_b1.py`，60 局）

small = 真实牌组 14 张 / 5 回合 / CLEAR 120 / PERFECT 170；within = 当前生产回合内
expectimax（budget 200ms）；beam = width 4 / budget 100ms / `score_tiebreak=1e-3` /
branching 默认；`beam+frontier` = 只对 beam 最深端点做 within rollout 重排。

| 策略 | 信息 | 均值 | P50 | CLEAR | PERFECT | vs within | 95% CI | 胜/平/负 |
|---|---|---:|---:|---:|---:|---:|---|---|
| within | unknown / known | 143.1 | 145 | 83.3% | 13.3% | — | — | — |
| beam | unknown | **164.0** | 162 | 98.3% | 33.3% | **+20.9** | [+14.4, +27.3] | 47/5/8 |
| beam | known | **165.5** | 165 | 100.0% | 38.3% | **+22.4** | [+16.5, +28.4] | 47/4/9 |
| beam+frontier | unknown | 164.0 | 162 | 98.3% | 33.3% | +20.9 | [+14.4, +27.3] | 47/5/8 |
| beam+frontier | known | 165.5 | 165 | 100.0% | 38.3% | +22.4 | [+16.5, +28.4] | 47/4/9 |

**决策门（WORKPLAN B1）**：未知/已知两种信息条件下 beam 都 ≥ within 的 90% → **PASS**。
注意这里 **unknown 也赢**：跨回合 beam 的期望抽样规划本身就比单回合解析叶子强，不依赖
known_draw；known 只是额外 +1.5。

### 消融：起作用的是 `score_tiebreak`，不是 branching（60 局，同 seed）

| beam 配置 | unknown 均值 | known 均值 | vs 默认（unknown） | vs 默认（known） |
|---|---:|---:|---|---|
| 默认（tiebreak=0，branching=默认） | 148.6 | 153.8 | — | — |
| **+ score_tiebreak=1e-3** | **164.0** | **165.5** | **+15.4 [+11.2,+19.7]** | **+11.8 [+7.6,+15.9]** |
| + branching=10（tiebreak=0） | 151.2 | 153.8 | +2.7 [−2.4,+7.8] | +0.1 [−2.5,+2.6] |
| + tiebreak + branching=10 | 161.6 | 164.8 | +13.1 [+7.4,+18.8] | +11.0 [+6.8,+15.1] |

旧结论「branching=10 贡献 +19.9」是同一个 bug 的副产物；修正后 **branching 无显著收益**，
`score_tiebreak=1e-3` 仍是真收益（方向与旧实验一致）。生产默认（expectimax /
tiebreak=0）本任务不改；T2 真机 A/B 时建议把 `beam + tiebreak` 作为候选。

### 受控 policy-evaluation 叶子（B1 交付）在中性

`search_beam(frontier_value=...)`：beam 被预算截断后，只对**最深端点**
（`end_state.turns_left > 0`）用执行同策略（`within`）rollout 重排；终局端点直接用精确档位
效用、不 rollout；默认 `None` = 历史行为逐位不变。60 局配对 **与普通 beam 逐位相同**。
原因：small 真实牌组上 beam 的 4 个根计划会收敛到同一个前沿状态（同 `canonical`），
rollout 值相同，重排自然无差；`turns_left=1` 的截断本来就接近精确。结论：实现保留
（默认关闭、有单测），但 **T4 的瓶颈不在叶子，而在评测执行器**；当前唯一可复现的
beam 增益是 `score_tiebreak`。

复现命令：

```powershell
.venv\Scripts\python.exe scripts\eval_t4_b1.py --games 60 --json out\t4_b1_tb.json
# 消融（tiebreak / branching 各开）见 HANDOVER 二·补十九 的命令清单
```

## T4 起点：档位效用封顶的平手项（2026-11-22 凌晨，实验）

> ⚠️ **2026-11-22 B1 复核：本节 beam 列（91.3 / 105.5 / 111.2 等）已作废**——它们由
> `_execute_plan` 丢回合 bug 产生。修正后 beam unknown 164.0 / known 165.5，已高于 within
> 143.1（见上一节）。within 列、tiebreak 方向与诊断记录仍有效，保留作历史。

T4 目标是让「全知 + beam」的离线优势变成分数，决策门是真实牌组上 beam 显著优于回合内
expectimax。先用真实小牌组（14 张 / 5 回合，CLEAR 120 / PERFECT 170）诊断 beam 为什么
还不如回合内搜索（87.9 vs 144）。

### 诊断
- 解析档位效用 `a·P(CLEAR) + b·P(PERFECT)` **封顶 2.0**：深搜里大量「稳过」分支打成
  平手；平手时搜索的 `_action_tiebreak` 优先保留出牌位/体力（= 存资源），beam 的 plan 排序
  在平手时退化成枚举顺序 → 实测偏好"少打牌/存体力"。
- 单独扫 σ（10~80）对 within/beam 决策完全无影响；beam 的 `branching` 从 3 提到 6/10
  有明显提升 → 抽样噪声也是原因之一。

### 改动（默认关闭，生产行为不变）
- `AnalyticLeafValue.score_tiebreak`（默认 0）：>0 时在档位效用上加极小的
  `预测总分 / PERFECT 线` 项，给平手一个「分数/进度」排序；默认 0 逐位保持历史行为。
- `scripts/eval_known_draw.py` 新增 `--score-tiebreak` / `--branching` 供配对评测。

### 配对评测（small、beam、unknown、60 局同 seed、budget 200ms）

| 策略 | 均值 | P50 | CLEAR | PERFECT |
|---|---:|---:|---:|---:|
| 回合内 expectimax（within） | 143.1 | 145 | 83.3% | 13.3% |
| within + tiebreak=1e-3 | 143.4 | 145 | 83.3% | 13.3% |
| beam（width 4，默认） | 91.3 | 85 | 28.3% | 0% |
| beam + tiebreak=1e-3 | 105.5 | 104 | 28.3% | 0% |
| beam + tiebreak + branching=10 | **111.2** | 111 | 36.7% | 3.3% |

- 配对差（同 seed）：beam+tiebreak vs beam **+14.3（95% CI [+7.9, +20.6]）**；
  再加 branching=10 **+19.9（CI [+12.8, +27.1]）**；within+tiebreak vs within
  +0.3（CI [−0.0, +0.6]），基本无副作用。
- **（2026-11-22 B1 复核）以上 beam 列全部作废**：它们来自 `_execute_plan` 白丢回合 bug；
  修正后 beam unknown 164.0 / known 165.5（+20.9/+22.4）已**超过** within 143.1，
  原「beam 低于 within 22.3%、决策门未达成」不成立。`score_tiebreak` 的真收益方向保留，
  branching 修正后无显著收益；生产默认本任务不改。

### 结论与下一步
1. ~~平手项证明「效用封顶导致 SKIP 偏置」是真因之一，但**主因仍是 V_leaf 的 μ 不准**~~
   （2026-11-22 B1 复核：诊断建立在丢回合 bug 上，已不成立；B1 修正后解析式 beam 已超 within）。
2. ~~下一步优先做 rollout 叶子估值~~ → B1 已做受控 frontier 版：**中性**；旧 rollout 叶子
   beam 侧负结果同样作废，learned V 留 B2 用修正 harness 重测。
3. beam 抽样分支配套：`branching=10` 有显著收益，继续加宽收益饱和（width 8/16/32 试验约 101~112）。
4. 仍按 T4 决策门：真实牌组 beam 显著优于 expectimax 之前，不改生产默认。

命令：`python scripts/eval_known_draw.py --games 60 --scenario small --policy beam --score-tiebreak 0.001 --branching 10`

## rollout 叶子实验（T4，2026-11-22 凌晨，**负结果**）

> ⚠️ **2026-11-22 B1 复核：本节 beam 侧数字（111.3 / 111.4 / 103.0 / 104.1 与各变体
> 78.8~89.0）已作废**——同一 `_execute_plan` 丢回合 bug。修正后解析式 beam 基线为
> 164.0/165.5（见上一节），旧「rollout 叶子负结果」不能当作路线否定证据；受控 frontier
> 叶子已按 B1 重测为中性。within 策略侧结论（within + rollout 叶子 ≈ 中性：145.4 vs 143.2）
> 不经过该执行器，仍然有效。

**动机**：T4 诊断结论是"V_leaf 的 μ 不准"（真实小牌组 beam 111.2 vs 回合内 expectimax 143.1）。
解析式 μ 高估"存体力"，于是做最小版 rollout 叶子：叶子用 `LessonSim` 把剩余回合快跑一遍，
拿最终分数增量当 μ。

**实现**
- `src/gkagent/sim/expectimax.py`：
  - `sim_from_state(state, *, rng, plan)`：把搜索里的纯 `ExpectState` 快照重建成可跑的 `LessonSim`
    （牌序：`known_draw` 已知→按已知顺序；未知→按 rollout rng 洗牌；叶子手牌为空时补一手）。
  - `RolloutLeafValue`：`predict` = `rollouts` 次 rollout 的分数增量均值/标准差（σ=max(sigma, 实测std)），
    `utility` 复用解析式档位公式；按 `state.canonical()` 缓存。
  - rollout 策略可选 `greedy`（快）或 `within`（每回合小预算 expectimax，慢）；后者用于验证
    "叶子策略必须跟执行策略同强度"。
- `scripts/eval_known_draw.py`：新增 `--leaf {analytic,rollout}`、`--rollouts`、
  `--rollout-policy {greedy,within}`、`--rollout-budget-ms`。

**配对评测（small，60 局，beam width=4 / budget=100ms / branching=10 / score_tiebreak=1e-3）**

| 叶子 | unknown 均值 | known 均值 | CLEAR 率(u/k) | fallback |
|---|---:|---:|---:|---:|
| analytic（基线） | **111.3** | **111.4** | 35.0% / 38.3% | 0 |
| rollout greedy r=3 | 103.0 | 104.1 | 28.3% / 26.7% | 0 |

- 20 局变体：rollout 且不开 tiebreak 更差（78.8~89.0）；`--rollout-policy within`（budget 5ms）
  也只有 78.8/85.3。within 策略本身：analytic 145.4 vs rollout 143.2（≈中性，略差）。
- 结论：**最小版 rollout 叶子没有改善 beam，反而 -7~8 分**。原因是 rollout 策略（greedy）
  比执行策略（回合内 expectimax）弱，leaf μ 的排序和执行结果错位；rollout 次数（1/3/6）不改变结论。

**为什么没继续硬啃**
1. 用执行同强度策略做 policy-evaluation 叶子，成本 = 每叶子"剩余回合 × 每回合 expectimax"，
   在 beam 的数百个端点上是十几倍的耗时；B1 的受控版（只对最深端点）已实测为中性；
2. 三次 learned 线性 V 失败说明"线性特征+回归"也不通，需要新信息（rollout 数据拟合/机制建模）；
3. ~~现有解析式 + tiebreak 在 beam 上已经是 111.2~~（旧 bug 口径；修正后解析式 + tiebreak
   已经是 164.0/165.5，不靠 rollout 叶子也超过 within）——T4 的收益先落在评测修正 + 平手项。

**下一步（按性价比）**
1. ~~**策略评价叶子（受控成本）**：只对 beam 最深一层端点做 rollout~~ → **B1 已做：中性**
   （见上一节 T4 修正）；
2. **rollout 数据 → 学 V_leaf**：用 rollout 的（状态, 最终分）样本重训 `v_leaf.json`
   （比纯解析特征多一个"自我对弈"监督信号；B2 方向，需用修正后的 harness 重测）；
3. 同时补 T5 机制建模（P 道具/回忆/附魔/选牌/减益），否则 rollout 再准也只是模拟器内准。

命令（复现旧负结果；beam 侧数字已被 B1 判定作废，仅作历史）：
```powershell
.venv\Scripts\python.exe scripts\eval_known_draw.py --games 60 --scenario small --policy beam \
  --width 4 --budget-ms 100 --branching 10 --score-tiebreak 0.001 \
  --leaf rollout --rollouts 3 --rollout-policy greedy
```

### known_draw 的已知边界（2026-11-22 情报更新）

群里公开的「考试 RNG 全部显式消费入口」清单（详见 [QQ_GROUP_NOTES](QQ_GROUP_NOTES.md)）与我们的 K 模型对照：
已覆盖 `open_turn_types(T-3)`、`session_start_turn(npc×T)`、`deck_shuffle(N-1)`、弃牌堆回收(N-1)、
支援升级判定；**未建模**：恐慌判定（`apply_panic_command`）、卡牌搜索随机排序（`get_search_card_list`）、
随机选取卡牌（`pickRangeType==2`）、随机卡池生成（`apply_card_create_search`）、出牌后随机返回牌库位置
（`play_move_position_type==4`）、效果随机移动（`move_pos==4`）、生成新卡随机插入（`create_card_deck_random`）。

- 影响：牌组里含这些效果（卡表 effects：`ExamCardCreateId` / `ExamCardCreateSearch` / `ExamCardMove` /
  `ExamCardSearchEffectPlayCountBuff` / `ExamForcePlayCardSearch` / 恐慌类）时，RNG 推进次数无法精确计数 →
  **known_draw 只能用到第一个此类事件**；之后必须退回期望。
- 现有保护是"核对失败即停用"（事后）；下一步应做**事前检测**：建 ExamSetup 时扫牌组/支援的 effects，
  命中上述机制 → 标记 `unverifiable`/不启用全知，避免白跑核对和错误计划。
- 纯牌组（无上述机制）的 4/4 场整段复现不受影响。

### 事前检测已实现（2026-11-22 凌晨）

- 新模块 `src/gkagent/sim/exam_risk.py`：扫描卡表/牌组里的**额外 RNG 机制卡**
  （`ExamCardCreateId`/`ExamCardCreateSearch`/`ExamCardMove`/`ExamForcePlayCardSearch`/
  `ExamCardSearchEffectPlayCountBuff`/`ExamReviewPerSearchCount`/搜索费用变化/恐慌类）；
- `scripts/build_exam_setup.py`：生成记录时写 `rng_risk` 字段（含默认全量 + `--current` 两种模式），
  命中就打印「known_draw 不可验」；
- `ExamSetup.known_info_ok`（`rng_risk` 为空才 True）；`ExamDrawPlan.start()` 对不可验 setup
  **直接停用**（不建 oracle、不给 known_draw，reason 写明原因）；
- `auto_produce.build_exam_plans()`：加载候选时跳过不可验的，日志
  `[exam-plan] 跳过 N 个含额外 RNG 机制的候选`；
- 实测：卡表 1829 张里 **169 条**带额外 RNG 机制；我们验证过的四场考试牌组命中 **0**（纯牌组），
  所以 4/4 精确复现成立；含机制的牌组以后不会再盲目跑核对。
- 回归：`tests/test_exam_risk.py` 8 条；`build_exam_setup` 4/4、`verify_exam_wiring` 36/36、3/3、29/29 不变。

---

## B2 学习叶子（2026-11-22）：全知数据 MLP 叶子 + B1 修正 harness

> ⚠️ **本节数字是 B3 之前的旧回合口径**（每回合 3 张）。B3 把模拟器改成真机 1 张/回合 +
> 跳过回体力后，本模型**失效**（确认段 beam −27.9 显著负）。**2026-11-23 已按 B3+ 规则
> 重采/重训（B2-R）：仍 FAIL（确认段 −7.2，ensemble 0.75 中性）；同日高预算验证
> （width8/300ms）也 FAIL（选择段 −4.4 CI[−8.8,−0.0]）→ 学习叶子路线已关闭**，
> 负结果与结论见文末「B2 重训（B2-R）」；生产 `leaf_model` 保持默认关闭。

**结论先行**：用**全知 beam 自我对弈**的「叶子状态 → 实际后续得分」样本训练 104 维结构化
MLP 叶子，接进 **B1 修正后的 beam**：真实小牌组 120 局配对（全新 seed 3000–3119，
同牌组同 seed）**beam 均值 157.8 → 165.5（learned，+7.7，95% CI [+4.2,+11.2]）/ 166.9
（analytic+learned ensemble 0.5，+9.0，CI [+5.8,+12.2]）**；known 条件同样 +7.2~+7.8。
CLEAR 95.0%→98.3%、PERFECT 33.3%→50.0%。**B2 DoD 达成**（离线配对显著优于解析式叶子）。

**为什么这次和三次历史失败不同**（见本文件「拟合 V_leaf 的实验结果」等三节）：

1. **标签来自搜索策略本身**（beam 全知自对弈的真实后续得分），不是贪心轨迹；
2. 样本取在**叶子状态分布**上——`expectimax._Search.leaf` 的输入是
   `end_turn_state(state)`（手牌已进弃牌堆、好印象已结算并 -1、buff 已倒计时、回合 -1）。
   `RecordingLessonSim` 在每次 `_draw_hand` 入口记录该瞬时点并换算成同形态
   （旧脚本在**回合开始手牌还在手上**采样，`hand_*` 训练/推理不同分布）；
3. 特征 104 维结构化（状态/分数缺口/体力、buff 计时、指針、饮料/P 道具、
   **牌库 vs 弃牌堆拆分**、牌库效果聚合、交互项），不是 35 维裸线性；
4. 模型 2 隐层 MLP（104→96→48），μ 用 MSE、σ 用残差头高斯 NLL；实现 `LeafValue`
   协议，直接替换 `AnalyticLeafValue`，**搜索/beam 代码零改动**；
5. 评测复用 B1 修正后的执行器（`eval_known_draw._execute_plan` 不再白丢回合）。

### 数据 / 训练

| 项 | 做法 | 产物 |
|---|---|---|
| 采集 | `scripts/build_b2_dataset.py`：`RecordingLessonSim` + beam 全知自对弈；teacher 3 批（width4/100ms ×1500 + ×3000 局；width8/300ms ×800 局），26,500 样本 | `out/b2_leaf_beam_*.npz`（gitignore，可重建） |
| 标签 | `y = 最终分 − 叶子状态分数`（on-policy return）；自然打满回合补 `turns_left=0` 终局样本（y=0） | — |
| 特征 | `src/gkagent/sim/leaf_mlp.py::features`（104 维）；叶子状态约定同搜索 | — |
| 训练 | `scripts/train_b2_leaf.py`：按 seed 分组 9:1 切分，MLP 104→96→48，700 epochs Adam，σ 残差头 | `data/knowledge/b2_leaf_mlp_small.json`（335KB，tracked） |
| 验证 | held-out seed：μ r²=0.943、MAE 8.8、corr 0.971（旧 35 维线性 r²≈0.91、MAE≈9.5；ridge 0.933） | `out/b2_report_beam_all.json` |
| 评测 | `scripts/eval_b2.py`（B1 修正 harness；within/beam × analytic/learned/ensemble，配对差 + 95% CI；退出码 = B2 判定） | `out/b2_eval_*.json` |

### 配对评测（small 真实牌组 14 张 / 5 回合 / CLEAR 120 / PERFECT 170）

**A. 选择段 seed 2000–2079（80 局，unknown 信息）**——选模型/集成权重：

| 策略 | 均值 | P50 | CLEAR | PERFECT | vs 解析式 beeam | 95% CI |
|---|---:|---:|---:|---:|---:|---|
| beam（解析式叶子，B1 配置） | 166.8 | 168 | 95.0% | 46.2% | — | — |
| beam + **learned** | **173.7** | 173 | 98.8% | 56.2% | **+6.8** | [+3.2,+10.4] |
| beam + ensemble w=0.25 | **174.4** | 174 | 98.8% | 60.0% | **+7.5** | [+3.7,+11.4] |
| beam + ensemble w=0.5 | 173.7 | 175 | 98.8% | 57.5% | +6.9 | [+2.7,+11.0] |
| beam + ensemble w=0.75 | 173.2 | 174 | 97.5% | 57.5% | +6.3 | [+2.6,+10.1] |

**B. 确认段 seed 3000–3119（120 局；模型/权重选定后才跑，未参与选择）**：

| 策略 | 信息 | 均值 | P50 | CLEAR | PERFECT | vs 解析式 beam | 95% CI |
|---|---|---:|---:|---:|---:|---:|---|
| beam 解析式 | unknown | 157.8 | 157 | 95.0% | 33.3% | — | — |
| beam + learned | unknown | **165.5** | 169 | 98.3% | 49.2% | **+7.7** | [+4.2,+11.2] |
| beam + ensemble w=0.25 | unknown | **166.2** | 170 | 97.5% | 50.0% | **+8.4** | [+5.0,+11.8] |
| beam + ensemble w=0.5 | unknown | **166.9** | 170 | 98.3% | 50.0% | **+9.0** | [+5.8,+12.2] |
| beam 解析式 | known | 159.9 | 158 | 96.7% | 36.7% | — | — |
| beam + learned | known | **167.1** | 170 | 98.3% | 50.0% | **+7.2** | [+3.7,+10.7] |
| beam + ensemble w=0.25 | known | **167.7** | 172 | 98.3% | 51.7% | **+7.8** | [+4.4,+11.1] |
| beam + ensemble w=0.5 | known | **167.4** | 169 | 98.3% | 49.2% | **+7.5** | [+4.1,+10.9] |

- **B1 基线未变**：seed 0–59 重跑仍 within 143.1 / beam unknown 164.0 / known 165.5（`out/b2_sanity_b1.json`）；
  `eval_b2` 的 B1 配置列与 `eval_t4_b1` 逐位一致（同分支/预算/tiebreak，注意 beam `branching=0→None`）。
- **数据量**：1500 局 teacher（7.5k 样本）时 +6.8；加宽/加量到 26.5k 样本后确认段 +7.7；
  **第二轮自对弈**（teacher=beam+learned，7.5k 样本）反而只有 +5.7/+6.2（选择段），未采用。
- 复现命令（worker 数无关，均为同机 deterministic）：

```powershell
# 采集（约 5–9 分钟/批；out/ 不进 git）
.venv\Scripts\python.exe scripts\build_b2_dataset.py --games 3000 --policy beam --known --out out\b2_leaf_beam_known2.npz --seed 600000
.venv\Scripts\python.exe scripts\build_b2_dataset.py --games 800 --policy beam --known --width 8 --budget-ms 300 --out out\b2_leaf_beam_strong.npz --seed 500000
# 训练（合并三批；约 1 分钟）
.venv\Scripts\python.exe scripts\train_b2_leaf.py --data out\b2_leaf_beam_known.npz out\b2_leaf_beam_known2.npz out\b2_leaf_beam_strong.npz --out data\knowledge\b2_leaf_mlp_small.json --hidden 96 48 --epochs 700
# 评测（选择段；确认段把 --seed 改 3000）
.venv\Scripts\python.exe scripts\eval_b2.py --leaf-model data\knowledge\b2_leaf_mlp_small.json --games 80 --seed 2000 --info unknown --ensembles 0.25 0.5 0.75 --json out\b2_eval_*.json
```

### 负结果（如实记录，避免重复踩）

1. **within 用 learned 叶子显著变差**：同搜索换成 learned（或 ensemble）叶子，确认段
   within 140.0 → 136.7（−3.3，CI [−5.6,−1.1]）。原因：V 的标签是**更强 beam 策略**的收益，
   对 within 执行来说系统性偏乐观；within 只拿叶子做"本回合动作排序 + 是否收手"，
   策略改进收益拿不到、只吃偏差。**结论：B2 叶子只对 `engine=beam` 有益**。
2. **within 自对弈叶子（正确策略标签）≈ 中性**：30k within 样本训练，60 局 +0.9（CI [−2.4,+4.2]）。
   与"解析式叶子不是 within 的瓶颈"一致。
3. **档位概率头（logistic P(CLEAR)/P(PERFECT)）在 beam 上灾难性变差**（−42~−46）：
   beam teacher 的叶子状态 98.7% 最终 CLEAR，P(CLEAR) 饱和到 0.96 → 搜索排序失去平滑
   μ 信号。保留实现（`train_b2_leaf.py --utility-heads`）但**不用于最终模型**。
4. **第二轮专家迭代**（teacher=beam+learned 的 7.5k 样本）未超过第一轮（选择段 +5.7 vs +6.8）。

### 生产接线（未默认打开）

- `LessonPolicy.DEFAULT_PARAMS` 新增 `leaf_model`（默认 `None` = 行为不变）与
  `leaf_model_weight`（默认 0.5）；`_leaf_value()` 显式配置时构
  `EnsembleLeafValue(analytic, learned)`，并**缓存**（旧实现每决策重读 JSON）。坏路径只 warning 退回解析式。
- **不要给 expectimax（within）打开**（见负结果 1）；T2 真机 A/B 时按引擎分别评估，
  建议候选：`engine=beam` + `leaf_model=data/knowledge/b2_leaf_mlp_small.json` +
  `leaf_model_weight=0.25`（选择段最佳权重）。真机是否同样有收益取决于 B3 机制对齐：
  **B3（2026-11-22）已把模拟器改成真机每回合 1 张 + 跳过回 2 体力 + 取整对齐**，
  这一改动让 B2 模型（在旧 3 张口径数据上训练）**失效**——重测显著变差、必须按 B3
  规则重采数据重训（见文末「B3 规则修正与重标定」）。
- 规格注意：叶子特征**不含 `known_draw`**（student 是公开信息策略）；known 条件的收益来自
  「把全知 teacher 的结果蒸馏进公开特征」，不是偷看牌序。

### 测试 / 基线

- `tests/test_b2_leaf.py` 11 条：叶子特征维度/纯函数/手牌归一化、`RecordingLessonSim`
  快照与标签、MLP save/load（含/不含档位头）、utility 契约、expectimax 接 learned 叶子、
  合成数据训练收敛、生产 `LessonPolicy` 的 `leaf_model` 接线 + 缓存 + 坏路径兜底。
- 全量 pytest **975 passed / 1 skipped**（976 收集 / 71 文件）；ruff 通过。
- 基线 ①③④ 全部不变（B2 只新增模块/脚本 + `eval_known_draw.play` 两个可选参数 +
  `LessonPolicy` 可选参数/缓存）。

## B3 规则修正与重标定（2026-11-22）：每回合 1 张 + 跳过回体力 + 取整

B3 把模拟器从"每回合 3 张"改成真机规则（每回合基础 1 张、打完自动结束回合、SKIP 回 2 体力、
`safeCeil` 取整），所有离线评测/自对弈的绝对分数都变了，**本节是 B3 后唯一有效口径**：
上面 T4/B2 各节数字只能当历史记录，不能新旧混比。

### B1 重测（`scripts/eval_t4_b1.py --games 60`，small，同配置）

| 信息 | within | beam | beam+frontier | vs within（95% CI） | 决策门 |
|---|---:|---:|---:|---|---|
| unknown | 89.1 | **95.7** | 95.7 | **+6.6** [+2.2,+11.1]，胜/平/负 28/19/13 | 107.4% PASS |
| known | 89.1 | **95.7** | 95.7 | **+6.6** [+3.1,+10.1]，胜/平/负 28/26/6 | 107.4% PASS |

- 结论不变（beam 显著强于 within、frontier 叶子仍中性），但绝对值从 143.1/164.0/165.5
  缩到 89.1/95.7：每回合 1 张后一局只有 5 张牌可打，量级变小是**口径**不是退化。
- JSON：`out/b3_eval_t4_b1.json`。

### B2 重测（未重训，模型仍是旧 3 张口径数据训练的）——**FAIL，必须重训**

| 段 | 基线（解析式） | + learned | + ensemble 0.75 | 判定 |
|---|---:|---:|---:|---|
| 选择段 seed 2000（80 局，unknown） | beam 97.3 | 71.2（**−26.1**，CI[−31.4,−20.8]） | 91.3（−6.0） | ❌ 全部显著负 |
| 确认段 seed 3000（120 局，unknown） | beam 94.9 | 67.1（**−27.9**，CI[−32.6,−23.1]） | 89.6（−5.3） | ❌ 全部显著负 |
| 确认段 known | beam 96.8（解析式） | 56.7（−40.1） | 90.6（−6.2） | ❌ |

- 原因：`leaf_mlp` 的 104 维特征里 `play_limit`/出牌位/回合内分数分布全是旧 3 张口径，
  训练标签（未来得分）与 B3 后的真实分布差一个量级 → 模型输出系统性偏乐观/偏悲观。
- **结论**：生产接线保持默认关闭（本来就没开）；B2 的有效结论作废。**2026-11-23 更新：
  T5 机制（B4–B10）补齐后已重采/重训（B2-R），仍 FAIL（确认段 −7.2，ensemble 0.75 中性）——
  见文末「B2 重训（B2-R）」负结果与结论**。JSON：
  `out/b3_eval_b2_select.json` / `out/b3_eval_b2_confirm.json`。

### 整局 A/B（`scripts/sim_engine_ab.py`，76 局）：expectimax 从"噪声内"变"显著更强"

| 种子组 | rules P50 | expectimax P50 | 配对 Δmean |
|---|---:|---:|---:|
| 9000（16 局） | 5170 | **5566** | **+372.2**（胜/平/负 15/0/1） |
| 21000（30 局） | 5176 | **5505** | **+341.8**（26/0/4） |
| 30000（30 局） | 5152 | **5513** | **+428.9**（29/0/1） |

- 0 blocked / 0 异常 / C+ 率 100%；B3 前是噪声内（−15.2/−4.9）。
- 解释：每回合只能出 1 张 → 单张选择的价值被放大，搜索相对规则启发式的优势才显现；
  这也说明**真机 T2 A/B 值得做**（旧口径低估了搜索引擎的价值）。
- 细节与 400 局培育标定带变化见 [SIMULATOR.md](SIMULATOR.md) §10/§11。

## B4（T5①）审查倍率进搜索（2026-11-22）：常量 4.11 → 屏幕真实倍率

**改了什么**：考试/舞台每回合的属性倍率（屏幕「歌唱 411%」）以前在搜索里恒为
`ExpectState.attribute_coefficient=1.0`（生产）——同回合内排序不变，但**绝对分估值**、
beam 跨回合比较、以及"先铺 buff 还是先打分"的长期收益都是按同一倍率估的。B4 之后：

- 真机 `LessonReader` 读到的屏幕倍率（如「舞蹈 207%」）经 `policy.audition_coefficient`
  换算成 `2.07` 喂进 `ExpectState.attribute_coefficient`；不可读时保持 1.0（不猜）；
- 搜索日志多一段 `attr=2.07`（`decision_note` / `last_decision.attr_multiplier`），
  真机能回答"这手搜索按什么倍率估的分"；
- 离线的模拟器（`LessonSim`）用 `attribute_bonuses` + `turn_attributes` 走**客户端真实公式**
  （分数表分段折线 × 审查基准联动惩罚 × 单精度取整，见 `sim/exam_multiplier.py`），
  出牌分含依赖分、回合末好印象也吃倍率。

**对搜索的影响（方向）**：
1. 同一回合内，所有候选牌乘同一个倍率 → **排序不变**（所以 B1/B2/B3 的评测结论不受影响）；
2. 但**叶子估值与阈值判断**（是否够 CLEAR/PERFECT、SKIP 回体力值不值）现在用真实量级，
   不会再出现"倍率 1.0 → 分数几十 → 全动作平手"的估值压缩；
3. beam 跨回合目前仍按"当前回合倍率"近似未来回合（回合属性由 RNG 决定、开局未知）；
   等 `ExamDrawPlan` 能给出逐回合 `parameterType` 后可以换成逐回合倍率——这一步留给 T3 实战验收/后续。
   注意：**不要**为了离线评测好看而把倍率写成 1.0 或常数 4.11，真机是逐回合不同的。

**与 B2 重训的关系**：B2 旧模型的特征/标签是"分数"量级，B3 改规则 + B4 改倍率后旧模型更不可用。
**2026-11-23 更新：T5 机制（B4–B10）补齐后已重训（B2-R），仍 FAIL**——small harness 无 P 道具/
属性倍率，B4–B10 对其局零影响（基线逐位不变）；重训负结果与结论见文末「B2 重训（B2-R）」。
生产 `leaf_model` 保持关闭。

**基线**：`tests/test_exam_multiplier.py` 21 条；全量 pytest 1006 passed / 1 skipped
（1007 收集 / 73 文件）；B1/B2/B3 的评测脚本不改口径（默认倍率仍 1.0/4.11）。
细节见 [RULES_REFERENCE §5.1](RULES_REFERENCE.md) / HANDOVER 二·补二十五。

## B5（T5②）熱意 + 温存解除进模拟器/搜索（2026-11-22）

**改了什么**：模拟器与搜索状态新增**独立熱意资源**（整数、回合内有效）：出牌分在集中之后
加算 `熱意 × 本牌熱意適用倍数`，温存解除给 +5/+8 熱意（2 段还 +5 固定元気）并让解除当回合
**可以多出一张牌**（`extra_plays`）；回合末清零，有「熱意延長」则保留并 -1；温存→全力的回合
边界切换也结算解除收益；卡牌熱意追加/増加/延長/本牌適用倍数由 `CardSpec` 承载并在
`sim_produce`（MODELED_EFFECTS 29→32）与生产卡表里解析。

**对搜索的影响（方向）**：
1. 非凡（アノマリー）牌组里「温存→強気」不再被当成单纯的好调回合：搜索现在能看到
   **+1 出牌次数**（多打一张的价值）和 **熱意加算**（后续每张打分牌都 +N，且吃好调/指針倍率），
   因此会更愿意在回合内做「解除温存」的连招；
2. 熱意適用倍数 ×2 的卡（`ExamMultipleEnthusiasticLesson`）在熱意 >0 时价值翻倍，搜索能自己发现；
3. 叶子估值：熱意回合末清零 → `end_turn_state` 里已归 0（延長除外），解析式叶子的口径不变；
   但 B2 学习叶子的 `save_cards_used` 特征已废弃（恒 0）。**B2-R（2026-11-23）重训保持
   104 维旧特征**（small 场景熱意/解除事件 0 次，不影响结论）；将来按 large/真机分布重训时
   再换熱意/score_buffs/modifier 特征（见文末 B2-R）。

**基线**：`tests/test_t5_enthusiasm.py` 16 条；全量 pytest 1023 passed / 1 skipped
（1024 收集 / 74 文件）。细节见 [RULES_REFERENCE §5.2](RULES_REFERENCE.md) / HANDOVER 二·补二十六。

## B2 重训（B2-R，2026-11-23）：按 B3+ 规则重采/重训 —— 仍 FAIL（可复现负结果）

> **结论先行**：T5 机制（B4–B10）补齐后，按本文件「B2 学习叶子」同配方在 B10 后模拟器上
> 重采 **26,500** 个 beam 全知自对弈叶子样本、重训 104 维 MLP（val r²=0.906 / MAE 7.0），
> B1 修正 harness 配对：**确认段 120 局 unknown beam 94.9 → learned 87.7（−7.2，
> CI[−9.5,−5.0]）/ known 96.8 → 85.3（−11.5）；ensemble 0.75 两段都中性（CI 含 0、点估计微负）；
> within_learned −19.9（显著负）**。**B2 DoD 走「可复现负结果 + 结论」分支达成**：
> B3 每回合 1 张规则下，学习叶子仍不能替代解析式叶子——重训把旧模型的 −26.1/−27.9
> 收窄到 −7.0/−7.2，但没能转正。**生产 `leaf_model` 保持默认关闭；beam 默认仍用解析式叶子。**
>
> **高预算验证（2026-11-23，用户指定「更强的 bot 能不能兑现学习叶子」）：仍 FAIL →
> 学习叶子路线关闭**。width8/300ms（teacher 级预算）选择段 80 局配对：beam 解析式 93.9 →
> learned 89.4（**−4.4，CI[−8.8,−0.0] 显著负**）/ ensemble 0.75 +0.0（中性）。
> 伤害从 −7.0 收窄到 −4.4，但**收窄主要来自解析式基线自己在高预算下变差（97.3→93.9），
> learned 绝对分几乎不动（90.3→89.4）**——提高搜索预算没有兑现学习叶子。
> 按用户判定规则（显著正才重开）：**路线关闭，负结果记录在案，转 C1 执行层可靠性**。
> 见下「高预算验证」小节。

### 做了什么

1. **重训前口径核对**：旧模型 FAIL 复现（选择段 seed 2000–2079，B10 后口径）——
   beam 解析式 97.3 → learned 71.2（−26.1，CI[−31.4,−20.8]），与 B3 重测**逐位一致**；
   within 89.1 / beam 97.3（选择段）、94.9/96.8（确认段 unknown/known）也逐位一致。
   说明 B4–B10 对 small harness 的局**零影响**（config 无 P 道具/属性倍率、牌组无熱意卡），
   解析式基线稳定，重训有干净对照。
2. **训练/推理分布等价性探针**（`data/_probe_b2_leaf_equiv.py`，未跟踪不提交）：
   greedy 300 局 + beam 全知 200 局，共 2000 个叶子快照 vs `end_turn_state` **逐字段等价**。
   查出并修掉一个**潜在口径差**（根因修复）：B5 温存→全力**回合边界**解除收益在
   `LessonSim._end_turn` 里是 `_draw_hand()` **之后**才结算的，而搜索侧 `end_turn_state`
   把它算进叶子——快照点（`_draw_hand` 入口）天然缺这块。`RecordingLessonSim` 现在在
   `_end_turn` 入口记录回合结束前指針（`_pre_end_turn_stance`），`leaf_state_at_draw`
   据此补上解除收益（熱意/固定元気/+1 出牌）。small 场景 2000 叶子 **0 次边界**（SAVE 只在
   全力值≥10 的回合末才切换），数据不受影响；修的是长回合场景重采会学歪的隐患。
   新增 1 条强制边界回归测试（`tests/test_b2_leaf.py` 11→**12 条**）。
3. **重采数据**（`scripts/build_b2_dataset.py`，3 批顺序跑避免 CPU 争用扭曲墙钟预算）：
   width4/100ms ×1500 局（seed 100000）+ ×3000 局（seed 600000）+ width8/300ms ×800 局
   （seed 500000），与评测段（2000–2079 / 3000–3119）错开 → **26,500 样本、0 fallbacks**，
   teacher 最终分 mean 97.4–97.7（与解析式 beam 基线一致）。标签 = **纯 on-policy 后续得分**
   （`y = 最终分 − 叶子分`），**不加 PBRS 势能塑形**——auto-gakumas 的 PBRS 负结果
   （−26,884）与我们 B2 历史负结果同向，见 [AUTO_GAKUMAS_NOTES §2.4/§5](AUTO_GAKUMAS_NOTES.md)。
4. **重训**（`scripts/train_b2_leaf.py`，B2 同配方）：MLP 104→96→48、700 epochs、
   seed 分组 9:1（val_mod=10）→ train r²=0.898 / **val r²=0.906 / MAE 7.0 / corr 0.952**
   （ridge val r²=0.896）；σ=11.1。**特征保持 104 维不变**（与 B2 配方可比；
   `save_cards_used` 仍废弃恒 0、熱意特征未加——small 场景熱意/解除事件 0 次，不影响本结论；
   将来若按 large/真机分布重训，先更新特征再采）。
5. **评测**（`scripts/eval_b2.py`，B1 修正 harness，同牌组同 seed 配对 + 95% CI）：
   选择段 80 局 seed 2000 选权重 → 确认段 120 局 seed 3000（unknown + known，未参与选择）。

### 配对数字（B3 后口径；small 14 张 / 5 回合 / CLEAR 120 / PERFECT 170）

**A. 选择段 seed 2000–2079（80 局，unknown）**：

| 策略 | 均值 | CLEAR | vs 解析式 | 95% CI |
|---|---:|---:|---:|---|
| within 解析式 | 89.1 | 7.5% | — | — |
| within + learned | 69.7 | 5.0% | −19.4 | [−25.0,−13.9] ❌ |
| within + ensemble 0.75 | 89.2 | 8.8% | +0.1 | [−3.5,+3.8] — |
| beam 解析式 | 97.3 | 11.2% | — | — |
| beam + learned | 90.3 | 5.0% | **−7.0** | [−10.4,−3.6] ❌ |
| beam + ensemble 0.25 | 95.1 | 10.0% | −2.2 | [−4.8,+0.4] — |
| beam + ensemble 0.5 | 95.8 | 12.5% | −1.5 | [−4.1,+1.2] — |
| beam + ensemble 0.75 | 97.3 | 11.2% | +0.1 | [−1.8,+2.0] — |

**B. 确认段 seed 3000–3119（120 局，模型/权重选定后才跑）**：

| 策略 | 信息 | 均值 | CLEAR | vs 解析式 | 95% CI |
|---|---|---:|---:|---:|---|
| beam 解析式 | unknown | 94.9 | 10.8% | — | — |
| beam + learned | unknown | 87.7 | 7.5% | **−7.2** | [−9.5,−5.0] ❌ |
| beam + ensemble 0.75 | unknown | 94.4 | 10.0% | −0.5 | [−2.0,+1.0] — |
| beam 解析式 | known | 96.8 | 11.7% | — | — |
| beam + learned | known | 85.3 | 9.2% | **−11.5** | [−14.6,−8.5] ❌ |
| beam + ensemble 0.75 | known | 96.3 | 11.7% | −0.6 | [−1.4,+0.3] — |
| within 解析式 | 两者 | 91.1 | 9.2% | — | — |
| within + learned | 两者 | 71.2 | 5.8% | −19.9 | [−24.9,−15.0] ❌ |
| within + ensemble 0.75 | 两者 | 88.2 | 9.2% | −3.0 | [−6.0,+0.1] — |

（within 的 known/unknown 逐位相同：within 不吃 known_draw，与 B1/B2 口径一致。）

### 诊断：σ 敏感性（负结果，排除校准假设）

假设「learned σ=11.1 相对解析式 σ=60 过小 → 过度自信」——选择段 beam only 放大 learned σ：

| 配置 | vs 解析式 | 95% CI |
|---|---:|---|
| learned σ×2 | −9.0 | [−12.9,−5.0] ❌ |
| learned σ×4 | −12.1 | [−16.0,−8.3] ❌ |
| ensemble 0.75 σ×2 | −0.8 | [−2.7,+1.2] — |
| ensemble 0.75 σ×4 | −3.0 | [−5.1,−1.0] ❌ |

**放大 σ 更差** → 不是 σ 校准问题，是 **μ 排序本身**在 B3 规则下对 beam 有害。

### 根因诊断（2026-11-23，模型回退后；探针未跟踪不提交）

用户指定回退重训模型（tracked 恢复旧版，重训候选保留 `out/b2r_leaf_mlp_small.json`），
先诊断再定方案。两个探针（`data/_probe_b2_diag.py` / `data/_probe_b2_mix.py`）：

**诊断 1：逐状态 μ vs 真实后续得分（选择段 80 局 × known/unknown 双条件）**

| 叶子 | bias mean(μ−y) | MAE | 同深度配对排序正确率（tl=1/2/3/4） |
|---|---:|---:|---|
| learned μ | **−0.2**（近无偏） | **9.2** | **0.889 / 0.853 / 0.743 / 0.678** |
| analytic μ | −28.8（系统性悲观） | 29.6 | 0.726 / 0.710 / 0.703 / 0.629 |

- **信息条件漂移假设被推翻**：y_known 56.49 ≈ y_unknown 56.66（差 −0.16，small 场景
  全知几乎没有优势）；learned μ 在两种条件下都近无偏。
- learned μ **更准、排序更好**：与 analytic 分歧的配对里 learned 对 **71.6%**。
- analytic μ 的 −28 悲观偏差来自 `playable_count` 的体力模型（「回合间不回复体力」，
  未计 B3 SKIP +2 回复/额外出牌来源）→ 低估未来可打张数。

**诊断 2：μ 来源 × σ × tiebreak 分解（选择段 80 局，beam only）**

| 配置 | 均值 | vs analytic | 95% CI |
|---|---:|---:|---|
| analytic μ + σ60（基线） | 97.3 | — | — |
| learned μ + σ11（=learned） | 90.3 | −7.0 | [−10.4,−3.6] ❌ |
| learned μ + σ60 | 95.2 | −2.0 | [−4.8,+0.7] — |
| **analytic μ + σ11** | **97.3** | **+0.0（逐位相同）** | — |
| learned μ + σ60/σ11 + tiebreak ×10/×100 | 95.2（全部逐位相同） | −2.0 | — |

**根因结论（证据支持）**：
1. **锐利 σ 放大伤害（约 5/7 分）**：learned σ≈11 把准确 μ 推进档位效用
   `Φ((μ−gap)/σ)` 的饱和/尾部区 → 决策改变；σ 换回 60 即恢复 −7.0→−2.0。
   analytic μ 对 σ 完全免疫（σ11 逐位不变）——悲观 μ 让状态都落在 sigmoid 中段。
2. **剩余 −2.0（中性）是 μ 排序本身**：tiebreak ×100 都不改决策（无平手可破），
   不是平手退化。**更准的价值 ≠ 更好的搜索引导**：标签是 teacher 完整执行的后续收益，
   而 100ms 预算的 beam 执行不出 teacher 质量的后续——价值-策略失配
   （V^teacher ≠ V^有限搜索），与 B2 历史 within 负结果同根。analytic 的「悲观启发式」
   恰好偏好稳健即得分，契合 B3 短 horizon。
3. **推论：加数据/改特征/提拟合度都救不了这条路线**——目标量本身（teacher return）
   不是有限搜索的可执行价值。要正增益需换目标（优势标签/动作排序蒸馏）或换路线
   （每战在线自适应，需真机）。**建议关闭学习叶子路线，保留负结果，beam 用解析式叶子。**
   **已验证（2026-11-23 高预算配对，用户指定）**：「提高 bot 能力能否兑现」——width8/300ms
   选择段 80 局 learned **−4.4 CI[−8.8,−0.0] 仍显著负** / ensemble 0.75 中性 → 按判定规则
   （显著正才重开）**路线关闭**，见下「高预算验证」小节。

**再下一候选方向（用户 2026-11-23 设计意图，高预算验证之后）**：
「教怎么拿更高分；学生学的不是答案，是技巧；自己摸索 70% + 老师教 30%」，
并**像扶小孩走路：老师占比逐轮渐退到 0%，学生强于老师后反过来当老师，循环几轮**——
即**专家迭代（expert iteration）/ 迭代自蒸馏 + 脚手架渐退**（AlphaZero 自对弈循环同族；
「渐退」对应 DAgger 的 β 衰减/课程学习）：
- 学「该打哪张牌 / 这张比平均好多少」（policy/advantage），标签来自**学生自己的对局**
  → 天然 on-policy，打法变了标签跟着变，**绕开价值-策略失配**（本节的根因 2）；
- 落地轮廓：student = 小策略网（复用 104 维结构化特征 → 动作排序/优势头）；
  第 1 轮数据 = 70% 学生自对弈（on-policy 优势标签）+ 30% beam 教师示范（软目标）；
  **每轮结束配对评测（同 harness、95% CI），学生 ≥ 教师才放手**：下一轮教师占比降
  （30→15→0）、教师换成上一轮学生；不达标就继续扶——**放手以评测门为准，不按轮数硬退**；
- 可行性：模拟器自对弈便宜（~0.08s/局，纯离线、无 OCR 噪声、奖励=精确终局分）；
  比例/渐退节奏是超参不是定律，要调；B2 第二轮专家迭代（全教师、仍学价值、无渐退门）
  未超第一轮，**不构成对本方案的否定**（目标量/节奏不同）；
- 风险（如实）：① 学生自对弈标签弱时 100% 自学可能平台/退化 → 必须有评测门兜底；
  ② **模拟器保真度是天花板**（fresh buff / 随机生成卡 RNG 等未建模）→ 离线增益要过
  T2 真机 A/B 才算数；③ 每轮 = 采集+训练+评测，多会话预算；
- 定位：多会话研究任务（80–150k token 级/轮），不保证正增益；**高预算验证已完成（FAIL，
  学习叶子路线关闭）——本候选是换目标量的新路线（policy/advantage，不是状态价值），
  启动前先问用户**（2026-11-23 用户：之后候选，先问我）。

### 高预算验证（width8/300ms，2026-11-23）：仍 FAIL → 学习叶子路线关闭

**背景**：根因诊断后用户问「为什么不提高 bot 能力让它打出来」——把搜索拉到 teacher 级
预算（width8/300ms，与重采数据第 3 批 teacher 同档）再配对，检验「价值-策略失配」是否
随执行力增强而消失。判定规则（用户指定）：选择段显著正 → 确认段 120 局复核再谈路线重开；
不显著 → 关闭路线、负结果写回、转 C1。

**命令**（选择段 80 局 seed 2000–2079，unknown，同预算配对；eval_b2 自动跑同预算解析式基线）：

```powershell
.venv\Scripts\python.exe scripts\eval_b2.py --leaf-model out\b2r_leaf_mlp_small.json --games 80 --seed 2000 --info unknown --width 8 --beam-budget-ms 300 --within-budget-ms 300 --ensembles 0.75 --json out\b2r_eval_highbudget_select.json
```

**结果（small 14 张 / 5 回合 / CLEAR 120 / PERFECT 170；0 fallbacks）**：

| 策略 | 均值 | P50 | CLEAR | vs 解析式 | 95% CI | 胜/平/负 |
|---|---:|---:|---:|---:|---|---|
| beam 解析式（width8/300ms） | 93.9 | 94 | 7.5% | — | — | — |
| beam + learned | 89.4 | 92 | 7.5% | **−4.4** | [−8.8,−0.0] ❌ 显著负 | 32/14/34 |
| beam + ensemble 0.75 | 93.9 | 97 | 8.8% | +0.0 | [−1.9,+2.0] — 中性 | 23/38/19 |
| within 解析式（300ms） | 89.1 | 84 | 7.5% | — | — | — |
| within + learned | 69.7 | 66 | 5.0% | −19.4 | [−25.0,−13.9] ❌ | 12/2/66 |
| within + ensemble 0.75 | 89.2 | 90 | 8.8% | +0.1 | [−3.5,+3.8] — | 17/28/35 |

**判定：FAIL**（unknown 下无任何 learned/ensemble 配置显著正）→ 按用户规则**不跑确认段，
学习叶子路线关闭**。

**三个事实（如实记录）**：

1. **伤害收窄但没转正**：learned vs 解析式 −7.0（width4/100ms）→ **−4.4**（width8/300ms），
   CI 上界 −0.03 仍 <0。与「执行力增强 → 失配减小」方向一致，但 teacher 级预算也兑现不了
   teacher return——**失配不是预算能消掉的**。
2. **收窄的主因是解析式基线自己变差，不是 learned 变好**：解析式 97.3→**93.9**（−3.4，
   CLEAR 11.2%→7.5%），learned 绝对分 90.3→**89.4**（几乎不动）。**更强的搜索对解析式叶子
   也不是免费午餐**——width8 更深地优化悲观启发式，选择段反而掉分（小场景口径；
   生产/T2 候选仍是 width4/100ms+tiebreak，本结果不改该候选，只说明「加预算」不是改进方向）。
3. **within 家族与 200ms 基线逐位相同**（89.1/69.7/89.2，CI 逐位一致）：within 搜索在
   预算内早已收敛；整个评测墙钟 <80s（远低于 15–25 分钟预估）——**small 场景 width8 搜索
   提前收敛，300ms 预算很少触顶**，预算不是小场景的约束，宽度才是。

**处置（2026-11-23，路线关闭）**：
- 生产 `leaf_model` 保持默认关闭（不变）；beam 默认 = 解析式叶子（不变）；
  T2 真机 A/B 候选不含 learned leaf（不变）。
- **学习叶子（状态价值 MLP 叶子）路线正式关闭**：B2 旧口径 +7.7 是 B3 前 3 张/回合的
  产物；B3+ 规则下重训 FAIL（−7.2）、高预算 FAIL（−4.4）、σ 校准 FAIL（×2/×4 更差）、
  根因 = 锐利 σ 放大 + 价值-策略失配（目标量本身不对）。加数据/改特征/提拟合度/加预算
  都已证伪或判定无效，**不再投入**。
- 重训候选 `out/b2r_leaf_mlp_small.json` 与本次 JSON `out/b2r_eval_highbudget_select.json`
  保留 out/（gitignore）作负结果证据；tracked 模型维持旧版（用户指定，生产关闭故行为无差）。
- **下一步转 C1 执行层可靠性**（用户指定）。再下一候选 = 渐退式专家迭代（学 policy/advantage
  而非状态价值，上节「再下一候选方向」）——**换目标量的新路线，启动前先问用户**。

### 结论与假设（如实记录）

- **事实**：拟合良好（val r²=0.906、MAE 7.0，比旧口径的 8.8 还低）但 beam 排序显著变差；
  ensemble 0.75 中性；within 显著负（与 B2 历史负结果 1 同向）。旧模型（B3 前 3 张口径数据）
  −26.1/−27.9 → 重训 −7.0/−7.2：**数据口径对齐消掉了大部分伤害，但消不掉剩余负增益**。
- **假设（2026-11-23 诊断后更新）**：原「全知 teacher return 对 unknown 执行偏乐观」假设
  **被诊断推翻**（y_known≈y_unknown）；确证根因 = 锐利 σ 放大 + 价值-策略失配
  （teacher return ≠ 有限搜索可执行价值），见下「根因诊断」。
- **处置**：生产 `leaf_model` **不打开**（默认 None 不变）；**重训模型候选保留在
  `out/b2r_leaf_mlp_small.json`（gitignore）；tracked `data/knowledge/b2_leaf_mlp_small.json`
  按用户指定回退为旧版**（2026-11-23；两版都 FAIL、旧版更差 −26~−28，生产关闭故行为无差）。
  beam 默认 = 解析式叶子；T2 真机 A/B 的候选里**去掉 learned leaf**，保留 beam+全知/tiebreak。
  ~~下一步：先诊断 μ 排序有害的根因，再定重训变量~~ **根因诊断已完成（锐利 σ 放大 +
  价值-策略失配）；高预算验证（width8/300ms）也已完成：仍 FAIL（−4.4 CI[−8.8,−0.0]）→
  学习叶子路线关闭，转 C1**（见上「高预算验证」/ HANDOVER_NEXT §8）。
- **不做（预算/已知负结果）**：第二轮专家迭代（B2 历史：未超第一轮）、档位概率头
  （B2 历史：灾难性 −42~−46）、large 场景重采（本模型是 small 5 回合分布；真机考试 9–12 回合，
  将来若再走学习叶子路线，需 large 数据 + 特征更新（熱意/score_buffs/modifier）先行）。
- **备选路线（外部情报）**：auto-gakumas 的**每战在线 PPO 自适应**是分布漂移的另一条路
  （[AUTO_GAKUMAS_NOTES §5](AUTO_GAKUMAS_NOTES.md)），需真机/独立副本，不在本会话。

### 复现命令

```powershell
# 采集（3 批顺序跑，约 2+4+2 分钟；out/ 不进 git）
.venv\Scripts\python.exe scripts\build_b2_dataset.py --games 1500 --policy beam --known --out out\b2r_leaf_beam_known.npz --seed 100000
.venv\Scripts\python.exe scripts\build_b2_dataset.py --games 3000 --policy beam --known --out out\b2r_leaf_beam_known2.npz --seed 600000
.venv\Scripts\python.exe scripts\build_b2_dataset.py --games 800 --policy beam --known --width 8 --budget-ms 300 --out out\b2r_leaf_beam_strong.npz --seed 500000
# 训练（约 40s）
.venv\Scripts\python.exe scripts\train_b2_leaf.py --data out\b2r_leaf_beam_known.npz out\b2r_leaf_beam_known2.npz out\b2r_leaf_beam_strong.npz --out out\b2r_leaf_mlp_small.json --hidden 96 48 --epochs 700 --report out\b2r_train_report.json
# 评测（选择段 → 确认段；确认段把 --seed 改 3000、--games 120、--info unknown known、--ensembles 0.75）
.venv\Scripts\python.exe scripts\eval_b2.py --leaf-model out\b2r_leaf_mlp_small.json --games 80 --seed 2000 --info unknown --ensembles 0.25 0.5 0.75 --json out\b2r_eval_select.json
# 高预算验证（2026-11-23，width8/300ms 选择段；FAIL → 路线关闭，未跑确认段）
.venv\Scripts\python.exe scripts\eval_b2.py --leaf-model out\b2r_leaf_mlp_small.json --games 80 --seed 2000 --info unknown --width 8 --beam-budget-ms 300 --within-budget-ms 300 --ensembles 0.75 --json out\b2r_eval_highbudget_select.json
```

### 测试 / 基线

- `tests/test_b2_leaf.py` **12 条**（+1 温存解除回合边界快照回归）；ruff 通过；
  全量 pytest **1155 passed / 1 skipped（1156 收集 / 79 文件）**；
  基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。
- JSON（out/ gitignore）：`b2r_eval_old_select.json`（旧模型 FAIL 复现）/ `b2r_train_report.json` /
  `b2r_eval_select.json` / `b2r_eval_confirm.json` / `b2r_eval_highbudget_select.json`
  （高预算验证 FAIL，路线关闭）。
- 细节见 HANDOVER 二·补三十四 / 二·补三十五 / HANDOVER_NEXT §8（B2-R 交接）。

## B11 渐退式专家迭代（第 1 轮，2026-11-23）：policy/advantage 学生 —— 确认段评测门 PASS

**结论先行**：B2-R 关闭学习叶子（状态价值）路线后，按用户设计意图换目标量启动
**渐退式专家迭代**（学技巧不学答案、摸索 70%+老师 30%、学生过评测门后当下一轮老师）。
第 1 轮混合学生 **v1**（70% 学生自对弈 on-policy 优势 + 30% beam 教师示范）在
**确认段 120 局（seed 3000–3119，未参与采集/训练）显著强于 beam 教师**：

| 段 | 学生 | 教师（beam width4/100ms+tiebreak） | Δ | 95% CI | 胜/平/负 | 判定 |
|---|---:|---:|---:|---|---|---|
| 选择段 80 局（2000–2079）v0 纯 BC | 97.4 | 97.3 | +0.1 | [−2.1,+2.4] | 23/34/23 | 中性 |
| 选择段 80 局 v1 混合 | 99.2 | 97.3 | +1.9 | [−0.2,+4.0] | 24/41/15 | 方向正 |
| **确认段 120 局（3000–3119）v0 纯 BC** | 97.3 | 94.9 | **+2.4** | **[+0.7,+4.1]** | 42/59/19 | **PASS** |
| **确认段 120 局 v1 混合** | **97.5** | **94.9** | **+2.6** | **[+1.1,+4.1]** | **39/59/22** | **PASS（放手）** |
| 稳健块 120 局（4000–4119，未触碰）v1 | 101.6 | 97.8 | +3.8 | [+1.6,+6.0] | 37/65/18 | PASS |

CLEAR 率：确认段 v1 11.7% vs 教师 10.8%；稳健块 17.5% vs 13.3%。教师基线 94.9/97.3
与 B2-R 逐位一致（harness 同口径）。学生推理 **0.40 ms/决策**（500 局探针，含
state_from_sim+特征+前向；教师预算 100ms/回合）——纯策略无搜索，约 250× 快。

**消融（如实记录，本轮最重要的诚实结论）**：**纯 BC v0 也过确认段门**（+2.4 CI[+0.7,+4.1]），
v1−v0 仅 +0.2（不显著）。第 1 轮增益的主力是**逐决策蒸馏 + 硬规矩禁跳**，
on-policy 优势精化尚未独立证明：

1. 示范采集是**逐决策**记录 beam 计划里的每张牌；学生每步重新 argmax，等价于
   「每个决策点都重规划的 beam」，而教师执行是「每回合规划一次、按序列执行」
   （抽牌/状态变化后计划会过期）；
2. 学生**有牌绝不 SKIP**（用户硬规矩编码进 `net_action`）；教师 beam 会提前 SKIP
   （400 局示范里 23 个「有牌却 SKIP」决策被剔除）——提前 SKIP 白丢出牌分；
3. on-policy 优势成分（70% 自对弈）方向为正（选择段 +0.1→+1.9、确认段 +2.4→+2.6、
   CLEAR 同向），但**尚未独立证明**——第 2 轮（教师←v1、占比 15%）继续检验。

**按设计放手**：评测门 = 学生−教师配对差 95% CI 下界 > 0（显著强才放手，非 inferior 不算）。
v1 过门 → **第 2 轮教师换成 v1、教师占比 30→15**（下一会话任务，启动前先问用户）。

### 设计（用户 2026-11-23 意图；轮廓见 B2-R「再下一候选方向」）

- **目标量**：学「该打哪张牌 / 这张比平均好多少」（policy/advantage），**不是状态价值**
  → 绕开 B2-R 确证的两个根因（锐利 σ 放大：学生不估 σ、不做档位概率；价值-策略失配：
  优势标签来自学生自己的延续，打法变标签跟着变）；
- **学生**：小 MLP（137 维输入 → 96 → 48 → 1 标量优势分），在**可出牌**里 argmax；
  特征 = B2 的 104 维结构化状态特征（`leaf_mlp.features`，决策态手牌按叶子口径并入
  弃牌堆聚合）+ 33 维动作特征（候选牌 23 维静态画像同源 `_card_profile` + 实际费用/
  体力上下文 + 手牌聚合 + 出牌位上下文）；
- **优势标签（on-policy，零近似）**：学生自对弈记录每个真实决策点（局面快照+合法动作+
  动作前缀）；对每张可出牌：`LessonSim(deck, config, seed)` **精确重放前缀**到达逐字段
  相同局面（`state_from_sim` 全等校验，失配抛错不静默）→ 打候选牌 → **当前学生**打完
  剩余回合 → 终局分 R(s,a)；`A = R − mean(R)`。模拟器同 seed+同动作序列完全确定，
  学生 argmax 也确定 → 每个分支是精确 on-policy 延续（分支间共享 rng 状态 = 共同随机数
  方差缩减）；**不走搜索镜像**（`sim_from_state`），无 B2-R 式快照口径坑；
- **教师示范（软目标）**：beam width4/100ms/tiebreak1e-3（unknown，B2-R 处置后的 T2
  候选档）逐决策记录；教师出的牌 +1、其余 −1/(k−1)；k=1 强制决策与教师有牌却 SKIP
  的决策剔除（学生动作空间没有「有牌 SKIP」）；
- **混合/渐退**：第 1 轮 70% 自对弈 + 30% 示范（按行数确定性下采样到精确比例）；
  每轮结束配对评测门，**过门才降教师占比（30→15→0）且教师换成上一轮学生**，
  不过门继续扶（占比不降，用新学生再采数据）；
- **硬规矩**：SKIP 只在所有牌付不起（`net_action` 编码）；推理异常直接抛出，
  无静默回退 rules。

### 实现（纯离线代码 + 单测）

- `src/gkagent/sim/policy_mlp.py`：`decision_features`（137 维）/ `PolicyMLP`
  （score/choose/save/load，格式 `gkagent.policy_mlp.v1`）/ `net_action`（硬规矩决策）/
  `train_policy_mlp`（numpy Adam 全批量 MSE，复用 `leaf_mlp._Adam`）/ `ranking_accuracy`；
- `src/gkagent/sim/policy_data.py`：`DecisionRecordingSim`（只记真实决策）/
  `replay_to` + `verify_replay`（逐字段全等）/ `advantage_samples`（分支优势）/
  `demo_samples`（软目标+剔除）/ `play_selfplay`；
- `scripts/build_ei_dataset.py`（demos/selfplay 两模式）/ `train_ei_policy.py`
  （BC/混合、seed 分组 9:1、比例下采样）/ `eval_ei.py`（配对评测门，复用
  `eval_t4_b1._table`；退出码 0=PASS/1=CONTINUE）；
- `scripts/eval_known_draw.py::play` 加 `policy="net"/"greedy"` + `net_model` 参数
  （**纯增量，默认行为逐位不变**，回归测试锁定）。

### 第 1 轮数据 / 训练（small：14 张 / 5 回合 / CLEAR 120 / PERFECT 170）

| 集 | 局数 / 决策 | 样本 | 备注 |
|---|---|---:|---|
| 教师示范（seed 100000–100399） | 400 / 1985 | 5747 | 剔除强制 37 / 教师 SKIP 23；教师均分 96.3；33s |
| v0 自对弈（seed 200000–200999） | 1000 / 4905 | 14314 | 优势 std 12.09；v0 均分 96.0；17s（含全部分支重放） |

- **v0（纯 BC）**：5747 样本，train MSE 0.093 / r² 0.816，val MSE 0.204 /
  **排序命中 0.889**（argmax 预测 = 教师选牌）；
- **v1（70/30）**：19156 样本（自对弈 13409 / 示范 5747，教师占比 0.300），
  train MSE 0.241，val MSE 0.292 / 排序命中 0.822（val 集含自对弈组，「最佳动作」
  定义 = argmax 优势，与 v0 的「教师选牌」不同靶，**不可直接比**）；
- 训练/评测 seed 纪律：采集 100000+/200000+，选择段 2000–2079，确认段 3000–3119，
  稳健块 4000–4119，互不重叠；模型/数据/JSON 全在 `out/`（gitignore）。

### 处置 / 风险（如实）

- **生产接线未做**：学生网是研究候选，`LessonPolicy`/`auto_produce` 未接；
  T2 真机 A/B 候选**暂不变**（beam+全知/tiebreak）；学生网要进 T2 需第 2 轮+
  生产接线（`engine=` 口径 + 决策可观测性 + 禁跳/禁回退红线）后再议；
- **模拟器保真度是天花板**（fresh buff / 随机生成卡 RNG 等未建模）→ 离线增益
  要过 T2 真机 A/B 才算数；本轮仅 small 场景（5 回合），large（9–12 回合真机口径）
  未测——第 2 轮起应加 large 配对；
- **v0 也过门**意味着「放手」的第 1 轮红利主要是蒸馏+禁跳，渐退 loop 的自对弈
  成分待第 2 轮独立验证；若第 2 轮（教师←v1、15%）学生不再显著强于新教师，
  按设计继续扶或如实记录平台期；
- 学生只看可观测状态（不用 known_draw/seed）→ 天然 **gkbench ranked 公平算法候选**
  （F 阶段 public-safe 适配器可复用，留待 F1/F2）；
- 优势标签是**单条确定性延续**（非采样均值）：跨 seed 体量平均吸收牌序噪声，
  第 1 轮 14314 样本未见异常；若 large 场景方差大，可加每动作多延续（改 rollout rng）。

### 复现命令

```powershell
# 采集（约 33s + 17s；out/ 不进 git）
.venv\Scripts\python.exe scripts\build_ei_dataset.py --mode demos --games 400 --out out\ei_r1_demos.npz
.venv\Scripts\python.exe scripts\train_ei_policy.py --demos out\ei_r1_demos.npz --out out\ei_r1_v0_bc.json
.venv\Scripts\python.exe scripts\build_ei_dataset.py --mode selfplay --games 1000 --student-model out\ei_r1_v0_bc.json --out out\ei_r1_selfplay.npz
.venv\Scripts\python.exe scripts\train_ei_policy.py --selfplay out\ei_r1_selfplay.npz --demos out\ei_r1_demos.npz --teacher-frac 0.3 --out out\ei_r1_v1_mix.json
# 评测（选择段 → 确认段 → 稳健块；退出码 0=PASS）
.venv\Scripts\python.exe scripts\eval_ei.py --net-model out\ei_r1_v1_mix.json --games 80 --seed 2000 --json out\ei_r1_eval_v1_select.json
.venv\Scripts\python.exe scripts\eval_ei.py --net-model out\ei_r1_v1_mix.json --games 120 --seed 3000 --json out\ei_r1_eval_v1_confirm.json
.venv\Scripts\python.exe scripts\eval_ei.py --net-model out\ei_r1_v1_mix.json --games 120 --seed 4000 --no-within --json out\ei_r1_eval_v1_robust4000.json
```

### 测试 / 基线

- `tests/test_ei_policy.py` **28 条**（特征维度/确定性/牌间区分、save/load、argmax、
  合成可训练、**硬规矩禁跳**、决策记录、**重放逐字段等价+失配抛错**、优势均值 0、
  **on-policy 分支终局分=原局终局分**、rollout 敏感性、示范软目标/剔除、
  harness net/greedy 接线、**默认行为逐位不变**）；ruff 通过；
- 全量 pytest **1251 passed / 1 skipped（1252 收集 / 84 文件，190.62s）**；
  基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变；
- JSON（out/ gitignore）：`ei_r1_eval_v0_select/v1_select/v0_confirm/v1_confirm/v1_robust4000.json`；
- 细节见 HANDOVER 二·补三十七 / WORKPLAN B11 / HANDOVER_NEXT §8（B11 交接）。

## B11 渐退式专家迭代（第 2 轮，2026-11-23）：教师←v1、占比 15%、large 首测 —— 平台期（CONTINUE）

**结论先行**：第 1 轮 PASS 后按设计放手——第 2 轮教师换成 v1 学生网、教师占比 30→15、
自对弈用 v1 采新数据，并**首次加 large 场景（31 张 / 9 回合真机口径）配对**。结果：

1. **small 评测门 CONTINUE（平台期）**：确认段 120 局 v2 97.9 vs v1 97.5，
   Δ=+0.4 CI[−0.4,+1.2] 不显著；选择/稳健 4000/**新鲜块 5000（两轮均未触碰）**四段全中性
   （|Δ|≤0.4，CI 全含 0；确认段 98/120 局逐位相同）。**按设计教师占比不降（保持 0.15）**，
   渐退节奏是超参不是定律——如实记录平台期；
2. **on-policy 成分仍未独立证明**：消融 v2_mix − v2_bc（纯 v1 示范自蒸馏）= +0.54
   CI[−0.40,+1.48]，方向正但不显著（与第 1 轮 v1−v0=+0.2 同向）；纯自蒸馏 v2_bc − v1 =
   −0.13 CI[−0.87,+0.60] 中性（克隆自己≈自己，符合预期）；
3. **large 首测 = 泛化缺口（本轮最重要的新信息）**：small 训练的学生到 large 显著弱于 beam——
   v1 −28.1 CI[−36.0,−20.2]（确认段 277.2 vs 305.3，CLEAR 36.7% vs 53.3%）；
   **v2 比 v1 还略差**（选择段 −14.8 CI[−21.3,−8.3] 显著；确认段 −6.5 CI[−13.2,+0.3]）。
   两学生仍显著强于 greedy（+58~+65）→ 学到的技巧真实，但 9 回合长 horizon 的天花板是
   beam 的跨回合规划；**large 要进生产要么用 beam（现 T2 候选），要么采 large 数据训练**；
4. **绝对水位保持**：v2 − beam（small 确认段）= +2.99 CI[+1.37,+4.62]；
   v1 − beam = +2.58 CI[+1.07,+4.10] 与第 1 轮**逐位一致**（beam 参照臂 94.9/97.3/97.8
   三个段全部逐位复现 → small beam 提前收敛、不受机器负载影响，数字可比）。

**处置**：生产接线未做（T2 候选暂不变：beam+全知/tiebreak）；v1 仍是 small 最佳学生；
下一轮候选（继续扶 / 采 large 训练数据 / 收 loop 于 v1 转 T7/D1/E0/E）**先问用户**。

### 第 2 轮代码（纯增量，默认行为逐位不变）

- `build_ei_dataset.py --teacher-net <model>`（demos 模式）：教师=学生网，走 `net_action`
  逐决策记录（硬规矩禁跳 → 「教师有牌却 SKIP」剔除恒 0），软目标同口径（+1/−1/(k−1)）；
  selfplay 模式拒收（`parser.error`）；meta 记 `teacher_kind`；
- `eval_ei.py --baseline-net <model>`：评测门基线=上一轮学生（`teacher_net` 臂），
  beam 臂保留作绝对水位参照；缺省基线=beam（第 1 轮口径不变）；verdict 记
  `baseline/baseline_model/beam_mean`；
- `train_ei_policy.py --round N`：meta.task 轮次（默认 1，第 1 轮输出不变）；
- large 场景无需新代码（`--scenario large` 第 1 轮已支持，本轮首次用于配对）。

### 第 2 轮数据 / 训练（small；seed 纪律：示范 400000–400399 / 自对弈 300000–300999，与 r1 错开）

| 集 | 局数 / 决策 | 样本 | 备注 |
|---|---|---:|---|
| v1 教师示范（`--teacher-net`） | 400 / 1981 | 5773 | 剔除强制 40 / 教师 SKIP **0**（硬规矩）；教师均分 98.1；2.1s |
| v1 自对弈优势 | 1000 / 4946 | 14526 | std 12.00；v1 均分 98.0；37.3s（含全部分支重放） |

- **v2（85/15）**：17089 样本（自对弈 14526 / 示范 2563，教师占比**精确 0.150**），
  train MSE 0.196 / r² 0.788，val MSE 0.254 / 排序命中 0.818（1721 样本 / 140 seeds）；
- **v2_bc（消融，纯 v1 示范自蒸馏）**：5773 样本，val MSE 0.137 / 排序命中 0.933
  （靶=v1 选牌，克隆保真度高；与 v2 的 val 靶不同不可直接比）。

### 评测（B1 修正 harness 配对，unknown，`--no-within`；门基线 = v1）

**small（14 张 / 5 回合）**：

| 段 | v2 | v1（门基线） | Δ | 95% CI | 胜/平/负 | beam 参照 |
|---|---:|---:|---:|---|---|---:|
| 选择 80 局（2000–2079） | 99.2 | 99.2 | −0.0 | [−0.9,+0.9] | 5/64/11 | 97.3 |
| **确认 120 局（3000–3119）** | 97.9 | 97.5 | **+0.4** | **[−0.4,+1.2]** | 11/98/11 | 94.9 |
| 稳健 120 局（4000–4119） | 101.3 | 101.6 | −0.2 | [−0.8,+0.3] | 8/101/11 | 97.8 |
| 新鲜块 120 局（5000–5119，两轮未触碰） | 97.5 | 97.6 | −0.1 | [−1.2,+1.1] | 13/93/14 | 96.3 |

CLEAR 确认段：v2 10.0% / v1 11.7% / beam 10.8%（均值微升、CLEAR 微降，噪声级）。
消融（确认段配对）：v2_bc 97.4（−0.1 vs v1，CI[−0.9,+0.6]）；
**v2_mix − v2_bc = +0.54 CI[−0.40,+1.48]**（on-policy 成分，13/96/11）；
v2 − beam = +2.99 CI[+1.37,+4.62]（41/56/23）。

**large（31 张 / 9 回合 / 体力 60 / CLEAR 300 / PERFECT 450，首测）**：

| 段 | v2 | v1 | Δ(v2−v1) | 95% CI | beam | greedy |
|---|---:|---:|---:|---|---:|---:|
| 选择 80 局（2000–2079） | 266.6 | 281.4 | **−14.8** | **[−21.3,−8.3]** | 302.5 | 219.9 |
| 确认 120 局（3000–3119） | 270.8 | 277.2 | −6.5 | [−13.2,+0.3] | 305.3 | 212.4 |

CLEAR：选择段 v2 23.8% / v1 35.0% / beam 46.2%；确认段 v2 26.7% / v1 36.7% / beam 53.3%。
v1 − beam（确认段）= **−28.1 CI[−36.0,−20.2]**（94/1/25 beam 胜）——small 蒸馏红利
（逐决策重评估+禁跳）在 large 不足以补上跨回合规划差距；v2 的 small 平台期训练还轻微
损害了 large 泛化。large beam 臂虽在游戏负载下测得，**另跑复核逐位复现**
（305.3/277.2/270.8，`ei_r2_eval_v2_large_confirm_recheck.json`）→ 数字稳定可比；
net-vs-net 两臂确定性、不受负载影响，门判定有效。

### 处置 / 风险（如实）

- **平台期**：两轮下来红利主力仍是第 1 轮的「逐决策蒸馏+禁跳」，on-policy 精化连续两轮
  方向正但不显著。继续扶的边际收益存疑——下一轮若做，建议换变量（large 训练数据 /
  更大学生网 / 多延续优势标签）而不是同配方再采一遍；
- **确认段复用风险**：3000–3119 与 4000–4119 两轮都用于评测（协议内），新鲜块 5000–5119
  本轮首次使用、同样中性 → 平台期结论不是段选择伪影；
- **large 泛化缺口**：学生只看可观测状态、特征含 turns_left/体力等，但 5 回合训练分布
  覆盖不了 9 回合的长 horizon 信用分配；gkbench hif 本戦是 9–12 回合口径 → **学生网要进
  F 阶段 public-safe 候选，必须先过 large 训练/评测**；
- 生产接线未做、T2 候选不变；模拟器保真度天花板与真机验收口径同第 1 轮；
- 模型/数据/JSON 全在 `out/`（gitignore）：`ei_r2_demos.npz` / `ei_r2_selfplay.npz` /
  `ei_r2_v2_mix.json` / `ei_r2_v2_bc.json` / `ei_r2_eval_v2_select/confirm/robust4000/fresh5000/`
  `large_select/large_confirm/large_confirm_recheck.json` / `ei_r2_eval_v2bc_confirm.json`。

### 复现命令

```powershell
# 采集（约 2s + 37s；out/ 不进 git）
.venv\Scripts\python.exe scripts\build_ei_dataset.py --mode demos --teacher-net out\ei_r1_v1_mix.json --games 400 --seed 400000 --out out\ei_r2_demos.npz
.venv\Scripts\python.exe scripts\build_ei_dataset.py --mode selfplay --student-model out\ei_r1_v1_mix.json --games 1000 --seed 300000 --out out\ei_r2_selfplay.npz
# 训练（v2 混合 + v2_bc 消融）
.venv\Scripts\python.exe scripts\train_ei_policy.py --selfplay out\ei_r2_selfplay.npz --demos out\ei_r2_demos.npz --teacher-frac 0.15 --round 2 --out out\ei_r2_v2_mix.json
.venv\Scripts\python.exe scripts\train_ei_policy.py --demos out\ei_r2_demos.npz --round 2 --out out\ei_r2_v2_bc.json
# 评测（门基线=v1；退出码 0=PASS/1=CONTINUE）
.venv\Scripts\python.exe scripts\eval_ei.py --net-model out\ei_r2_v2_mix.json --baseline-net out\ei_r1_v1_mix.json --games 120 --seed 3000 --no-within --json out\ei_r2_eval_v2_confirm.json
.venv\Scripts\python.exe scripts\eval_ei.py --net-model out\ei_r2_v2_mix.json --baseline-net out\ei_r1_v1_mix.json --scenario large --games 120 --seed 3000 --no-within --json out\ei_r2_eval_v2_large_confirm.json
```

### 测试 / 基线

- `tests/test_ei_policy_r2.py` **15 条**（teacher-net 示范软目标/确定性/selfplay 拒收/
  峰值=net 选牌/beam 默认路径不变；baseline-net 门/默认仍 beam/同模型自比逐位中性；
  0.15 精确占比/round meta/默认 round1 不变；large 牌组配置/net 确定性/重放优势/
  eval 与 selfplay CLI 冒烟）；ruff 通过；
- 全量 pytest **1266 passed / 1 skipped（1267 收集 / 85 文件）**；
  基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 复跑全部不变；
- 环境备注：本轮全量 pytest 首跑曾遇 `test_drink_search_latency_stays_bounded` 失败
  （11.8–12.4ms > 10ms）——证实为机器游戏负载（TslGame）所致的墙钟抖动（同搜索 5 轮
  6.6–12.1ms 随负载波动；同 HEAD 19:0x 基线全绿；代码改动不碰搜索），负载回落后复跑全绿，
  **未改测试门槛**；
- 细节见 HANDOVER 二·补三十九 / WORKPLAN B11 / HANDOVER_NEXT §8（B11 第 2 轮交接）。

## B11 第 2 轮续（r3–r8 继续扶 + 门协议修正，2026-11-23）：v6 过门（显著强于 v1）

**结论先行**：r2 平台期后用户指令「继续迭代直到学生显著强于老师（v1）」。r3–r8 六轮
继续扶（教师始终 v1@0.15），依次换变量：**新学生数据 / 数据×10 / epochs×3 / 容量×2 /
ε-greedy 探索（两个体量）**。结果：

1. **确认段 3000–3119（120 局）七轮全是最弱 draw**（+0.2~+0.6，从未单独显著）；
   稳健段 4000 同样低（+0.2~+0.4）；选择段 2000 恒 +0.9；**未触碰块 6000 恒
   +1.3~+1.7 显著**。差异由**种子段**决定（该段 v1 还可改进的状态多少），不由模型决定；
2. 数据量（14.5k→171k）、训练量（400→1200 epochs）、容量（96×48→192×96）、探索
   （ε=0.15，44k/146k）**全部试过，val 排序饱和 0.860–0.862，确认段不动**——当前目标量
   在确认段种子上的天花板已至；
3. **整体显著**：v6 池化 820 局（select 80 + confirm500 + robust 120 + fresh6000 120）
   **+0.71 CI[+0.40,+1.02]，W/T/L 101/678/41**；
4. **门协议修正（用户批准）**：120 局门为 r1 检测 +2.6 设计，对 +0.5 效应检验力 ~50%。
   确认段扩到 **500 局（3000–3499）、判据不变（CI 下界>0）**：**v6 98.6 vs v1 98.1，
   Δ=+0.6 CI[+0.2,+0.9] → PASS**（W/L 62/27）；独立佐证 fresh6000 **+1.7 CI[+0.6,+2.8]
   PASS**。**v6 显著强于教师 v1，任务达成**。

### 迭代总表（门基线始终 v1；small；unknown；--no-within）

| 轮 | 学生 | 变量 | 样本 | val 排序 | 确认 3000（120 局） | 新鲜块 |
|---|---|---|---:|---:|---|---|
| r2 | v2 | 基线（v1 自对弈 300000+） | 17089 | 0.818 | +0.4 [−0.4,+1.2] | — |
| r3 | v3 | 新学生数据（v2 自对弈 500000+） | 17160 | 0.827 | +0.2 [−0.3,+0.7] | — |
| r4 | v4 | 数据×5（v3 自对弈 600000+，5000 局） | 85582 | 0.843 | +0.6 [−0.0,+1.2] | — |
| r5 | v5 | 数据×10（v4 自对弈 700000+，10000 局） | 171300 | 0.860 | +0.4 [−0.2,+1.0] | 6000: +1.5 PASS |
| r6 | **v6** | 容量×2（192×96）+ epochs 1200 | 171300 | 0.861 | +0.5 [−0.1,+1.0] | 6000: **+1.7 PASS** |
| r7 | v7 | ε-greedy 0.15（v6 自对弈 800000+，3000 局） | 51516 | 0.849 | +0.3 [−0.3,+0.8] | 7000: +0.6 |
| r8 | v8 | ε-greedy 0.15 匹配体量（810000+，10000 局） | 171988 | 0.862 | +0.2 [−0.5,+0.9] | 6000: +1.3 PASS |

r4 起补采 v1 示范 2000 局（seed 410000–411999，28934 样本）解锁 0.15 占比下的自对弈
上限（示范行数不足时训练脚本会下采样自对弈到 max_s = n_d×(1−f)/f）。探索采集均分
90.6–90.8（ε=0.15 牺牲 ~9 分），标签仍 on-policy 有效；探索变量中性（v8≈v5）。

### v6 最终评测（过门证据）

| 段 | v6 | v1 | Δ | 95% CI | 胜/平/负 | 判定 |
|---|---:|---:|---:|---|---|---|
| **确认 500 局（3000–3499，门）** | **98.6** | **98.1** | **+0.6** | **[+0.2,+0.9]** | 62/411/27 | **PASS** |
| 新鲜块 120 局（6000–6119） | 101.1 | 99.4 | +1.7 | [+0.6,+2.8] | 18/97/5 | PASS（佐证） |
| 选择 80 局（2000–2079） | 100.1 | 99.2 | +0.9 | [−0.2,+2.0] | 10/66/4 | 方向正 |
| 稳健 120 局（4000–4119） | 101.7 | 101.6 | +0.2 | [−0.4,+0.8] | 11/104/5 | 中性 |
| **池化 820 局** | — | — | **+0.71** | **[+0.40,+1.02]** | 101/678/41 | **显著** |

vs beam 绝对水位：确认 500 局 98.6 vs 96.5（+2.1）；确认 120 局 98.0 vs 94.9（+3.1）。
CLEAR 确认 500 局 12.2% vs 11.4%。v6 = 192→96 MLP、1200 epochs、171300 样本
（v4 argmax 自对弈 145605 / v1 示范 25695，占比 0.150）。

**large（31 张 / 9 回合，确认段 120 局）**：v6 **291.6** / v1 277.2 / beam 305.3 /
greedy 212.4；**v6 − v1 = +14.4 CI[+6.5,+22.2] PASS**（CLEAR 45.0% vs 36.7%）；
v6 − beam = −13.7（v1 − beam = −28.1，缺口收窄一半）。数据量+容量显著改善 large
泛化（r2 的 v2 在 large 比 v1 还差 → v6 反转）；large 生产候选仍是 beam。

### 设计变量结论（如实）

- **ε-greedy 探索采集**（r7/r8 新代码，`play_selfplay explore_eps` / `--explore-eps`）：
  假设「argmax 路径覆盖不足」被**否证**——匹配体量下 v8≈v5，确认段不动。平台期主因
  不是覆盖，是确认段种子上 v1 已近天花板；
- **数据/容量/训练量**：val 排序 0.818→0.862 后饱和；剩余误差是单延续标签噪声 +
  种子段结构，加量不转化成分数；
- **门协议**：120 局确认门对 <1.0 效应检验力不足（r1 为 +2.6 设计）。**后续轮次门
  改为 500 局（3000–3499）或多段池化**；单段 120 局只作快速筛查。这是本轮最重要的
  方法论修正；
- **种子段结构**：确认/稳健段恒低、选择/新鲜块恒高，跨 7 个模型一致 → 评测段选择
  本身引入 ±1 分的系统噪声；报告必须多段 + 池化，单段数字不可尽信。

### 处置 / 下一步

- **v6 = 当前最佳学生**（显著强于 v1，门 PASS + 新鲜块佐证）；按设计下一轮可
  教师←v6、占比 15→0——**但用户任务「显著强于老师」已达成，是否继续降档先问用户**；
- **生产接线仍未做**（过门后才谈：engine= 口径 + 可观测性 + 禁跳/禁回退红线）；
  T2 候选暂不变（beam+全知/tiebreak）；
- **large 泛化显著改善但仍低于 beam**：v6 large 确认段 **291.6 vs v1 277.2：
  +14.4 CI[+6.5,+22.2] PASS**（CLEAR 45.0% vs 36.7%；`ei_r6_eval_v6_large_confirm.json`）——
  数据量+容量对 large 泛化有效（r2 的 v2 在 large 比 v1 还差，v6 反转）；
  但 vs beam 305.3 仍差 −13.7（v1 是 −28.1，缺口收窄一半）。**large 生产候选仍是 beam**；
  v6 进 F 阶段 public-safe 前建议补 large 训练数据进一步收窄；
- 模型/数据/JSON 全在 out/（gitignore）：`ei_r3_selfplay.npz` / `ei_r4_selfplay.npz` /
  `ei_r4_demos.npz` / `ei_r5_selfplay.npz` / `ei_r7_selfplay.npz` / `ei_r8_selfplay.npz` /
  `ei_r3_v3_mix.json` … `ei_r8_v8_mix.json` / 各轮 eval JSON（含 `ei_r6_eval_v6_confirm500.json`）。

### 复现命令（v6 过门路径）

```powershell
# r4：补采 v1 示范 + v3 自对弈 5000 局
.venv\Scripts\python.exe scripts\build_ei_dataset.py --mode demos --teacher-net out\ei_r1_v1_mix.json --games 2000 --seed 410000 --out out\ei_r4_demos.npz
.venv\Scripts\python.exe scripts\build_ei_dataset.py --mode selfplay --student-model out\ei_r3_v3_mix.json --games 5000 --seed 600000 --out out\ei_r4_selfplay.npz
.venv\Scripts\python.exe scripts\train_ei_policy.py --selfplay out\ei_r4_selfplay.npz --demos out\ei_r4_demos.npz --teacher-frac 0.15 --round 4 --epochs 800 --out out\ei_r4_v4_mix.json
# r5：v4 自对弈 10000 局
.venv\Scripts\python.exe scripts\build_ei_dataset.py --mode selfplay --student-model out\ei_r4_v4_mix.json --games 10000 --seed 700000 --out out\ei_r5_selfplay.npz
.venv\Scripts\python.exe scripts\train_ei_policy.py --selfplay out\ei_r5_selfplay.npz --demos out\ei_r4_demos.npz --teacher-frac 0.15 --round 5 --epochs 800 --out out\ei_r5_v5_mix.json
# r6：容量×2 + 1200 epochs（同 r5 数据）
.venv\Scripts\python.exe scripts\train_ei_policy.py --selfplay out\ei_r5_selfplay.npz --demos out\ei_r4_demos.npz --teacher-frac 0.15 --round 6 --epochs 1200 --hidden 192 96 --out out\ei_r6_v6_mix.json
# 门（500 局修正协议）+ 新鲜块佐证
.venv\Scripts\python.exe scripts\eval_ei.py --net-model out\ei_r6_v6_mix.json --baseline-net out\ei_r1_v1_mix.json --games 500 --seed 3000 --no-within --json out\ei_r6_eval_v6_confirm500.json
.venv\Scripts\python.exe scripts\eval_ei.py --net-model out\ei_r6_v6_mix.json --baseline-net out\ei_r1_v1_mix.json --games 120 --seed 6000 --no-within --json out\ei_r6_eval_v6_fresh6000.json
```

### 测试 / 基线

- `tests/test_ei_explore.py` **7 条**（ε=0 逐位不变 / ε>0 确定性+真的探索 / 硬规矩禁跳 /
  参数校验 / 探索局优势仍 on-policy / CLI selfplay 接线 / demos 拒收）；ruff 通过；
- 全量 pytest **1273 passed / 1 skipped（1274 收集 / 86 文件）**；基线 ①③④⑤ 不变；
- 细节见 HANDOVER 二·补四十 / WORKPLAN B11 / HANDOVER_NEXT §8。

## B11 v6 生产接线（2026-11-23）：engine=net（opt-in，默认逐位不变）

**结论先行**：v6 过门（显著强于 v1）后，把学生网接进生产引擎口径，让 T2 真机 A/B
能带上第四臂。**纯增量**：默认引擎不变（bot 入口 expectimax / `LessonPolicy` rules），
`net_model` 默认 None，其它引擎完全不读它；`engine="net"` 显式打开才走学生网。

### 口径

- **引擎**：`LessonPolicy(engine="net", net_model=<policy_mlp JSON 路径>)`；
  `_ALLOWED_VALUES["engine"]` 增加 `net`；`_decide_search` 分发到 `_try_net`。
- **决策**：`_search_state(state, with_plan=False)` 构造可观测 `ExpectState` →
  `legal_cards`（指針修正后实际牌费付得起 + 有出牌次数，去重）→ `model.score`
  argmax 优势分 → `_search_action` 映射回原手牌坐标。**无搜索、无叶子、无饮料动作**。
- **可观测状态（public-safe）**：`with_plan=False` 不注入采集全知字段——挂了激活的
  `ExamDrawPlan` 也不给 net 喂 `known_draw/deck/discard`（与 B11「学生只看可观测状态」
  定位一致，F 阶段 public-safe 适配器可复用同口径）。expectimax/beam 的全知注入逐位不变
  （`with_plan` 默认 True，回归测试锁定）。
- **硬规矩**：有可出牌绝不 SKIP（argmax 只在可出牌里）；所有牌付不起 → SKIP
  （`allow_skip=True`）/ wait（考试 `allow_skip=False`）；`decide()` 的 SKIP 拦截照常兜底。
- **禁回退红线**：模型缺失/文件损坏/格式不符/推理异常/结果不在手牌 →
  `RuleFallbackBlocked`（真机入口记 `[engine][BLOCKED]` 中止本局），**绝不静默回退 rules**；
  状态没读全（手牌空/体力未知/回合未知）→ wait 等下一帧。与 B2 `leaf_model`（叠加层，
  坏了退解析式叶子）不同：net 是引擎本身，坏了就停。`allow_rule_fallback=True` 调试开关
  沿用旧约定（真机入口永远不传）。
- **可观测性**：`last_decision["engine"]="net"`，`decision_note()` 打 `eng=net`；
  动作 reason 带 `net: <牌名>（优势 <分>，<k> 候选，<ms>ms）`，`expected`=优势分。

### 真机入口（auto_produce）

- `allowed_engines` 增加 `net`；模型路径优先级：`--net-model` CLI >
  `policy.json` 的 `produce.net_model` > **默认入库 v6**（`data/knowledge/ei_policy_v6.json`）。
- 缺模型在**起跑前**大声报错 return 2（不带空模型进局再 BLOCKED）；相对路径按 ROOT 解析。
- 日志首行 `[engine] 出牌引擎 = net（来源：…）` + `[engine] net 模型 = <路径>（来源：…）`。
- 用法：`auto_produce.py 300 ep-ab-net --engine net --ignore-user --max-minutes 30`
  （`--net-model out\ei_r8_v8_mix.json` 可换其它轮次做 A/B）。

### 入库模型

- `data/knowledge/ei_policy_v6.json`（tracked，≈1.0MB）= `out/ei_r6_v6_mix.json` 逐权重拷贝，
  meta 补 `production` 溯源（gate：confirm500 v6 98.6 vs v1 98.1 +0.6 CI[+0.2,+0.9] PASS；
  fresh6000 +1.7；pooled820 +0.71；large −13.7 vs beam）。B2 叶子模型入库同惯例
  （`b2_leaf_mlp_small.json`）；研究产物仍在 out/（gitignore）。
- `PolicyMLP.load` 校验格式/动作特征名/状态维（137）/隐层（192×96），不符直接抛错。

### 如实记录的口径差 / 风险

- **生产 deck/discard 未知**：`_search_state` 不带牌库/弃牌堆（读屏拿不到），104 维状态
  特征里的 deck/discard 聚合段按空集进特征（0）；离线评测 `net_action` 走 `state_from_sim`
  是**全牌库**分布。这是生产与离线的特征分布差，T2 真机 A/B 才算数（模拟器保真度是天花板）。
- **large 仍低于 beam**（v6 −13.7）：large 生产候选仍是 beam；net 进 F public-safe 前
  建议补 large 训练数据（下一候选之一）。
- 学生网每决策 ~0.4ms（r1 探针口径），无搜索预算参数；推理异常不重试、直接 BLOCKED。

### 测试 / 基线

- `tests/test_ei_wiring.py` **21 条**（引擎开关/默认不变、argmax 优势选牌、只选付得起、
  全付不起才 SKIP/考试 wait、全零网有牌绝不 SKIP、确定性、状态没读全 wait、
  缺模型/坏模型/推理异常/CardSpec 失配 → BLOCKED、调试回退开关、rules/expectimax
  不读 net_model、**net 无视 draw_plan + expectimax 全知注入回归**、入库 v6 load+真模型
  走生产链路、auto_produce 静态接线）；ruff 通过；
- 全量 pytest **1294 passed / 1 skipped（1295 收集 / 87 文件，202.95s）**；
  基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155 全部不变；
- 细节见 HANDOVER 二·补四十一 / WORKPLAN B11 / HANDOVER_NEXT §8。



