# auto-gakumas 分析（外部情报，2026-11-23，只读参考）

> 来源：用户 B 站发现（视频标题「学偶HIF本战剧本自动化优化部署 -S4+达成！」）→
> GitHub **tactfullotto/auto-gakumas**（公开仓库，2026-11-22 22:39 北京时间创建，
> 单次 push，tree `c29da9a`，约 137 MB，0 star/0 fork）。
> 本文只做**公开资料静态分析**（README / README_HANDOVER / manifest / 目录树 / 扫库样例），
> **未运行其代码、未拷贝任何代码/数据进本仓库**。许可证见 §6 红线。

---

## 1. 它是什么

**零 LLM、全本地**的《学园偶像大师》**H.I.F 本戦**自动培育 + 打牌决策系统：
从 Home 进本 → 日程/课程/选卡/换牌/商店 → W7 1回戦（9 回合）/ W9 2回戦（12 回合）→
培育完走自动停机。重点面向 `[ガラクタロード] 秦谷美鈴`（`p_idol_id=163` / logic 好印象流），
兼顾三职业知识库。

- **平台**：Android 模拟器（MuMu，ADB `127.0.0.1:16384` 或局域网 `192.168.x.x:5555`）；
  另有 `win32` 窗口 / `mock` 合成帧模式。**不是 DMM PC 客户端**——与我们不同平台。
- **视觉**：Windows 原生 **WinRT OCR**（ja/en，常驻 PowerShell Worker）+ OpenCV ROI；
  交接文档明确「无需 PaddleOCR / Tesseract」（根 README 提 Tesseract 是旧口径）。
- **执行**：MaaFramework 桥（`MaaAdbController` + ADB CLI fallback）+ 自写 Runner
  （loading 防抖、扫库预算隔离、Idle Watchdog、防卡死、自动停机）。
- **LLM**：H.I.F 本地主链路**零 LLM**；demo app 另有一条可选 OpenAI 兼容 LLM 决策链路
  （未配 key 自动启发式兜底，单合法动作零 token 跳过）——与主链路无关。

## 2. 架构与算法（据其 README_HANDOVER.md，未读源码验证）

```
ADB → LiveScreenRecognizer（场景分类/卡牌网格/三维/Buff/饮料 OCR）
    → LocalHybridDecisionAgent
        ├ ScheduleAgent（固定周日程）/ CardRewardAgent（选卡/删除规则）/ ShopAgent（强化/买饮料/刷新）
        └ LiveBattlePlanner
            ├ 每战现场训练 Maskable PPO（纯 NumPy，2000 eps，约 60–65s，gamma=1.0，hidden=128）
            └ 每步 SO-ISMCTS（64 次 determinized PUCT，value_weight=0.35）
                └ HeadlessBattleSimulator（快速本地 rollout）
```

1. **模拟器**（`demo/sim/battle_simulator.py`，102 KB）：直接执行 gakumas-data 导出的
   **结构化 JSON AST**（`parsedEffects`/`dsl`）——护盾/绿血/红血、好印象/干劲/好调/集中、
   **手牌/牌堆/弃牌/除外四区守恒**、P 道具触发（`@trigger`/`ttl`/`limit`）、
   费用修正（`costReduction`/`halfCostTurns`/`doubleCostTurns`，与我们 B9 同一套参考语义）、
   **回忆（メモリー）词条 Stage 级全场限 1 次**（按 base_id 跨重复卡强制）。
2. **决策**：进入每场战斗时**扫库得到真实牌组/P 道具/三维/开局 Buff → 现场训练 2000 局
   Maskable PPO → 每步 64 次单观察者信息集 MCTS（SO-ISMCTS，determinized PUCT）**。
   特征 68 维标量 + 区计数，**严格信息集安全（对抽牌堆顺序置换不变）**——他们没有 seed，
   特征不能泄露牌序（对照：我们 known_draw 是精确牌序，路线根本不同）。
3. **领域先验/守卫**（写进模拟器与搜索先验）：
   - `is_safe_dominating_free_card`：不消耗稀有跨回合资源的**免费再动卡**严格优先
     （#159 アイドル魂+ / #171 私がスター+ / #297 止められない想い+ / #137 やる気は満点+ 回忆再动）；
   - **干劲经济守卫**：耗干劲的 +1 使用数卡（#299/#305/#97/#173）在 `turns_remaining>2` 时，
     仅当干劲引擎 #128/#129 ワクワクが止まらない 已在场且干劲高于安全阈值才视为占优，
     其余交给 PPO/ISMCTS 权衡——避免前中期抽空干劲后期断档；
   - 回忆除外先验：有眠気且 `turns_remaining>=3` 时引导除外。
4. **负结果（对我们 B2 重训有参考价值）**：叠加 PBRS 干劲势能塑形（weight=0.035）后
   eval30 均值 477,670 → **450,786（−26,884）**；关闭强制耗干劲剪枝、`motivation_cost_weight=0.0`
   纯分表现最佳。**与我们的 B2 负结果同向：教师/塑形偏乐观，纯分数标签最稳。**

## 3. 数据血缘（与我们同源）

- 卡/饮料数据从 **gakumas-tools/gakumas-tools**（BSD-3，**我们 B8/B9/B10 的同一参考引擎**）
  commit `a82c3a3`（2026-11-15）解析导出：**926 卡 / 28 P 饮料 / 15 偶像 / 165 P 偶像 /
  111 自定义改造**；SQLite（4.41 MB）+ JSON + PNG 图鉴。
- DSL 效果 schema 来自 **pnpm/gakumas-data**。
- 他们的卡 id 是 gakumas-tools 数字 id（#23=眠気、#111=静かな意志+、#436=花ロボ(黄)），
  与我们主数据 `p_card-*` / `pitem_*` 是**同一上游的不同 id 方案**（B10 已用其 csv 做过交叉验证）。
- 扫库输出样例（`produce_library.json`）：p_idol/plan/scenario/recommended_effect/p_points/
  三维/deck_ids（含重复）/cards（带 memory_hooks）/p_items/card_memory_hooks
  （#127/#129 force_initial_hand）——**纯视觉扫库，无 MITM/seed**。

## 4. 成绩（快照 2026-11-23，均为其自述，未独立验证）

| 场景 | 数字 |
|---|---|
| 离线基准（W9 真卡组 24 卡，GI=3/Mot=3 开局，2000 eps 训练 / 30 局未见评估） | bestVal **466,850**；eval30 均值 **477,670**（中位 482,942 / 最高 687,855）；100% T2 前开出干劲引擎；后期平均干劲 21.16；干劲卡手数 0.0/局 |
| 实机 smoke_v7（Home 零干预） | Day1 扫库 p_idol=163 / Vo2393 Da1108 Vi1644 / 22 卡 + 7 P 道具无误标；W7 bestVal 477,554（T9 好印象 110 / 干劲 22）；W8 自动买饮料 + 4 轮カスタマイズ；W9 bestVal 734,656，T11 以 620,331 反超第 1，T13 结算前 **962,352**（simQ=1,554,892）稳拿第 1 |
| 实机 live7（根 README） | 2/2 回戦完成，**2回戦分数 +1,594,997** |
| B 站视频标题 | **「S4+ 达成」**（H.I.F 评级；仓库文档未直接写 S4，只写第 1 名/分数——**标题宣称，待核**） |
| 测试 | README：298 passed / 2 skipped（~91s）；交接：278 passed / 1 failed（ADB IP 依赖用例）/ 1 deselected |

**口径警告**：他们的 1.59M 是**真机 H.I.F 本戦 2回戦原始分**（秦谷美鈴 logic 好印象、
特定卡组/账号）；gkbench oracle 分母 1.45M 是**托管判官固定种子题**；hiro 的 1.30M 是
其账号/卡组；我们的 LessonSim 离线分（B10 auto 4638）是**简化模拟器小场景**。
**四者互不可比**（同 COMPARE §3 陷阱）。 simQ 1.55M vs 实机 T13 0.96M 也提示
**其模拟器同样偏乐观**（与我们 B2 教师偏乐观负结果同构）。

## 5. 与我们对照 / 可吸收点

| 维度 | auto-gakumas | 我们 |
|---|---|---|
| 平台 | Android 模拟器 ADB（MuMu）+ WinRT OCR | DMM PC 客户端 + MITM 采集 + PP-OCRv6 |
| 信息 | **纯视觉扫库**（无 seed）→ 信息集安全特征 + ISMCTS determinization | **seed → 整段牌序全知**（4/4 场逐张 + F0 官方 366/384）→ 精确 known_draw/beam |
| 搜索 | 每步 64 次 SO-ISMCTS（PUCT + PPO 价值混合 0.35） | 回合内 expectimax / 跨回合 beam（B1 修正后显著强于 within） |
| 学习 | **每战在线训练** 2000 eps Maskable PPO（~60s，随扫库牌组自适应） | B2 离线全局 MLP 叶子（B3 规则下失效待重训；生产默认关闭） |
| 机制 | AST 执行 DSL：四区守恒 / 费用修正 / P 道具触发 / **回忆限 1** / 自定义改造（部分） | B3–B10：回合规则/审查倍率/熱意/P 道具 1042/1849 段/生成卡确定式/卡名映射；**回忆/附魔未接** |
| 培育侧 | 固定日程 + 选卡/删除规则（核心卡强保护）+ 商店花光 P 点 + 饮料 #19 禁 / #25 三条件门控 | 培育决策较简（课程硬打保分 A2 / 事件屏 A3）；商店/选卡策略未系统化 |
| 整局 | **H.I.F 本戦全自动完走**（实机多次，第 1 名） | 初 REGULAR-PRO 跑完 C/4242，T1 未验收；H.I.F 未跑 |

**可吸收（只按语义，用我们自己的主数据/参考引擎证据重验，不拷代码）**：
1. **回忆（メモリー）Stage 级限 1（按 base_id）**——我们 catalog 有 `MemoryAbility` 表，
   T5 剩余「回忆/附魔」可据此建模（需先核对我们主数据语义，不直接信其描述）。
2. **干劲经济守卫 / 免费再动安全优先**——候选搜索先验，进我们 A/B harness 验证后再谈
   （其 PBRS 负结果提示：先验要克制，纯分标签最稳）。
3. **B2 重训参考**：其「每战在线自适应」绕开了分布漂移（我们 B2 旧模型在 B3 规则下 FAIL
   的根因之一）；若重训仍不稳，可评估「按牌组聚类离线训练」或「在线微调」路线（T2 候选，
   60s/战训练预算需真机验证）。**纯分数标签、不加势能塑形**与其负结果一致。
4. **饮料门控**（#19 随机强化卡饮料禁选/禁买/自动弃；#25 双动饮料三条件：非 Legend Active
   在手 + 饮后可立即打出 + 承诺当回合打出）与**商店花光 P 点/强化优先**、**核心卡删除保护**
   ——我们培育侧策略（META_STRATEGY / produce driver）的候选规则。
5. **WinRT OCR**（系统内置 ja）作为 OCR 备选数据点（我们 A1 已选 PP-OCRv6，不切换）。

**他们也没有的**：seed/牌序全知（信息维度我们仍然唯一）；gkbench 公开榜单提交（同我们，
ranked 禁 seed 对其无影响——其算法本就只看 UI，**理论上可交榜单**，值得关注后续是否提交）。

## 6. 红线（许可证 / 安全）

- 仓库**无开源许可证**（GitHub API `license: null`；README 只写「Research / personal use.
  Game assets © Bandai Namco Entertainment.」）→ **默认版权保留，禁止拷贝/合并其代码、
  数据库、图鉴资源进本仓库**（比 BSD-3 的 gakumas-tools 更严；与 hiro AGPL 同列「只参考」）。
- 本文引用的算法/规则描述来自其公开交接文档，**吸收时必须用我们自己的主数据 + BSD-3
  参考引擎语义重新验证**（clean-room，ADR-007 同口径）。
- 不公开对比细节、不在群/公开仓贴链接或成绩截图（项目铁律）；其 B 站视频公开信息仅作内部情报。
- 其「禁止消耗ジュエル / 禁止リタイア / 完走自动停机 / 不开第二局」与我们
  `--ignore-user` / 墙钟上限 / 账号安全口径一致，可作执行层 checklist 对照（C1）。

## 7. 复现抓取（只读）

本机 `raw.githubusercontent.com` 不通（fetch failed），`api.github.com` 可直连：

```powershell
# 元数据 / 树 / 文件（base64）
Invoke-RestMethod https://api.github.com/repos/tactfullotto/auto-gakumas
Invoke-RestMethod https://api.github.com/repos/tactfullotto/auto-gakumas/git/trees/main
Invoke-RestMethod https://api.github.com/repos/tactfullotto/auto-gakumas/contents/demo/README_HANDOVER.md
# 解码：[Convert]::FromBase64String($r.content)
```

本次抓取快照存 `data/_intel_ag_*`（未跟踪，不入库）：README.md / demo_README_HANDOVER.md /
demo_README.md / manifest.json / produce_library.json。关键源码文件（未下载，仅树清单）：
`demo/sim/battle_simulator.py`（102 KB）/ `live_battle_planner.py`（44 KB）/ `rl_env.py`（24 KB）/
`maskable_ppo.py`（22 KB）/ `ismcts.py`（16 KB）。

## 8. 2026-11-25 更新（作者入群 + 产品化转向，lead 核实）

**身份链确认（群内）**：QQ **◇◇◇•（2073086895，11-25 新入群）= B站 nvtv（mid 6807581）= GitHub tactfullotto**。
17:35 其问"是谁要来讨论 MCTS 的"→ matto 认出视频作者 → 17:47 确认 → matto **17:54 邀其上传 gkbench"赛马"**
（"你的基底算法用的哪一块，有兴趣用 cli 上传和已有算法赛一下"）→ 其答"ppo+mcts，引擎见我的仓库，都是公开的"；
muskot"过下研究一下"、Ert'Aria"严肃研究中"。**§5 预言"理论上可交榜单、关注是否提交"→ 现已获 matto 明确邀请，
public-safe PPO+SO-ISMCTS 新算法即将上榜**（无 seed 阵营竞争加剧）。

**B站视频**：① BV1UNyXzREEf《学园偶像大师智能打牌控制台》（11-23 22:56，109s，简介指向仓库）；
② BV1xby6zDEW7《最新科研：[ガラクタロード] 姫崎莉波 一战》（**11-25 16:00 新发**，"实战效果"）——
从 11-23 的秦谷美鈴扩到**姫崎莉波**，多偶像泛化。

**新推送（11-23 基线 c29da9a 之后 4 次，sparse clone 核实 data/_auto_gakumas_latest，gitignore 不提交）**：
| commit | 日期 | 内容 |
|---|---|---|
| bcc069d | 11-23 | **H.I.F Workbench Web UI** + ProducePreferences + loadout 模式（auto/manual/hybrid） |
| 525fe4b | 11-24 | W1 奖励修复、**5 张手牌上限强制**、**anti-SKIP 剪枝** + Trouble 牌除外兜底、三语 README |
| 9669e67 | 11-25 | **P点"三明治法"OCR**（白描边数字抗 HUD 遮挡）、手牌动画稳定器、P-idol 数值 fallback、商店状态机、finisher 连击门控、workbench 卡过滤 |
| b738b7f | 11-25 | OCR 稳定器、商店状态机、finisher 门控、workbench 改进、测试扩充（298 passed/2 skipped） |

**核心算法/成绩未变**（zero-LLM、纯视觉 MuMu ADB、无 MITM/seed、每战在线 2000eps NumPy PPO + 64 次 SO-ISMCTS、
68 维信息集安全特征、HeadlessBattleSimulator 执行 gakumas-tools BSD-3 AST）；live7 2回戦 +1,594,997、eval30 477,670、
PBRS 负结果 −26,884 均同 §4。**新工作全在执行层可靠性 + 产品化**：
- **Web Workbench**（localhost:5000，三职业配置器 + 回忆编辑器 + 多维卡偏好过滤 + 实时 ADB 预览 + SSE 进度，
  免命令行）——**面向普通玩家的产品化**，印证用户判断"他们主轴是让普通玩家玩到，不是冲 seed 榜"。
- **finisher 连击门控**：#162/#163→#813/#814 仅在 goodConditionTurns≥13（或 OCR 遮挡+末 2 回合）触发。
- **手牌动画稳定**：读牌前等帧差均值<6.0（≤3 探测×0.85s），防抽牌动画误识。
- **anti-SKIP**＝我们硬规矩（有牌绝不 SKIP），双方独立收敛到同一规则。

**新增可吸收（clean-room，只语义不拷码）**：① P点三明治 OCR 抗遮挡（对照我们 PUBじ 色块→倍率多位坑）；
② 手牌动画帧差稳定等待（进 C1 tapguard/读牌守卫）；③ finisher 好調≥13 门控（培育/考试末段连击先验，A/B 验证）；
④ 商店访问状态机 + 花光 P 点（培育侧策略）。**许可证不变**：README"仅供个人研究使用"、无 OSS license → 禁拷码入库。