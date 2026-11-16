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

### 近似

- `AnalyticLeafValue`：解析未训练 V_leaf。`μ = n·集中 + 好印象年金 + 均值牌面×n`
  （n 用体力/费用模型封顶），`σ=60`；CLEAR/PERFECT 用 `math.erf` 正态 CDF。
- `ExamLessonBuffDependParameterBuff`（好调数值依赖审查基准加成，缺 parameter buff
  状态）：按**至少 1 回合好调**记——不虚构跨回合收益，但避免把真 buff 牌当空白牌。
- `LessonSim` 原有近似（延迟效果时机、检索/生成/移动→抽 1、附魔展开等）不改变；
  见 `sim/lesson.py` 模块 docstring。

### 未建模（接口/状态就位，等数据）

- **P 道具**：`LessonConfig.p_items` 默认空；`LessonSim.p_items` 只保存。仓库已有
  `sim/p_items.py` 的被动效果纯函数与数据表，但课程 `step()` 尚未接入自动触发；
  expectimax 也不把 P 道具计分。**未编造数值**。
- 考试对手/追击/干扰、饮料槽获得流程、强化后数值等：沿用原模拟器缺口。
- 真机 OCR 读不到 buff 层数/牌库/总回合数：`LessonPolicy` 的 expectimax 模式用
  已知手牌/体力/剩余回合/分数/CLEAR 构造状态；牌库空、buff 默认 0，异常退回 rules。
- 饮料已进状态，但 `expectimax` 的动作仍只有 play/SKIP；真机饮料仍走现有
  `use_drink` 流程（不占出牌次数，`drinks_per_turn=None` 时按仓库最新口径不限瓶数）。

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

`tests/test_expectimax.py`（27 条）+ `tests/test_mechanism_corrections.py`（11 条）：

- 背包（10 vs 3+6=9）、元气抵费、集中先手（18 > 16）、阈值风险（A=+5 vs B=30%+100/70%-20）、
  空放 buff、可复现、可行性、再动 6/5 体力、再动不吃体力截断、抽牌+再动；
- 动作敏感、机会节点 32 种牌序 ≥28 后继、超几何 P(A)=0.4/P(B)=0.6、状态转换与
  `LessonSim` 对齐；
- buff vs 再动、盾 vs 大牌、体力不足 SKIP；
- 除外/牌库、buff 剩余回合/总回合/饮料、P 道具接口、beam 投资线/deadline/可复现；
- 机制核对：饮料不占出牌次数、CLEAR/PERFECT 连续收益、好印象下回合开始扣层、
  やる気/元气分离、考试分数名次、训练体力、休息 70%、考试回合、指針代价、支援加成
  （见 §2.1 / §2.2）。

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
