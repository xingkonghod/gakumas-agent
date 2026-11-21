# 主数据已入库（2026-11-20）

## 拿到的东西

用社区公开的 **gakumasu-diff** 快照构建了模拟器用的主数据库：

```
来源：https://github.com/vertesan/gakumasu-diff
提交：d31baf6608ee4553091f28446f628cd3ad66ff01（h iro 文档引用的同一个快照）
产物：data/hiro/vendor/gakumas-player/data/master/<commit>/catalog.sqlite
规模：286 张表 / 163,974 行 / 476 个卡 base / 1,817 个卡变体
原始：216 MB YAML → 74 MB sqlite（构建 68 秒）
```

## 立刻验证的三件事

**① 考试基础分（produce-001 初 REGULAR，stepType 16 = 中間 / 18 = 最終）**

| 角色 | 中間 baseScore | 中間封顶 forceEndScore | 最終 baseScore |
|---|---:|---:|---:|
| 篠澤広 (hrnm) | **600** | **900** | **2450** |
| 其他角色 | 600 | 900 | 2500 |

**和 hiro 文档 §4.3 完全一致**（他们写 REGULAR 中間 600/900、最終 2450）。

**② 字段齐了**：`rankThreshold`（名次线）、`parameterBaseLine`、`produceExamBattleConfigId`、
`produceExamBattleNpcGroupId`、`voteCountBaseLine` 等都在。

**③ 引擎能读**：`gakumas_exam.master.Master()` 直接可用，`m.table('ProduceStepAuditionDifficulty')` 返回 4,686 行。

## 现在能做什么

```
✅ 用主数据核对我们的常数（已经对上 exam base score）
✅ 用他们的 gakumas_exam 当 oracle，验证我们的 LessonSim 算分
✅ 查任意卡牌的真实效果定义（不用再猜 52 条定制卡）
✅ 查 NPC 组的分数结构（ExamBattleNpcData 的 ScoreMin/Max）
```

## 待办

- [ ] 用主数据修正 `hajime_data.py` 里的常数（考试基础分已确认，课程档位待查 `ProduceStepLessonLevel`）
- [ ] 抽一场考试，用 gakumas_exam 跑一遍，和我们的 LessonSim 对比
- [ ] 查 52 条定制卡的真实定义，补我们的效果表


## 附：seed 在流量里（2026-11-20 发现）

UserProduceProgress.ExamSeedValueFieldNumber = 600，服务器会把它下发给客户端。
同一培育的多个响应里值一致：

`
StepAuditionStart        = 1347175689 (0x504C4509)
StepAuditionEndExamBattle = 1347175689
User/Get                  = 1347175689
`

配合客户端同款 RNG（xorshift32，见 gakumas_exam/rng.py）可以精确重放洗牌。
工具：scripts/find_seed.py / scripts/verify_seed.py。

## 附：考试时刻的牌堆字段已定位（2026-11-21）

**之前的误区**：`UserData.userProduceCardList`(field **230550472**) 不是牌堆，是**卡牌图鉴/收集库**
（155+ 张，含同一 base 的 +0/+1 双变体、跨 p_card-00/01/02/03 多前缀）。StepAuditionStart 响应里
那「9 种卡」是 `userProduceProgressSupportCardList`(field **256246388**) = **支援卡**，也不是牌堆。

**真正的当前培育牌组** = `UserData.userProduceProgressProduceCardList`(field **309641228**)，
元素 `UserProduceProgressProduceCard`：

| field | 含义 |
|---|---|
| 2 | number（本局唯一实例号） |
| 3 | produceCardId |
| 4 | upgradeCount |
| 6 | deleted（true = 已删卡） |
| 7 | originType |
| 20 | produceCardSkinId |

**考试牌堆 = 该列表里 deleted=false 的卡。**

**更新语义**（关键，重建时必须区分）：
- `Produce/Start`、`User/Get` 下发**全量快照** → 整体替换牌组；
- 其余步骤响应（StepEvent / StepPresentReceive / ActivateEffect / StepShopBuy / StepAuditionEnd…）
  是**按 number 的增量 upsert**（新卡 / 强化 / deleted=true 删卡）。

**重建 + 交叉验证**（scripts/reconstruct_deck.py → out/deck_snapshots.json）：
| 考试 | 牌堆 | 校验 |
|---|---|---|
| 11-20 期中 12:36 | 18 张 | == User/Get[14:54] 全量快照 |
| 11-20 期末 15:08 | 26 张 | == User/Get[15:26] 27 张 − 被删的 #4 |
| 11-20 17:19（未打完）| 15 张 | 另一偶像（hkne）局，没采到考试结束 |
| 11-21 期中 17:27 | 15 张 | 本局没有考试后的 User/Get；用洗牌重放 15/15 反证（见下）|
| 11-21 期末 17:37 | 27 张 | 用洗牌重放 27/27 反证（见下）|

**逐回合 ground truth**（scripts/decode_exam_actions.py --json → out/exam_truth.json）：
请求顶层 field3 = `ExamTurnEndLog`，其中 **field50 = startPlayHandProduceCards（回合开始手牌）**、
field100 = commands（本回合打出，useProduceCard=5 带真实卡 id）、field7 = 回合属性。
回合末手牌进弃牌堆（打出后去 Lost 区的卡除外），故一般情况下**每回合开始手牌 = 当回合从牌堆顶
抽的 turnStartDistribute(=3) 张**；例外是第 1 回合要先抽 isInitial 卡再补抽（见下）。
牌堆抽完前，洗牌后牌序 = 各回合手牌依次拼接（期中 18 张 = 前 6 回合正好抽完，可整段对照）。

**洗牌重放：四场实机全部精确破解（2026-11-21）**

完整模型（实现 `src/gkagent/sim/exam_shuffle.py`，验证 `scripts/verify_shuffle.py`）：
```
考试开局 RNG 消耗顺序（同一 xorshift32(考试 seed)）：
  ① 回合属性：只有前 turns-3 回合随机（逐个随机取并移除，消耗 turns-3 次），末 3 回合固定
  ② NPC 分数：npc_count 个 NPC × turns 回合，每对消耗 1 次（四场都是 5 个 NPC）
  ③ 洗牌：Fisher-Yates 倒序洗「number 升序」牌堆
⇒ 洗牌前消耗 K = (turns-3) + npc_count*turns = 6*turns - 3（5 NPC 时）

⚠️ 这里的 turns 是**配置回合数**，不是实战回合数：中间考试到 forceEndScore 会提前结束
   （2026-11-21 那场配置 9 回合、打 7 回合到 1700 提前结束，K 仍 = 51），详见下节。

发牌：
  · 第 1 回合先 SetInitialCard：从牌堆「底→顶」扫，把 isInitial 卡移入手牌，
    再从牌堆顶补抽到 turnStartDistribute(3) 张；
  · 第 2 回合起每回合从牌堆顶抽 3 张；
  · 牌堆抽空前的抽牌序列 = 各回合开始手牌依次拼接。
```

| 局 | 考试 | seed | 配置回合 | 实战回合 | K | isInitial | 结果 |
|---|---|---|---:|---:|---:|---|---|
| 11-20 hmsz | 期中 | 0x504C4509 | 9 | 9 | (9-3)+5×9 = **51** | 无 | 18/18 精确、回合集合 6/6 ✅ |
| 11-20 hmsz | 期末 | 0x7ECD7553 | 11 | 11 | (11-3)+5×11 = **63** | `p_card-02-men-2_054` | 26/26 精确、回合集合 8/8 ✅ |
| 11-21 hkne | 期中 | 0x47E1B2A5 | 9 | **7**（到 1700 提前结束）| (9-3)+5×9 = **51** | `p_card-01-men-2_035+0` | 15/15 精确、回合集合 5/5 ✅ |
| 11-21 hkne | 期末 | 0x1E1A740D | 12 | 12 | (12-3)+5×12 = **69** | `p_card-01-men-2_035` 的 +0/+1 三张 | 27/27 精确、回合集合 9/9 ✅ |

**期末之前复现不出的根因**：期末牌堆里的 `p_card-02-men-2_054` 是 `isInitial`（主数据
`ProduceCard.isInitial=true`），第 1 回合会被**优先抽入手牌**，所以「首回合手牌 = 洗后牌堆
前 3 张」的假设失效，后面所有回合跟着错位。旧版搜索 k=0..2000 全部失败正是这个原因。

**「实战回合数 ≠ 配置回合数」的坑（2026-11-21 新采集发现）**：主数据
`ProduceStepAuditionDifficulty` 里中间考试有 `forceEndScore`（produce-002 プロ：配置回合 9，
`baseScore` 1150 的考试封顶 1700、1200 的封顶 1800）。达到封顶分后考试提前结束，上传的
`ExamTurnEndLog` 只有实战回合；但回合属性/NPC 分数在开局仍按**配置回合**生成，所以 K 要用
配置回合算。该场实战 7 回合：按配置 9 回合 K=51 精确复现（按实战 7 回合算 K=39 会整段错位）。
验证工具现在会自动尝试「配置回合 ≥ 实战回合」的候选并报告是提前结束。

**回合属性独立验证**：把 `CalculatedTurnParameterType` 的算法（池 = 末 3 回合的权重降序拼接，
逐个 `pool.pop(integer(0,len))`）放在 **RNG offset 0** 跑，四场考试的「前 配置turns-3 回合属性」
都能逐项复现；剩下的消耗正好 = 5×turns，与 NPC 组（`ProduceExamBattleNpcGroup` 5 行）一致。
所以 K 的分解不是拟合，是逐段对上的。末 3 回合的静态表顺序随考试不同（olde 两场是 [2,3,1]，
11-21 两场是 [2,1,3]），由 `ExamUtility.GetBonusParameterTypeOrderedList(vocalPermil, dancePermil,
visualPermil)` 按 NPC 权重定序，不是固定值。

**弃牌堆重洗 + 支援强化掷点：已完整建模（2026-11-21 深夜）**

整场考试只有一条 xorshift32 随机数流；洗完初始牌堆后继续按下面顺序消耗：

1. **每回合抽牌后 → 支援强化掷点**（客户端 `ExamSupportCard` 的考试内临时强化）：
   按「入手顺序 × 支援卡顺序（编成槽位号 `number` 升序）」**每对掷一次 `integer(0,1000)`**；
   - 牌在主数据里没有 `upgrade+1` 变体（已叠满）→ 整张跳过、不掷；
   - 支援卡 `produceCardUpgradeLessonParameterType` ≠ 0 且 ≠ 本回合属性 → 跳过不掷；
   - `roll < produceCardUpgradePermil`（服务器下发的值，‰；不是主数据基础值）即成功：
     该牌显示强化 +1，且这张支援**本回合不再参与**（每回合开始清空）；
   - 牌堆抽空才重洗时，重洗发生在「本回合已抽到的牌」的支援强化**之前**
     （第 1 回合 `SetInitialCard` 的初始卡批次、补抽批次各判一次，共用本回合的已用集合）。
2. **牌堆抽空 → 洗弃牌堆**：弃牌堆顺序 = 卡进弃牌堆的先后——出牌后去 Grave 的牌按出牌顺序 append，
   回合末剩余手牌按手牌顺序 append；`playMovePositionType=Lost` / `isEndTurnLost` 的卡不进弃牌堆。
   用同一个 Fisher-Yates 倒序洗，洗完后接成新牌堆，继续从牌堆顶（下标 0）抽。

三组实机重洗样本逐张复现（`scripts/verify_shuffle.py` 端到端跑，回归在 `tests/test_exam_shuffle.py`）：

| 局 | 重洗时点 | 重洗前掷点 | Grave | 重洗后实战手牌 |
|---|---|---:|---:|---|
| 11-20 期中 | T7 回合开始 | **45 次**（0 次成功）| 12 张 | T7-T9 9/9 ✅ |
| 11-21 期中 | T6 回合开始 | **29 次**（1 次成功）| 11 张 | T6-T7 6/6 ✅ |
| 11-21 期末 | T10 回合开始 | **46 次**（6 次成功）| 20 张 | T10-T12 9/9 ✅ |

模型在 `src/gkagent/sim/exam_shuffle.py`：`opening_deck_and_rng` / `support_upgrade` / `reshuffle_grave`
（`replay_initial_deck` 只覆盖牌堆抽空前的那段）。现在「seed + 考试时刻牌堆 + 支援编成 + 回合属性 +
出牌序列」可以精确推演整场牌序（含弃牌堆重洗）。

**主数据缺两张 11-21 游戏版本的新卡**（catalog 是 gakumasu-diff d31baf6）：
- `p_card-01-ido-3_292`：工程内较新的 gakumasu-diff `ProduceCard.yaml` 里有
  （`playMovePositionType=Lost`、有 +0..+3 变体）；catalog 缺所以按「可强化、打出后去 Lost」处理；
- `s_card-3-0115`：`SupportCard` 缺条目，考试内强化 filter 由 11-21 两场掷点唯一反推 = **Vocal**。

`scripts/verify_shuffle.py` 顶部用 `SUPPLEMENT_CARD_MOVE` / `SUPPLEMENT_SUPPORT_FILTER` 兜底，主数据更新后可删。

**仍未做**：① 非 5 NPC 的 produce 类型验证（四场都是 5 NPC，公式里 npc 项还没换过数）；
② 11-20 期末 T9 的「回合内重洗」样本（牌堆在第 9 回合第 3 抽才空）暂跳过：该局 T8 打出过
考试内生成的卡（`p_card-00-men-3_003+1`），弃牌堆顺序和生成卡的随机消耗还没建模；
③ 考试内生成卡 / 中途抽牌等其它随机数消耗源（本批四场没触发，`support_upgrade` 的
`IsEnchantTriggerActive` 条件还没验证过）。
