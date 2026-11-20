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

**还没验证完**：考试时刻的「卡组列表」在哪个字段（Produce/Start 响应里有 23 种 base/idol 卡，
但考试时牌组会因抓卡/删卡变化，需要在 StepAuditionStart 响应里定位实际 deck）。
