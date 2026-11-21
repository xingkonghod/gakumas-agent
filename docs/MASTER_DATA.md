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
| 期中 12:36 | 18 张 | == User/Get[14:54] 全量快照 |
| 期末 15:08 | 26 张 | == User/Get[15:26] 27 张 − 被删的 #4 |
| 第三局 17:19 | 15 张 | 另一偶像（hkne）局 |

**逐回合 ground truth**（scripts/decode_exam_actions.py --json → out/exam_truth.json）：
请求顶层 field3 = `ExamTurnEndLog`，其中 **field50 = startPlayHandProduceCards（回合开始手牌）**、
field100 = commands（本回合打出，useProduceCard=5 带真实卡 id）、field7 = 回合属性。
回合末手牌进弃牌堆（打出后去 Lost 区的卡除外），故一般情况下**每回合开始手牌 = 当回合从牌堆顶
抽的 turnStartDistribute(=3) 张**；例外是第 1 回合要先抽 isInitial 卡再补抽（见下）。
牌堆抽完前，洗牌后牌序 = 各回合手牌依次拼接（期中 18 张 = 前 6 回合正好抽完，可整段对照）。

**洗牌重放：期中 + 期末都已精确破解（2026-11-21 晚）**

完整模型（实现 `src/gkagent/sim/exam_shuffle.py`，验证 `scripts/verify_shuffle.py`）：
```
考试开局 RNG 消耗顺序（同一 xorshift32(考试 seed)）：
  ① 回合属性：只有前 turns-3 回合随机（逐个随机取并移除，消耗 turns-3 次），末 3 回合固定
  ② NPC 分数：npc_count 个 NPC × turns 回合，每对消耗 1 次（produce-001 是 5 个 NPC）
  ③ 洗牌：Fisher-Yates 倒序洗「number 升序」牌堆
⇒ 洗牌前消耗 K = (turns-3) + npc_count*turns = 6*turns - 3（5 NPC 时）

发牌：
  · 第 1 回合先 SetInitialCard：从牌堆「底→顶」扫，把 isInitial 卡移入手牌，
    再从牌堆顶补抽到 turnStartDistribute(3) 张；
  · 第 2 回合起每回合从牌堆顶抽 3 张；
  · 牌堆抽空前的抽牌序列 = 各回合开始手牌依次拼接。
```

| 考试 | seed | 回合 | K | isInitial | 结果 |
|---|---|---:|---:|---|---|
| 期中 | 0x504C4509 | 9 | (9-3)+5×9 = **51** | 无 | 18/18 精确、回合集合 6/6 ✅ |
| 期末 | 0x7ECD7553 | 11 | (11-3)+5×11 = **63** | `p_card-02-men-2_054` | 26/26 精确、回合集合 8/8 ✅ |

**期末之前复现不出的根因**：期末牌堆里的 `p_card-02-men-2_054` 是 `isInitial`（主数据
`ProduceCard.isInitial=true`），第 1 回合会被**优先抽入手牌**，所以「首回合手牌 = 洗后牌堆
前 3 张」的假设失效，后面所有回合跟着错位。旧版搜索 k=0..2000 全部失败正是这个原因。

**回合属性独立验证**：把 `CalculatedTurnParameterType` 的算法（池 = 末 3 回合的权重降序拼接，
逐个 `pool.pop(integer(0,len))`）放在 **RNG offset 0** 跑，两场考试的「前 turns-3 回合属性」
都能逐项复现；剩下的消耗正好 = 5×turns，与 NPC 组（`ProduceExamBattleNpcGroup` 5 行）一致。
所以 K 的分解不是拟合，是逐段对上的。

**洗后（弃牌堆重洗）**：期中第 7 回合牌堆抽空后重洗弃牌堆，从洗牌后状态再消耗 45 次随机数
即可精确复现 T7-T9 手牌（9/9；45 应为支援卡临时强化等掷点，尚未完全建模）。
注意「打出后去 Lost 区」的卡（`playMovePositionType=Lost`）不进弃牌堆，重洗时只洗 Grave 区。

**仍未做**：① 采第三场考试验证 K=6×turns-3 的普适性（尤其非 5 NPC 的 produce 类型）；
② 弃牌堆重洗前的那 45 次消耗（支援强化掷点）建模，才能从 seed 预测整场牌序；
③ 期末 T9-T11 的弃牌堆重洗同口径验证。
