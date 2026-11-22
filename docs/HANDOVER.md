# 项目交接（2026-11-22 B6 + 外部整合包分析 更新）

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

**仍未做**：T1 整局真机验收（20 分钟内跑完一局）、T3 真机考试日志验收、T2 三引擎 A/B、T4 策略强度
（T4 已由 B1 完成离线升级，见二·补十九；真机 A/B 仍待 T2）。
**注意**：换一局后的 `[exam-plan] mismatch` 是预期（离线 setup 来自别的采集），不要当 bug 修（FAILURES #33）。


---

### 二·补七、11-21 深夜三段（第一次完整跑完一局 + 禁跳规则 + 7 类真机卡点）

**战报（20:55–22:20，7 次短跑，每次 4–6 分钟）**：从"某一局课程中途"接手，第一次**完整跑到结算**：
期中考试 **914 分 / 第 3 名** → 培育终了 → **最终评价 C / 4242**（22:19 停在「点击继续」页）。
对照：用户手动 A/10237、旧版 bot C+/5992。

**这局为什么崩（因果链，均有日志/截图）**：
1. 课程里"读不到牌的价值 → 搜索建议 SKIP → 规则执行跳过"→ 大量 `lesson-skip`，属性没涨起来（见 FAILURES #39）；
2. 考试里 9/32 步 `eng=expectimax fallback=搜索未产出动作，退回规则`（同上，搜索建议 SKIP 但考试禁跳）；
3. 全知优势 **0 锁定**：采集进程没开 → 拿不到当前场 seed → `[exam-plan] attempts=8 retries=8 locked_turn=0`
   （4 个候选全部对不上）→ known_draw/beam 一手都没参与。
4. 加上 3 类界面卡点反复吃掉步数（见下面修复表）。

**修复（提交 4b07fa7 / 8a2af2b / b231b3f）**：

| # | 问题（现象） | 根因 | 修复 | FAILURES |
|---|---|---|---|---|
| 1 | 初模式「授课」答题屏 → 点快进 → 弹确认 → 循环 95 步 | 有「快进」按钮就被当剧情 | `class-quiz` 分支：点三个属性答案行（Vo/Da/Vi） | #34 |
| 2 | 领奖弹窗被误判成答题屏，点空白 10 步 | 半透明弹窗背后课程 HUD 仍可见 | 答题屏排除「请选择要领取/领取/再抽选」 | #35 |
| 3 | 「回合结束」确认框没人点「是」→ card/force-skip 死循环（3 次复现） | 课程快速路径把整屏 OCR 省了，`text` 恒为"剩余回合" | 卡住（同屏重复）即强制整屏 OCR + 每 5 步回看 + 先于点「是」 | #36 |
| 4 | 用户碰键鼠 → 所有点击被暂停门拒绝 → 画面僵住 → 强制 SKIP | 无人值守却开着交互暂停门 | `--ignore-user`（`pause_gate.gate_ms=0`，日志会记） | #37 |
| 5 | 4 费牌被记成 29 费 | 费用预览把体力条读两次（cost==stamina 被放过） | 费用必须严格小于体力才入缓存 | #38 |
| 6 | 搜索 SKIP 被直接执行 → 大面积跳课（C/4242 主因） | 把"读不到价值"当"0 分" | **用户规则：只有所有牌都付不起才允许 SKIP**；四引擎全拦截；`unknown_score_fallback=skip` 废除 | #39 |
| 7 | 搜索为什么退回规则说不清 | 回退原因只有一句"搜索未产出动作" | 日志细化：`complete/nodes/ms` 或 `CardSpec 失配` | #39 |

**新增规矩（后续不许破）**
- 跑真机整局必须带 `--ignore-user`，人不要碰键鼠、不要最小化窗口；
- **SKIP 只在"所有牌都付不起"时允许**；读不到分/分低/搜索建议都不算（用户 2026-11-21 指定）；
- 读不到价值 = OCR/卡表问题 → 去修那个，不许用 SKIP 补偿；
- 每局日志首行 `[engine]` + 每步 `| eng=… fallback=…`，先看这个再谈分数。

**测试**：`pytest tests/ -q` 全绿（**904 条 / 62 文件**）；新增回归：授课答题屏 2、领奖误判 1、禁跳规则改写 6+。

**下一步（二选一，用户决定）**
- A：直接重开一局初（用修好的策略）→ 验收"不再乱跳 + 分数回升"；
- B：先开采集（游戏走采集客户端重启，当前会话丢弃）→ 带实时 seed/全知跑。

---

### 二·补八、11-21 深夜四段（用户规则：bot 不许回退 rules）

**用户指令**（2026-11-21）：**「你把 rules 禁用了，不许 bot 回退 rules」**。

**改了什么**
- `LessonPolicy`（[lesson.py](../src/gkagent/policy/lesson.py)）：搜索引擎（expectimax/beam/uinet）
  不再先算规则动作、失败时也不拿 rules 兜底——
  - 搜索建议 SKIP 但还有付得起的牌 → 按**搜索自己的动作排序**硬打（expectimax `actions` /
    beam 根回合计划首牌 / UINet 合法动作概率）；
  - 状态没读全（手牌/体力/回合/卡表）→ 返回 `wait` 等下一帧重读，日志
    `fallback=等待重读：…（不回退 rules）`；
  - 搜索异常 / 搜索结果不在手牌 → 抛 `RuleFallbackBlocked`；
  - `engine=` 写错 → 构造期 `ValueError`（不再静默变 rules）。
- `scripts/auto_produce.py`：bot 入口默认引擎改为 **expectimax**（不再默认 rules）；
  `--engine rules` 仍保留但只用于 A/B 对照/离线复现（日志警告）；`--engine`/`produce.engine`
  非法直接 exit 2。捕获 `RuleFallbackBlocked` → `[engine][BLOCKED]` + `fallback= rule-fallback-blocked`
  并中止本局（`stuck=true`）。`decide_lesson_pick` 的 `pick_hand_card` 兜底、卡名脏了用规则另选、
  连点不动换牌等老规则路径在搜索引擎下一律不接（改为等待/中止）。
- `lesson_pick.py`：严格模式不再调用 `fallback`；无法执行的动作抛 blocked。
- 测试：expectimax/beam/uinet 的「异常退回 rules」用例全部改写为「必须 blocked」；新增
  skip→按搜索排名硬打、beam 根计划首牌、uinet 概率硬打、wait 语义、显式 engine 写错等回归。

**提交**：`ae86e1c` feat(policy): 禁用 rules 回退——搜索引擎失败必须暴露，不许静默改用规则

**改后基线（全绿）**
- `verify_shuffle.py`：4/4 场整段复现（含重洗）
- `pytest tests/ -q`：**887 passed，1 skipped**（888 条收集 / 61 文件）全绿
- `build_exam_setup.py`：4/4 场、初始段 86/86 张、重洗段 24/24 张
- `verify_exam_wiring.py`：手牌 36/36 回合、重洗 3/3、known_draw 29/29、策略链路 beam 出牌 28 次

**下一步**：T1 整局真机验收。日志里不应再出现 `fallback=搜索未产出动作，退回规则`；
若出现 `[engine][BLOCKED]`，说明搜索被真实缺陷挡住——按原因修 OCR/卡表，不许把 rules 加回来兜底。

**上真机前的模拟器整局 A/B（2026-11-21 深夜，本条同时做）**
- 新增 [sim_engine_ab.py](../scripts/sim_engine_ab.py)：同一批种子跑完整 16 周培育局，
  训练和考试都注入真 `LessonPolicy.decide`（`ProduceSim.exam_policy_fn` 为本次新增；默认仍 greedy）。
- 三组种子共 **76 局**（seed 9000/21000，16+30+30 局，rules/expectimax，预算 800ms）：
  - `RuleFallbackBlocked` **0**、异常 **0**；每局都跑完 16 周 + 2 场考试；
  - 模拟器口径满局评价 **C+ 率 100%**；P50 评价点 rules **5049** / expectimax **5063**；
  - 配对差在噪声内（16 局 Δ−15.2、30 局 Δ−4.9；与 EXPECTIMAX「真实牌组 beam 只 +3.0」一致：
    差距在 V_leaf，不在回退）；
  - 单局模拟耗时：rules ~0.01s / expectimax ~0.2–0.3s（800ms 预算在小状态上提前完成）。
  - 边界：模拟器没有 UI/OCR，只能证明**决策层**不卡、不回退；UI 卡屏仍需真机 20 分钟验收。
- 顺手修掉的模拟器接线坑：考试策略原硬编码 `greedy_policy`（新增 `ProduceSim.exam_policy_fn`）；
  `LessonSim` 的指針体力修正会让引擎选的牌"实际付不起"（A/B harness 记为 `非法/局` 并用合法动作
  兜底，属已知 G5 费用模型缺口，不影响"有没有回退 rules"的结论）。
- 新增回归：`tests/test_strict_engine_sim.py`（整局 8 周 + 考试，必须 0 blocked）、
  `tests/test_sim_produce.py::test_exam_policy_can_be_injected_for_offline_ab`。

**真机防卡死（同条）**：`auto_produce --max-minutes`（默认 30，0=关闭）。超时写
`episode-timeout` failure 并主动停局，不再出现"卡两个多小时还跑到 C"；新增
`tests/test_auto_produce_timeout.py`。整局起跑命令带上它即可。

**提交**：`09b9358` feat(sim): 上真机前整局引擎 A/B + 考试策略注入 + auto_produce 墙钟上限

---

### 二·补九、11-22 凌晨（T4 起点：V_leaf 平手项 + beam 采样分支）

> ⚠️ **2026-11-22 B1 复核：本节 beam 数字（91.3 / 105.5 / 111.2）作废**——评测执行器
> `_execute_plan` 白丢回合 bug；修正后 beam unknown 164.0 / known 165.5（二·补十九）。
> within 列（143.1）与 tiebreak 方向仍有效。

**背景**：用户要求先补「我们 vs 别人的差距」、暂不跑真机。按 [HANDOVER_NEXT §9](HANDOVER_NEXT.md)，
差距主要在策略强度（T4 V_leaf）与机制覆盖（T5），先动 T4。

**诊断（真实小牌组 14 张 / 5 回合，CLEAR 120 / PERFECT 170）**
- beam 明显不如回合内 expectimax（91.3 vs 143.1，60 局同 seed）：解析档位效用封顶 2.0 →
  深搜里大量「稳过」分支打平 → 搜索的平手 tie-break 优先保留出牌位/体力（存资源）→
  beam 少打牌、存体力。
- σ 从 10 扫到 80 对两者决策完全无影响；beam 的抽样分支 `branching` 从 3 提到 10 有明显提升。

**改动（默认关闭，生产行为不变）**
- `AnalyticLeafValue.score_tiebreak`（默认 0）：>0 时在档位效用上加极小的
  `预测总分 / PERFECT 线`，给平手一个分数排序；默认 0 逐位保持历史行为。
- `scripts/eval_known_draw.py` 新增 `--score-tiebreak` / `--branching`。

**配对评测（60 局同 seed）**
- beam：91.3 → **105.5**（+14.3，95% CI [+7.9, +20.6]）→ **111.2**（再加 branching=10，
  +19.9，CI [+12.8, +27.1]）；CLEAR 28.3% → 36.7%。
- within：143.1 → 143.4（+0.3，CI [−0.0, +0.6]，基本无副作用）。
- **beam 最好仍比 within 低 22.3%**：T4 DoD 未达成，`score_tiebreak` 保持默认 0，生产不默认 beam。

**结论/下一步**：平手项是真因之一，但主因仍是 **V_leaf 的 μ 不准**（存体力被高估）；
下一步做 **rollout 叶子估值**（叶子用 `LessonSim`/greedy 快跑剩余回合），再按 T4 决策门考核；
三次 learned 线性 V 失败说明"线性特征+回归"不通。细节见 [EXPECTIMAX.md](EXPECTIMAX.md) 同名小节。

**测试**：`pytest` 全绿（**889 passed / 1 skipped，890 条收集 / 61 文件**）；新增 2 条 leaf tie-break 回归。

**提交**：`4c9f024` feat(eval): T4 起点——档位效用平手项 + beam 采样分支（实验，默认关闭）

---

### 二·补十、11-22 凌晨（T4 rollout 叶子：实现完成，结果负）

> ⚠️ **2026-11-22 B1 复核：本节 beam 侧数字作废**（同一 `_execute_plan` bug）；within 侧
> rollout 叶子 ≈ 中性（145.4 vs 143.2）仍有效。修正后 B1 的受控 frontier 叶子为中性，
> 见二·补十九。

**做了什么**（`src/gkagent/sim/expectimax.py` + `scripts/eval_known_draw.py`）
- `sim_from_state()`：把搜索的纯 `ExpectState` 快照重建成可跑的 `LessonSim`
  （`known_draw` → 已知牌序；未知 → 按 rollout rng 洗牌；叶子空手补一手；P 道具/除外区/成长计数全带过去）。
- `RolloutLeafValue`：叶子处用 `LessonSim` 跑完剩余回合，μ=分数增量均值，σ=max(sigma, 实测std)；
  支持 `policy=greedy|within`（within = 每回合小预算 expectimax）；按 `canonical()` 缓存。
- `eval_known_draw.py` 新增 `--leaf {analytic,rollout}`、`--rollouts`、`--rollout-policy`、
  `--rollout-budget-ms`，默认全部保持 analytic（生产行为不变）。

**结果（small 60 局，beam width4 / budget100ms / branching10 / tiebreak=1e-3）**

| 叶子 | unknown | known | CLEAR(u/k) | fallback |
|---|---:|---:|---:|---:|
| analytic（基线） | **111.3** | **111.4** | 35.0% / 38.3% | 0 |
| rollout greedy r=3 | 103.0 | 104.1 | 28.3% / 26.7% | 0 |

- 20 局变体：rollout 无 tiebreak 更差（78.8~89.0）；`rollout-policy=within`（5ms）也只有 78.8/85.3；
  within 策略本身 analytic 145.4 vs rollout 143.2（≈中性）。
- **结论：最小版 rollout 叶子没有改善 beam，反而 −7~8 分**；根因是 rollout 策略（greedy）比执行策略
  （回合内 expectimax）弱，leaf μ 的排序与执行结果错位。rollout 次数 1/3/6 不改变结论。

**为什么停在这里**：用执行同强度策略做 policy-evaluation 叶子，成本 ≈ 每叶子"剩余回合 × expectimax"，
beam 数百端点上是十几倍耗时，当前预算不可行；learned 线性 V 已失败三次。下一步建议：
①只对 beam 最深端点的受控 policy-evaluation 叶子；②用 rollout 数据当监督信号重训 `v_leaf.json`；
③补 T5 机制建模。细节与复现命令见 [EXPECTIMAX.md](EXPECTIMAX.md)「rollout 叶子实验」。

**测试**：新增 `tests/test_rollout_leaf.py` 7 条（快照往返/缓存/边界/单调性/known_draw 确定性/不改输入）；
全量 `pytest tests/ -q` 收集 **897 条（1 skipped）全绿**；`ruff` 通过。

**提交**：`366131a` feat(t4): rollout 叶子最小版（ExpectState→LessonSim 快照 + RolloutLeafValue + eval 开关）——实验负结果，默认关闭

---

### 二·补十一、11-22 凌晨（known_draw 事前检测：额外 RNG 机制）

**背景**：群公开的「考试 RNG 全部显式消费入口」清单（已归档到 [QQ_GROUP_NOTES](QQ_GROUP_NOTES.md)）说明，
除我们已建模的 K 组成之外，恐慌/卡牌搜索/随机选取/生成卡/随机移动还会额外消耗 xorshift32 —— 这类牌组
`known_draw` 只能用到第一个事件，之前只能靠"核对失败才停用"事后兜底。

**改动**
- 新增 `src/gkagent/sim/exam_risk.py`：`EXTRA_RNG_EFFECT_TYPES` + 卡表索引 + `deck_rng_risks()`
  （返回 `[{card_id, effects}]`）+ `known_info_ok()`/`format_rng_risks()`；
- `build_exam_setup.py`：默认全量 + `--current` 记录都写 `rng_risk`，命中打印「known_draw 不可验」；
- `ExamSetup.rng_risk` + `known_info_ok`；`ExamDrawPlan.start()` 对不可验 setup **直接停用**
  （不建 oracle、known_draw 恒空，reason 写明）；`exam_plan` 单测覆盖；
- `auto_produce.build_exam_plans()`：加载候选时跳过不可验的并打日志
  `[exam-plan] 跳过 N 个含额外 RNG 机制的候选`；安全设计不变（核对失败仍自动停用）。

**实测**
- 卡表 1829 张里 **169 条**带额外 RNG 机制（`ExamCardCreateId/CreateSearch/Move/ForcePlayCardSearch/
  SearchEffectPlayCountBuff/...`）；
- 我们验证过的四场考试牌组命中 **0** → 纯牌组，4/4 精确复现成立（与之前结论一致）；
- `build_exam_setup` 4/4 场、86/86 + 重洗 24/24；`verify_exam_wiring` 36/36、3/3、29/29 不变。

**测试**：新增 `tests/test_exam_risk.py` 8 条（卡表扫描/牌组扫描/序列化往返/计划拒用/摘要格式）；全量 `pytest` **904 条收集（1 skipped）全绿**。

---

### 二·补十二、11-22 凌晨（采集+真机首次合体：4 次短跑、剧情选项修复、群文件情报）

**背景**：用户手动开 DMM 刷新 token，首次把「采集链路 + 真机 bot + 全知候选」合到一局里跑。

**过程与结果**
- 采集：`一键采集启动.bat` 成功（本地服务 18443/18444、token 01:24、C 盘副本 game 启动、traffic 写入）；
- bot 4 次短跑（ep-t3-1..4）全部中途停：
  - 1–3 卡在培育开场「日文剧情二选一」：我们 OCR 字典是中文，日文选项只剩碎片（`飲物持`/`？`/`、。`），
    旧逻辑只点「快进」→ 循环 100+ 步；
  - 4 已过剧情选项、进培育（外出事件选择正常），但**舞蹈课程连续打 buff 牌 → 0 分 FAILED**，
    随后结果页 `result-tap/gain` 连点 10 次被自保护停局；
- **修复**（`584f742`）：剧情选项按布局识别（中部白色气泡宽 200–700/高≤90）+ 连续 5 次快进兜底
  + 有快进的帧补读中下部区域 OCR；2 条回归测试。其余两处进 FAILURES #42/#43 待修。

**群文件情报（用户下载，已存 `D:\GakumasAgentArchive\group_files\`，不入仓库）**
- 论文《体系建模概率分析与高分路线搜索》（花吹雪また一年/2K9TNJ8S，2026-11-03）：GakumasCLI +
  原生核心 GKMSCLIGPU；三体系/评分语义/支援强化分布/Bellman 上下界/GNRPA+精英前缀重启；
  74 局逐局重放一致、704 场考试 666 场终分一致、实例 C 141,225→194,962。
- `run12-card-picks.pdf`（11-11）：**2B 模型**一个决策一次前向、无搜索；期末 1st 324,063、SS+/18,866。
- `GKMSMAA_20261120.zip`：魔改 MaaGakumasu v1.5.3（**AGPL-3.0**）+ gkmsmaa 执行层
  （station 127.0.0.1:8765 出计划 → 按屏执行，produce/exam follow、probe、H.I.F TOP100 ranking）。
- `launch_gakumas.ps1`：DMM 免客户端直启（pf_access_token）。
- 结论：他们领先「精确引擎+离线优化+2B 决策+MAA 执行」；我们领先「MITM seed→洗牌 4/4 验证」，
  但 GKMSMAA 文档表明他们也有客户端采集 → 全知非独占，需尽快把信息优势变成成绩。
- **边界**：GKMSMAA 是 AGPL-3.0 派生，禁止拷入本仓库；论文公式可引用并标注作者/日期（见 PROVENANCE）。

**下次开工**
1. 修 FAILURES #42（硬打必须保证得分：优先 `score>0` 且付得起的牌，buff/打分按剩余回合平衡）与
   #43（静态结果页找「下一步/继续/完成」）；
2. 重跑一局到考试，验证 T3 `[exam-plan] locked_turn=2~3 / verified=N`（采集已可随时启动）；
3. 之后按群论文补 T5 公式 / 做离线固定实例最优路线（自写 Bellman/GNRPA，不抄 AGPL 代码）。

---

### 二·补十三、11-22 凌晨二段（群文件解包：OCR 根因证实 + 魔改 MAA/手机实验版结构）

**结论（重要）**：我们的 OCR 问题根因 = **RapidOCR 默认中文模型（ch_PP-OCRv4，字典无假名）**，日文 UI 只剩碎片；
换成魔改 MAA 包自带的**日文 OCR 模型 + keys（18,708 行，含假名）**后，同一截图能完整读出
「ヨーグルトパフェ／つくねハンバーグ／ドリンクバー／そこまで真剣だと…」。管理员"没问题"是因为 MaaGakumasu
自带日文模型（也可能用 Localify 中文化客户端）。**这是能一次性修好大量文本分支的 P0**。

- 群文件结构/许可证/实测命令/修复方案：见 **[GROUP_FILES_ANALYSIS.md](GROUP_FILES_ANALYSIS.md)**；
- `GKMSMAA_20261120.zip`（AGPL-3.0，MaaGakumasu 魔改）：station（127.0.0.1:8765）出计划 → `gkmsmaa`
  执行层按屏点（follow/produce-follow/probe/ranking；大量 tap 确认/重试/提权逻辑）→ 只学架构不拷代码；
- `GKMS小白鼠实验版.apk.1`（LSPatch 打包）：origin.apk + **Localify 模块**（master 中文翻译，81 MB）+
  **gkms-phone 模块**（`libgkms-gadget.so` 24 MB + portal/pem/identity → 手机端 gadget 桥）；
- 解包位置：`D:\GakumasAgentArchive\group_files\{GKMSMAA, GKMS实验版APK}`（**不入库**）。

**A1 已完成**（2026-11-22，见二·补十四）：OCR 换官方 PP-OCRv6 多语言模型，日文完整可读。
**A2 也已完成**（2026-11-22，见二·补十五）：F#42 课程硬打必须得分——修掉课程 HUD 语义
（右上属性值/圆环还差分）与"每回合默认 1 张牌"两个模型错误，硬打保证得分。
**A3 也已完成**（2026-11-22，见二·补十六）：F#43 结果页空转——真根因是日文饮料选择事件屏
（中文 OCR 读不出假名选项 + P 费标签被飘字正则当成 +N）→ 点中央空转 10 步。
接着按 WORKPLAN 阶段 A 做 A4（离线回放素材）→ A5（T3 离线预演），
**阶段 A 已全部完成**（A5 见二·补十八）；之后进阶段 B/C/D 离线，全部离线做完再上真机。

**总作战计划**：见 [WORKPLAN.md](WORKPLAN.md)（离线全部做完 → 真机 T3→T1→T2 → gkbench 比算法；
含 A1 OCR / A2 F#42 / A3 F#43 / T4 / T5 / 可靠性 / 数据 / 真机 / gkbench 各阶段与 DoD）。

### 二·补十四、11-22（WORKPLAN A1 落地：OCR 换日文/多语言模型 ✅）

**结论**：RapidOCR 内置中文模型（`ch_PP-OCRv4`，字典无假名）→ 官方 **PP-OCRv6_small_det +
PP-OCRv6_small_rec（Apache-2.0，多语言）**。同一张 `step_025.png` 日文从碎片变成完整句子，
中文 UI 同时可读；F#41/#42/#43 的「文本读不到」前提修好。按 WORKPLAN 先做离线阶段 A 剩余
（A2 F#42 / A3 F#43 / A4 回放素材 / A5 T3 离线预演），再上真机（阶段 A 现已全部完成）。

- **代码**：`OcrEngine(config_path=)` + 环境变量 `GKAGENT_OCR_CONFIG` + 本地 `configs/ocr_jp.yaml`
  自动发现（优先级从高到低；都没有 → 内置中文模型，默认行为不变）。配置/模型文件缺失**直接报错**，
  不静默回退中文模型。两阶段主引擎和单行 `_line_core` 引擎共用同一套模型配置；
  模型路径支持 `%VAR%`/`$VAR`、相对 YAML 目录解析；`describe_model()` 给日志。
- **模型/工具**：`scripts/download_ocr_models.py`（官方 URL + sha256 锁定、校验、从 rec
  `inference.yml` 导出 18,708 行字典，生成 `configs/ocr_jp.yaml`；`--check` 自检）；
  `configs/ocr_jp.example.yaml`（完整 RapidOCR 配置 + v6 det 预处理参数）；
  `scripts/ocr_probe.py` 单图验字。模型落 `data/models/ocr_jp/`（`data/models/*` 已 gitignore）。
  AGPL 的魔改 MAA 日文模型只本地对照（官方 v6 与它逐行输出相同），**未入库**。
- **实测**（`data/auto/step_025.png`，720x1280，全屏 ≈1.0s）：
  `ヨーグルトパフェ / つくねハンバーグ / ドリンクバー / そこまで真剣だと慰労を超えますが…… /
  倉本さんのお気に入りは……`；中文 `外出 / 审查基准 / 快进` 同时读对；
  同帧 `ProduceDriver` 判 `event-choice/last-row` → 点 (360,935) 选项（不再点「快进」）。
- **中文 UI / 性能回归**（`scripts/bench_ocr.py --after --verify --threads 8`，JP 模型）：
  关键词检查 **5/5**（行动/事件/领奖/课程/加载屏中文关键词全部可读）；
  行动页单步 ≈**189ms**、课程页读屏 ≈**402ms**、全屏 read ≈752ms（仍远低于 1500ms 目标）。
- **测试**：`tests/test_ocr_config.py` 17 条（优先级/路径/缺文件报错/单行引擎接线）+
  `tests/test_ocr_jp_model.py` 4 条真图（日文/对白/中文 UI/决策选选项；模型缺失自动 skip）；
  修复基线过期断言 `test_read_fast_event_page_uses_option_rows`（事件快速路径补读对话区后
  `read_calls` 不再为 0，改为断言只补读 `FAST_DIALOGUE_AREA`、不整屏 OCR）。
  全量 `pytest tests/`：**926 passed / 1 skipped**（927 条收集 / 65 个测试文件，212s；A1 当时口径，
  A4 后当前为 950/1、951 收集 / 68 文件，见二·补十七）；`ruff` 通过。
- **真机日志**：`auto_produce.py` 首行新增 `[ocr] 模型 = …`——上真机先确认不是内置中文模型。

### 二·补十五、11-22（WORKPLAN A2 落地：F#42 课程硬打必须得分 ✅）

**结论**：F#42 不是"硬打排序不好"这么简单，是**两个课程模型假设和真机不一致**叠在一起：

1. **课程 HUD 语义读反**：右上角是**培育属性值**（图标+评级+数字），不是课程分；正中圆环
   「CLEAR截止 / PERFECT截止 N」是**还差 N 分**到当前档位（过了 CLEAR 换成 PERFECT）。
   旧代码把属性值当课程分、把还差分当过关线 → 真机帧「属性 90 / CLEAR截止 30」被当成
   "分数 90 ≥ 过关线 30，已经 PERFECT" → expectimax 档位效用全封顶（动作全 2.00 平手）→
   每回合建议 SKIP → 禁跳规则按动作排序硬打 → 稳定挑 buff 牌 → 整节课 0 分 FAILED。
2. **每回合出牌上限写死 3**：游戏**默认每回合只能出 1 张牌**（一手 3 张是"选 1 张"；
   额外出牌来自卡效果/P 道具）。证据：四场采集考试 39 个实战回合里 32 回合正好 1 张、
   7 回合 2 张（2 张的都是卡效果 `ExamPlayableValueAdd`）；课程实拍"打 1 张 → 剩余回合 -1"；
   社区/维基口径一致。旧搜索 `play_limit=3` 让"buff + 两刀"永远划算 → 每回合先铺 buff。

- **代码**：
  - `vision/lesson.py`：`LessonReader` 读圆环档位 + 按"属性值 − 开课属性值"换算课程分；
    过关线 = 已得分 + 圆环还差分；满分线查档位表（普通/SP = 2×，追い込み 90→360、165→600）。
    `LessonState` 新增 `perfect` / `goal` / `attr` 字段（`score` 语义改为**本课已得分**），
    `reset_lesson()` 每课重置属性基线；`auto_produce.py` 在课程开始处调用。
  - `policy/lesson.py`：`_search_state` 改 `play_limit=1`（每次决策只建模"现在打 1 张"，
    额外出牌下一帧重新读屏再决策；`plays_used` 不再喂搜索，避免 plays_left=0 假死），
    满分线用读屏换算值；**硬打保证得分**：搜索建议 SKIP 时先筛"屏幕分数预览 > 0"的牌
    （buff 牌记 0）按（搜索价值, 屏幕分）硬打；一张正分牌都没有才退回原排序。
  - `auto_produce.py`：`lesson_score` 记**真课程分**（0 分也记，旧日志把属性值写成 lesson_score）。
- **实测**（真机帧 `data/auto/step_001.png` = ep-t3-4 step1，与 ep-t3-3 step286 同屏；
  `tests/fixtures/lesson_ep_t3_4_step001.png` 已归档）：修复前 `name-pick 表情的基础`（buff，0 分）；
  修复后回放该帧 → `name-pick 魅力的基础`（29 分，硬打保分）。前一回合帧（turns=2）修复前也会
  先铺 buff，修复后直接打 `击掌+`（23 分）。
- **测试**：`tests/test_lesson_play_f42.py` 3 条（HUD 换算 / DoD 回放 / "buff 多、分数少"）+
  `tests/test_lesson.py` 4 条 HUD 换算假 OCR 单测 + `test_hardplay_prefers_scoring_card_on_flat_tie`；
  修复过程中还发现并修掉一个连带问题：搜索把 `plays_used` 喂进去后，模拟器 A/B 同一回合第二次
  决策会 `plays_left=0` → `RuleFallbackBlocked`（`tests/test_strict_engine_sim.py` 抓到）。
- **基线复核**：全量 pytest **934 passed / 1 skipped**（935 收集 / 66 文件）；四条基线里
  ② 的期望值从 926/1 变成本数字；①③ 未变；④ `verify_exam_wiring.py` 仍 4/4、36/36、3/3、
  known_draw 29/29、beam 出牌 28 次（`play_limit=1` 不改变离线核对口径）。
- **遗留（不属于 A2，已记 WORKPLAN T5/B3 / FAILURES #42）**：`sim/lesson.py` 的
  `plays_per_turn` 默认 3 也要对齐真机（默认 1 张 + 额外出牌），模拟器整局 A/B 与评分要重标；
  每回合 1 张对**考试**同样成立（本修复顺带改了考试搜索的出牌上限）。

### 二·补十六、11-22（WORKPLAN A3 落地：F#43 结果页空转 ✅）

**结论**：F#43 不是"静态结果页找不到按钮"——看真机截图才查清：ep-t3-4 steps 20–29 的 10 帧
是**日文饮料选择事件屏**（`ヨーグルトパフェ -100P / つくねハンバーグ -50P / ドリンクバー 免费`，
右下「快进」、底部对白）。两层根因：

1. **旧中文 OCR 字典没有假名**，三条选项行一条都读不出 → `option_rows=0`，事件屏识别不出来
   （F#41 同类；A1 换日文模型后该屏已能读出整行选项）；
2. **飘字正则 `[+\-]\s*\d+` 把右侧 P 费标签「-100 / -50」当成 +N 飘字** → 走进 4.5) 的
   `result-tap/gain` 分支，点屏幕中央 (360,1000)（对话区，点了没反应）→ 同动作连续 10 次自保护停局。

- **代码**（`tasks/produce_ui.py`）：
  - `_GAIN_RE` 只认**正收益**（`+45`/`＋45`）；负数是 P 费/体力消耗，绝不当飘字；
  - 事件屏退化兜底：`option_rows=0` 但还读得到 P 费标签时，用「最后一个费用标签中心 +138px」
    点免费项；`_EVENT_ROW_COST_RE` 费用后缀放宽到 3 位（`-100`）；
  - 静态结果页（原计划的修法）：第 3 次飘字起**每帧**找「下一步/继续/确定/完成/关闭/领取/了解」，
    找到就点、找不到才继续点中央（保持计数，不再回到 0 重数）。
- **实测/回放**（真机帧 `data/auto/step_021.png` → `tests/fixtures/event_ep_t3_4_drink_choice.png`）：
  修后生产链路 `read_fast → decide` 判 `event-choice/last-row` → 点 (360,935)（第 3 行免费项
  `ドリンクバー`），同帧下一决策 = `confirm`（选中→确认两步）；同屏连续 10 步全部 `event-choice`，
  不再出现 `result-tap/gain`。**退化条件也验证**：临时移走 `configs/ocr_jp.yaml` 复现旧中文模型
  （选项行全读不出、只剩 `-100`/`-50`）→ 新代码仍判 `event-choice/last-row` 点 (360,901) 免费项；
  旧代码同帧正是 `result-tap/gain` 点 (360,1000)。
- **测试**：`tests/test_produce_ui_f43.py` 7 条（3 条真机帧回放 + 4 条合成：P 费不是飘字 /
  无选项文字用费用标签 / 静态页第 3 下点「下一步」/ 没按钮时保持计数点中央）。
- **基线复核**：全量 pytest **941 passed / 1 skipped**（942 收集 / 67 个测试文件；A3 当时口径，
  A4 后为 950/1、951 收集 / 68 文件，见二·补十七）；① 洗牌 4/4 + 重洗 3/3、
  ③ exam_setup 4/4 场 86/86 + 24/24、④ wiring 36/36 + 3/3 + known_draw 29/29 + beam 28（A3 只改
  UI 决策规则，不动数据链路）。
- **DoD（离线）**：真机帧回放从旧日志的 `result-tap/gain` 空转变成 `event-choice/last-row → confirm`
  两步推进；真机整局验收留到阶段 E（T1，按 WORKPLAN E2 跑 `--ignore-user` 整局）。
- **教训**：**先看截图再信日志的屏幕分类**——日志写"结果页"，实际是日文选择屏；
  「P 费负数」和「+N 飘字」长得一样，正则里一个符号之差就是 10 步空转。日文 OCR（A1）把这类
  「读不到选项」的屏一次性修好一大片，但**不能只靠模型**，事件屏识别要有不依赖 OCR 的兜底。
- **提交**：`106ef2b`（fix：代码+真机帧回放测试+fixture）、`cdf7fca`（docs：补哈希）、
  `1a4b7f8`（chore：`scripts/probe_frame_decide.py` + `scripts/scan_event_frames.py` + gitignore）。

### 二·补十七、11-22（WORKPLAN A4 落地：离线回放素材 ✅）

**目标**：把真机关键屏归档成 fixture，用「真像素 → 真 OCR → 生产 `read_fast`/`decide`」做回归，
服务"全部离线做完再上真机"；六类屏至少要覆盖：日文剧情二选一 / 课程 buff / 结果页 / 外出事件 /
考试浮层 / 回合结束确认框。

- **归档**（`tests/fixtures/`，新增 `README.md` 溯源表）：本次新增 6 张真机帧 —
  `story_choice_ep_t3_3_step049.png`（ep-t3-3 step49 培育开场日文剧情两气泡「飲み物を持ってきました /
  慣れてきましたか?」）、`result_ep_t3_4_step004.png`（课程结果页「Da.上升了0!」）、
  `outing_choice_ep_full1_step049.png`（外出三选一「悠闲懒散 -8 / 彻底运动 / 去购物怎么样 -4」）、
  `exam_card_overlay_20261115.png`（考试页 1st..6th + 卡片详情浮层「考试·舞台中仅限1次」）、
  `confirm_dialog_ep_t3_4_step019.png`（真机「快进确认」弹窗）、`drink_limit_20261114.png`
  （持有上限「请选择保留的3瓶饮料 / 还可选择2个」）。另沿用 A2/A3 已归档的课程 buff 帧与
  外出饮料事件帧；`data/auto/*.png` 是轮转覆盖的，归档进 `tests/fixtures/` 才不会再丢。
- **工具**：新增 [scripts/scan_frames.py](../scripts/scan_frames.py)——目录/glob/单帧批量走
  `read_fast→decide`，输出 `screen/action/点击坐标/OCR 文本`，支持 `--screen/--contains/--json/--limit`
  （A4 挑帧真源；`scan_event_frames.py` 保留为廉价小框预扫）。`probe_frame_decide.py` 的假 device
  补 `click/swipe`，否则 drink-keep 滚动分支会 `AttributeError`。本次扫了 1352 张历史截图
  （data/auto step+fail 487、data/manual/arun/bench/video/ssr 511、data 根目录 354）+ data/bench 26 张。
- **测试**：`tests/test_frames_replay_a4.py` 9 条，全部真机帧回放：
  1. 日文剧情二选一（读得出两条假名选项、`story/choice` 点上部气泡，**不点右下快进** F#41）；
  2. 课程 buff 帧（`decide` 交 `LessonPolicy`，`LessonReader` 换算出 0 分/还差 30，策略打
     「魅力的基础」29 分不选 buff F#42）；
  3. 结果页（`result-tap/gain`→第 3 次 `next`，A3 修法；点中央 (360,1000)）；
  4. 外出三选一（`event-choice/last-row`→`confirm`，负 P 费不是飘字）；
  5. 考试浮层（`exam_mode=True` + `card_detail_open=True` + 卡名「在我发现的世界」+ `kind="audition"`
     手牌 + 体力 0 时 `lesson_stamina_gate(exam=True)` 仍返回 None → 考试永不禁跳 F#17/F#32）；
  6. 真机确认弹窗（点 OCR 读到的「确定」按钮）；
  7. 回合结束确认框（⚠️ 真机帧已丢，用真机课程帧 OCR 行 + F#36 真实弹窗文案 → `dialog/end-turn-yes`
     点 `TURN_END_YES`）；
  8. 持有上限保留饮料（`_checkbox_bands` 扫行 + 点勾选框列 (632,897)）。
- **回放抓到的真机 bug（F#44，已修）**：`ProduceDriver._checkbox_bands` 漏了 `@staticmethod`，
  真机带 image 进「持有上限/还可选择 N 个」分支会 `TypeError`（整局异常退出）。合成单测不传 image，
  所以此前没红；`data/drink3.png` 回放一跑就暴露。修一条装饰器 + 真机帧回归。
- **缺口（如实记录）**：回合结束确认框的真机截图**已经不存在**——`step_NNN.png` 会被后续跑局覆盖，
  含该弹窗的旧局（ep-cplus11 / ep-finish3/4/5 / ep-exp4）帧已被 ep-t3 跑局盖掉；扫 1352+26 张 0 命中
  「结束回合 / 尚可使用技能卡」。该分支暂用「真机课程帧 OCR 行 + FAILURES #36 记录的真实文案」回放，
  **下次真机跑局出现该弹窗时补拍 fixture**（挑帧命令见 `tests/fixtures/README.md`）。
- **DoD 对照**：六类屏全部有回放；5 类是真机帧，回合结束确认框用真机帧文字 + 同 UI 组件的真机
  确认弹窗兜底（等真机补拍后升级为纯真机帧）。
- **基线复核**：全量 pytest **950 passed / 1 skipped**（951 收集 / 68 个测试文件；A4 新增 9 条）；
  ① 洗牌 4/4 + 重洗 3/3、③ exam_setup 4/4 场 86/86 + 24/24、④ wiring 36/36 + 3/3 + known_draw 29/29
  + beam 28 不变（A4 只加素材/测试 + 一个漏装饰器修复，不动数据链路）。
- **教训**：1）**真机帧是消费品**：`step_NNN.png` 会被下一次跑局覆盖，关键屏要立刻归档，别等"下次一起"；
  2）**合成 OCR 行单测测不到需要真图像的分支**（颜色/勾选框/模板定位）——批量真机帧回放能直接抓出
  latent `TypeError`；3）屏幕分类以截图像素为准，日志里的 `screen/action` 只是当时的判断（F#43 已证明）。
- **提交**：`99bb6df`（feat：`_checkbox_bands` 修复 + 8 张真机帧 fixture + 9 条回放测试 + `scan_frames.py`）、
  `7eba62d`（docs：A4 完成交接——状态/基线数字/提交记录同步）；完整提交记录见 [七、最近提交记录](#七最近提交记录)。

### 二·补十八、11-22（WORKPLAN A5 落地：T3 离线预演 ✅）

**目标**：不碰真机，用**已结束采集**验证 T3 实时链路的核心机制——`build_exam_setup.py --current
--allow-finished` 拿不到「当前考试」的配置回合数，于是输出多个 `config_turns` 候选（默认 9/11/12），
`ExamPlanSelector` 用每回合实机手牌逐回合淘汰，唯一剩下即锁定；DoD：候选收敛到 1、`locked_turn<=3`。

- **脚本**：新增 [scripts/verify_exam_plan_offline.py](../scripts/verify_exam_plan_offline.py)——
  一条命令跑两条路径：① `--current` 路径：加载（`--refresh` 时现场重建，等价
  `build_exam_setup.py --current --allow-finished`）最近一场考试的候选，用该场 truth 逐回合驱动
  `ExamPlanSelector`；② 四场 sweep：对 `out/exam_setup.json` 每场各造 9/11/12 候选，同样用 truth 驱动。
  输出锁定回合 / 存活候选轨迹 / 选中 `config_turns` / 锁定后逐回合核对 / `known_draw` 覆盖下一手；
  退出码 = DoD 是否通过，`--json` 给明细。
- **实测**（最新场 = 11-21 17:38 期末，seed=0x1E1A740D、27 张牌、支援 6）：
  `--current` 3 候选（9/11/12）→ **第 2 回合锁定 `config_turns=12`（真值 12）**；锁定后手牌核对
  11/11（T2–T12）、`known_draw` 覆盖下一手 9/9；T12 打出考试内生成卡 → 按数据限制停下（不算失败）。
  四场 sweep：考试0/1/2 第 1 回合锁定、考试3（= 最新场）第 2 回合锁定；选中 `config_turns` =
  9/11/9/12，**全部等于真值**；候选 3→1；`locked_turn` 最大 2。第 1 回合分不出的场是 isInitial 卡
  相同，第 2 回合收敛，和 QQ 群「2–3 回合锁定 seed」口径一致。
- **测试**：`tests/test_exam_plan_offline.py` 8 条（候选复制 / truth 驱动统计 / 真实与错误候选 /
  生成卡提前停止 / `evaluate_row` DoD 判定 / CLI 全链路）。
- **DoD 对照**：候选收敛到 1 ✅、`locked_turn<=3` ✅；结论写回
  [EXPECTIMAX 完全信息搜索 §④](EXPECTIMAX.md) 与本节。真机 T3 验收（考试进行中跑 `--current` +
  bot 运行时重载 + `[exam-plan] summary`）留到阶段 E。
- **基线复核**：全量 pytest **958 passed / 1 skipped**（959 收集 / 69 个测试文件；A5 新增 8 条；
  `ruff check` 对新增文件通过）；① 洗牌 4/4 + 重洗 3/3、③ exam_setup 4/4 场 86/86 + 24/24、
  ④ wiring 36/36 + 3/3 + known_draw 29/29 + beam 28 全部不变（A5 只加脚本/测试/文档）。
- **提交**：`7c16abe`（feat：离线预演脚本 + 8 条单测）、`3bb6a6e`（docs：A5 完成交接——
  状态/基线数字/提交记录同步）；完整提交记录见 [七、最近提交记录](#七最近提交记录)。

---

### 二·补十九、11-22（WORKPLAN B1 落地：T4 评测 bug 修正 + 受控 frontier 叶子 ✅）

**目标（B1）**：只对 beam 最深端点做 rollout（执行同策略 within + 缓存 + 小预算），决策门：
真实牌组 beam ≥ within 的 90% 再谈生产。

**先查到真正的瓶颈：评测执行器白丢回合（不是 V_leaf）**
- `LessonSim.step` 在「手牌打空」时会自动结束本回合；旧 `scripts/eval_known_draw.py::_execute_plan`
  在按 beam 计划打光 3 张后又补了一刀 `sim.step(None)`——此时已进入下一回合，**白丢下一整个回合**。
  每个 beam 决策都少打一回合，旧 beam 数字（91.3→111.2）被系统性低估；within 逐张决策不走该
  执行器，所以它的 143.1 一直是真实的。旧结论「V_leaf μ 是主因」实为测量 bug。
- 修法：执行前记 `start_turns_left`，只有仍在同一回合时才补 SKIP；短计划才正常结束回合。
  回归测试 `tests/test_beam_frontier.py::test_execute_plan_*` 2 条。

**受控 policy-evaluation 叶子（B1 交付）**
- `src/gkagent/sim/expectimax.py`：`search_beam(frontier_value=...)` 只对预算截断后的**最深端点**
  （`end_state.turns_left > 0`）用 `frontier_value.utility` 重排根动作；终局端点直接用精确档位
  效用、不 rollout；`frontier_value=None`（默认）行为逐位不变。
- `scripts/eval_known_draw.py` 新增 `--frontier-rollout` / `--frontier-budget-ms` / `--beam-depth`；
  新增 `scripts/eval_t4_b1.py`（B1 配对评测脚本，退出码 = 决策门）。

**60 局配对（small，同牌组同 seed；`--games 60`）**

| 策略 | 信息 | 均值 | P50 | CLEAR | PERFECT | vs within | 95% CI |
|---|---|---:|---:|---:|---:|---:|---|
| within | unknown/known | 143.1 | 145 | 83.3% | 13.3% | — | — |
| beam | unknown | **164.0** | 162 | 98.3% | 33.3% | **+20.9** | [+14.4,+27.3] |
| beam | known | **165.5** | 165 | 100.0% | 38.3% | **+22.4** | [+16.5,+28.4] |
| beam+frontier | unknown/known | 164.0 / 165.5 | 162/165 | 同 beam | 同 beam | 同 beam | — |

- **决策门 PASS**：114.6%（unknown）/ 115.7%（known），门槛 90%；逐局不劣于 within 为 52/60、51/60。
- **受控叶子中性**：frontier 与普通 beam 逐位相同。原因是 small 真实牌组上 4 个根计划收敛到
  同一前沿状态（同 `canonical`），rollout 值相同；`turns_left=1` 的截断本来也接近精确。
- **消融**（60 局）：beam 默认 148.6/153.8；`score_tiebreak=1e-3` 164.0/165.5（+15.4/+11.8）；
  `branching=10` 151.2/153.8（+2.7/+0.1，无显著收益）；两者同开 161.6/164.8。
  旧「branching=10 贡献 +19.9」是 bug 副产物。
- **生产默认不改**（expectimax / tiebreak=0）；T2 真机 A/B 时把 `beam + tiebreak` 作为候选。
  旧 rollout 叶子的 beam 侧负结果同样作废（within 侧 ≈ 中性仍有效），B2 需用修正 harness 重测
（**B2 已完成**：学习叶子在 beam 上显著 +7.7，见二·补二十）。

**测试 / 基线**
- 新增 `tests/test_beam_frontier.py` 6 条（前沿重排、终局不 rollout、默认行为不变、只问最深层、
  执行器不再丢回合 2 条）；`ruff check` 对改动文件通过。
- 全量 pytest **964 passed / 1 skipped**（965 收集 / 70 个测试文件）；
  ① 洗牌 4/4 + 重洗 3/3、③ exam_setup 4/4 场 86/86 + 24/24、④ wiring 36/36 + 3/3 + known_draw 29/29
  + beam 28 全部不变（B1 只动 beam 评测/搜索可选参数 + 测试/文档）。
- **提交**：见 [七、最近提交记录](#七最近提交记录)（feat + docs 两个提交）。

---

### 二·补二十、11-22（WORKPLAN B2 落地：全知数据训练 MLP 叶子 ✅）

**目标（B2）**：用全知（exact/known_draw）数据训练叶子/小模型，teacher = 全知搜索，
student = V_leaf，用 B1 **修正后的 harness** 做配对评测；DoD：显著优于解析式 leaf（或可复现负结果）。

**数据（这次和三次历史失败的关键区别）**
- `scripts/build_b2_dataset.py` + `src/gkagent/sim/leaf_data.py::RecordingLessonSim`：
  beam **全知**自对弈（teacher 看得到牌序），在每次 `_draw_hand` 入口记录**叶子状态**——
  与 `expectimax._Search.leaf` 的输入 `end_turn_state(state)` 同形态（手牌已进弃牌堆、好印象已结算
  并 -1、好调/持续 buff 已倒计时、回合 -1）。旧 `fit_v_leaf` 在**回合开始手牌还在手上**采样，
  `hand_*` 训练/推理不同分布，是失败原因之一。
- 标签 = 该局最终分 − 叶子状态分数（**on-policy 实际后续得分**，不是贪心轨迹）；自然打满回合补
  `turns_left=0` 终局样本（y=0）。
- 三批 teacher：width4/100ms 1500 + 3000 局、width8/300ms 800 局 → **26,500 叶子样本**
  （`out/b2_leaf_beam_*.npz`，gitignore、可重建）。

**模型**
- `src/gkagent/sim/leaf_mlp.py`：104 维结构化特征（状态/分数缺口/体力、buff 计时、指針、
  饮料/P 道具、**牌库 vs 弃牌堆拆分**、牌库效果聚合、交互项）+ MLP 104→96→48；
  μ 用 MSE、σ 用残差头高斯 NLL；实现 `LeafValue` 协议（`predict`/`utility`），搜索代码零改动。
- `scripts/train_b2_leaf.py`：按 seed 分组 9:1 切分；held-out **r²=0.943 / MAE=8.8 / corr=0.971**
  （旧 35 维线性 r²≈0.91、MAE≈9.5；ridge 0.933）。
- 模型入库：`data/knowledge/b2_leaf_mlp_small.json`（335KB，可 `train_b2_leaf.py` 重建）。

**评测（`scripts/eval_b2.py`，复用 B1 修正 harness；同牌组同 seed 配对 + 95% CI）**
- 选择段 seed 2000–2079（80 局，unknown）：beam 解析式 **166.8** → learned **173.7
  （+6.8，CI [+3.2,+10.4]）** / ensemble 0.25 **174.4（+7.5，CI [+3.7,+11.4]）**。
- **确认段 seed 3000–3119（120 局，未参与选择）**：
  - unknown：beam 解析式 157.8 → learned **165.5（+7.7，CI [+4.2,+11.2]）** /
    ensemble 0.5 **166.9（+9.0，CI [+5.8,+12.2]）**；
  - known：159.9 → learned **167.1（+7.2，CI [+3.7,+10.7]）** / ensemble 0.25 **167.7（+7.8）**；
  - CLEAR 95.0%→98.3%、PERFECT 33.3%→50.0%。
- B1 基线逐位复现（seed 0–59：within 143.1 / beam 164.0/165.5；`out/b2_sanity_b1.json`）。
- **DoD 达成**（beam 上显著优于解析式叶子）。

**负结果（如实记录，详见 EXPECTIMAX）**
- **within 用 learned 叶子显著变差 −3.3**（CI [−5.6,−1.1]）：V 的标签来自更强 beam 策略，
  对 within 执行偏乐观；within 只拿叶子做动作排序，策略改进收益拿不到 → **只对 engine=beam 有益**。
- within 自对弈叶子（正确策略标签）≈ 中性（+0.9 n.s.）——解析式叶子不是 within 瓶颈。
- 档位概率头（logistic P(CLEAR)/P(PERFECT)）在 beam 上灾难性变差（−42~−46）：teacher 叶子
  98.7% CLEAR → P(CLEAR) 饱和，排序失去平滑 μ 信号。
- 第二轮专家迭代（teacher=beam+learned）未超过第一轮（+5.7 vs +6.8，选择段）。

**生产接线（未默认打开）**
- `LessonPolicy.DEFAULT_PARAMS` 新增可选 `leaf_model`（默认 `None` = 行为不变）+
  `leaf_model_weight`（默认 0.5）；`_leaf_value()` 显式配置时构 ensemble 并**缓存**（旧实现每决策
  重读 JSON），坏路径 warning 退回解析式。
- **不要给 expectimax（within）打开**；T2 真机 A/B 候选 = `engine=beam` +
  `leaf_model=data/knowledge/b2_leaf_mlp_small.json`（建议 weight 0.25）。真机收益取决于 B3
  机制对齐（`LessonSim plays_per_turn=3` vs 真机 1、P 道具/饮料/减益等），离线数字不是真机保证。

**测试 / 基线 / 提交**
- `tests/test_b2_leaf.py` 11 条（特征契约/叶子快照与标签/模型存取/搜索接线/生产 loader 缓存与兜底/
  合成训练收敛）；`ruff check` 通过。
- 全量 pytest **975 passed / 1 skipped**（976 收集 / 71 文件）；
  ① 洗牌 4/4 + 重洗 3/3、③ exam_setup 4/4 场 86/86 + 24/24、④ wiring 36/36 + 3/3 + known_draw 29/29
  + beam 28 全部不变（B2 只增模块/脚本 + `eval_known_draw.play` 两个可选参数 + 生产可选参数/缓存）。
- **提交**：feat `ccabd0a` + docs `5cd23d0`（见 [七、最近提交记录](#七最近提交记录)）。

### 二·补二十一、11-22（WORKPLAN B3 落地：T5 机制建模——回合规则对齐真机 1 张 + 规则核验表 ✅）

**目标（B3）**：把模拟器 `plays_per_turn` 对齐真机（每回合基础 1 张 + 额外出牌），
逐条核验 `RULES_REFERENCE` 的公式/机制，给出差异表 + 补丁 + 配对回归。

**核心结论**：真机**每回合基础只能出 1 张牌**（一手 3 张是"选 1 张"），打完最后一张
**立即自动结束回合**；回合结束如果还有出牌次数没用（SKIP）**回 2 体力**。
证据：gakumas-tools（BSD-3）`TurnManager.startTurn` 的 `cardUsesRemaining = 1`、
`CardManager.useCard` 末尾 `cardUsesRemaining < 1 → endTurn`、`TurnManager.endTurn`
的 `stamina+2`；真机 4 场考试 39 回合逐回合日志（32 回合 1 张、7 回合 2 张，
每回合手牌都 3 张；7 个 2 张回合里 3 个首张牌带 `ExamPlayableValueAdd`）。

**补丁（4 项，全部有回归）**
1. 默认 `plays_per_turn` / `ExpectState.play_limit` / `UIObs.DEFAULT_PLAY_LIMIT` **3 → 1**
   （`sim.lesson` / `sim.expectimax` / `sim.play_choice` / `sim.uiobs` / `sim.v_leaf` /
   `scripts/local_bench.py`）；
2. `LessonSim.step`：出牌次数用尽或手牌空 → **自动结束回合**（真机语义）；
3. `LessonSim._end_turn` / `expectimax.end_turn_state`：**回合末还有剩余次数 → 体力 +2 封顶**
   （参考引擎 endTurn 顺序：先回体力再 endOfTurn）；
4. **取整对齐** `safeCeil`：buff/指針/不调乘完 ceil 一次，回合属性倍率乘完再 ceil 一次
   （旧：课程 floor / 考试结尾 round 一次）。实机回放黄金值核对：考试 250% 回合
   アピールの基本 9→**23**、好调后→**35**、愛嬌 13+好调→**50**、情熱ターン 11 集中 0/3/6→
   **28/35/43**；课程好调 10→15、5→**8**、2→3，温存 9→5、2→1、15→8。

**配对回归素材（真机）**
- `scripts/export_t5_turn_rules.py` → `tests/fixtures/t5_exam_turn_rules.json`：
  4 场考试 39 回合的「出牌数/手牌数/首张牌/是否带额外出牌效果」摘要（含溯源）。
- `tests/test_t5_turn_rules.py` 9 条：默认 1 张、自动结束、SKIP 回体力（封顶）、
  `end_turn_state` 同口径、额外次数保持回合、beam 每回合只排 1 张、真机 39 回合规则回归。
- `tests/test_sim_lesson.py` 实机回放黄金值 2 条（课程 6 个值 + 考试 6 个值）。

**规则核验表**：`docs/RULES_REFERENCE.md` 重写为逐条核验表（参考引擎/官方 wiki/真机三方对照），
覆盖回合规则、`resolveScore` 结算顺序与取整、buff 生命周期与好印象年金 `W(r,T)`、
牌序（洗牌/支援强化/重洗/回合属性，✅ 4/4+3/3）、审查倍率（❌ 仍是常量 4.11）、
熱意/温存解除额外次数/P 道具/fresh buff 等剩余差距（都写了证据与下一步）。

**重标定（规则改了，旧数字全部不可混比）**
- `sim_engine_ab` 76 局：0 blocked / 0 异常 / C+ 100%；**expectimax 从噪声内变显著更强**：
  rules vs expectimax 评价点 P50 5170→5566（16 局）、5176→5505（30 局）、5152→5513（30 局），
  配对 Δmean **+372/+342/+429**（B3 前 −15/−5）。
- B1 60 局：within **89.1** → beam **95.7**（+6.6，CI [+2.2,+11.1] unknown / +6.6 [+3.1,+10.1] known，
  决策门 107.4% PASS）。结论不变，绝对值缩小是口径。
- B2 学习叶子（旧口径数据训练的模型）：**重测 FAIL**——确认段 beam 解析式 94.9 → learned
  67.1（−27.9，CI [−32.6,−23.1]）、ensemble 0.75 89.6（−5.3）；**必须按 B3 规则重采数据重训**
  （建议等 T5 剩余机制补齐后一次重训，避免再废一次）。生产接线保持默认关闭。
- `tests/test_sim_produce.py` 400 局培育标定带 650–1100 → **950–1450**（≈1198，口径变化）。

**测试 / 基线**
- 全量 pytest **985 passed / 1 skipped**（986 收集 / 72 文件；B3 新增 `tests/test_t5_turn_rules.py` 9 条
  + 实机黄金值净 +1 条）。
- ① 洗牌 4/4 + 重洗 3/3、③ exam_setup 4/4 场 86/86 + 重洗 24/24、④ wiring 36/36 + 3/3 +
  known_draw 29/29 + beam 28 **全部不变**（B3 只改模拟器回合规则/取整 + 文档/素材）。
- 文档：`RULES_REFERENCE.md` 重写；`SIMULATOR.md` §10 重标定 + §11 B3；`EXPECTIMAX.md`
  文末「B3 规则修正与重标定」；`WORKPLAN.md` / `HANDOVER_NEXT.md` / `INDEX.md` 状态同步。

**提交**：feat `4316f9a` + docs（见 [七、最近提交记录](#七最近提交记录)）。

**下一步**：T5 剩余机制（审查倍率分段+联动惩罚、熱意、温存解除额外次数、fresh buff 差一回合、
P 道具数据接入）→ 阶段 C（执行层可靠性）/ D（补采集）→ 真机 T3→T1→T2 → gkbench。

---

### 二·补二十二、11-22（F 阶段数据 + F0 预检：gkbench 官方种子/对局批量下载，洗牌模型 286/384 命中）

**背景**：用户登录 gkbench（`hiro.matto.top/gkbench`）并生成了命令行令牌 → 可以批量下载
**公开数据**（题模板/runs/路线/榜单）和**令牌数据**（开发集种子 `seed`+官方 `check`、保密种子逐局记录）。
规则红线不变：**ranked 禁 seed**，下载数据只做本地分析/理论上限分母（官方也把看种子的搜索
只当 denominator）。

**新增工具**：`scripts/bench_download.py`（stdlib、只读 API、断点续传、manifest 按磁盘重建）：
- 公开：`/api/sets`、`/api/runs?set=`、`/api/runs/<run>`（逐局索引**含 route**）、
  `/api/runs/<run>/episodes/<id>/<i>`（固定种子公开；保密种子要令牌）、
  `/api/sets/<set>/saves?answers=1`、`/api/leaderboard?set=&kind=fixed|template`；
- 令牌（`GKBENCH_TOKEN` 或 `~/.config/gkbench/token`，**仓库外**）：`/api/sets/<set>/seeds`
  （seed+`check{turn,score,stamina,hand,rules,commit}`）、保密种子逐局 `steps`。

**已下载**（`data/bench_local/gkbench_dl/`，gitignore，`hif` 题集，210 文件 / 58.8 MB）：
- **80 个目标 run 索引 / 36,350 条对局路线**（uinet 37、uihorizon 13、official-ai 2、
  best-known 28；含 UINet/UIHorizon 变体 13 个另计）；
- **`seeds.json`：329 题 / 384 组开发种子 + 官方 `check`**（F0 基准）；
- 逐局 steps：公开固定种子 **79 局** + 保密种子抽样 27 局（该接口服务端≈20 s/局，全量不现实）；
- 505 题模板存档；fixed/template 两种榜单（含 vs_oracle）。
- 参考分（template 主榜，与 README/COMPARE 一致）：best-known **1,452,088**（分母）/
  UIHorizon v2.1 **631,129（0.5113）** / UINet v2.1 **578,722（0.4551）** /
  official-ai **232,710（0.2131）**。

**F0 预检（用官方 `check.hand` 核对我们的洗牌模型，详见 [GKBENCH.md](GKBENCH.md) §4.5）**：
- **npc 数按 stage 不同**：H.I.F 選抜（sel1/2/3）6 人制 → npc=5；**本戦（main1/main2）3 人制 → npc=2**
  （K=24/33）；牌序必须用 `loadout.deck_cards` 原顺序（按主数据 order 重排 1/384，错）。
- 结果：sel1 **60/60**、sel2 47/55、sel3 44/57、main1 64/97、main2 71/115 → **286/384 = 74.5%**
  精确命中（不区分 stage、一律 npc=5 只有 152/384）。
- 不一致根因：① 牌组带 `p_card_custom-…-initial_add`（训练开始时加入手牌）的卡官方会强制进
  开局手牌，我们没算 initial；② 主数据 `isInitial` 只标基础变体、牌组用 +1。修完预计接近 100%。
- 文档：新建 [GKBENCH.md](GKBENCH.md)（API/令牌边界/下载清单/参考分/F0 预检）；
  WORKPLAN 阶段 F 加 F0/F1；COMPARE 来源同步；INDEX 文档清单。

**令牌**：只存在 `%USERPROFILE%\.config\gkbench\token`（仓库外，可随时在网页吊销）；
已确认仓库内无任何令牌字符串。

**提交**：`57e2a8d`（WORKPLAN F0）、`b6d7868`（下载工具 + GKBENCH.md）、`cc1d0cf`（令牌补齐 + F0 预检）。

**下一步**：**F0 收尾**（修 initial 集合 → 重跑逐题命中率/根因 → 校准起点 `stamina/turn/rules`）；
之后回到 T5 剩余机制 → C/D → 真机 T3→T1→T2 → F1/F2 gkbench 公开对比。

---

### 二·补二十三、11-22（开工基线复核：四条全绿，与文档期望逐项一致）

**背景**：2026-11-22 17:2x 新会话按 [HANDOVER_NEXT.md](HANDOVER_NEXT.md) §2 做开工自检——
**只跑基线、不改代码/数据**。环境：Python 3.11.17；`C:\GakumasLocal\GakumasUnlock\out\` 的
`traffic.jsonl` / `deck_snapshots.json` / `exam_truth.json` 均在；日文 OCR 模型
`download_ocr_models.py --check` 全部就绪（det/rec/18708 字典/config）。

**实测**（四条命令，退出码均 0）：
1. `scripts/verify_shuffle.py`：**4/4 场整段复现 + 3/3 重洗**——期中 18/18、期末 26/26、
   PRO 期中 15/15、PRO 期末 27/27 张；重洗 9/9、6/6、9/9（考试1 重洗段因考试内生成卡按规则跳过）。
2. `pytest tests/`：**985 passed / 1 skipped**（196.5 s；`--collect-only` 复核 **986 条 / 72 个测试文件**）。
   唯一 skip = `tests/test_produce_ui.py:1181`「step_047 当前不是行动页（data/auto 正被真机运行持续覆写）」
   ——属文档预期，不是回归。
3. `scripts/build_exam_setup.py`：**4/4 场、初始段 86/86、重洗段 24/24**（1 场按规则跳过 7 张生成卡）。
4. `scripts/verify_exam_wiring.py`：**手牌 36/36 回合、重洗样本 3 组、known_draw 29/29、策略链路
   beam 28 回合/28 次出牌**（4/4 场通过；⚠️ 计划在重洗前 grave 对不上时自动停用=设计）。

**结论**：四个数字与 [WORKPLAN.md](WORKPLAN.md) / [HANDOVER_NEXT.md](HANDOVER_NEXT.md) §2 /
[INDEX.md](INDEX.md) 的期望值**完全一致**；B3 与 F0 预检没有破坏任何已验收基线，本会话无需修基线、
无需改代码。工作区未新增 tracked 改动（`out/exam_setup.json`、`data/pytest-tmp-*` 均被 `.gitignore` 覆盖）。

**提交**：`90d5b87` docs(handover)（仅文档；本会话无代码改动）。

**下一步**：按 WORKPLAN 做 **F0 收尾**（修 initial 集合 → 逐题命中率/根因 → 校准起点
`stamina/turn/rules`；数据已就绪），开新会话做。

---

### 二·补二十四、11-22（F0 收尾：官方种子核洗牌模型 286 → 366/384 + 考试起点校准）

**背景**：F0 预检（二·补二十二）用官方 `check.hand` 只到 286/384=74.5%，根因初步归为
initial_add / isInitial 变体。本会话按 [HANDOVER_NEXT §4 F0](HANDOVER_NEXT.md) 做收尾：
修 initial 集合 → 逐题逐张命中率/根因 → 用 `check` 校准考试起点。

**新增**：`scripts/verify_gkbench_shuffle.py`——只读本地 `data/bench_local/gkbench_dl/hif/` +
主数据（catalog.sqlite），不联网、不读令牌；`--json/--verbose/--stage-npc/--variant-initial`。

**口径修正（两条）**：
1. **initial 按 base 卡 id**：主数据 `isInitial` 在 +0/+1/+2/+3 各变体上都有记录，旧口径按
   `(id, upgradeCount)` 精确匹配，deck 写 `...+1` 的卡漏判；现按 base id 命中所有变体，再把
   deck 里 `g_effect-initial_add` 自定义的卡并进 initial（考试开始强制入手）。
2. **npc 人数按 idol 卡，不是 stage 常数**：`IdolCard.produceStepAuditionDifficultyId` →
   `ProduceStepAuditionDifficulty(produceId, stepType)` → `produceExamBattleNpcGroupId` → NPC 行数。
   **選抜一律 6 人制（npc=5）**；**本戦按培育角色**——多数 3 人制（npc=2，135 张 idol 卡）、
   **十王星南 jsna 4 人制（npc=3，13 张）**、**藤田ことね fktn 2 人制（npc=1，12 张）**；
   部分采集 loadout 没有 `step_type/step_id`，用 `round`（mid1/mid2/final）兜底。旧口径 main
   写死 npc=2 → 26 组对不上。

**结果（384 组 = 329 题 × 1–2 个开发种子；逐张=按位置）**：
- 旧口径 **286/384（74.5%，逐张 913/1155=79.0%）** → 只修 initial **338/384（88.0%，1060/1155=91.8%）**
  → 再修 npc+round 兜底 **366/384（95.3%，逐张 1125/1155=97.4%）**；
- 按 stage：sel1 **60/60**、sel2 **55/55**、sel3 56/57、main1 96/97、main2 99/115；
  逐题 **311/329 题的全部种子命中**；
- 剩余 18 组根因：**initial 0 / turnStartDistribute 0 / 牌序 0 / 其他 18**——
  15 组「考试初始牌组 `ExamInitialDeck` 未建模」（produce-008 沿用
  `initial_deck-produce_007-concentration/lesson_buff/review`，12/2/1 组）、
  3 组「考试开始额外 +1 手牌」（都是 `kllj-3-005`，第 4 张=牌堆下一张）。
  **没有一组是洗牌模型本身错**——K 与 Fisher-Yates 在 366 组上全对。

**考试起点校准**（`check.turn/score/stamina/rules/commit`）：
- `turn=1`×384、`score=0`×384 → 考试从第 1 回合开始、起点分 0（与 `LessonSim` 一致）；
- `rules=55`×384、`commit=f4d9e6e6148d`×339（45 组空=随机 40 + 实机 5）；官方榜上 run 现在跨
  **rules 55/59/65** 三档 → F1 裁判对齐要标版本，别默认最新；
- `stamina` **369/384=96.1% 等于 `loadout.starting_stamina`**，15 组差异是**偶像卡自带 P 道具的
  考试开始附魔常量**（shro-3-016 −28×5、atbm-3-015 +5×4、kllj-3-005 −1×3、ssmk-3-002 +6、
  kcna-3-019 +6、shro-3-007 +1）→ **基准复算用 `check.stamina` 覆盖 `loadout.starting_stamina`**。

**文档**：GKBENCH §4.5 重写（方法/消融表/逐 stage/根因/起点校准）；COMPARE §1/§2.3/§5/§6/§7 同步；
RULES_REFERENCE §0 前加「官方规则版本口径」；HANDOVER_NEXT §0/§1/§2/§4 F0/§8 状态；INDEX/WORKPLAN/README 同步。

**基线复核**（改完再跑，四条全绿、退出码 0）：① 4/4+3/3；② **985 passed / 1 skipped**（986 收集）；
③ 4/4、初始 86/86、重洗 24/24；④ 36/36、重洗 3/3、known_draw 29/29、beam 28。
无 src/tests 改动（只加脚本 + 文档）→ pytest 数字不变。

**提交**：`83f1f96` feat(f)（脚本 + 文档；无 src/tests 改动 → pytest 数字不变）；哈希记录提交随后补。

**下一步**：**F0 收尾完成** → T5 剩余机制（审查倍率分段+联动惩罚、熱意、温存解除额外次数、
fresh buff 差一回合、P 道具数据接入）→ 阶段 C/D → 真机 T3→T1→T2 → F1/F2 gkbench 公开对比。

### 二·补二十五、11-22（B4 / T5① 审查倍率分段 + 联动惩罚：常量 4.11 → 客户端真实公式 + 屏幕倍率接线）

**背景**：T5 剩余机制里影响最大的一项——考试每回合顶部「歌唱 411%」类的属性倍率
（审查倍率）我们一直用常量 `4.11`（C+/5577 反推的平均值）。本会话把它换成**客户端真实公式**：
分数表分段折线 × 审查基准**联动惩罚** × 单精度取整，并让真机搜索直接用屏幕读到的真实倍率。

**机制（原生客户端行为）**：
1. **分段折线**：每个属性在自己的培育属性值上，按主数据
   `ProduceExamBattleScoreConfig` 的节点表（本次两张表都是 5 节点：0/128/192/320/3000，
   表中 `vocalPermil/dancePermil/visualPermil` 三列）折线插值 → `component_permil`；
2. **联动惩罚**：每项低于本场 `ProduceExamBattleConfig` 的审查基准（如期中 Vo/Da/Vi =
   320/128/192）时按 `GetPenaltyPermil` 线性罚分（全局 `Setting`
   `produceExamBattleScorePenaltyMinPermil/MaxPermil` = 100/250‰）；
   **`common = 1000 − Σpenalties`，三项共用**——一项不达标会把三项倍率一起压低；
3. **归一化**：`bonus = 1000 + (component × common / 1000)` 向上取整到 10 的倍数；
4. **取整**：出牌分/回合末好印象 `ceil(f32(f32(bonus/1000) × amount) − f32(1e-4))`
   （客户端 `CalcCurrentTurnBattleBonus`；单精度，不是 double）。
证据/口径来源：gakumas-tools（BSD-3）`typeMultipliers.js` 的同结构公式；hiro-gakumas-hero
（AGPL，`data/hiro/` 只参考）vendor 里 `gakumas_produce/attributes.py` 的客户端反编译还原实现
（`calculate` / `normalize_bonus` / `battle_bonus_score`）；主数据四张表（gakumasu-diff 快照）。
**按语义重写，没有拷贝 AGPL 代码**。

**落地**：
- `src/gkagent/sim/exam_multiplier.py`：纯公式（`calculate_bonus` / `normalize_bonus` /
  `battle_bonus_score` / `f32` / 分段插值 / 罚分）；
- `src/gkagent/data/exam_bonus.py`：主数据解析（`IdolCard.produceStepAuditionDifficultyId` →
  `ProduceStepAuditionDifficulty`（produceId+stepType）→ `ProduceExamBattleConfig` →
  `ProduceExamBattleScoreConfig` + `Setting`）；缺数据**显式抛错**（新偶像卡不在快照里等），
  不静默退回 4.11；
- 模拟器：`LessonConfig.attribute_bonuses`（Vo/Da/Vi 千分比）+ `turn_attributes`
  （`ExamTurnEndLog.parameterType` 1/2/3）→ 按当前回合属性乘；出牌分**含好印象/元气/全力值
  依赖分**一起乘（参考引擎里依赖分也是普通 `score +=`）、回合末好印象合成结算也乘；不配这两项
  时行为与旧版逐位相同（单标量 `attribute_coefficient` 路径保留）；
- 生产：`policy.audition_coefficient`——真机考试帧顶部读到的「舞蹈 207%」= 2.07 →
  `ExpectState.attribute_coefficient`；决策日志 `decision_note` 加 `attr=2.07`（真机能看出
  搜索用的倍率）；读不到时不传（保持旧行为，不猜）；
- 夹具：`scripts/export_exam_multipliers.py`（traffic + 主数据 → 夹具，支持 `--check`）→
  `tests/fixtures/t5_exam_multipliers.json`：
  - **11-20 采集局（`i_card-hmsz-3-018` / produce-002）期中**：三维 373/218/187 →
    Vo/Da/Vi = **4.09 / 2.20 / 2.60×**（Vi 187 < 基准 192 → 罚 103‰，common 897 把三项一起压低）；
  - **同局期末**：842/350/629 → **6.97 / 2.85 / 4.96×**（Vo 842<961、Da 350<384 两项不达标）；
  - 11-21 的 `i_card-hkne-3-000` 不在主数据快照 → 夹具显式 `skipped`（生产只用屏幕倍率）。

**测试**：`tests/test_exam_multiplier.py` 21 条——分段/边界/超上限、联动惩罚把三项一起压低、
归一化到 10、客户端取整黄金值（250% 9→23 等）、模拟器按回合属性乘（3 回合 Vo/Vi/Da）、
回合末好印象吃倍率、默认路径逐位不变、生产屏幕倍率→搜索系数（含真机帧 OCR「舞蹈 207%」→2.07）、
主数据解析器（缺偶像卡显式报错）。

**基线复核（改完再跑，退出码均 0）**：① 4/4 + 3/3；② **1006 passed / 1 skipped**
（1007 收集 / 73 文件；唯一 skip 仍 `tests/test_produce_ui.py:1181`）；③ 4/4 场 86/86 + 24/24；
④ 36/36 + 3/3 + known_draw 29/29 + beam 28；⑤ gkbench 366/384=95.3% / 97.4% 逐张。

**如实记录的剩余差距**：本轮只保证**倍率本身**与客户端公式/主数据一致；真机**逐分回放**还差
P 道具考试开始附魔（如 hmsz-3-018 的 `enchant-...-336-0` 好印象触发）、`ExamStatusEnchant`
附魔触发、考试内生成卡、`ExamReviewMultiple`「次数」语义（我们按千分比）——这些补完后才能把
4 场 39 回合逐分锁死（T5 剩余机制/后续会话）。

**文档**：RULES_REFERENCE §0/§2/§5.1/§6/§7（含许可口径）；WORKPLAN B4；HANDOVER_NEXT §0/§1/§2/§4/§8；
INDEX/COMPARE/EXPECTIMAX B4/PROVENANCE/fixtures README 同步。

**提交**：feat `6b4beae`（代码 + 测试 + 夹具 + 文档）；哈希记录 `bb8171a`。

**下一步**：T5 剩余机制（熱意、温存解除额外次数、fresh buff 差一回合、P 道具数据接入）→
阶段 C/D 离线收尾 → 真机 T3→T1→T2 → F1/F2 gkbench 公开对比。

### 二·补二十六、11-22（B5 / T5② 熱意 + 温存解除：独立熱意资源 + 出牌次数/固定元気）

**背景**：T5 剩余机制里第二、三项——「熱意（enthusiasm）」以前只是把温存解除近似成
「好调回合 = 温存期间打出数 + 1」，既没有独立资源、也不给额外出牌次数/元气；本次按
参考引擎（gakumas-tools，BSD-3）与官方 wiki 完整实现。

**机制（参考引擎行为）**：
1. **熱意 = 本牌分数加算**：`resolveScore` 在集中加算之后、好调/指針倍率之前
   `score += 熱意 × 熱意適用倍数`；熱意是 `WHOLE_FIELDS`，获得时
   `Math.ceil(Number(value.toFixed(2)))`（=向上取整），回合末清零（有延長则保留）；
2. **温存解除**（`constants.js STANCE_CHANGED_EFFECTS`）：1 段階解除 → 熱意 +5、出牌次数 +1；
   2 段階解除 → 熱意 +8、**固定元気 +5**（不吃やる気）、出牌次数 +1；同回合重复解除按次数叠加；
   温存→温存2 的段階升级不触发；温存→全力的**回合边界**切换也触发（`startTurn` 的
   `FULL_POWER_EFFECTS → setStance(fullPower)`）；
3. **获得公式**：`(熱意追加 + 基础) × (1 + 熱意増加‰)`；次日来源 = 卡牌效果
   `ExamEnthusiasticAdditive`（熱意追加 buff）、`ExamEnthusiasticMultiple`（熱意増加‰ buff）、
   `ExamEnthusiasticTurnAdd`（熱意延長回合）、`ExamMultipleEnthusiasticLesson`
   （**本牌**熱意適用倍数 ×2，卡面「熱意效果会2倍生效」）；
4. 回合末：好印象结算（走同一个 `resolveScore`，会加熱意）→ buff 倒计时 → 熱意清零/延長。

**落地**：
- `src/gkagent/sim/enthusiasm.py`：纯规则 `release_on_stance_change` / `enthusiasm_gain`（ceil）/
  `turn_end_enthusiasm`；
- `LessonSim`：`enthusiasm` / `enthusiasm_extension_turns` + `Buffs` 熱意 buff；
  `_card_award` 加熱意（含本牌 `enthusiasm_multiplier`）；`_apply_card_buffs` 登记熱意追加/増加/延長；
  `_end_turn` 好印象加熱意 → 回合末清零/延長 → 温存→全力边界解除；旧 `_save_cards_used` 近似删除；
- `ExpectState`：同字段/canonical/`_card_award`/`_apply_card_effects`/`end_turn_state`/
  `state_from_sim`/`sim_from_state` 全镜像（搜索里能看到「温存解除 +1 出牌 +5 熱意」的价值）；
- `CardSpec` 新增 `enthusiasm_bonus` / `enthusiasm_bonus_turns` / `enthusiasm_multiple` /
  `enthusiasm_multiple_turns` / `enthusiasm_extension` / `enthusiasm_multiplier`；
  `scripts/sim_produce.py`（CardRow + `_effect_fields`，MODELED_EFFECTS 29→32）与
  `src/gkagent/sim/play_choice.py`（生产卡表 → CardSpec）映射上述效果。

**测试**：`tests/test_t5_enthusiasm.py` 16 条——纯规则（温存 1/2 段解除常量、温存段階升级不触发、
获得公式 ceil、回合末清零/延長）、LessonSim（+1 出牌次数、固定元気不吃やる気、同回合重复解除叠加、
熱意参与算分、纯 buff 牌不加、回合末好印象加熱意、熱意追加/増加 buff、延長跨回合、回合边界解除、
本牌熱意適用倍数 ×2）、ExpectState 镜像（同序出牌分数一致、回合末重置/延長）；另外
`test_sim_produce.py` / `test_play_choice.py` / `test_mechanism_corrections.py` 同步更新
（旧「解除温存给好调回合」断言删除）。

**基线复核（改完再跑，退出码均 0）**：① 洗牌 4/4 + 重洗 3/3；② **1023 passed / 1 skipped**
（1024 收集 / 74 文件；唯一 skip 仍 `tests/test_produce_ui.py:1181`）；③ 4/4 场 86/86 + 24/24；
④ 36/36 + 3/3 + known_draw 29/29 + beam 28；⑤ gkbench 366/384=95.3% / 97.4% 逐张。
（新增 1 个测试文件、16 条测试 + 1 条 play_choice 映射测试，旧 mechanism 测试同数替换。）

**如实记录的剩余差距**：のんびり（leisure）指針及其解除规则、全力回合額外出牌/保留牌回手、
P 道具/附魔来源的熱意未建模；生产读屏还没读熱意图标与当前温存段階（`_search_state` 每步按
回合开始熱意 0 估，同现有「不读好调/集中层数」口径，影响只在同回合第二张/額外出牌时）。
B2 学习叶子特征的 `save_cards_used` 已废弃（恒 0），重训时再换熱意特征（模型本来就要重训）。

**文档**：RULES_REFERENCE §0/§1/§2/§3/§5.2/§6/§7；WORKPLAN B5；HANDOVER_NEXT §0/§1/§2/§4/§8；
INDEX/COMPARE/EXPECTIMAX/SIMULATOR/README 同步。

**提交**：feat `aca21da`（代码 + 测试 + 文档）；哈希记录 `01c983a`。

**下一步**：T5 剩余机制（fresh buff 差一回合、P 道具数据接入）→ 阶段 C/D 离线收尾 →
真机 T3→T1→T2 → F1/F2 gkbench 公开对比。

### 二·补二十七、11-22（B6 / T5③ P 道具数据接入：loadout → PItemSpec → 模拟器/评测/提交）

**背景**：`sim/p_items.py` 早就有「事件 → 增量」的被动结算接口，`LessonSim`/`ExpectState`
也在触发时机上调它；缺的是**真实对局到底带哪些 P 道具**（RULES_REFERENCE §6.5
「produce 侧 P 道具列表未采集」）。本会话把离线能拿到的数据源接上：

- 真机采集 `traffic.jsonl`（3.2MB，11-22 02:29）全文件扫 `produceItem/ProduceItem/`
  `produce_item/itemIds/item_ids/pItem/p_item` **全部 0 命中** → 真机培育侧 P 道具列表
  只能等 T6/D1 补采（例如 produce 开始 API 响应/存盘）；
- 离线完整数据源 = **gkbench 505 个题模板**：`saves.jsonl[].loadout.produce_item_ids`
  （每局 1–10 个，共 2686 个 id / 83 个唯一）。gkbench 合约（`data/bench_repo/gkbench/`
  `algos/base.py`）明确 `ctx.loadout` 是**开局配置（不含种子）**，用它是公平的；
  官方 AI 笔记 §3.6 也把「P 道具映射」列为 gkbench 适配器最大分数缺口之一。

**机制/口径（不猜、不静默）**：

1. **id 精确匹配** `data/knowledge/p_items.json`（1068 件，2026-09-16 主数据快照）：
   `pitem_02-3-293-0` 就是同名行，**不做**「去掉 `-N` 后缀当强化前版本」的兜底
   （强化变体数值不同，猜错会凭空加减分）。快照之后新增的道具落进 `unknown_ids`，
   显式上报（生产侧不会假装结算过它们）。
2. **新增触发时机 `exam_start`**（训练/考试开始时；素材里 288 段）：`LessonSim`
   构造时（抽第 1 手牌**之前**）结算一次，顺序 = `exam_start` → `turn_start`；
   `exam_start` 给的额外出牌次数属于第 1 回合（初始抽牌不清零）。
3. **新增效果 `ExamPlayableValueAdd` → `extra_plays`**：技能卡使用数追加 +N；
   数值在 `count` 列（51 段全部 `count=1`）——旧解析只取 `value1` 会把这类道具
   退化成 0 值 no-op。`PItemDelta` 增加 `extra_plays`，`LessonSim`/`ExpectState` 镜像。
4. 其余未实现 effect_type 继续 no-op（由 `summarize`/报告统计，不抛异常）。

**落地**：

- `src/gkagent/data/p_items_db.py`（新增）：`PItemCatalog`（id → spec 段）、
  `resolve_produce_item_ids`（未知/重复 id 显式返回）、`catalog_coverage`；
  数据文件缺失/格式错**抛 `PItemDataUnavailable`**，不静默当"没有 P 道具"。
- `src/gkagent/sim/p_items.py`：`EXAM_START`、`EXTRA_PLAY_EFFECTS`、
  `PItemDelta.extra_plays`、`_effect_value`（ExamPlayableValueAdd 取 `count`）、
  `_trigger_matches` 的 exam_start 分支。
- `src/gkagent/sim/lesson.py`：构造时 `_fire_p_items(EXAM_START)` +
  `_draw_hand(keep_extra_plays=True)`；`_fire_p_items` 结算 `extra_plays`。
- `src/gkagent/sim/expectimax.py`：`fire_p_items` 镜像 `extra_plays`；
  `_p_item_event_subset` 增加 exam_start 分支（搜索从中途开始，不会重复触发）。
- `src/gkagent/sim/leaf_data.py`：`RecordingLessonSim._draw_hand` 跟随新签名
  （B2 数据采集用）。
- `scripts/local_bench.py`：`build_problem` 把 `loadout.produce_item_ids` 解析成
  `PItemSpec` 塞进 `LessonConfig.p_items`；新增 `PItemStats` + 报告 `p_items` 块
  （模式/题数/id 数/已知/未知/spec 段/已实现段），`deck_modeling.p_items_modeled`
  从常量 0 变成真实计数；新增 `--p-items auto|off`（A/B 对照，off = 旧行为）。
- `submissions/expectimax/algo.py`（gkbench 提交）：`ctx.loadout.produce_item_ids`
  → `PItemSpec` → `ExpectState.p_items`（一局解析一次、可缓存）；新增
  `p_items=false` 参数；缺数据文件时按空清单跑但 `Decision.meta["p_items_error"]`
  记原因（不假装结算过）。提交打包时把 `data/knowledge/p_items.json` 也复制到
  提交目录旁（与 card_table.json 同口径）。

**数据/覆盖率（如实）**：

- catalog 1068 件 → 1764 个 spec 段；已实现 421 段（8 种 effect_type：
  ExamLesson/ExamBlock/ExamLessonBuff/ExamReview/ExamCardPlayAggressive/
  ExamFullPowerPoint/ExamStaminaRecoverFix/ExamPlayableValueAdd），no-op 1343 段
  （effect_type 不支持 980 / 触发时机不支持 194 / 无值 169）。
- gkbench 505 题模板：2686 个 id / 83 唯一 / **72 已知 / 11 未知**（快照后新道具：
  `pitem_01-3-349-0`、`pitem_02-3-336-1`、`pitem_03-3-334/337/345-*`、
  `pitem_3-258-research-event-008/009/010` 等）；72 个已知 → 131 段 spec，已实现 31 段。
- **起点体力校准补注**：F0 记的 15 组体力偏差里，5 组（`i_card-shro-3-016` ×5，
  −28）现在可以用 `pitem_02-3-293-0` 的 exam_start「最大体力的 80% 数值变为体力消耗」
  解释：`floor(36×0.8)=28`（对应 5 组 `check.stamina = starting − 28`）；其余 10 组
  涉及快照缺行的新 P 道具或主道具附魔，**不猜**（见 GKBENCH §4.5 补注）。

**离线 A/B（`scripts/local_bench.py`，hif 样本 30 题 × 2 seed，同题同 seed 配对）**：

| 算法 | off（不结算 P 道具） | auto（按 loadout 接入） | 配对 Δ | 变化局 |
|---|---:|---:|---:|---:|
| greedy | 3840.7 | **3969.7** | **+128.9（+3.36%）CI95 [+9.5,+248.4]** | 8/60（8 胜 0 负 52 平） |
| expectimax(analytic) | 3759.3 | **3908.9** | **+149.6（+3.98%）CI95 [−171.0,+470.2]** | 12/60（6 胜 6 负 48 平） |

- 覆盖：30 题共 147 个 id（130 已知 / 8 未知，样本里没抽到全部 11 个）、174 段 spec
  中 33 段已实现；**大部分局逐位不变**（P 道具效果多是带条件/次数上限/百分比，
  未实现的仍是 no-op），所以 Δ 的方向为正、幅度受覆盖率限制。
- 结论：数据接入路径正确（同题同 seed 分数不降；greedy 显著提升、expectimax 方向
  为正但被大分差局噪声淹没）。这不是"P 道具建模完成"，只是"数据接进管线"。

**测试**：新增 `tests/test_p_items_db.py`（10 条：catalog/未知显式/重复/缺文件、
真数据 1068 件、gkbench 505 题模板 72 已知/11 未知）、
`tests/test_gkbench_submission_p_items.py`（6 条：loadout 解析/缓存/开关/缺数据
meta/ExpectState 接线/端到端 meta）、`tests/test_p_items.py` +5、
`tests/test_p_items_integration.py` +4（exam_start 构造时结算/先于 turn_start/
额外次数保第 1 回合/真数据只触发一次）、`tests/test_local_bench.py` +4
（loadout → config/端到端考试开始效果/off 开关/报告覆盖率）；旧
`test_unsupported_trigger_is_noop` 去掉 exam_start（它已被支持）。
全量 pytest：**1051 passed / 1 skipped（1052 收集 / 76 文件）**（唯一 skip 仍
`tests/test_produce_ui.py:1181`；旧 1024 + 净增 28 条）。

**基线复核（改完复跑，退出码均 0）**：① 洗牌 4/4 + 重洗 3/3；② **1051/1**
（1052 收集 / 76 文件）；③ 4/4 场 86/86 + 24/24；④ 36/36 + 3/3 + known_draw 29/29
+ beam 28；⑤ gkbench 366/384=95.3% / 97.4% 逐张（①②③④⑤ 数字全不变——本次只动
P 道具数据管线，不动洗牌/牌序/审查倍率）。

**文档**：RULES_REFERENCE §0/§1/§3/§5.3/§6/§7；WORKPLAN B6；HANDOVER_NEXT
§0/§1/§2/§4/§8；INDEX/COMPARE/GKBENCH §4.5/OFFICIAL_AI_NOTES §3.6/§5/
EXPECTIMAX B2 重训注/SIMULATOR；本文件二·补二十七。

**如实记录的剩余差距（下一段）**：

1. **produce 侧真机 P 道具列表仍未采集**（traffic 无字段）→ T6/D1 采集扩展
   （produce 开始 API/存盘），否则真机培育模拟仍拿不到本人这局带的 P 道具。
2. **效果覆盖低**：gkbench 已知 72 个道具里 131 段 spec 只实现 31 段；未实现大户 =
   `ExamLessonValueMultiple`（打分上升量）、`ExamParameterBuff`（好调/审查基准两种
   口径未定）、`ExamStaminaReduceFix`（体力消耗为百分比且数据缺值）、
   `ExamCardCreateId`（生成卡）、`ExamConcentration/ExamPreservation`（指針）、
   `ExamReviewMultiple` 等 → 需要参考引擎语义 + 主数据文本重解析（如「最大体力的
   N%」）再补，别猜。
3. `p_items.json` 快照落后（11 个新 id 缺行）→ 刷新 gkumasu-diff 主数据快照后重生成。
4. gkbench 提交侧：`obs` 没有 P 道具已用次数 → 保守从 0 开始（高估剩余次数）；
   主道具附魔 `main_item_enchant_ids` / 回忆 `memory_ability_ids` 未接入。
5. B2 学习叶子重训仍等 **fresh buff（需真机逐回合截图）+ P 道具效果覆盖** 补齐
   （本轮只完成数据接入，不是效果全集）。

**提交**：feat `f531d20`（代码 + 测试 + 文档）；哈希记录 `639f0b0`。

**下一步**：**fresh buff 差一回合**（需真机逐回合截图；E0 若能跑离线培育可作替代截图来源）
→ 阶段 C（执行层可靠性，含 C0）/ D（补采集）→ 真机 T3→T1→T2（含 E0 实验）→ F1/F2 gkbench 公开对比。
**另（2026-11-22 用户指定「开新对话做」）**：候选任务 **T9 = B7（P 道具 47 条补全，默认首选）/
C0（采集更新可靠性经验吸收）/ E0（离线培育测试台实验）三选一**，见
[HANDOVER_NEXT §4 T9](HANDOVER_NEXT.md)。背景见二·补二十八 / [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)。

### 二·补二十八、11-22（外部情报：作者 11-22 四游戏整合启动器包——只读分析，衍生候选任务 T9）

**来源**：用户提供 `偶像大师启动器.7z`（215,136,770 B，sha256 `28eb9f8b…39e3ab`），作者 =
当初「本地化部署」路线同一线（同一 `yaha_proxy` hook + `mitm/cache_server.py` + `unlock.py`
后端）。**只做静态分析，没有运行 exe/服务/游戏**；7z 归档 `data/dl/`（gitignore），解包在
仓库外 `D:\Games\_launcher_inspect\THE IDOLM@STER\`（400.1 MB / 1458 文件）；包内
`交付文件清单.sha256.json` **1457/1457 条逐条校验通过**。完整分析见
[LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)，提交 `ddf221f`。

**包是什么**：不是单个学マス补丁，而是**四游戏整合启动器**（学园/百万现场/灰姑娘/闪耀色彩）：
启动器本体（11-22 18:42 构建）+ 学园本地服务源码 + 四游戏适配 + 完整文档 + 哈希清单。
包内文档最新只到 11-14，**11-22 的代码变化没有发布说明**（只能从 diff/文件时间看）。

**11-22 新版本变化（包内可验证）**：
1. **启动器**：新增整套中文错误诊断（`LauncherErrors.cs` + 「更多→错误提示与解决方法」+
   根目录 `错误提示与解决方法.txt`；日志/退出码→中文原因+处理）；百万现场新增「停止服务」；
   修子进程输出流/Exited 竞态、停止中 busy 判定、grab_master UTF-8 输出等。
2. **学园本地服务**：新增 **`produce_runtime.py`+`produce_catalog.json`（离线培育
   Selection Exam / produce-007 进度状态机）**——161 偶像卡组/18 lesson/20 event/shop/休息；
   **考试算分仍在客户端**（服务端只发 `exam_seed`、收 lesson 结果，无 Audition/Exam 结算）；
   另有 `activity_cache` / `octo_catalog` / `master_lifecycle`（发布事务+回滚槽）/
   `local_costume_master`+`tools/local_playability`（新偶像/服装离线 Live 可玩）/
   `tools/local_content_sync`（从已下载缓存同步 19 类表，不联网）；数据/回放夹具刷新。
3. **包内文档化的既有修复（11-07→11-14）**：学更新链路真实 onetime_token/拒绝零值票据/
   TLS 失败回退直连/DMM 非必须；代理生命周期（CA 精确指纹、只停本目录服务、不覆盖用户
   Clash 代理）；更新桥接丢失客户端版本/平台/会话头与 `x-error-code 2004`；MLTD 中文路径
   编码/高分辨率截图；11-13 移除 MLTD 汉化+资源快照修正；11-12 交接另记 CGSS sqlite3 等。

**对我们的帮助（结论：参考级，能吸收经验/语义，救不了当前卡点）**：
- **能吸收（低成本）**：① 游戏更新后采集/更新断链的排障判据（2004、协议 hash/master 结构、
  TLS 回退、CA 指纹、代理恢复、只停本目录服务）；② Produce API 字段语义/成长接受式
  （`min(score,limit,3000-stat)` 等）可核对采集解析与模拟器口径；③ **P 道具 47 条 id 清单**
  （包内 `masterTrans/ProduceItem.json` = 1115 个 id，正好是 I18N_TODO 的 1068→1115 缺口，
  且 **B6 的 11 个 gkbench 未知 id 全在其中**；但只有 id、没有效果数据，不能直接补
  `p_items.json`，正路是更新 gkumasu-diff 快照重建）。
- **可实验（中成本，可能高价值）**：离线培育若能在**独立副本**上推进到考试，可作为 fresh buff
  逐回合截图/T1 UI 回归的**零账号风险**来源；但代码没看到考试处理，很可能卡在考试日，
  需一次实验确认（独立副本，勿动采集安装）。
- **不能指望**：考试/课程算分公式（客户端算，服务端没有）、替换/升级我们的采集安装
  （新包 **没有 `GKM_TRAFFIC`**、hook 构建不同，覆盖会毁采集链路）、把代码/数据直接拷进
  本仓库（未声明仓库级许可证 + 作者自测未做游戏内验收 + 含作者离线存档）。

**产出**：新增候选任务 **T9**（B7/C0/E0 三选一，见 [HANDOVER_NEXT §4](HANDOVER_NEXT.md)）；
WORKPLAN 增 B7/C0/E0 候选节。用户要求「开新对话做」，一次会话只做 1 个；**默认建议先 B7**
（纯离线、收益明确：47 条补全、gkbench 未知 id 清零）。当前 T5/阶段 C/D 主线不变。

### 二·补二十九、11-22（T9-B7 落地：P 道具 47 条补全，p_items.json 1068→1115、gkbench 未知 id 清零）

**背景**：B6 把 P 道具数据管线接进了模拟器/评测/提交，但 `data/knowledge/p_items.json` 还是
2026-09-16 的本地中文 master 快照（1068 件）；上游 gakumasu-diff `ProduceItem.yaml` 已到
**1115 件**（缺 47 条，其中含 B6 里 gkbench 的 11 个「未知 id」）。作者 11-22 整合包只给了
1115 个 id、没有效果数据（[二·补二十八](#二补二十八11-22外部情报作者-11-22-四游戏整合启动器包只读分析衍生候选任务-t9)），
所以本任务走「新 yaml 结构 + 仓库自译表」的正路，纯离线、不碰真机/账号。

**做法（`scripts/build_p_items.py`）**：

1. 生成口径从「只遍历本地 masterTrans」改为**合并**：本地 1068 件仍走原分段对齐逻辑
   （中文描述+数值取本地化文本），yaml 独有的 47 件走**纯 yaml 口径**
   （`_extract_effects_yaml`：结构化字段/数值来自 yaml 分段，不猜）。
2. **中文缺口显式标记**：47 条的卡名用仓库已提交的自译表
   `data/i18n/translation_new.json`（47/47 命中，含「+」强化变体按基础名+`+`匹配）；
   **描述没有中文**→ `text_zh=""`、`text_ja` 保留 yaml 日文、记录标
   `i18n_text_source="ja"`（不臆造译文）。
3. **条件未知保守处理**：新道具用的新触发 id 在本地 masterTrans 的触发表里没有中文触发句，
   无法解析条件（如「剩余5回合内/体力80%以上/手牌特定卡」）→ 记录标 `condition_known=False`
   （22 件），`PItemSpec.condition_known` 传给 `apply_passive` **跳过**——
   宁可不触发，也不把带条件的道具当无条件结算。`summarize` 单列 `condition_unknown` 计数，
   不混进 implemented/noop 口径。
4. `stats`/`source` 增加显式计数：`items_local_master` / `items_from_yaml` /
   `items_i18n_name_ja` / `items_i18n_text_ja` / `items_condition_unknown`；
   `local_bench` 报告也带 `condition_unknown_specs`（不再把「未知 id」当快照缺行）。

**数据结果（如实）**：

| 指标 | B6（1068） | B7（1115） |
|---|---:|---:|
| catalog 件数 | 1068 | **1115**（本地 1068 + yaml 新增 47） |
| spec 段数 | 1764 | **1849**（+85：80 段效果 + 5 段无效果 unknown） |
| 已实现段数 | 421 | **445**（+24） |
| no-op 段 | 1343 | 1404（effect_type 1026 / 触发时机 207 / 无值 171） |
| 条件未知段（另计） | 0 | **46**（22 件；新增 47 条里条件没解析出来的） |
| gkbench 505 题模板唯一 id | 83（72 已知/11 未知） | 83（**83 已知/0 未知**） |
| gkbench 唯一 id spec 段 | 131（实现 31） | 153（**实现 34**、条件未知 10） |

- 47 条新增都能解析出 ≥1 段 spec（5 条育成期道具没有考试效果 → unknown no-op 段）；
  新增 id 与 yaml/包内 1115 id 清单完全一致（`yaml 缺 id = 0`）。
- 样本覆盖（A/B 的 30 题）：147 id / **147 已知 / 0 未知**（B6 130/8）、198 段 spec
  （B6 174）、已实现 35 段（B6 33）、条件未知 9 段。

**离线 A/B（`scripts/local_bench.py`；hif 30 题×2 seed、seed 1000/1001、`--budget-ms 100`、
同题同 seed 配对；CI = mean±1.96·SE，与 B6 同口径）**：

| 算法 | off | auto | 配对 Δ | 95% CI | 变化局（胜/负/平） |
|---|---:|---:|---:|---|---|
| greedy | 3840.7 | **3969.7** | **+128.9（+3.36%）** | [+9.5,+248.4] | 8/60（8/0/52） |
| expectimax(analytic) | 3732.0 | **3953.6** | **+221.5（+5.94%）** | [−71.4,+514.4] | 13/60（10/3/47） |

- **greedy 与 B6 逐位相同**（连 CI 都相同）：新增 47 条里 22 条条件未知、其余多是
  未实现效果类型/育成期触发 → 不触发。所以 B7 的 A/B 变化来自「数据更全」而非「新效果生效」，
  +128.9 仍然是 B6 数据接入的收益；**新增 47 条目前对分数贡献 0**。
- expectimax 差异受墙钟预算抖动影响（B6 同 harness 是 3759.3→3908.9，+149.6；
  本次 3732.0→3953.6，+221.5），两次 CI 都含 0，只作方向记录。
- 结论：DoD「catalog 1115 / gkbench 未知 0 / pytest 全绿 / A/B 数字记录 / 文档同步」达成；
  下一步的分数空间在**条件/效果语义**（`condition_known` + 未实现 effect_type），
  不再是数据缺失。

**测试/基线（改完复跑，退出码均 0）**：新增 3 条测试（`test_p_items_db.py` +1：
47 条新增全覆盖/未知清零/条件未知计数；`test_p_items.py` +2：`condition_known`
保守跳过、`summarize` 计数；`test_p_items_integration.py` 触发候选过滤加
`condition_known`）；全量 pytest **1054 passed / 1 skipped（1055 收集 / 76 文件）**；
基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。

**文档**：RULES_REFERENCE §0/§3/§5.3/§6；WORKPLAN B7；HANDOVER_NEXT §0/§1/§2/§4/§8；
README/INDEX/COMPARE/GKBENCH/SIMULATOR/EXPECTIMAX/OFFICIAL_AI_NOTES/PROVENANCE/I18N_TODO/
LOCAL_LAUNCHER_20261122；本文件二·补二十九。

**提交**：feat `ca83800`（代码 + 数据 + 测试 + 文档），见 [七、最近提交记录](#七最近提交记录)。

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
- 2026-11-21 深夜用户反馈：**群里已开始出现 MITM/RNG 讨论**（"最新发现"），但只是刚摸到
  「能拿 seed/RNG」的入口，尚未复现牌堆重建+洗牌+决策全链路；我们仍是完整链路唯一的实现方。

- 2026-11-22 01:40 补充：群主 **Muskot** 在 B 站发《让2B决策模型来当学P【EP1｜一局完整的培育】》
  （BV1dnsp6WEos，约 11-15 发布）：微调 **~2B 决策模型** + 修改版 **MaaGakumas / macOS** 完整跑一局，
  置顶评论是群招募。**群内所有技术讨论（MITM/RNG/视觉/组卡）都是这个项目的组成部分**；
  他们的路线是"小模型端到端决策"，我们是"MITM 全知 + 模拟器搜索"——互补，且我们的 exact
  state/action/score 数据是训练/校准模型缺的监督信号（对应 T4 rollout 监督方向）。
  **对外策略**：不公开可复现路径（hook/解密/字段/算法），最多发结论；优先趁封堵窗口自用验证与备份数据。

详见 `docs/QQ_GROUP_NOTES.md`、`docs/HIRO_VIDEO_NOTES.md`；**我们 vs 他们的完整进度对照
（口径/数字/唯一可比路径）见 [COMPARE.md](COMPARE.md)**。

---

## 四、下一步（按优先级）

> **任务拆分、验收标准、依赖顺序见 [HANDOVER_NEXT.md](HANDOVER_NEXT.md) §4**（T1 → T3 → T2 → T4 …）。
> 本节只记"大方向 + 已经完成的项"。

**离线阶段 A 收口（2026-11-22 完成 ✅）**：A1 OCR 日文模型 ✅（二·补十四）→ A2 F#42 课程硬打必须得分 ✅
（二·补十五）→ A3 F#43 结果页空转 ✅（二·补十六）→ A4 离线回放素材 ✅（二·补十七）→
**A5 T3 离线预演 ✅**（二·补十八）；阶段 A 全部完成。**B1 T4 修正 ✅**（二·补十九：评测执行器
bug 修正后 beam unknown 164.0 / known 165.5 vs within 143.1，决策门 PASS；frontier 叶子中性）。
**B2 全知数据训练 MLP 叶子 ✅**（二·补二十：B1 修正 harness 上确认段 120 局 beam 157.8 →
165.5（+7.7，CI [+4.2,+11.2]）/ ensemble 166.9（+9.0）；within 用 learned 变差为已记录负结果，
只对 engine=beam 有益）。**B3 T5 机制建模 ✅**（二·补二十一：模拟器对齐真机「每回合基础 1 张 +
打完自动结束 + SKIP 回 2 体力 + 取整 safeCeil」，RULES_REFERENCE 重写为逐条核验表，
真机 39 回合回合规则配对回归；重标定后整局 A/B 里 expectimax 显著强于 rules（+342~+429 评价点），
B2 旧模型失效需按新规则重训）。**F 阶段数据 + F0 预检 ✅**（二·补二十二：用户登录 gkbench 拿令牌，
批量下载 80 run/36,350 条路线/329 题官方种子+check/505 题存档/两种榜单 + 参考分；用官方
`check.hand` 核对洗牌模型 **286/384=74.5%** 精确命中，npc 按 stage：選抜 5、本戦 2；
不一致根因=initial_add 自定义 + isInitial 变体，见 [GKBENCH.md](GKBENCH.md)）。
**F0 收尾 ✅**（二·补二十四：initial 按 base id（含强化变体）+ initial_add、npc 按 idol 卡
（本戦 jsna 4 人制/fktn 2 人制/其余 3 人制）→ 官方 `check.hand` **366/384=95.3%**
精确 / 97.4% 逐张，選抜 100%；剩余 18 组全是考试开始加卡机制、无一洗牌错误；
起点校准 turn=1/score=0/stamina 96.1%=starting_stamina/rules=55，见 [GKBENCH §4.5](GKBENCH.md)）。
**开工基线复核 ✅ 2026-11-22 17:2x**（二·补二十三：四条基线全绿——① 4/4+3/3、② 985/1、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28，与文档期望逐项一致）。
**B4 / T5① 审查倍率分段 + 联动惩罚 ✅ 2026-11-22**（二·补二十五：常量 4.11 → 客户端真实公式
「分段折线 × 审查基准联动惩罚 × 单精度取整」；模拟器按回合属性乘、生产读屏倍率进搜索
（日志 `attr=2.07`）；真机夹具期中 4.09/2.20/2.60×、期末 6.97/2.85/4.96×；21 条测试，
全量 pytest 1006/1（1007 收集 / 73 文件））。
**B5 / T5② 熱意 + 温存解除 ✅ 2026-11-22**（二·补二十六：熱意独立整数资源（出牌分加算、
获得时 ceil、回合末清零/熱意延長）；温存解除 +5/+8 熱意、2 段固定元気 +5、解除当回合 +1
出牌次数（同回合可重复、温存→全力回合边界也触发）；卡牌熱意追加/増加/延長/本牌適用倍数 ×2
接入 MODELED_EFFECTS 29→32；16 条测试，全量 pytest 1023/1（1024 收集 / 74 文件））。
**B6 / T5③ P 道具数据接入 ✅ 2026-11-22**（二·补二十七：新增 `data/p_items_db.py`
把 loadout 的 `produce_item_ids` 解析成 `PItemSpec`（未知 id 显式上报）；新增
`exam_start` 触发时机（288 段素材，LessonSim 构造时结算）与 `ExamPlayableValueAdd →
extra_plays`（51 段，取 `count` 列）；`LessonSim`/`ExpectState` 镜像；gkbench 提交适配器
从 `ctx.loadout`（公开配置）接入；`local_bench --p-items auto/off` 离线 A/B：hif 30 题×2 seed
greedy **+128.9（+3.36%，CI[+9.5,+248.4]）** / expectimax +149.6（+3.98%）；新增 29 条测试，
全量 pytest **1051/1（1052 收集 / 76 文件）**。仍缺：真机培育侧 P 道具列表（T6/D1 补采）、
效果覆盖（已知 72 道具 131 段 spec 只实现 31 段）、主道具附魔）。
**下一步：T5 剩余机制**（**fresh buff 差一回合**——需真机逐回合截图；E0 若能跑离线培育可作
替代截图来源；P 道具效果覆盖先做 B7）→ 阶段 C（执行层可靠性，含 C0）/ D（补采集）离线收尾
→ 真机（T3→T1→T2，含 E0 实验）→ F1/F2 gkbench 公开对比。
**另（2026-11-22 用户指定「开新对话做」）**：候选任务 **T9 = B7（P 道具 47 条补全，默认首选）/
C0（采集更新可靠性经验吸收）/ E0（离线培育测试台实验）三选一**，见
[HANDOVER_NEXT §4 T9](HANDOVER_NEXT.md) / 二·补二十八。
总序列以 [WORKPLAN.md](WORKPLAN.md) 为准。

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
**已完成（见二·补五）**；④ 采集进程 ↔ 决策进程实时打通（traffic.jsonl → policy 进程）——
代码 + 离线预演已完成（A5，见二·补十八），差真机考试验收。
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
（2026-11-22 T9-B7 P 道具 47 条补全：p_items.json 1068→1115、gkbench 未知 id 清零、条件未知段保守跳过）
ca83800 feat(t9): B7 P 道具 47 条补全——catalog 1068→1115 + 条件未知保守跳过（3 条测试）
（2026-11-22 交接：作者整合包帮助评估 + 候选任务 T9（B7/C0/E0，开新对话做））
508aa34 docs(handover): 记录作者 11-22 整合包的帮助评估 + 新增候选任务 T9（B7/C0/E0，开新对话做）
（2026-11-22 外部情报：作者四游戏整合启动器包 11-22 版静态分析——只读参考，衍生候选任务 T9）
ddf221f docs(intel): 作者 2026-11-22 四游戏整合启动器包分析——新版本变化/修复与采集安装边界
（2026-11-22 B6 / T5③ P 道具数据接入：loadout produce_item_ids → PItemSpec + exam_start/extra_plays + gkbench 提交/本地评测接线）
639f0b0 docs(handover): 补 B6 提交哈希（f531d20）+ 最近交接记录
f531d20 feat(t5): B6 P 道具数据接入——loadout produce_item_ids → PItemSpec + exam_start/extra_plays + gkbench 提交/本地评测接线（29 条测试）
（2026-11-22 B5 / T5② 熱意 + 温存解除：独立熱意资源 + +1 出牌/固定元気 + 卡牌效果接入）
01c983a docs(handover): 补 B5 提交哈希（aca21da）+ 最近交接记录
aca21da feat(t5): B5 熱意 enthusiasm + 温存解除——独立熱意资源 + 出牌次数/固定元気 + 卡牌效果接入（16 条测试）
（2026-11-22 B4 / T5① 审查倍率分段 + 联动惩罚：常量 4.11 → 客户端真实公式 + 屏幕倍率进搜索）
bb8171a docs(handover): 补 B4 提交哈希（6b4beae）+ 最近交接记录
6b4beae feat(t5): B4 审查倍率分段+联动惩罚——客户端公式 + 主数据解析 + 屏幕倍率进搜索（21 条测试）
（2026-11-22 F0 收尾：官方 gkbench 384 组种子核洗牌模型 286→366/384 + 起点校准）
2e4deee docs(handover): 补二·补二十四提交哈希（83f1f96）+ 最近提交记录
83f1f96 feat(f): F0 收尾——官方 gkbench 384 组种子核洗牌模型 286→366/384 + 考试起点校准
（2026-11-22 开工基线复核）
90d5b87 docs(handover): 二·补二十三——开工基线复核四项全绿（985/1、86/86、36/36、beam 28）+ 同步 B3 后测试状态
（2026-11-22 F 阶段数据 + F0 预检：gkbench 批量下载 + 官方种子核洗牌）
fcce824 docs(handover): F0 数据与预检交接——gkbench 批量下载/官方种子核洗牌 286/384/参考分，下一项 F0 收尾
cc1d0cf feat(f): gkbench 令牌数据补齐 + F0 初步验证（官方 check.hand 对照洗牌模型 286/384 精确命中）
b6d7868 feat(f): gkbench 公开数据批量下载工具 + GKBENCH.md（API/参考分/令牌边界）
57e2a8d docs(workplan): F 阶段加 F0——用户已登录 gkbench 可下载固定种子题，先用官方 check 交叉验证洗牌模型/校准口径
（2026-11-22 B3 T5 机制建模：回合规则对齐 + RULES_REFERENCE 核验表）
d797802 docs(handover): B3 完成交接——回合规则对齐真机 + RULES_REFERENCE 核验表 + 重标定（pytest 985/1，B2 旧模型待重训）
4316f9a feat(b3): T5 机制建模——模拟器回合规则对齐真机（每回合 1 张 + 自动结束 + 跳过回 2 体力 + safeCeil 取整）
（2026-11-22 B2 全知数据训练 MLP 叶子）
5cd23d0 docs(handover): B2 完成交接——状态/基线数字(975/1)/确认段 beam +7.7/负结果与生产接线，下一项 B3
ccabd0a feat(b2): 全知数据训练 MLP 叶子——叶子状态样本 + 104 维结构化特征（B1 修正 harness 配对确认段 beam +7.7）
（2026-11-22 B1 T4 修正）
4512836 docs(handover): B1 完成交接——状态/基线数字(964/1)/决策门 PASS/下一步 B2
fda7b90 feat(b1): T4 修正——评测执行器白丢回合 bug + 受控 frontier 叶子（60 局 beam 已超 within，决策门 PASS）
（2026-11-22 A5 T3 离线预演）
3bb6a6e docs(handover): A5 完成交接——状态/基线数字(958/1)/提交记录同步，下一项 B1
7c16abe feat(a5): T3 离线预演——--current 候选 + ExamPlanSelector 逐回合锁定（脚本 + 8 条单测）
（2026-11-22 A4 离线回放素材）
7eba62d docs(handover): A4 完成交接——状态/基线数字(950/1)/提交记录同步，下一项 A5
99bb6df feat(a4): A4 离线回放素材——8 张真机关键帧 + 9 条帧回放测试 + scan_frames 挑帧工具（修 _checkbox_bands TypeError，F#44）
（2026-11-22 A3 收尾：复现脚本 + 交接同步）
1a4b7f8 chore(tools): A3 复现脚本（帧回放 / 事件屏扫描）+ gitignore 过滤 pytest 临时产物
cdf7fca docs(handover): 补 A3 F#43 提交哈希（106ef2b）
106ef2b fix(ui): F#43 结果页空转——真根因日文饮料选择屏 + P 费标签误判飘字（真机帧回放 7 条）
（2026-11-22 A2 F#42 课程硬打必须得分）
b388274 fix(lesson): F#42 课程硬打必须得分（HUD 语义 + 每回合 1 张 + 硬打保分）
（2026-11-22 A1 OCR 日文模型）
1496370 docs(handover): A1 日文 OCR 落地记录 + 提交哈希（aae2647/884272f）
8823bb7 docs(handover): A1 补中文 UI/性能回归数字（bench_ocr --verify 5/5、行动页 189ms）
aae2647 feat(ocr): A1 换日文/多语言模型（官方 PP-OCRv6 Apache-2.0）+ 下载脚本/配置/probe/测试
884272f test(ocr): 事件快速路径允许补读对话区后，修正 read_calls 过期断言（基线修复）
（2026-11-22 凌晨）
4c9f024 feat(eval): T4 起点——档位效用平手项 + beam 采样分支（实验，默认关闭）
（2026-11-21 深夜四段）
09b9358 feat(sim): 上真机前整局引擎 A/B + 考试策略注入 + auto_produce 墙钟上限
ae86e1c feat(policy): 禁用 rules 回退——搜索引擎失败必须暴露，不许静默改用规则
（2026-11-22 凌晨四段）
2cb4c20 docs(workplan): master plan for next session - offline finish, then real machine, then gkbench
a608c6e docs: group-files analysis - OCR root cause (JP model), GKMSMAA structure, experimental APK
26459dc docs: 11-22 P0/T3 first real run (F#41-43) + group files intel + launcher flags
584f742 fix(ui): story choice bubbles - layout fallback + region OCR (real-machine ep-t3-1..3)
e820e34 docs(exam): known_draw 事前检测实现记录（169/1829 机制卡、四场牌组 0 命中）
beec501 feat(exam): known_draw 事前检测——额外 RNG 机制卡扫描（exam_risk）+ ExamSetup.rng_risk + 计划拒用 + bot 跳过候选
67a1a37 docs(t4): rollout 叶子负结果 + C/4242 整局记录 + 群 MITM 情报更新
366131a feat(t4): rollout 叶子最小版（ExpectState→LessonSim 快照 + RolloutLeafValue + eval 开关）——实验负结果，默认关闭
（2026-11-21 深夜三段）
8a9b5aa docs(handover): 二·补七——真机首局战报(C/4242)+禁跳规则+7类卡点+下一步
b231b3f fix(policy): 禁跳例外只剩真没体力；费用预览读歪防护（29==体力 视为无效）
8a2af2b feat(policy): 用户规则——只有真没体力才 SKIP；读不到价值一律硬打 + 搜索回退原因细化
4b07fa7 fix(bot): 授课答题屏/回合结束弹框/领奖误判/--ignore-user——真机整局卡点收敛
（2026-11-21 深夜二段）
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

**测试状态**：`pytest tests/` **1023 passed / 1 skipped**（1024 条收集 / 74 个测试文件），含
`tests/test_exam_shuffle.py` 四场考试洗牌回放 + 「实战回合算 K 会错」回归防线 +
三组弃牌堆重洗样本对照；`tests/test_expectimax_known_draw.py` 8 条 +
`tests/test_exam_oracle.py` 6 条完全信息搜索；`tests/test_expectimax_discard_order.py` 17 条
重洗后段全知 + `tests/test_exam_plan.py` 19 条（生产接线数据层 + ExamPlanSelector）+
`tests/test_policy_beam_engine.py` 7 条 beam/接线策略层 + `tests/test_policy_engine.py`
决策可观测性 + F#42 硬打保分 + `tests/test_lesson_play_f42.py` 3 条真机课程帧回放 +
`tests/test_produce_ui_f43.py` 7 条 F#43 真机外出帧回放/静态页兜底 +
`tests/test_frames_replay_a4.py` 9 条六类关键屏真机帧回放（A4）+
`tests/test_exam_plan_offline.py` 8 条 T3 离线预演（A5：--current 候选 + 四场 sweep）+
`tests/test_beam_frontier.py` 6 条 B1（前沿 policy-evaluation + 评测执行器丢回合回归）+
`tests/test_b2_leaf.py` 11 条 B2（叶子特征/叶子状态快照与标签/MLP 存取/搜索接线/生产
`leaf_model` 缓存与兜底/合成训练收敛）+
`tests/test_t5_turn_rules.py` 9 条 B3（真机 39 回合回合规则配对）+ `tests/test_sim_lesson.py`
实机回放黄金值 2 条；`tests/test_ocr_jp_model.py` 4 条日文 OCR 真图；
**`tests/test_exam_multiplier.py` 21 条 B4（分段折线/联动惩罚/归一化/客户端取整/模拟器回合倍率/
生产屏幕倍率接线/真机帧「舞蹈 207%」/主数据解析）+ `tests/fixtures/t5_exam_multipliers.json`
真机采集局夹具**；**`tests/test_t5_enthusiasm.py` 16 条 B5（温存 1/2 段解除常量、熱意获得公式
ceil、回合末清零/延長、+1 出牌次数、固定元気不吃やる気、同回合重复解除、熱意算分/纯 buff 牌不加、
回合末好印象加熱意、熱意追加/増加 buff、回合边界解除、本牌適用倍数 ×2、ExpectState 镜像）
+ `test_sim_produce.py`/`test_play_choice.py` 卡表映射**；`ruff check` 对改动文件通过；
四条开工基线（2026-11-22 19:5x B5 后复核全绿）：① 4/4 场 + 3/3 重洗、② 本行数字、
③ 4/4 场 86/86 + 24/24、④ 36/36、3/3、29/29、beam 28；⑤ gkbench 366/384=95.3%；唯一 skip =
`tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写，非行动页）。

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

