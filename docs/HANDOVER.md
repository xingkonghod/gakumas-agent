# 项目交接（2026-11-22 B2 更新）

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
只对 engine=beam 有益）。下一项 **B3（T5 机制建模：模拟器 plays_per_turn 对齐真机 1 张 +
RULES_REFERENCE 核验表）**；B/C/D 全部离线收尾后才上真机（T3→T1→T2），最后 gkbench。
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

**测试状态**：`pytest tests/` **975 passed / 1 skipped**（976 条收集 / 71 个测试文件），含
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
`tests/test_ocr_jp_model.py` 4 条日文 OCR 真图。`ruff check` 对改动文件通过；
四条开工基线：① 4/4 场 + 3/3 重洗、② 本行数字、③ 4/4 场 86/86 + 24/24、④ 36/36、3/3、29/29、beam 28。

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

