# 官方 AI 研读笔记：`gkbench/algos/official_ai.py`

> 阅读对象：`data/bench_repo/gkbench/algos/official_ai.py`（448 行，24 KB，MIT）。
> 对照实现：`src/gkagent/sim/expectimax.py`、`docs/EXPECTIMAX.md`。
> 阅读日期：2026-11-19。本文只做机制/工程分析，不复制官方 AI 代码。

## 摘要（给赶时间的人）

1. 官方 AI 的真实搜索/评估内核在 GKMS 私有仓库 `GKMSContest/official_ai`；本文件
   只是宿主桥。**能确认**的是搜索帧、50+ 评估特征、2 回合/20 万命令预算、计划
   重放、选牌评估、触发差分预测；**不能确认**的是评估权重和目标函数。
2. 它不是「元气/好印象/指针按固定优先级」的规则 AI。桥里没有写死顺序，而是把
   这些量拆成独立特征喂给评估表（元气还带限制项，好印象带层/强化/锁定，指针带
   段阶/切换次数/累计全力值）。真正的权重在 `ai_master/current`，本机没有。
3. 最值得借的 5 条：**计划重放 + 局面键校验**（H1）、**固定搜索预算**（H2）、
   **累计层 × 剩余回合**（H4）、**选牌评估器**（H7）、**动作剪枝**（H10）。
   完整 10 条见第 2 节。
4. 它比纯搜索合理的地方：限深 + 命令预算 + 选牌评估器 + 计划重放，专门对付
   搜索爆炸；它比我们强的地方：50+ 特征的考试评估、真实牌序、原生效果预测。
   我们比它强的地方：公开信息下的精确抽牌机会节点、CLEAR/PERFECT 档位效用、
   纯 Python 可托管。
5. 目前最大的分数缺口：P 道具/回忆/附魔、定制/成长、饮料、考试减益、选牌。

## 0. 先划边界：我们读到的是「桥」，不是「大脑」

`official_ai.py` 开头写得很清楚（第 1–20 行）：官方 AI 的搜索与评估在 GKMS 的
`GKMSProject/GKMSContest/official_ai` 里，那是**私有、无许可证**的仓库；本文件只实现
`SequenceHost` / `EvaluationHost` 两个接口，把 GKMS 原生考试会话喂给官方 AI。

本机没有 `GKMSProject` / `GKMSContest`（检查过 `D:\Games`、`%USERPROFILE%\github\_ext`，
只有空的 `data/GKMSUINet` 克隆），所以：

- 能确认：**状态特征、搜索深度/预算、动作空间、计划重放、效果预测方式**；
- 不能确认：评估表的**具体权重**、叶子目标函数（期望分？评价分？名次？）、
  搜索内核（最佳优先/GNRPA/αβ？）、选牌评估器的具体打分公式。
- 评估权重来自 `ai_master/current` 配置表（第 44–55 行），不在本仓库里。

因此下面的结论分两档：**[可见]** = 桥里直接看得到、行号可查；**[反推]** = 从它要求
宿主提供的特征推断设计取向，不能当成官方实现细节。

---

## 1. 决策流程（每一步到底做什么）

### 1.1 开局

1. `official()` 载入官方 AI 包和配置表 `ai_master/current`（第 44–55 行）。
2. `exam_effect(ctx.loadout["idol_card_id"])` 从 `IdolCard.jsonl` 读偶像卡的
   `examEffectType`（第 87–98 行），作为评估表的分组键；`begin` 里把它传给
   `NativeHost(main_effect=...)`（第 414–417 行）。
3. 记录 `ctx.loadout["produce_item_ids"]`（第 417 行）——P 道具的身份也参与评估
   （`evaluation_state` 的 `resource_item_ids`，第 300–310 行）。
4. `create_official_search(host, configuration)`（第 418–419 行）创建官方搜索器。

### 1.2 每个决策点：先看计划还能不能照走

`OfficialAIAlgo.decide`（第 440–448 行）：

```
当前局面 search_key  ==  计划首项的期望 key ？
  是 → 直接弹出并执行计划里的下一个动作（含选牌动作）
  否 → _replan() 重新搜一整段
```

- 计划项不是单个动作，而是 `(动作, 执行前局面 key)`；选牌动作会插在 `play` 之前
  （第 422–435 行）。
- 重搜时会克隆**真实局面**（`ctx.true_session.clone()`，第 424 行），清空搜索历史，
  在 `command_budget=200000` 下跑 `self.search.search(...)`（第 427 行）。
- 返回的 `selected.sequence._oa_hist` 被展开成 plan；同时记录
  `solve_seconds / leaves / expanded / steps / evaluate_score / path_len`（第 436–438 行）。

这是「**搜索一段 + 重放 + 局面不符再重搜**」的混合策略，不是每一步都从头搜。
`sees_seed = True`、`needs_gkms = True`（第 405–408 行）也说明它看的是真实牌序/
真实局面，不是公开信息下的平均世界。

### 1.3 搜索帧与动作空间

- 搜索帧 `SearchFrame(phase, turn, remaining_turns, plan_type, main_effect, score)`
  （第 149–151 行）：`phase` = 考试中 6 / 已结束 8；`main_effect` 是偶像卡
  `examEffectType`；`score` 是当前分。
- 手牌可用性由原生 `legal_actions()` 决定（第 153–157 行）。
- 动作只有 `use_hand(index)` / `end_turn()`（第 159–163 行）；原生 `step` 一次推进到
  下一个决策点，所以 `run_to_decision` 是空实现（第 165–167 行）。
- **不喝饮料**（第 14 行）：比赛 AI 没有饮料，直接把这个动作从搜索空间删掉。
- 搜索预算是 `command_budget=200000`（第 410、427 行），不是墙钟时间；官方 AI 的
  搜索深度是「往后两回合内的出牌顺序」（第 3 行）。
- 选牌（检索/生成/从山札选卡）**不展开组合搜索**：在克隆上试打拿到候选，交给
  `OfficialCardSelectCalculator` 逐张打分，`select_cards_by_auto_evaluation` 选
  top-k，再排队真打；一次动作最多循环 16 层选牌（第 168–190 行）。

### 1.4 局面评估接口

`NativeHost` 实现 `EvaluationHost`（第 219–334 行），把原生局面翻译成官方 AI 的
`EvaluationState`：

- `frame`：阶段、回合、剩余回合、plan、偶像 examEffectType、当前分（149–151）。
- 基础数值：`parameter`（分数）、`block`（元气）、`stamina`、`remaining_turns`
  （第 268–271 行）。
- buff/状态：`lesson_buff`（集中）、`review`（好印象）、`aggressive`（やる気）、
  `parameter_buff_turns`（好调剩余回合）等（第 272–288 行）。
- 资源/次数：`playable_value_add_count`（额外出牌次数）、`extra_turns`、
  `hold_count`（保留区张数）、`total_effect_draw_card_count`、`anti_debuff_count`、
  `stance_lock`（第 289–298 行）。
- 指针：`idol_status_type`、`idol_status_step`、`full_power_point_get_sum_count`、
  三种 `stance_*_change_count`（第 291–295 行）。
- 累计层：`accumulated_statuses` 槽位 33–44（第 105–118、234–260、298 行）。
- 资源卡/道具/成长：`resource_card_ids`（手/山/弃/除外/保留全部卡的 id）、
  `resource_item_ids`、`card_growth`（第 300–310 行）。
- 触发效果：`trigger_statuses` 只收「技能卡来源」的持续效果和直接定时效果
  （第 312–331 行）；每条触发再用 `_Resolver` 在克隆上逐条执行、记前后差值
  （第 345–400 行）。

---

## 2. 官方 AI 的启发式清单（可直接借用）

以下 10 条按「迁移到我们的 expectimax 的收益/成本」排序，最后附 1 条可选。
行号均指 `gkbench/algos/official_ai.py`。

### H1. 计划重放 + 局面键校验（而不是每步重搜）

**位置**：第 403–448 行（`decide` / `_replan`），第 430–435 行（plan 构造），
第 443–447 行（key 比较）。

**做法**：一次搜出整段出牌路线，执行时只弹出下一步；只有当前局面的
`search_key` 和计划里记录的期望 key 不一致，才重新搜索。选牌动作被插在
`play` 前面，所以「选哪张」也属于计划的一部分。

**借到我们这里**：`expectimax.py` 已经有 `best_turn_sequence()`（第 1526–1553 行）
和 `search_beam()`（第 1706–1847 行），但真机/live 决策仍是一步一搜。可以：

1. 第一次决策时用 `best_turn_sequence` 算本回合的整段序列；
2. 把剩余序列和「执行前状态指纹」缓存起来；
3. 后续每一步先比对公开观测的指纹（turn/score/stamina/hand ids/status），一致就照走，
   不一致再重搜。

收益：每回合搜索次数从「每张牌一次」降到「每回合一次」，而且不会因为抽牌后
期望值微调而在两张近似牌之间来回抖。风险：观测指纹必须包含足够多的字段，
否则会在「局面已经变了」时错误照走。

### H2. 固定搜索预算：深度 2 回合 + 命令数上限

**位置**：第 3 行（「往后搜两回合内」），第 410、427 行（`command_budget=200000`）。

**做法**：不按墙钟做 anytime，而是按**命令展开数**给预算；深度也限死在 2 回合。

**借到我们这里**：`ExpectimaxConfig` 同时有 `max_nodes` 和 `time_budget_ms`
（第 296–307 行），当前默认是 20 万节点 + 800 ms。可以：

- 比赛/评测用 `max_nodes` 做主预算（可复现、跨机器公平）；
- 真机再用 `time_budget_ms` 做硬上限；
- 对跨回合 beam，显式限制深度（官方是 2 回合，我们 `search_beam` 可配置）。

收益：可复现、不会被机器性能影响排名；也避免「对手牌少时搜得深、牌多时搜不动」
的预算漂移。风险：命令数上限对不同分支因子的牌组不等价，需要按题集调。

### H3. 搜索帧带上 plan / 偶像卡 effect / 剩余回合 / 当前分

**位置**：第 149–151 行（`SearchFrame`），第 87–98、416 行（`main_effect`）。

**做法**：评估不是只看 `ExpectState`，而是把「方案（plan）、偶像卡考试效果类型、
剩余回合、当前分」一起作为搜索帧。评估表按 `main_effect` 分组
（第 88 行注释：「官方 AI 的评估表按它分组」）。

**借到我们这里**：`AnalyticLeafValue.predict`（第 383–397 行）只看
`ExpectState`，没有 plan/idol 维度；所有卡组共用同一套 `μ` 公式。可以给
`AnalyticLeafValue` 增加一个 `profile` 参数（sense / logic / anomaly / 偶像卡
effect 类型），不同的 profile 用不同的：
- `condition_multiplier`（好调价值）；
- `impression` 年金权重（好印象 vs 集中）；
- `playable_count` 的体力/费用折现。

收益：感性/理性/非凡的出牌节奏本来就不同（集中 vs 好印象 vs 指针）。风险：需要
标签数据或人工先验；没有数据时容易过拟合。

### H4. 把「累计层 × 剩余回合」做成评估特征

**位置**：第 105–118 行（`_ACCUMULATED` 槽位 33–44），第 234–260 行
（`_layer_rows`），第 298 行（`accumulated_statuses`）。

**做法**：官方 AI 不只记录「当前层数」，而是记录**每一层**的
`(千分比数值, 剩余回合)`，覆盖：

- `lesson_parameter_multiple_layers`（打分上升量增加）
- `review_multiple_layers`（好印象强化）
- `enthusiastic_additive_layers` / `enthusiastic_multiple_permil`（热意）
- `full_power_lesson_multiple_additive_layers`（全力强化）
- `concentration_lesson_multiple_additive_layers`（强气强化）
- `lesson_buff_additive_multiple` / `parameter_buff_additive_multiple`
- `aggressive_additive_multiple` / `review_additive_multiple`
- `full_power_point_additive_layers`

**借到我们这里**：`AnalyticLeafValue.impression_annuity`（第 368–380 行）已经做了
好印象年金，但其它层（`review_multiple`、`full_power_lesson_multiple`、
`lesson_parameter_multiple`）没有进入未来收益。可以把 `ExpectState` 里已有的
`review_multiple(_turns)` / `full_power_lesson_multiple(_turns)` 也做成年金：

```
value = 层数 × (剩余回合数 + … + 1)    # 永久层按 turns_left 封顶
```

收益：这些层在考试里经常是几倍分数，忽略会把「先铺层还是先打大牌」判断反。
风险：层的实际衰减/消耗规则因效果而异，年金只是上界；要按 `turns=-1`（永久）
和有限回合分开算。

### H5. 永久状态用 `INF_TURNS`，并与剩余回合取小

**位置**：第 34 行（`INF_TURNS = 1 << 20`），第 220–232 行（`_left` / `_flag_left`）。

**做法**：`until == -1` / `inf` 的状态剩余回合记为 `INF_TURNS`；真正参与评估时
再和 `remaining_turns` 取小。这样「永久」既不会在倒计时里被减没，也不会在评估里
被当成无限大。

**借到我们这里**：`ExpectState` 的 `review_multiple_turns` /
`full_power_lesson_multiple_turns` / `condition_additive_turns` 有 `-1 = 永久`
哨兵（`_tick_turns`，第 589–591 行），但 `AnalyticLeafValue` 只对 `impression`
做年金，其它层没有统一处理；`condition_turns` 不走 `_tick_turns`，回合结束直接
-1 到 0。建议在 state → leaf 的适配层统一把 `-1` 换成 `min(turns_left, ...)`，
不要直接丢 0。

### H6. 触发效果「差分预测」，且只算技能卡来源

**位置**：第 312–331 行（`trigger_statuses`），第 345–400 行（`_Resolver` /
`affect_effect`），第 16–20 行（与原生实现的差异说明）。

**做法**：

1. 只收 `trigger_effect_states` 里「技能卡来源」的持续效果（从 enchant id 的
   `enchant-p_card-` 反推）和 `effect_timer_queue` 里的**直接**定时效果；
   `~` 开头的是持续效果/P 道具装的间接定时效果，不算卡来源（第 326–331 行）。
2. 对每条效果，在局面的克隆上执行一次（`bx_apply_effect`），前后 snapshot
   对比 `parameter / stamina / block` 和 `_PAIR_SLOT` 里的 30+ 状态槽，记一条
   `EffectDifference`（第 353–400 行）。

**借到我们这里**：

- 我们的 `p_items.py` 是「按 P 道具类型查表」的静态模型，未知类型 no-op；
  官方 AI 的做法是「在局面上实际执行一条效果，看差分」——更不容易漏机制。
  但这条路需要 GKMS 原生核心，和 `needs_gkms=False` 冲突；只适合我们自己的
  真机/离线全引擎，不适合 gkbench 托管提交。
- **可借的是「来源过滤」**：评估未来收益时，卡牌来源的持续效果和 P 道具/回忆
  来源的效果分开算，避免同一层被两条路径重复计入。

> 注：H6 的「差分执行」是**有条件借用**（需要全引擎）；其余 9 条是纯评估/剪枝
> 逻辑，gkbench 适配器可以直接借。

### H7. 选牌用评估器，不展开组合搜索

**位置**：第 128–134 行（`OfficialCardSelectCalculator`），第 168–190 行
（`_step` 的试打/排队），第 213–217 行（`selection_context`，含保留区）。

**做法**：检索/生成/从山札选卡时，不枚举「选哪 k 张」的组合，而是在克隆上
试打出候选，用评估器逐张打分，按分数选 top-k。

**借到我们这里**：`sim_produce.py` 对 `ExamForcePlayCardSearch` /
`ExamCardCreateId` / `ExamCardMove` 的近似是「至少 +1 抽牌」（第 190–195 行），
遇到「从 5 张里选 2 张」会低估资源价值。可以写一个小的选牌评估器：

```
score(card) = 卡面分 + 集中/好调/好印象的边际收益 + 费用/体力惩罚
```

在 `apply_card` 的选牌分支里按 top-k 选，而不是固定抽 1。

收益：检索/生成类卡的期望更接近真机；也避免「选牌分支 × 出牌分支」的组合爆炸。
风险：评估器本身要维护，选错牌会引入偏差。

### H8. 额外次数 / 额外回合 / 保留 / 抽牌数作为显式特征

**位置**：第 289–296 行（`playable_value_add_count`、`extra_turns`、`hold_count`、
`total_effect_draw_card_count`），第 213–217 行（保留区参与选牌上下文）。

**做法**：这些「资源/节奏」量不是搜索的副产物，而是评估的独立特征。

**借到我们这里**：

- `ExpectState` 有 `extra_plays` / `plays_left`（第 221–222 行），但
  `AnalyticLeafValue.playable_count` 只用 `plays_left` 和体力，没有把
  「多一张可出牌」折算成分数价值；`_action_tiebreak`（第 1222–1230 行）只在
  打平时比较剩余出牌位。
- `hold` 区我们完全没有进 `ExpectState`；考试里保留牌可以通过效果回手，价值不低。
- `extra_turns` 在 gkbench 里已经折进 `exam.limit`（适配器用
  `limit - turn + 1`），但跨回合 beam 没有显式价值。

建议：在 leaf 里给 `extra_plays × 平均单牌期望` 一个正价值；`hold_count` 先按
「每张保留牌 = 一张手牌的价值 × 折扣」近似。

### H9. 指针变化次数 / 全力值累计作为特征

**位置**：第 113 行（`_STANCE`）、第 291–295 行（`idol_status_type`、
`idol_status_step`、`full_power_point_get_sum_count`、三个
`stance_*_change_count`）、第 297 行（`stance_lock`）。

**做法**：指针不是「当前倍率」一个数，而是 `(类型, 段阶, 切换次数, 全力值累计,
锁定回合)` 的组合。切换次数会影响某些卡的收益（例如「每切换一次 +N」），
全力值累计则是「全力」回合的启动资源。

**借到我们这里**：`StanceState`（`sim/stance.py`）目前只有
`(stance, strong_level, save_level, full_power_point)`，没有切换次数/累计值。
`ExpectState.stance` 也只冻结这四项。如果卡池里有「依赖切换次数/累计全力值」的
效果，现在的模型会低估。短期可以只在适配层记录，长期要扩 `ExpectState`。

### H10. 动作剪枝：官方 AI 直接不喝饮料

**位置**：第 14 行（「它不喝饮料（比赛 AI 没有饮料）」）。

**做法**：不是评估后觉得饮料不好，而是**根本不把饮料放进动作空间**。

**借到我们这里**：`ExpectimaxConfig.allow_drinks=True`（第 307 行）默认把 3 个
饮料槽全部展开；`_candidate_drinks`（第 496–520 行）虽然做了价值门控，但在
「每回合最多 1 瓶」的约束下仍会增加分支。gkbench 的 obs 只给饮料 id、不给效果，
我们的适配器已经默认 `allow_drinks=False`；真机全引擎可以保留，但建议：
- 只在「体力不够打关键牌」或「饮料是唯一合法动作」时展开；
- 或者在 leaf 里给饮料一个保守的固定价值，而不是逐瓶搜索。

### 附：H11（可选）评估表按偶像卡 effect 分组，而不是一套权重打天下

**位置**：第 87–98 行、第 416 行；配置表 `ai_master/current`（第 53 行）。

**做法**：`examEffectType` 是评估表的分组键。不同偶像卡/方案用不同的评估表，
而不是用一套全局权重。

**借到我们这里**：我们已经有 `data/knowledge/plans.json`、`policy_weights.json`
和 `CardTable.value` 的分档逻辑，但 `AnalyticLeafValue` 仍是全局参数。可以按
`plan`（sense/logic/anomaly）给不同的 `a_clear/a_perfect/sigma/condition_multiplier`。
这是 H3 的轻量版，不需要改搜索。

---

## 3. 它用了、我们没建模（或只建模了一半）的机制

### 3.1 元气（`block` / `vitality`）

官方 AI 的评估态里 `block` 是一等公民（第 271 行），并且还单独跟踪：

- `block_add_down_turns`（元气增加量减少，第 277 行）
- `block_add_down_fix`（减少的固定值，第 287 行）
- `block_restriction_turns`（元气增加无效，第 282 行）

我们的模型：

- `ExpectState.vitality` 已建模为「先扣元气、再扣体力」的费用资源
  （`is_legal` / `effective_cost`，第 435–445 行），也支持
  `ExamLessonDependBlock`（`block_scale`）的依赖分；
- 但**没有**「元气增加量减少/无效」「对手攻击/护盾消耗」这些考试机制；
- `AnalyticLeafValue` 的 `predict` 也不把 `vitality` 本身当成未来打点资源
  （只有 `block_scale` 依赖分）。

结论：元气我们建模了「费用 + 依赖分」，官方 AI 建模了「费用 + 依赖分 + 限制 +
防御」。在 gkbench 的 hif 题里，`block_scale` 是主要打点之一，漏掉限制会高估
元气牌；但比完全不建模好。

### 3.2 好印象（`review`）

官方 AI 跟踪：

- `review`（层数，第 273 行）
- `review_multiple_layers`（好印象强化层，第 106、298 行）
- `review_additive_multiple`（好印象获得量增加，第 110 行）
- `review_turn_end_reduce_lock_turns`（回合末减少锁定，第 286 行）
- `lesson_multiple_depend_review_or_aggressive_turns`（打分依赖好印象/やる気，
  第 283 行）
- `_PAIR_SLOT` 里效果类型 196–199 → 评估项 50–53（第 118 行）；桥里没给这四项
  的中文名，其中可能包含好印象追加/依赖类，本文不硬猜。

我们的模型：

- `ExpectState.impression` + `review_multiple` + `review_multiple_turns`；
- `end_turn_state` 按层数加分、下一回合开始 -1（第 1176–1188 行）；
- `AnalyticLeafValue.impression_annuity` 做了年金（第 368–380 行）。

缺：`review_additive_multiple`、回合末减少锁定、以及「分数依赖好印象/やる気」的
卡（`ExamLessonValueMultipleDependReviewOrAggressive` 在卡表里有，但我们的
`_effect_fields` 没映射）。结论：好印象的主干有了，但「好印象的成长/锁定/依赖」
没建全。

### 3.3 指针（`stance`）

官方 AI 跟踪：

- `idol_status_type`（Concentration / Preservation / FullPower，第 113、291 行）
- `idol_status_step`（段阶，第 291 行）
- `full_power_point_get_sum_count`（全力值累计，第 292 行）
- `stance_concentration_change_count` / `stance_preservation_change_count` /
  `stance_full_power_change_count`（切换次数，第 293–295 行）
- `stance_lock`（指針固定，第 297 行）
- 累计层（含 `concentration_lesson_multiple_additive_layers` 等，第 108、298 行）

我们的模型：

- `StanceState` 有类型/段阶/全力值（`sim/stance.py`）；
- `score_multiplier` 和 `stamina_cost_multiplier` 已接入 `_card_award` 和
  `effective_cost`；
- `end_turn` 处理「全力值 ≥10 → 下回合全力」；
- 没有切换次数、累计全力值、指針固定。

结论：**当前倍率**我们有，**指针历史/资源**没有。如果卡池里有「每切换一次」或
「消耗全力值」的卡，纯搜索会低估。官方 AI 的做法不是「优先切强气」这种硬规则，
而是把这些量全部喂给评估表；它没有在桥里写死优先级。

### 3.4 やる気 / 好调 / 绝好调

- `aggressive`（やる気，第 273 行）+ `aggressive_additive_multiple`
  （第 110 行）：我们的 `motivation` 只放大元气获得量（`CardSpec.motivation`），
  没有做「やる気层数 × 元气获得」的完整链。
- `parameter_buff_turns`（好调，第 274 行）：我们映射成
  `condition_turns`，`_card_award` 里按 ×1.5 算（第 782 行）。
- `parameter_buff_multiple_per_turn`（绝好调，第 280 行）：我们**没有**建模
  「1.5 + 0.1 × 好调回合数」的绝好调公式。
- `parameter_buff_additive_multiple`（好调获得量增加，第 110 行）：
  我们只建模了 `condition_additive`（好调增加量）。

### 3.5 考试减益 / 限制（我们基本没建模）

官方 AI 的评估态里有：

- `stamina_consumption_down_turns` / `stamina_consumption_add_turns`
  （体力消耗增减，第 275–276 行）
- `stamina_consumption_down_fix`（固定削减，第 288 行）
- `slump_turns`（スランプ，第 279 行）
- `parameter_debuff_turns`（审查ギミック的参数低下，第 278 行）
- `buff_consumption_add_turns`（强化状态消耗增加，第 285 行）
- `lesson_debuff`（集中减少/弱气，第 287 行）
- `anti_debuff_count`（低下无效，第 297 行）
- `panic`（パニック）和 `play_card_limit`（技能卡使用限制）：UIObs 的 status
  表里有，官方桥的 `_raw` 没有单列；这里只确认它们存在于观测，不推断官方权重。

我们的 `ExpectState` 没有这些字段，`_status_fields`（适配器）也直接忽略。
在 hif 题里这些减益出现的频率不低（尤其 `stamina_consumption_*` 和
`block_restriction`），忽略会高估「能打多少张/能拿多少分」。

### 3.6 P 道具 / 回忆 / 附魔

官方 AI：

- `item_ids`（第 417 行）和 `resource_item_ids`（第 309 行）进入评估；
- `trigger_effect_states` 里的附魔/持续效果参与触发预测（第 312–331 行）；
- 效果选牌时把附魔产生的候选也纳入 `card_view`（第 192–211 行）。

我们的模型：

- `sim/p_items.py` 有 6 个触发时机的 `PItemSpec`，未实现类型 no-op；
- `ExpectState.p_items` 可以带 P 道具，但 gkbench 适配器**没有**把
  `ctx.loadout.produce_item_ids` 转成 `PItemSpec`（obs 里只有 `ench` id，
  没有可结算的数值）；
- 回忆/附魔的持续效果没有进 `ExpectState`。

结论：这是 gkbench 适配器最大的分数缺口之一。短期可以先把 P 道具 id 映射到
我们已有的 `data/knowledge/p_items.json`（1.2 MB）里的 `PItemSpec`；但那是
`ctx.loadout` 的公开信息，和「只读 obs」的约束需要确认。

### 3.7 选牌 / 检索 / 生成 / 移动

- 官方 AI：专门评估器（第 128–134、168–190 行）。
- 我们：`sim_produce.py` 把 `ExamForcePlayCardSearch` / `ExamCardCreateId` /
  `ExamCardMove` 近似成「至少 +1 抽牌」（第 190–195 行）。

在 hif 题里「从山札选 2 张」的牌不少，+1 抽牌会低估「选到关键牌」的价值。

### 3.8 卡牌成长 / 定制

- 官方 AI：`card_growth`（第 301–310 行）按卡的 grow effect 类型评估；但文档
  也说明「效果里的卡牌成长（差分类型 20）没记」（第 19 行）。
- 我们：`CardSpec.grow_score` 接口在，但真实卡表 `ProduceCardGrowEffect` 数据
  为空，`grow_score` 恒 0；定制 `c` 在适配器里直接忽略（见 `algo.py::_spec`）。
- 结果：带定制/成长的卡会被低估。定制 id 里其实编码了
  `g_effect-...-600` 这类数值，后续可以解析；但格式不是公开稳定协议，先不硬解。

### 3.9 保留区（`hold`）

- 官方 AI：`hold_count`（第 296 行）和选牌上下文里的保留卡（第 213–217 行）。
- 我们：`ExpectState` 没有 hold 区，适配器把 `obs["hold"]` 直接丢掉。
- 影响：保留牌可以通过效果回手，完全忽略会低估「保留/检索」类卡。

### 3.10 额外回合 / 战斗倍率 / 牌序

- 额外回合：官方 AI `extra_turns`（第 289 行）；gkbench 适配器把
  `exam.limit`（含追加回合）折成 `turns_left`，这块基本对齐。
- 战斗倍率：官方 AI `battle_bonus_permils`（第 270 行）是三项倍率；我们只有
  一个 `attribute_coefficient`（当前回合倍率），跨回合 beam 会把当前倍率套到
  未来所有回合，未来回合属性不同时会偏。
- 牌序：官方 AI 看真实牌序（`sees_seed=True`，第 407 行）；我们的 expectimax
  在公开信息下对抽牌做机会节点/多重集。这不是「漏建模」，而是评测约束下的
  本质差异。

### 3.11 目标函数

官方 AI 的评估态里没有 CLEAR/PERFECT 阈值，只有 `parameter`（分数）和一堆
状态；`result.selected.evaluate_score`（第 438 行）是标量评价分。可以推断它更
像是「评估未来得分/评价分」，而不是显式的「档位概率」。我们的
`AnalyticLeafValue.utility`（第 400–415 行）是
`a·P(score≥CLEAR) + b·P(score≥PERFECT)`，目标不同。两者没有绝对优劣：
- 排行榜按原始分排名时，期望分/评价分更直接；
- 只关心过关/PERFECT 时，档位效用更稳。

---

## 4. 和我们的 expectimax 对比：官方 AI 哪里比「纯搜索」更合理

| 维度 | 官方 AI | 我们的 expectimax | 结论 |
|---|---|---|---|
| 搜索世界 | 真实局面（`true_session.clone()`，第 424 行），看牌序 | 公开信息的抽牌机会节点/多重集 | 官方更强，但 gkbench 托管不能用；我们只能用公开信息 |
| 搜索深度 | 2 回合 + 20 万命令预算（第 3、410、427 行） | 回合内精确、跨回合 beam 可选 | 官方用「限深 + 限预算」防爆炸；我们的回合内精确在牌多/饮料多时会爆炸 |
| 计划 | 搜一整段，重放，key 不符才重搜（第 403–448 行） | 适配器每步重搜（`expectimax_with_stats`） | 官方的计划一致性和耗时更好；我们对隐藏抽牌的反应更自然 |
| 动作空间 | 不喝饮料（第 14 行）；选牌用评估器（第 168–190 行） | 饮料可搜索；选牌近似 +1 抽 | 官方剪枝更狠，分支更小 |
| 评估 | 50+ 特征 + 配置表（第 262–310 行） | 解析式 6 个特征（`AnalyticLeafValue`，第 326–415 行） | 官方对考试机制覆盖更全，尤其是元气/好印象/指针的层与限制 |
| 效果预测 | 在克隆上执行一条效果、看差分（第 345–400 行） | 静态 P 道具表 + 卡表解析 | 官方的差分预测更不容易漏机制；但依赖 GKMS 核心 |
| 目标 | 标量评价分（推测） | 档位效用（CLEAR/PERFECT 概率） | 排行榜按分 → 官方目标更直接；过关场景 → 我们更稳 |
| 可移植性 | 私有 GKMS + C++ 扩展 + 原生核心 | 纯 Python，`needs_gkms=False` | 我们可托管/跨平台；官方只能在有 GKMS 的机器跑 |

**最值得学的一句话**：官方 AI 不是「搜得越深越好」，而是
**「限深 2 回合 + 命令预算 + 计划重放 + 动作剪枝 + 选牌评估器」** 的组合。
纯 expectimax 如果在整回合上枚举所有有序序列（再乘上抽牌和饮料），分支会迅速
超过 20 万；官方 AI 的工程折中是把「搜索」留给出牌顺序，把「组合选择」交给
评估器，把「长期一致性」交给计划重放。

**我们比它强的地方**：

- 不需要 GKMS 私有仓库/原生核心/C++ 扩展，纯 Python 可托管；
- 抽牌在公开信息下是**精确机会节点**（组合枚举/超几何），不是看真实牌序；
- 直接优化 CLEAR/PERFECT 档位效用，不是猜一个标量评价分；
- 对已建模的机制（费用/元气/好印象/指针倍率/再动/饮料）是精确状态转移，
  不是学出来的权重。

---

## 5. 落地优先级（只针对我们仓库）

### P0：gkbench 适配器已经做的

- `obs -> ExpectState`：手牌/山札/弃牌/除外 id+u 查卡表；status 映射
  review/aggressive/lesson_buff/parameter_buff/review_multiple/
  full_power_lesson_multiple/lesson_parameter_multiple；指针字符串/整数兼容。
- 动作合法性：只返回 `obs["legal"]` 里的 `play/end/drink`；搜索动作不在 legal
  时用「只含 legal 手牌」重搜，仍不一致就结束回合。
- 不依赖 GKMS：`needs_gkms=False`，`allow_drinks=False`。

### P1：下一步最划算的三件事

1. **计划重放**：用 `best_turn_sequence()` 缓存本回合序列 + 公开状态指纹，
   减少每步重搜（H1）。
2. **leaf 加层/资源特征**：把 `review_multiple`、`full_power_lesson_multiple`、
   `extra_plays`、`hold_count` 进 `predict`（H4/H8）。
3. **P 道具映射**：如果允许读 `ctx.loadout`，把 `produce_item_ids` 映射成
   `PItemSpec`，这是 hif 分数缺口最大的一块（3.6）。

### P2：需要引擎/数据支持的

- 选牌评估器（H7）；
- 指针切换次数/累计全力值（H9）；
- 差分触发预测（H6，需要 GKMS）；
- plan/idol 分组 leaf（H3/H11）；
- 绝好调/减益/元气限制（3.4/3.5）。

---

## 6. 行号索引（`gkbench/algos/official_ai.py`）

| 行号 | 内容 |
|---|---|
| 1–20 | 文档：官方 AI 来源、两回合搜索、桥接说明、与原生实现的差异 |
| 33–34 | `EXT_SRC`、`INF_TURNS` |
| 39–55 | `contest_dir` / `official()` / 配置表 `ai_master/current` |
| 58–84 | `ext_lib()`：编译/缓存官方 AI 扩展 |
| 87–98 | `exam_effect()`：按偶像卡 `examEffectType` 分组 |
| 101–119 | `_ACCUMULATED` / `_FLOAT_LAYERS` / `_STANCE` / `_PAIR_SLOT` / `_ZONES` |
| 122–217 | `NativeHost` 的 SequenceHost：clone/frame/hand/use/end/选牌 |
| 149–151 | `frame`：phase/turn/remaining/plan/main_effect/score |
| 168–190 | `_step`：选牌试打、评估、排队 |
| 192–217 | `card_view` / `selection_context`（含保留区） |
| 219–334 | `NativeHost` 的 EvaluationHost |
| 220–232 | `_left` / `_flag_left`：永久状态 `INF_TURNS` |
| 234–260 | `_layer_rows`：累计层的 `(千分比, 剩余回合)` |
| 262–299 | `_raw`：50+ 评估字段 |
| 300–310 | `evaluation_state`：资源卡/道具/成长 |
| 312–331 | `trigger_statuses`：来源过滤、直接定时效果 |
| 345–400 | `_Resolver`：逐条效果差分预测 |
| 403–448 | `OfficialAIAlgo`：decide / replan / plan 重放 |
| 410、427 | `command_budget=200000` |
| 440–448 | `search_key` 校验与重搜 |

---

## 7. 没确认的事（留给后续）

1. 官方 AI 评估表的**权重**和目标函数（在 `ai_master/current`，本机没有）。
2. 搜索内核的具体算法（最佳优先？GNRPA？αβ？）和候选剪枝策略。
3. 选牌评估器 `OfficialCardSelectCalculator` 的打分公式。
4. 「两回合」是硬深度还是软深度；`command_budget` 与深度的关系。
5. 官方 AI 是否会把 CLEAR/PERFECT 的目标折进 `evaluate_score`；从接口看不到。
6. 我们如果要复现官方 AI 的强度，必须拿到 GKMS 私有仓库，但许可上不适合
   直接移植；本文只借工程结构，不复制实现。
