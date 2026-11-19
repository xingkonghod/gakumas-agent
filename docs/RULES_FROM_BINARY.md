# Gakumas PC 二进制静态分析：考试/课程结算规则

> 分析对象：`D:\Games\Gakumas\gakumas\`（Unity **6000.0.77f1**，IL2CPP **metadata v31**）
>
> 分析方式：**只做静态分析**。未启动游戏、未修改游戏文件、未注入进程。
>
> 结论边界：**原生代码段被加密/加壳，方法体不可见**；本报告能确认的是
> **类型/字段/方法签名/枚举/常量/主数据表结构**，以及由这些名字和签名反推出的
> **数据流与规则形状**。具体算术细节（乘除顺序、取整、系数值）标注为「未确定」。

---

## 0. 结论速览

1. **Il2CppDumper 能识别版本但无法 dump**：`GameAssembly.dll` 的
   `.text`/`il2cpp`/`.pdata` 在磁盘上只有 **4 KiB 原始数据**，其余是
   114 MB 高熵密文；Il2CppDumper 找不到 CodeRegistration/MetadataRegistration
   （均为 0），回退 `LoadLibrary` 失败（Win32 126 / 1114）。
2. `global-metadata.dat` **没有加密**，因此改用自写的 v31 元数据解析器，生成了
   **`data/reverse/out/dump.cs`：75,041,567 字节 / 1,016,640 行**。
   它是**元数据级 dump**：有全部类/字段/属性/方法签名/枚举值，但**没有 RVA 和方法体**。
3. 游戏真正的结算代码集中在 `Campus.InGame.Exam` 命名空间；核心类型是
   `ExamParameterModel`、`ExamEffectCalculateContext`、`ExamEffectDifferenceData`、
   `ExamEffectAffectData`、`ExamStatusEffectCollection`、`ExamRuleCalculator`、
   `ExamRuleEvaluationLog`、`ExamSaveTurnLog`。
4. 已确认：
   - 考试分数来自 `ExamParameterModel.GetScoreList(scoreSum, 前/中/后段 turn 数,
     前/中/后段 ratio, Vocal/Dance/Visual ratio, ...)`；
   - 分数权重表 `ProduceExamBattleScoreConfig` 使用 **VocalPermil / DancePermil /
     VisualPermil（千分比）**；
   - 姿态（Stance）有 **Concentration / Preservation / FullPower / OverPreservation**
     四种 + `Step` 层数；
   - 状态效果是**带回合数、可叠层、可百分比**的（`ExamStatusEffectBase.Turn /
     IsValuePercent`）；
   - 存在明确常量：`ExamConst.FullPowerPointForFullPower = 10`、
     `ContestCalculateTurn = 2`、`ContestCalculateTurnPlan3 = 1`、
     `ContestCalculateTurnPlan4 = 2`；
   - 卡牌区域有 Hand/Deck/Grave/Lost/Hold/Remove **六区**，**没有卡牌 Discard 区**；
     `Discard` 只命中饮料丢弃（drink），卡牌的“弃牌”走 Grave/Lost/Remove。
5. **不存在** `ExamScore`、`LessonScore`、`ApplyEffect` 这些名字；
   `AddScore` 只出现在 UI 结果模型，`CalculateScore` 只命中
   `CalculateScoreBonus`；`ScoreResult` 只命中 Tour/Angya 的结果 UI 枚举。
   因此不要按这些名字去找公式，实际名字见第 4 节。

---

## 1. 材料、工具、版本

| 项目 | 值 |
|---|---|
| `GameAssembly.dll` | 164,327,424 字节；SHA256 `06FC9FB271969A97D16478CBEBB2C74B7C89DCE61C167656A3121497BB336554` |
| `global-metadata.dat` | 46,660,356 字节；SHA256 `856A60FF5207A283BC8C4D5B2F3FAC0C0856180A34B100B967539EAD6CD1DC4B` |
| Unity 版本 | `6000.0.77f1 (88f89d0d8b31)`（来自 `gakumas.exe` VersionInfo） |
| metadata header | magic `0xFAB11BAF`，version **31**，header size 256 |
| 工具 | Il2CppDumper **v6.7.46**（`Il2CppDumper-win-v6.7.46.zip`，11,215,992 字节） |
| 工具位置 | `data/reverse/Il2CppDumper/`（解压后含 `Il2CppDumper.exe`、`config.json` 等） |
| 本机运行时 | .NET 运行时 8.0.21 / 10.0.14；Il2CppDumper 使用自带 runtime 的 win 包 |

下载使用 `codeload.github.com` / release 直链均成功。`config.json` 中
`RequireAnyKey` 已改为 `false`，避免等待按键。

---

## 2. 解包过程与结果

### 2.1 Il2CppDumper 运行失败

命令：

```powershell
Il2CppDumper.exe `
  "D:\Games\Gakumas\gakumas\GameAssembly.dll" `
  "D:\Games\Gakumas\gakumas\gakumas_Data\il2cpp_data\Metadata\global-metadata.dat" `
  "data\reverse\out"
```

原始日志（`data/reverse/dumper.log`，UTF-16 重定向）：

```text
Initializing metadata...
Metadata Version: 31
Initializing il2cpp file...
Il2Cpp Version: 31
Searching...
CodeRegistration : 0
MetadataRegistration : 0
Use custom PE loader
System.ComponentModel.Win32Exception (126): 找不到指定的模块。
   at Il2CppDumper.PELoader.Load(String fileName) ... PELoader.cs:line 46
   at Il2CppDumper.Program.Init(...) ... Program.cs:line 216
ERROR: An error occurred while processing.
```

在游戏目录作为 cwd 再跑一次（`data/reverse/dumper-cwd.log`），错误从 126 变成
**1114（DLL 初始化例程失败）**：

```text
CodeRegistration : 0
MetadataRegistration : 0
Use custom PE loader
System.ComponentModel.Win32Exception (1114): 动态链接库(DLL)初始化例程失败。
```

这说明：

- **不是 metadata 版本不支持**：v31 已被识别，metadata 表也能读；
- 是 **GameAssembly.dll 的 PE 代码段在磁盘上被加密**，Il2CppDumper 的
  模式搜索（`PlusSearch`）找不到注册数组；
- 它回退到“把 DLL 加载进本进程再拷贝节区”的自定义 PE Loader，但该 DLL 的
  DllMain 在非游戏环境返回失败（126 → 1114）。

### 2.2 PE 证据：代码段只剩 4 KiB

`data/reverse/pe_sections.py` + `data/reverse/entropy.py` 的结果（关键项）：

| 节 | VirtualSize | SizeOfRawData | 文件偏移 | 说明 |
|---|---:|---:|---:|---|
| `.text` | `0x009D0000`（10.3 MB） | `0x1000`（4 KiB） | `0x06D4D000` | 只有入口/引导代码，其余为零 |
| `il2cpp` | `0x07EFF000`（127 MB） | `0x1000`（4 KiB） | `0x06D4E000` | 同上 |
| `.rdata` | `0x024DB000`（38.6 MB） | `0x024D9000` | `0x06D4F000` | **99.97% 为零** |
| `.data` | `0x00D31000`（13.8 MB） | `0x00A8D000` | `0x09228000` | **100% 为零** |
| `.pdata` | `0x00BF7000`（12.3 MB） | `0x1000` | `0x09CB5000` | 只有 4 KiB |

文件前部 `0x1000 .. 0x6D4D000` 是 **114.5 MB 的高熵数据**
（抽样 entropy ≈ 7.99–8.00，非零率 ≈ 0.995），不属于任何节；
这符合“加壳器把原始节区压缩/加密后放在文件前部，PE 头只保留一个引导页”的布局。
`gakumas.exe` 也是同样的布局（`.text`/`_RDATA` 各只有 `0x1000` raw），
游戏目录里还有高熵的 `gakumas.exe._` 与 DMM/Octo 分发目录
（`octo\v1\400\...`、`gakumas_Data\Octo\...`）。**本机没有可直接读取的
明文 `GameAssembly.dll` 副本。**

> 因此，Il2CppDumper 在当前磁盘文件上**不可能**生成带 RVA/方法体的 dump.cs。
> 这是二进制保护问题，不是工具用法问题。

### 2.3 备选路径：直接解析 `global-metadata.dat`

`global-metadata.dat` 是明文（header/字符串/表结构都能直接读），
所以编写了 `data/reverse/metadata_parse.py`：

- 按 v31 读 header（31 对 offset/size，header size 256）；
- 读 typeDefs / methods / fields / parameters / properties / events /
  images / assemblies / fieldDefaultValues / stringLiterals；
- v29+ 的默认值使用 **compressed int（zigzag varint）**，不是裸 int32；
  用 `System.DayOfWeek` 做校验：解码为 Sunday=0 … Saturday=6，正确；
- 用 typeDef 的 `byvalTypeIndex` 建立「native type index → 类型定义」映射，
  能解析出相当一部分类型名；解析不了的显示为 `type#N`。

表规模（自检）：

| 表 | 数量 |
|---|---:|
| images / assemblies | 185 / 185 |
| typeDefs | 53,021 |
| methods | 353,273 |
| fields | 228,403 |
| parameters | 312,498 |
| properties | 68,783 |
| fieldDefaultValues | 38,453 |
| stringLiterals | 52,139 |

### 2.4 产物 `dump.cs`

| 指标 | 值 |
|---|---|
| 路径 | `data/reverse/out/dump.cs` |
| 大小 | **75,041,567 字节** |
| 行数 | **1,016,640** |
| SHA256 | `0970E75AF3E6A5417FEC99ED6D9F8ECE383F28EFCA170411595B97181C22D2C5` |
| 内容 | 全部 185 个 assembly 的 namespace/class/enum/field/property/method/parameter |
| 不包含 | RVA、方法体、字段的 static/const/access 修饰（metadata 中没有） |

附带产物：`data/reverse/out/stringliteral.json`（3,784,679 字节，52,139 条
字符串字面量）。`DummyDll/` **没有生成**：它依赖 CodeRegistration 的
methodPointers，而当前二进制里这些指针不可读。

`dump.cs` 头部明确写了：

- `GameAssembly.dll` 被加壳，Il2CppDumper 无法定位注册数组；
- 本文件来自明文 metadata，因此没有 native 地址；
- `type#N` 是 native `Il2CppType[]` 的下标（在 `.data`/加密区，无法从
  metadata 恢复），不是笔误。

**它不是 Il2CppDumper 原生输出**，但它是当前唯一能对每个符号给出行号的
“dump.cs”。本报告所有行号都指这个文件。

---

## 3. 关键词命中（`dump.cs` 行号）

下表是 `data/reverse/keyword_hits.py` 对 `dump.cs` 的统计与代表性命中。
“行数”是该关键词出现的总行数，不等于独立符号数。

| 关键词 | 行数 | 代表性命中（行号） | 说明 |
|---|---:|---|---|
| `Score` | 3,557 | `ExamRuleEvaluationLogScore` **100908**；`ExamParameterModel.GetScoreList` **82870**；`ExamEffectAffectData.EvaluateScore` **90209**；`ExamRuleEvaluationLog._totalScore` **100874** | 实际分数相关符号，不含 `ExamScore` |
| `ExamScore` | **0** | — | 不存在这个类/字段名 |
| `LessonScore` | **0** | — | 不存在 |
| `AddScore` | 4 | `AuditionBattleResultHifRankingListCellModel.AddScore` **28725**；field **28714** | 只出现在结算 UI 模型，不是核心结算 |
| `CalculateScore` | **1** | `ParameterBonusData.CalculateScoreBonus` **380376** | 不是考试分公式 |
| `ScoreResult` | 44 | `TourScoreResultType` **45861**；`AngyaScoreResultType` **46753**；`ProduceHighScoreResult` **448675** | 都是 UI/API 结果类型 |
| `ExamEffect` | 1,859 | `ExamEffectCalculateContext` **74962**；`IExamEffectExecutor` **75388**；`ExamEffectExecutorBase` **75395**；`ExamEffectUtility` **75798** | 效果执行器体系 |
| `EffectType` | 1,110 | `ExamStatusEffectType` **388723**；`ProduceExamEffectType` **391376** | 两个核心枚举 |
| `ResolveEffect` | 21 | `ProduceApiUtility.ResolveEffectAsync` **67157**；`RefineApiUtility.ResolveEffectAsync` **51991** | 都是演出/API 协程，不是数值结算 |
| `ApplyEffect` | **0** | — | 不存在；应用效果叫 `ExamEffectUtility.AffectEffect` **75838** |
| `Condition` | 1,960 | `ConditionType` **387946**；`ProduceConditionType` **390867**；`FusionConditionType` **63207** | 注意：`ConditionType` 是账号/时间/日期条件，不是考试条件 |
| `Concentration` | 104 | `ExamIdolStatusType.Concentration` **388552**；`ConcentrationEffectExecutor` **76383**；`StanceLockConcentrationEffectExecutor` **77844** | Concentration 是**姿态**，也有同名效果执行器 |
| `GoodImpression` | **0** | — | 不存在这个英文名 |
| `Motivation` | **0** | — | 不存在这个英文名 |
| `Stance` | 209 | `ExamIdolStatusType` **388549**；`ExamIdolStatusEffect` **78319**；`ExamEffectDifferenceData` stance 字段 **75194–75197**；`StanceLock...` **77844–77884** | 姿态 + 姿态锁定体系 |
| `Turn` | 1,609 | `ExamPhaseType` **20246**；`ExamParameterModel` 回合属性 **82531–82550**；`ExamSaveTurnLog` **83317** | 回合制 |
| `Draw` | 1,431 | `DrawEffectExecutor` **76438**；`ExamEffectCalculateContext` 卡区 **74967–74972**；`IExamSequenceHandler.OnTurnStartDraw` **83354** | 抽牌 |
| `Deck` | 2,764 | `ExamEffectCalculateContext.DeckList` **74968**；`ExamEffectDifferenceData.SetIsDeckShuffle` **75376**；`...GraveShuffle` **75377**；`...LostShuffle` **75378** | 牌库 + 洗牌 |
| `Discard` | 126 | `DrinkDiscardRequestAsync` **65287**；`ProduceDiscardDrinkRequest` **445380** | **没有卡牌 Discard**；卡牌弃置走 Grave/Lost/Remove |

---

## 4. 能确定的规则结论

> 标记说明：**[确认]** = 名字/签名/枚举值/常量直接可见；
> **[高置信推断]** = 由字段名 + 方法签名 + 调用关系推出，但不含方法体。

### 4.1 考试类型与阶段

`Campus.InGame.Exam.ExamType`（`dump.cs:82244–82258`）**[确认]**：

```csharp
Lesson = 0, Audition = 1, Contest = 2, Seminar = 3, SeminarAudition = 4,
Tower = 5, Angya = 6, TourManual = 7, TourAuto = 8, Competition = 9,
LessonRefine = 10, AuditionRefine = 11
```

`Campus.InGame.ExamPhaseType`（`dump.cs:20246–20256`）**[确认]**：

```csharp
None=0, ExamStandBy=1, TurnStart=2, TurnStartAfter=3, TurnStartDraw=4,
MainStart=5, Main=6, TurnEnd=7, ExamEnd=8
```

`IExamSequenceHandler`（`dump.cs:83348`）的回调顺序也直接给出了回合流程
（`dump.cs:83351–83357`）**[确认]**：

```
OnExamStart → OnTurnStart → OnTurnStartBeforeDraw → OnTurnStartDraw
→ OnTurnBeforeEnd → OnTurnEnd → OnExamEnd
```

### 4.2 牌库与卡牌区域：六区，没有卡牌 Discard

`ExamEffectCalculateContext`（`dump.cs:74962`）持有（`dump.cs:74967–74972`）**[确认]**：

| 字段 | 含义 |
|---|---|
| `HandList` | 手牌 |
| `DeckList` | 牌库 |
| `GraveList` | 弃牌区/墓场（grave） |
| `LostList` | 消失区（lost） |
| `HoldList` | 保留区（hold） |
| `RemoveList` | 移除区（remove） |

`ExamEffectDifferenceData` 对应的洗牌/替换操作（`dump.cs:75372–75378`）**[确认]**：

- `SetIsDeckReplace()` — 替换牌库
- `SetIsDeckShuffle()` — 洗牌库
- `SetIsDeckGraveShuffle()` — 洗弃牌区入牌库
- `SetIsDeckLostShuffle()` — 洗消失区入牌库

**结论**：卡牌的“弃置”不是 `Discard`，而是进入 **Grave / Lost / Remove**；
`Discard` 关键词只命中饮料丢弃 API。若需要“弃牌”规则，应查
`ExamCardMoveController` 与 `ExamEffectDifferenceData`，而不是 `Discard*`。

### 4.3 回合与每回合结算快照

`ExamParameterModel`（`dump.cs:82412`）的回合/出牌字段（`dump.cs:82531–82550`）
**[确认]**：

```csharp
CurrentTurn, RemainTurn, IsExamEndComplete, LimitTurn, ExtraTurn,
Stamina, MaxStamina, ProducePoint, JudgeParameter, Block,
IsTurnCardPlayEnd, TurnCardPlayCount, TurnCardRemoveCount,
ExamCardPlayCount, IsTurnCardGrave, IsTurnCardLost
```

`ExamSaveTurnLog`（`dump.cs:83317`）是**逐回合结算日志**，字段包括
（`dump.cs:83320–83342`）**[确认]**：

- `turn`
- `resultTargetValue` / `resultTargetValueVocal` / `Dance` / `Visual`
- `addTargetValue`（本节新增的目标值）
- `stamina` / `consumedStamina` / `block` / `additionBlock`
- `handProduceCards` / `holdProduceCards`
- `statuses` / `statusEffects` / `resultStatusEffects`
- `commandLogs`
- `parameterType`
- `idolStatusType` / `idolStatusStepCount`（姿态与层数）
- `stancePreservationChangeCount` / `stanceConcentrationChangeCount` /
  `stanceFullPowerChangeCount`

这说明游戏在**每回合结束时**会把“目标值/参数、体力、护盾、手牌、状态、
指令日志、姿态层数”快照化；这就是实际结算日志的数据模型。

### 4.4 状态效果：带回合、可叠层、可百分比

`ExamStatusEffectBase`（`dump.cs:78341`）字段与属性 **[确认]**：

- `_isTurnLimited`（`dump.cs:78344`）→ `IsTurnLimited`（78350）
- `_turn`（78345）→ `Turn`（78351）
- `_isPassingTurnStart`（78346）→ `IsPassingTurnStart`（78352）
- `_uid`（78347）→ `Uid`（78354）
- `Type` / `IconValue` / `TargetCategory` / `Name` / `TurnText`
  （78353–78364）
- `IsValuePercent`（78362）——状态值可以是百分比
- `IsDisable` / `IsShowBuffList`（78363–78364）

方法（`dump.cs:78384–78388`）：`SetTurn`、`AddTurn`、`ReduceTurn`、
`SpendTurn`、`ClearTurnState` —— 明确的**回合递减/清理**语义。

`ExamStatusEffectCollection`（`dump.cs:79662`）按状态提供成对的
`TryAdd* / Get* / Consume*` 方法，例如：

| 状态 | 方法（行号） |
|---|---|
| Lesson Buff | `TryAddLessonBuffStatus` **79706**；`GetLessonBuff` **79709**；`ConsumeLessonBuff` **79711** |
| Lesson Parameter Multiple | `TryAddLessonParameterMultipleStatus` **79719**；`GetLessonParameterMultiple` **79720**（float） |
| Enthusiastic（やる気系） | `TryAddEnthusiasticStatus` **79717**；`GetEnthusiasticBuff` **79718** |
| Review（好調系？） | `TryAddReviewStatus` **79775**；`GetReview` **79776**；`ConsumeReview` **79778**；`GetReviewMultiple` **79785**（float）；`GetReviewAdditiveMultiple` **79781**（float） |
| Uplifting | `TryAddUpliftingStatus` **79772**；`GetUplifting` **79773**；`ReduceUplifting` **79774** |
| Aggressive | `GetAggressive` **79763**；`TryAddAggressiveStatus` **79767** |
| Stance Lock | `TryAddStanceLockStatus` **79813**；`GetStanceLock` **79814** |

`ExamUseEffectWarningType`（`dump.cs:75403–75431`）把这些上限/归零条件
直接命名出来了 **[确认]**：

```csharp
ReviewZero, ReviewConsumptionZero, EnthusiasticZero,
StanceStepMax, StanceOverPreservation,
HandLimit, DeckEmpty, GraveEmpty, LostEmpty,
StaminaMax, BlockZero, TimerOver, FullPowerPointGetSumZero, ...
```

这条枚举是“规则上限”的最强证据：例如使用好调/やる気系卡牌时，如果
数值为 0 或层数已达上限，会进入对应 warning，而不是无条件生效。

> **未确定**：`Review` / `Enthusiastic` / `Uplifting` 与日文「好調 / やる気 /
> 好印象」的精确对应。内部英文名已确认，但本地没有文本映射表，不能硬下结论。

### 4.5 姿态 Stance：四种 + 层数 + 全力点

`ExamIdolStatusType`（`dump.cs:388549–388556`）**[确认]**：

```csharp
Unknown = 0
Concentration = 1   // 集中
Preservation = 2    // 温存
FullPower = 3       // 全力
OverPreservation = 4 // 超出普通 Preservation 的状态
```

`ExamIdolStatusEffect`（`dump.cs:78319`）保存 `CurrentType` + `CurrentStep`
（`dump.cs:78325–78326`），方法（`dump.cs:78330–78336`）**[确认]**：

- `SetStatus(type, step)`
- `SetConcentration(step)`
- `SetPreservation(step)`
- `SetOverPreservation()`
- `SetFullPower()`
- `StanceReset()`
- `IsStepMax()`

`ExamEffectDifferenceData` 的差值字段（`dump.cs:75194–75197`）**[确认]**：

```csharp
StanceDifference, StanceStepDifference, StanceChangeCountDifference,
FullPowerPointDifference
```

对应 setter：`SetStanceDifference(...)`（`dump.cs:75364`）、
`SetFullPowerPointDifference(...)`（75365）、
`SetStancePreservationRemoveDifference(...)`（75363）**[确认]**。

`ExamEffectUtility` 提供（`dump.cs:75862–75868`）**[确认]**：

```csharp
SetStance(stance, step, context)
TryInternalSetStance(stance, step, context, isFullPowerPointConsumption)
UnsetFullPower(context)
ConsumeFullPowerPoint(context)
AddFullPowerPoint(fullPowerPoint, context)
ReduceFullPowerPoint(fullPowerPoint, context)
```

**常量**（`ExamConst`，`dump.cs:19643–19650`）**[确认]**：

```csharp
ContestCalculateTurn       = 2
ContestCalculateTurnPlan3  = 1
ContestCalculateTurnPlan4  = 2
FullPowerPointForFullPower = 10
```

`Plan4GroupCount = 4` 见 `ExamParameterModel`（`dump.cs:82467`）**[确认]**。

**可下结论**：
- 姿态是 `type + step` 的二维状态，存在“满层”概念（`IsStepMax`）；
- `OverPreservation` 是独立状态，不是普通 Preservation 的别名；
- 进入全力需要/消耗全力点；`FullPowerPointForFullPower = 10` 是明确的
  进入全力时的点数常量（具体加/减方向由方法体决定，**未确定**）；
- Contest 的结算回合数按 Plan 不同：普通 2、Plan3 1、Plan4 2。

### 4.6 分数流水线（Audition/Exam）

#### (a) 公式入口：`ExamParameterModel.GetScoreList`

`dump.cs:82870` **[确认]**：

```csharp
public type#58741 GetScoreList(
    System.Int32 scoreSum,
    System.Int32 startTurnCount,
    System.Int32 midTurnCount,
    System.Int32 endTurnCount,
    System.Single startRatio,
    System.Single midRatio,
    System.Single endRatio,
    System.Int32 vocalRatio,
    System.Int32 danceRatio,
    System.Int32 visualRatio,
    type#26323 startTurnTypeCount,
    type#26323 midTurnTypeCount,
    type#26323 endTurnTypeCount)
```

同一类还有 `GetSectionScore(targetSectionIndex)`（`dump.cs:82878`）**[确认]**。
`ExamParameterModel` 属性中包含（`dump.cs:82539`, `82541–82544`,
`82569–82582`）**[确认]**：

```csharp
JudgeParameter (int)
ClearBorder / OriginClearBorder / LimitBorder / HasLimit
VocalBonusPermil / DanceBonusPermil / VisualBonusPermil
VocalConfigParameter / DanceConfigParameter / VisualConfigParameter
JudgeParameterVocal / JudgeParameterDance / JudgeParameterVisual
NpcScoreMultiplePermil
```

**能确定的形状**：

```
每个区段（start/mid/end）的分数
  = f(该区段的 scoreSum 部分, 该区段的 turn 数, 该区段的 ratio,
      Vocal/Dance/Visual 比例, 该区段的类型计数)
最终分数 = 各区段分数合并（GetScoreList 返回列表）
```

**未确定**：`startRatio` 是加法还是乘法、`scoreSum` 如何分配到三个区段、
取整/四舍五入/ceil 的顺序、`type#26323` 的具体容器类型。

#### (b) 权重表：`ProduceExamBattleScoreConfig`（主数据）

`Campus.Common.Proto.Client.Master.ProduceExamBattleScoreConfig`
（`dump.cs:511150`）字段/属性 **[确认]**：

```csharp
Id           (string)
Parameter    (int)
VocalPermil  (int)
DancePermil  (int)
VisualPermil (int)
```

（`dump.cs:511169–511173`）

这是 **protobuf 主数据表**，由 `ProduceExamBattleScoreConfigMaster`
（`dump.cs` 中 `Campus.Common.Master.ProduceExamBattleScoreConfigMaster`）
通过 SQLite 读取。值是**千分比**，不是代码里的硬编码常量。

`ExamBattleNpcData`（`dump.cs:73728`）对 NPC 使用同一套比例模型
（`dump.cs:73733–73746`）**[确认]**：

```csharp
ScoreMin, ScoreMax, VocalRatio, DanceRatio, VisualRatio,
StartRatio, MidRatio, EndRatio, ScoreList, CurrentScore, ...
```

#### (c) 自动评测：`ExamRuleCalculator`

`ExamRuleCalculator`（`dump.cs:84809`）持有 5 张评测表
（`dump.cs:84812–84818`）**[确认]**：

```csharp
_seq
_isDirectUseSequence
_autoEvaluations
_resourceEvaluations
_triggerEvaluations
_growEffectEvaluations
_playProduceCardEvaluations
```

`Evaluate(...)`（`dump.cs:84823`）签名 **[确认]**：

```csharp
int Evaluate(ExamSequence sequence, int term, ExamPlayType playType,
             ProduceExamEffectType examEffectType,
             type#52914 playCardInTermIds, type#96254 log)
```

同类的局部函数（`dump.cs:84824`）**[确认]**：

```csharp
EvaluateScore(type#80298 value, double coefficient,
              ProduceExamAutoResourceEvaluation resourceEvaluation)
```

`ProduceExamAutoResourceEvaluation`（`dump.cs:511072`）的字段
（`dump.cs:511100–511101`）**[确认]**：

```csharp
int Addition
int Multiplication
```

`ProduceExamAutoEvaluation`（`dump.cs:510926`）的字段
（`dump.cs:510951–510952`）**[确认]**：

```csharp
int Evaluation
int ExamStatusEnchantCoefficientPermil
```

**能确定**：自动评测/竞赛计算是**主数据表驱动**的：
每行有 `Addition`、`Multiplication`、`Evaluation`、`RemainingTerm`、
`ExamStatusEnchantCoefficientPermil`，代码把 `value` 与 `coefficient` 交给
`EvaluateScore` 聚合。`ExamRuleEvaluationLog` 有累计字段 `_totalScore`
（`dump.cs:100874`），其评分条目 `ExamRuleEvaluationLogScore.Score` /
`BaseValue` 与 `AddEvaluationScore` 的参数都是 `System.Double`
（`dump.cs:100890`, `100924–100925`），最终 `GetResultScore()` 返回 int
（`dump.cs:100888`）。

**未确定**：`Addition`/`Multiplication` 的单位与顺序（`(base+add)*mul` 还是
`base*mul+add`）、`coefficient` 是否为 permil、如何取整、以及这些表在
普通手动考试中是否也参与。

#### (d) 单个效果的结果：`ExamEffectAffectData`

`dump.cs:90176` **[确认]**，属性（`dump.cs:90196–90211`）包括：

```csharp
Parameter, Stamina, MaxStamina, Block, BlockGain,
ExamIdolStatusType StanceType, StanceStep, FullPowerPoint,
CalculateWarningType, IsTurnEnd,
EvaluateScore, IsStanceLock, ...
```

`EvaluateScore` 是 int（`dump.cs:90209`）。这说明每个卡牌/饮料/道具效果
结算后，会产出一份“参数、体力、护盾、姿态、全力点、评测分”的增量数据；
`ExamEffectDifferenceData`（`dump.cs:75164`）再把这些增量合并成 diff
（`JudgeParameterDifference`、`StanceDifference`、`TurnCanCardPlayCountDifference`、
`RemainTurnDifference`、`ExtraTurnDifference` 等，`dump.cs:75178–75197`）。

#### (e) 课/考试结果：`ExamResultScreenModel`

`dump.cs:97930`，属性（`dump.cs:97962–97989`）**[确认]**：

```csharp
ProduceExamResultType ResultType   // Success / Normal / Failed
Stamina, MaxStamina, BeforeProducePoint
ParameterHardGrowthVocal/Dance/Visual
ParameterGrowthVocalBonus / DanceBonus / VisualBonus
VocalAfterParameter / DanceAfterParameter / VisualAfterParameter
VocalGrowthRatePermil / DanceGrowthRatePermil / VisualGrowthRatePermil
ClearBorder / LimitBorder
ParameterGrowthVocal / Dance / Visual
TargetParameterGrowthValue
```

`ProduceExamResultType`（`dump.cs:391744–391749`）**[确认]**：

```csharp
Unknown=0, Success=1, Normal=2, Failed=3
```

**能确定**：课程结算结果至少包含“原始成长 + 加成 + 千分比成长率 +
ClearBorder/LimitBorder”；`ResultType` 三态（成功/普通/失败）。
**未确定**：这些值如何由每回合 `ExamSaveTurnLog` 汇总、Border 比较是否
`>=`、失败如何截断参数。

### 4.7 课程/参数增益：四个乘法率

`ExamEffectUtility.CalculateAddingParameter`（`dump.cs:75839`）与
`AddParameter`（`dump.cs:75841`）**[确认]**。

`ExamAddingParameterAdditionalData`（`dump.cs:74915`）有四个 float
（`dump.cs:74923–74926`）**[确认]**：

```csharp
MultipleParameterBuffRate
MultipleEnthusiasticRate
MultipleConcentrationRate
MultipleFullPowerRate
```

`ExamEffectUtility` 还提供：

- `GetRatioEffectIntValue(value, ratio, isCeil)`（`dump.cs:75856`）——
  按 ratio 缩放，**显式 ceil**；
- `CalculateAddBlock(value, context, additionalMultipleAggressiveRate)`
  （`dump.cs:75845`）；
- `CalculateStaminaRecover` / `CalculateDamage` / `CalculateBuffCost`
  （`dump.cs:75848–75859`）。

`ExamStatusEffectCollection` 提供课程增益的读取口：
`GetLessonBuff`、`GetLessonParameterMultiple`、`GetReview`、
`GetEnthusiasticBuff`（`dump.cs:79706–79776`）。

**能确定**：课程参数增长不是单一“分数”，而是
`基础值 × (若干 buff 倍率) + 固定值` 形态，至少包含
ParameterBuff / Enthusiastic / Concentration / FullPower 四个乘率；
且有 `isCeil` 显式取整开关。
**未确定**：这些乘率是相加还是相乘、是 permil 还是 float 倍率、
Enthusiastic/Concentration 的作用顺序。

### 4.8 效果枚举目录（用于对照主数据）

`ProduceExamEffectType`（`dump.cs:391376`，194 个成员）**[确认]**。
关键值：

| 值 | 名称 | 行号 |
|---:|---|---|
| 1 | `ExamLesson` | 391379 |
| 3 | `ExamBlock` | 391381 |
| 4 | `ExamCardDraw` | 391382 |
| 9 | `ExamCardMove` | 391386 |
| 31 | `ExamReview` | 391404 |
| 45 | `ExamConcentration` | 391411 |
| 46 | `ExamPreservation` | 391412 |
| 47 | `ExamFullPower` | 391413 |
| 48 | `ExamStanceReset` | 391414 |
| 62 | `ExamUplifting` | 391422 |
| 63 | `ExamExtraTurn` | 391423 |
| 170 | `ExamEnthusiasticAdditive` | 391497 |
| 191 | `ExamStanceLockConcentration` | 391518 |
| 192 | `ExamStanceLockFullPower` | 391519 |
| 193 | `ExamStanceLockPreservation` | 391520 |

`ExamStatusEffectType`（`dump.cs:388723`，75 个成员）**[确认]**。
关键值：

| 值 | 名称 | 行号 |
|---:|---|---|
| 3 | `Enthusiastic` | 388728 |
| 35 | `Review` | 388755 |
| 37 | `Uplifting` | 388757 |
| 51 | `StanceLock` | 388768 |
| 54 | `EnthusiasticMultiple` | 388771 |
| 56 | `ConcentrationLessonMultipleAdditive` | 388773 |
| 63 | `ReviewMultiple` | 388780 |

`ProduceStepType`（`dump.cs:392542`，51 个成员）**[确认]**：

```csharp
LessonVocalNormal=1, LessonVocalSp=2, ...
AuditionMid1=16 (392560), AuditionMid2=17 (392561), AuditionFinal=18 (392562)
```

`ExamTriggerOriginType`（`dump.cs:20057–20067`）**[确认]**：

```csharp
Unknown=0, Character=1, IdolCard=2, SupportCard=3,
Memory=4, Event=5, Item=6, Drink=7
```

`ConditionType`（`dump.cs:387946`，80 个）包含**时间/日期类条件**
（`TimeTerm`, `TimeDuration`, `TimeWeekday`…），不是考试条件枚举；
考试/生产条件用 `ProduceConditionType`（`dump.cs:390867`，76 个，
`EventOccurred`, `EventNotOccurred`, `SupportCard`…）；
融合用 `FusionConditionType`（`dump.cs:63207`，7 个）**[确认]**。

### 4.9 其他已确认常量/字段

- `ExamConst.Plan4GroupTypes`（field，`dump.cs:19646`）——Plan4 分组类型表。
- `ExamParameterModel.Plan4GroupCount = 4`（`dump.cs:82467`）。
- `ExamStatusEffectBase.IsValuePercent`（`dump.cs:78362`）——状态值可为百分比。
- `ExamUseEffectWarningType.StanceStepMax` / `StanceOverPreservation`
  （`dump.cs:75419–75420`）——姿态层数上限与温存超限是显式规则。
- `ExamUseEffectWarningType.HandLimit` / `DeckEmpty` / `GraveEmpty` / `LostEmpty`
  （`dump.cs:75414`, `75423–75425`）——手牌上限、牌库/弃牌/消失区空是显式规则。
- `ExamResultScreenModel.ResultType` 三态（`dump.cs:97963`）。

---

## 5. 不能确定的 / 不要误读

1. **方法体不可见**：所有 native 实现都在加密区。因此：
   - 不能给出 `GetScoreList` 的具体乘除顺序、取整方式；
   - 不能给出 `CalculateAddingParameter` 的最终公式；
   - 不能给出 `ProduceExamAutoResourceEvaluation.Addition/Multiplication`
     的符号、单位、是否 permil。
2. **主数据数值不可见**：`VocalPermil`/`DancePermil`/`VisualPermil` 等
   是运行时从主数据（SQLite/Protobuf）读的，代码里只有列名；
   本报告没有提取主数据表的具体行值。
3. **字段修饰不可见**：metadata 不含字段的 `static/const/access`；
   `dump.cs` 中字段只写类型/名字，不写 `public/private`。
4. **`type#N` 未解析**：例如 `ExamRuleCalculator._seq` 是 `type#96316`，
   `GetScoreList` 返回 `type#58741`；这些是 native `Il2CppType` 下标，
   需要 `.data` 里的 types 数组才能解析。
5. **`Review` / `Enthusiastic` / `Uplifting` 的日文语义未确认**：
   内部英文名可以确认，但“好調 / やる気 / 好印象”的对应关系没有本地
   文本表佐证；不要直接把它们写成官方中文名。
6. **没有 `ExamScore` / `LessonScore` / `ApplyEffect` / 卡牌 `Discard`**：
   这些是本任务关键词假设，但二进制里不存在；实际名字见上表。

---

## 6. 下一步建议（按性价比排序）

1. **运行时 dump（最直接，但本任务禁止）**：在游戏进程内 dump 解密后的
   `GameAssembly.dll`，再跑 Il2CppDumper，可得到完整 `dump.cs` + RVA +
   DummyDll；配合 Ghidra/IDA 可读 `GetScoreList`、`CalculateAddingParameter`
   的方法体。需要 Frida/调试器，且会触发游戏完整性检测，不属于“静态分析”。
2. **静态解包**：`GameAssembly.dll` 的 4 KiB 引导代码 + 114 MB 密文是加壳
   布局；需要逆向引导代码/DllMain 的解密例程和密钥。当前引导代码是混淆过的
   （字符串解码 + 间接跳转），工作量较大；没有在本次承诺时间内展开。
3. **提取主数据**：`ProduceExamBattleScoreConfig`、`ProduceExamAutoEvaluation`、
   `ProduceExamAutoResourceEvaluation` 等表是 SQLite/Protobuf 主数据；
   找到 master DB 后可直接得到 `VocalPermil`、`Addition`、`Multiplication`、
   `Evaluation` 的具体数值。游戏使用 `Qua.Master.SQLite`，
   表名/主键方法在 `ProduceExamBattleScoreConfigMaster` 等类中可见。
4. **只做规则建模**：如果目标只是做模拟器，用本报告的字段/枚举/签名 +
   社区已验证的公式做交叉校验，比继续死磕加壳二进制更快；但必须把
   “社区公式”和“本地二进制证据”分开标注。

---

## 附录 A：原始错误与日志

- `data/reverse/dumper.log`：首次运行，`CodeRegistration : 0`，
  `Win32Exception (126)`（找不到模块）。
- `data/reverse/dumper-cwd.log`：以游戏目录为 cwd 重跑，
  `Win32Exception (1114)`（DLL 初始化例程失败）。
- 两次都先打印 `Metadata Version: 31` / `Il2Cpp Version: 31`，
  说明版本识别正常，失败点是 PE/代码段，不是 metadata 版本。

## 附录 B：产物与哈希

| 文件 | 大小 | SHA256 |
|---|---:|---|
| `GameAssembly.dll` | 164,327,424 | `06FC9FB271969A97D16478CBEBB2C74B7C89DCE61C167656A3121497BB336554` |
| `global-metadata.dat` | 46,660,356 | `856A60FF5207A283BC8C4D5B2F3FAC0C0856180A34B100B967539EAD6CD1DC4B` |
| `data/reverse/out/dump.cs` | 75,041,567 | `0970E75AF3E6A5417FEC99ED6D9F8ECE383F28EFCA170411595B97181C22D2C5` |
| `Il2CppDumper-win-v6.7.46.zip` | 11,215,992 | `F5FC60DFC5C034C1FF3FC651514416EBD47658A63493207734537FD25FA2DEA2` |

## 附录 C：复现脚本

- 下载/解压：`data/reverse/Il2CppDumper/`（release zip）
- PE/节区/熵：`data/reverse/pe_sections.py`、`data/reverse/entropy.py`
- metadata 解析：`data/reverse/metadata_parse.py`
- dump 生成：`data/reverse/make_dump.py`
- 关键词统计：`data/reverse/keyword_hits.py`
- 类型/枚举查询：`data/reverse/detail.py`、`data/reverse/query_*.py`

> 再次强调：本报告没有运行游戏、没有修改游戏文件、没有注入进程；
> 所有结论都来自磁盘上的 `GameAssembly.dll` / `global-metadata.dat` 及其
> PE/metadata 结构。方法体级别的公式需要等二进制解密或运行时 dump 才能确认。
