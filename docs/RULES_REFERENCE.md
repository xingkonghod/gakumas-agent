# 规则核验表（对照 gakumas-tools 参考引擎 / 官方 wiki / 真机采集）

> 2026-11-22 B3（T5 机制建模）重写。原名「参考引擎的规则（对照我们的模拟器）」，
> 现在改成**逐条核验表**：每一行给出「参考实现或真机证据 → 我们的实现 → 状态 → 回归」。
>
> 状态口径：**✅** 已对齐且有回归；**⚠️** 近似建模（误差方向写清）；**❌** 未建模/有差距。
>
> 核验来源：
>
> - **参考引擎**：`surisuririsu/gakumas-tools`（**BSD-3**，本地 `data/dl/gt/gakumas-tools-master`）。
>   关键文件：`packages/gakumas-engine/engine/Executor/resolvers.js`（分数结算）、
>   `engine/TurnManager.js`（回合 / 出牌次数 / 跳过回体力 / 抽牌）、
>   `engine/CardManager/index.js`（出牌、可用性、抽牌上限 5、打完最后一张自动结束回合）、
>   `engine/BuffManager.js`（buff 衰减、fresh 保护）、`typeMultipliers.js`（审查倍率）；
>   常量在 `engine/constants.js`（`GOOD_IMPRESSION_EFFECTS` / `STANCE_CHANGED_EFFECTS` /
>   `FULL_POWER_EFFECTS`）。它的 `tests/training-fidelity.md` / `tests/contest-fidelity.md`
>   记录**逐次真机截图回放**核对过的黄金值（本表引用的「实机回放值」都出自那里）。
> - **官方 wiki 公式**：见 [WIKI_DUAL_SOURCE.md](WIKI_DUAL_SOURCE.md)（好调 `1.5+0.1×回合`、
>   训练收益、评价点公式）。
> - **真机采集**：2026-11-20/21 四场考试 39 回合逐回合日志（牌序见
>   `scripts/verify_shuffle.py`；回合规则摘要见 `tests/fixtures/t5_exam_turn_rules.json`）。
>
> B3 的「配对回归」素材：`tests/test_sim_lesson.py` 里的实机回放黄金值
> （250% 回合 アピールの基本 9→23/好调 35、愛嬌 13+好调→50、情熱ターン 11→28/35/43；
> 课程好调 10→15、5→8、2→3；温存 9→5、2→1、15→8）+
> `tests/test_t5_turn_rules.py`（39 回合出牌数规则）。
>
> **官方规则版本口径（2026-11-22 F0 校准，见 [GKBENCH.md §4.5](GKBENCH.md)）**：gkbench 官方
> `check.rules=55`（GKMS 原生引擎 `exam_rules_version`，配对 commit `f4d9e6e6148d`）是开发种子的
> 起点快照；官方榜上 run 现在跨 **rules 55/59/65** 三档。**我们的实现不跟随原生版本号**，
> 只按本表逐条对齐「机制」；F1 用官方种子做同题同种子复算时，起点状态用 `check`（turn/score/stamina），
> 并注明对比的 rules 版本。

## 0. 一句话结论（B3 + T5① 后）

分数结算顺序、好调/指針/メタモルフォーゼ/不调、**取整**、**每回合 1 张牌**、
**跳过回 2 体力**、牌序（洗牌 / 支援强化 / 重洗 / 回合属性）、**审查倍率（分段 + 联动惩罚）**
都已按参考引擎/客户端语义/真机对齐；剩余差距是 **熱意（enthusiasm）** 与
**温存解除的额外次数/元气**、**P 道具/附魔**、**fresh buff 的差一回合衰减**、
**依赖分结算顺序**（我们保守口径）等。

---

## 1. 回合规则（B3 2026-11-22 对齐）

| 规则 | 参考实现 / 真机证据 | 我们的实现 | 状态 | 回归 |
|---|---|---|---|---|
| 每回合基础出牌 **1 张** | `TurnManager.startTurn`: `cardUsesRemaining = 1`；真机 39 回合：32 回合 1 张、7 回合 2 张，每回合手牌都 3 张 | `LessonConfig.plays_per_turn=1`、`ExpectState.play_limit=1`、`DEFAULT_PLAY_LIMIT=1` | ✅ | `tests/test_t5_turn_rules.py::test_*default*` + 真机 fixture |
| 打完最后一张**自动结束回合** | `CardManager.useCard` 末尾 `cardUsesRemaining < 1 → endTurn` | `LessonSim.step`：次数用尽或手牌空 → `_end_turn`；搜索侧 `plays_left<=0` 即按 `end_turn_state` 叶子处理 | ✅ | `test_one_card_auto_ends_turn_without_stamina_recovery` |
| SKIP/没出完牌 → 体力 **+2**（封顶最大体力） | `TurnManager.endTurn`: `if (cardUsesRemaining > 0) stamina = min(stamina+2, max)` | `LessonSim._end_turn` / `end_turn_state`：`plays_this_turn < 上限` 时 +2 | ✅ | `test_skip_recovers_two_stamina_capped_at_max`、`test_skip_recovery_matches_expect_state_rule` |
| 额外出牌 = 使用次数 +N | `ExamPlayableValueAdd` 效果（卡 / P 道具）加 `cardUsesRemaining`；真机 7 个 2 张回合里 3 个首张牌带该效果 | `CardSpec.extra_play` → `LessonSim.extra_plays` / `ExpectState.extra_plays` | ✅ 卡效果；⚠️ P 道具数据未接入 | `test_extra_play_keeps_turn_open_then_auto_ends`、fixture |
| 每回合开始抽 3 张（手牌 3） | `TurnManager.startTurn`: `cardsToDraw = max(3 - handDecrease, 0)` | `LessonConfig.hand_size=3`，每回合 `_draw_hand` | ✅（handDecrease 未建模 ⚠️） | `test_sim_lesson.py` 各回合测试 |
| 抽牌/手牌**上限 5** | `CardManager.drawCard`: `if handCards.length >= 5 return` | `LessonSim._draw` 不设上限 | ⚠️ 只有抽牌卡溢出时才不同 | — |
| 温存解除：熱意 +5/+8、元气 +5（2 段）、**+1 次出牌** | `constants.js STANCE_CHANGED_EFFECTS`；实机回放「leaving 温存 grants 5 熱意 and an extra use」 | 只把熱意近似成「好调回合 = 温存期间打出数+1」，不加额外次数/元气 | ❌ 待补（T5） | `test_save_release_gives_heat_turns`（旧近似） |
| 全力回合：+1 次出牌、保留牌回手 | `constants.js FULL_POWER_EFFECTS` / `FULL_POWER_CHANGED_EFFECTS` | 只建模全力 ×3 分数与全力值消耗 | ⚠️ 额外次数/保留牌未建模 | `test_full_power_point_triggers_triple_next_turn` |
| 饮料不占出牌次数 | 真机 UI/用户确认 | `use_drink` 不动 `plays_this_turn` | ✅ | `test_mechanism_corrections.py::test_drinking_does_not_consume_play_slots` |
| `turnSkipped` 是独立触发时机（P 道具） | `PHASES` 含 `turnSkipped`；master 里 12 个 turn_skip P 道具 | P 道具接口只触发 turn_start/turn_end/card_play/status_gain | ⚠️ 跳过类 P 道具未触发 | — |

## 2. 出牌结算顺序（`resolvers.js::resolveScore`，BSD-3）

参考顺序（原文逻辑）：

```
① growth（成长）加成
② if score > 0:
   a. score += 集中 × 集中倍率 × 集中效果加成
   b. score += 熱意 × 熱意倍率
   c. ceil
   d. 好调：score *= 1 + (0.5 + (绝好调 ? 好调回合数×0.1 : 0)) × 好调倍率
   e. 指針：強気1 ×2 / 強気2 ×2.5 / 温存1 ×0.5 / 温存2 ×0.25 / 全力 ×3 / 余裕 ×0
   f. score *= 1 + 分数增益之和（含自尊 min(好印象,やる気)×0.02 上限 0.5；メタモルフォーゼ披露 +0.25）
   g. score *= max(分数减益之和, 0)（メタモルフォーゼ支度基础 0.75）
   h. 不调：score *= 0.67
   i. ceil
③ score *= 回合属性倍率（考试/舞台 typeMultiplier）
④ ceil
```

| 项 | 参考实现 / 真机证据 | 我们 | 状态 | 回归 |
|---|---|---|---|---|
| 集中加在白值上（乘之前） | `resolveScore` a；实机 250% 情熱ターン 集中 0/3/6 → 28/35/43 | `_card_award`: `(base + focus) × …` | ✅ | `test_audition_multiplier_matches_captured_real_machine_scores` |
| やる気（motivation）→ **元气获得量** | `resolveGenki`: `genki += motivation × multiplier`；实机回放 やる気 放大元气 | `motivation` 字段：获得元气时 `vitality += value + motivation` | ✅ | `test_mechanism_corrections.py::test_motivation_and_vitality_are_separate_and_persist` |
| 熱意（enthusiasm）→ **本牌分数加算** | `resolveScore` b：`score += enthusiasm × multiplier`；温存解除给 5/8 熱意 | 没有独立熱意资源；温存解除近似成好调回合 | ❌ 待补（会高估/低估分数，方向不定） | — |
| 好调倍率 `1+(0.5+绝好调0.1×g)×倍率` | `resolveScore` d；wiki `1.5+0.1×好调回合`（绝好调） | `Buffs.condition_turns/perfect_condition_turns` 同式 | ✅ | `test_lesson_rules_reference.py` |
| 指針倍率（0.5/0.25/2/2.5/3） | `resolveScore` e；实机回放 強気 9→18、温存 9→5/15→8 | `sim/stance.py MULTIPLIER` | ✅ | `test_preservation_card_halves_later_scores`、实机黄金值 |
| 指針牌费（温存减半/強気双倍/強気2 穿透 1） | `resolveCost`（费用是负数，`floor(-cost×m)` = 绝对值向上取整） | `_effective_cost` 用 `ceil(cost×m)`（同语义） | ✅ | `test_mechanism_corrections.py::test_stance_cost_modifiers_and_strong_pierce` |
| 分数增益/减益（scoreBuffs/scoreDebuffs） | `resolveScore` f/g；实机回放「審査基準 +1500‰ = ×1.5」 | `parameter_buff` 千分比近似（乘在最终分上，`int()`） | ⚠️ 语义近似（卡表把它映射成好调/审查基准两种口径） | `test_parameter_buff_*` |
| 自尊 pride `min(好印象,やる気)×0.02` 上限 +0.5 | `resolveScore` f | 未建模 | ❌ 影响小（需要 prideTurns 来源） | — |
| メタモルフォーゼ：披露 +25% / 支度 ×0.75 | `resolveScore` f/g；实机回放 100→ceil(125)、100→ceil(75) | `Buffs.metamorphosis` | ✅ 分数；❌ 支度→披露半场翻转未做 | `test_lesson_rules_reference.py` |
| 不调 ×0.67 | `resolveScore` h | `Buffs.poor_condition_turns` | ✅ | `test_poor_condition_multiplies_by_0_67`（40×0.67→27） |
| **取整时机**：加算后 ceil、buff 段后 ceil、回合倍率后 ceil | `resolveScore` c/i/④ 的 `safeCeil`（整数附近取整、否则 ceil）；实机回放 9→23、5→8、2→3 | `safe_ceil`（B3 补）：buff 段一次 + 回合倍率一次 | ✅ | 实机回放黄金值 6 条（课程）+ 6 条（考试） |
| 回合属性倍率（审查倍率） | 客户端：按 3 维参数在**分数表分段折线**插值（`ProduceExamBattleScoreConfig`）→ 低于 `ProduceExamBattleConfig` 审查基准时按 `GetPenaltyPermil` 罚分（`Setting` 100~250‰）→ `common=1000−Σpenalties` **三项共乘（联动惩罚）** → `1000+component×common/1000` 归一化到 10；每回合按属性取倍率，`ceil(f32(f32(bonus/1000)×amount)−1e-4)` | `sim/exam_multiplier.py`（纯公式）+ `data/exam_bonus.py`（主数据解析）+ `LessonConfig.attribute_bonuses`/`turn_attributes`；生产侧读屏幕「舞蹈 207%」直接喂 `ExpectState.attribute_coefficient`；旧常量 4.11 仅作无读数时的历史默认 | ✅ 公式/主数据对齐（2026-11-22 T5①）；真机逐分回放还差 P 道具附魔/生成卡等未建模项 | `tests/test_exam_multiplier.py` 21 条 + `tests/fixtures/t5_exam_multipliers.json`（11-20 采集局期中 4.09/2.20/2.60×、期末 6.97/2.85/4.96×）+ 真机帧「舞蹈 207%」→2.07 |
| 依赖分（好印象/元气/全力值折算）是否吃倍率 | 参考引擎里 `score+=goodImpressionTurns*…` 也是普通 `score+=`，**会吃**好调/指針/回合倍率 | 旧路径保守不吃；**T5① 考试真实倍率路径已把依赖分并进属性倍率**（出牌分先加依赖段、乘 buff/审查基准、最后乘属性倍率）；单标量路径保持旧行为 | ⚠️ 两条路径口径不同（生产读屏走标量路径仍保守；模拟器真实倍率路径已对） | `test_dependent_scores_ignore_attribute_coefficient`（旧路径）+ `test_sim_applies_per_turn_attribute_bonus`（新路径） |
| 单精度舍入（JS double vs Python float） | 两边都是 IEEE-754 double；参考 `safeCeil` 有 1e-9 epsilon；属性倍率乘用**单精度**（`CalcCurrentTurnBattleBonus`） | `safe_ceil` 同实现；`exam_multiplier.f32`/`battle_bonus_score` 用 struct 模拟 f32 | ✅ | 实机黄金值 + `test_battle_bonus_score_matches_client_rounding` |
| growth（成长表） | `resolveScore` ① 用 growth 表的**加算**（g.score 等） | `grow_score` 是卡面百分比乘白值；数据为空 → 恒 0 | ❌ 数据缺口（`ProduceCardGrowEffect` 未下载） | — |

## 3. Buff 生命周期 / 好印象年金 W(r,T)

| 项 | 参考实现 / 真机证据 | 我们 | 状态 | 回归 |
|---|---|---|---|---|
| 好印象：回合末 `score += 层数 × 强化倍率` | `GOOD_IMPRESSION_EFFECTS`：`score += goodImpressionTurns × buff`；回合末触发 | `_end_turn`：`score += int(层数 × (1000+review_multiple)/1000)` | ✅ | `test_exam_review_scores_at_turn_end_then_decays` |
| 好印象回合推进 -1 | `BuffManager.decrementBuffTurns`（`EOT_DECREMENT_FIELDS` 含 goodImpressionTurns） | 下一回合开始时 -1（最低 0） | ✅ | `test_depend_exam_review_*` |
| 年金 `W(r,T) = r+(r-1)+…` | 上述逐回合结算的闭式；解析叶子用它估未来分 | `AnalyticLeafValue.impression_annuity` | ✅（与参考同语义） | `tests/test_expectimax.py` 相关用例 |
| 好调/绝好调/不调回合数衰减 | `EOT_DECREMENT_FIELDS` | `_end_turn` / `end_turn_state` 各 -1 | ✅ | `test_new_condition_buffs_tick_down_at_turn_end_in_both_engines` |
| **fresh buff 保护**：获得 buff 的当回合末不扣 1（回合末从 0→正 的字段打 fresh 标记跳过衰减） | `Executor/index.js` L271-279「Protect fresh stats from decrement」+ `BuffManager.decrementBuffTurns` | 我们的 buff 当回合末就 -1（**少 1 回合持续**） | ❌/⚠️ 未真机核实；参考引擎的 fidelity 截图常省略回合末 buff 数 | 待真机逐回合截图验证（T6） |
| 好印象强化 / 好调加算 / 全力强化 持续回合 | `ExamReviewMultiple` / `ExamParameterBuffAdditiveFix` / `ExamFullPowerLessonMultipleAdditive` | `Buffs.review_multiple` 等 + `_tick_buff_turns` | ✅ | `test_review_multiple_*`、`test_condition_additive_*` |
| メタモルフォーゼ 支度→披露（半场自动翻转） | `TurnManager.endTurn`: `turnsElapsed >= floor(turnCount/2)` | 只有外部设置的 `Buffs.metamorphosis`，不自动翻转 | ❌ 小（需要偶像特性数据） | — |
| 饮料（体力/集中/好调/直接分） | 参考引擎 `p_drinks.csv`；实机每回合 1 瓶（用户确认无上限） | `LessonSim.use_drink`：4 种效果，不占出牌次数 | ✅ 已建模的 4 种；⚠️ 其余 20+ 种效果报错不静默 | `test_drink_*` |
| P 道具（被动，按触发时机） | `p_items.csv` + 参考引擎 `PItems`；exam_start/turn_start/card_play/turn_skip 等 | `sim/p_items.py` 接口 + `LessonSim._fire_p_items`；但卡表/读屏没有真实 P 道具数据 → 培育模拟默认空 | ⚠️ 接口有、数据未接（T5/T6） | `tests/test_p_items_integration.py` |

## 4. 考试 / 牌序机制（已真机验证）

| 项 | 参考/真机证据 | 我们 | 状态 | 回归 |
|---|---|---|---|---|
| 洗牌 = xorshift32 + Fisher-Yates（含支援强化掷点） | gakumas `NativeRandom`；真机 4 场逐张对照 | `sim/exam_shuffle.py`（`NativeRandom`/`shuffle`/`opening_deck_and_rng`） | ✅ 4/4 场（期中 18/18、期末 26/26、PRO 期中 15/15、PRO 期末 27/27） | `scripts/verify_shuffle.py` |
| 洗牌前消耗 K = `(配置回合数−3) + npc数×回合数` | 4 场反推（offset 0 复现回合属性池） | `k_before_shuffle` | ✅ | 同上 |
| 回合属性：首回合分布 + 末 3 回合静态各一 + 中间洗 | 4 场回合属性序列 | `generate_turn_types` / `infer_turn_type_pool` | ✅ | 同上 |
| 支援强化：掷点次数 / 成功次数 / 每回合强化增量 | 4 场：掷点 45/46/29/46、成功 0/6/1/6，逐回合增量对照 | `support_upgrade` | ✅ | 同上 |
| 弃牌堆重洗（回合内/回合开始） | 三组重洗样本 9/9、6/6、9/9 逐张对照 | `reshuffle_grave` + `ExamDrawPlan` | ✅ 3/3 | `verify_shuffle.py` 汇总；`verify_exam_wiring.py` |
| 牌序全知接线（`ExamSetup`→`known_draw`/`discard_order`） | 生产端到端 | `build_exam_setup` + `ExamDrawPlan` | ✅ 4/4 场、初始段 86/86、重洗 24/24、手牌 36/36、known_draw 29/29、beam 出牌 28 次 | `scripts/verify_exam_wiring.py` |
| 额外 RNG 机制卡（panic/search/generate/move） | 群论文/官方 AI 笔记；未知额外 RNG 会让 K 偏 | `exam_risk.py`：牌组命中即**事前停用全知**（不静默错算） | ✅ 检测（169/1829 机制卡，四场牌组 0 命中）；❌ 建模 | `tests/test_exam_risk.py` |
| 考试内生成/移动卡（grave 不可重建） | 真机 2 场出现生成卡 | 全知验证按数据限制提前停（不算失败）；模拟里近似成抽 1 张 | ⚠️ 近似（低估生成卡价值） | `verify_exam_wiring.py` 汇总 |
| hand_limit（手牌上限 5） | 采集 `hand_limit=5` | `LessonSim.hand_size` 固定 3；考试 setup 不驱动抽牌上限 | ⚠️ 只在抽牌卡时不同 | — |

## 5. B3 实际改动（2026-11-22）

| 改动 | 文件 | 证据 | 回归 |
|---|---|---|---|
| 模拟器默认每回合 **1 张**（旧 3 张是"手牌 3 张"误读） | `sim/lesson.py`、`sim/expectimax.py`、`sim/play_choice.py`、`sim/uiobs.py`、`sim/v_leaf.py`、`scripts/local_bench.py` | gakumas-tools `TurnManager` + 真机 39 回合 | `test_t5_turn_rules.py`（9 条） |
| 打完最后一张**自动结束回合** | `sim/lesson.py::step` | `CardManager.useCard` 末尾 | 同上 + 旧机制测试改显式口径 |
| 回合末**跳过回 2 体力**（封顶） | `sim/lesson.py::_end_turn`、`sim/expectimax.py::end_turn_state` | `TurnManager.endTurn` | 同上 |
| **取整对齐**：buff 段 ceil + 回合倍率段 ceil（旧：课程 floor / 考试结尾 round 一次） | `safe_ceil`（`sim/lesson.py`）+ `sim/expectimax.py` 镜像 | `resolvers.js::safeCeil` + 实机回放黄金值 | 实机黄金值 12 条 |
| 重标定（规则改变后） | 见下 | — | — |

**重标定数字（B3 后口径，勿与 B3 前数字混用）**：

- `sim_engine_ab.py` 整局 A/B（16+30+30=76 局，训练+考试都注入真 `LessonPolicy`）：
  **0 RuleFallbackBlocked / 0 异常 / C+ 率 100%**；expectimax 现在**显著优于 rules**：
  seed 9000（16 局）评价点 P50 5170→5566、Δmean +372；seed 21000（30 局）5176→5505、Δmean +342；
  seed 30000（30 局）5152→5513、Δmean +429（B3 前是噪声内 −15/−5）。
- B1 配对评测（60 局，small）：within **89.1** → beam **95.7**（+6.6，CI [+2.2,+11.1] unknown /
  +6.6 [+3.1,+10.1] known）；决策门 107.4% PASS（B3 前：143.1→164.0/165.5，+20.9/+22.4）。
- B2 学习叶子（B3 前训练的数据，未重训）：数字见 HANDOVER 二·补二十一 / EXPECTIMAX「B2」的
  B3 重测表；**结论以重测为准，重训留到 T5 数据修正后**。
- `tests/test_sim_produce.py` 400 局标定带：三维总和均值 650–1100 → **950–1450**（≈1198），
  原因是 1 张/回合 + 跳过回体力让 16 周能打更多训练；这是口径变化，不是真机吻合度提升。

### 5.1 T5 ① 审查倍率分段 + 联动惩罚（2026-11-22 完成）

| 改动 | 文件 | 证据 | 回归 |
|---|---|---|---|
| **分段折线 + 联动惩罚 + 客户端取整**的纯公式 | [sim/exam_multiplier.py](../src/gkagent/sim/exam_multiplier.py) | 原生客户端语义：分段表插值 → 低审查基准罚分 → `common = 1000−Σpenalties` 三项共乘 → `1000 + component×common/1000` 归一化；出牌/好印象 `ceil(f32(f32(bonus/1000)×amount) − f32(1e-4))`（hiro vendor `gakumas_produce/attributes.py` 从其客户端反编译还原；gakumas-tools `typeMultipliers.js` 同结构） | `tests/test_exam_multiplier.py`（分段/惩罚/归一化/取整 golden） |
| **主数据解析**：偶像卡 → 考试配置 → 分数表 | [data/exam_bonus.py](../src/gkagent/data/exam_bonus.py) | `IdolCard.produceStepAuditionDifficultyId` → `ProduceStepAuditionDifficulty`（produceId+stepType）→ `ProduceExamBattleConfig`（turn/审查基准/分数表 id）→ `ProduceExamBattleScoreConfig`（节点表）+ `Setting` 惩罚上下限（100/250） | 夹具 + `test_resolver_*`（主数据可用时） |
| **真机配对夹具**（11-20 采集局期中/期末） | [scripts/export_exam_multipliers.py](../scripts/export_exam_multipliers.py) → [tests/fixtures/t5_exam_multipliers.json](../tests/fixtures/t5_exam_multipliers.json) | 采集三维 Vo373/Da218/Vi187（期中）→ **4.09/2.20/2.60×**（Vi 187<基准 192 罚 103‰，common 897 把三项一起压低＝联动惩罚）；期末 Vo842/Da350/Vi629 → **6.97/2.85/4.96×**（Vo/Da 两项不达标） | `test_captured_exam_*` |
| **模拟器按回合属性乘**（出牌分 + 回合末好印象） | [sim/lesson.py](../src/gkagent/sim/lesson.py) `LessonConfig.attribute_bonuses` + `turn_attributes` | 出牌分含好印象/元气/全力值依赖分一起乘（参考引擎里依赖分也是普通 `score +=`）；回合末好印象合成 `ExamLesson` 结算同样吃倍率；不配这两项时行为逐位不变 | `test_sim_applies_per_turn_attribute_bonus` 等 6 条 |
| **生产接线：屏幕倍率进搜索** | [policy/lesson.py](../src/gkagent/policy/lesson.py) `audition_coefficient` + `_search_state` | 真机考试顶部「舞蹈 207%」是真实本回合倍率（原生公式算出来的值）→ `ExpectState.attribute_coefficient=2.07`；日志 `decision_note` 变 `eng=… attr=2.07 …` | 真机帧 `exam_card_overlay_20261115.png` 回放：OCR 读数 207 → 2.07；`test_audition_coefficient_*` |

**口径与剩余差距（如实记录）**：
- 旧常量 `AUDITION_ATTRIBUTE_COEFFICIENT=4.11` 是 C+/5577 反推的**平均值**；真实考试三项倍率不同
  （本次采集：Vo 4.09 / Da 2.20 / Vi 2.60），且**低于审查基准会联动压低三项**，固定 4.11 换账号/参数
  不足时会偏很多。
- 主数据缺 2026-11-21 新偶像卡 `i_card-hkne-3-000` → 该场只能靠屏幕倍率（生产侧本来就只读屏幕）；
  夹具把它记进 `skipped`，不猜配置。
- **真机逐分回放仍差几项**：P 道具考试开始附魔（如 hmsz-3-018 的 `enchant-...-336-0` 好印象触发）、
  `ExamStatusEnchant` 附魔触发、考试内生成卡、`ExamReviewMultiple`「次数」语义（我们按千分比）。
  这轮只保证**倍率本身**与客户端公式/主数据一致，逐分回放等这些机制补齐后再锁。

## 6. 最该补的差距（按对真机分数影响排序，留给 T5/T6）

1. ~~**审查倍率分段 + 联动惩罚**~~ ✅ **2026-11-22 完成**（§5.1：公式 + 主数据 + 屏幕倍率生产接线；
   剩余差距只在 P 道具/附魔等未建模项，倍率本身已对齐）。
2. **熱意（enthusiasm）**：需要独立资源字段（分数加算 + 来源：温存解除 +5/+8、其它卡）。
3. **温存解除的额外出牌次数/元气**：异常（アノマリー）方案核心机制。
4. **fresh buff 保护**（差一回合）：好调/好印象/绝好调持续时间可能整体少 1 回合，需真机逐回合截图核实。
5. **P 道具数据接入**（produce 侧 P 道具列表未采集；`p_items.json` 有 1068 条效果模板）。
6. **考试内生成卡/额外 RNG 机制**（现有数据不够，T6 补采）。
7. **好印象/元气依赖分是否吃倍率**：参考引擎说明会吃；模拟器真实倍率路径（T5①）已按「吃」实现，
   生产读屏走单标量路径时仍保守（两条路径口径不同，见 §2 表）。逐分实机核对等 P 道具/附魔补齐。
8. **抽牌上限 5 / handDecrease / 保留牌（held cards）**。
9. **自尊 pride / growth 成长表 / 支度→披露半场翻转**（小项）。

## 7. 复现

```powershell
# 四条基线（洗牌 / pytest / 考试牌序 / 生产接线）
.venv\Scripts\python.exe scripts\verify_shuffle.py
.venv\Scripts\python.exe -m pytest tests/ --basetemp=data\pytest-tmp
.venv\Scripts\python.exe scripts\build_exam_setup.py
.venv\Scripts\python.exe scripts\verify_exam_wiring.py

# B3 新素材/规则回归
.venv\Scripts\python.exe scripts\export_t5_turn_rules.py   # 从采集 traffic 重导回合规则 fixture
.venv\Scripts\python.exe -m pytest tests\test_t5_turn_rules.py -q

# B3 重标定
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800
.venv\Scripts\python.exe scripts\eval_t4_b1.py --games 60
.venv\Scripts\python.exe scripts\eval_b2.py --leaf-model data\knowledge\b2_leaf_mlp_small.json --games 120 --seed 3000

# T5① 审查倍率（公式 + 主数据夹具 + 真机帧屏幕倍率）
.venv\Scripts\python.exe scripts\export_exam_multipliers.py          # 从采集+主数据重导夹具
.venv\Scripts\python.exe scripts\export_exam_multipliers.py --check  # 只校验夹具没漂
.venv\Scripts\python.exe -m pytest tests\test_exam_multiplier.py -q
```

## 许可

`gakumas-tools` 是 **BSD-3-Clause**：本表引用的公式/常量与实机回放值需保留版权声明；
我们只引用口径并重写实现，不拷贝代码。

T5① 的「分段折线 + 联动惩罚 + `normalize_bonus`/`battle_bonus_score` 算术语义」参考了
`hiro-gakumas-hero`（AGPL-3.0，`data/hiro/` 仅本地参考）里 `vendor/.../gakumas_produce/
attributes.py` 从其客户端反编译还原的实现；我们**按语义重写**（`src/gkagent/sim/exam_multiplier.py`），
没有把 AGPL 代码拷进本项目。主数据（`ProduceExamBattleConfig` 等）来自社区 gakumasu-diff 快照，
夹具只保存计算结果的回归快照（见 `tests/fixtures/t5_exam_multipliers.json` 的 `source` 字段）。
