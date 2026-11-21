# 项目交接（2026-11-21 深夜更新）

> **导航看 [INDEX.md](INDEX.md)**（按任务列了该读哪些文档）。
> **要动手做事看 [HANDOVER_NEXT.md](HANDOVER_NEXT.md)**（补什么 · 做什么 · 验收标准，下一件事的唯一真源）。
> 本文只写：现状 + 已完成什么 + 路径速查 + 注意事项。

## 一、这个项目在做什么

让 AI 自动玩《学园偶像大师》的培育（produce）模式：
读屏幕 → 决策（出牌/选行动）→ 点击 → 复盘。

当前主线是**初（REGULAR/PRO）**模式，目标是逼近手打水平（A / 10,237）。

---

## 二、今天（11-20）完成了什么

### A. 真机数据采集彻底打通（最重要的基础设施）

```
游戏副本      C:\GakumasLocal（12.34GB，D 盘原版的完整复制，D 盘不动）
采集工具      C:\GakumasLocal\GakumasUnlock
一键启动      双击「一键采集启动.bat」
采集产物      C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl
提取考试结果  python scripts\extract_exams.py
文档          docs/CAPTURE_PIPELINE.md
```

**解决的四个坑**（详见文档）：
1. 客户端 rustls 不信任我们的证书 → hook 改走明文 h2c（18444）
2. grpc-dotnet 在明文 http 下降级 HTTP/1.1 → hook 强制 `http2_only` + 跳过证书校验
3. Firebase 走 libcurl 不用系统代理 → 启动脚本注入代理变量（仅 Firebase 域名）
4. 代理端口已关仍注入 → 启动前 TCP 探测，不通就**清除**变量（不能写空字符串）

**已采到的真实数据**：
| 考试 | 名次 | 分数 | 三维 | 操作数 |
|---|---:|---:|---|---:|
| 期中 | 3 | 569 | 413/87/69 | 10 |
| 期末 | 2 | 4798 | 3266/476/1056 | 17 |

整局：**B / 7404**，三维 1011/493/79。

### B. 模拟器与公式校准

```
src/gkagent/sim/hajime_eval.py    初评价公式（属性和×2.3 + 名次分 + 期末分分段折算）
src/gkagent/sim/hajime_data.py    验证过的常数（考试基础分 / 课程档位 / 收益公式）
```

**4 局实机逐分回归通过**（9973 / 10428 / 8790 / 12903），测试在 `tests/test_hajime_eval.py`。

### C. 主数据入库（游戏真实数据）

```
来源   vertesan/gakumasu-diff 提交 d31baf6
产物   data/hiro/vendor/gakumas-player/data/master/<commit>/catalog.sqlite
规模   286 表 / 163,974 行 / 476 卡 base / 1,817 卡变体（74MB）
```

已验证 `produce-001` 考试基础分：中間 600/封顶 900、最終 2450（与社区文档一致）。

### D. seed 在流量里（今天最大的发现）

```
UserProduceProgress.ExamSeedValueFieldNumber = 600
同一培育的三个响应里 seed 一致：
  StepAuditionStart / StepAuditionEndExamBattle / User/Get → 0x504C4509
```

配合客户端同款 RNG（xorshift32，见 hiro 的 `gakumas_exam/rng.py`）可以精确重放洗牌。
工具：`scripts/find_seed.py`、`scripts/verify_seed.py`。

### E. bot 的几个死循环修复

```
f6b99c0  外出事件屏识别（不再只靠「快进」按钮）
9bd3551  click_force 不再被「用户活跃」门限拦截自己；领卡选卡后等按钮点亮
7e58b4b  点击坐标按实际客户区缩放（窗口非 720x1280 时全部落空）
```

---

## 二·补、11-21 进展（牌堆定位 + 洗牌端到端破解）

```
✅ 牌堆字段定位：UserData.userProduceProgressProduceCardList = 309641228
   （230550472 是图鉴、256246388 是支援卡，都不是牌堆）
   元素 UserProduceProgressProduceCard: number=2 / produceCardId=3 / upgradeCount=4 / deleted=6
✅ 更新语义：Produce/Start、User/Get = 全量快照；步骤响应 = 按 number 增量 upsert
✅ 重建并交叉验证：期中 18 张、期末 26 张（27−删 1），与 User/Get 快照逐张吻合
✅ ground truth：ExamTurnEndLog.field50 = 每回合开始手牌（一般=当回合抽的 3 张；T1 可能先含
   isInitial 卡），field100 = 打出卡
✅ 洗牌模型完整破解（期中 + 期末都精确复现，模型在 src/gkagent/sim/exam_shuffle.py）：
   · 洗牌前 RNG 消耗 K = (turns-3) + npc_count*turns（5 NPC ⇒ 6*turns-3）
     期中 9 回合 → K=51；期末 11 回合 → K=63（不是固定常数！）
   · 洗牌 = xorshift32(examSeedValue) advance K → Fisher-Yates 倒序洗「number 升序」牌堆
   · 第 1 回合先 SetInitialCard：isInitial 卡从牌堆底→顶扫入手牌，再补抽到 3 张
     （期末的 p_card-02-men-2_054 就是 isInitial，旧模型漏了它才会「期末复现不出」）
   · 结果：期中 18/18（6/6 回合集合）、期末 26/26（8/8）——scripts/verify_shuffle.py
✅ 回合属性算法在 RNG offset 0 上可逐项复现四场考试（前 turns-3 回合随机、末 3 回合固定）
✅ 洗后弃牌堆重洗：期中 T7 从洗牌后状态再消耗 45 次随机数 → T7-T9 精确 9/9
   （45 应为支援临时强化等掷点；打出后去 Lost 区的卡不进弃牌堆，重洗只洗 Grave 区）
```

**新工具**（scripts/，ruff 通过）：
```
dig_deck.py            按 dump.cs 字段号标注解析任意响应（--tree 全树）
scan_deck_updates.py   扫描图鉴字段 230550472（对照用）
reconstruct_deck.py    重建考试时刻牌堆 → out/deck_snapshots.json
decode_exam_actions.py 逐回合手牌/出牌/属性 → out/exam_truth.json（--json）
verify_shuffle.py      洗牌重放验证：自动读主数据 isInitial + 尝试配置回合，四场考试都 ✅
```

### 二·补二、11-21 晚（PRO 局两场考试：K 公式验证 + 提前结束的坑）

用户用 `i_card-hkne-3-000`（produce-002「プロ」= PRO）跑完一整局，采到期中 7 回合 / 期末 12 回合：

```
✅ 11-21 期末 seed=0x1E1A740D，配置 12 回合：K=(12-3)+5×12=69 → 27/27 整段精确、回合集合 9/9
✅ 11-21 期中 seed=0x47E1B2A5，实战 7 回合：按配置 9 回合 K=51 → 15/15 整段精确、5/5
   ⚠️ 期中到 forceEndScore(1700) 提前结束（配置 9 回合，实战 7 回合）；K 必须按配置回合算，
      按实战 7 回合算 K=39 会错位 → verify_shuffle.py 已改成「自动试配置回合 ≥ 实战回合」
✅ 两场的回合属性也能在 RNG offset 0 复现（池/静态末 3 回合自动反推）
✅ tests/test_exam_shuffle.py 加了这两场作回归（含「实战回合算 K 会错」的防线）
```

主数据里确认：`ProduceStepAuditionDifficulty` 的中间考试有 `forceEndScore`（produce-002：
baseScore 1150 → 封顶 1700；1200 → 封顶 1800），期末 `forceEndScore=0`（不提前结束）。
produce-001 = レギュラー（REGULAR）、produce-002 = プロ（PRO），四场采集都是 produce-002。

**下一会话从这里继续**（先读 MASTER_DATA.md 附录「弃牌堆重洗 + 支援强化掷点」）：
1. ~~洗后重洗前那张账要记全~~ → **已完整拆清，见二·补三**（45 次 = 支援强化掷点，不是常数）。
2. 采非 5 NPC 的 produce 类型补充公式样本（四场都是 5 NPC，K 公式的 npc 项还没换过数）。
3. 主数据缺 11-21 新卡：`s_card-3-0115` 的考试内强化 filter 反推 = Vocal，
   `p_card-01-ido-3_292` 较新 gakumasu-diff 里是 `playMovePositionType=Lost`；
   `verify_shuffle.py` 有 `SUPPLEMENT_*` 兜底，更新主数据后可删。
4. **之后接「完全信息搜索」**：seed + 牌堆 + 支援编成 + 回合属性 + 出牌序列 → 整段牌序
   （含弃牌堆重洗）→ expectimax 叶子。**第一步已接入，见二·补四**。

### 二·补三、11-21 傍晚（支援强化掷点 + 弃牌堆重洗完整破解 ✅）

三组重洗样本一起拆，同一条 RNG 流逐张复现：

```
✅ 支援强化掷点建模（每回合抽牌后）：
   入手顺序（外）× 支援卡顺序/编成槽位号升序（内），每对掷一次 integer(0,1000)；
   roll < 服务器下发的 produceCardUpgradePermil（‰）即成功 → 该牌 +1、该支援本回合不再参与；
   牌叠满（主数据无 upgrade+1 变体）或属性 filter 不符 → 不掷（不消耗随机数）
✅ 弃牌堆顺序：出牌后去 Grave 的按出牌顺序 append；回合末剩余手牌按手牌顺序 append；
   Lost 卡（playMovePositionType=Lost / isEndTurnLost）不进弃牌堆
✅ 牌堆抽空 → Fisher-Yates 倒序洗弃牌堆（同一随机数流）→ 接成新牌堆继续抽
✅ 三组样本（11-20 期中 T7 / 11-21 期中 T6 / 11-21 期末 T10）：
   重洗前掷点 45 / 29 / 46 次，Grave 12 / 11 / 20 张
   → 重洗后实战手牌 9/9、6/6、9/9 逐张对上（含每回合支援强化增量）
✅ scripts/verify_shuffle.py 端到端：4/4 场初始发牌 + 3/3 重洗样本全过
✅ tests/test_exam_shuffle.py 新增 6 条：掷点数 45/29/46 + 逐回合强化增量 + 重洗手牌
```

**模型改动**（`src/gkagent/sim/exam_shuffle.py`）：
```
opening_deck_and_rng(seed, deck, k)   开局：advance k → FY 洗初始牌堆，返回 (rng, 牌堆)
support_upgrade(rng, added, supports, parameter_type, used=, upgradeable=)
                                      支援强化掷点（返回成功列表 + 掷点次数）
reshuffle_grave(rng, grave)           弃牌堆 FY 重洗（返回新牌堆顺序）
```

**未验证/未建模**（都不影响已跑的四场）：
11-20 期末 T9 回合内重洗样本（T8 有考试内生成卡）；考试内生成卡/中途抽牌等其它随机消耗源；
非 5 NPC 的 K 公式。

### 二·补四、11-21 晚（完全信息搜索：第一步接入）

```
✅ 牌序数据链路：src/gkagent/sim/exam_oracle.py
   initial_shuffled_deck(seed, deck, config_turns) = 开局真实牌堆顺序
   ExamDrawOracle：每回合 draw_next_turn(param) 返回真实手牌（含支援强化掷点），
   牌堆空时按调用方给的真实 grave 顺序重洗 → 整段牌序可从 seed 推出
✅ 搜索侧开关：ExpectState.known_draw（已知后续抽牌顺序）
   非空 → 抽牌机会节点退化成确定分支（_draw_distribution / sample_draws）；
   空 → 原「只知多重集」期望模型（默认生产行为不变）
✅ 离线评测入口：state_from_sim(sim, known_deck_order=True)
✅ 新测试 14 条（tests/test_expectimax_known_draw.py 8 + tests/test_exam_oracle.py 6）
✅ 配对评测脚本 scripts/eval_known_draw.py，实测（同牌组同 seed unknown vs known）：
   · 真实牌组回合内搜索：增益 ≈0（牌组里几乎没有抽牌卡，回合内用不到未来信息）
   · 真实小牌组跨回合 beam：+3.0 均值（P50 +4，CLEAR 22.5%→30%）
   · 抽牌多构造牌组 beam：+44.6 均值 / P50 +55（+16.8%）
   → 信息本身值钱，但要变成分数需要跨回合规划 + 更好的叶子估值（V_leaf 仍是瓶颈）
```

**下一步（完全信息搜索第二段）**：
1. ~~生产接线：`auto_produce` 用采集到的 seed/牌组/支援编成/配置回合建 `ExamDrawOracle`，
   每回合与实机抽牌核对后把 `known_draw` 写进 `ExpectState`~~ → **已完成，见二·补五**；
2. ~~重洗后段全知：给 `ExpectState` 加 `discard_order`（现在只有多重集），
   第一次重洗后也能用 oracle 的 `reshuffle(grave)`~~ → **已完成，见二·补五**；
3. ~~生产策略：把 beam/全信息规划接成 `lesson.engine` 选项（beam ~100ms/回合）~~ → **已完成，见二·补五**；
4. 打通 MITM 采集进程与 bot 决策进程（seed 数据在 traffic.jsonl 里）——**只剩这一项**。

### 二·补五、11-21 深夜（完全信息搜索第二段：生产接线 + 重洗后段全知 + beam 选项 ✅）

```
✅ ② 重洗后段全知：ExpectState.discard_order（None=未知 / ()=已知为空）+ 搜索 reshuffle 钩子
   · apply_card / end_turn_state 全程维护弃牌堆顺序；_draw_distribution / sample_draws 在牌堆
     抽空时用 reshuffle(discard_order) 走确定分支；多重集对不上自动退回期望（绝不用错牌序）
   · ExamDrawOracle.reshuffle(grave) 纯预览（不推进考试 RNG）；
     reshuffle_from_sim(sim) 适配 LessonSim（尾部 pop → 抽牌顺序 = reversed(shuffled)）
   · 新测试 17 条 tests/test_expectimax_discard_order.py；eval_known_draw.py 加 --full-info

✅ ① 生产接线：采集数据 → ExamSetup → ExamDrawPlan → LessonPolicy → ExpectState
   · scripts/build_exam_setup.py：traffic.jsonl + deck_snapshots.json + 主数据 → out/exam_setup.json
     （4 场：seed / 牌堆 / 支援编成 / config_turns / isInitial / card_variants / Lost + 逐回合 truth）
     自带 --check：ExamDrawOracle 逐回合重放 4/4 场、86/86 张；重洗段 24/24 张
   · src/gkagent/sim/exam_plan.py：ExamSetup + ExamDrawPlan
     每回合 begin_turn 预测手牌 vs 实机逐张核对 → 过了就喂 known_draw/discard_order/重洗钩子；
     核对失败就地停用并记原因（搜索退回期望模型，绝不用错信息）
   · LessonPolicy(draw_plan=...) / attach_draw_plan：expectimax 与 beam 自动吃到全知牌序
   · auto_produce 加 --exam-setup（默认 out/exam_setup.json；缺文件 = 不启用，行为与旧版一致）
   · scripts/verify_exam_wiring.py 端到端：4/4 场、手牌 36/36 回合逐张命中、
     重洗样本 3/3（T7/T6/T10）、known_draw 覆盖下一手 29/29；
     真 LessonPolicy(engine=beam) 核对 28 回合、出牌 28 次

✅ ③ lesson.engine = "beam"：跨回合 beam 接进生产策略
   · policy.json 的 lesson.engine 新增 "beam"；参数 beam_width=4 / beam_deadline_ms=250
   · 没有 known_draw 时自动退回回合内 expectimax；搜索异常退回 rules（绝不退化）
   · 新测试 7 条 tests/test_policy_beam_engine.py
```

**仍未接（唯一剩下的）**：采集进程 ↔ 决策进程实时打通——现在 bot 读的是离线生成的
`out/exam_setup.json`（可在考试期间重新生成），进入考试时从 traffic.jsonl 取「当前这场」seed 还要接线。
已知限制见 [EXPECTIMAX.md](EXPECTIMAX.md) 末节（考试内生成卡 / 同局多次重洗 / 离线回放出牌与实机不同）。

**下一会话从这里继续**（完整任务表 / 验收标准见 **[HANDOVER_NEXT.md](HANDOVER_NEXT.md)**）：
```powershell
# 1) 先重建数据 + 端到端核对（依赖 C:\GakumasLocal 的采集文件）
.venv\Scripts\python.exe scripts\build_exam_setup.py
.venv\Scripts\python.exe scripts\verify_exam_wiring.py
# 2) 真机：引擎用 --engine 覆盖（不传时用 policy.json produce.engine=expectimax）
.venv\Scripts\python.exe scripts\auto_produce.py 340 ep-xxx --skip-home --exam-setup out\exam_setup.json --engine expectimax
```

### 二·补六、11-21 深夜二段（T1 真机流程 + 决策可观测性 + T3 实时接线代码）

2026-11-21 晚接手另一个会话的真机 T1 工作，合并并补齐：

```
✅ T1 真机流程（12 次短跑定位，FAILURES #27-33）：
   点击坐标双重缩放（撤销 7e58b4b 的预缩放，MaaFramework 原生自己换算）、
   难度页「レギュラー」按钮中心 (220,915)、「自动编成」确认框误判记录页、
   外出/事件屏选项行兜底、领卡卡面中心 (230,918)、考试详情浮层文案（得分+/仅限1次）、
   通信错误弹窗先于 loading 判重试、加载快速路径连续 12 步强制完整 OCR、
   无可用决策连续 2 步强制 SKIP（不再点中位卡空转）、暂停帧不计入同屏判死
✅ 决策可观测性 + 引擎接线：
   真机引擎优先级 --engine > policy.json produce.engine > 默认 rules（lesson.engine 只作
   LessonPolicy/单测默认）；日志首行 [engine]，每步 "... | eng=… fallback=…" 能看出
   是 expectimax/beam 在打还是搜索静默退回规则、退回原因（体力/回合/手牌读不到/异常）
✅ T3 实时接线（代码完成，待真机考试验收）：
   build_exam_setup.py --current（只读最新 StepAuditionStart，config_turns 输出候选 9/11/12）；
   reconstruct_deck.build_snapshots() 抽函数可运行时调用；
   ExamPlanSelector 逐回合用实机手牌收窄候选，唯一剩下即锁定（采集局离线实测第 2 回合锁定）；
   auto_produce 进入考试时按 mtime 重载 out/exam_setup.json、换场自动换 selector、结束打 summary
✅ 新增测试：决策可观测性 4 条 + ExamPlanSelector 4 条 + 点击坐标回归 + produce_ui 增补
```

**仍未做**：T1 整局真机验收（20 分钟内跑完一局）、T3 真机考试日志验收、T2 三引擎 A/B、T4 策略强度。
**注意**：换一局后的 `[exam-plan] mismatch` 是预期（离线 setup 来自别的采集），不要当 bug 修（FAILURES #33）。


---

## 三、社区情报（他们做到哪了）

**hiro-gakumas-hero**（matto49，AGPL-3.0，28 star）：

```
H.I.F 本战夺冠 6 次（最高 130 万）；初 REGULAR 评价 A（10,428）
架构  识别层 / 战略层 / 操作层，层间只交换数据契约
特点  读不到就留空不猜；状态纯函数可重放；动作前预算下一帧做互验
规模  120 模块 / 600+ 测试
平台  Mac 成熟，Windows 还在追赶（DMM 版最好第 2）
```

**QQ 群「初星学园情报处理部」关键结论**：
- `uihorizon 和 uinet 都到头了`，`上了十倍的训练量指标反而倒退了`
- 他们在做 **seed 反推**（2^31-1 枚举 + 观测剪枝），并已逆出来，但**定下规矩实战不用**
- 他们用 **frida 注入**（需要管理员），有人卡在 `VirtualAllocEx 0x5`
- 没人提过 **MITM/抓包**——这是我们独有的路线

详见 `docs/QQ_GROUP_NOTES.md`、`docs/HIRO_VIDEO_NOTES.md`。

---

## 四、下一步（按优先级）

> **任务拆分、验收标准、依赖顺序见 [HANDOVER_NEXT.md](HANDOVER_NEXT.md) §4**（T1 → T3 → T2 → T4 …）。
> 本节只记"大方向 + 已经完成的项"。

### ① 考试时刻的牌堆 + 洗牌（最高优先）—— 已端到端破解 ✅

```
✅ 牌堆 = UserData.userProduceProgressProduceCardList (309641228)，已重建
✅ 逐回合 ground truth = ExamTurnEndLog.field50（每回合开始手牌）
✅ 洗牌完整破解：K = (turns-3) + npc_count*turns（5 NPC ⇒ 6*turns-3）
   → xorshift32(examSeedValue) advance K → FY倒序洗 Number升序牌堆
   → 第 1 回合 SetInitialCard 先抽 isInitial 卡，再补抽
   → 四场整段精确：11-20 期中 18/18、期末 26/26；11-21 PRO 期中 15/15、期末 27/27
✅ turns = 配置回合数（中间考试到 forceEndScore 提前结束时也按配置回合算 K；
   11-21 期中配置 9 回合、实战 7 回合 → K=51）
✅ 支援强化掷点 + 弃牌堆重洗完整建模：三组样本 45/29/46 次掷点后洗 grave（12/11/20 张），
   重洗后手牌 9/9、6/6、9/9 逐张复现（2026-11-21 傍晚，见二·补三）
```

**下一步**：① 采非 5 NPC 的 produce 类型补充 K 公式样本；② 11-20 期末 T9「回合内重洗」样本
（有考试内生成卡，未建模）；③ ~~完全信息搜索第二段：生产接线 + 跨回合规划 + 重洗后段全知~~
**已完成（见二·补五）**；④ 采集进程 ↔ 决策进程实时打通（traffic.jsonl → policy 进程）。
**完成后**：seed+牌堆+支援编成+回合属性+出牌序列→精确牌序→完全信息搜索。

**注意**：中间考试有 `forceEndScore`（produce-002：baseScore 1150→封顶 1700、1200→封顶 1800），
bot/模拟器要按「达到封顶分即提前结束」处理。

### ② bot 能无人值守跑完一局

```
现状：能跑到领卡/外出等界面，修了几个死循环，但还没跑完一整局
已知坑：窗口必须是 720x1280 客户区（现在窗口 540x960，代码已按比例缩放）
下一步：起 bot 跑一局验证，卡住就抓屏幕看是哪一屏
```

### ③ 三引擎真机 A/B（需要 ② 完成）

```
rules / expectimax(ensemble) / uinet
同偶像同卡组各一局，用 extract_exams.py 比真实考试分数
```

---

## 五、关键路径速查

```
游戏副本          C:\GakumasLocal
采集工具          C:\GakumasLocal\GakumasUnlock
一键启动          C:\GakumasLocal\GakumasUnlock\一键采集启动.bat
采集数据          C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl
主数据库          D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master
元数据 dump       D:\Games\gakumas-agent\data\reverse\out\dump.cs（75MB，勿读全文）
策略配置          D:\Games\gakumas-agent\data\knowledge\policy.json（lesson.engine：rules/expectimax/uinet/beam）
当前引擎          rules（想用完全信息规划：lesson.engine=beam + auto_produce --exam-setup）
考试牌序数据      D:\Games\gakumas-agent\out\exam_setup.json（scripts/build_exam_setup.py 生成）
```

**常用命令**：
```powershell
# 提取考试结果
.venv\Scripts\python.exe scripts\extract_exams.py
# 挖 seed
.venv\Scripts\python.exe scripts\find_seed.py
# 重建考试时刻牌堆（→ deck_snapshots.json）
.venv\Scripts\python.exe scripts\reconstruct_deck.py
# 逐回合 ground truth：手牌/出牌/属性（→ exam_truth.json）
.venv\Scripts\python.exe scripts\decode_exam_actions.py --json
# 洗牌重放验证（seed+牌堆 → 牌序，对照实战手牌）
.venv\Scripts\python.exe scripts\verify_shuffle.py
# 采集数据 → 考试牌序（生产接线用；--check 顺带逐回合重放核对）
.venv\Scripts\python.exe scripts\build_exam_setup.py
# 生产接线端到端核对（手牌 36/36、重洗 3/3、策略链路 beam）
.venv\Scripts\python.exe scripts\verify_exam_wiring.py
# 跑 bot（需游戏停在培育设置界面）；--exam-setup 不传则自动用 out/exam_setup.json
.venv\Scripts\python.exe scripts\agent_cmd.py shell --command "D:\Games\gakumas-agent\.venv\Scripts\python.exe D:\Games\gakumas-agent\scripts\auto_produce.py 340 ep-xxx --skip-home --exam-setup out\exam_setup.json"
# 全量测试
.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=data/pytest-tmp-xxx
```

---

## 六、坑与注意事项

| 坑 | 说明 |
|---|---|
| 窗口尺寸 | bot 的坐标按 720x1280 设计，代码已按实际客户区缩放；但**窗口不能改大到超过屏幕**（1316 高会看不到底部）|
| 重启游戏后 token | `launch-args.json` 里的 onetime_token 会过期，从 DMM 启动一次即可刷新（一键脚本自动做）|
| VPN | 必须日本节点；TUN 和 7897 任一生效即可，两个都关会「初始化失败」|
| 守护进程 | `GDEAgent` 计划任务偶尔卡住，`schtasks /End` 再 `/Run` 重启 |
| 不要碰 D 盘原版 | `D:\Games\Gakumas\gakumas` 是用户正在用的客户端 |
| 采集必须关 unlock | `GKM_UNLOCK=0 / GKM_FORGE=0 / GKM_STATIC_USER=0`，否则污染账号数据 |
| 读 memory 不可行 | 游戏进程有反作弊，管理员 ReadProcessMemory 也被拒（实测 err=5）|
| AGPL 代码 | `data/hiro/` 是 AGPL-3.0，**只做参考/对照，不要拷进本项目** |

---

## 七、最近提交记录

```
（2026-11-21 深夜）
304d393 feat(bot): T3 实时接线（build --current + ExamPlanSelector + 运行时重载）+ T1 卡点收尾 + 文档状态
a9537b0 fix(bot): T1 真机流程修复（点击坐标/难度/领卡/外出/考试浮层/网络重试/加载）+ 出牌引擎接 produce.engine + 决策可观测性
233e9d7 feat(search): 完全信息搜索第二段——生产接线(ExamSetup/ExamDrawPlan) + 重洗后段全知(discard_order) + lesson.engine=beam
（2026-11-21 晚）
e0bd668 feat(search): 完全信息搜索第一步——ExamDrawOracle 牌序链路 + ExpectState.known_draw 确定分支 + 配对评测
c8c4c71 feat(seed): 支援强化掷点+弃牌堆重洗完整破解——三组样本 45/29/46 次掷点后逐张复现
（2026-11-21）
58b39d3 feat(seed): 期末洗牌破解——isInitial 首回合 + K=6*turns-3，期中/期末整段复现(18/18, 26/26)
59d7e07 docs(handover): 期中洗牌破解与期末异常交接
3ccaed9 feat(seed): 期中洗牌重放精确破解(18/18，advance 51次)；期末异常记录
61c07e0 docs(index): 铁律加第四条——成本纪律
ccc2653 docs(handover): 追加成本纪律
9212cd8 fix(usage): 用量按会话最后一个 totals 统计
d93a2ac feat(usage): 汇总 DSH 会话 token 用量
4e3b53c feat(seed): 定位考试牌堆字段(309641228)并重建牌组
1cd6c14 feat(seed): 第三/四场洗牌验证——K 按配置回合算，forceEndScore 提前结束也精确复现
（2026-11-20）
436b6a8 docs(master): 记录 seed 在流量里的发现与待验证项
02c20f2 feat(seed): seed 提取 + xorshift32 重放工具
7230370 docs(master): 主数据库构建（286 表）
8583ace feat(policy): PERFECT 线改用验证档位
d7db974 feat(sim): 初模式验证数值模块
ebabcd4 docs: hiro 视频要点
7bb05e2 feat(sim): 初评价公式 + 4 局实机回归
c9c2751 docs: QQ 群讨论记录
7e58b4b fix(click): 点击坐标按实际客户区缩放
9bd3551 fix(click): click_force 不再被用户门限拦截
f6b99c0 fix(produce): 外出事件识别 + 领卡坐标
eb59057 docs(capture): 采集链路文档
8b6dc49 docs(runs): 首次完整采集局
b80cc05 feat(ground-truth): extract_exams 工具
add71dc docs(reverse): 元数据解包验证
```

**测试状态**：`pytest tests/ -q` 全绿（**876 条 / 59 文件**，含 `tests/test_exam_shuffle.py` 四场考试
洗牌回放 + 「实战回合算 K 会错」回归防线 + 三组弃牌堆重洗样本的掷点数/强化增量/重洗手牌对照；
`tests/test_expectimax_known_draw.py` 8 条 + `tests/test_exam_oracle.py` 6 条完全信息搜索测试；
`tests/test_expectimax_discard_order.py` 17 条重洗后段全知 + `tests/test_exam_plan.py` 19 条
（生产接线数据层 + ExamPlanSelector 候选锁定）+ `tests/test_policy_beam_engine.py` 7 条 beam/接线策略层
+ `tests/test_policy_engine.py` 增补 4 条决策可观测性 + `tests/test_device_click_coords.py` 点击坐标回归），
`ruff check src` 与改动文件的 ruff 通过。

---

## 八、成本纪律（接手 agent 必读）

**背景**：2026-10-25 ~ 11-21 四周花了 **418 元**，其中
缓存读 43% / 未缓存输入 31% / 输出 26%——**思考只占 26%，重读占 43%**。
同样的活用对方法能压到 200 元左右。

### 8.1 你必须自己做的三件事

**① 派子智能体时显式指定低推理档**

`
机械活（跑测试、改一行、grep、读文件）→ reasoning_effort: low
常规实现（写模块、修 bug）            → reasoning_effort: medium
架构设计 / 复杂调试                    → 不指定，继承 max
`

用 list_subagent_models(provider, model) 查可用档位再传 
easoning_effort。
**不要所有子智能体都继承 max**——那是成本放大器。

**② 大文件永远 grep，不 read**

`
❌ read data/reverse/out/dump.cs          （75MB / 101 万行）
✅ grep dump.cs 关键词，只读命中行附近
❌ read data/bench_local/leaderboard_*.json 全文
✅ 用 python 脚本汇总后只打印统计量
`

**③ 完成一个子任务就提醒用户开新会话**

`
任务边界（例如「牌堆字段挖完了」）之后，上下文里的探索过程不再有价值，
但每个回合仍在重读它。开新会话 = 缓存读归零。
`

### 8.2 汇报要短

`
❌ 把命令输出原样贴回来
✅ 只给结论 + 关键数字 + 文件路径
`

每次长输出都会进入上下文，后续每回合都要重读。

### 8.3 失败立刻写进 TROUBLESHOOTING.md

试错是必要的，但**失败的推理过程留在上下文里会一直烧钱**。
写进文档后就可以忘掉它。

### 8.4 成本参考线

| 会话时长 | 建议 |
|---|---|
| < 1 小时 | 正常 |
| 1-3 小时 | 注意上下文大小 |
| **> 3 小时** | **该换会话了** |

单个会话超过 20 万 token 上下文后，每回合的成本是初始的几十倍。
