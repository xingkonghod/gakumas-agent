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

## 0. 一句话结论（B3 + T5① + T5② + T5④ + P1-1 + P1-2 + P1-3 + P1-4 后）

分数结算顺序、好调/指針/メタモルフォーゼ/不调、**取整**、**每回合 1 张牌**、
**跳过回 2 体力**、牌序（洗牌 / 支援强化 / 重洗 / 回合属性）、**审查倍率（分段 + 联动惩罚）**、
**熱意（enthusiasm）与温存/のんびり解除**（熱意 +5/+8/+10、固定元気 +5、解除当回合 +1 出牌次数、
熱意算分/获得取整/回合末清零与延長、本牌熱意適用倍数）、**全力回合 +1 出牌/保留牌回手**、
**のんびり指針**（分数/费用 ×0、解除收益、预约来源、全力/のんびり指針守卫）
都已按参考引擎/客户端语义/真机对齐；**P 道具**已接数据管线（gkbench loadout，catalog 1115 件）
并实现两批**条件/效果语义**（B8：新语法 trigger id 结构化解析、依赖换算「X 的 N% 数值变为 Y」、
固定/百分比体力消耗与回复、新触发时机；B9：**持续倍率 / modifier 类**——打分上升量增加/减少
（`resolveScore` f/g）、好印象强化/追加发动、热意/集中/好印象/干劲/全力值增益倍率、绝好调/不调、
费用削减/追加/减少回合/增加回合、回合追加、温存/强气指針直给；B10：**生成卡确定式 +
指定卡名/手牌张数映射**——card_meta（idol_unique/effectGroupIds）+ play_filter/zone_count
结构化 + ExamCardCreateId 落牌；**P1-1 のんびり直给** stance_leisure；**P1-2 handDecrease
抽牌修正 + pride 自尊**——`cardsToDraw=max(3−handDecrease,0)`、`resolveScore` f 的
min(好印象,やる気)×0.02 上限+0.5，来源主数据+参考 DSL 交叉；**P1-3 hold 保留区建模 +
指針固定**——holdThisCard/holdSelected/moveHeldCardsToHand 卡效果（上限 2、跨回合保留、
超限最旧进弃牌堆、全力回手 LIFO）+ lockStanceTurns（EOT 递减 + fresh 保护锁下一回合 +
setStance 守卫 + 全力进入门）+ hold 区张数条件（countCards[held]）+ 温存 2 段階直给；
**P1-4 nullifyDebuff 低下状态无效拦截**——消耗式计数器（无回合倒计时）拦截
setScoreDebuff/setHandDecrease 施加（P 道具侧 ExamAntiDebuff count 11 段；卡侧 4 SSR 族
values 恒空延迟）；**⑦ ExamBuffConsumptionAdd / countDebuffs 评估保持 no-op**（卡模型不承载
buff 花费 / 低下状態の数参考+主数据零使用，无落点）；
数据层 **1067/1849 段**（P1-4 +11 ExamAntiDebuff；P1-3 触发未知 **3→0 件**清零），
见 §5.3 B8/B9/B10 / §5.4 P1-1 / §5.5 P1-2 / §5.6 P1-3 / §5.7 P1-4）。
剩余差距是 **随机生成卡**（H.I.F应援棒，考试 RNG 流未知）、**强化状态花费卡类**
（`ExamBuffConsumptionAdd` 的落点——我们的卡牌模型不建「以强化状态为花费」的卡，
88 张参考 buff-cost 卡 card_table cost=0、CardSpec 无 buff_cost 字段，P1-4 评估保持 no-op）、
**保留区卡成长 target:held**（g.scoreTimes/g.score/g.cost，新的舞台+/发挥本领/
实现的觉悟 等）与 **holdCard P 道具来源**（那一天的塑料伞/章鱼烧科幻小狗/彼此许下的约定，
效果文本未结构化）、**card_play_interval_after 触发时机**（2 件のんびり道具因此仍保守不触发）、
**附魔**、**fresh buff 的差一回合衰减**（lockStanceTurns 已按参考 fresh 实现，其余 buff 仍缺）、
**依赖分结算顺序**（我们保守口径）等。

---

## 1. 回合规则（B3 2026-11-22 对齐）

| 规则 | 参考实现 / 真机证据 | 我们的实现 | 状态 | 回归 |
|---|---|---|---|---|
| 每回合基础出牌 **1 张** | `TurnManager.startTurn`: `cardUsesRemaining = 1`；真机 39 回合：32 回合 1 张、7 回合 2 张，每回合手牌都 3 张 | `LessonConfig.plays_per_turn=1`、`ExpectState.play_limit=1`、`DEFAULT_PLAY_LIMIT=1` | ✅ | `tests/test_t5_turn_rules.py::test_*default*` + 真机 fixture |
| 打完最后一张**自动结束回合** | `CardManager.useCard` 末尾 `cardUsesRemaining < 1 → endTurn` | `LessonSim.step`：次数用尽或手牌空 → `_end_turn`；搜索侧 `plays_left<=0` 即按 `end_turn_state` 叶子处理 | ✅ | `test_one_card_auto_ends_turn_without_stamina_recovery` |
| SKIP/没出完牌 → 体力 **+2**（封顶最大体力） | `TurnManager.endTurn`: `if (cardUsesRemaining > 0) stamina = min(stamina+2, max)` | `LessonSim._end_turn` / `end_turn_state`：`plays_this_turn < 上限` 时 +2 | ✅ | `test_skip_recovers_two_stamina_capped_at_max`、`test_skip_recovery_matches_expect_state_rule` |
| 额外出牌 = 使用次数 +N | `ExamPlayableValueAdd` 效果（卡 / P 道具）加 `cardUsesRemaining`；真机 7 个 2 张回合里 3 个首张牌带该效果 | `CardSpec.extra_play` → `LessonSim.extra_plays` / `ExpectState.extra_plays`；T5③ 起 P 道具同效果（`PItemDelta.extra_plays`，考试开始/回合开始/出牌后都会加，见 §5.3） | ✅ 卡效果 + P 道具（仅 loadout 能拿到的数据；真机培育侧列表待补采） | `test_extra_play_keeps_turn_open_then_auto_ends`、`test_exam_start_extra_play_keeps_first_turn_open`、fixture |
| 每回合开始抽 3 张（手牌 3），**handDecrease 抽牌修正** | `TurnManager.startTurn`: `cardsToDraw = max(3 - handDecrease, 0)`；`BuffManager.setHandDecrease(amount, turns?)` / `getHandDecrease`（handDecreases 列表按 turns 分组加算、回合末倒计时）；wiki buffs.json「手札減少」合算 ≥3 抽 0、只影响回合开始抽牌 | `LessonConfig.hand_size=3`；**P1-2（2026-11-24）**：`LessonSim.hand_decreases` / `ExpectState.hand_decreases`（timed 列表，-1 永久）+ `_draw_hand` / `turn_draw_count` / beam 下一手 / `sim_from_state` 补手牌同口径 `max(hand_size−Σ,0)`；来源 `ExamGimmickStartTurnCardDrawDown`（塔 gimmick 12 段，exam_start）；卡效果抽牌不受影响 | ✅（nullifyDebuff 拦截 P1-4 已建模，见 §5.7） | `test_sim_lesson.py` 各回合测试 + `tests/test_p12_hand_decrease_pride.py` |
| 抽牌/手牌**上限 5** | `CardManager.drawCard`: `if handCards.length >= 5 return` | `LessonSim._draw` 不设上限 | ⚠️ 只有抽牌卡溢出时才不同 | — |
| 温存解除：熱意 +5/+8、元气 +5（2 段）、**+1 次出牌** | `constants.js STANCE_CHANGED_EFFECTS`；实机回放「leaving 温存 grants 5 熱意 and an extra use」 | T5②（2026-11-22）按参考引擎实现：熱意独立资源 +5/+8、2 段**固定元気 +5**（不吃やる気）、解除当回合 **+1 出牌次数**；回合末熱意清零（有熱意延長则保留）；同回合重复解除可叠加；**温存→のんびり不触发**（`stance!=leisure` 条件，P1-1 补） | ✅ | `tests/test_t5_enthusiasm.py`（纯规则 + LessonSim）+ `tests/test_p1_stance_rules.py` |
| 全力回合：+1 次出牌、保留牌回手 | `constants.js FULL_POWER_EFFECTS` / `FULL_POWER_CHANGED_EFFECTS`；`TurnManager.startTurn` 抽牌后触发；contest-fidelity 美鈴回放「全力回合三张牌」「held スパート used in the 全力 turn」 | **P1-1（2026-11-24）**：以全力开始的回合 `extra_plays += 1`（连续全力每回合都有）+ `held` 全部回手（`_move_held_to_hand`，无手牌上限检查同参考）；全力值 ≥10 消耗 10 进全力（超出保留）口径不变；**全力期间禁切指針**（`stance_change_allowed`，setStance 守卫）；**P1-3**：保留区来源接通（holdThisCard/holdSelected，逐卡证据表）+ 回手 **LIFO**（参考 `pop()`）+ **指針固定期间全力进入门不满足**（`lockStanceTurns==0`，全力值不消耗） | ✅ 额外次数/回手/守卫/来源/固定门 | `test_full_power_turn_grants_extra_play` / `test_full_power_moves_held_cards_to_hand` / `test_p13_hold_zone.py::test_full_power_returns_held_lifo_real_card` / `test_lock_blocks_full_entry_next_turn_fresh` |
| **hold 保留区**（P1-3）：上限 2、超限最旧进弃牌堆、跨回合保留、holdThisCard 不进弃牌/除外 | `CardManager.hold/enforceHoldLimit/holdThisCard/holdSelectedByTarget/moveHeldCardsToHand`（:959-1102）+ `useCard` thisCardHeld（:639）+ `TurnManager.endTurn` 只弃手牌 | **P1-3（2026-11-24）**：`LessonSim.held` / `ExpectState.held`（P1-1 已有字段，来源接通）；`hold.HOLD_SOURCES` 13 族卡证据表（BSD-3 skill_cards.csv 逐卡交叉）；holdThisCard（温存条件）/holdSelected（hand/deck/deck_grave，白值分降序确定性选牌）/moveHeldCardsToHand 卡效果；`_enforce_hold_limit`；known_draw/discard_order 同步；表外 ExamCardMove 卡保留旧 +1 抽牌近似 | ✅ 已建模 13 族；⚠️ 表外（全力值消耗/holdSelectedUpto/target:held 成长/干扰卡计数）保留近似 | `tests/test_p13_hold_zone.py`（纯规则/LessonSim/双镜/解析） |
| **指針固定 lockStanceTurns**（P1-3）：>0 禁切指針 + 全力进入门不满足；回合末 -1（fresh 保护锁下一回合） | `constants.js` EOT_DECREMENT_FIELDS / FULL_POWER_EFFECTS（`lockStanceTurns==0` 门）；`BuffManager.setStance`（:262）/ `decrementBuffTurns`（freshBuffs 位）；`Executor/index.js`（:271-279 fresh 保护）；skill_cards.csv 424/425 切磋琢磨 `lockStanceTurns+=1` | **P1-3（2026-11-24）**：`LessonSim.lock_stance_turns` / `ExpectState.lock_stance_turns`（+fresh 标记）；`StanceLock` turn=N 卡效果（切磋琢磨）；`stance_change_allowed(locked=…)` / `end_turn(locked=…)` 守卫；fresh 保护按参考实现（获得当回合末不扣——「锁下一回合」是卡面确定语义） | ✅（一般 buff 的 fresh 差一回合缺口仍留真机核实，见 §3） | `test_lock_stance_gain_real_card` / `test_lock_blocks_stance_change_mid_turn` / `test_lock_blocks_full_entry_next_turn_fresh` / `test_lock_expires_after_next_turn` / `test_lock_does_not_block_full_exit` |
| のんびり（leisure）指針：分数/费用 ×0；解除 固定元気+5 / +1 次出牌 / 熱意+10（→全力时改为**全体卡打分成长+10**）；温存→のんびり不触发温存解除；のんびり期间禁切温存 | `constants.js STANCE_CHANGED_EFFECTS`（:57-68）；`resolveScore`/`resolveCost` leisure ×0；`BuffManager.setStance`（:264）；contest-fidelity 美鈴回放「のんびり zero cost/zero score、leaving のんびり for 強気 元気+5 熱意+10、for 全力 元気+5」 | **P1-1（2026-11-24）**：`Stance.LEISURE` + `MULTIPLIER["leisure"]=0` + 费用 ×0；`release_on_stance_change` 扩 4 元组（末位=全体卡成长，`score_growth_all` 永久加算进白值，参考 `target:all g.score+=10` 是 cardMap growth 不是即时分）；来源=卡预约（`ExamOverPreservation`，4 族卡 CSV 逐卡证据表 `LEISURE_RESERVE_SOURCES`，回合开始条件触发/次数扣减）+ P 道具 `stance_leisure` 直给 | ✅ 规则/来源/双镜；⚠️ 2 件道具触发时机 card_play_interval_after 未支持（保守不触发） | `tests/test_p1_stance_rules.py` 36 条 |
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
| 熱意（enthusiasm）→ **本牌分数加算** | `resolveScore` b：`score += enthusiasm × enthusiasmMultiplier`；温存解除给 5/8、のんびり解除给 10；熱意属 `WHOLE_FIELDS`，获得时向上取整；`ExamMultipleEnthusiasticLesson` 本牌倍数 ×2 | `sim/enthusiasm.py` + `LessonSim.enthusiasm` / `ExpectState.enthusiasm`（整数）；`CardSpec.enthusiasm_bonus / enthusiasm_multiple / enthusiasm_extension / enthusiasm_multiplier`；生产卡表 `_effect_fields` 映射 | ✅（のんびり来源 P1-1 已建模；P 道具熱意触发未接入） | `tests/test_t5_enthusiasm.py` 16 条 + `test_p1_stance_rules.py` |
| 好调倍率 `1+(0.5+绝好调0.1×g)×倍率` | `resolveScore` d；wiki `1.5+0.1×好调回合`（绝好调） | `Buffs.condition_turns/perfect_condition_turns` 同式 | ✅ | `test_lesson_rules_reference.py` |
| 指針倍率（0.5/0.25/2/2.5/3/のんびり 0） | `resolveScore` e；实机回放 強気 9→18、温存 9→5/15→8；contest-fidelity のんびり アッチェレランド/ジャストアピール 0 分 | `sim/stance.py MULTIPLIER`（P1-1 加 leisure=0） | ✅ | `test_preservation_card_halves_later_scores`、实机黄金值、`test_leisure_turn_zero_score_zero_cost` |
| 指針牌费（温存减半/強気双倍/強気2 穿透 1/のんびり ×0） | `resolveCost`（费用是负数，`floor(-cost×m)` = 绝对值向上取整）；contest-fidelity のんびり zero cost | `_effective_cost` 用 `ceil(cost×m)`（同语义）；P1-1 加 leisure=0 | ✅ | `test_mechanism_corrections.py::test_stance_cost_modifiers_and_strong_pierce`、`test_leisure_turn_zero_score_zero_cost` |
| 分数增益/减益（scoreBuffs/scoreDebuffs） | `resolveScore` f/g；实机回放「審査基準 +1500‰ = ×1.5」 | `parameter_buff` 千分比近似（乘在最终分上，`int()`） | ⚠️ 语义近似（卡表把它映射成好调/审查基准两种口径） | `test_parameter_buff_*` |
| 自尊 pride `min(好印象,やる気)×0.02` 上限 +0.5 | `resolveScore` f：`prideTurns>0 → scoreBuff += min(min(goodImpressionTurns, motivation)×0.02, 0.5)`；`prideTurns` ∈ EOT_DECREMENT_FIELDS（回合末 -1）/ WHOLE_FIELDS（整数） | **P1-2（2026-11-24）**：`LessonSim.pride_turns` / `ExpectState.pride_turns`；出牌分与回合末好印象在 f 段加算 `min(min(好印象,干劲)×20, 500)` 千分比（与 score_buffs 累加后一次乘）；来源=卡「我、绝不」（turn=5，门槛干劲>=9）+ P 道具「一笔入魂」（turn=2/3，status_gain aggressive & 好印象>=6 & limit1），见 §5.5 | ✅ | `tests/test_p12_hand_decrease_pride.py`（公式/封顶/倒计时/来源/双镜） |
| メタモルフォーゼ：披露 +25% / 支度 ×0.75 | `resolveScore` f/g；实机回放 100→ceil(125)、100→ceil(75) | `Buffs.metamorphosis` | ✅ 分数；❌ 支度→披露半场翻转未做 | `test_lesson_rules_reference.py` |
| 不调 ×0.67 | `resolveScore` h | `Buffs.poor_condition_turns` | ✅ | `test_poor_condition_multiplies_by_0_67`（40×0.67→27） |
| **取整时机**：加算后 ceil、buff 段后 ceil、回合倍率后 ceil | `resolveScore` c/i/④ 的 `safeCeil`（整数附近取整、否则 ceil）；实机回放 9→23、5→8、2→3 | `safe_ceil`（B3 补）：buff 段一次 + 回合倍率一次 | ✅ | 实机回放黄金值 6 条（课程）+ 6 条（考试） |
| 回合属性倍率（审查倍率） | 客户端：按 3 维参数在**分数表分段折线**插值（`ProduceExamBattleScoreConfig`）→ 低于 `ProduceExamBattleConfig` 审查基准时按 `GetPenaltyPermil` 罚分（`Setting` 100~250‰）→ `common=1000−Σpenalties` **三项共乘（联动惩罚）** → `1000+component×common/1000` 归一化到 10；每回合按属性取倍率，`ceil(f32(f32(bonus/1000)×amount)−1e-4)` | `sim/exam_multiplier.py`（纯公式）+ `data/exam_bonus.py`（主数据解析）+ `LessonConfig.attribute_bonuses`/`turn_attributes`；生产侧读屏幕「舞蹈 207%」直接喂 `ExpectState.attribute_coefficient`；旧常量 4.11 仅作无读数时的历史默认 | ✅ 公式/主数据对齐（2026-11-22 T5①）；真机逐分回放还差 P 道具附魔/生成卡等未建模项 | `tests/test_exam_multiplier.py` 21 条 + `tests/fixtures/t5_exam_multipliers.json`（11-20 采集局期中 4.09/2.20/2.60×、期末 6.97/2.85/4.96×）+ 真机帧「舞蹈 207%」→2.07 |
| 依赖分（好印象/元气/全力值折算）是否吃倍率 | 参考引擎里 `score+=goodImpressionTurns*…` 也是普通 `score+=`，**会吃**好调/指針/回合倍率 | 旧路径保守不吃；**T5① 考试真实倍率路径已把依赖分并进属性倍率**（出牌分先加依赖段、乘 buff/审查基准、最后乘属性倍率）；单标量路径保持旧行为 | ⚠️ 两条路径口径不同（生产读屏走标量路径仍保守；模拟器真实倍率路径已对） | `test_dependent_scores_ignore_attribute_coefficient`（旧路径）+ `test_sim_applies_per_turn_attribute_bonus`（新路径） |
| **分数倍率 buff/debuff**（P 道具 `ExamLessonValueMultiple(+Down)`） | `resolveScore` f/g：`score *= 1 + Σ scoreBuff`，再 `score *= max(1 − Σ scoreDebuff, 0)`（`BuffManager.setScoreBuff(amount, turns)` 按 turns 分组、amount 加算、回合末倒计时、turns=None 永久） | B9（2026-11-22）：`LessonSim.score_buffs/score_debuffs` + `ExpectState` 双镜（列表元素 `(千分比, 剩余回合)`，`add_timed/tick_timed` 纯函数）；出牌分与回合末好印象都按 f/g 顺序乘（在メタモルフォーゼ披露之后、支度/不调之前）；取整仍走 `safe_ceil` 一次 | ✅（fresh buff 差一回合问题不适用于 startOfTurn 触发；卡触发的 P 道具沿用同一「回合末 -1」口径，见 §3 fresh buff 行） | `tests/test_p_items_b9.py`（score buff/debuff/加算/倒计时/双镜/算分一致） |
| **费用修正**（P 道具 `ExamStaminaConsumptionDownFix/AddFix/Down/Add`） | `resolveCost`：`cost = floor(cost × 指針 × halfCostTurns × doubleCostTurns)`（负数 floor = 幅度向上取整）→ `cost += costReduction − costIncrease` → 夹到 ≤0（我们正数口径夹 ≥0） | B9：`cost_reduction/cost_increase`（永久加减）、`half_cost_turns/double_cost_turns`（接下来 N 回合 ×0.5/×2 计数器）；`LessonSim._effective_cost` 与 `expectimax.effective_cost` 同式；「随机 1 张手牌」版本保守 no-op（无手牌定位） | ✅（全局费用修正）；随机手牌版本 ❌ 不猜 | `tests/test_p_items_b9.py::test_lesson_half_cost_turns_*` / `test_lesson_cost_reduction_and_increase` |
| 单精度舍入（JS double vs Python float） | 两边都是 IEEE-754 double；参考 `safeCeil` 有 1e-9 epsilon；属性倍率乘用**单精度**（`CalcCurrentTurnBattleBonus`） | `safe_ceil` 同实现；`exam_multiplier.f32`/`battle_bonus_score` 用 struct 模拟 f32 | ✅ | 实机黄金值 + `test_battle_bonus_score_matches_client_rounding` |
| growth（成长表） | `resolveScore` ① 用 growth 表的**加算**（g.score 等） | `grow_score` 是卡面百分比乘白值；数据为空 → 恒 0。**P1-1 例外**：のんびり→全力 的 `target:all g.score+=10` 是规则触发的全体卡成长，已按加算实现（`score_growth_all`，每次出牌加进白值、永久、可叠加） | ❌ 卡表成长数据缺口（`ProduceCardGrowEffect` 未下载）；✅ のんびり→全力成长 | `test_leisure_to_full_boundary_grants_growth` / `test_expect_award_includes_growth_all` |

## 3. Buff 生命周期 / 好印象年金 W(r,T)

| 项 | 参考实现 / 真机证据 | 我们 | 状态 | 回归 |
|---|---|---|---|---|
| 好印象：回合末 `score += 层数 × 强化倍率` | `GOOD_IMPRESSION_EFFECTS`：`score += goodImpressionTurns × buff`；回合末触发 | `_end_turn`：`score += int(层数 × (1000+review_multiple)/1000)` | ✅ | `test_exam_review_scores_at_turn_end_then_decays` |
| 好印象回合推进 -1 | `BuffManager.decrementBuffTurns`（`EOT_DECREMENT_FIELDS` 含 goodImpressionTurns） | 下一回合开始时 -1（最低 0） | ✅ | `test_depend_exam_review_*` |
| 年金 `W(r,T) = r+(r-1)+…` | 上述逐回合结算的闭式；解析叶子用它估未来分 | `AnalyticLeafValue.impression_annuity` | ✅（与参考同语义） | `tests/test_expectimax.py` 相关用例 |
| 好调/绝好调/不调回合数衰减 | `EOT_DECREMENT_FIELDS` | `_end_turn` / `end_turn_state` 各 -1 | ✅ | `test_new_condition_buffs_tick_down_at_turn_end_in_both_engines` |
| 熱意回合末清零 / 熱意延長 | `TurnManager.endTurn`：好印象结算之后，`enthusiasmExtensionTurns>0` 则 -1、否则 `enthusiasm=0`；好印象结算在清零之前（会加熱意） | `enthusiasm.turn_end_enthusiasm`；`LessonSim._end_turn` / `ExpectState.end_turn_state` | ✅ | `test_enthusiasm_extension_keeps_enthusiasm_across_turn_end`、`test_turn_end_good_impression_adds_enthusiasm` |
| **fresh buff 保护**：获得 buff 的当回合末不扣 1（回合末从 0→正 的字段打 fresh 标记跳过衰减） | `Executor/index.js` L271-279「Protect fresh stats from decrement」+ `BuffManager.decrementBuffTurns` | 我们的 buff 当回合末就 -1（**少 1 回合持续**） | ❌/⚠️ 未真机核实；参考引擎的 fidelity 截图常省略回合末 buff 数 | 待真机逐回合截图验证（T6） |
| 好印象强化 / 好调加算 / 全力强化 持续回合 | `ExamReviewMultiple` / `ExamParameterBuffAdditiveFix` / `ExamFullPowerLessonMultipleAdditive` | `Buffs.review_multiple` 等 + `_tick_buff_turns` | ✅ | `test_review_multiple_*`、`test_condition_additive_*` |
| メタモルフォーゼ 支度→披露（半场自动翻转） | `TurnManager.endTurn`: `turnsElapsed >= floor(turnCount/2)` | 只有外部设置的 `Buffs.metamorphosis`，不自动翻转 | ❌ 小（需要偶像特性数据） | — |
| 饮料（体力/集中/好调/直接分） | 参考引擎 `p_drinks.csv`；实机每回合 1 瓶（用户确认无上限） | `LessonSim.use_drink`：4 种效果，不占出牌次数 | ✅ 已建模的 4 种；⚠️ 其余 20+ 种效果报错不静默 | `test_drink_*` |
| P 道具（被动，按触发时机） | `p_items.csv` + 参考引擎 `PItems`；exam_start/turn_start/card_play/turn_skip 等 | `sim/p_items.py` 接口（exam_start/turn_start/turn_start_after/turn_interval/turn_end/card_play/status_gain/status_gain_interval/stance_change/stamina_reduce 等触发）；T5③ 数据接入：`data/p_items_db.py` 把对局 loadout 的 `produce_item_ids` 解析成 `PItemSpec`（B7 起 catalog 1115 件，gkbench 505 题模板 83 唯一 id **83 已知 / 0 未知**）；`LessonSim` 构造时结算 exam_start；**B9 起效果覆盖 1025/1849 段**（B8 676），含持久分数倍率/好印象强化/增益倍率/费用修正/回合追加/指針直给等 20 类 target | ✅ 数据接入（gkbench/离线；条件未知 6 件/10 段、指定卡/手牌限定 103 件/185 段保守不触发）；⚠️ 真机培育侧 P 道具列表未采集（T6/D1）、生成卡/强化状态花费卡/附魔仍未建模 | `tests/test_p_items.py` / `test_p_items_b8.py` / `test_p_items_b9.py` / `test_p_items_db.py` / `test_p_items_integration.py` / `test_gkbench_submission_p_items.py`；§5.3 |

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

### 5.2 T5② 熱意 + 温存解除（2026-11-22 完成）

| 改动 | 文件 | 证据 | 回归 |
|---|---|---|---|
| **熱意独立资源**：整数、回合内有效；出牌分在集中之后、好调/指針倍率之前加算（`score += 熱意 × 本牌熱意適用倍数`）；回合末归 0 | `sim/enthusiasm.py`（纯规则）+ `LessonSim.enthusiasm` + `ExpectState.enthusiasm` | 参考引擎 `Executor/resolvers.js:131-132`（resolveScore b）、`TurnManager.js:160-164`（延長/清零）；官方 wiki 温存描述 | `tests/test_t5_enthusiasm.py` |
| **温存解除**：1 段階 熱意+5 / 2 段階 熱意+8 + **固定元気+5**（不吃やる気）+ 解除当回合 **出牌次数+1**；同回合重复解除可叠加；温存段階升级（save→save2）不触发 | `sim/enthusiasm.py::release_on_stance_change`；`LessonSim.step` / `ExpectState._apply_card_effects` | `constants.js STANCE_CHANGED_EFFECTS`（:49-56）、`BuffManager.setStance`（:285-290）同步触发 | 同上 |
| **熱意获得公式**：`(熱意追加 + N) × (1 + 熱意増加‰)`，获得时向上取整（WHOLE_FIELDS ceil） | `sim/enthusiasm.py::enthusiasm_gain` | `resolveEnthusiasm`（resolvers.js:339-349）+ `WHOLE_FIELDS` 处理（Executor/index.js:493-500）；wiki「計算後切り上げ」 | 同上 |
| **卡牌来源接入**：`ExamEnthusiasticAdditive`（熱意追加 buff）/ `ExamEnthusiasticMultiple`（熱意増加 buff‰）/ `ExamEnthusiasticTurnAdd`（熱意延長）/ `ExamMultipleEnthusiasticLesson`（本牌熱意適用倍数 ×2，卡面「熱意效果会2倍生效」） | `scripts/sim_produce.py`（CardRow/`_effect_fields`，MODELED_EFFECTS 29→32）+ `sim/play_choice.py`（生产卡表 → CardSpec） | 主数据 `ProduceExamEffect.yaml` 实例（`-0005-inf` 等）+ 官方 wiki 词条；卡例「あたらしい光」「フルスロットル」「結果としての今」「手を伸ばした先に」 | `test_sim_produce.py` / `test_play_choice.py` |
| **回合边界解除**：温存→全力（全力值攒满）在回合末切换时也结算解除收益（+5 熱意 / +1 新回合出牌次数；2 段 +5 元気） | `LessonSim._end_turn` / `ExpectState.end_turn_state` | 参考引擎 `TurnManager.startTurn` 的 `FULL_POWER_EFFECTS`（setStance(fullPower) 触发 STANCE_CHANGED_EFFECTS） | `test_save_release_at_turn_boundary_grants_next_turn_extra_play` |

**口径与剩余差距（如实记录）**：

- ~~のんびり（leisure）指針本模拟器没建模~~ ✅ **P1-1（2026-11-24）已建模**（解除规则/×0 倍率/
  预约来源/守卫，见 §5.4）；全力回合 +1 出牌/保留牌回手同批补全（§1 已改 ✅）。
- 参考引擎 fidelity 的实机黄金值只用于口径核对（`training-fidelity.md`：温存 9/2/15→5/1/8 +
  「leaving 温存 grants 5 熱意 and an extra use」；`contest-fidelity.md`：温存 2 段解除给
  5 元気/8 熱意/额外出牌、のんびり→強気 元気+5 熱意+10、のんびり zero cost/zero score、
  全力回合 held スパート 回手出牌）；我们没有逐帧 fixture JSON，未做逐分回放。
- 生产读屏还没读熱意图标/当前温存段階：`policy/lesson.py::_search_state` 每步按回合开始（熱意 0）建模，
  同回合第二张（額外出牌）时不会带上上一张刚获得的熱意——与现有「不读好调/集中层数」同口径；
  真机逐分核对留到 T6/读屏补强。
- B2 学习叶子的 104 维特征里 `save_cards_used` 已废弃（恒 0），重训时再换熱意特征；模型本来就要重训。

### 5.3 T5③ P 道具数据接入（2026-11-22 完成）

| 改动 | 文件 | 证据 | 回归 |
|---|---|---|---|
| **loadout → PItemSpec 数据层**：对局 `produce_item_ids` 精确匹配 `p_items.json`（1068 件模板，2026-09-16 主数据快照）；未知/重复 id 显式返回，缺文件抛 `PItemDataUnavailable` | [p_items_db.py](../src/gkagent/data/p_items_db.py) | gkbench `saves.jsonl[]`（505 题模板）`loadout.produce_item_ids`：2686 个 id / 83 唯一 / 72 已知 / 11 未知；`gkbench/algos/base.py` 明说 `ctx.loadout` 是「开局配置（不含种子）」→ 公平可用 | `tests/test_p_items_db.py`（10 条，含 505 题模板真数据断言） |
| **新增触发时机 `exam_start`**（训练/考试开始时，288 段素材）：`LessonSim` 构造时（抽第 1 手牌前）结算一次，先于 `turn_start`；额外出牌次数属于第 1 回合 | [sim/p_items.py](../src/gkagent/sim/p_items.py)、[sim/lesson.py](../src/gkagent/sim/lesson.py) | 原生触发 id `e_trigger-exam_start_exam` / `start_exam_play`；F0 起点体力偏差 5 组（shro-3-016 −28）可用 `pitem_02-3-293-0` 考试开始「最大体力 80% 变体力消耗」解释（`floor(36×0.8)=28`） | `test_exam_start_items_apply_at_sim_construction` / `test_exam_start_runs_before_turn_start` / `test_real_exam_start_item_fires_once` |
| **新增效果 `ExamPlayableValueAdd` → `extra_plays`**（51 段素材，N 在 `count` 列）：`PItemDelta` 增加 `extra_plays`，`LessonSim`/`ExpectState` 镜像 | [sim/p_items.py](../src/gkagent/sim/p_items.py)、[sim/expectimax.py](../src/gkagent/sim/expectimax.py) | 卡效果同类型早已映射 `CardSpec.extra_play`（B3 真机 39 回合证据）；P 道具数据 51 段全 `count=1` | `test_extra_play_effect_adds_action_slot` / `test_record_to_specs_uses_count_for_playable_add` / `test_exam_start_extra_play_keeps_first_turn_open` |
| **离线跑分/提交接线**：`local_bench` 从题模板 loadout 接入（`--p-items auto/off`、报告 `p_items` 覆盖率）；gkbench 提交从 `ctx.loadout` 接入（缺数据 meta 记原因） | [scripts/local_bench.py](../scripts/local_bench.py)、[submissions/expectimax/algo.py](../submissions/expectimax/algo.py) | hif 30 题 × 2 seed 配对 A/B：greedy 3840.7 → **3969.7（+128.9，+3.36%，CI95 [+9.5,+248.4]）**；expectimax 3759.3 → 3908.9（+149.6，+3.98%，CI95 [−171.0,+470.2]）；其余局逐位不变（33/174 段已实现） | `tests/test_local_bench.py`（+4 条）/ `tests/test_gkbench_submission_p_items.py`（6 条） |

**B7（2026-11-22 完成）：catalog 补到上游 1115 件（gkbench 未知 id 清零）**

- [build_p_items.py](../scripts/build_p_items.py) 改为「本地中文 masterTrans（2026-09-16，1068 件，
  逐段对齐）+ gakumasu-diff `ProduceItem.yaml` 独有 47 条」合并生成：新 id 的结构化字段/数值
  来自 yaml（`_extract_effects_yaml` 兜底口径），卡名用仓库自译表
  `data/i18n/translation_new.json`（47/47 命中），**中文描述缺失**处 `text_zh=""`、
  `text_ja` 保留日文并标 `i18n_text_source="ja"`（不猜、不臆造译文）。
- 新 id 的触发 id 本地 masterTrans 里没有中文触发句（快照早于新表）→
  `condition_known=False`（22 件 / 46 段 spec）；`apply_passive` **保守跳过**，不把带条件的
  道具当无条件结算（`PItemSpec.condition_known`，`summarize` 单列计数，不混进 implemented）。
- 数据：**1068 → 1115 件**；spec 1764 → **1849 段**，已实现 421 → **445 段**
  （no-op 1404：effect_type 不支持 1026 / 触发时机不支持 207 / 无值 171；条件未知 46 段另计）；
  gkbench 505 题模板：2686 个 id / 83 唯一 / **83 已知 / 0 未知**（唯一口径 153 段 spec，
  实现 34 段、条件未知 10 段）。
- 离线 A/B（同 harness：hif 30 题 × 2 seed = seed 1000/1001，`--budget-ms 100`，
  `local_bench --p-items off/auto`，同题同 seed 配对，CI = mean±1.96·SE）：

| 算法 | off | auto | 配对 Δ | 95% CI | 变化局（胜/负/平） |
|---|---:|---:|---:|---|---|
| greedy | 3840.7 | **3969.7** | **+128.9（+3.36%）** | [+9.5,+248.4] | 8/60（8/0/52） |
| expectimax(analytic) | 3732.0 | **3953.6** | **+221.5（+5.94%）** | [−71.4,+514.4] | 13/60（10/3/47） |

  - **greedy 与 B6 逐位相同**：新增 47 条里 22 条条件未知、其余多为未实现类型/育成期触发
    → 不触发，所以 +128.9 仍是「数据接入」本身的收益；expectimax 受墙钟预算抖动
    （B6 同 harness 为 3759.3→3908.9，+149.6，两次 CI 都含 0），只作方向记录。
  - 样本覆盖（30 题）：147 id / **147 已知 / 0 未知**（B6：130/8）、198 段 spec（B6 174）、
    已实现 35 段（B6 33）、条件未知 9 段。
- 回归：`test_p_items_db.py` +1（47 条新增全覆盖 / 未知清零 / 条件未知计数）、
  `test_p_items.py` +2（condition_known 保守跳过 / summarize 计数）、
  `test_p_items_integration.py` 触发候选过滤加 `condition_known`；
  全量 pytest **1054 passed / 1 skipped（1055 收集 / 76 文件）**。

**B8（2026-11-22 完成）：P 道具条件/效果语义（第一批）**

目标：把「条件/效果语义」从文本猜测推进到可验证的结构化实现（B7 清了数据缺口后的下一段）。
三块改动：

1. **新语法 trigger id 结构化解析**（[build_p_items.py](../scripts/build_p_items.py)：
   `parse_exam_trigger_id` / `trigger_id_has_unparsed_condition`）：上游 2026-11 的新触发把
   条件编码在 id 后缀里（`…-remaining_turn-5`、`…-parameter_buff_up-8`、
   `…-stamina_up_multiple-800`、`…-stamina_less_multiple-500`、`…-full_power_point_get_sum_up-10`、
   `…-card_play_aggressive_up-5`、`exam_review_up_interval-N`、`…-lesson_visual`），从 id
   解析成 `trigger_params` + 条件串（`好调在N回合以上` / `体力在N%以上|以下` /
   `累计全力值在N以上` / `干劲在N以上` / `剩余N回合内` / `每N回合`）——**条件未知 22→6 件**
   （16 件从 id 恢复）。指定卡名（`p_card_search-…-p_card-…`）与手牌指定卡张数
   （`card_search_count_up-N`）这类没有卡名→id 映射的限定，**单列 `trigger_known=False`**
   （103 件 / 185 段 spec）保守跳过——不能当无条件触发（会在任意卡上误触发）。
2. **效果语义**（[sim/p_items.py](../src/gkagent/sim/p_items.py)）：
   - **依赖换算**「X 的 N% 数值变为 Y」：数据层标注 `depends_on` + `percent`
     （65 段），结算 `目标增量 = int(源层数 × N / 100)`；源 = 好印象 / 元气 / 干劲 /
     集中 / 累计全力值 / 消耗过的体力（后两个用 `full_power_point_total` /
     `consumed_stamina_total` 伪 stack key 传入）。**源段只作系数，不再当直接加层数**。
   - **「X 变为 0」**：`zero_stack`（3 段）→ 结算时把对应层数清零（不是加 0 层）。
   - **`ExamStaminaReduceFix`（固定体力消耗）**：`value1` 固定值，或「最大体力的 N%」
     （`percent_max`，9 段）→ 直接扣体力；`ExamStaminaRecoverFix` 的百分比形式同口径回复。
3. **新触发时机 + 双镜**（[sim/lesson.py](../src/gkagent/sim/lesson.py) /
   [sim/expectimax.py](../src/gkagent/sim/expectimax.py)）：新增 `turn_start_after`、
   `turn_interval`（每 N 回合）、`status_gain_interval`（状态累计增加 N 次，用
   `status_gain_counts` 累计）、`stance_change`（指針切换）、`stamina_reduce`
   （体力实际减少）五类事件；`full_power_point_total` / `consumed_stamina_total`
   两个本场累计量随全力值获得 / 体力消耗维护，`state_from_sim` / `sim_from_state`
   与 `canonical` 全镜像（搜索与执行同口径）。

**数据/回归（2026-11-22 复跑）**：

| 指标 | B7 | B8 | B9 |
|---|---:|---:|---:|
| catalog 件数 / spec 段 | 1115 / 1849 | 1115 / 1849（不变） | 1115 / 1849（不变） |
| 数据层已实现 spec 段 | 445 | 676（+231） | **1025（+349）** |
| no-op spec 段 | 1404 | 1173 | **824** |
| 条件未知 | 22 件 / 46 段 | 6 件 / 10 段 | 6 件 / 10 段（不变） |
| 触发限定未知（指定卡/手牌） | —（旧口径算作条件已知但实际不触发） | 103 件 / 185 段（新单列） | 103 件 / 185 段（不变） |
| 依赖换算 / 百分比体力 / 归零 | 0 / 0 / 0 | 65 / 9 / 3 段 | 65 / 9 / 3 段（不变） |
| 持久倍率/modifier（B9 target） | — | — | **337 段**（20 类 target） |
| 描述解析次数上限 | —（只有 9 件有 max_uses） | — | **896 件**（「训练内N次」等） |
| gkbench hif 83 唯一 id（153 段含无效果育成期道具）已实现 | 34 段 | 59 段 | **103 段** |

- 全量 pytest **1067 passed / 1 skipped**（1068 收集 / 77 文件；B8：新增
  `tests/test_p_items_b8.py` 19 条，旧测试按新口径更新）；基线 ① 4/4+3/3、
  ③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。
- B9 全量 pytest **1116 passed / 1 skipped**（1117 收集 / 78 文件；新增
  `tests/test_p_items_b9.py` 49 条）；基线 ①③④⑤ 与 B8 逐项相同（见 §5.3 B9）。
- 离线 A/B（同 B7 harness：hif 30 题×2 seed = 1000/1001、`--budget-ms 100`、同题同 seed
  配对，CI = mean±1.96·SE；off 与 B7 逐位相同）：

| 算法 | off | auto | 配对 Δ | 95% CI | 变化局（胜/负/平） |
|---|---:|---:|---:|---|---|
| greedy | 3840.7 | **4065.9** | **+225.2（+5.86%）** | [+86.7,+363.6] | 18/60（17/1/42） |
| expectimax(analytic) | 3726.4 | **3921.8** | **+195.4（+5.24%）** | [−125.3,+516.2] | 21/60（17/4/39） |

- **如实记录（B8）**：expectimax 的 CI 含 0（`--budget-ms 100` 墙钟预算噪声大，B6/B7 两次也
  都是方向记录）；greedy 是确定性执行、CI 全正。**B8 当时不动的**：`ExamLessonValueMultiple`
  （持续分数倍率 buff，需要新的持久字段与取整顺序证据）、`ExamCardCreateId`（生成卡）、
  `ExamExtraTurn` / `ExamBuffConsumptionAdd` / `ExamReviewMultiple` / `ExamReviewCountAdd`
  等 modifier 类、`ExamPreservation`/`ExamConcentration` 直给式、好调依赖换算
  （模拟器里好调是剩余回合数，量纲不同不猜）——其中除生成卡/`ExamBuffConsumptionAdd`/
  好调依赖换算外，**B9 已完成**（见下）。真机培育侧 P 道具列表仍未采集（T6/D1）。

**口径与剩余差距（如实记录）**：

- 真机采集 `traffic.jsonl`（3.2MB）全文件 0 命中 produce 编成字段 → **真机培育侧**
  P 道具列表未采集（T6/D1 补采 produce 开始 API/存盘）；本轮接的是 gkbench 题模板的
  loadout（离线、公开配置）。
- 效果覆盖（B8 后）：catalog **1115 件 → 1849 段 spec，数据层已实现 676 段**（B7 445）；
  gkbench 83 个已知道具 → 153 段 spec，已实现 **59 段**（B7 34）。
  未实现大户：`ExamLessonValueMultiple`（持续分数倍率 buff）、`ExamCardCreateId`（生成卡）、
  `ExamStaminaConsumptionDownFix`（削减消耗体力）、`ExamPreservation`/`ExamConcentration`
  （指針直给）、`ExamExtraTurn` / `ExamBuffConsumptionAdd` / `ExamReviewMultiple` /
  `ExamReviewCountAdd` 等 modifier 类 → 需要参考引擎语义/持久 buff 字段与取整顺序证据再补，
  **不猜**。**条件未知只剩 6 件**（新语法 id 解析不了的残余）；**触发限定未知 103 件**是
  指定卡名/手牌张数（缺卡名→id 映射，保守跳过），不是效果语义缺口。
- **11 个未知 id 已清零**（B7，2026-11-22）：`pitem_01-3-349-0`、`pitem_02-3-336-1`、
  `pitem_03-3-334/337/345-*`、`pitem_3-258-research-event-008/009/010` 等已进 catalog；
  但它们的**条件未知/效果未实现** → 保守不触发（0 分贡献），开放点变成「条件与效果语义」。
- gkbench 提交侧 `obs` 没有 P 道具已用次数 → 保守从 0 开始（可能高估剩余次数）；
  主道具附魔 `main_item_enchant_ids` / 回忆 `memory_ability_ids` 未接入。
- 生产真机（`policy/lesson.py` 读屏路径）**没接**：屏幕读不到 P 道具 id 清单，仍按空
  P 道具算（同旧口径）；要真机用上需要采集 loadout 或读图标（T6）。

**B9（2026-11-22 完成）：P 道具持久倍率 / modifier 类效果（第二批）**

目标：B8 清了条件/第一批效果后，补**会持续若干回合、影响分数/费用/回合数的 modifier**。
语义来源：gakumas-tools 参考引擎（BSD-3）`Executor/resolvers.js::resolveScore` f/g、
`resolveCost`、`BuffManager.js`（`setScoreBuff(amount, turns)` 列表 + 回合末倒计时 +
`fresh` 保护）与 `p_items.csv` 的 DSL（`setScoreBuff(0.5,1)` / `setStance(preservation)` /
`costReduction+=N` / `halfCostTurns` 等）。**只按语义重写，不拷代码**。

1. **数据层**（[build_p_items.py](../scripts/build_p_items.py)）：
   `annotate_modifier_effects` 把 effect_type（+ 效果文本）标成 `target` / `duration`
   （20 类 target、**369 段 / 298 件道具**）；百分比类 `percent1`（人类百分比）存成
   **千分比**（与卡表 `review_multiple` 同口径）、持续时间取 `values.turn`（缺 = 永久）。
   另从描述文本解析「（训练内N次）/（培育中N次）/（レッスン内N回）」→ 记录级
   `max_uses`（**9→896 件**）：没有这个上限，持续倍率类效果会每回合重复触发、把分数算爆；
   这也修正了 B6–B8 期「生效效果可无限触发」的口径（所以 B9 的 auto 数字与 B8 的 auto
   **不可直接比**，A/B 只比同一代码的 off/auto）。
2. **纯规则增量**（[sim/p_items.py](../src/gkagent/sim/p_items.py)）：`PItemDelta` 新增
   `score_buffs / score_debuffs / modifiers / cost_reduction / cost_increase /
   half_cost_turns / double_cost_turns / extra_turns / stances / perfect_condition_turns /
   poor_condition_turns`；定时倍率列表纯函数 `add_timed`（同 turns 合并加算）/
   `total_timed` / `tick_timed` / `timed_dict_*` / `normalize_turns`（0 = 永久 = -1）。
   - **打分上升量增加/减少**（`ExamLessonValueMultiple` / `Down`）：`resolveScore` f/g
     → 出牌分 `× (1+Σ)`、再 `× max(1−Σ,0)`；**加算**（同回合数合并），不是取最大。
   - **好印象强化**（`ExamReviewMultiple`）→ 沿用卡效果 `Buffs.review_multiple` 渠道（千分比）；
     **好印象追加发动**（`ExamReviewCountAdd`）→ 回合末好印象结算重复 N+1 次。
   - **增益倍率**（获得量 ×(1+N%)，向上取整）：热意增加/追加（沿用 T5② 渠道）、
     集中强化（集中对分数的贡献 ×）、集中/好印象/干劲/全力值增加量增加（`setConcentrationBuff`
     / `setGoodImpressionTurnsBuff` / `setMotivationBuff` / `setFullPowerChargeBuff` 语义）。
   - **绝好调/不调回合**（`ExamParameterBuffMultiplePerTurn` / `ExamGimmickParameterDebuff`）
     → `perfect_condition_turns` / `poor_condition_turns`。
   - **费用修正**（`ExamStaminaConsumptionDownFix/AddFix/Down/Add`）：永久加减 +
     「接下来 N 回合 ×0.5/×2」计数器；`effective_cost` 两引擎同式（见 §2）。
   - **回合追加**（`ExamExtraTurn`）：本回合得到的追加在回合末 `turns_left−1` 之后补上，
     `total_turns` 同步增长（回合号不跳变；等价参考引擎 `turnsRemaining+=1` 后同帧 `--1`）。
   - **指針直给**（`ExamPreservation`/`ExamConcentration` 的「温存变更/强气变更」）：
     直接 `setStance`（同指針再加 → 2 段階），并触发温存解除收益与 `stance_change` 事件
     （递归深度 ≤3）。**卡类强化段（「温存效果的技能卡的…」）不是指針变更 → 保守 no-op**。
   - **固定元气**（`ExamBlockFix`）/ **好印象减少**（`ExamReviewReduce`）走层数增量；
     「消耗体力减少状态」条件用 `half_cost_state` 伪 stack 解析。
3. **双镜**（[sim/lesson.py](../src/gkagent/sim/lesson.py) /
   [sim/expectimax.py](../src/gkagent/sim/expectimax.py)）：`LessonSim.score_buffs/
   score_debuffs/modifiers/cost_*/half_cost_turns/double_cost_turns/extra_turns_pending/
   extra_turns_granted` 与 `ExpectState` 对应字段 + `canonical()` +
   `state_from_sim`/`sim_from_state` 全镜像；两引擎的 `_card_award`/回合末好印象/费用/
   回合末倒计时同口径（测试 `test_lesson_expect_award_parity` 逐位对齐）。

**数据/回归（B9）**：catalog spec 1849 不变；已实现 **676→1025 段**（no-op 1173→824）、
持久倍率/modifier **337 段**；gkbench hif 83 唯一 id 已实现 **59→103/153 段**；
新增 `tests/test_p_items_b9.py` **49 条**、旧 `test_p_items.py` 把 `ExamLessonValueMultiple`
从「未实现」名单移除；全量 pytest **1116 passed / 1 skipped（1117 收集 / 78 文件）**；
基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。

**离线 A/B（B9，同 harness：hif 30 题×2 seed=1000/1001、`--budget-ms 100`、配对，
CI = 按题整体重采样 10000 次 percentile bootstrap）**：

| 算法 | off | auto | 配对 Δ | 95% CI | 胜/负/平 |
|---|---:|---:|---:|---|---|
| greedy | 3840.7 | **3951.0** | **+110.3（+2.87%）** | [+39.6,+193.3] | 20/2/38 |
| expectimax(analytic) | 3666.5 | **3822.8** | **+156.2（+4.26%）** | [−137.4,+435.4] | 21/6/33 |

- greedy 是确定性执行、CI 全正；expectimax 的 CI 含 0（`--budget-ms 100` 墙钟噪声，同 B6–B8
  只作方向记录）。
- **不可直接比 B8 auto 4065.9**：B9 的 `max_uses` 口径修正（描述里的「训练内N次」生效）
  把 B6–B8 期可无限触发的效果收紧；同一代码的 off/auto 配对仍是 +110.3。

**如实记录的剩余（B9 后）**：
- **`ExamBuffConsumptionAdd`**（強化状態コスト増加ターン，4 段 / 22 题权重）：需要「以强化
  状态作为花费值的技能卡」这一机制，我们的卡牌模型没有 buff-cost 卡 → **保持 no-op**，
  不猜。
- **`ExamCardCreateId` 生成卡**（17 段 catalog / gkbench 172 段权重）：需要考试内生成卡
  模型（考试 RNG 入口之一），不在本轮范围。
- **指定卡名 / 手牌指定卡张数**（`trigger_known=False` 103 件 / 185 段）：缺卡名→id 映射，
  保守不触发。
- **数值/取整顺序的近似**：P 道具增益倍率在我们的整数层数模型里用 `safe_ceil`（参考引擎
  是浮点层数）；回合末好印象的 `resolveScore` 只 apply 分数倍率/熱意/好印象强化/追加发动，
  不重复 apply 集中（参考引擎会，见 §2 依赖分口径；B5 已记录同一近似）；
  fresh buff 差一回合问题（§3）同样作用于卡/`turn_end`/`stamina_reduce` 触发的新 buff。
- 真机培育侧 P 道具列表仍未采集（T6/D1）；主道具附魔/回忆未接入。

**B10（2026-11-23 完成）：T5 剩余机制①②——ExamCardCreateId 生成卡 + 指定卡名/手牌张数映射**

目标：B9 之后纯离线可做的两块——生成卡（确定式）与触发限定结构化（卡名→id 映射）。
语义来源：masterTrans `ProduceCardSearch.json` 描述表 + 主数据 `ProduceCard.effectGroupIds` /
`originIdolCardId` / `originCharacterId` + BSD-3 参考引擎 gakumas-tools（`usedCardBaseId` /
`countCards` / `addCardTo*` / `limit:N`，只按语义重写、不拷代码）。

1. **卡元数据**（[build_card_meta.py](../scripts/build_card_meta.py) →
   [card_meta.json](../data/knowledge/card_meta.json) + [card_meta.py](../src/gkagent/data/card_meta.py)）：
   卡名 → id/upgrade/**idol_unique**/**effect_groups** + 日文别名。idol_unique 判据
   （originIdolCardId 或 originCharacterId 非空）与参考 `skill_cards.csv` pIdol 集合
   交叉验证 **340/342、0 误报**（一番星=prima stella 不算；微熱ノスタルジー♡ 无 origin
   字段保守不计）。effect_groups 直接取卡面 `effectGroupIds`（与触发限定同一套 id，
   `EffectGroup` 表定义组→效果类型，不猜映射）。
2. **数据层**（[build_p_items.py](../scripts/build_p_items.py)）：`parse_card_search`
   解析 `play_filter`（指定卡名 base id 不限强化 / 偶像固有 / 效果组 / 原本费用 min_max /
   类别 / 稀有度）与 `zone_count`（hand/deck/discard/excluded 四区张数 + `not-` 取反）；
   `annotate_create_effects` 文本最长后缀匹配卡名 → `create`（id/强化/手牌/牌堆顶/弃牌堆）
   / `create_random`（随机基础卡补到 22 张，只记语义）。**触发未知 103→3 件 / 185→6 段**
   （hold 保留区 2 + period810_hotfix 1）、**条件未知 6→0**；play_filter 234 件 /
   zone_count 27 件；生成卡 **11 段确定 + 6 段随机**。
3. **纯规则 + 双镜**（[p_items.py](../src/gkagent/sim/p_items.py) /
   [lesson.py](../src/gkagent/sim/lesson.py) / [expectimax.py](../src/gkagent/sim/expectimax.py) /
   [play_choice.py](../src/gkagent/sim/play_choice.py)）：`CardFilter`/`ZoneCount`/`CreateCard`
   结构化求值（查不到 → None 保守不触发）；`exam_start_after` 新时机（抽完第一手牌后）；
   生成卡落牌（**手牌≥5 不生成** / 牌堆顶=deck 末尾，ExpectState 同步 `known_draw[0]` /
   弃牌堆同步 `discard_order`）；`spec_from_name` 与牌组构建同口径。
   **次数上限按道具计**（同事件多效果段只记 1 次，参考 limit:N；旧按段累计会让多段道具
   提前用完——B10 口径修正，B10 auto 与 B9 auto 不可直接比）。

**数据/回归（B10）**：catalog 1849 段不变；已实现 **1025→1042**（no-op 824→807）；
gkbench 103/153 段（口径不变；loadout 里 4 件/8 段原 trigger 未知道具现在真实触发）；
新增 `tests/test_p_items_b10.py` **38 条**（含参考引擎生成卡 id / pIdol 判据交叉验证，
参考 csv 缺失自动 skip）；全量 pytest **1154 passed / 1 skipped（1155 收集 / 79 文件）**；
基线 ①③④⑤ 全部不变。

**离线 A/B（B10，同 harness：hif 30 题×2 seed=1000/1001、`--budget-ms 100`、配对，
CI = 按题整体重采样 10000 次 percentile bootstrap）**：

| 算法 | off | auto | 配对 Δ | 95% CI | 胜/负/平 |
|---|---:|---:|---:|---|---|
| greedy | 3840.7 | **4638.2** | **+797.5（+20.76%）** | [+399.0,+1250.1] | 31/3/26 |
| expectimax(analytic) | 3665.8 | **4466.9** | **+801.1（+21.85%）** | [+66.3,+1697.9] | 28/8/24 |

- off 与 B9 逐位相同；增益来自触发映射（加油鼓劲等 4 件/8 段 loadout 道具开始触发）+
  次数按道具计修正。确定式生成卡不在 hif loadout（只有应援棒随机式）→ ① 的 A/B 贡献 0，
  由单测覆盖。expectimax 这次 CI 也全正（增益远大于墙钟噪声）。

**如实记录的剩余（B10 后）**：
- `ExamBuffConsumptionAdd`（强化状态花费卡）：卡牌模型没有 buff-cost 卡 → **保持 no-op**（不猜）。
- **H.I.F应援棒随机基础卡**（6 段 / gkbench 172 段权重）：考试 RNG 入口、真机流未知 →
  记 `create_random` 语义，**保持 no-op**（与 `exam_risk` 事前检测同口径）。
- **hold（保留）区**未建模（§6.8）→ 2 件保留区张数条件保守不解析；hotfix 未知词 1 件同。
- 微熱ノスタルジー♡ 无 origin 字段 → 不算偶像固有；12 张快照后新卡无 meta → 限定不可判（保守）。
- fresh buff 差一回合（需真机逐回合截图，§3）、真机培育侧列表（T6/D1）、主道具附魔/回忆。

### 5.4 P1-1 全力回合 + のんびり指針（2026-11-24 完成）

| 改动 | 文件 | 证据 | 回归 |
|---|---|---|---|
| **全力回合 +1 出牌**：以全力开始的回合 `extra_plays += 1`（连续全力每回合都有；与温存解除的 +1 是两条独立效果，温存→全力边界后新回合 = 2 次额外） | `LessonSim._end_turn` / `expectimax.end_turn_state`（`enters_full` 分支） | `constants.js FULL_POWER_CHANGED_EFFECTS`（`if:stance==fullPower { cardUsesRemaining+=1; moveHeldCardsToHand }`）+ `TurnManager.startTurn`（抽牌后触发；先 fullPower→none 再按 charge 进全力，故连续全力也触发）；contest-fidelity 美鈴回放「switch to 全力 keeps the extra 1, that turn's three cards score 778」 | `test_full_power_turn_grants_extra_play` / `test_consecutive_full_power_turns_each_grant_extra_play` / `test_end_turn_state_full_entry_extra_play_and_held` |
| **保留牌回手**：全力回合 `held` 全部弹回手牌（无手牌上限检查，同参考） | `LessonSim.held` / `ExpectState.held` + `_move_held_to_hand`；`end_turn_state` 把回手牌放进下一手 | `CardManager.moveHeldCardsToHand`（:1008-1027）；contest-fidelity「held スパート used in the 全力 turn」多场 | `test_full_power_moves_held_cards_to_hand` / `test_leaf_snapshot_full_boundary_held_and_extra` |
| **指針守卫**：全力期间禁切指針（setStance 只允许 none）；のんびり期间禁切温存；全力值获得不受守卫影响 | `stance.stance_change_allowed`；`_apply_card_stance` / `_apply_direct_stances` / expectimax 双镜同守卫 | `BuffManager.setStance`（:258-265）；`resolveFullPowerCharge` 独立 | `test_stance_change_guards_match_set_stance` / `test_full_power_blocks_stance_changes_but_not_charge` / `test_leisure_blocks_preservation_card` |
| **のんびり倍率**：分数 ×0、费用 ×0 | `Stance.LEISURE` + `MULTIPLIER["leisure"]=0` + `stamina_cost_multiplier` leisure=0 | `resolveScore`（:168-169）/`resolveCost`（:56-57）；contest-fidelity「のんびり zero cost and zero score」 | `test_leisure_multipliers_are_zero` / `test_leisure_turn_zero_score_zero_cost` / `test_apply_card_full_guard_and_leisure_cost` |
| **のんびり解除**：固定元気+5 / +1 出牌 / 熱意+10；**→全力时熱意改为全体卡打分成长+10**（`target:all g.score+=10` 是 cardMap growth，每次出牌加进白值、永久、可叠加，不是即时分）；温存→のんびり不触发温存解除 | `release_on_stance_change` 扩 4 元组 `(熱意, 元気, 次数, 成长)`；`LessonSim.score_growth_all` / `ExpectState.score_growth_all`（canonical/快照往返/叶子双镜） | `constants.js STANCE_CHANGED_EFFECTS`（:57-68）；`CardManager.grow` + `targeting.js target:all`；wiki 熱意条「Nは温存１=5,温存２=8,のんびり=10」；contest-fidelity「leaving のんびり for 強気 元気+5 熱意+10 / for 全力 元気+5」「card growth applied at each switch」 | `test_leisure_release_to_non_full` / `test_leisure_release_to_full_is_card_growth` / `test_leisure_to_full_boundary_grants_growth` / `test_expect_award_includes_growth_all` |
| **卡牌来源（预约）**：`ExamOverPreservation`（主数据在 `ExamStatusEnchant.inner`，values 恒空）→ 出牌登记预约，回合开始按条件触发 setStance(leisure)：温存中触发（のんびり屋さん/休み休み、前へ/屋上からの景色，永久）/ 非温存触发（星々を見下ろす一番星，limit 3）；条件不成立不扣次数 | `CardSpec.leisure_reserve / leisure_reserve_when_save`；`stance.LEISURE_RESERVE_SOURCES`（卡 base id → 条件/次数证据表）；`LessonSim.leisure_reserves` / `ExpectState.leisure_reserves` + `_apply_leisure_reserves(_state)`；`sim_produce._effect_fields`（MODELED_EFFECTS 32→33）/ `play_choice._effect_fields`（旧 `ExamOverPreservation→preservation` 误映射移除） | 主数据 card_table 4 族 13 行 + BSD-3 `skill_cards.csv` 540-545/834 逐卡 DSL（日文卡名↔中文卡名用 card_meta 别名交叉）；contest-fidelity「のんびり屋さん's 温存→のんびり at each turn's start」「全力后 stance goes back to のんびり」 | `test_leisure_reserve_evidence_table` / `test_leisure_reservation_fires_at_turn_start` / `test_leisure_reserve_limit_variant_decrements` / `test_sim_produce_leisure_parse_real_cards` / `test_play_choice_leisure_spec` |
| **P 道具来源**：`ExamOverPreservation` → `stance_leisure` 直给（「悠闲变更/のんびりに変更」文本判定）；数据层 2 件标注（夜空を従える花 pitem_03-3-303-0/1），modifier 标注 **369→371 段**（已实现计数仍 1042：触发时机未支持） | `sim/p_items.py`（STANCE_EFFECT_TARGETS / classify / FLAG_TARGETS / STATUS_NAMES / delta.stances）；`scripts/build_p_items.py` 重标注重建 p_items.json | 参考 `p_items.csv` 419-420（`setStance(leisure); setEnthusiasmBuff(0.4,1); genki+=3`）；主数据 p_items.json 两件「悠闲变更」段 | `test_classify_exam_over_preservation` / `test_catalog_leisure_items_target_annotated` / `test_apply_passive_leisure_delta` / `test_lesson_sim_p_item_leisure_direct_and_release` / `test_fire_p_items_leisure_mirror` |

**口径与剩余差距（如实记录）**：

- **评测牌组组成不变**：4 族のんびり来源卡 score=0 或 SSR/Legend，本就不进 `build_pool`
  （score>0 过滤）；small/large 评测牌组逐张不变（`test_eval_deck_composition_unchanged` /
  `test_pool_excludes_leisure_cards`）。small 牌组无全力值卡（全力规则零触达）；large 有
  冲刺（全力值 1）但 9 回合攒满 10 概率低。**sim_engine_ab 重标定（P1-1）：改前/改后
  64 局逐位相同（差异=0）**——seed 9000/9100 各 16 局 rules/expectimax（budget 800ms），
  逐局非时间字段全等（新规则路径未触达）；expectimax 仍显著强于 rules（Δ+372.2 / +219.1
  评价点，C+ 100%，0 blocked / 0 error），B3 重标定结论保持。
- **保留区来源未建模**（holdCard/holdThisCard/holdSelected，P1-3）：`held` 当前恒空，
  回手钩子用合成保留牌验证；**指針固定 lockStanceTurns** 来源卡切磋琢磨含 holdSelected，
  随 P1-3 一并补（当前恒 0，全力进入门 `lockStanceTurns==0` 自然满足）。
- **2 件のんびり P 道具仍保守不触发**：触发时机 `card_play_interval_after`（强气卡每使用
  3 次后）是 B8 遗留未支持触发（`test_p_items.py::test_unsupported_trigger_is_noop` 锁定）；
  `stance_leisure` 目标机制本身就绪（合成 CARD_PLAY spec 全链路验证）。
- 预约时机近似：参考 `afterStartOfTurn`（抽牌后）/`startOfTurn`（抽牌前）两种预约在本模型
  都在抽牌后结算——期间无其它指針交互，观测等价；再演（encore）不翻倍预约（延迟效果非直接效果）。
- 旧 B11 数据/模型是**旧规则口径**（用户指定全保留不覆盖）：本批规则改动后阶段2 重采新 seed
  块练新批再新旧对比（HANDOVER_NEXT §8.0）；参照臂需按新规则重评。

### 5.5 P1-2 handDecrease 抽牌修正 + pride 自尊（2026-11-24 完成）

| 改动 | 文件 | 证据 | 回归 |
|---|---|---|---|
| **④ handDecrease 抽牌修正**：回合开始抽牌 `max(hand_size − Σ handDecrease, 0)`；timed 列表（按 turns 分组加算、回合末倒计时、∞ 永久）；**只减回合开始抽牌**，卡效果抽牌（ExamCardDraw）不受影响 | `LessonSim.hand_decreases` / `ExpectState.hand_decreases` + `turn_draw_count`；`_draw_hand` / `end_turn_state` / `fire_p_items` / beam 下一手 / `sim_from_state` 补手牌 / `state_from_sim` 双镜 + canonical | BSD-3 `TurnManager.startTurn`（:98-104 `cardsToDraw = Math.max(3 - getHandDecrease, 0)`）+ `BuffManager.setHandDecrease/getHandDecrease/decrementBuffTurns`（:39/:342/:242，handDecreases ∈ BUFF_LIST_FIELDS）；wiki `data/knowledge/buffs.json`「手札減少」（合算、≥3 抽 0、不影响效果抽牌）；参考单测 `BuffManager.test.mjs`「setHandDecrease draws fewer cards」 | `test_hand_decrease_reduces_turn_start_draw` / `test_hand_decrease_three_or_more_draws_zero` / `test_hand_decrease_stacks_by_amount` / `test_hand_decrease_timed_expires` / `test_hand_decrease_does_not_affect_card_draw` / `test_beam_next_turn_draw_uses_reduced_count` |
| **④ 来源**：`ExamGimmickStartTurnCardDrawDown` → `hand_decrease`（塔阶段 gimmick「手牌减少1（∞回合）」，exam_start，12 段 / 6 件初星灯光紫） | `sim/p_items.py`（HAND_DECREASE_EFFECTS / TARGET_BY_EFFECT / DURATION_TARGETS / PItemDelta.hand_decreases / `_apply_modifier_target`）；`build_p_items.py` 重标注（无需改代码，分类纯函数驱动） | 主数据 p_items.json 12 段（pitem_tower_001-…-stage_023/026 六族）；参考 DSL 无 setHandDecrease 用法（参考引擎标注 UNVERIFIED——机制按参考引擎实现，来源/数值按主数据 + wiki 口径，**不猜**） | `test_p_items_data_annotations` / `test_apply_passive_hand_decrease_delta` / `test_expect_state_fire_p_items_hand_decrease` |
| **⑤ pride 自尊计分**：`prideTurns>0` 时出牌分/回合末好印象在 resolveScore f 段加算 `min(min(好印象,干劲)×0.02, 0.5)`（千分比 `min(min×20, 500)`，与 score_buffs 累加后一次乘）；`prideTurns` 回合末 -1（EOT_DECREMENT_FIELDS，好印象结算之后）；score>0 门（纯 buff 牌不吃） | `LessonSim.pride_turns` / `ExpectState.pride_turns`；`_card_award` / `_end_turn` / `end_turn_state` / `fire_p_items` / `_apply_card_buffs` / `_apply_card_effects` 双镜 + canonical + 叶子快照对齐 | BSD-3 `resolvers.js::resolveScore`（:178-184）+ `constants.js` EOT_DECREMENT_FIELDS（:331）/ WHOLE_FIELDS（:415） | `test_pride_score_formula_min_and_cap` / `test_pride_zero_turns_no_effect` / `test_pride_only_positive_score` / `test_pride_applies_to_end_turn_impression` / `test_pride_turns_decrement_at_end_turn` / `test_pride_stacks_with_score_buffs` / `test_leaf_snapshot_aligns_with_end_turn_state` |
| **⑤ 卡牌来源**：「我、绝不」（p_card-02-ido-3_140，SSR/理性/偶像固有，4 强化变体）`ExamLessonValueMultipleDependReviewOrAggressive` turn=5 → `prideTurns+=5`；**条件门**出牌前干劲 >=9（主数据 trigger `e_trigger-none-card_play_aggressive_up-9` 结构化解析；未知 trigger 保守不给）；再演翻倍 | `CardSpec.pride_turns / pride_min_motivation`；`sim_produce._effect_fields`（MODELED_EFFECTS 33→34，35 元组）/ `play_choice._effect_fields` + `pride_min_motivation_from_trigger` | 主数据 card_table turn=5 / trigger …aggressive_up-9 ↔ BSD-3 `skill_cards.csv` 632/633「私は、決して」`if:motivation>=9, prideTurns+=5; cardUsesRemaining+=1; goodImpressionTurns+=8/9; drawCard`（pIdol 118「理論武装して」= 雨夜燕，idols.csv idolId 13 交叉） | `test_pride_card_source_gate` / `test_pride_card_gate_uses_pre_card_motivation` / `test_pride_card_no_gate_and_encore` / `test_sim_produce_pride_card_parse` / `test_play_choice_pride_card_parse` / `test_pride_trigger_gate_parser` |
| **⑤ P 道具来源**：「一笔入魂」/「一笔入魂+」（pitem_02-2-117-0/1，SR）`ExamLessonValueMultipleDependReviewOrAggressive` turn=2/3 → `prideTurns+=2/3` + 干劲+4/5；触发 status_gain（直接效果干劲增加后）& 好印象>=6 & limit:1（按道具计） | `sim/p_items.py`（PRIDE_EFFECTS / pride_turns target / PItemDelta.pride_turns）；`LessonSim._fire_p_items` / `expectimax.fire_p_items` 落状态 | 主数据 p_items.json（trigger status_gain aggressive / condition 好印象在6以上 / max_uses 1）↔ BSD-3 `p_items.csv` 354/355「一筆入魂」`at:motivationIncreased { if:isDirectEffect & goodImpressionTurns>=6 { prideTurns+=2/3; motivation+=4/5 }; limit:1 }`（pIdol 117「初志貫徹」= 雨夜燕）；isDirectEffect 语义=本模型 STATUS_GAIN 只从卡直接效果发射（P 道具给的干劲不触发） | `test_pride_p_item_source_real_data` / `test_pride_p_item_condition_blocks` / `test_pride_p_item_requires_direct_effect` / `test_pride_p_item_plus_variant` / `test_expect_fire_p_items_pride` / `test_apply_passive_pride_delta` |

**口径与剩余差距（如实记录）**：

- **评测牌组 / gkbench loadout 组成不变**：自尊卡 score=0 且 SSR，本就不进 `build_pool`；
  gkbench 688 个 loadout / 94 唯一道具 id **无「一笔入魂」（117）也无塔 gimmick（tower）**
  （塔 gimmick 是塔阶段专用，不在 hif 题模板）。**sim_engine_ab 重标定（P1-2）：改前/改后
  64 局逐位相同（差异=0）**——seed 9000/9100 各 16 局 rules/expectimax（budget 800ms），
  逐局非时间字段全等（新规则路径未触达）；expectimax 仍显著强于 rules（Δ+372.2 / +219.1
  评价点，15/0/1 与 11/0/5，C+ 100%，0 blocked / 0 error），B3 结论保持。
  数据层 implemented **1042→1056/1849 段**（+12 hand_decrease +2 pride_turns），
  modifier 标注 371→385；p_items.json 重建仅 14 条记录标注变化（逐条 diff 校验）。
- **nullifyDebuff 拦截**：~~未建模~~ ✅ **P1-4 已建模**（§5.7）——消耗式计数器拦截
  setScoreDebuff/setHandDecrease（P 道具侧 ExamAntiDebuff count 11 段）；卡侧 4 SSR 族
  values 恒空延迟、标量 DEBUFF_FIELDS/decreaseFullPowerCharge 拦截点留后续。
  `countDebuffs`（低下状態の数）参考+主数据零使用 → 无落点，保持未建模（§5.7）。
- **参考引擎 setHandDecrease 标注 UNVERIFIED**（未对真机截图核验）：机制按参考引擎
  实现、来源/数值按主数据 + wiki 口径；真机核验留阶段3（T6/D1）。
- **fresh buff 保护**沿用既有口径（P 道具 timed 列表回合末 -1，不做 fresh 跳过；
  当前 handDecrease 来源全是 exam_start 永久段，无差一回合问题）。
- 旧 B11 数据/模型是**旧规则口径**（用户指定全保留不覆盖）：阶段2 重采新 seed 块练新批
  再新旧对比（HANDOVER_NEXT §8.0）；参照臂需按新规则重评。

### 5.6 P1-3 hold 保留区建模 + lockStanceTurns 指針固定（2026-11-24 完成）

| 改动 | 文件 | 证据 | 回归 |
|---|---|---|---|
| **hold 保留区机制**：上限 2（超限最旧进弃牌堆）、跨回合保留（endTurn 只弃手牌）、holdThisCard 本牌不进弃牌/除外、holdSelected 从目标区选牌移入、moveHeldCardsToHand **LIFO** 回手（无手牌上限检查） | [sim/hold.py](../src/gkagent/sim/hold.py)（纯规则 + 证据表）+ [sim/lesson.py](../src/gkagent/sim/lesson.py)（`_apply_hold`/`_enforce_hold_limit`/`_move_held_to_hand`）+ [sim/expectimax.py](../src/gkagent/sim/expectimax.py)（`_apply_hold_state`，known_draw/discard_order 同步） | BSD-3 `CardManager/index.js` hold/enforceHoldLimit/holdCard/holdThisCard/holdSelectedByTarget/moveHeldCardsToHand（:959-1102）+ useCard thisCardHeld（:639）+ `TurnManager.endTurn` discardHand；contest-fidelity「held スパート used in the 全力 turn」 | `test_hold_limit_evicts_oldest_to_discard` / `test_held_persists_across_turns` / `test_hold_this_precedes_once_exclusion` / `test_full_power_held_lifo_order` / `test_hold_select_syncs_known_draw` / `test_hold_select_syncs_discard_order_and_limit` |
| **卡牌来源（13 族逐卡证据表）**：主数据 `ExamCardMove`（values 恒空）→ `hold.HOLD_SOURCES`（BSD-3 skill_cards.csv 行号交叉，card_meta 别名核对）：冲刺/积累（holdThisCard 温存中，trigger preservation_up 交叉）、潜在能力/互动的基础（holdSelected[hand]）、切磋琢磨/觉悟/新的舞台/努力了，哦/那一天，在这里/对战请多指教！/让群星散落吧（holdSelected[deck\|discarded]，那一天 +/++/+++ 2 张）、爱意彩虹（holdSelected[deck]）、一点一滴的进步（moveHeldCardsToHand） | [sim/hold.py](../src/gkagent/sim/hold.py) `HOLD_SOURCES`/`hold_source_for` + [scripts/sim_produce.py](../scripts/sim_produce.py)（MODELED 34→35 StanceLock、41 元组）+ [sim/play_choice.py](../src/gkagent/sim/play_choice.py)（生产卡表同口径） | skill_cards.csv 372/373/388/389/416/417/424/425/444/445/486/487/492/493/526/527/528/529/498/499/847/848/917/918；主数据卡面文本（那一天 ++/+++「2张」）；**表外卡保留旧 +1 抽牌近似**（潮流领袖/展翅高飞/发挥本领：全力值消耗/holdSelectedUpto/target:held 成长未建模；决不停歇：干扰卡计数条件；其余参考无对应行） | `test_sim_produce_hold_parse_real_cards` / `test_play_choice_hold_parse_parity` / `test_unverified_cards_keep_approx_draw` / `test_pool_hold_cards_fields` |
| **lockStanceTurns 指針固定**：`StanceLock` turn=N（切磋琢磨）→ lock_stance_turns+=N；>0 禁切指針（setStance 守卫）+ 全力进入门不满足（全力值不消耗）；回合末 -1，**fresh 保护**（卡效果 0→正 的当回合末不扣 → 锁下一回合）；再演翻倍（直接效果）；全力解除不受守卫 | [sim/stance.py](../src/gkagent/sim/stance.py)（`stance_change_allowed(locked=…)`/`end_turn(locked=…)`）+ lesson.py/expectimax.py（lock 字段 + fresh 标记 + canonical + 快照往返 + 叶子） | `constants.js` EOT_DECREMENT_FIELDS / FULL_POWER_EFFECTS（`if:lockStanceTurns==0 & fullPowerCharge>=10`）；`BuffManager.setStance`（:262）/ decrementBuffTurns（freshBuffs 位）；`Executor/index.js`（:271-279）；skill_cards.csv 424/425 `lockStanceTurns+=1` ↔ 主数据 StanceLock turn=1 | `test_lock_stance_gain_real_card` / `test_lock_blocks_stance_change_mid_turn` / `test_lock_blocks_full_entry_next_turn_fresh` / `test_lock_expires_after_next_turn` / `test_lock_does_not_block_full_exit` / `test_lock_stance_encore_doubles` / `test_end_turn_locked_blocks_full_entry_keeps_charge` |
| **hold 区张数条件（B10 遗留 2 件）**：`p_card_search-hold` → zones ["held"]；实现的觉悟/±（pitem_03-3-078）trigger = 魅力刚刚好（p_card-03-act-1_038 ↔ ジャストアピール csv 380）使用后 + countCards[held]>=1 → 温存变更/温存阶段变更 + 全力值+2/+4 | [scripts/build_p_items.py](../scripts/build_p_items.py)（`_ZONE_MAP` hold→held）+ [sim/p_items.py](../src/gkagent/sim/p_items.py)（`PassiveState.held` + `_zone_count_matches`）+ lesson.py/expectimax.py（`_passive_state` held 投影） | BSD-3 p_items.csv 212/213 叶える覚悟（pIdol 74）`at:afterCardUsed { if:usedCardBaseId==380 & countCards[held]>=1 { setStance(preservation/preservation2); fullPowerCharge+=2/4; target:held {…} } limit:1 }`；主数据 trigger_id 结构化 | `test_zone_count_hold_condition_real_item` / `test_lesson_sim_hold_zone_count_item_fires` / `test_build_p_items_hold_zone_and_hotfix_parsed` |
| **hotfix 1 件（B10 遗留）**：咲季营养餐・改（pitem_02-3-309-0）trigger 后缀 `period810_hotfix` 证实为**非限定标记**（masterTrans ProduceCardSearch 描述表无此目标 + 中文触发句无卡限定 + 参考 DSL 无卡过滤，三源一致）→ 回合内每第 2 张卡：好印象+2 / 好印象强化+25%（limit 1） | [scripts/build_p_items.py](../scripts/build_p_items.py)（`_parse_search_filter` 白名单） | BSD-3 p_items.csv 404 咲季の完全食・改 `at:cardUsed { if:turnCardsUsed%2==1 { goodImpressionTurns+=2; setGoodImpressionTurnsEffectBuff(0.25) }; limit:1 }` | `test_hotfix_item_fires_on_second_card_per_turn` / `test_catalog_trigger_unknown_zero` |
| **温存 2 段階直给 preservation2**：「温存阶段变更」（value1=2）→ `setStance(preservation2)`（从任何指針直接 2 段階，区别于「温存变更」的 1 段階/同指針升级）；7 段重标注（实现的觉悟+/初星手办/圆润的春色/±/梦想中的星辉/±/强化滚轮桃） | [sim/p_items.py](../src/gkagent/sim/p_items.py)（classify/FLAG_TARGETS/delta.stances）+ lesson.py/expectimax.py（`_apply_direct_stances` preservation2 分支，过固定守卫） | BSD-3 p_items.csv 213 叶える覚悟+ / 167 はつぼしフィギュア / 234-235 まあるい春色 / 315-316 夢見る星 均 `setStance(preservation2)`；主数据 value1=2 | `test_preservation2_direct_stance_real_item` / `test_preservation2_blocked_by_lock` / `test_stance_effects_only_when_text_says_change`（更新） |

**口径与剩余差距（如实记录）**：

- **评测牌组组成变化（与 P1-1/P1-2 不同，如实记录）**：冲刺/积累 的 `ExamCardMove`
  从 **+1 抽牌近似**改为真实 holdThisCard（温存中保留自身，**不是抽牌**）→ draw 1→0。
  `eval_expectimax.build_deck("large")` 的「抽牌机制签名槽」改选 决不停歇（表外卡保留
  近似），冲刺/积累 让出槽位 → **large 牌组组成变化**（旧近似把保留当抽牌是高估，
  这是保真度修正）；**small 牌组（14 张基础卡）不变**。新 hold 规则在 eval_expectimax
  牌组零触达（large 无已建模 hold 卡）；`sim_engine_ab` 奖励池仍可采到冲刺/积累。
  **sim_engine_ab 重标定（P1-3）：改前/改后 64 局逐局对照**——见下方重标定数字。
- **选牌是玩家选择**：holdSelected 参考引擎由策略选牌（HeuristicStrategy.pickCardsToHold
  按「全新全力状态预览分」降序）；全新状态下依赖分/折算分恒 0，预览分 ≈ 白值 × 全力倍率
  × 回合倍率（对所有候选相同）→ 本模型按**白值分降序、稳定排序**（同分按区/位置序，
  deck 在前）确定性选牌，排序等价。
- **再演不翻倍 hold**：参考 hold() 按卡索引幂等（doubleCardEffectCards 重复 holdThisCard
  是 no-op）；holdSelected 重执行属策略选择，保守不翻倍。lockStanceTurns 是直接效果，
  再演翻倍（与 pride_turns 同口径）。
- **fresh 保护口径**：lockStanceTurns 按参考 freshBuffs 实现（获得当回合末不扣，锁下一
  回合）——「指针固定1回合」的卡面语义就是锁下一回合（全力进入门在回合开始检查，若当回合
  就扣完则固定毫无作用）。**一般 buff 的 fresh 差一回合缺口仍留真机核实**（§3），本字段
  例外是因为语义确定（切磋琢磨 ↔ DSL 424/425 交叉）。
- **保留区卡成长 target:held 未建模**（g.scoreTimes/g.score/g.cost）：新的舞台+（g.score+=5）、
  发挥本领（g.scoreTimes+=1; g.cost-=6）、实现的觉悟（g.scoreTimes+=1; g.cost-=2/-1）等——
  per-card 成长机制不在本批范围（与 P1-1 全体卡成长 score_growth_all 不同，那是规则触发的
  全局加算）；这些卡的 hold 本体已建模，成长段保守 no-op。
- **holdCard P 道具来源未建模**：那一天的塑料伞（pitem_03-3-048，holdCard(466)）/
  章鱼烧科幻小狗（pitem_03-3-168，holdCard(604) + target:604 成长）/ 彼此许下的约定
  （pitem_03-3-289，holdCard(638)）——主数据效果文本未结构化（hold 语义嵌在文本里），
  且伴随成长/条件交互；其中那一天的塑料伞在 gkbench loadout（hold 段当前 no-op）。
- **爱意彩虹整卡使用条件**（温存的时候可以使用）未建模（本模型卡总是可打出，既有口径）；
  hold 效果本身无条件（DSL holdSelected[deck],1 在卡动作里）。
- **nullifySelect 守卫未建模**（参考 holdSelectedByTarget 开头 `if (state[S.nullifySelect])
  return`；本模型无 nullifySelect 资源，同 ExamAntiDebuff no-op 口径）。
- 旧 B11 数据/模型是**旧规则口径**（用户指定全保留不覆盖）：阶段2 重采新 seed 块练新批
  再新旧对比（HANDOVER_NEXT §8.0）；参照臂需按新规则重评。

**重标定数字（P1-3）**：sim_engine_ab 改前（git stash）/改后 **64 局逐位相同（差异=0）**——
seed 9000/9100 各 16 局 rules/expectimax budget 800ms，逐局非时间字段全等
（`data/_p13_ab_compare.py`，不提交）。冲刺/积累 在这 64 局的培育奖励选择中未被采到，
池字段变化零触达（sim_engine_ab 用 14 张基础牌组 + 奖励池动态采牌，与 eval_expectimax
固定 large 牌组不同口径——large 牌组组成变化不影响本 harness）。expectimax 仍显著强于
rules（Δ+372.2 / +219.1 评价点，15/0/1 与 11/0/5，C+ 100%，0 blocked / 0 error），
B3 重标定结论保持。产物 out/_p13_ab_{before,after}_{9000,9100}.json（gitignore）。

### 5.7 P1-4 nullifyDebuff 低下状态无效拦截 + ⑦ ExamBuffConsumptionAdd / countDebuffs 评估（2026-11-24 完成）

| 改动 | 文件 | 证据 | 回归 |
|---|---|---|---|
| **nullifyDebuff 拦截**（P1-2 遗留）：`nullifyDebuff>0` 时拦截一次 debuff 施加并 -1（消耗式计数器，**无回合倒计时**，不在 EOT_DECREMENT_FIELDS）；本批拦截已建模的两个 DEBUFF_SPECIAL_ACTIONS：`setScoreDebuff`（score_debuffs 列表逐条）/`setHandDecrease`（hand_decreases 列表逐条） | [sim/p_items.py](../src/gkagent/sim/p_items.py)（`intercept_debuff_entries` 纯函数）+ [sim/lesson.py](../src/gkagent/sim/lesson.py)（`nullify_debuff` 计数器 + `_fire_p_items` 拦截）+ [sim/expectimax.py](../src/gkagent/sim/expectimax.py)（`ExpectState.nullify_debuff` + canonical + `fire_p_items` 拦截 + `state_from_sim`/`sim_from_state` + `end_turn_state` 携带） | BSD-3 `Executor/index.js` executeAssignment（:429 `if nullifyDebuff && DEBUFF_FIELDS.includes(lhs) → nullifyDebuff--; return`）/ executeCallAction（:507）/ executeSpecialAction（:545）；`constants.js` DEBUFF_SPECIAL_ACTIONS = setScoreDebuff/decreaseFullPowerCharge/setHandDecrease（:379）、nullifyDebuff ∉ EOT_DECREMENT_FIELDS；`BuffManager.initializeState`（:118 标量 0）；参考单测 `BuffManager.test.mjs`「nullifyDebuff blocks setHandDecrease」 | `test_intercept_*`（5 条纯规则）/ `test_nullify_blocks_score_debuff` / `test_nullify_blocks_hand_decrease` / `test_nullify_blocks_both_order` / `test_nullify_no_eot_decrement` / `test_lesson_expect_nullify_parity` |
| **nullifyDebuff 来源（P 道具侧）**：`ExamAntiDebuff` values.count → `nullify_debuff` 目标（主数据 P 道具侧有 count 值）；11 段：偷懒的毛巾（pitem_00-2-116-0，おさぼりタオル，舞蹈回合开始无效 1 次 limit1）+ 塔 gimmick 初星灯光/旗帜/道具 10 段（status_gain / card_play_interval 触发） | [sim/p_items.py](../src/gkagent/sim/p_items.py)（ANTI_DEBUFF_EFFECTS / TARGET_BY_EFFECT / `effect_value` 读 count / PItemDelta.nullify_debuff / `_apply_modifier_target`）；`build_p_items.py` 重标注（分类纯函数驱动） | 主数据 p_items.json 11 段 ExamAntiDebuff values.count；BSD-3 `p_items.csv` 317 おさぼりタオル `at:startOfTurn { if:isDanceTurn { fixedGenki+=4; at:turn { nullifyDebuff+=1; limit:1 } } limit:1 }`；塔 gimmick 主数据 trigger_id 结构化 | `test_classify_exam_anti_debuff` / `test_effect_value_reads_count` / `test_apply_passive_nullify_delta` / `test_catalog_anti_debuff_specs` / `test_real_item_towel_spec` / `test_anti_debuff_implemented_not_noop` |
| **⑦ ExamBuffConsumptionAdd 保持 no-op**（强化状态花费卡机制无落点）：参考语义 = `doubleBuffCostTurns`（processCost/checkCost 时 BUFF_FIELDS 花费 ×2，EOT 递减，∈ DEBUFF_FIELDS）；主数据 4 段（不息的风暴 pitem_03-3-345-0/1、迷倒世界的模样 pitem_01-3-349-0/1），gkbench 22 loadout | 无代码改动（classify_effect_target 返回 ""，no-op） | BSD-3 `Executor/index.js`（:463 `if doubleBuffCostTurns>0 && BUFF_FIELDS.includes(lhs) → rhsValue*=2`）+ `constants.js` EOT_DECREMENT_FIELDS/DEBUFF_FIELDS；`CardManager.useCard`（:654 buffCostConsumed 触发）+ `Executor.triggerChangeEffects`（:345 processCost 时 BUFF_FIELDS 减少 → buffCostConsumed=true）；主数据 4 段 ↔ `p_items.csv` 488/489 止まない嵐 / 500/501 世界を魅了する姿 `doubleBuffCostTurns+=1` | `test_exam_buff_consumption_add_classify_noop` / `test_buff_consumption_add_catalog_noop` |
| **countDebuffs 保持未建模**（低下状態の数，无落点）：参考 `BuffManager.countDebuffs`（:331，DEBUFF_FIELDS>0 计数 + scoreDebuffs/handDecreases 条目数，标注 **UNVERIFIED**）；参考全部 CSV + 主数据**零使用**（仅 removeDebuffs 用于「属于我的色彩」わたしらしい色 csv 534/535） | 无代码改动 | BSD-3 `BuffManager.js` countDebuffs / DEBUFF_LIST_FIELDS（:43）；`skill_cards.csv`/`p_items.csv`/`stages.csv` 等全部 CSV 无 countDebuffs 用法；主数据无 debuff 计数触发/效果 | `test_count_debuffs_no_landing_point` |

**口径与剩余差距（如实记录）**：

- **⑦ 为什么无落点**：`ExamBuffConsumptionAdd`（doubleBuffCostTurns）的作用是「以强化状态
  作为花费值的技能卡」花费翻倍。参考引擎确实有 **88 张 buff-cost 卡**（skill_cards.csv cost
  列含 `concentration-=3`/`motivation-=3`/`goodImpressionTurns-=2`/`fullPowerCharge-=2` 等），
  其中 6 张在 `build_pool`（潮流领袖/行走步调/齐声应援 ±）、潮流领袖在 eval large 牌组、
  gkbench hif 牌组 340 条 buff-cost 卡 entry。**但我们的卡模型不承载 buff 花费**：
  card_table.json 这些卡 `cost=0`（只提取了体力费）、`CardSpec` 无 buff_cost 字段、
  可用性/支付/buffCostConsumed 触发均未建模。要落地 doubleBuffCostTurns 必须先扩卡模型
  （buff 花费数据 + 可用性检查 + 支付消耗层数 + buffCostConsumed 时机），超出本批 bounded
  范围 → **保持 no-op，不猜**。机制语义/主数据 4 段/gkbench 22 loadout 已如实记录。
- **nullifyDebuff 卡侧来源延迟**：4 个 SSR 卡族（偶像之魂 p_card-00-men-3_003 /
  精确无比的标牌制作 p_card-01-ido-3_080 / 红叶下奔跑 p_card-00-sup-3_093 /
  甜蜜陷阱♡ p_card-02-ido-3_248，参考 skill_cards.csv 158/159/350/351/452/453/887/888
  `nullifyDebuff+=1`）主数据 `ExamAntiDebuff` **values 恒空**（同 P1-3 hold，需逐卡证据表
  从参考 DSL 取 count），且 SSR 不进 build_pool → 卡侧 `CardSpec.nullify_debuff` 延迟，
  本批只落 P 道具侧（count 有值）。`test_nullify_card_side_deferred` 记录此口径。
- **nullifyDebuff 拦截范围（如实）**：本批拦截已建模的两个 DEBUFF_SPECIAL_ACTIONS
  （setScoreDebuff/setHandDecrease，列表逐条消耗）。**标量 DEBUFF_FIELDS**（cost_increase/
  double_cost_turns/poor_condition_turns/lock_stance_turns 等）的拦截未建模——P 道具 delta
  把同类标量聚合（`delta.cost_increase += …`），丢失参考逐动作施加的粒度，无法忠实逐次消耗；
  `decreaseFullPowerCharge`（DEBUFF_SPECIAL_ACTIONS 之一）本模型未建模；lock_stance_turns
  是卡效果路径（切磋琢磨）非 P 道具 delta，亦未拦截。这些拦截点留待后续（评测零触达）。
- **拦截顺序近似**：参考按动作触发顺序逐条消耗；本模型 delta 批量聚合，固定按
  score_debuffs → hand_decreases 顺序拦截（评测无来源零触达，顺序差异不影响重标定）。
- **评测牌组 / gkbench loadout 组成不变**：nullifyDebuff 来源（偷懒的毛巾 P 道具 +
  塔 gimmick + 4 SSR 卡族）**评测零落点**——gkbench 688 loadout / 94 唯一道具 id
  **无 116（おさぼりタオル）也无 tower**（塔 gimmick 塔阶段专用）；build_pool 无
  ExamAntiDebuff 卡（SSR）。**sim_engine_ab 重标定（P1-4）：改前/改后 64 局逐位相同
  （差异=0）**——seed 9000/9100 各 16 局 rules/expectimax（budget 800ms），逐局非时间
  字段全等（新规则路径未触达）；expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，
  15/0/1 与 11/0/5，C+ 100%，0 blocked / 0 error），B3 结论保持。
  数据层 implemented **1056→1067/1849 段**（+11 ExamAntiDebuff），modifier 标注 385→396；
  p_items.json 重建仅 **11 条记录**标注变化（逐条 diff 校验，全是 ExamAntiDebuff target
  None→nullify_debuff）。
- 旧 B11 数据/模型是**旧规则口径**（用户指定全保留不覆盖）：阶段2 重采新 seed 块练新批
  再新旧对比（HANDOVER_NEXT §8.0）；参照臂需按新规则重评。

**重标定数字（P1-4）**：sim_engine_ab 改前（git stash）/改后 **64 局逐位相同（差异=0）**——
seed 9000/9100 各 16 局 rules/expectimax budget 800ms，逐局非时间字段全等
（`data/_p14_ab_compare.py`，不提交）。nullifyDebuff 来源评测零落点，新规则路径未触达。
expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，15/0/1 与 11/0/5，C+ 100%，
0 blocked / 0 error），B3 重标定结论保持。产物 out/_p14_ab_{before,after}_{9000,9100}.json
（gitignore）。

## 6. 最该补的差距（按对真机分数影响排序，留给 T5/T6）
1. ~~**审查倍率分段 + 联动惩罚**~~ ✅ **2026-11-22 完成**（§5.1：公式 + 主数据 + 屏幕倍率生产接线；
   剩余差距只在 P 道具/附魔等未建模项，倍率本身已对齐）。
2. ~~**熱意（enthusiasm）**~~ ✅ **2026-11-22 T5② 完成**：独立整数资源（出牌分加算 +
   温存解除 +5/+8 等来源 + 熱意追加/増加/延長/本牌適用倍数卡牌效果 + 回合末清零/延長）；
   见 §5.2。~~剩余来源（のんびり/P 道具）未建模~~ のんびり来源 ✅ **P1-1 完成**（§5.4）；
   P 道具熱意触发仍未接入。
3. ~~**温存解除的额外出牌次数/元气**~~ ✅ **2026-11-22 T5② 完成**：+1 出牌次数、2 段 +5 固定元気、
   同回合重复解除可叠加；见 §5.2。~~全力回合額外次数/保留牌仍未建模~~ ✅ **P1-1 完成**（§5.4；
   保留区来源 holdCard/holdThisCard 留 P1-3）。
4. **fresh buff 保护**（差一回合）：好调/好印象/绝好调持续时间可能整体少 1 回合，需真机逐回合截图核实。
5. ~~**P 道具数据接入**~~ ✅ **2026-11-22 T5③ 完成（§5.3）**：gkbench/离线 loadout 的
   `produce_item_ids` → `PItemSpec` 已接入模拟器/评测/提交；exam_start 与 extra_plays 新支持；
   **B7（T9）已把 catalog 补到上游 1115 件、gkbench 未知 id 清零**（1068→1115 件、
   spec 1764→1849、已实现 421→445；新增 47 条条件未解析段保守不触发）。
   **B8（T5④，2026-11-22）完成条件/效果语义第一批**：新语法 trigger id 结构化解析
   （条件未知 22→6 件）+ 依赖换算「X 的 N% 数值变为 Y」（65 段）+ 固定/百分比体力
   （9 段）+ 「X 变为 0」（3 段）+ 5 类新触发时机；数据层 445→**676/1849 段**、
   gkbench 34→**59/153 段**；greedy 配对 A/B **+225.2（CI [+86.7,+363.6]）**。
   **B9（T5④ 第二批，2026-11-22）完成持久倍率/modifier 类**：打分上升量增加/减少
   （`resolveScore` f/g）、好印象强化/追加发动、热意/集中/好印象/干劲/全力值增益倍率、
   绝好调/不调、费用修正（加减 + ×0.5/×2 回合）、回合追加、温存/强气指針直给；
   数据层 676→**1025/1849 段**、gkbench 59→**103/153 段**；greedy 配对 A/B
   **+110.3（CI [+39.6,+193.3]）**。
   **剩余**：~~生成卡（`ExamCardCreateId`）~~ ✅ **B10 确定式已实现**（随机基础卡 RNG 未知保持 no-op）、
   强化状态花费卡（`ExamBuffConsumptionAdd` 无落点，保持 no-op；**P1-4 评估**：卡模型不承载
   buff 花费，88 张参考 buff-cost 卡 card_table cost=0，见 §5.7）、
   ~~指定卡名/手牌张数限定~~ ✅ **B10 已结构化**（触发未知 103→3 件：hold 保留区 2 + hotfix 1）、
   fresh buff 差一回合、真机培育侧列表（T6/D1 补采）、主道具附魔/回忆。
   **B10（T5 剩余①②，2026-11-23）**：card_meta（idol_unique 参考交叉 340/342 零误报 +
   effectGroupIds）+ parse_card_search（play_filter 234 件 / zone_count 27 件）+ 生成卡
   11 段确定（手牌/牌堆顶/弃牌堆，手牌≥5 不生成）；条件未知 6→0；数据层 1025→**1042/1849 段**；
   次数上限按道具计（limit:N 口径修正）；greedy 配对 A/B **+797.5（+20.76%，
   CI [+399.0,+1250.1]）** / expectimax **+801.1（CI [+66.3,+1697.9]）**。
6. **考试内生成卡/额外 RNG 机制**：~~生成卡确定式~~ ✅ B10（卡名→id + addCardTo* 语义）；
   **随机式（H.I.F应援棒）与 panic/search/move 的 RNG 流仍未知**（T6 补采；`exam_risk` 事前检测不变）。
7. **好印象/元气依赖分是否吃倍率**：参考引擎说明会吃；模拟器真实倍率路径（T5①）已按「吃」实现，
   生产读屏走单标量路径时仍保守（两条路径口径不同，见 §2 表）。逐分实机核对等 P 道具/附魔补齐。
8. **抽牌上限 5 / ~~handDecrease~~ / ~~保留牌来源（holdCard/holdThisCard）~~**：
   ~~handDecrease~~ ✅ **P1-2 完成**（§5.5：cardsToDraw=max(3−Σ,0) + 塔 gimmick 12 段来源；
   nullifyDebuff 拦截 ✅ **P1-4 完成**，见 §5.7）；抽牌上限 5 仍 ⚠️（只有抽牌卡溢出时才不同）；
   ~~保留区来源~~ ✅ **P1-3 完成**（§5.6：holdThisCard/holdSelected/moveHeldCardsToHand
   13 族卡证据表 + 上限 2 + 跨回合保留 + 全力回手 LIFO；hold 区张数条件 + hotfix 清零；
   剩余 target:held 成长 / holdCard P 道具来源未建模）。
9. ~~**自尊 pride**~~ ✅ **P1-2 完成**（§5.5：resolveScore f min(好印象,干劲)×0.02 上限+0.5 +
   卡「我、绝不」/ P 道具「一笔入魂」来源，主数据+参考 DSL 交叉）；
   **growth 成长表 / 支度→披露半场翻转**仍缺（小项；のんびり→全力 的全体卡成长
   P1-1 已按规则实现，见 §2 growth 行）。
10. ~~**指針固定 lockStanceTurns**~~ ✅ **P1-3 完成**（§5.6：切磋琢磨 StanceLock turn=1，
     EOT 递减 + fresh 保护锁下一回合 + setStance 守卫 + 全力进入门）；
     **card_play_interval_after 触发时机**（2 件のんびり道具「夜空を従える花」因此仍保守
     不触发；stance_leisure 目标机制本身就绪）/ **target:held 保留区卡成长**（P1-3 遗留）。
11. ~~**nullifyDebuff 低下状态无效拦截**~~ ✅ **P1-4 完成**（§5.7：消耗式计数器拦截
      setScoreDebuff/setHandDecrease，P 道具侧 ExamAntiDebuff count 11 段，implemented
      1056→1067）；**卡侧 4 SSR 族来源**（values 恒空需逐卡证据表）/ **标量 DEBUFF_FIELDS
      拦截**（delta 聚合丢失逐动作粒度）/ **decreaseFullPowerCharge**（未建模）留后续；
      **⑦ ExamBuffConsumptionAdd / countDebuffs 保持 no-op**（卡模型不承载 buff 花费 /
      低下状態の数参考+主数据零使用，无落点，P1-4 评估如实记录）。

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

# T5② 熱意 + 温存解除（纯规则 / LessonSim / ExpectState 镜像 / 生产卡表映射）
.venv\Scripts\python.exe -m pytest tests\test_t5_enthusiasm.py -q

# P1-1 全力回合 + のんびり指針（纯规则 / 双镜 / 解析 / P 道具 / 叶子快照）
.venv\Scripts\python.exe -m pytest tests\test_p1_stance_rules.py -q
.venv\Scripts\python.exe scripts\build_p_items.py --check  # modifier 标注 371（stance_leisure 2；已实现仍 1042）
# P1-1 重标定（评测牌组无のんびり来源、small 无全力值卡 → 实测改前/改后 64 局逐位相同）
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --seed 9000 --out out\sim_engine_ab_p1.json

# P1-2 handDecrease + pride（纯规则 / 来源 / 双镜 / 解析 / 叶子快照）
.venv\Scripts\python.exe -m pytest tests\test_p12_hand_decrease_pride.py -q
.venv\Scripts\python.exe scripts\build_p_items.py --check  # modifier 标注 385（+hand_decrease 12 / pride_turns 2；已实现 1056）
# P1-2 重标定（评测牌组/gkbench loadout 无来源 → 实测改前/改后 64 局逐位相同）
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --seed 9000 --out out\_p12_ab_after_9000.json
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --seed 9100 --out out\_p12_ab_after_9100.json

# P1-3 hold 保留区 + lockStanceTurns（纯规则 / 来源 / 双镜 / P 道具 / 解析 / 叶子快照）
.venv\Scripts\python.exe -m pytest tests\test_p13_hold_zone.py -q
.venv\Scripts\python.exe scripts\build_p_items.py --check  # 触发未知 3→0；preservation2 7 段；已实现仍 1056
# P1-3 重标定（冲刺/积累 draw 近似移除 → large 牌组组成变化；改前/改后 64 局逐局对照）
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --seed 9000 --out out\_p13_ab_after_9000.json
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --seed 9100 --out out\_p13_ab_after_9100.json

# P1-4 nullifyDebuff 拦截 + ⑦/countDebuffs 评估（纯规则 / P 道具解析 / 双镜 / no-op 记录）
.venv\Scripts\python.exe -m pytest tests\test_p14_nullify_debuff.py -q
.venv\Scripts\python.exe scripts\build_p_items.py --check  # nullify_debuff 11 段；已实现 1056→1067
# P1-4 重标定（nullifyDebuff 来源评测零落点 → 实测改前/改后 64 局逐位相同）
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --seed 9000 --out out\_p14_ab_after_9000.json
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --seed 9100 --out out\_p14_ab_after_9100.json

# T5③ P 道具数据接入（catalog / loadout 解析 / exam_start / extra_plays / 提交适配器）
.venv\Scripts\python.exe -m pytest tests\test_p_items.py tests\test_p_items_db.py tests\test_p_items_integration.py -q
.venv\Scripts\python.exe -m pytest tests\test_gkbench_submission_p_items.py -q
# T5④ P 道具效果语义（B8 条件/第一批 + B9 持久倍率/modifier）
.venv\Scripts\python.exe -m pytest tests\test_p_items_b8.py tests\test_p_items_b9.py -q
# P 道具 A/B（hif 题模板；auto=按 loadout 接入，off=不结算）
.venv\Scripts\python.exe scripts\local_bench.py --problems data\bench_local\problems_hif.json --sample 30 --episodes 2 --algos greedy,expectimax-analytic --budget-ms 100 --p-items off --out data\bench_local\ab_pitems_off_b9.json
.venv\Scripts\python.exe scripts\local_bench.py --problems data\bench_local\problems_hif.json --sample 30 --episodes 2 --algos greedy,expectimax-analytic --budget-ms 100 --p-items auto --out data\bench_local\ab_pitems_auto_b9.json
```

## 许可

`gakumas-tools` 是 **BSD-3-Clause**：本表引用的公式/常量与实机回放值需保留版权声明；
我们只引用口径并重写实现，不拷贝代码。

T5① 的「分段折线 + 联动惩罚 + `normalize_bonus`/`battle_bonus_score` 算术语义」参考了
`hiro-gakumas-hero`（AGPL-3.0，`data/hiro/` 仅本地参考）里 `vendor/.../gakumas_produce/
attributes.py` 从其客户端反编译还原的实现；我们**按语义重写**（`src/gkagent/sim/exam_multiplier.py`），
没有把 AGPL 代码拷进本项目。主数据（`ProduceExamBattleConfig` 等）来自社区 gakumasu-diff 快照，
夹具只保存计算结果的回归快照（见 `tests/fixtures/t5_exam_multipliers.json` 的 `source` 字段）。
