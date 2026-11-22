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
- P 道具：6 个时机（turn_start/card_played/card_play/status_gain/turn_end/
  card_play_interval）在 `LessonSim` 与 `ExpectState` 都触发；未实现类型 no-op。
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
| P 道具（全部 1764 spec，upper bound）P50 | 5096 | 11270 | **+6174** |
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
