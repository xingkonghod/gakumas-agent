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
回合末手牌全进弃牌堆，故**每回合开始手牌 = 当回合从牌堆顶抽的 turnStartDistribute(=3) 张**；
牌堆抽完前，洗牌后牌序 = 各回合手牌依次拼接（期中 18 张 = 前 6 回合正好抽完，可整段对照）。

**洗牌重放：期中已精确破解（18/18）**

已验证模型（`scripts/verify_shuffle.py`）：
```
牌堆输入序 = number 升序
rng = xorshift32(examSeedValue)，洗牌前先 advance K=51 次
洗牌 = Fisher-Yates 倒序（n=len..2, j=integer(0,n), swap(a[j],a[n-1])）
发牌 = 每回合从牌堆顶抽 turnStartDistribute(=3) 张，回合末全部进弃牌堆
→ 牌堆抽完前，牌序 = 各回合开始手牌依次拼接
```
期中 seed=0x504C4509、K=51：整段精确 **18/18**、回合集合 6/6 ✅

**期末异常（未解决）**：seed=0x7ECD7553、牌堆 26 张（牌堆多重集与首 26 张手牌**完全一致**，
即牌堆重建正确），但 k=0..2000 × 输入排序(Number 升/降、id 升/降、新卡前置/后置) ×
种子变换(seed±1、异或、midterm seed 等) **均无法复现**（回合集合最好仅 1/8）。期中与期末
唯一的结构差异是期末牌堆在期中考试后由「删 1 张 + 加 9 张 + 强化 2 张」演化而来，
疑为牌堆顺序/种子派生在跨考试时不同。需再采一局期末（或另一局期中）判断是局特有还是普遍差异。
