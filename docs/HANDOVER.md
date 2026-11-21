# 项目交接（2026-11-20 收尾）

> **导航看 [INDEX.md](INDEX.md)**（按任务列了该读哪些文档）。
> 本文只写：现状 + 下一步 + 路径速查 + 注意事项。

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
✅ 回合属性算法在 RNG offset 0 上可逐项复现两场考试（前 turns-3 回合随机、末 3 回合固定）
✅ 洗后弃牌堆重洗：期中 T7 从洗牌后状态再消耗 45 次随机数 → T7-T9 精确 9/9
   （45 应为支援临时强化等掷点；打出后去 Lost 区的卡不进弃牌堆，重洗只洗 Grave 区）
```

**新工具**（scripts/，ruff 通过）：
```
dig_deck.py            按 dump.cs 字段号标注解析任意响应（--tree 全树）
scan_deck_updates.py   扫描图鉴字段 230550472（对照用）
reconstruct_deck.py    重建考试时刻牌堆 → out/deck_snapshots.json
decode_exam_actions.py 逐回合手牌/出牌/属性 → out/exam_truth.json（--json）
verify_shuffle.py      洗牌重放验证：自动读主数据 isInitial + NPC 数，期中/期末都 ✅
```

**下一会话从这里继续**（先读 MASTER_DATA.md 附录「洗牌重放」）：
1. **采第三场考试**（另一局期中/期末都行），用 reconstruct_deck + verify_shuffle 跑一遍，
   确认 `K = (turns-3) + npc_count*turns` 普适（尤其换 produce 类型 / NPC 数不是 5 时）。
2. **洗后重洗前那张账要记全**：目前期中 T7 重洗前多消耗 45 次随机数（推测是支援卡临时强化
   的掷点：每「入手的牌 × 支援卡」一次 `integer(0,1000)`）。把这 45 次拆清楚，才能从 seed
   预测整场（含弃牌堆重洗）的牌序；期末 T9-T11 可当同一模型的验证样本。
3. 弃牌堆「Grave 顺序」已确认（按入手/打出先后 append；Lost 卡不进 Grave）。
4. 之后才接「完全信息搜索」：seed + 牌堆 → 整段牌序 → expectimax 叶子。

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

### ① 考试时刻的牌堆 + 洗牌（最高优先）—— 已端到端破解 ✅

```
✅ 牌堆 = UserData.userProduceProgressProduceCardList (309641228)，已重建（期中18/期末26）
✅ 逐回合 ground truth = ExamTurnEndLog.field50（每回合开始手牌）
✅ 洗牌完整破解：K = (turns-3) + npc_count*turns（5 NPC ⇒ 6*turns-3，期中51/期末63）
   → xorshift32(examSeedValue) advance K → FY倒序洗 Number升序牌堆
   → 第 1 回合 SetInitialCard 先抽 isInitial 卡，再补抽
   → 期中 18/18、期末 26/26 整段精确（src/gkagent/sim/exam_shuffle.py）
✅ 洗后弃牌堆重洗：期中 T7 多消耗 45 次随机数后 T7-T9 精确 9/9
```

**下一步**：① 采第三场考试确认 K 公式普适（换 produce 类型 / NPC 数）；② 拆清洗后重洗前的
45 次消耗（支援临时强化掷点），才能预测整场牌序；**完成后**：seed+牌堆→精确牌序→完全信息搜索。

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
策略配置          D:\Games\gakumas-agent\data\knowledge\policy.json（lesson.engine）
当前引擎          rules
```

**常用命令**：
```powershell
# 提取考试结果
.venv\Scripts\python.exe scripts\extract_exams.py
# 挖 seed
.venv\Scripts\python.exe scripts\find_seed.py
# 重建考试时刻牌堆（→ out/deck_snapshots.json）
.venv\Scripts\python.exe scripts\reconstruct_deck.py
# 逐回合 ground truth：手牌/出牌/属性（→ out/exam_truth.json）
.venv\Scripts\python.exe scripts\decode_exam_actions.py --json
# 洗牌重放验证（seed+牌堆 → 牌序，对照实战手牌）
.venv\Scripts\python.exe scripts\verify_shuffle.py
# 跑 bot（需游戏停在培育设置界面）
.venv\Scripts\python.exe scripts\agent_cmd.py shell --command "D:\Games\gakumas-agent\.venv\Scripts\python.exe D:\Games\gakumas-agent\scripts\auto_produce.py 340 ep-xxx --skip-home"
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

## 七、今天的提交记录

```
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

**测试状态**：`pytest tests/ -q` 全绿（795 条，含新的 `tests/test_exam_shuffle.py` 两场考试
洗牌回放），`ruff check` 通过。

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
