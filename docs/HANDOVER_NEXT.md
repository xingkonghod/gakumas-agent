# 交接清单：补什么 · 做什么（GDE / gakumas-agent）

> **这份文档是行动型交接**：`HANDOVER.md` 讲"发生过什么"，本文讲**接下来还缺什么、按什么顺序做、怎么验收**。
> **总顺序以 [WORKPLAN.md](WORKPLAN.md) 为准**（离线 A→B→C→D 全部做完 → 真机 E：T3→T1→T2 → gkbench F）。
> 新会话第一句话（紧凑版，2026-11-24 P1-8 完成后更新；完整版见 WORKPLAN「新会话开场白」）：
> 「工作目录 D:\Games\gakumas-agent，HEAD 以 git log -1 为准。读 docs/INDEX.md → docs/WORKPLAN.md →
> docs/HANDOVER_NEXT.md §2 跑基线（期望 ② 1644/1（1645 收集 / 99 文件）；①③④⑤ 同 B10 口径），不绿先修。
> Hindsight 记忆已停用（2026-11-24，因后台 qwen-plus/text-embedding-v4 走普通按量 key 烧阿里云余额；不用 hindsight_* 工具，跨会话上下文靠 docs 交接）。
> **按 §8.0 多会话路线图做**（用户确认 A 顺序：阶段1 离线补未知 → 阶段2 重采+练学生+新旧对比 →
> 阶段3 真机 → 阶段4 gkbench → 阶段5 收尾；每会话 1–3 任务，旧学生/老师数据模型全保留不覆盖）。
> **P1-8 已完成，下一任务先问用户**：阶段1 剩 P 道具后续批次（塔 gimmick/全力・强气效果卡打分/
> ExamParameterBuffReduce，证据充分需新机制/真机；日文好調の%分 ✅ P1-8），或直接进阶段2 重采+练学生 r11；
> P1-1 ✅（r10 探针 + 全力回合 + のんびり）、P1-2 ✅（handDecrease + pride）、
> P1-3 ✅（hold 保留区 + lockStanceTurns）、P1-4 ✅（nullifyDebuff 拦截 + ⑦ buff-cost/countDebuffs 评估 no-op）、
> P1-5 ✅（P 道具层数减少 + 好调回合 + 好调依赖换算，1067→1164/1849）、
> P1-6 ✅（T7②③ 纯函数状态重放 + 自动复盘页 + 标注转回归闭环，不改规则/不作废 B11 数据）、
> P1-7 ✅（好调增加量增加 + 元气增加无效 + 不安 + 通用延迟生效，1164→1179/1849）、
> P1-8 ✅（日文好調の%分 / 天生的才能，数据层日文换算源标注 sim/ 零改动，1179→1181/1849）；
> 旧路线图未完成项已全并入 §8.0。规则见 §4 硬约束。」
>
> 维护方式：完成一个任务 → 把对应状态改成 ✅（A 阶段在 WORKPLAN、T1–T8 在本文 §4）并在 §8 记一条；
> 本文档是 T1–T8 的"下一件事"真源，WORKPLAN 是总序列真源。

---

## 0. 十秒版

```
已完成：采集链路 / 牌序破解 / 完全信息搜索数据链路 / 生产接线接口（233e9d7）
         决策可观测性 + 出牌引擎接线 + T1 流程修复 + T3 实时接线代码（a9537b0/304d393）
         真机第一次完整跑完一局：期中 914/第3 → 最终 C/4242；20:55–22:20 七次短跑修掉 7 类卡点
         根因已定：课程"读不到价值 → 搜索建议 SKIP → 规则执行跳过"（C/4242 主因）
         已落地用户规则：**只有所有牌都付不起（真没体力）才允许 SKIP**（4b07fa7/8a2af2b/b231b3f）
         已落地用户规则：**bot 不许回退 rules**——搜索引擎失败 → [engine][BLOCKED] 中止本局，
         绝不静默改用规则；入口默认 expectimax（见 F#40，本次提交）
         上真机前模拟器整局 A/B 已绿：76 局 0 blocked / 0 异常 / C+率 100%（sim_engine_ab.py）
         真机防卡死：auto_produce --max-minutes（默认 30）超时主动停局，不再无限空转
         2026-11-22 A1：OCR 换官方 PP-OCRv6 多语言模型（Apache-2.0）——日文剧情/选项完整可读，
         下载脚本/配置/probe/测试齐全（见 HANDOVER 二·补十四）
         2026-11-22 A2：F#42 课程硬打必须得分——修掉课程 HUD 语义（右上=属性值、圆环=还差分）
         与「游戏默认每回合 1 张牌」两个模型错误；硬打先打正分牌（HANDOVER 二·补十五 / FAILURES #42）
         2026-11-22 A3：F#43 结果页空转——真根因是**日文饮料选择事件屏**（不是结果页）：中文 OCR
         读不出假名选项 + 飘字正则把 P 费标签「-100」当 +N → 点中央空转；修法与真机帧回放 7 条见
         HANDOVER 二·补十六 / FAILURES #43（提交 106ef2b / cdf7fca；复现脚本 scripts/probe_frame_decide.py
         + scripts/scan_event_frames.py）
         2026-11-22 A4：离线回放素材——8 张真机关键帧归档（tests/fixtures + README 溯源表）+ 9 条
         真机帧回放测试（六类关键屏，见 HANDOVER 二·补十七）+ scripts/scan_frames.py 批量挑帧工具；
         回放顺手抓到并修掉 _checkbox_bands 缺 @staticmethod 的真机 TypeError（F#44）
         2026-11-22 A5：T3 离线预演——scripts/verify_exam_plan_offline.py：最新场 3 候选第 2 回合锁定
         config_turns=12（真值 12），四场 sweep 全部 T1–T2 锁定且选对真值（候选→1、locked_turn≤3，
         见 HANDOVER 二·补十八 / EXPECTIMAX §④）
         2026-11-22 B1：T4 修正——查出评测执行器 `_execute_plan` 在「手牌打空自动结束回合」后又补
          SKIP、白丢下一回合的 bug；修正后 60 局配对 beam unknown 164.0 / known 165.5 vs within 143.1
          （+20.9/+22.4，CI 全正；决策门 114.6%/115.7% PASS）；受控 frontier 叶子中性；
          见 HANDOVER 二·补十九 / EXPECTIMAX「T4 修正」
         2026-11-22 B2：全知数据训练 MLP 叶子——beam 全知自对弈 26.5k 叶子样本（叶子状态分布 +
         on-policy 后续得分标签）→ 104 维 MLP（val r²=0.943）；B1 修正 harness 配对：选择段
         seed 2000–2079 beam 166.8→173.7（+6.8）/ensemble 174.4（+7.5）；确认段 seed 3000–3119
         （120 局）beam 157.8→165.5（+7.7 CI[+4.2,+11.2]）/ensemble 0.5 166.9（+9.0 CI[+5.8,+12.2]），
         known 同向；within 用 learned 变差 −3.3（负结果，只对 engine=beam 有益）；
         见 HANDOVER 二·补二十 / EXPECTIMAX「B2 学习叶子」
         2026-11-22 B3：T5 机制建模——模拟器对齐真机「每回合基础 1 张 + 打完自动结束回合 +
          SKIP 回 2 体力 + 取整 safeCeil」（gakumas-tools TurnManager/CardManager 证据 + 真机
          39 回合日志）；RULES_REFERENCE.md 重写为逐条核验表；真机回合规则配对回归
          （tests/fixtures/t5_exam_turn_rules.json + tests/test_t5_turn_rules.py 9 条）；
          重标定：sim_engine_ab 里 expectimax 显著强于 rules（+342~+429 评价点，B3 前噪声内）、
          B1 60 局 within 89.1→beam 95.7（+6.6，门 107.4% PASS）、B2 旧模型重测 FAIL 待重训；
          见 HANDOVER 二·补二十一 / RULES_REFERENCE / SIMULATOR §11
          2026-11-22 F 阶段数据 + F0 预检：用户登录 gkbench 并给命令行令牌 → 新增
          scripts/bench_download.py（公开 API + 令牌，断点续传）；下载 hif 80 run/36,350 条路线、
          329 题官方种子+check、505 题存档、两种榜单与参考分；用官方 check.hand 核洗牌模型
          **286/384=74.5%**（npc 按 stage：選抜 5、本戦 2；不一致根因=initial_add 自定义 +
          isInitial 变体）；见 HANDOVER 二·补二十二 / GKBENCH.md（数据在 data/bench_local/gkbench_dl/，gitignore）
          2026-11-22 F0 收尾 ✅：新增 scripts/verify_gkbench_shuffle.py（只读本地种子+主数据）——
          initial 按 base id（含强化变体）+ initial_add、**npc 按 idol 卡**（本戦 jsna 4 人制/fktn 2 人制/
          其余 3 人制）+ round 兜底；官方 check.hand **366/384=95.3% 精确 / 97.4% 逐张**（選抜 100%，
          逐题 311/329 全中；剩余 18 组全是考试开始加卡机制、无一洗牌错误）；起点校准
          turn=1/score=0/stamina 96.1%=starting_stamina/rules=55；见 HANDOVER 二·补二十四 / GKBENCH §4.5
          2026-11-22 B4（T5①）✅：审查倍率分段 + 联动惩罚——客户端真实公式（分数表分段折线 +
          审查基准联动惩罚 + 单精度取整）落地 sim/exam_multiplier.py + 主数据解析 data/exam_bonus.py；
          模拟器按回合属性乘（含依赖分/回合末好印象），生产搜索改用屏幕真实倍率（日志 attr=2.07）；
          真机采集局夹具期中 Vo/Da/Vi 4.09/2.20/2.60×、期末 6.97/2.85/4.96×；见 HANDOVER 二·补二十五 /
          RULES_REFERENCE §5.1 / WORKPLAN B4
          2026-11-22 B5（T5②）✅：熱意 + 温存解除——sim/enthusiasm.py 纯规则 + LessonSim/ExpectState
          熱意独立资源（集中之后加算、获得时 ceil、回合末清零/熱意延長）；温存解除 1 段 +5 /
          2 段 +8 熱意 +5 固定元気 + 解除当回合 +1 出牌次数（同回合可重复、温存→全力回合边界也触发）；
          卡牌熱意追加/増加/延長/本牌適用倍数 ×2 接入 sim_produce（MODELED_EFFECTS 29→32）与生产卡表；
          见 HANDOVER 二·补二十六 / RULES_REFERENCE §5.2 / WORKPLAN B5
          2026-11-22 B6（T5③）✅：P 道具数据接入——新增 src/gkagent/data/p_items_db.py（对局
          loadout.produce_item_ids → PItemSpec，未知/重复 id 显式上报、缺数据抛错）+ 新增 exam_start
          触发时机（288 段素材，LessonSim 构造时先于 turn_start 结算）与 ExamPlayableValueAdd →
          extra_plays（51 段，取 count 列）；LessonSim/ExpectState 镜像；local_bench 从 gkbench 题模板
          loadout 接入（--p-items auto/off，505 题/83 唯一 id/72 已知/11 未知）+ 提交适配器从
          ctx.loadout（公开配置、不含种子）接入；离线 A/B（hif 30 题×2 seed）greedy +128.9
          （+3.36%，CI[+9.5,+248.4]）/ expectimax +149.6（+3.98%）；见 HANDOVER 二·补二十七 /
          RULES_REFERENCE §5.3 / WORKPLAN B6
          2026-11-22 T9-B7 ✅：P 道具 47 条补全——build_p_items.py 合并本地中文 master 1068 +
          gakumasu-diff yaml 新增 47 → p_items.json **1068→1115 件 / spec 1764→1849 / 已实现
          421→445**；gkbench 505 题模板未知 id **11→0**（83 唯一 id 全已知）；新增 47 条卡名用
          仓库自译表、描述只有日文（显式标记 i18n_text_source="ja"）、条件未解析的 22 件记
          condition_known=False 且**保守不触发**；离线 A/B greedy 3840.7→3969.7（+128.9，
          CI[+9.5,+248.4]，与 B6 逐位相同——新道具目前 0 分贡献）/ expectimax 3732.0→3953.6
          （+221.5，CI[−71.4,+514.4]，墙钟抖动）；见 HANDOVER 二·补二十九 / RULES_REFERENCE §5.3
          全量 pytest 1054 passed / 1 skipped（1055 收集 / 76 文件）
未完成：① 还没跑出一局"不再乱跳 + 分数达标"的整局（上局 C/4242，期中不合格）
        ② 没做过同卡组真机 A/B（三引擎谁强不知道）
        ③ 采集进程 ↔ 决策进程**代码已接**、离线预演已通（A5），但真机跑局时采集没开 → 全知 0 锁定，差实战验收
        ④ 策略强度：B1 已推翻「beam 不如 within」的旧结论（B3 重测 within 89.1→beam 95.7）；
           B2 旧模型在 B3 规则下失效（确认段 −27.9）→ **B2-R 已重训（2026-11-23）：仍 FAIL
            （确认段 −7.2，ensemble 0.75 中性），学习叶子不进 T2 候选、生产保持关闭**。
           剩余：T5 机制（~~审查倍率分段+联动惩罚~~ ✅ B4 已完成、~~熱意~~ ✅ B5、~~温存解除额外次数~~ ✅ B5、
           ~~P 道具数据接入（离线 loadout 侧）~~ ✅ B6；~~P 道具 47 条补全/未知 id~~ ✅ B7；
           剩 fresh buff 差一回合（需真机截图）+ P 道具条件/效果语义 + 真机培育侧列表）
        ⑤ 分数/费用 OCR 仍需用新截图校准（已加回退原因日志：complete/nodes/ms、CardSpec 失配）
        ⑥ A4 缺一张真机帧：「回合结束确认框」旧截图被 step_NNN 轮转覆盖（扫 1352 张 0 命中）；
           分支已用真机课程帧文字 + F#36 文案回放，下次真机跑局出现时补拍 fixture
         ⑦ ~~F0 收尾~~ ✅ 2026-11-22 已完成（366/384 + 起点校准；剩余 18 组=考试初始牌组/开局加牌，
            见 GKBENCH.md §4.5 / HANDOVER 二·补二十四）
          ⑧ ~~T5① 审查倍率分段+联动惩罚~~ ✅ 2026-11-22 已完成（公式/主数据/屏幕倍率接线 + 21 条测试；
            真机逐分回放仍差 P 道具附魔/生成卡等未建模项，见 RULES_REFERENCE §5.1）
          ⑨ ~~T5② 熱意 + 温存解除额外次数/元气~~ ✅ 2026-11-22 已完成（独立熱意资源 + 温存解除
            +5/+8、固定元気+5、+1 出牌次数、回合末清零/延長、卡牌熱意追加/増加/延長/適用倍数接入 +
            16 条测试；のんびり/全力額外次数/P 道具来源未建模，见 RULES_REFERENCE §5.2）
          ⑩ ~~T5③ P 道具数据接入~~ ✅ 2026-11-22 已完成（loadout → PItemSpec；exam_start +
            ExamPlayableValueAdd→extra_plays；local_bench/提交适配器接线 + A/B + 29 条测试；
            剩余效果覆盖 421/1764 段、真机培育侧列表、主道具附魔，见 RULES_REFERENCE §5.3）
          ⑪（2026-11-22 外部情报）**作者四游戏整合启动器包**（用户提供，215 MB，11-22 构建）已解包
            静态分析 → [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)（提交 `ddf221f`）；
            带来候选任务 **T9**（B7 P 道具 47 条补全 / C0 采集更新可靠性经验吸收 / E0 离线培育
            测试台实验，见 §4）；**B7 已于 2026-11-22 完成**（p_items 1068→1115、gkbench 未知
            id 清零、A/B 记录，见 HANDOVER 二·补二十九）；**C0 也已完成**（2026-11-22，排障判据
            进 TROUBLESHOOTING §四 + CAPTURE_PIPELINE 更新后自检，纯文档不改代码，见 HANDOVER
            二·补三十）；T9 只剩 **E0**（需独立副本 + 用户配合）。
          ⑫ ~~T5④ P 道具条件/效果语义（第一批）~~ ✅ 2026-11-22 完成（**B8**）：新语法 trigger id
            结构化解析（条件未知 22→6 件）+ 依赖换算「X 的 N% 数值变为 Y」（65 段）+ 固定/百分比
            体力（9 段）+「X 变为 0」（3 段）+ 5 类新触发时机；数据层 **445→676/1849 段**、
            gkbench 已实现 **34→59/153 段**；greedy 配对 A/B **+225.2（CI [+86.7,+363.6]）**；
            全量 pytest **1067/1（1068 收集 / 77 文件）**；见 HANDOVER 二·补三十一 / RULES_REFERENCE §5.3。
            剩余：持续倍率类 `ExamLessonValueMultiple`、生成卡、modifier 类、指定卡名/手牌限定。
          ⑬ ~~T5④ P 道具持久倍率 / modifier 类效果（第二批）~~ ✅ 2026-11-22 完成（**B9**）：
            20 类 target / **369 段 / 298 件道具**——打分上升量增加/减少（`resolveScore` f/g，
            加算列表 + 回合末倒计时）、好印象强化/追加发动、热意/集中/好印象/干劲/全力值
            增益倍率、绝好调/不调、费用修正（永久加减 + 接下来 N 回合 ×0.5/×2）、回合追加、
            温存/强气指針直给；同时解析描述里的「（训练内N次）」→ max_uses **9→896 件**
            （修正 B6–B8 期生效效果可无限触发的口径）；数据层 **676→1025/1849 段**
            （no-op 1173→824）、gkbench **59→103/153 段**；`LessonSim`/`ExpectState` 新字段 +
            canonical + 双镜；新增 `tests/test_p_items_b9.py` 49 条；greedy 配对 A/B
            **+110.3（+2.87%，CI [+39.6,+193.3]，20胜/2负/38平）** / expectimax +156.2（CI 含 0）；
            全量 pytest **1116/1（1117 收集 / 78 文件）**；基线 ①③④⑤ 不变。
            见 HANDOVER 二·补三十二 / RULES_REFERENCE §5.3。**仍保持 no-op**：
            `ExamBuffConsumptionAdd`（强化状态花费卡机制不在模型里）、`ExamCardCreateId` 生成卡、
            指定卡名/手牌限定（见 RULES_REFERENCE §5.3 B9 如实记录）。
          ⑭ ~~T5 剩余机制①② 生成卡 + 指定卡名/手牌张数映射~~ ✅ 2026-11-23 完成（**B10**）：
            新 card_meta（idol_unique 判据 originIdolCardId/originCharacterId，与参考引擎
            pIdol 交叉验证 **340/342、0 误报**；effect_groups 取卡面 effectGroupIds；日文别名）
            + `parse_card_search`（play_filter 234 件 / zone_count 27 件：指定卡名 base id
            不限强化 / 偶像固有 / 效果组 / 原本费用 / 类别 / 稀有度 / 四区张数含取反）
            + `ExamCardCreateId` 确定式生成卡 **11 段**（手牌≥5 不生成 / 牌堆顶 / 弃牌堆，
            参考 addCardTo* 语义；生成卡 id 与参考 DSL 交叉验证）+ `exam_start_after` 新时机
            + **次数上限按道具计**（limit:N 口径修正，多段道具不再提前用完）；
            触发未知 **103→3 件 / 185→6 段**（hold 保留区 2 + hotfix 1）、条件未知 **6→0**；
            数据层 **1025→1042/1849 段**；gkbench 103/153 段（loadout 4 件/8 段原 trigger
            未知道具现在真实触发）；greedy 配对 A/B **+797.5（+20.76%，CI [+399.0,+1250.1]，
            31胜/3负/26平）** / expectimax **+801.1（CI [+66.3,+1697.9]）**；
            新增 `tests/test_p_items_b10.py` 38 条；全量 pytest **1154/1（1155 收集 / 79 文件）**；
            基线 ①③④⑤ 不变。见 HANDOVER 二·补三十三 / RULES_REFERENCE §5.3。
            **仍保持 no-op**：`ExamBuffConsumptionAdd`（强化状态花费卡，不猜）、
            **随机生成卡**（H.I.F应援棒 6 段 / gkbench 172 段权重，考试 RNG 流未知）、
            hold 保留区张数条件（2 件，保留区未建模）。
           ⑮ **B2 按 B3+ 规则重训（B2-R）** ✅ 2026-11-23 完成（**可复现负结果；高预算验证后路线关闭**）：
             旧模型 FAIL 复现（−26.1，与 B3 重测逐位一致）；2000 叶子快照 vs end_turn_state
             逐字段等价探针 + 温存→全力回合边界解除收益快照口径修正（+1 回归测试）；
             重采 26,500 beam 全知叶子样本（纯分数标签、不加 PBRS 塑形）→ MLP val r²=0.906/MAE 7.0；
             确认段 120 局 unknown beam 94.9→learned **87.7（−7.2 CI[−9.5,−5.0]）** / known −11.5 /
             ensemble 0.75 中性；σ×2/×4 更差（μ 排序本身有害）。**高预算验证（width8/300ms
             选择段 80 局）也 FAIL：93.9→89.4（−4.4 CI[−8.8,−0.0]）/ ens 0.75 中性；收窄主因是
             解析式基线自己变差（97.3→93.9），learned 绝对分几乎不动 → 学习叶子路线关闭**。
             **生产 leaf_model 保持关闭、beam 默认解析式叶子、T2 候选去掉 learned leaf**；
             重训候选保留 out/，tracked 模型按用户指定回退旧版；根因诊断已完成：锐利 σ 放大 +
             价值-策略失配（EXPECTIMAX B2-R·根因诊断/高预算验证）。**下一步转 C1**（用户指定）。
             pytest **1155/1（1156 收集 / 79 文件）**；基线 ①③④⑤ 不变。
             见 EXPECTIMAX「B2 重训（B2-R）」/ HANDOVER 二·补三十四/三十五。
           ⑯ **C1 执行层可靠性** ✅ 2026-11-23 完成（用户指定；纯离线代码+单测，真机验收留阶段 E）：
             新 runtime/tapguard.py（TapExpectation 动作前预算下一帧 + TapGuard 互验：
             confirmed / moved 不重试（rev254）/ 同屏 retap≤2 / lost 上报绝不静默 SKIP /
             加载暂停帧 postpone；PickerGuard 两段式选牌：选中后只重试确认不重点卡位）
             + device/privilege.py（游戏 elevated/本进程 non-elevated → UIPI 静默丢点击，
             启动 blocked 拒跑 + elevation-blocked failure + 管理员提示）
             + runtime/trace.py（StepTrace 每步 reason/预算/互验结果）+ scripts/replay_steps.py
             离线复盘 CLI；produce_ui.decide() 每击自动预算（弹窗确认/回合结束「是」/通信错误
             =dialog-gone）+ card-reward 接 PickerGuard；auto_produce 接 tap 互验
             （连续 3 次 lost 止损停局）+ attempt_drink（对话未开重试槽位≤2，失败留痕）
             + 每步 data/step_trace.jsonl + 局末 [tap] 汇总。参考 GKMSMAA 架构自写不拷贝（AGPL）。
             新增 4 测试文件 68 条；pytest **1223/1（1224 收集 / 83 文件）**；基线 ①③④⑤ 不变。
             见 WORKPLAN C1 / HANDOVER 二·补三十六。
           ⑰ **B11 渐退式专家迭代 第 1 轮** 🟡 2026-11-23 完成（用户选定启动；纯离线代码+单测；
             **确认段评测门 PASS → 按设计放手**）：学 policy/advantage 而非状态价值（绕开 B2-R
             价值-策略失配根因）——新 sim/policy_mlp.py（137 维=B2 104 状态特征+33 动作特征 →
             96→48→1 优势分；net_action 编码硬规矩：有牌绝不 SKIP、无静默回退）+
             sim/policy_data.py（决策记录 + **精确重放分支** on-policy 优势标签：同 seed 重放
             前缀逐字段全等校验 → 打候选牌 → 当前学生打完 → A=R−mean(R)，不走搜索镜像）+
             build_ei_dataset.py / train_ei_policy.py / eval_ei.py；eval_known_draw.play 加
             net/greedy 分支（默认逐位不变）。示范 400 局 5747 样本（beam width4/100ms+tiebreak，
             unknown）→ v0 BC（val 排序命中 0.889）→ v0 自对弈 1000 局 14314 优势样本 →
             v1 70/30 混合（教师占比 0.300）。**确认段 120 局（seed 3000–3119）v1 97.5 vs
             教师 94.9：Δ=+2.6 CI[+1.1,+4.1] 显著正 → PASS**；稳健块 4000–4119 +3.8
             CI[+1.6,+6.0]；学生 0.40ms/决策（纯策略无搜索）。**消融（如实）**：纯 BC v0 也过门
             （+2.4 CI[+0.7,+4.1]），v1−v0=+0.2 不显著 → 第 1 轮红利主力=逐决策蒸馏+硬规矩禁跳
             （教师每回合规划一次会过期/提前 SKIP），on-policy 优势成分方向正但未独立证明。
             新增 28 条测试；pytest **1251/1（1252 收集 / 84 文件）**；基线 ①③④⑤ 不变。
             生产接线未做（T2 候选暂不变）；模拟器保真度是天花板、large 未测、真机 T2 才算数。
             见 EXPECTIMAX B11 / WORKPLAN B11 / HANDOVER 二·补三十七。
            ⑱ **B11 渐退式专家迭代 第 2 轮** 🟡 2026-11-23 完成（用户选定；纯增量代码+单测；
             **平台期 CONTINUE + large 泛化缺口**）：教师←v1（build_ei_dataset --teacher-net
             逐决策示范，教师 SKIP 剔除恒 0）、eval_ei --baseline-net（门基线=上一轮学生，
             beam 臂保留作绝对水位）、train_ei_policy --round；默认行为逐位不变。
             v1 示范 400 局 5773 样本（seed 400000+）+ v1 自对弈 1000 局 14526 优势样本
             （seed 300000+）→ v2 85/15（17089 样本，占比精确 0.150）+ 消融 v2_bc（纯自蒸馏）。
             **small 确认段 120 局 v2 97.9 vs v1 97.5：+0.4 CI[−0.4,+1.2] → CONTINUE**；
             选择/稳健 4000/新鲜块 5000（两轮未触碰）四段全中性（98/120 局逐位相同）；
             消融 v2_mix−v2_bc=+0.54 CI[−0.40,+1.48] → on-policy 成分连续两轮方向正、
             未独立证明；纯自蒸馏中性。**large 首测（31 张/9 回合）**：v1 比 beam −28.1
             CI[−36.0,−20.2]（277.2 vs 305.3，CLEAR 36.7% vs 53.3%），v2 比 v1 还略差
             （选择段 −14.8 显著）→ small 训练不泛化 large；两学生仍显著强于 greedy。
             绝对水位 v2−beam small +2.99 CI[+1.37,+4.62]；beam 参照臂与 r1 逐位一致、
             large 复核逐位复现。**处置：占比不降（保持 0.15）、生产接线未做、T2 候选不变**。
             新增 15 条测试；pytest **1266/1（1267 收集 / 85 文件）**；基线 ①③④⑤ 不变。
             见 EXPECTIMAX B11 第 2 轮 / WORKPLAN B11 / HANDOVER 二·补三十九。
            ⑲ **B11 r3–r8 继续扶 + 门协议修正** 🟡 2026-11-23 完成（用户指令「显著强于
             老师才结束」；纯增量代码+单测）：六轮换变量（新学生数据/数据×10/epochs×3/
             容量×2/ε-greedy 探索 --explore-eps 两体量），val 排序饱和 0.862，确认段 3000
             七轮恒 +0.2~0.6（**种子段结构，非模型问题**）；探索变量中性（覆盖假设否证）。
             **门协议修正（用户批准）：确认段扩 500 局 3000–3499、判据不变 → v6 98.6 vs
             v1 98.1：+0.6 CI[+0.2,+0.9] PASS**；新鲜块 6000 +1.7 CI[+0.6,+2.8] 独立佐证；
             池化 820 局 +0.71 CI[+0.40,+1.02]（W/L 101/41）。**v6（192×96）= 当前最佳学生，
             显著强于 v1**。large 泛化显著改善（v6 291.6 vs v1 277.2：+14.4 CI[+6.5,+22.2]，
             vs beam 缺口 −28.1→−13.7）但仍低于 beam；生产接线仍未做。
             新增 7 条探索测试；pytest **1273/1（1274 收集 / 86 文件）**；基线 ①③④⑤ 不变。
             见 EXPECTIMAX B11 r3–r8 续 / WORKPLAN B11 / HANDOVER 二·补四十。
            ⑳ **B11 v6 生产接线** ✅ 2026-11-23 完成（用户授权综合推荐后选定；纯增量代码+单测；
             **opt-in，默认逐位不变**）：`LessonPolicy(engine="net", net_model=…)` 在可观测状态
             可出牌里 argmax 优势分（无搜索）；`with_plan=False` 不注入采集全知（public-safe）；
             硬规矩有牌绝不 SKIP / 全付不起才 SKIP；缺模型/推理异常/失配 → RuleFallbackBlocked
             （禁回退 rules）；`eng=net` + 优势分进 reason；auto_produce `--net-model` >
             `produce.net_model` > 默认入库 v6（`data/knowledge/ei_policy_v6.json`，tracked，
             gate 溯源 meta），缺模型起跑前 return 2；T2 增第四臂 `--engine net`
             （large 生产候选仍是 beam，net 值不值由真机 A/B 定）。21 条新单测；
             pytest **1294/1（1295 收集 / 87 文件）**；基线 ①③④⑤ 不变。
             见 EXPECTIMAX「B11 v6 生产接线」/ WORKPLAN B11 / HANDOVER 二·补四十一。
            ㉑ **B11 r9-large（small+large 混合训练）** 🟡 2026-11-23 完成（用户授权安排；
             **large 主门 PASS 且首超 beam，small 护栏 FAIL → 复合门未过，不入库**）：
             `train_ei_policy --selfplay/--demos` 多文件纯增量（单文件 sha256 逐位不变 +
             12 条回归测试）；large 自对弈 5000 局 126969 样本（v6 学生，seed 900000–904999）+
             small r5 全量 145605 + 示范 48101（补采 v1 1600 局解锁 0.15 上限）= 320675 行，
             192×96/1200ep 全同 r6。**large500 r9 315.4 vs v6 285.8：+29.6 CI[+26.2,+33.0] PASS；
             vs beam 301.3 +14.2 CI[+10.9,+17.5]（首个 large 超 beam 学生网，CLEAR 62.6% vs 50.6%）**；
             新鲜块 6000 +24.0 佐证。**small500 r9 98.2 vs v6 98.6：−0.42 CI[−0.67,−0.17]
             显著回退**（池化 580 −0.47；vs v1 +0.16 不显著，原门未保持）→ 不入库，
             生产 ei_policy_v6.json 保持 r6 权重；r9 留 out/ei_r9_v9_mix.json 作 large specialist
             （T2 可 --net-model 换臂）。诊断假设：全局 std 稀释 small 信号（18.71 vs 12.21 → 65%）
             + v1 示范拉扯；候选修复=按场景 std 归一化（r10，先问用户）。12 条新单测；
             pytest **1306/1（1307 收集 / 88 文件）**；基线 ①③④⑤ 不变。
             见 EXPECTIMAX B11 r9-large / WORKPLAN B11 / HANDOVER 二·补四十二。
             ㉒ **B11 r10（按场景 std 归一化）** 🟡 2026-11-23 晚完成（用户选定；
             **small 回退收窄 39% 但仍显著、large 增益保持 → 复合门未过，不入库**）：
             `train_ei_policy --norm-by-scenario` 纯增量（默认关=逐位不变：4 参照 sha256
             改前/改后一致；多文件各文件按自身 std，scenario 取 npz meta.args.scenario，
             mix/meta 记逐场景 std；单文件/demos 不受影响）+ 12 条回归测试。复用 r9 数据
             320675 行重训（单变量=归一化口径：small std 12.2115 / large 24.0878 vs 全局
             18.7065）；能量份额 small 20.9%→**49.0%** / large 70.9%→**42.7%**（预测吻合）。
             **large500 r10 314.9 vs v6 285.8：+29.1 CI[+25.8,+32.3] PASS，vs beam +13.6
             CI[+10.3,+16.9] 仍超**（r10−r9 同 seed 中性 → 增益保持）；新鲜块 6000 +23.0。
             **small500 r10 98.38 vs v6 98.64：−0.256 CI[−0.500,−0.012] 仍显著回退**
             （池化 580 −0.267 同显著；**vs v1 原门恢复 +0.322 CI[+0.032,+0.612]**；
             CLEAR 12.2%==v6）→ 不入库，生产保持 r6 权重；r10 留 out/ei_r10_v10_mix.json。
             **归一化修复有效但不充分**（输入侧场景漂移仍在，R9_ANALYSIS §8 证实）。
             12 条新单测；pytest **1318/1（1319 收集 / 89 文件）**；基线 ①③④⑤ 不变。
             见 EXPECTIMAX B11 r10 / R9_ANALYSIS §8 / WORKPLAN B11 / HANDOVER 二·补四十三。
            ㉓ **P1-1 阶段1 首批：r10 行为探针 + 全力回合 + のんびり指針** ✅ 2026-11-24 完成
             （用户确认 A 顺序首批；纯离线规则+探针，BSD-3 有据）：
             **探针**（R9_ANALYSIS §9）：残留 small 回退 −0.256 **已非 v1 风格贪即时分**
             （首分歧贪即时分偏置 r9 24:9 → r10 11:8；对 v1 耐心比 25:11 恢复 v6 水平 29:13；
             CLEAR 翻转 1:1 对称）→ 无方向漂移噪声（通道 2），r11 small 上采样仍对症。
             **规则**：全力回合 +1 出牌（连续全力每回合）/保留牌回手钩子（held 来源留 P1-3）/
             全力期间禁切指針；のんびり ×0（分数/费用）+ 解除（元気+5/次数+1/熱意+10，
             →全力 = 全体卡打分成长+10）+ 温存→のんびり不触发温存解除 + のんびり禁温存；
             来源 = 4 族卡 ExamOverPreservation 预约（CSV 逐卡证据表）+ P 道具 stance_leisure
             直给（2 件标注，card_play_interval_after 触发未支持仍保守不触发）；
             LessonSim/ExpectState 双镜 + canonical/快照/叶子对齐；release 扩 4 元组。
             **评测牌组组成不变**（のんびり卡 score 0/SSR/Legend 本就不进池）→ sim_engine_ab
             重标定**改前/改后 64 局逐位相同（差异=0**；expectimax 仍显著强于 rules）；
             旧 B11 数据/模型旧规则口径全保留。36 条新单测；
             pytest **1354/1（1355 收集 / 90 文件）**；基线 ①③④⑤ 不变。
             见 RULES_REFERENCE §5.4 / R9_ANALYSIS §9 / WORKPLAN P1-1 / HANDOVER 二·补四十四。
             ㉔ **P1-2 阶段1 第二批：handDecrease 抽牌修正 + pride 自尊** ✅ 2026-11-24 完成
              （用户确认 A 顺序；纯离线规则，BSD-3 有据）：
              **④ handDecrease**：cardsToDraw=max(3−Σ,0)（TurnManager.startTurn +
              BuffManager.setHandDecrease/getHandDecrease；timed 列表合算/倒计时/∞永久；
              只减回合开始抽牌、卡效果抽牌不受影响，wiki buffs.json 口径）；来源=塔 gimmick
              ExamGimmickStartTurnCardDrawDown 12 段（exam_start，手牌减少1∞回合）；
              nullifyDebuff 拦截未建模如实记（ExamAntiDebuff 本就 no-op）。
              **⑤ pride**：resolveScore f min(好印象,干劲)×0.02 上限+0.5（千分比 min×20/500，
              与 score_buffs 累加后一次乘；prideTurns 回合末 -1；score>0 门）；**来源离线可确定**
              （主数据+参考 DSL 交叉，pIdol 117/118=雨夜燕）：卡「我、绝不」p_card-02-ido-3_140
              turn=5 ↔ skill_cards.csv 632/633 prideTurns+=5，条件门出牌前干劲>=9
              （trigger …aggressive_up-9 结构化解析，未知 trigger 保守不给）+ P 道具「一笔入魂」
              pitem_02-2-117-0/1 turn=2/3 + 干劲+4/5 ↔ p_items.csv 354/355
              at:motivationIncreased{if:isDirectEffect & goodImpressionTurns>=6; limit:1}。
              **落地（纯增量）**：lesson.py/expectimax.py（hand_decreases/pride_turns 双镜 +
              canonical + 快照往返 + 叶子对齐 + beam 下一手 turn_draw_count）+
              p_items.py（hand_decrease/pride_turns target + PItemDelta）+
              CardSpec.pride_turns/pride_min_motivation（sim_produce MODELED 33→34、35 元组；
              play_choice + pride_min_motivation_from_trigger）+ p_items.json 重标注
              （modifier 371→385，implemented **1042→1056/1849**，仅 14 条记录标注变化）。
              **评测牌组/gkbench loadout 组成不变**（自尊卡 score 0/SSR 不进池；688 loadout /
              94 唯一 id 无 117/tower）→ sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，
              expectimax 仍显著强于 rules Δ+372.2/+219.1）；旧 B11 数据/模型旧规则口径全保留。
              36 条新单测（+既有断言随规则更新：MODELED 34 / no-op 参数表）；
              pytest **1389/1（1390 收集 / 91 文件）**；基线 ①③④⑤ 不变。
              见 RULES_REFERENCE §5.5 / WORKPLAN P1-2 / HANDOVER 二·补四十五。
             ㉕ **P1-3 阶段1 第三批：hold 保留区建模 + lockStanceTurns 指針固定** ✅ 2026-11-24 完成
              （用户确认 A 顺序；纯离线规则，BSD-3 有据）：
              **⑥ hold 保留区**（CardManager hold/enforceHoldLimit/holdThisCard/holdSelected/
              moveHeldCardsToHand）：上限 2（超限最旧进弃牌堆）/跨回合保留（endTurn 只弃手牌）/
              holdThisCard 本牌不进弃牌除外/holdSelected 从 hand/deck/deck_grave 选牌
              （known_draw/discard_order 同步）/moveHeldCardsToHand **LIFO** 回手；
              主数据 ExamCardMove（values 恒空）→ **13 族卡逐卡证据表** hold.HOLD_SOURCES
              （skill_cards.csv 行号交叉：冲刺/积累 holdThis 温存中、潜在能力/互动的基础
              holdSelected[hand]、切磋琢磨/觉悟/新的舞台/努力了，哦/那一天，在这里（+2张）/
              对战请多指教！/让群星散落吧 holdSelected[deck|grave]、爱意彩虹 holdSelected[deck]、
              一点一滴的进步 moveHeldCardsToHand）；**表外卡保留旧 +1 抽牌近似**（潮流领袖/
              展翅高飞/发挥本领/决不停歇：全力值消耗/holdSelectedUpto/target:held 成长/
              干扰卡计数未建模，不猜）。**lockStanceTurns**（切磋琢磨 StanceLock turn=1 ↔
              DSL 424/425）：EOT 递减 + **fresh 保护锁下一回合** + setStance 守卫 + 全力进入门
              （lockStanceTurns==0，全力值不消耗）；再演翻倍。**B10 遗留 trigger_unknown 3 件清零**：
              hold 区张数条件（实现的觉悟/± countCards[held]>=1 ↔ 叶える覚悟 pIdol 74）+
              hotfix（咲季营养餐・改 period810_hotfix **三源证实非限定标记** ↔ 咲季の完全食・改
              csv 404）；**温存 2 段階直给 preservation2**（7 段重标注）。
              **落地（纯增量）**：新 sim/hold.py + stance.py locked 守卫 + lesson.py/expectimax.py
              （_apply_hold(_state)/lock+fresh 双镜 + canonical + 快照往返 + 叶子 LIFO）+
              p_items.py（PassiveState.held + zone_count held + preservation2）+ build_p_items.py
              （hold→held + period810 白名单）+ sim_produce MODELED 34→35（StanceLock）/41 元组 +
              play_choice 同口径 + p_items.json 重建（仅 9 条记录变化，逐条 diff 校验）。
              implemented 保持 **1056/1849**（机制本就支持，触发保守不解析→现在真实触发）。
              **large 评测牌组组成变化**（冲刺/积累 draw 近似移除 → 抽牌签名槽改选决不停歇；
              保真度修正，旧近似把保留当抽牌是高估；**small 不变**）→ sim_engine_ab 重标定
              改前/改后 64 局逐局对照（见 §8 最近交接）。旧 B11 数据/模型旧规则口径全保留。
              46 条新单测（+既有断言随规则更新：MODELED 35 / 41 元组 / trigger_unknown 0 /
              preservation2 / large 牌组）；pytest **1435/1（1436 收集 / 92 文件）**；基线 ①③④⑤ 不变。
              见 RULES_REFERENCE §5.6 / WORKPLAN P1-3 / HANDOVER 二·补四十六。
             ㉖ **P1-4 阶段1 第四批：nullifyDebuff 低下状态无效拦截 + ⑦ ExamBuffConsumptionAdd /
              countDebuffs 评估** ✅ 2026-11-24 完成（用户确认 A 顺序；纯离线，BSD-3 有据）：
              **nullifyDebuff 拦截**（P1-2 遗留；Executor executeAssignment :429 / executeCallAction
              :507 / executeSpecialAction :545：nullifyDebuff>0 拦截一次 debuff 施加并 -1；
              DEBUFF_SPECIAL_ACTIONS = setScoreDebuff/decreaseFullPowerCharge/setHandDecrease；
              消耗式计数器无回合倒计时）：LessonSim/ExpectState.nullify_debuff + canonical +
              快照往返 + intercept_debuff_entries 纯函数，拦截已建模的 setScoreDebuff/setHandDecrease
              （列表逐条，顺序 score_debuffs→hand_decreases）。**来源 P 道具侧** ExamAntiDebuff
              values.count 11 段（偷懒的毛巾 pitem_00-2-116-0 ↔ p_items.csv 317 + 塔 gimmick 10 段）。
              **⑦ ExamBuffConsumptionAdd 保持 no-op**（doubleBuffCostTurns 语义/主数据 4 段/
              gkbench 22 loadout 如实记；卡模型不承载 buff 花费——88 张参考 buff-cost 卡
              card_table cost=0、CardSpec 无 buff_cost 字段，无落点不猜）。**countDebuffs 无落点**
              （低下状態の数参考+主数据零使用）。卡侧 4 SSR 族来源（values 恒空）/标量
              DEBUFF_FIELDS 拦截/decreaseFullPowerCharge 留后续。implemented **1056→1067/1849**
              （+11，modifier 385→396，p_items.json 仅 11 条记录变化）。评测零落点 →
              sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）。30 条新单测（+test_p13
              implemented 断言更新）；pytest **1465/1（1466 收集 / 93 文件）**；基线 ①③④⑤ 不变。
              见 RULES_REFERENCE §5.7 / WORKPLAN P1-4 / HANDOVER 二·补四十七。
             ㉗ **P1-5 阶段1 第五批：P 道具剩余效果语义补全 bounded batch（层数减少 + 好调回合 +
               好调依赖换算）** ✅ 2026-11-24 完成（BSD-3 + DSL 三重核实；详见 §8 交接记录）：
               implemented **1067→1164/1849**（+97）、依赖换算 65→76；sim_produce 不引用 p_items →
               评测零 P 道具结算，sim_engine_ab 改前/改后 64 局差异=0；38 条新单测，pytest
               **1503/1（1504 收集 / 94 文件）**；留后续（需新机制，no-op 如实记）：好调增加量增加/
               元气增加无效/不安/塔 gimmick/全力・强气效果卡打分/日文好調の%分。
               见 RULES_REFERENCE §5.8 / WORKPLAN P1-5 / HANDOVER 二·补四十九。
             ㉘ **P1-6 阶段1 第六批：T7②③ 离线可靠性工程（纯函数状态重放 + 自动复盘页 +
               标注转回归闭环）** ✅ 2026-11-24 完成（用户确认 A 顺序；**不改考试规则、不作废 B11 数据**）：
               ⑨ 新 `data/run_replay.py`（apply_event 纯函数/深不可变 RunState/同观测序列两遍重放
               指纹逐位相等/compare_replays 逐步比对首个分歧步/legacy_events 旧格式确定式重建/
               consistency_check 三方对账）+ RunRecorder 增量 events 观测日志（旧文件续跑先重建）+
               `scripts/replay_run.py`（--verify/--compare，退出码=DoD）；⑩ 新 `report/review_page.py`
               自包含 HTML（逐回合/考试/结算/重放一致性/观测日志/C1 逐步轨迹/行内标注导出导入，
               全量转义+内嵌 JSON 防逃逸）+ `report/annotations.py`（verdict=bad 带 expected →
               整态/分类结论**冻结**进 tests/fixtures/review_regressions.json）+
               `scripts/review_page.py`/`scripts/annotations_to_regression.py`；auto_produce 局末
               自动生成（[review]，best-effort 不影响收尾）；样例页 docs/review_sample.html
               （ep-rule1 真实记录 + 合成演示轨迹显著标注）；ep-t1-g 真实卡屏 28 次重复观测被
               重放显式 surfaced。**sim/ 零引用新模块 → 评测零影响、无需重标定**；61 条新单测
               （38+20+3），pytest **1564/1（1565 收集 / 97 文件）**；基线 ①③④⑤ 不变。
               见 WORKPLAN P1-6 / LIVE_RUN §2.1 / HANDOVER 二·补五十。
 当前最高优先：**按 §8.0 多会话路线图推进**（用户 2026-11-23 晚确认 A 顺序：先补离线规则→重采→
练学生→真机→网站；每会话 1–3 任务；旧学生/老师数据模型全保留，新批练出来再新旧对比；
旧路线图未完成项已全并入 §8.0）。r10 后 small 仍显著回退（−0.256 CI 上界 −0.012）→ 复合门未过、不入库；
**P1-1 探针判定残留回退已非 v1 贪即时分（通道 2 漂移噪声）→ r11 small 上采样仍是对症变量**。
→ **P1-6 已完成，下一任务先问用户**：阶段1 剩 P 道具后续批次（证据充分需新机制），或直接进阶段2 重采+练学生 r11；
阶段1 离线补未知（~~全力/のんびり/r10 探针~~ ✅ P1-1；~~handDecrease/pride~~ ✅ P1-2；~~hold/lockStanceTurns~~ ✅ P1-3；~~nullifyDebuff/⑦ buff-cost/countDebuffs 评估~~ ✅ P1-4；~~P 道具层数减少/好调回合/好调依赖换算~~ ✅ P1-5；~~T7②③ 纯函数状态重放/自动复盘页~~ ✅ P1-6；剩 P 道具后续批次）→
阶段2 重采+练学生 r11（small 上采样，双过入库）+新旧对比 →
阶段3 真机 T3→T1→T2（+T6/D1 补采 + E0 + C1 真机验收）→ 阶段4 gkbench F1/F2 → 阶段5 收尾 G。
T5 剩余里需真机数据的（RNG 流/fresh buff/附魔/真机 P 道具列表）留阶段3。
**另**：用户 2026-11-22 指定「开新对话做」候选任务 **T9**（§4；一次会话只做 1 个；
 B7 ✅ / C0 ✅，剩 E0 需真机/独立副本实验）。
（总计划见 WORKPLAN.md；阶段 A 全部完成、B1/B2/B3/B4/B5/B6/B7/B8/B9/B10/C0/F0 已完成、
B11 渐退式专家迭代第 1–2 轮 + r3–r8 续完成（r1 PASS / r2 平台期 / **v6 过门显著强于 v1**）、F 数据已下）
**与 hiro / QQ 群 / 官方 AI 的进度对比**：见 [COMPARE.md](COMPARE.md)（口径、数字、唯一可比路径）。
```

> **新会话先读 [WORKPLAN.md](WORKPLAN.md)**：总顺序 = **离线全部做完 → 真机（T3→T1→T2）→ 去 gkbench 比算法**。
> WORKPLAN 里含完整任务表（A1 OCR ✅ / A2 F#42 ✅ / A3 F#43 ✅ / A4 回放素材 ✅ / A5 T3 离线预演 ✅ / B1 T4 修正 ✅ / B2 学习叶子 ✅（B2-R 重训 FAIL，路线关闭）/ B3 回合规则+核验表 ✅ / B4 T5① 审查倍率 ✅ / B5 T5② 熱意+温存解除 ✅ / B6 T5③ P 道具数据接入 ✅ / B7 T9 P 道具 47 条补全 ✅ / C0 T9 更新断链判据吸收 ✅ / C1 可靠性 ✅（真机验收留阶段 E）/ B11 渐退式专家迭代 🟡（第 1 轮 PASS / 第 2 轮平台期，下一轮先问用户）/ D 数据 / E 真机 / F gkbench / G 收尾）
> 和「已完成不要重做」清单。

> **2026-11-21 用户硬规矩（不许破）**：SKIP 只在"所有牌都付不起"时允许；读不到分数/费用不是跳过理由，
> 那是 OCR/卡表 bug，去修它，不许用 SKIP 补偿。**bot 不许回退 rules**：搜索/规划/神经网络失败 =
> 记 `[engine][BLOCKED]` 并中止本局、去修 root cause，不许静默改用规则引擎（见 §4 硬约束 5/6）。
> 真机整局必须带 `--ignore-user`（人别碰键鼠/别最小化窗口）。

当前最好成绩对照（都是"初/REGULAR-PRO"路线，口径见 [RUNS.md L229](RUNS.md#L229)）：

| 谁 | 评价 | 说明 |
|---|---:|---|
| bot（2026-11-21 晚接管局） | **C / 4242** | 期中 914/第3 → 培育终了；原因：课程大面积跳过 + 考试搜索退回规则 + 全知未启用；修复见 [HANDOVER 二·补七](HANDOVER.md#L269) |
| bot（2026-11-15 旧版） | **C+ / 5992** | 11.8 分钟，差 B 门槛 8 点；之后未再跑完全局 |
| 用户手动 | **A / 10237** | 20.2 分钟，True End 3/3；这是追赶目标 |
| 用户手动（采集局） | B / 7404 | 11-20 一局两场考试，全部考试数据已采到 |

> 对手 hiro 的 A / 10 428 是不同账号/卡组/模式，**不能直接和 5992 比**；要可比必须走 T2 的同环境 A/B。

---

## 1. 已完成、不要再做（先读这一节，避免重做）

| 能力 | 产物 | 验证 / 数字 |
|---|---|---|
| MITM 采集链路 | `C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl` | 四场考试全采到；见 [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md) |
| 考试牌堆重建 | `scripts/reconstruct_deck.py` → `deck_snapshots.json` | 期中 18 / 期末 26 张逐张吻合 |
| 洗牌模型破解 | [exam_shuffle.py](../src/gkagent/sim/exam_shuffle.py) | 4/4 场整段复现；3/3 重洗样本 |
| 牌序全知数据链路 | [exam_oracle.py](../src/gkagent/sim/exam_oracle.py) + [exam_plan.py](../src/gkagent/sim/exam_plan.py) | 每回合预测手牌 vs 实机逐张核对 |
| 采集数据 → setup | `scripts/build_exam_setup.py` → `out/exam_setup.json` | 4/4 场、86/86 张；重洗段 24/24 |
| 完全信息搜索（搜索侧） | `ExpectState.known_draw` / `discard_order` / `reshuffle` 钩子 | 17 条测试；重洗后段可确定分支 |
| 生产接线接口 | `LessonPolicy(draw_plan=…)` + `auto_produce --exam-setup` | [verify_exam_wiring.py](../scripts/verify_exam_wiring.py)：36/36 手牌、3/3 重洗、29/29 known_draw |
| 跨回合 beam 选项 | `lesson.engine="beam"`（`beam_width=4` / `beam_deadline_ms=250`） | 7 条测试；无 known_draw 自动退回回合内搜索 |
| 决策可观测性 + 引擎接线 | 日志首行 `[engine]`、每步 `| eng=…` / `fallback=…`；真机引擎由 `--engine` > `produce.engine` 决定 | 4 条测试；能回答"到底是不是 rule 在打、为什么退回"；2026-11-21 深夜起搜索引擎**禁止回退 rules**（失败→`[engine][BLOCKED]`，见 F#40） |
| T3 实时接线（代码） | `build_exam_setup.py --current` + `ExamPlanSelector` + `auto_produce` 运行时重载 | 4 条 selector 测试；已用采集局离线验证第 2 回合锁定正确 config_turns |
| 模拟器 + 评价公式 | [hajime_eval.py](../src/gkagent/sim/hajime_eval.py)、[hajime_data.py](../src/gkagent/sim/hajime_data.py) | 4 局实机逐分回归（9973/10428/8790/12903） |
| 主数据库 | `data/hiro/vendor/.../catalog.sqlite` | 286 表 / 163,974 行 |
| A1 日文 OCR 模型 | `configs/ocr_jp.example.yaml` + `scripts/download_ocr_models.py` | 真图 4 条 + 配置 17 条；见 HANDOVER 二·补十四 |
| A2 课程硬打必须得分（F#42） | [vision/lesson.py](../src/gkagent/vision/lesson.py) 课程 HUD 换算 + [policy/lesson.py](../src/gkagent/policy/lesson.py) 每回合 1 张/硬打保分 | `tests/test_lesson_play_f42.py` 真图回放 3 条 + HUD 换算 4 条 + flat-tie 硬打 1 条；见 HANDOVER 二·补十五 |
| A3 F#43 结果页空转 | [produce_ui.py](../src/gkagent/tasks/produce_ui.py) `_GAIN_RE` 只认正收益 + 事件屏 P 费标签兜底 + 静态页第 3 次找按钮 | `tests/test_produce_ui_f43.py` 7 条（真机帧回放 3 + 合成 4）；见 HANDOVER 二·补十六 |
| A4 离线回放素材 | [tests/fixtures/README.md](../tests/fixtures/README.md) 8 张真机帧溯源 + [scan_frames.py](../scripts/scan_frames.py) 批量挑帧 | `tests/test_frames_replay_a4.py` 9 条（六类关键屏真帧回放；回合结束确认框用真机课程帧文字 + F#36 文案，真机帧已被轮转覆盖）；全量 pytest **950/1（951 收集 / 68 文件）**；F#44 `_checkbox_bands` 修复；见 HANDOVER 二·补十七 |
| A5 T3 离线预演 | [verify_exam_plan_offline.py](../scripts/verify_exam_plan_offline.py)：`--current` 候选（--refresh 现场重建）+ 四场 sweep，truth 驱动 `ExamPlanSelector` | 最新场 3 候选第 2 回合锁定 `config_turns=12`（真值 12）；四场 sweep T1–T2 锁定、选中 = 9/11/9/12 全对；候选→1、`locked_turn≤3`；`tests/test_exam_plan_offline.py` 8 条；全量 pytest **958/1（959 收集 / 69 文件）**；见 HANDOVER 二·补十八 |
| B1 T4 修正（评测 bug + 受控 frontier 叶子） | [eval_t4_b1.py](../scripts/eval_t4_b1.py)：`_execute_plan` 白丢回合修复 + `search_beam(frontier_value=…)` | 60 局配对：beam unknown **164.0** / known **165.5** vs within **143.1**（+20.9 / +22.4，CI 全正），决策门 **114.6%/115.7% PASS**；frontier 中性；`tests/test_beam_frontier.py` 6 条；全量 pytest **964/1（965 收集 / 70 文件）**；见 HANDOVER 二·补十九 / EXPECTIMAX「T4 修正」 |
| B2 全知数据训练 MLP 叶子 | [build_b2_dataset.py](../scripts/build_b2_dataset.py) + [leaf_data.py](../src/gkagent/sim/leaf_data.py)（叶子状态快照）+ [leaf_mlp.py](../src/gkagent/sim/leaf_mlp.py)（104 维 MLP 叶子）+ [train_b2_leaf.py](../scripts/train_b2_leaf.py) + [eval_b2.py](../scripts/eval_b2.py) | 26.5k 全知 beam 自对弈样本，val r²=0.943 / MAE 8.8；B1 修正 harness 配对：选择段 seed 2000–2079 beam **166.8→173.7（+6.8）** / ensemble 174.4（+7.5）；**确认段 seed 3000–3119（120 局）beam 157.8→165.5（+7.7 CI[+4.2,+11.2]）/ ensemble 0.5 166.9（+9.0 CI[+5.8,+12.2]）**，known 同向；within 用 learned 变差 −3.3（负结果、只对 engine=beam 有益）；`tests/test_b2_leaf.py` 11 条；全量 pytest **975/1（976 收集 / 71 文件，B3 前口径）**；**B3 后旧模型失效；B2-R（2026-11-23）已按新规则重采/重训，仍 FAIL（确认段 −7.2，ensemble 0.75 中性），生产保持关闭**；见 HANDOVER 二·补二十 / EXPECTIMAX「B2 学习叶子」+「B2 重训（B2-R）」 |
| B3 T5 机制建模（回合规则 + 核验表） | [RULES_REFERENCE.md](RULES_REFERENCE.md) 重写为逐条核验表 + [export_t5_turn_rules.py](../scripts/export_t5_turn_rules.py)（真机 39 回合摘要）+ [t5_exam_turn_rules.json](../tests/fixtures/t5_exam_turn_rules.json) + `safe_ceil`（`sim/lesson.py`） | 模拟器对齐真机：每回合基础 **1 张** + 打完自动结束回合 + SKIP 回 2 体力 + 取整 `safeCeil`；实机回放黄金值 12 条；真机 39 回合配对回归（32×1 张 / 7×2 张 / 手牌全 3 张）；重标定：sim_engine_ab expectimax 显著强于 rules（+342~+429 评价点）、B1 60 局 within 89.1→beam 95.7（+6.6，门 107.4% PASS）、B2 旧模型 FAIL 待重训；`tests/test_t5_turn_rules.py` 9 条；全量 pytest **985/1（986 收集 / 72 文件）**；见 HANDOVER 二·补二十一 / SIMULATOR §11 |
| **B4 T5① 审查倍率（分段 + 联动惩罚）** | [exam_multiplier.py](../src/gkagent/sim/exam_multiplier.py)（纯公式）+ [exam_bonus.py](../src/gkagent/data/exam_bonus.py)（主数据解析）+ [export_exam_multipliers.py](../scripts/export_exam_multipliers.py)（真机夹具）+ `LessonConfig.attribute_bonuses/turn_attributes` + `policy.audition_coefficient` | 客户端真实公式：分数表分段折线 × 审查基准联动惩罚（`common=1000−Σpenalties` 三项共乘）× 单精度取整；11-20 采集局期中 Vo/Da/Vi **4.09/2.20/2.60×**、期末 **6.97/2.85/4.96×**（Vi/Vo/Da 低于基准的联动惩罚已对上）；生产读屏 「舞蹈 207%」→ 搜索 `attribute_coefficient=2.07`（日志 `attr=`）；`tests/test_exam_multiplier.py` 21 条；全量 pytest **1006/1（1007 收集 / 73 文件）**；真机逐分回放仍差 P 道具附魔/生成卡等未建模项；见 HANDOVER 二·补二十五 / RULES_REFERENCE §5.1 |
| **B5 T5② 熱意 + 温存解除** | [enthusiasm.py](../src/gkagent/sim/enthusiasm.py)（纯规则：温存解除/熱意获得/回合末清零延長）+ `LessonSim`/`ExpectState` 熱意字段与算分 + [sim_produce.py](../scripts/sim_produce.py)（MODELED_EFFECTS 29→32）+ [play_choice.py](../src/gkagent/sim/play_choice.py)（生产卡表映射） | 参考引擎（BSD-3）+ 官方 wiki：熱意出牌分加算、获得时 ceil、回合末清零/延長；温存解除 1 段 +5 / 2 段 +8 熱意 + 5 固定元気 + **+1 出牌次数**（同回合可重复、温存→全力回合边界也触发）；卡牌 `ExamEnthusiasticAdditive/Multiple/TurnAdd` 与 `ExamMultipleEnthusiasticLesson`（本牌倍率 ×2）接入；`tests/test_t5_enthusiasm.py` 16 条；全量 pytest **1023/1（1024 收集 / 74 文件）**；见 HANDOVER 二·补二十六 / RULES_REFERENCE §5.2 |
| **2026-11-22 作者整合包分析（外部情报，只读参考）** | [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)（包结构 / 11-22 新版本变化与修复 / 与采集安装的边界；7z 归档 `data/dl/`，解包在仓库外） | 用户提供 215 MB 四游戏整合启动器包（11-22 构建，1457 条 sha256 清单逐条校验通过）；新版本：启动器中文错误诊断/MLTD 停止服务、学园后端新增离线培育（Selection Exam/produce-007 状态机）等；**不能替换我们的采集安装**（无 `GKM_TRAFFIC`、hook 构建不同）、**拿不到考试算分公式**（服务端无 Audition）；给出 P 道具 47 条 id 清单（含 B6 的 11 个未知 gkbench id）。候选任务 T9（§4），提交 `ddf221f` |
| **B6 T5③ P 道具数据接入** | [p_items_db.py](../src/gkagent/data/p_items_db.py)（loadout `produce_item_ids` → `PItemSpec`，未知/重复 id 显式、缺数据抛错）+ `sim/p_items.py`（新增 `exam_start` 触发时机 + `ExamPlayableValueAdd`→`extra_plays`，51 段取 `count` 列）+ [lesson.py](../src/gkagent/sim/lesson.py)（构造时结算考试开始效果）+ [local_bench.py](../scripts/local_bench.py)（报告 `p_items` 覆盖率 + `--p-items auto/off`）+ [algo.py](../submissions/expectimax/algo.py)（`ctx.loadout` 接入） | gkbench 505 题模板 2686 个 id / 83 唯一 / 72 已知 / 11 未知（快照缺行不猜）；catalog 1764 段 spec 已实现 421 段、gkbench 已知 131 段实现 31 段；F0 起点体力 15 组偏差里 5 组（shro-3-016 −28）可用 `pitem_02-3-293-0` 考试开始「最大体力 80% 变体力消耗」（`floor(36×0.8)=28`）解释；离线 A/B hif 30 题×2 seed 配对：greedy **3840.7→3969.7（+128.9，+3.36%，CI95[+9.5,+248.4]）**、expectimax **3759.3→3908.9（+149.6，+3.98%）**，其余局逐位不变；新增 29 条测试；全量 pytest **1051/1（1052 收集 / 76 文件）**；见 HANDOVER 二·补二十七 / RULES_REFERENCE §5.3 |
| **B7 T9 P 道具 47 条补全（2026-11-22）** | [build_p_items.py](../scripts/build_p_items.py)（本地中文 master 1068 + gakumasu-diff yaml 新增 47 合并；卡名用 `data/i18n/translation_new.json`，描述日文+`i18n_text_source="ja"`；新触发 id 无中文触发句 → `condition_known=False`）+ [p_items.py](../src/gkagent/sim/p_items.py)（`PItemSpec.condition_known` 保守跳过 + `summarize` 单列计数）+ [p_items_db.py](../src/gkagent/data/p_items_db.py)（`condition_unknown` 覆盖率）+ [local_bench.py](../scripts/local_bench.py)（报告 `condition_unknown_specs`） | **catalog 1068→1115 件**（spec 1764→1849、已实现 421→445、条件未知 46 段另计）；**gkbench 505 题模板 83 唯一 id 全部已知、未知 0**（B6: 72 已知/11 未知）；47 条新增都能解析出 ≥1 段 spec（5 条育成期道具=unknown no-op）；A/B hif 30 题×2 seed：greedy **3840.7→3969.7（+128.9，+3.36%，CI[+9.5,+248.4]）**（与 B6 逐位相同，新道具目前 0 分贡献）、expectimax 3732.0→3953.6（+221.5，CI[−71.4,+514.4]，墙钟抖动）；新增 3 条测试；全量 pytest **1054/1（1055 收集 / 76 文件）**；见 HANDOVER 二·补二十九 / RULES_REFERENCE §5.3 |
| **T9-C0 采集/更新断链排障判据吸收（2026-11-22，纯文档）** | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) **§四** 13 条清单（触发→症状→处理→参考：2004、hook 被 DMM 还原、协议 hash、master 清单结构/长度/SQLCipher 判据、版本哈希不透明、http1_bridge 头丢失、Auth/Login 865-833、上游端口、停服务顺序、CA 指纹/TLS 回退、代理残留、诊断脱敏、互斥）+ §4.2 与 1.3–1.9 对应表；[CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md)「游戏客户端大版本更新后自检」**8 步** | 来源作者 11-22 整合包（只读，[LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)）；**外部经验、本项目待验证**，只写结论未拷代码/未加依赖/未动数据；纯文档 **pytest 仍 1054/1**；见 HANDOVER 二·补三十 |
| **B8 T5④ P 道具条件/效果语义（第一批，2026-11-22）** | [build_p_items.py](../scripts/build_p_items.py)（`parse_exam_trigger_id` / `annotate_effects`：新语法 trigger id 解析 + 依赖换算标注）+ [p_items.py](../src/gkagent/sim/p_items.py)（`depends_on`/`percent`/`percent_max`/`zero_stack` + `turn_start_after`/`turn_interval`/`status_gain_interval`/`stance_change`/`stamina_reduce`）+ [lesson.py](../src/gkagent/sim/lesson.py)/[expectimax.py](../src/gkagent/sim/expectimax.py)（事件与累计量双镜）+ [test_p_items_b8.py](../tests/test_p_items_b8.py) | 数据层已实现 **445→676/1849 段**（no-op 1404→1173）；条件未知 22→**6 件**（46→10 段）；触发限定未知 103 件/185 段（指定卡/手牌，保守跳过）；依赖换算 65 / 百分比体力 9 / 归零 3 段；gkbench hif 83 唯一 id 已实现 **34→59/153 段**；离线 A/B（hif 30×2 seed）greedy 3840.7→**4065.9（+225.2，+5.86%，CI[+86.7,+363.6]）** / expectimax 3726.4→**3921.8（+195.4）**；全量 pytest **1067/1（1068 收集 / 77 文件）**；基线 ①③④⑤ 不变；见 HANDOVER 二·补三十一 / RULES_REFERENCE §5.3 |
| **B10 T5 剩余①② 生成卡 + 指定卡名/手牌张数映射（2026-11-23）** | 新 [build_card_meta.py](../scripts/build_card_meta.py) + [card_meta.json](../data/knowledge/card_meta.json) + [card_meta.py](../src/gkagent/data/card_meta.py)（idol_unique/effect_groups/日文别名）+ [build_p_items.py](../scripts/build_p_items.py)（`parse_card_search`/`annotate_create_effects`）+ [p_items.py](../src/gkagent/sim/p_items.py)（CardFilter/ZoneCount/CreateCard + exam_start_after + 次数按道具计）+ [lesson.py](../src/gkagent/sim/lesson.py)/[expectimax.py](../src/gkagent/sim/expectimax.py)（生成卡落牌双镜）+ [play_choice.py](../src/gkagent/sim/play_choice.py)（`spec_from_name`）+ [test_p_items_b10.py](../tests/test_p_items_b10.py) | 触发未知 **103→3 件 / 185→6 段**、条件未知 **6→0**；play_filter 234 件 / zone_count 27 件；生成卡 **11 段确定 + 6 段随机 no-op**；数据层 **1025→1042/1849 段**；gkbench 103/153 段（loadout 4 件/8 段开始真实触发）；idol_unique 参考交叉 **340/342 零误报**；greedy A/B **+797.5（+20.76%，CI[+399.0,+1250.1]）** / expectimax +801.1（CI[+66.3,+1697.9]）；全量 pytest **1154/1（1155 收集 / 79 文件）**；基线 ①③④⑤ 不变；见 HANDOVER 二·补三十三 / RULES_REFERENCE §5.3 |
| F 阶段数据 + F0 预检（gkbench） | [bench_download.py](../scripts/bench_download.py)（公开 API + 令牌批量下载，断点续传）+ [GKBENCH.md](GKBENCH.md)（API/令牌边界/下载清单/参考分/F0） | hif 已下 80 run / **36,350 条对局路线** / 329 题官方种子+check / 505 题存档 / fixed+template 榜单；**官方 check.hand 核洗牌模型 286/384=74.5%**（npc 按 stage：選抜 5、本戦 2；sel1 60/60）；不一致根因=initial_add 自定义 + isInitial 变体（F0 收尾）；数据在 `data/bench_local/gkbench_dl/`（gitignore）；令牌在仓库外 `~/.config/gkbench/token`；见 HANDOVER 二·补二十二 |
| **F0 收尾（gkbench 官方种子校准）** | [verify_gkbench_shuffle.py](../scripts/verify_gkbench_shuffle.py)（384 组 check.hand 核对 + 起点校准，只读本地数据）+ [GKBENCH §4.5](GKBENCH.md) | **initial 按 base id（含强化变体）+ initial_add、npc 按 idol 卡（jsna 4 人制/fktn 2 人制/其余 3 人制）+ round 兜底** → **366/384=95.3% 精确 / 97.4% 逐张**（sel1 60/60、sel2 55/55、main1 96/97；逐题 311/329 全中）；剩余 18 组全是考试开始加卡机制（ExamInitialDeck 15 + kllj 开局 +1 手牌 3），**无一洗牌错误**；起点校准 turn=1/score=0/stamina 96.1%=starting_stamina/rules=55(commit f4d9e6e6148d)；见 HANDOVER 二·补二十四 |

| **P1-6 T7②③ 离线可靠性工程（2026-11-24，不改考试规则）** | [run_replay.py](../src/gkagent/data/run_replay.py)（纯函数重放/逐步比对/三方对账）+ `RunRecorder.events` 观测日志 + [replay_run.py](../scripts/replay_run.py)（--verify/--compare）+ [review_page.py](../src/gkagent/report/review_page.py)（自包含复盘页）+ [annotations.py](../src/gkagent/report/annotations.py)（标注转回归）+ [review_page.py](../scripts/review_page.py)/[annotations_to_regression.py](../scripts/annotations_to_regression.py) + auto_produce 局末 `[review]` | 同观测序列两遍重放指纹逐位相等；ep-kinami1/ep-rule1/ep-verify1 三方对账一致；ep-t1-g 卡屏 28 次重复观测显式 surfaced；样例 [docs/review_sample.html](review_sample.html)；夹具 2 条 synthetic-demo 演示用例；61 条新单测，pytest **1564/1（1565 收集 / 97 文件）**；sim/ 零引用 → 评测零影响；见 WORKPLAN P1-6 / LIVE_RUN §2.1 / HANDOVER 二·补五十 |

**改动以上任何部分的规矩**：先跑 §2 基线命令（四条必跑 + ⑤ 可选）；数值/状态语义改动必须补单测并更新对应文档（`EXPECTIMAX.md` / `MASTER_DATA.md` / `HANDOVER.md`）。

---

## 2. 开工自检（每次新会话，5–10 分钟；四条必跑 + ⑤ 可选）

```powershell
cd D:\Games\gakumas-agent
# ① 洗牌重放：应为 4/4 场（期中 18/18、期末 26/26、PRO 期中 15/15、PRO 期末 27/27）+ 3/3 重洗样本
.venv\Scripts\python.exe scripts\verify_shuffle.py

# ② 全量测试：应为 1644 passed, 1 skipped（1645 条收集 / 99 个测试文件；含 A1 日文 OCR 21 条 + A2 F#42 8 条 + A3 F#43 7 条 + A4 帧回放 9 条 + A5 离线预演 8 条 + B1 beam/frontier 6 条 + B2 学习叶子 12 条（B2-R +1 温存解除边界快照回归）+ B3 回合规则 9 条 + B4 T5① 审查倍率 21 条 + B5 T5② 熱意/温存解除 16 条 + B6 T5③ P 道具 29 条 + B7 T9 P 道具 3 条 + B8 T5④ 条件/效果语义 19 条 + B9 T5④ 持久倍率/modifier 49 条 + B10 T5 剩余①② 生成卡/卡名映射 38 条 + C1 执行层可靠性 68 条（tapguard 28 + privilege 18 + trace 12 + wiring 10）+ B11 渐退式专家迭代 28 条 + B11 第 2 轮 15 条 + B11 ε-greedy 探索 7 条 + B11 v6 生产接线 21 条 + B11 r9 多文件混合 12 条 + B11 r10 按场景归一化 12 条 + P1-1 全力回合/のんびり指針 36 条 + P1-2 handDecrease/pride 36 条 + P1-3 hold 保留区/lockStanceTurns 46 条 + P1-4 nullifyDebuff 拦截/⑦评估 30 条 + P1-5 层数减少/好调回合/好调依赖换算 38 条 + P1-6 纯函数状态重放 38 条 + 复盘页/标注闭环 20 条 + 标注回归夹具 3 条 + P1-7 好调增加量/元气无效/不安/延迟生效 48 条 + P1-8 日文好調の%分换算 32 条 + 实机回放黄金值 2 条）
#    注意：pytest 9 下命令行再传 -q 会「双静默」——只剩点号、不打印 "N passed" 汇总行；想看到数字就去掉 -q。
.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=data/pytest-tmp-<日期>

# ③ 采集数据 → 考试牌序：应为 4/4 场、初始段 86/86 张、重洗段 24/24 张
.venv\Scripts\python.exe scripts\build_exam_setup.py

# ④ 生产接线端到端：应为手牌 36/36 回合、重洗 3/3、known_draw 29/29、策略链路 beam 出牌 28 次
.venv\Scripts\python.exe scripts\verify_exam_wiring.py

# ⑤（可选，F0 已收尾后新增）gkbench 官方种子核洗牌模型：应为 366/384 精确（95.3%）、逐张 1125/1155
#    需要 data/bench_local/gkbench_dl/hif/（gitignore，缺数据可跳过；只读本地、不联网）
.venv\Scripts\python.exe scripts\verify_gkbench_shuffle.py
```

**最近一次复核（2026-11-24 14:2x，P1-8 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1644/1（1645 收集 / 99 文件，214.43s，+32 P1-8 日文好調の%分换算单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。**规则口径变化（P1-8）**：日文好調の%分（天生的才能
pitem_01-3-346-0/1）已建模——DSL 天性の才能 493/494 `score+=goodConditionTurns*0.3/0.5` +
`countCards[hand & baseId(23)]>=1`（眠気卡张数条件 B10 zone_count 已解析）；本批**只补数据层
日文换算源标注**（CONVERSION_SOURCES_JA，sim/ 零改动，复用 P1-5 换算渠道）→ 旧 B11 数据/模型
是旧规则口径（全保留不覆盖，阶段2 重采新批再对比）；**sim_produce p_items 默认 () + sim_engine_ab
不注入 P 道具 + sim/ 零改动 → 评测零影响**，sim_engine_ab 重标定**改前/改后 64 局逐位相同
（差异=0**，seed 9000/9100 各 16 局；expectimax 仍显著强于 rules Δ+372.2/+219.1）。
implemented 1179→1181/1849（+2）、依赖换算 76→78（好调换算 11→13）。**保持 no-op 如实记**：
全力・强气效果卡打分（per-card g.score 成长 43 段，values 恒空需逐卡证据表+新机制）/塔 gimmick
（29 段参考无字段）/ExamParameterBuffReduce（3 段 produce/buff_consume 触发未支持）。
P1-8 见 RULES_REFERENCE §5.10 / WORKPLAN P1-8 / HANDOVER 二·补五十二。

**上一次复核（2026-11-24 13:5x，P1-7 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1612/1（1613 收集 / 98 文件，218.08s，+48 P1-7 好调增加量/元气无效/不安/延迟单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。**规则口径变化（P1-7）**：好调增加量增加 condition_gain
（resolveGoodConditionTurns ×(1+Σbuffs)）+ 元气增加无效 nullify_genki_turns / 不安 unease_turns
（resolveGenki return / ×0.67，∈ EOT_DECREMENT+DEBUFF_FIELDS）+ ExamBlockFix 分离 fixed_vitality +
**通用延迟生效**（yaml exam_effect_timer ↔ DSL delay/嵌套 at:turn，34 段，修正おさぼりタオル/美铃/
温存变更类等时序）已建模 → 旧 B11 数据/模型是旧规则口径（全保留不覆盖，阶段2 重采新批再对比）；
**sim_produce 不引用 p_items + genki_gate/condition_gain 无来源恒等 → 评测零影响**，
sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，seed 9000/9100 各 16 局；
expectimax 仍显著强于 rules Δ+372.2/+219.1）。implemented 1164→1179/1849（+15）、modifier 409→442。
**保持 no-op 如实记**：塔 gimmick（参考无字段）/塔 ∞ 段（value=0）/全力・强气效果卡打分（per-card
g.score 成长）/日文好調の%分/ExamParameterBuffReduce。P1-7 见 RULES_REFERENCE §5.9 / WORKPLAN P1-7 /
HANDOVER 二·补五十一。

**上一次复核（2026-11-24 13:1x，P1-6 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1564/1（1565 收集 / 97 文件，+61 P1-6 重放/复盘页/标注回归单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。**本批不改考试规则**（T7②③ 纯可靠性工程）：新模块
run_replay/report 与 sim/ 零耦合（grep 0 命中）→ 评测零影响、无需 sim_engine_ab 重标定；
旧 B11 数据/模型全保留。真实记录端到端 `replay_run.py --verify`：ep-kinami1/ep-rule1/
ep-verify1 三方对账全一致；ep-t1-g 卡屏局 28 次重复观测被显式 surfaced。
P1-6 见 WORKPLAN P1-6 / LIVE_RUN §2.1 / HANDOVER 二·补五十。

**上一次复核（2026-11-24 10:3x，P1-5 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1503/1（1504 收集 / 94 文件，223.75s，+38 P1-5 层数减少/好调单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。**规则口径变化（P1-5）**：P 道具层数减少类（干劲/集中/全力值
-= N 夹取 ≥0 + 体力减少）+ 好调回合（ExamParameterBuff turn 列 → condition_turns）+
好调依赖换算（好调的N%数值变为打分/集中）已建模 → 旧 B11 数据/模型是旧规则口径（全保留
不覆盖，阶段2 重采新批再对比）；**sim_produce 不引用 p_items → 评测零 P 道具结算**，
sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，seed 9000/9100 各 16 局；
expectimax 仍显著强于 rules Δ+372.2/+219.1）。implemented 1067→1164/1849（+97）、
依赖换算 65→76。留后续（证据充分需新机制，no-op 如实记）：好调增加量增加/元气增加无效/
不安/塔 gimmick/全力・强气效果卡打分/日文好調の%分。
P1-5 见 RULES_REFERENCE §5.8 / WORKPLAN P1-5 / HANDOVER 二·补四十九。

**上一次复核（2026-11-24 09:2x，P1-4 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1465/1（1466 收集 / 93 文件，+30 P1-4 nullifyDebuff 单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。**规则口径变化（P1-4）**：nullifyDebuff 低下状态无效拦截
（消耗式计数器拦截 setScoreDebuff/setHandDecrease，P 道具侧 ExamAntiDebuff 11 段）已建模；
⑦ ExamBuffConsumptionAdd / countDebuffs 评估保持 no-op（卡模型不承载 buff 花费 /
低下状態の数零使用，无落点）→ 旧 B11 数据/模型是旧规则口径（全保留不覆盖，阶段2 重采
新批再对比）；评测牌组/gkbench loadout 组成不变（nullifyDebuff 来源评测零落点），
sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，seed 9000/9100 各 16 局；
expectimax 仍显著强于 rules Δ+372.2/+219.1）。implemented 1056→1067/1849。
P1-4 见 RULES_REFERENCE §5.7 / WORKPLAN P1-4 / HANDOVER 二·补四十七。

**上一次复核（2026-11-24 09:0x，P1-3 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1435/1（1436 收集 / 92 文件，230.80s，+46 P1-3 hold/lockStanceTurns 单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = 	ests/test_produce_ui.py:1181（data/auto/step_047.png 被真机跑局覆写、
当前不是行动页），属预期。**规则口径变化（P1-3）**：hold 保留区（13 族卡证据表）+
lockStanceTurns 指針固定（fresh 锁下一回合）+ hold 区张数条件/hotfix 清零 + preservation2
已建模 → 旧 B11 数据/模型是旧规则口径（全保留不覆盖，阶段2 重采新批再对比）；
**large 评测牌组组成变化**（冲刺/积累 draw 近似移除，保真度修正；small 不变），
sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，seed 9000/9100 各 16 局；
冲刺/积累 未被这 64 局奖励采到；expectimax 仍显著强于 rules Δ+372.2/+219.1）。
P1-3 见 RULES_REFERENCE §5.6 / WORKPLAN P1-3 / HANDOVER 二·补四十六。

**上一次复核（2026-11-24 08:1x，P1-2 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1389/1（1390 收集 / 91 文件，+36 P1-2 handDecrease/pride 单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。**规则口径变化（P1-2）**：handDecrease 抽牌修正
（cardsToDraw=max(3−Σ,0)）+ pride 自尊（resolveScore f min(好印象,干劲)×0.02 上限+0.5）
已建模 → 旧 B11 数据/模型是旧规则口径（全保留不覆盖，阶段2 重采新批再对比）；
评测牌组/gkbench loadout 组成不变（自尊卡 score 0/SSR 不进池；94 唯一 loadout id 无
117/tower），sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0**，seed 9000/9100
各 16 局；expectimax 仍显著强于 rules Δ+372.2/+219.1）。P1-2 见 RULES_REFERENCE §5.5 /
WORKPLAN P1-2 / HANDOVER 二·补四十五。

**上一次复核（2026-11-24 00:3x，P1-1 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1354/1（1355 收集 / 90 文件，+36 P1-1 全力回合/のんびり单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。**规则口径变化（P1-1）**：全力回合 +1 出牌/保留牌回手/指針守卫、
のんびり指針（×0/解除/预约来源）已建模 → 旧 B11 数据/模型是旧规则口径（全保留不覆盖，
阶段2 重采新批再对比）；评测牌组组成不变（のんびり卡本就不进池），sim_engine_ab 重标定
**改前/改后 64 局逐位相同（差异=0**，seed 9000/9100 各 16 局；expectimax 仍显著强于 rules
Δ+372.2/+219.1）。P1-1 见 RULES_REFERENCE §5.4 / R9_ANALYSIS §9 /
WORKPLAN P1-1 / HANDOVER 二·补四十四。

**上一次复核（2026-11-23 23:4x，B11 r10 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1318/1（1319 收集 / 89 文件，225.05s，+12 r10 按场景归一化单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。r10 评测参照臂与 r9 JSON 逐位一致（small500 v6/beam、
large500 v6/beam/greedy 全 500 局；large 前 120 水位 291.6083/305.3417/212.4083/277.2417
复现文档数字）；r10 见 EXPECTIMAX B11 r10 / R9_ANALYSIS §8 / HANDOVER 二·补四十三。

**上一次复核（2026-11-23 22:0x，B11 r9-large 后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1306/1（1307 收集 / 88 文件，206.53s，+12 r9 多文件混合单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。r9 评测参照臂与 r6 JSON 逐位一致（small500 v6/beam、
large 前 120 v6/beam/greedy）；r9 见 EXPECTIMAX B11 r9-large / HANDOVER 二·补四十二。

**上一次复核（2026-11-23 21:3x，B11 v6 生产接线后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1294/1（1295 收集 / 87 文件，202.95s，+21 v6 生产接线单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。v6 生产接线见 EXPECTIMAX「B11 v6 生产接线」/ HANDOVER 二·补四十一。

**上一次复核（2026-11-23 21:1x，B11 r3–r8 续后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1273/1（1274 收集 / 86 文件，205.92s，+7 ε-greedy 探索单测）**、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。B11 r3–r8 见 EXPECTIMAX B11 续 / HANDOVER 二·补四十。

**上一次复核（2026-11-23 20:0x，B11 第 2 轮后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1266/1（1267 收集 / 85 文件，372.30s，+15 B11 r2 单测）**、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。**环境备注**：本轮 ② 首跑曾遇 `test_drink_search_latency_stays_bounded`
失败（11.8–12.4ms > 10ms）——证实为机器游戏负载（TslGame）墙钟抖动（同搜索 5 轮 6.6–12.1ms
随负载波动；同 HEAD 19:0x 全绿；r2 代码不碰搜索），用户确认后继续任务、负载回落复跑全绿，
**未改测试门槛**。B11 r2 见 EXPECTIMAX B11 第 2 轮 / HANDOVER 二·补三十九。

**上一次复核（2026-11-23 19:0x，新会话开工复跑，HEAD 8768296）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1251/1（1252 收集 / 84 文件，281.87s）**、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%），与 18:1x 复核逐项一致
（墙钟 281.87s vs 190.62s 为机器负载差异，通过/收集数字不变）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。Hindsight 播种进行中（synced=false，5 页已建、后台深化，
无需干预）；B11 第 2 轮前置 `out/ei_r1_v1_mix.json` 等 r1 产物齐全。
下一候选按约定先问用户（B11 第 2 轮 / T7 剩余 / D1 / E0 / 直接阶段 E）。

**上一次复核（2026-11-23 18:1x，B11 渐退式专家迭代第 1 轮后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1251/1（1252 收集 / 84 文件，190.62s，+28 B11 单测）**、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。B11 见 EXPECTIMAX B11 / HANDOVER 二·补三十七。

**上一次复核（2026-11-23 17:4x，新会话开工复跑，HEAD 1376d21）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1223/1（1224 收集 / 83 文件，195.97s）**、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%），与 17:2x 复核逐项一致。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。下一候选按约定先问用户（渐退式专家迭代 / T7 剩余 / D1 / E0 / 直接阶段 E）。

**上一次复核（2026-11-23 17:2x，C1 执行层可靠性后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1223/1（1224 收集 / 83 文件，181.16s，+68 C1 失败场景单测）**、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。C1 见 HANDOVER 二·补三十六 / WORKPLAN C1。

**上一次复核（2026-11-23 12:3x，B2-R / B2 按 B3+ 规则重训后复跑）**：①②③④⑤ 全绿、退出码 0
（① 4/4+3/3、② **1155/1（1156 收集 / 79 文件，+1 温存解除边界快照回归）**、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。

**上一次复核（2026-11-23 00:3x，B10 / T5 剩余①② 后复跑）**：①②③④⑤ 全绿、退出码 0（① 4/4+3/3、
② 1154/1、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）。
② 唯一 skip = `tests/test_produce_ui.py:1181`（`data/auto/step_047.png` 被真机跑局覆写、
当前不是行动页），属预期。B4/T5① 见 HANDOVER 二·补二十五，B5/T5② 见 HANDOVER 二·补二十六，
B6/T5③ 见 HANDOVER 二·补二十七，B7/T9 见 HANDOVER 二·补二十九，B8/T5④ 见 HANDOVER 二·补三十一 /
[RULES_REFERENCE §5.3](RULES_REFERENCE.md)，B9/T5④ 第二批见 HANDOVER 二·补三十二，
**B10/T5 剩余①② 见 HANDOVER 二·补三十三**，
C0/T9 见 HANDOVER 二·补三十 /
[TROUBLESHOOTING §四](TROUBLESHOOTING.md)，F0 收尾见 HANDOVER 二·补二十四 / [GKBENCH §4.5](GKBENCH.md)。

**环境前提**：

- 采集文件在 `C:\GakumasLocal\GakumasUnlock\out\`（`traffic.jsonl` / `deck_snapshots.json` / `exam_truth.json`）。**不在就只跑 ①②**，并把 ③④ 标记为"待采集"。
- **日文 OCR 模型**：`.venv\Scripts\python.exe scripts\download_ocr_models.py --check` 应显示"全部就绪"；
  缺了就重跑（不带 `--check`）下载。日文模型缺失时 `OcrEngine` 会**直接报错**（不静默回退），
  配置/模型在 `data/models/ocr_jp/` + `configs/ocr_jp.yaml`（均 gitignore）。
- Windows + DMM 客户端；VPN 日本节点（TUN 或 7897 任一）；游戏窗口客户区 **540x960**（代码自动缩放，别改成 720x1280，会截崩，见 F#10）。
- `out/exam_setup.json` 已 gitignore，**每次采集后要重建**。
- **Hindsight 本地记忆已停用（2026-11-24）**：原 daemon 模式（127.0.0.1:9077，内嵌 PostgreSQL，
  LLM=百炼 qwen-plus / embeddings=text-embedding-v4，bank `coding-agent::gakumas-agent`）。
  **停用原因**：qwen-plus / text-embedding-v4 走**标准 dashscope 按量端点 + 普通 DASHSCOPE_API_KEY**，
  不在千问 Token Plan 订阅（sk-sp-，token-plan 端点）覆盖范围 → 后台深化 300 commit diff +
  吞长会话 + 维护 12 页 + 定时刷新 mental model，两天几千次调用烧掉约 ¥10 余额（用户发现后
  删普通 key 止血，daemon 401 空转）。**处置**：禁用插件 bundle `@vectorize-io/hindsight-coding-agents`
  （plugin_manager set_bundle enabled=false）+ 杀 daemon 进程树 + pg_ctl 停内嵌 PG（9077/5432 已释放）。
  **新会话不要用 hindsight_* 工具**（已下线），跨会话上下文全靠 docs 交接；主 agent 走订阅不受影响。
  历史启用配置/坑见 HANDOVER 二·补三十八，停用记录见二·补四十八。要恢复记忆需另配订阅覆盖的
  LLM + 本地 embeddings（零余额方案）或恢复普通 key 设消费上限，先问用户。
- 基线不绿就先修基线，不要在新功能上叠 bug。

---

## 3. 补什么（差距清单，按影响排序）

| 编号 | 缺口 | 现状 / 证据 | 影响 | 对应任务 |
|---|---|---|---|---|
| G1 | **自动化完成度**：bot 没跑完整局 | 2026-11-21 晚已修 10 类真机卡点（点击双重缩放/难度坐标/自动编成确认框/外出事件/领卡坐标/考试浮层/网络重试弹窗/加载快速路径逃逸/无决策空转/暂停误判同屏卡死，见 [FAILURES #27-32](FAILURES.md#L6)），**还没整局真机验收** | 自动拿分的**前提**；没有它一切策略都只是离线数字 | T1 |
| G2 | **没有真机 A/B** | 三引擎（rules / expectimax / beam+全知）从没同卡组同账号跑过 | 不知道 search 值不值；无法向用户证明 | T2 |
| G3 | **采集↔决策未打通**（原 item④） | bot 读离线 `out/exam_setup.json`；换一局/换一场考试就对不上（`ExamDrawPlan` 会安全停用） | 全知搜索（known_draw/beam）**实战用不上**，只在离线核对里有效 | T3 |
| G4 | **策略强度**：B1 修正 + B2 学习叶子（beam）+ B3 回合规则 | B1（B3 前口径）：beam unknown 164.0 / known 165.5 vs within 143.1；B3 规则修正后重测 within 89.1 → beam 95.7（+6.6，CI 全正，决策门 107.4% PASS）。B2：旧口径数据训练的 MLP 叶子在 B3 规则下**显著变差**（确认段 beam −27.9）→ 必须重采数据重训。B3 已把模拟器每回合 1 张 + 跳过回体力 + 取整对齐真机，整局 A/B 里 expectimax 显著强于 rules（+342~+429 评价点）。剩余：T5 机制（审查倍率/熱意/P 道具）→ B2 重训 → 真机 A/B（T2） | 考试分（评价点主要来源之一） | T5 / T2 |
| G5 | **机制建模缺口** | [OFFICIAL_AI_NOTES §3/§5](OFFICIAL_AI_NOTES.md#L330)：P 道具/回忆/附魔、选牌评估器、饮料、考试减益、考试内生成卡；回合内重洗（11-20 期末 T9）、同局多次重洗 RNG 快照未建模 | 模拟器与实战偏差 → 搜索决策偏 | T5 / T6 |
| G6 | **工程可靠性**：无互验/复盘 | 对照 hiro 三条原则（[HIRO_VIDEO_NOTES L32](HIRO_VIDEO_NOTES.md#L32)）：动作前预算下一帧、纯函数状态、自动复盘页——我们都没有 | 排障慢、回归靠人肉 | T7 |
| G7 | **情报跟踪** | hiro Windows 版进展、QQ 群 seed 口径都在变（[QQ_GROUP_NOTES](QQ_GROUP_NOTES.md#L59)） | 方向判断；低成本 | T8 |

**明确不需要补的**（ADR 已定，别浪费预算）：

- 不做日常/商店/启动/汉化（MaaGakumasu 已做，[PROJECT_PLAN ADR-001](PROJECT_PLAN.md#L180)）；
- 不替 MAA 抢输入；LLM 只做兜底、不做每步决策（[ADR-006](PROJECT_PLAN.md#L185)）；
- 不拷 `data/hiro/` 的 AGPL 代码。

---

## 4. 做什么（任务表：目标 → 步骤 → 验收 → 预算）

> 顺序建议：**T1 → T3 → T2 → T4 → T5/T6 → T7 → T8**。
> "预算"是按成本纪律估的**单次会话 token 量级**；做完一项就更新状态、开新会话（见 §8）。

> **本轮新增硬约束（2026-11-21 用户指定，违反即返工）**
> 1. **SKIP 只在"所有牌都付不起（真没体力）"时允许**；读不到分数/费用/搜索建议 SKIP 都不算理由。
> 2. "读不到" = OCR 或卡表 bug → 去修识别/卡表，不许用 SKIP/降级补偿。
> 3. 真机整局必须 `--ignore-user`（无人值守），人不要碰键鼠、不要最小化窗口。
> 4. 每步日志必须能回答"这手是谁决定的、为什么退回"（`eng=… fallback=…`）；新增决策引擎必须接这个口径。
> 5. **bot 不许回退 rules**（2026-11-21 追加）：搜索引擎/规划/神经网络失败时不许静默改用 rules。
>    状态没读全 → `wait` 等下一帧；搜索异常/结果失配 → `[engine][BLOCKED]` 中止本局，去修 OCR/卡表/参数。
> 6. bot 入口默认 `expectimax`；`--engine rules` 只用于 A/B 对照/离线复现，正常整局跑局不许用。
> 7. **一局必须有墙钟上限**：`auto_produce --max-minutes 30`（默认 30，0=关闭）。卡住时写
>    `episode-timeout` 主动停局并留日志，不许再出现"卡两个多小时还跑到 C"。

### T1（P0）无人值守跑完整局 🟡（流程卡点已修，差整局真机验收）
**目标**：bot 从主页起跑，一路到期末考试/结算，**不停机、不白给回合**，一局 ≤20 分钟。

**已完成（2026-11-21 晚，a9537b0 起）**
- 12 次真机短跑定位并修掉 10 类卡点（详见 [FAILURES #27-32](FAILURES.md#L6) + [TROUBLESHOOTING](TROUBLESHOOTING.md)）：
  点击坐标双重缩放、难度按钮坐标、自动编成确认框误判、外出/事件屏、领卡卡面中心、
  考试详情浮层（「得分+」/「仅限1次」）、通信错误弹窗重试、加载快速路径定时回看、
  无可用决策空转（连续 2 步强制 SKIP）、暂停帧计入同屏判死（暂停时 reset 同屏计数）。
- 出牌引擎接线 + 决策可观测性（见 T2 前置）：`[engine]`/`[training] … | eng=…` 日志能一眼看出
  这手是 expectimax 还是 rules 退回，以及退回原因（体力/回合/手牌读不到/搜索异常）。
- 新增回归测试：`tests/test_device_click_coords.py`、`tests/test_produce_ui.py` 增补。

**第二段（2026-11-21 22:00–22:20，4b07fa7/8a2af2b/b231b3f）**
- 7 次真机短跑，第一次**完整跑到结算**：期中 914/第 3 → 培育终了 → **最终 C/4242**（FAILURES #34-39）。
- 修掉：授课答题屏误判剧情（95 步循环）、领奖弹窗误判答题屏、课程快速路径吞「回合结束」确认框、
  用户操作时点击被拒→强制 SKIP（`--ignore-user`）、费用预览读歪（4 费记成 29 费）、
  **搜索 SKIP 被直接执行**（主因，已按用户规则全面禁止）。
- 现在课程/考试里 **SKIP 只在"所有牌都付不起"时发生**；四引擎（rules/expectimax/beam/uinet）统一拦截。

**第三段（2026-11-22 凌晨，采集+真机首次合体）**
- 采集链路通了（服务 18443/18444、token 刷新、C 盘副本）；4 次短跑 ep-t3-1..4 全部中途停。
- 已修：培育开场**日文剧情二选一**（布局识别选项气泡 + 补读中下部 OCR，`584f742`，FAILURES #41）。
- 当时待修（→ WORKPLAN A2/A3，**现均已修**：A2 `b388274` / A3 `106ef2b`）：**#42 舞蹈课程连打 buff
  → 0 分 FAILED**（禁跳硬打必须保证得分）；**#43 结果页 result-tap 循环**。
- 群文件情报（论文/2B run/GKMSMAA AGPL）见 HANDOVER 二·补十二；**A1 OCR 换日文模型已完成**
  （2026-11-22，官方 PP-OCRv6 Apache-2.0，见 HANDOVER 二·补十四 / WORKPLAN A1）；
  **A2 F#42 已完成**（2026-11-22，课程 HUD 语义 + 每回合 1 张 + 硬打保分，见 HANDOVER 二·补十五 /
  WORKPLAN A2）；**A3 F#43 已完成**（2026-11-22，真根因是日文饮料选择事件屏 + P 费标签被当飘字，
  见 HANDOVER 二·补十六 / FAILURES #43）；**A4 离线回放素材已完成**（2026-11-22，8 张真机帧 +
  9 条回放测试 + scan_frames 挑帧工具，见 HANDOVER 二·补十七 / WORKPLAN A4）；**A5 T3 离线预演已完成**
  （2026-11-22，`--current` 3 候选第 2 回合锁定 `config_turns=12`、四场 sweep T1–T2 锁定且选对真值，
  见 HANDOVER 二·补十八 / WORKPLAN A5）。**B1 T4 修正已完成**（2026-11-22：评测执行器丢回合
  bug 修正后 beam unknown 164.0 / known 165.5 vs within 143.1，决策门 PASS；frontier 叶子中性；
  见 HANDOVER 二·补十九 / WORKPLAN B1）。**B2 全知数据训练 MLP 叶子也已完成**（2026-11-22：
  B1 修正 harness 确认段 120 局 beam 157.8→165.5（+7.7 CI[+4.2,+11.2]）/ ensemble 0.5 166.9
  （+9.0）；within 用 learned 变差为负结果，只对 engine=beam 有益；生产 `leaf_model` 默认 None
  未打开，T2 A/B 再定；见 HANDOVER 二·补二十 / EXPECTIMAX「B2 学习叶子」）。
**B3 T5 机制建模也已完成**（2026-11-22：模拟器对齐真机「每回合基础 1 张 + 打完自动结束回合 +
SKIP 回 2 体力 + 取整 safeCeil」，RULES_REFERENCE 重写为逐条核验表，真机 39 回合配对回归；
重标定后整局 A/B 里 expectimax 显著强于 rules（+342~+429 评价点），B1 60 局 within 89.1→beam 95.7；
**B2 旧模型在 B3 规则下重测 FAIL，必须按新规则重采数据重训**；见 HANDOVER 二·补二十一）。
下一步 **T5 剩余机制**（审查倍率分段+联动惩罚、熱意、温存解除额外次数、fresh buff 差一回合、
P 道具数据），再上真机重验 F#42/#43 与 T3。

**剩余（跑一局验收）**
1. **上真机前先跑模拟器整局 A/B（不碰游戏）**：
   `sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --out out\sim_engine_ab.json`
   → 验收：0 `RuleFallbackBlocked`、0 error、满局 C+ 率 100%、单局模拟耗时正常；
   2026-11-21 实测 76 局（3 组种子）全绿，见 [HANDOVER 二·补八](HANDOVER.md)。
2. 按 [LIVE_RUN.md](LIVE_RUN.md) §0 自检；起跑必须带 `--ignore-user`（人别碰键鼠/别最小化），
   并带墙钟上限（默认 30 分钟，卡住会写 `episode-timeout` 停局）：
   `auto_produce.py 300 ep-<名字> --skip-home --engine expectimax --ignore-user --max-minutes 30`。
3. 验收点：整局 **不再出现"还有牌却 SKIP"**，也**不再出现 `fallback=…退回规则`**（搜索引擎已禁止回退 rules）；
   若出现 `[engine][BLOCKED]`，按后面原因修 OCR/卡表，别把 rules 加回来兜底。
   期中/期末分数、评价、时长记进 `docs/RUNS.md`；若分数仍低，看日志 `| eng=… fallback=…` 与
   `[unknown-card]` 定位是 OCR 还是策略问题。
4. 完成一局后把记录写进 `docs/RUNS.md`，再决定是否上 T3（开采集）。

**改哪儿**：`scripts/auto_produce.py`、`src/gkagent/tasks/produce_ui.py`、`docs/FAILURES.md`、`docs/RUNS.md`

**验收（DoD）**
- `docs/RUNS.md` 新增一局记录：起止/步数/时长/是否完成/评价/卡点；
- 完成时：评价 ≥ C+（课题达标）、时长 ≤20 分钟；未完成时：明确写出卡在第几屏、复现步骤、截图路径；
- `pytest tests/ -q` 仍全绿（改了识别/UI 逻辑必须补测试）。

**预算**：1–2 小时真机 + 30–60k token。

### T3（P0，依赖 T1 的稳定起跑）采集进程 ↔ 决策进程实时打通（原 item④）🟡（代码 + 离线预演已完成，差真机考试验收）
**目标**：bot 进入考试的那一刻，自动从采集数据拿到**当前这一场**的 seed / 支援编成 / 牌堆 / 配置回合，建 `ExamDrawPlan`；每回合手牌核对通过，2–3 回合内锁定牌序。

**已完成（2026-11-21 晚，a9537b0 起）**
1. ✅ `scripts/build_exam_setup.py --current`：只读最新 `StepAuditionStart`（不依赖 EndExamBattle），
   牌堆用 `reconstruct_deck.build_snapshots()` 现场重放；`config_turns` 输出多个候选（默认 9/11/12）。
   `--allow-finished` 用于对已结束的采集做离线核对。
2. ✅ `ExamPlanSelector`（[exam_plan.py](../src/gkagent/sim/exam_plan.py)）：逐回合用实机手牌**收窄候选**，
   唯一剩下即锁定（第 1 回合可能因 isInitial 卡相同分不出，第 2–3 回合收敛；实测采集局第 2 回合锁定）；
   全部淘汰会重置重试（有上限），过期数据不会无限烧 CPU。
3. ✅ `reconstruct_deck.build_snapshots()` 抽成函数（运行时可调用，不复制逻辑）。
4. ✅ `auto_produce`：进入考试时按文件 mtime **运行时重载** `out/exam_setup.json`、新考试换新 selector、
   考试结束打 `[exam-plan] summary`（锁定回合/候选/核对回合数）。
5. ✅ **2026-11-22 A5 离线预演（不碰真机）**：`scripts/verify_exam_plan_offline.py` 一条命令跑
   `--current --allow-finished` 候选（最新场 3 个：9/11/12）+ 四场 sweep，用采集 truth 驱动
   `ExamPlanSelector` → 候选全部收敛到 1、`locked_turn` = T2/T1/T1/T1/T2（≤3）、选中
   `config_turns` = 12/9/11/9/12 全等于真值、锁定后逐回合手牌核对全中；测试
   `tests/test_exam_plan_offline.py` 8 条（见 HANDOVER 二·补十八 / EXPECTIMAX §④）。

**剩余（需要游戏+采集进程）**
1. 开采集（`一键采集启动.bat`）→ 起 bot 到考试 → **考试进行中**另开一个进程跑
   `build_exam_setup.py --current`（默认输出 `out/exam_setup.json`）→ bot 下一帧自动重载并开始核对；
2. 验收日志：`[exam-plan] 重载/挂上` + `[exam-plan] summary` 里 `locked_turn` 2–3、`verified == 实战回合数`；
3. ~~离线兜底验证（不依赖真机）~~ ✅ 已完成（A5，见上第 5 条；`verify_exam_plan_offline.py`
   最新场锁定 T2/config_turns 12，四场 sweep 全对）。

**改哪儿**：`scripts/build_exam_setup.py`、`scripts/auto_produce.py`、`scripts/reconstruct_deck.py`、`src/gkagent/sim/exam_plan.py`

**风险**：traffic.jsonl 写入缓冲/时序；deck 快照与考试开始时刻的对齐；`forceEndScore` 提前结束时 config_turns 仍按配置回合（见 [HANDOVER 二·补二](HANDOVER.md#L113)）。
**兜底**：对不上就自动停用（现有设计），**绝不能**用错牌序。

> 2026-11-22 情报补充（**已实现事前检测**：`exam_risk.py` + `rng_risk` 字段 + bot 跳过候选）：考试 RNG 还有恐慌/搜索排序/随机选取/生成卡/随机移动等入口（见
> [QQ_GROUP_NOTES](QQ_GROUP_NOTES.md) 凌晨条目），我们的 K 模型未覆盖。牌组含这些效果的考试
> **known_draw 只能用到第一个此类事件**；T3 验收时用"纯牌组"考试跑，或在建 setup 时前置标记不可验。

**验收（DoD）**：真机一局考试的每回合核对通过（离线预演 A5 已通过：候选→1、`locked_turn≤3`、选中
真值、逐回合核对全中）+ selector 单测（已加 4 条 + A5 离线预演 8 条）+ 文档更新。
**预算**：60–100k token（代码 + 离线预演已完成，剩真机验收 ~20k）。

### T2（P0，依赖 T3）三引擎真机 A/B ⬜（+ net 第四臂：B11 v6 学生网已接线，2026-11-23）
**目标**：同偶像、同卡组、同 seed（能同 seed 最好），各跑 rules / expectimax / beam+全知 一局，比考试分。
**第四臂（可选）**：`--engine net`（B11 v6 学生网，2026-11-23 生产接线完成，见 EXPECTIMAX「B11 v6 生产接线」）——
small 确认段 v6 显著强于 v1（+0.6 CI[+0.2,+0.9]）。**r9-large（2026-11-23）large 首超 beam
（+14.2）但 small 显著回退（−0.42）→ 复合门未过、未入库**；**r10（同日晚，按场景 std
归一化）small 回退收窄至 −0.256 CI[−0.500,−0.012] 仍显著、large +29.1 保持 → 仍未入库**；
large A/B 可加 `--net-model out\ei_r9_v9_mix.json` specialist 臂（生产默认仍是 r6）：
**large 生产候选离线口径 r9/r10 最强（统计不可分），但须 small+large 双过才入库/进 F**，
net 值不值由真机 A/B 定。

**前置（2026-11-21 已做）**：真机之前先跑**模拟器整局 A/B**（`scripts/sim_engine_ab.py`）——
训练+考试都注入真 `LessonPolicy`，16 局×3 引擎全绿：0 `RuleFallbackBlocked`、0 error、C+ 率 100%，
expectimax 与 rules 评价点差异在噪声内（P50 5063 vs 5049）。模拟器不覆盖 UI/OCR 卡屏，
所以真机 A/B 仍要做；但"引擎选牌导致掉分/卡死"这一层已先排掉。

**步骤**
1. 引擎开关（**已接线**）：真机 bot 读 `--engine` > `policy.json` 的 `produce.engine`；
   `lesson.engine` 只是 `LessonPolicy` 独立/单测默认（保持 rules，别只改它）。
   ```powershell
   auto_produce.py 300 ep-ab-rules   --engine rules
   auto_produce.py 300 ep-ab-exp     --engine expectimax
   auto_produce.py 300 ep-ab-beam    --engine beam --exam-setup out\exam_setup.json
   auto_produce.py 300 ep-ab-net     --engine net   # 默认入库 v6；--net-model 可换其它轮次
   ```
2. 每局看日志首行 `[engine]` 和每步 `| eng=…`：确认搜索真的在出牌，退回率（`fallback=`）多少。
3. 每局跑完：`scripts/extract_exams.py` 记录期中/期末分数、名次、三维；记 `docs/RUNS.md`。
4. 注意：**beam 只在有 `known_draw` 且核对通过时才生效**（否则自动退回 expectimax）——所以 T3 必须先做，否则测不出 beam。
5. 结论写回 [EXPECTIMAX.md](EXPECTIMAX.md)（新增"真机 A/B"小节）。

**验收（DoD）**：三局成绩表（考试分 + 评价 + 时长 + `fallback=` 次数）+ 明确结论"哪个引擎值得默认"。
**预算**：3 局×20 分钟真机 + 30–50k token。

### T4（P1）策略强度：V_leaf + beam 调优 ✅（B1 修评测 bug；B2 学习叶子：B3 前 +7.7；**B2-R 重训仍 FAIL、高预算验证也 FAIL → 学习叶子路线关闭，leaf 不进 T2 候选**）
**目标**：让"全知 + beam"的离线优势变成分数。~~当前证据：构造抽牌牌组 beam known−unknown **+44.6**，但真实牌组只有 **+3.0**，因为 leaf 估不准~~（旧口径；B1 已推翻"beam 弱于 within"的前提）。

**B1 完成（2026-11-22，见 [EXPECTIMAX](EXPECTIMAX.md)「T4 修正」/ HANDOVER 二·补十九）**
- 查到旧 beam 数字被评测执行器坑了：`eval_known_draw._execute_plan` 在「手牌打空自动结束回合」后
  又补一个 SKIP，**白丢下一整个回合**；within 不走该执行器，所以它的 143.1 是真的。
- 修正后 60 局配对（small，同牌组同 seed，`scripts/eval_t4_b1.py --games 60`）：
  beam unknown **164.0**（+20.9，CI [+14.4,+27.3]）、known **165.5**（+22.4，CI [+16.5,+28.4]）
  vs within **143.1**；决策门 **114.6% / 115.7% → PASS**（门槛 90%）。
- 受控 policy-evaluation 叶子（只对 beam 最深端点 rollout，within 策略 + canonical 缓存 + 5ms/回合）
  **中性**：与普通 beam 逐位相同。消融：`score_tiebreak=1e-3` 是真增益（+15.4/+11.8），
  branching=10 修正后无显著收益（旧 +19.9 是 bug 副产物）。
- 生产默认不改（expectimax / tiebreak=0）；T2 真机 A/B 时再把 `beam + tiebreak` 作为候选。
- **旧实验记录（已作废，勿引用 beam 列）**：2026-11-22 凌晨「beam 91.3→105.5→111.2」与
  rollout 叶子「analytic 111.3 / rollout 103.0」都来自同一条 bug 执行器。within 列、
  tiebreak 方向、learned leaf 三次失败（不走该执行器）仍有效。

**B2 完成（2026-11-22，见 [EXPECTIMAX](EXPECTIMAX.md)「B2 学习叶子」/ HANDOVER 二·补二十）**
- 数据：beam **全知**自对弈，叶子状态分布（`end_turn_state` 形态）+ on-policy 后续得分标签，
  26.5k 样本；模型 104 维结构化特征 MLP（val r²=0.943）。
- 评测（B1 修正 harness）：选择段 seed 2000–2079 beam 解析式 **166.8 → learned 173.7（+6.8）/
  ensemble 0.25 174.4（+7.5）**；**确认段 seed 3000–3119（120 局）beam 157.8 → 165.5
  （+7.7，CI [+4.2,+11.2]）/ ensemble 0.5 166.9（+9.0，CI [+5.8,+12.2]）**；CLEAR 95→98.3%、
  PERFECT 33.3→50.0%；known 同向（+7.2~+7.8）。
- 负结果：within 用 learned 叶子 −3.3（只对 engine=beam 有益）；within 自对弈叶子中性；
  档位概率头在 beam 上灾难性变差；第二轮专家迭代未超过第一轮。
- 生产接线：`LessonPolicy` 新增可选 `leaf_model`/`leaf_model_weight`（**默认 None 不开**，
  加缓存）；T2 真机 A/B 候选（仅 engine=beam，建议 weight 0.25）。

**下一步（T2 真机 A/B 的前置）**
1. T5 剩余机制（~~审查倍率~~ ✅ B4、~~熱意~~ ✅ B5、~~温存解除额外次数~~ ✅ B5、
   ~~P 道具数据接入（离线 loadout）~~ ✅ B6、~~条件/效果语义~~ ✅ B8、~~持久倍率/modifier~~ ✅ B9、
   ~~生成卡确定式/卡名映射~~ ✅ B10；剩 fresh buff 差一回合（需真机截图）/ 随机生成卡 RNG /
   hold 保留区 / 真机培育侧列表）。**B2 按 B3+ 规则重训 ✅ 2026-11-23 完成（B2-R）：
   仍 FAIL（确认段 −7.2）；高预算验证（width8/300ms）也 FAIL（−4.4）→ 学习叶子路线关闭，
   学习叶子不进 T2 候选**；
2. T2 真机 A/B：同卡组 rules / expectimax / beam+全知 各一局（**去掉 learned leaf**，B2-R 负结果）；
3. 生产默认在 T2/T3 前保持 expectimax（leaf_model 不开）。

**B2-R 完成（2026-11-23，见 [EXPECTIMAX「B2 重训（B2-R）」](EXPECTIMAX.md) / HANDOVER 二·补三十四/三十五）**
- 旧模型 FAIL 复现（选择段 −26.1，与 B3 重测逐位一致 → B4–B10 对 small harness 零影响）；
  2000 叶子快照 vs `end_turn_state` 逐字段等价探针 + 温存→全力回合边界解除收益快照口径修正
  （`RecordingLessonSim._pre_end_turn_stance`，+1 回归测试，`test_b2_leaf.py` 12 条）。
- 重采 26,500 beam 全知叶子样本（3 批顺序跑；纯 on-policy 分数标签、**不加 PBRS 塑形**，
  auto-gakumas −26,884 负结果同向）→ MLP 104→96→48 val r²=0.906 / MAE 7.0 / σ=11.1。
- 确认段 120 局：unknown beam 94.9→learned **87.7（−7.2 CI[−9.5,−5.0]）** / known −11.5 /
  ensemble 0.75 中性；within_learned −19.9；σ×2/×4 更差（μ 排序本身有害，非校准）。
- **高预算验证（同日，用户指定）**：width8/300ms 选择段 80 局 seed 2000：beam 解析式 93.9→
  learned **89.4（−4.4 CI[−8.8,−0.0] 显著负）** / ens 0.75 +0.0（中性）→ **FAIL，不跑确认段**。
  收窄（−7.0→−4.4）主因是解析式基线自己变差（97.3→93.9），learned 绝对分几乎不动
  （90.3→89.4）；within 家族与 200ms 逐位相同（搜索提前收敛，墙钟 <80s）。
- **处置（路线关闭）**：生产 leaf_model 默认关闭不变；beam 默认解析式叶子；重训候选保留 out/，
  tracked 模型按用户指定回退旧版（两版都 FAIL、生产关闭故行为无差）；根因诊断已完成（锐利 σ 放大 + 价值-策略失配）；
  **高预算验证也 FAIL → 学习叶子路线正式关闭，转 C1**（用户指定）；
  不做第二轮迭代/档位头（已知负结果）；large 重采需先更新特征（预算外）。
  再下一候选：渐退式专家迭代（学 policy/advantage，**启动前先问用户**）。

**改哪儿**：`src/gkagent/sim/expectimax.py`（leaf）、`src/gkagent/sim/v_leaf.py`、`src/gkagent/sim/leaf_mlp.py`、`data/knowledge/b2_leaf_mlp_small.json`、`scripts/eval_*.py`
**验收（DoD）**：B1 已交（60 局配对 + EXPECTIMAX 更新 + 单测）；**B2 已交**（学习叶子配对增益
`beam 157.8→165.5（+7.7，CI 全正）`，负结果如实记录；`data/knowledge/b2_leaf_mlp_small.json` + 3 个脚本 + 11 条单测）。
**预算**：80–150k token（这是最难的一块，别一次会话硬啃）。

### T5（P1/P2）机制建模补齐（按官方 AI 对比表挑）🟡（B3+B4+B5+B6+B8+B9+B10 已做回合规则/审查倍率/熱意+温存解除/P 道具数据接入/条件+效果语义/持久倍率modifier/生成卡确定式+卡名映射）
**目标**：缩小"模拟器 vs 实战"偏差。

**已完成（B3，2026-11-22，见 WORKPLAN B3 / HANDOVER 二·补二十一）**：模拟器回合规则对齐真机
（每回合基础 1 张 + 打完自动结束 + SKIP 回 2 体力 + 取整 `safeCeil`）、`RULES_REFERENCE.md`
逐条核验表、真机 39 回合回合规则配对回归。

**已完成（B4，2026-11-22，见 WORKPLAN B4 / HANDOVER 二·补二十五）**：审查倍率分段 + 联动惩罚
（客户端真实公式 + 主数据 + 屏幕倍率进搜索）。

**已完成（B5，2026-11-22，见 WORKPLAN B5 / HANDOVER 二·补二十六）**：熱意独立整数资源
（出牌分加算、获得时 ceil、回合末清零/熱意延長、本牌適用倍数）+ 温存解除
（熱意 +5/+8、2 段固定元気 +5、+1 出牌次数；同回合可重复、回合边界也触发）+ 卡牌熱意来源接入。

**已完成（B6，2026-11-22，见 WORKPLAN B6 / HANDOVER 二·补二十七 / RULES_REFERENCE §5.3）**：
P 道具数据接入——`data/p_items_db.py`（对局 loadout `produce_item_ids` → `PItemSpec`，未知 id
显式上报）+ `exam_start` 触发时机（288 段素材；LessonSim 构造时先于 turn_start 结算）+
`ExamPlayableValueAdd → extra_plays`（51 段，取 `count` 列）；`local_bench` 从 gkbench 题模板
loadout 接入（`--p-items auto/off`）+ gkbench 提交从 `ctx.loadout`（公开配置、不含种子）接入；
离线 A/B hif 30 题×2 seed：greedy **+128.9（+3.36%，CI[+9.5,+248.4]）** / expectimax +149.6（+3.98%）。
仍缺：真机培育侧 P 道具列表（T6/D1 补采）、效果覆盖（gkbench 已知 72 道具 131 段 spec 只实现
31 段）、主道具附魔/回忆。

**已完成（B8，2026-11-22，见 WORKPLAN B8 / HANDOVER 二·补三十一 / RULES_REFERENCE §5.3）**：
P 道具**条件/效果语义第一批**——新语法 trigger id 从 id 后缀解析条件（`remaining_turn-N` /
`parameter_buff_up-N` / `stamina_up_multiple-N` / `full_power_point_get_sum_up-N` / …；
条件未知 22→**6 件**，16 件恢复）；指定卡名/手牌张数缺映射 → `trigger_known=False`
（103 件/185 段）保守跳过；**依赖换算**「X 的 N% 数值变为 Y」（65 段，`depends_on`+`percent`）、
「X 变为 0」（3 段）、固定/最大体力百分比体力消耗/回复（9 段）；新增
`turn_start_after`/`turn_interval`/`status_gain_interval`/`stance_change`/`stamina_reduce`
五类触发 + `LessonSim`/`ExpectState` 事件与累计量双镜。数据层已实现 **445→676/1849 段**、
gkbench hif 83 唯一 id **34→59/153 段**；离线 A/B greedy **+225.2（CI[+86.7,+363.6]）**；
全量 pytest **1067/1（1068 收集 / 77 文件）**。仍缺：持续倍率类 `ExamLessonValueMultiple`、
生成卡/modifier 类、指定卡名/手牌映射、真机培育侧列表。

**已完成（B10，2026-11-23，见 WORKPLAN B10 / HANDOVER 二·补三十三 / RULES_REFERENCE §5.3）**：
T5 剩余①②——**生成卡确定式 + 指定卡名/手牌张数映射**。新 card_meta（idol_unique 判据与参考
pIdol 交叉 340/342 零误报 + effectGroupIds + 日文别名）；`parse_card_search` 结构化
play_filter（234 件）/ zone_count（27 件）；`ExamCardCreateId` 确定式 11 段（手牌≥5 不生成 /
牌堆顶 / 弃牌堆，参考 addCardTo* + 生成卡 id 交叉验证）；`exam_start_after` 新时机；
**次数上限按道具计**（limit:N 口径修正）。触发未知 **103→3 件**、条件未知 **6→0**；
数据层 **1025→1042/1849 段**；greedy A/B **+797.5（+20.76%，CI[+399.0,+1250.1]）** /
expectimax +801.1（CI[+66.3,+1697.9]）；全量 pytest **1154/1（1155 收集 / 79 文件）**。
仍缺：随机生成卡（RNG 未知）、`ExamBuffConsumptionAdd`（保持 no-op）、hold 保留区、
真机培育侧列表。

**已完成（P1-1，2026-11-24，见 WORKPLAN P1-1 / HANDOVER 二·补四十四 / RULES_REFERENCE §5.4）**：
阶段1 首批——**全力回合 +1 出牌/保留牌回手/指針守卫 + のんびり指針（×0/解除/预约来源/
stance_leisure 直给）+ r10 行为探针**（残留 small 回退已非 v1 贪即时分，R9_ANALYSIS §9）。
BSD-3 参考引擎 + contest-fidelity 真机回放证据；LessonSim/ExpectState 双镜 + 叶子对齐；
评测牌组组成不变 → sim_engine_ab 重标定**改前/改后 64 局逐位相同（差异=0）**；36 条新单测，
pytest **1354/1（1355 收集 / 90 文件）**。仍缺：held 来源（P1-3）、lockStanceTurns（随 P1-3）、
card_play_interval_after 触发（2 件のんびり道具保守不触发）、~~handDecrease/pride（P1-2）~~ ✅ P1-2。

**已完成（P1-2，2026-11-24，见 WORKPLAN P1-2 / HANDOVER 二·补四十五 / RULES_REFERENCE §5.5）**：
阶段1 第二批——**④ handDecrease 抽牌修正**（cardsToDraw=max(3−Σ,0)，timed 列表合算/倒计时/
∞永久，只减回合开始抽牌；来源塔 gimmick ExamGimmickStartTurnCardDrawDown 12 段；nullifyDebuff
拦截未建模如实记）+ **⑤ pride 自尊**（resolveScore f min(好印象,干劲)×0.02 上限+0.5，prideTurns
回合末 -1；来源离线可确定：卡「我、绝不」turn=5 门槛干劲>=9 + P 道具「一笔入魂」turn=2/3
status_gain&好印象>=6&limit1，主数据↔参考 DSL 交叉）。BSD-3 参考引擎证据；LessonSim/ExpectState
双镜 + canonical + 叶子对齐；sim_produce MODELED 33→34、p_items.json implemented 1042→1056/1849
（modifier 371→385）；评测牌组/gkbench loadout 组成不变 → sim_engine_ab 重标定**改前/改后
64 局逐位相同（差异=0）**；36 条新单测，pytest **1389/1（1390 收集 / 91 文件）**。
仍缺：~~held 来源/lockStanceTurns（P1-3）~~ ✅ P1-3、~~ExamBuffConsumptionAdd（P1-4 评估 no-op）/nullifyDebuff 拦截~~ ✅ P1-4。

**已完成（P1-3，2026-11-24，见 WORKPLAN P1-3 / HANDOVER 二·补四十六 / RULES_REFERENCE §5.6）**：
阶段1 第三批——**⑥ hold 保留区建模 + lockStanceTurns 指針固定**。BSD-3 CardManager
（hold/enforceHoldLimit/holdThisCard/holdSelectedByTarget/moveHeldCardsToHand）+ TurnManager
（endTurn 只弃手牌）+ constants（FULL_POWER_EFFECTS lockStanceTurns==0 门）+ BuffManager.setStance
守卫 + Executor freshBuffs。`sim/hold.py` 13 族卡逐卡证据表（ExamCardMove values 恒空，
skill_cards.csv 行号交叉）；上限 2/跨回合保留/holdThisCard 不进弃牌除外/holdSelected 选牌
（known_draw/discard_order 同步）/moveHeldCardsToHand LIFO；lockStanceTurns（切磋琢磨
StanceLock turn=1，EOT+fresh 锁下一回合+setStance 守卫+全力进入门）；**B10 遗留
trigger_unknown 3 件清零**（hold 区张数条件：实现的觉悟 countCards[held]>=1 ↔ 叶える覚悟；
hotfix：咲季营养餐・改 period810_hotfix 三源证实非限定标记 ↔ 咲季の完全食・改）；
温存 2 段階直给 preservation2（7 段）。sim_produce MODELED 34→35、41 元组；implemented
保持 **1056/1849**（机制本就支持）；**large 评测牌组组成变化**（冲刺/积累 draw 近似移除，
保真度修正；small 不变）→ sim_engine_ab 重标定改前/改后逐局对照（见 §8 最近交接）；
46 条新单测，pytest **1435/1（1436 收集 / 92 文件）**。仍缺：target:held 保留区卡成长、holdCard P 道具来源
（那一天的塑料伞等文本未结构化）、~~ExamBuffConsumptionAdd（P1-4）~~ ✅ P1-4 评估 no-op、card_play_interval_after。

**已完成（P1-4，2026-11-24，见 WORKPLAN P1-4 / HANDOVER 二·补四十七 / RULES_REFERENCE §5.7）**：
阶段1 第四批——**nullifyDebuff 低下状态无效拦截 + ⑦ ExamBuffConsumptionAdd / countDebuffs 评估**。
BSD-3 Executor（executeAssignment :429 / executeCallAction :507 / executeSpecialAction :545：
nullifyDebuff>0 拦截一次 debuff 施加并 -1）+ constants（DEBUFF_SPECIAL_ACTIONS =
setScoreDebuff/decreaseFullPowerCharge/setHandDecrease；nullifyDebuff ∉ EOT_DECREMENT_FIELDS）。
`LessonSim/ExpectState.nullify_debuff` 消耗式计数器 + canonical + 快照往返 +
`intercept_debuff_entries` 纯函数，拦截已建模的 setScoreDebuff/setHandDecrease（列表逐条）。
来源 P 道具侧 ExamAntiDebuff values.count 11 段（偷懒的毛巾 + 塔 gimmick）。
**⑦ ExamBuffConsumptionAdd 保持 no-op**（doubleBuffCostTurns 语义/主数据 4 段/gkbench 22
loadout 如实记；卡模型不承载 buff 花费，88 张参考 buff-cost 卡 card_table cost=0、CardSpec
无 buff_cost 字段，无落点不猜）；**countDebuffs 无落点**（低下状態の数参考+主数据零使用）。
卡侧 4 SSR 族来源（values 恒空）/标量 DEBUFF_FIELDS 拦截/decreaseFullPowerCharge 留后续。
implemented **1056→1067/1849**（+11，modifier 385→396，p_items.json 仅 11 条记录变化）；
评测零落点 → sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；30 条新单测，
pytest **1465/1（1466 收集 / 93 文件）**。仍缺：卡侧 nullifyDebuff 来源、标量 DEBUFF_FIELDS
拦截、⑦ buff-cost 卡模型扩展（需先承载 buff 花费）、~~P 道具剩余效果语义（P1-5）~~ ✅ P1-5 首批。

**已完成（P1-5，2026-11-24，见 WORKPLAN P1-5 / HANDOVER 二·补四十九 / RULES_REFERENCE §5.8）**：
阶段1 第五批——**P 道具剩余效果语义补全（bounded batch）**：层数减少类（干劲/集中/全力值 -= N
夹取 ≥0，DSL motivation-=1/concentration-=1/fullPowerCharge-=2；全力值独立
PItemDelta.full_power_point_reduce 不计累计）+ 体力减少（ExamStaminaDamage 并入 STAMINA_LOSS，
cost-=1 genki==0 穿透）+ 好调N回合（ExamParameterBuff turn 列 → condition_turns，DSL
goodConditionTurns+=N）+ 好调依赖换算（好调的N%数值变为打分/集中，CONVERSION_SOURCES 加
好调:parameter_buff，DSL score+=goodConditionTurns*0.3）。BSD-3 + 主数据 + DSL 三重核实。
implemented **1067→1164/1849**（+97）、依赖换算 65→76（p_items.json 仅 24 条记录变化）；
**sim_produce 不引用 p_items → 评测零 P 道具结算** → sim_engine_ab 重标定改前/改后 64 局逐位
相同（差异=0）；38 条新单测，pytest **1503/1（1504 收集 / 94 文件）**。**留后续**（证据充分需
新机制，no-op 如实记）：好调增加量增加（setGoodConditionTurnsBuff）/元气增加无效
（nullifyGenkiTurns）/不安（uneaseTurns，delay）/塔 gimmick（低谷/紧张/弱气/体力回复无效）/
全力・强气效果卡打分（setFullPowerEffectBuff/setStrengthEffectBuff）/日文好調の%分（眠気卡条件）/
ExamParameterBuffReduce（触发未支持）。

**剩余（按对真机分数影响排序，每条都要补单测 + 文档核验表状态）**：
1. ~~**审查倍率分段 + 联动惩罚**~~ ✅ **2026-11-22 完成（B4）**：客户端公式（分数表分段折线 +
   审查基准联动惩罚 + 单精度取整）→ `sim/exam_multiplier.py` + 主数据解析 `data/exam_bonus.py`；
   模拟器按回合属性乘（含依赖分/回合末好印象），生产搜索读屏幕「舞蹈 207%」→ `attr=2.07`；
   真机夹具期中 **4.09/2.20/2.60×**、期末 **6.97/2.85/4.96×**；`tests/test_exam_multiplier.py` 21 条；
   剩余差距（不阻塞本项）：P 道具附魔/考试内生成卡未建模 → 逐分回放待后续。见 HANDOVER 二·补二十五；
2. ~~**熱意（enthusiasm）**~~ ✅ **2026-11-22 完成（B5）**：独立整数资源 + 温存解除 +5/+8 +
   卡牌熱意追加/増加/延長/本牌適用倍数；回合末清零/延長；`tests/test_t5_enthusiasm.py` 16 条；
   ~~剩余来源（のんびり/P 道具）未建模~~ のんびり来源 ✅ **P1-1 完成**（解除+10/预约来源）；
   P 道具熱意触发仍未接入。见 HANDOVER 二·补二十六 / RULES_REFERENCE §5.2/§5.4；
3. ~~**温存解除的额外次数/元气**~~ ✅ **2026-11-22 完成（B5）**：+1 出牌次数、2 段 +5 固定元気、
   同回合重复解除可叠加、温存→全力回合边界也触发。~~全力回合额外次数/保留牌未建模~~
   ✅ **P1-1 完成**（全力 +1/回手钩子/守卫；held 来源留 P1-3）。见 HANDOVER 二·补二十六/四十四；
4. ~~**P 道具数据接入（离线 loadout 侧）**~~ ✅ **2026-11-22 完成（B6）**：见上；
   **B7** 已把 catalog 补到上游 1115 件、gkbench 未知 id 清零；**B8** 已完成条件/效果语义第一批
   （见上）。**剩余**：真机培育侧列表（T6/D1）、持续倍率类/modifier 效果、主道具附魔/回忆。
5. **fresh buff 保护**（获得 buff 当回合末不扣 1，需真机逐回合截图核实）。
   → **E0 候选（§4 T9）**：先试作者包的离线培育（Selection Exam），若考试能跑通，
   可提供**无账号风险**的逐回合截图来源，替代/补充真机截图成本。
6. ~~**P 道具条件/效果语义（第一批）**~~ ✅ **2026-11-22 完成（B8）**：新语法 trigger id 解析 +
   依赖换算 + 固定/百分比体力 + 5 类新触发（见上）。
   ~~**P 道具持久倍率 / modifier 类效果（第二批）**~~ ✅ **2026-11-22 完成（B9）**：
   打分上升量增加/减少（`resolveScore` f/g）、好印象强化/追加发动、热意/集中/好印象/干劲/
   全力值增益倍率、绝好调/不调、费用修正、回合追加、温存/强气指針直给（20 类 target、
   369 段 / 298 件）；数据层 **1025/1849 段**、gkbench **103/153 段**；
   greedy A/B **+110.3（CI [+39.6,+193.3]）**；见 RULES_REFERENCE §5.3 B9。
   **剩余**：~~`ExamCardCreateId` 生成卡~~ ✅ **B10 确定式已实现**（随机基础卡 RNG 未知保持 no-op）、
   `ExamBuffConsumptionAdd`（强化状态花费卡机制不在模型里 → 保持 no-op）、
    ~~指定卡名/手牌张数~~ ✅ **B10 已结构化**（~~剩 hold 保留区 2 件 + hotfix 1 件保守~~
    ✅ **P1-3 清零**：hold 区建模 + period810_hotfix 非限定标记证实）、
   附魔/考试减益、fresh buff 差一回合（需真机逐回合截图；lockStanceTurns 已按参考 fresh 实现）。
7. **饮料**（官方 AI 直接不喝 = 最强剪枝，可作为 A/B 对照）。

**验收（DoD）**：每补一项 → 模拟器 4 局逐分回归仍一致（`tests/test_hajime_eval.py`）+ 新机制单测 + 对应文档小节。
**预算**：每项 40–80k token。

### T9（可选，2026-11-22 新增）作者四游戏整合包带来的三件事 🟡（B7 ✅ / C0 ✅ / E0 ⬜；一次会话只做 1 个）

**背景**：用户 2026-11-22 提供作者新的四游戏整合启动器包（215 MB，11-22 构建），已做静态
分析并归档 → [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)、提交 `ddf221f`。
结论：**帮助属参考级**——不能替换采集安装、拿不到算分公式，但有 3 个具体可做的事。
新会话按用户指定做**其中 1 个**（一次会话只做 1 个任务）；**建议顺序 B7 → C0 → E0**。
**B7 已于 2026-11-22 完成**（见下）；**C0 也已完成**（2026-11-22，纯文档判据吸收，见下）；
只剩 **E0**（需真机/独立副本实验，先问用户）。

#### T9-B7（推荐，纯离线）P 道具 47 条补全（更新 master 快照重建 `p_items.json`）✅ 2026-11-22 完成
- **事实**：包内 `mitm/masterTrans/ProduceItem.json` 给出 **1115 个 id**（=上游最新结构口径，
  与 [I18N_TODO.md](I18N_TODO.md) 的「本地 1068 / 上游 1115 / 缺 47」一致）；B6 里 gkbench
  的 **11 个未知 P 道具 id 全部在这 47 条里**。
- **做法（已完成）**：`data/cache/ProduceItem.yaml` 已是最新 1115 件（无需再拉）→
  [build_p_items.py](../scripts/build_p_items.py) 改为「本地中文 masterTrans 1068（逐段对齐）
  + yaml 独有 47 条（结构化字段/数值来自 yaml）」合并生成；47 条卡名用仓库已提交的自译表
  `data/i18n/translation_new.json`（47/47），**中文描述缺失**处 `text_zh=""`、`text_ja`
  保留日文并标 `i18n_text_source="ja"`；新触发 id 没有中文触发句 → `condition_known=False`
  （22 件 / 46 段 spec），`apply_passive` **保守跳过**（不猜条件）→ 重建
  `data/knowledge/p_items.json`（1068→1115）→ 更新测试预期（72 已知/11 未知 → 83/0）→
  `local_bench --p-items auto` 重跑覆盖率与 A/B → 文档同步。
- **结果**：catalog **1115 件 / 1849 段 spec / 已实现 445 段**（B6: 1068/1764/421；
  条件未知 46 段另计）；gkbench 505 题模板 **83 唯一 id 全已知、未知 0**；A/B hif 30 题×2 seed：
  greedy **3840.7→3969.7（+128.9，+3.36%，CI[+9.5,+248.4]）**（与 B6 逐位相同——新道具目前
  0 分贡献）、expectimax 3732.0→3953.6（+221.5，CI[−71.4,+514.4]，墙钟抖动）；新增 3 条测试；
  全量 pytest **1054/1（1055 收集 / 76 文件）**。
- **DoD**：catalog 1115 件且 47 条都有 spec 段 ✅；gkbench 505 题模板未知 id = 0 ✅；
  全量 pytest 全绿 ✅；`local_bench` 覆盖率提升（30 题样本：147 已知/0 未知、198 段 spec、
  实现 35 段）并有配对 A/B 新数字 ✅；文档数字同步 ✅。**不碰真机/账号。**
- **如实记录**：新增 47 条目前不改变离线分数（条件未知保守跳过 + 剩余为未实现效果类型/育成期
  触发）；下一步的分数空间 = P 道具**条件/效果语义**，不是数据缺失。
  细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) / HANDOVER 二·补二十九。

#### T9-C0（低成本）采集/更新可靠性经验吸收 ✅ 2026-11-22 完成
- **事实**：作者这版已经把「游戏更新后采集/更新断链」的坑踩过并修了：官服
  `x-error-code=2004` 识别、`http1_bridge` 丢失客户端版本/平台/会话头、协议 hash/master
  表结构变化判据、TLS 代理失败回退直连、CA 精确指纹/有效期、系统代理恢复、只停本目录服务。
- **做法**：把上述**判据/症状/处理**整理成检查清单写进
  [TROUBLESHOOTING.md](TROUBLESHOOTING.md)（新小节「游戏更新/协议/代理/TLS 断链」）+
  [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md)（对应四个坑的补充），链接
  `LOCAL_LAUNCHER_20261122.md`；**只写结论，不拷代码**。
- **DoD**：文档新增检查清单（触发条件→症状→处理→参考文件），pytest 不变；
  不新增依赖/数据。
- **预算**：~10–20k token。
- **落地（2026-11-22）**：[TROUBLESHOOTING §四](TROUBLESHOOTING.md) 新增「游戏更新 / 协议 /
  代理 / TLS 断链（外部经验吸收，本项目待验证）」——先给「先分清操作再读错误码」，再给
  **13 条清单**（触发→症状/证据→处理→参考）：① `System/Check` 200 空体 + `x-error-code=2004`
  = 客户端太旧；② DMM 更新会还原 hook DLL（模式判定别用 SameFile）；③ 协议变更关键词 + 停止
  自动更新；④ master 清单结构/长度/SQLCipher 判据（64-hex version、pack 名/文件名/key/size/
  URL host 规则、pack≥100）；⑤ 版本哈希不透明（不按文件时间判新旧、单份回退槽、别动
  `Master_Get` 夹具）；⑥ `http1_bridge` 丢客户端版本/平台/会话头 + 不透传业务错误头 + 缺
  `grpc-status` 当成功；⑦ `Auth/Login` `req_body_len` 865 正常/833→1003、`x-p-s` 需 DMM 常驻；
  ⑧ 上游端口写死 7897 → 10061/`OFFLINE-FALLBACK`；⑨ 停服务顺序（先还原系统代理再停进程，
  反序 = 全机断网事故）；⑩ CA 精确指纹+有效期、TLS 回退直连两条都校验/不重复 POST；⑪ 代理
  残留/更新后自清理；⑫ 诊断收集与脱敏；⑬ 更新/采集互斥与「停止服务」优先级。另加 §4.2 与本
  项目 1.3–1.9 的对应表（哪些我们已踩过、哪些待验证）。[CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md)
  新增「游戏客户端大版本更新后自检」**8 步**（DMM 更新 → 核对 hook/traffic → 证书/TLS → 上游
  代理 → 票据 → 协议/主表变化即停 → `build_exam_setup`+`verify_exam_wiring` 重建核对 → 自清理），
  并修正「离线培育/作者暂不做」的过期说法（包内已有 `produce_runtime.py`，无考试结算）。
- **结果**：纯文档，**未改代码/未加依赖/未动数据**；复跑全量 pytest 仍 **1054 passed / 1 skipped
  （1055 收集 / 76 文件）**；一次会话只做 1 个任务。细节见 HANDOVER 二·补三十。

#### T9-E0（可选实验，需要真机/独立副本）离线培育测试台
- **目标**：验证作者包能否离线跑 produce-007（Selection Exam）并推进到**考试**；若可 →
  作为 **fresh buff 逐回合截图 / T1 UI 回归**的零账号风险来源（考试机制与 produce 类型无关）。
- **约束**：**独立游戏副本**（第 3 份，勿动 `D:\Games\Gakumas` 与 `C:\GakumasLocal`
  采集安装）；不覆盖现有采集链路；若必须 DMM 首次抓参按作者文档，别用主账号做未知操作。
  先问用户是否投入（要碰 GUI/DMM）。
- **已知不确定性**：`produce_runtime.py` 只看到 lesson/event/shop/rest 处理，**没有
  Audition/Exam 处理**（考试算分在客户端）→ 很可能考试日卡住/未实现；本实验就是确认这点。
- **DoD**：明确结论（能否到考试；卡在第几屏/日志/截图证据路径）；若可，标注能服务哪些
  离线素材需求（fresh buff/T1 回归）；更新 `LOCAL_LAUNCHER_20261122.md` 与 HANDOVER。
- **预算**：半天左右（含装包/启动）+ 用户配合；结果可能是「不可用」也算完成。

### T6（P2）补采数据（需要真机 + 采集）⬜
- **非 5 NPC 的 produce 类型**：K 公式的 `npc_count*turns` 项只验过 5 NPC（[HANDOVER 四①](HANDOVER.md#L266)）。
- **11-20 期末 T9 回合内重洗**：考试内生成卡导致 grave 不可重建；需带更多日志信息采集或换一局同类样本。
- **同局两次重洗**：验证 `oracle.reshuffle` 的 RNG 快照第二次是否需推进（当前只按"一次重洗"快照，[EXPECTIMAX L505-510](EXPECTIMAX.md#L500)）。

**验收（DoD）**：`verify_shuffle.py` 新增样本全过 + 测试加回归（参考现有 6 条"实战回合算 K 会错"防线）。
**预算**：采集 1–2 小时 + 40–80k token。

### T7（P2）可靠性工程（照 hiro 三条原则补）✅（① 动作前互验 C1；②③ P1-6，2026-11-24 完成）
1. ~~**动作前互验**：点之前预算"下一帧应读到什么"，对不上丢弃重读（照 hiro 原则 3）~~
   ✅ **C1 已落地**（TapExpectation/TapGuard：预算→互验→retap/lost/moved；见 WORKPLAN C1）；
2. ~~**纯函数状态 + 离线重放**：`run_record` 有雏形，改成"同观测序列 → 同状态 → 可逐步比对"~~
   ✅ **P1-6 已落地**：`data/run_replay.py`（apply_event 纯函数 + 深不可变 RunState +
   fingerprint 两遍重放逐位相等 + compare_replays 逐步比对首个分歧步 + legacy_events 旧格式
   确定式重建 + consistency_check 三方对账）；RunRecorder 增量 events 观测日志（旧文件续跑
   先重建）；`scripts/replay_run.py --verify/--compare`（退出码=DoD）。
3. ~~**自动复盘页**：每局生成逐回合页 + 人工标注转回归用例~~ ✅ **P1-6 已落地**：
   `report/review_page.py` 自包含 HTML（逐回合/考试/结算/重放一致性/C1 逐步轨迹/行内标注
   导出导入）+ `report/annotations.py` 标注转回归（verdict=bad 带 expected → 整态/分类结论
   冻结进 `tests/fixtures/review_regressions.json`）+ `scripts/review_page.py` /
   `scripts/annotations_to_regression.py`；auto_produce 局末自动生成（`[review]`）。

**验收（DoD）**：新增测试（互验的假观测序列）✅ C1 68 条 + P1-6 61 条（假观测序列重放/逐步
比对 38 + 复盘页/标注闭环 20 + 标注回归夹具 3）；一局自动复盘页样例 ✅
[docs/review_sample.html](review_sample.html)（ep-rule1 真实记录 + 合成演示轨迹显著标注）；
`LIVE_RUN.md` 更新 ✅ §2.1。细节见 WORKPLAN P1-6 / HANDOVER 二·补五十。
**预算**：60–120k token（剩余 ②③）→ 已用完结项。

### F0（P0，2026-11-22 新增）gkbench 官方种子校准收尾 ✅（2026-11-22 完成：366/384）
**目标**：用 gkbench 官方固定种子题的 `check.hand` 把我们的洗牌模型命中率从 74.5% 推近 100%，
并校准考试起点（`check.stamina/turn/rules`）——这是 F1/F2 之前的口径基础。

**已完成**（详见 [GKBENCH.md §4.5](GKBENCH.md) / HANDOVER 二·补二十四；数据在
`data/bench_local/gkbench_dl/`，gitignore）：
- 新增 [verify_gkbench_shuffle.py](../scripts/verify_gkbench_shuffle.py)：384 组官方 `check.hand`
  逐张核对 + 起点校准（只读本地种子+主数据，不联网/不读令牌；`--json/--verbose/--stage-npc/--variant-initial`）。
- **initial 修正**：主数据 `isInitial` 按 **base 卡 id**（覆盖 +1 等强化变体）+ deck 里
  `g_effect-initial_add` 自定义卡；**npc 修正**：人数不是 stage 常数，按 idol 卡
  （`IdolCard.produceStepAuditionDifficultyId` → `ProduceStepAuditionDifficulty` → NPC 组行数）——
  選抜=5，本戦多数 3 人制=2、**jsna 4 人制=3、fktn 2 人制=1**；缺 step 字段用 `round` 兜底。
- 结果：**286/384（74.5%）→ 366/384（95.3%，逐张 1125/1155=97.4%）**；按 stage sel1 60/60、
  sel2 55/55、sel3 56/57、main1 96/97、main2 99/115；逐题 311/329 全中。
- 剩余 18 组根因：**initial 0 / turnStartDistribute 0 / 牌序 0 / 其他 18**（15 组考试初始牌组
  `ExamInitialDeck` 未建模；3 组 `kllj-3-005` 开局 +1 手牌）——没有一组是洗牌模型错。
- 起点校准：`check.turn=1/score=0`（全部）；`rules=55`（全部，commit `f4d9e6e6148d` 339 组）；
  `stamina` 369/384 == `starting_stamina`，15 组差 = 偶像卡 P 道具考试开始附魔常量
  （shro-3-016 −28、atbm-3-015 +5、kllj −1、ssml/kcna +6、shro-3-007 +1）→ 基准复算用
  `check.stamina` 覆盖 loadout 值。
- DoD 达成；剩余 `ExamInitialDeck`/开局加牌机制留给 F1（需官方引擎或更多样本），不阻塞 F1/F2。

### T8（P3，低成本）情报与决策记录 🟡（持续；2026-11-23 新增 auto-gakumas 分析）
- 每完成一个任务：更新 `QQ_GROUP_NOTES.md` / `HIRO_VIDEO_NOTES.md`（有变化时）、写一条 ADR（`ARCHITECTURE.md`）。
- 只在有明确收益时更新；别为写文档而写。
- **2026-11-23**：用户 B 站发现 **tactfullotto/auto-gakumas**（零 LLM / Android ADB /
  每战在线 PPO + SO-ISMCTS，H.I.F 本戦实机 2回戦 1.59M，B 站宣称 S4+）→
  [AUTO_GAKUMAS_NOTES.md](AUTO_GAKUMAS_NOTES.md)（公开资料静态分析，未运行未拷贝；
  **无许可证 → 禁止拷代码/数据**）；COMPARE §2/§3/§7 + PROVENANCE §4/§5 已同步。
  可吸收候选（须用我们主数据重验）：回忆 Stage 级限 1、干劲经济守卫、饮料 #19/#25 门控、
  B2 重训「纯分标签不加塑形」（其 PBRS 负结果 −26,884 与我们 B2 负结果同向）。

---

## 5. 里程碑建议（按会话切分）

| 里程碑 | 内容 | 完成标志 | 预估 |
|---|---|---|---|
| M1 | T1 跑完整局 | RUNS.md 有完整一局记录 | 1 个会话 |
| M2 | T3 实时打通 | 真机考试 `[exam-plan] verified` | 1 个会话 |
| M3 | T2 三引擎 A/B | 同卡组三局成绩表 + 结论 | 1 个会话 |
| M4 | T4 leaf 调优 | 真实牌组配对评测有显著提升 | 1–2 个会话 |
| M5 | T5/T6 机制+数据 | 模拟器回归不破 + 新样本全过 | 2–3 个会话 |
| 终态 | **真机评价 A（10237+）** | 同账号同卡组追平/超过手动 | — |

---

## 6. 路径 / 命令速查（交接必用）

```
采集数据        C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl
考试牌堆快照    C:\GakumasLocal\GakumasUnlock\out\deck_snapshots.json
逐回合真值      C:\GakumasLocal\GakumasUnlock\out\exam_truth.json
考试牌序 setup  D:\Games\gakumas-agent\out\exam_setup.json     （gitignore，可重建）
主数据库        D:\Games\gakumas-agent\data\hiro\vendor\gakumas-player\data\master
策略配置        D:\Games\gakumas-agent\data\knowledge\policy.json
真机日志        D:\Games\gakumas-agent\data\auto\auto_log_<ep>.log + step_*.png
```

```powershell
# 单场/全量考试牌序数据（生产接线用）
.venv\Scripts\python.exe scripts\build_exam_setup.py
# T3：当前这场考试的候选（考试进行中也能跑；bot 会运行时重载并逐回合锁定）
.venv\Scripts\python.exe scripts\build_exam_setup.py --current
# 离线核对 --current（对已结束的采集；真机没在考试时用）
.venv\Scripts\python.exe scripts\build_exam_setup.py --current --allow-finished --out out\exam_setup_current_test.json
# A5 T3 离线预演（--current 候选 + 四场 sweep 用 truth 驱动 ExamPlanSelector；退出码 = DoD）
.venv\Scripts\python.exe scripts\verify_exam_plan_offline.py --refresh
# 生产接线端到端核对（36/36 手牌、3/3 重洗）
.venv\Scripts\python.exe scripts\verify_exam_wiring.py
# F#42 课程帧回放回归（真机课程截图 → LessonReader → expectimax 决策，最后一个用例不选 buff）
.venv\Scripts\python.exe -m pytest tests\test_lesson_play_f42.py -q
# F#43 结果页空转回归（真机外出饮料帧 → read_fast → decide 必须点选项行；P 费不当飘字）
.venv\Scripts\python.exe -m pytest tests\test_produce_ui_f43.py -q
# 任意真机帧走生产链路（OCR→decide）看判定/点击：离线复现"某一步为什么点这里"
.venv\Scripts\python.exe scripts\probe_frame_decide.py 21
# 批量扫截图按屏幕分类挑 fixture（目录/glob/单帧；--screen/--contains/--json/--limit）
.venv\Scripts\python.exe scripts\scan_frames.py "data/auto/step_*.png" --json out\scan_frames.json
# A4 真机帧回放（六类关键屏；需要日文 OCR 模型，缺模型自动 skip）
.venv\Scripts\python.exe -m pytest tests\test_frames_replay_a4.py --basetemp=data/pytest-tmp-a4
# 扫本地截图找事件选项屏（混合预扫用，命中才打印）
.venv\Scripts\python.exe scripts\scan_event_frames.py data\auto --keywords ドリンク ヨーグルト
# 上真机前：模拟器整局 A/B（训练+考试都注入真 LessonPolicy；0 blocked/0 error/C+率）
.venv\Scripts\python.exe scripts\sim_engine_ab.py --episodes 16 --engines rules,expectimax --budget-ms 800 --out out\sim_engine_ab.json
# 离线配对评测：known_draw / beam / full-info（重洗后段全知；注意 beam 必须用修正后的执行器）
.venv\Scripts\python.exe scripts\eval_known_draw.py --games 40 --scenario small --policy beam --full-info
# B1 T4 修正后的配对评测（within / beam / beam+frontier；退出码 = 决策门）
.venv\Scripts\python.exe scripts\eval_t4_b1.py --games 60 --json out\t4_b1_tb.json
# B2 学习叶子：采数据（beam 全知自对弈）→ 训练 MLP → 配对评测（退出码 = B2 判定）
.venv\Scripts\python.exe scripts\build_b2_dataset.py --games 3000 --policy beam --known --out out\b2_leaf_beam_known2.npz --seed 600000
.venv\Scripts\python.exe scripts\train_b2_leaf.py --data out\b2_leaf_beam_known.npz out\b2_leaf_beam_known2.npz out\b2_leaf_beam_strong.npz --out data\knowledge\b2_leaf_mlp_small.json --hidden 96 48 --epochs 700
.venv\Scripts\python.exe scripts\eval_b2.py --leaf-model data\knowledge\b2_leaf_mlp_small.json --games 120 --seed 3000 --info unknown known --ensembles 0.25 0.5 --json out\b2_eval.json
# B2 单测（叶子特征/快照标签/模型存取/生产接线）
.venv\Scripts\python.exe -m pytest tests\test_b2_leaf.py -q
# 真机跑局（引擎：--engine > policy.json produce.engine > 默认 expectimax；rules 只用于 A/B 对照）
# --max-minutes 默认 30：卡住会写 episode-timeout 主动停局，不再无限空转
.venv\Scripts\python.exe scripts\agent_cmd.py shell --command "D:\Games\gakumas-agent\.venv\Scripts\python.exe D:\Games\gakumas-agent\scripts\auto_produce.py 300 ep-xxx --skip-home --exam-setup out\exam_setup.json --engine expectimax --max-minutes 30" --timeout 2400
# 考试分数提取（A/B 对比用）
.venv\Scripts\python.exe scripts\extract_exams.py
# 一局体检
.venv\Scripts\python.exe scripts\episode_report.py ep-xxx
# P1-6 纯函数状态重放（同观测序列→同状态→逐步比对；--verify 退出码=DoD）
.venv\Scripts\python.exe scripts\replay_run.py --episode ep-xxx --verify
.venv\Scripts\python.exe scripts\replay_run.py --episode ep-a --compare data\runs\ep-b.json
# P1-6 自动复盘页（逐回合+逐步轨迹+行内标注；auto_produce 局末也自动生成 out/review/<ep>.html）
.venv\Scripts\python.exe scripts\review_page.py --episode ep-xxx
# P1-6 标注闭环：复盘页导出 annotations_<ep>.json → 回归用例夹具（tests/test_review_regressions.py 逐条守）
.venv\Scripts\python.exe scripts\annotations_to_regression.py annotations_ep-xxx.json
```

---

## 7. 坑与红线（先看，别踩）

| 类别 | 内容 |
|---|---|
| 四条铁律 | ① 不碰 `D:\Games\Gakumas\gakumas`（用户在用）；② 采集必须 `GKM_UNLOCK=0 / GKM_FORGE=0 / GKM_STATIC_USER=0`；③ `data/hiro/` 是 AGPL 只参考；④ 成本纪律（见 [HANDOVER 八](HANDOVER.md#L404)） |
| 真机 | 一局只允许一个 `auto_produce` 进程；窗口 540x960、不能最小化；游戏重启后必须重启 `GDEAgent`；`data/STOP` 要清 |
| 卡死上限 | `auto_produce --max-minutes 30`（默认 30，0=关闭）：超时写 `episode-timeout` failure 主动停局，不许无限空转（用户 2026-11-21：见过卡两个多小时还跑到 C） |
| 跳过红线 | **SKIP 只在所有牌都付不起时允许**（用户 2026-11-21 指定）；读不到分/费用=去修 OCR/卡表，不许跳过补偿。`--ignore-user` 是无人值守跑整局的默认参数 |
| 规则回退 | **bot 不许回退 rules**（用户 2026-11-21）：搜索失败 = `[engine][BLOCKED]` 中止本局 + 修 OCR/卡表/参数，不许静默改用 rules 兜底；`--engine rules` 仅 A/B/离线；`allow_rule_fallback=True` 只是代码级调试开关（policy.json 不可配） |
| 快速路径 | 课程/加载帧的模板快速路径会吞掉遮罩弹窗（回合结束确认框、通信错误弹窗）：新增弹窗必须配"同屏重复→强制整屏 OCR"的逃生门 |
| 全知搜索 | 牌序**核对失败自动停用**是设计（宁可用期望模型也不用错牌序）；离线回放里策略出牌与实机不同会在重洗前停用，属正常 |
| 课程/考试 HUD | 课程右上角是**培育属性值**（不是课程分，`LessonState.attr`），课程分 = 属性值 − 开课基线；正中圆环「CLEAR截止 / PERFECT截止 N」是**还差 N 分**（不是过关线）。`LessonReader.read(kind="lesson")` 已换算好 `score/gauge/perfect/goal`；新读屏字段别再把语义弄反（F#42 就是这么 0 分的） |
| 出牌上限 | **游戏默认每回合只能出 1 张牌**（额外出牌来自卡效果 `ExamPlayableValueAdd`/P 道具），课程和考试都成立；搜索 `play_limit=1` 是刻意的，别改回 3（否则会偏好"buff+补刀"→ 0 分）。模拟器 `plays_per_turn` 已在 B3 对齐成 1（模拟器/评测/整局 A/B/`local_bench` 全部默认 1，别改回 3；`RULES_REFERENCE.md` §1 有证据与回归） |
| 配置陷阱 | 引擎优先级：`--engine` CLI > `policy.json` 的 `produce.engine`（真机 bot）> 默认 **expectimax**（bot 入口；`LessonPolicy` 自身默认仍是 rules，供离线/单测）；`lesson.engine` 只作 `LessonPolicy` 独立使用/单测默认（保持 rules，别只改它）。每局日志首行 `[engine]` 写明实际用了谁。OCR 模型优先级：`OcrEngine(config_path=)` > `GKAGENT_OCR_CONFIG` > 本地 `configs/ocr_jp.yaml`（下载脚本生成）> 内置中文模型；日志首行 `[ocr] 模型=` 可确认；配置/模型文件缺失**直接报错**，不静默回退中文模型 |
| 数据 | 主数据缺 11-21 新卡：`verify_shuffle.py` 用 `SUPPLEMENT_*` 兜底，更新主数据后可删；`out/` 不进 git |
| 截图归档 | `data/auto/step_NNN.png` 会被**后续跑局轮转覆盖**：关键屏要及时归档进 `tests/fixtures/`（A4 已归 8 张，README 有溯源表）。回合结束确认框的真机帧就是这么丢的（扫 1352 张 0 命中），下次真机跑局出现时补拍 |
| 时间口径 | 期中考试有 `forceEndScore` 提前结束，但 K（洗牌前 RNG 消耗）**按配置回合**算，不是实战回合 |
| 提交 | 一次任务一个 `feat(...)` 提交（含测试+文档），再一个 `docs(handover): 补提交记录哈希`；`.gitignore` 已忽略 `out/` |
| 存档 | 私有存档/私有仓库见 [ARCHIVE.md](ARCHIVE.md)：`scripts\archive_private.ps1`（bundle+裸仓库+采集数据备份，`-Push` 推 Gitee 私有仓）；**只能私有** |

---

## 8. 交接程序

1. **开新会话**：工作目录 `D:\Games\gakumas-agent`，第一句话用本文件开头那段。
2. **先跑 §2 基线**（四条必跑；⑤ F0 gkbench 核对可选，数据缺失就跳过），不绿先修基线。
3. **挑任务**：按下方「多会话路线图」队列取 **1–3 个任务**（2026-11-23 晚用户确认放宽；小任务合并一批，重的单独一个；成本纪律：上下文 >3 小时/20 万 token 就该换会话）。
4. **完成后**：
   - 更新 §4 该任务状态 ⬜→✅，并把实测数字写进正文；
   - 更新相关文档（任务里写明的那些）；
   - 提交代码 + 文档 + 测试，再补一条哈希提交；
   - 在 [HANDOVER.md](HANDOVER.md) 的提交记录里加一行。
5. **写不清=没完成**：DoD 必须能用命令/数字验证；"感觉能跑"不算。
6. **发用户下一会话开场白**（用户 2026-11-23 晚指定，每次必做）：准备开新对话时，给用户一份**可直接粘贴**的开场白——含工作目录 / HEAD（git log -1）/ 读文档顺序 / §2 基线期望数字 / Hindsight 状态（**已停用**，注明不用记忆工具）/ **下一会话具体任务（按 §8.0 队列）** / §4 硬约束 / 完成后交接+再发开场白。让用户开新对话直接粘贴即可接续。

### 8.0 多会话路线图（2026-11-23 晚用户确认）

**用户选定 A 顺序：先补离线规则 → 重采 → 练学生 → 真机 → 上网站跑算法；每会话 1–3 个任务（小任务合并），从现在起开新对话做。**
**两条补充（用户指定）**：① **现有学生/老师数据与模型全部保留**（不覆盖不删），新规则下另采新 seed 块练新批，**等新批练出来再新旧对比**；② **旧路线图（WORKPLAN 总序列 + 本文 §4 T1–T9）未完成项全部并入本路线图**（下方逐项映射，无遗漏）。
总顺序：**阶段1 离线补未知（含 T5 剩余/T7②③）→ 阶段2 重采+练学生（新旧对比，small+large 双过入库）→ 阶段3 真机（T3→T1→T2 + T6/D1 补采 + E0）→ 阶段4 gkbench F1/F2 → 阶段5 收尾 G**。
每会话从队列取 1–3 个（重的单独一个），做完更新状态+提交+开新对话。

**阶段 1 · 离线补未知（练学生前；改模拟器规则的项参考引擎 gakumas-tools BSD-3 有据才做，不猜）**
- **P1-1** ✅ **2026-11-24 完成**：① r10 决策行为探针（R9_ANALYSIS §9：残留回退已非 v1 贪即时分，通道 2 漂移噪声）② 全力回合 +1 出牌/保留牌回手（FULL_POWER_EFFECTS/FULL_POWER_CHANGED_EFFECTS + setStance 守卫；held 来源留 P1-3）③ のんびり指針（×0/解除收益/预约来源/stance_leisure 直给）；36 条单测，pytest 1354/1（1355 收集 / 90 文件）；RULES_REFERENCE §5.4；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0，牌组无来源）
- **P1-2** ✅ **2026-11-24 完成**：④ handDecrease 抽牌修正（cardsToDraw=max(3−Σ,0)，timed 列表；塔 gimmick 12 段来源；nullifyDebuff 拦截未建模如实记）⑤ pride 自尊（resolveScore f min(好印象,干劲)×0.02 上限+0.5；**来源离线已确定**：卡「我、绝不」turn=5 门槛干劲>=9 + P 道具「一笔入魂」turn=2/3，主数据↔参考 DSL 交叉）；36 条单测，pytest 1389/1（1390 收集 / 91 文件）；RULES_REFERENCE §5.5；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0，牌组/loadout 无来源）；implemented 1042→1056/1849
- **P1-3** ✅ **2026-11-24 完成**：⑥ hold 保留区建模（上限 2/跨回合保留/holdThisCard/holdSelected/moveHeldCardsToHand LIFO，13 族卡证据表；lockStanceTurns 切磋琢磨 EOT+fresh 锁下一回合+守卫+全力进入门；B10 遗留 trigger_unknown 3 件清零：hold 区张数条件 实现的觉悟 + hotfix 咲季营养餐・改；preservation2 直给 7 段）；46 条单测；RULES_REFERENCE §5.6；implemented 保持 1056/1849；large 评测牌组组成变化（冲刺/积累 draw 近似移除，保真度修正；small 不变）→ sim_engine_ab 改前/改后逐局对照（见 §8）
- **P1-4** ✅ **2026-11-24 完成**：⑦ `ExamBuffConsumptionAdd` buff-cost 卡评估**保持 no-op**（参考 doubleBuffCostTurns 语义/主数据 4 段/gkbench 22 loadout 如实记；卡模型不承载 buff 花费，88 张参考 buff-cost 卡 card_table cost=0、CardSpec 无 buff_cost 字段，无落点不猜）+ **nullifyDebuff 拦截落地**（P1-2 遗留；消耗式计数器拦截 setScoreDebuff/setHandDecrease，P 道具侧 ExamAntiDebuff count 11 段；卡侧 4 SSR 族/标量 DEBUFF_FIELDS 拦截延迟）+ **countDebuffs 无落点**（低下状態の数参考+主数据零使用）；30 条单测，pytest 1465/1（1466 收集 / 93 文件）；RULES_REFERENCE §5.7；implemented 1056→1067/1849；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0，评测零落点）
- **P1-5** ✅ **2026-11-24 完成**：⑧ P 道具剩余效果语义补全（bounded batch：层数减少类 干劲/集中/全力值 -= N 夹取 ≥0 + 体力减少 ExamStaminaDamage + 好调N回合 ExamParameterBuff turn 列 → condition_turns + 好调依赖换算 好调的N%数值变为打分/集中；BSD-3 + DSL 三重核实）；38 条单测，pytest 1503/1（1504 收集 / 94 文件）；RULES_REFERENCE §5.8；implemented 1067→1164/1849（+97）、依赖换算 65→76；**sim_produce 不引用 p_items → 评测零 P 道具结算**，sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；**留后续**（证据充分需新机制，no-op 如实记）：好调增加量增加/元气增加无效/不安/塔 gimmick/全力・强气效果卡打分/日文好調の%分/ExamParameterBuffReduce
- **P1-6** ✅ **2026-11-24 完成**（T7②③，离线可靠性工程，**不改考试规则、不作废 B11 数据**）：⑨ 纯函数状态重放（`data/run_replay.py` apply_event 无副作用/深不可变 RunState/同观测序列两遍重放指纹逐位相等/compare_replays 逐步比对首个分歧步/legacy_events 旧格式确定式重建/consistency_check 三方对账；RunRecorder 增量 events 观测日志，旧文件续跑先重建；`scripts/replay_run.py --verify/--compare`）⑩ 自动复盘页（`report/review_page.py` 自包含 HTML 逐回合/考试/结算/重放一致性/C1 逐步轨迹/行内标注导出导入 + `report/annotations.py` verdict=bad 带 expected → 整态/分类结论冻结进 `tests/fixtures/review_regressions.json` + `scripts/review_page.py`/`annotations_to_regression.py`；auto_produce 局末自动生成 `[review]`；样例 docs/review_sample.html）；61 条单测（38+20+3），pytest 1564/1（1565 收集 / 97 文件）；**sim/ 零引用新模块 → 评测零影响、无需重标定**；基线 ①③④⑤ 不变；ep-t1-g 真实卡屏 28 次重复观测被显式 surfaced。**阶段1 剩 P 道具后续批次；下一任务先问用户（P 道具批次 vs 阶段2 r11）**
- **P1-7** ✅ **2026-11-24 完成**（P 道具后续批次 bounded batch，BSD-3 + DSL 三重核实）：好调增加量增加 ExamParameterBuffAdditive → condition_gain（resolveGoodConditionTurns ×(1+Σ goodConditionTurnsBuffs)，夜闇の星 313/314；卡 + P 道具双渠道）+ 元气增加无效 ExamBlockRestriction → nullify_genki_turns / 不安 ExamBlockAddDown → unease_turns（resolveGenki `if(nullifyGenkiTurns)return` / `genki*=0.67` 向上取整，∈ EOT_DECREMENT_FIELDS+DEBUFF_FIELDS；いたずらパペット 149/150、初陣の証・美鈴 302/303、雨上がりの花 253/254）+ ExamBlockFix 分离 fixed_vitality（resolveFixedGenki 不受闸门）+ **通用延迟生效机制**（yaml `e_effect-exam_effect_timer-NNNN` ↔ DSL 嵌套 at:turn/delay:N-1，EffectManager.decrementDelay；34 段标注，登记时计次/到点结算，修正おさぼりタオル nullifyDebuff 下回合/美铃干劲 3 回合后/温存变更类下回合等已实现道具时序）；48 条单测，pytest 1612/1（1613 收集 / 98 文件）；RULES_REFERENCE §5.9；implemented 1164→1179/1849（+15）、modifier 409→442；**sim_produce 不引用 p_items + genki_gate/condition_gain 无来源恒等 → 评测零影响**，sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；gkbench 94 唯一 loadout id 无 timer/新目标道具 → local_bench 零触达；**保持 no-op 如实记**：塔 gimmick（低谷/紧张/弱气/体力回复无效，参考无独立字段）/塔 ∞ 段（value=0）/全力・强气效果卡打分（per-card g.score 成长，values 恒空）/日文好調の%分（眠気卡张数条件）/ExamParameterBuffReduce（produce/buff_consume 触发未支持）。**阶段1 剩 P 道具后续批次；下一任务先问用户（P 道具剩段 vs 阶段2 r11）**
- **P1-8** ✅ **2026-11-24 完成**（P 道具剩段 bounded batch，BSD-3 + DSL 三重核实；**只改数据层标注 sim/ 零改动**）：日文好調の%分（天生的才能 pitem_01-3-346-0/1）——DSL 天性の才能 493/494 `at:afterCardUsed { if:countCards[hand & baseId(23)]>=1 { score+=goodConditionTurns*0.3 } }`（+ genki+=1; ×0.5）；眠気 baseId(23)↔card_table/card_meta 睡意 p_card-00-acc-0_002（B10 zone_count 已解析 hand≥1）；本批补 `CONVERSION_SOURCES_JA={"好調":"parameter_buff"}` 日文换算源标注（「Xの%分」），结算复用 P1-5 依赖换算渠道 int(condition_turns×N/100)；32 条单测，pytest 1644/1（1645 收集 / 99 文件）；RULES_REFERENCE §5.10；implemented 1179→1181/1849（+2）、依赖换算 76→78（好调换算 11→13）；p_items.json 仅 2 条记录变化；**评测零 P 道具结算 + sim/ 零改动**，sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；天生的才能 sense pIdol 158 不在 gkbench hif loadout → local_bench 零触达；**保持 no-op 如实记**：全力・强气效果卡打分（per-card g.score 成长 43 段，DSL target:effect(fullPowerCharge){g.score+=11}，values 恒空需逐卡证据表+新机制，超出 bounded）/塔 gimmick（低谷11/紧张6/弱气6/体力回复无效6=29 段，参考引擎 ALL_FIELDS 无字段）/ExamParameterBuffReduce（3 段 produce_start_lesson/buff_consume 触发未支持，buff_consume 依赖 buff-cost 卡机制 P1-4 已记无落点）。**阶段1 剩 P 道具后续批次（新机制/真机）；下一任务先问用户（P 道具剩段 vs 阶段2 r11）**
- 每项 DoD：参考引擎证据（规则项）+ 代码 + 单测 + [RULES_REFERENCE](RULES_REFERENCE.md) 核验表更新（规则项）+ `sim_engine_ab` 重标定（规则项，如 B3 例）。
- **留阶段 3（离线做不了，需真机数据）**：考试 RNG 流（随机生成卡 H.I.F应援棒 / panic / search / move）、fresh buff 差一回合衰减（真机逐回合截图）、附魔/主道具回忆、真机培育侧 P 道具列表（T6/D1）。
- **T8 情报跟踪**：持续低成本，有变化才更新 QQ_GROUP_NOTES/HIRO_VIDEO_NOTES/AUTO_GAKUMAS_NOTES + ADR，不单独占会话。

**阶段 2 · 重采 + 练学生 + 新旧对比**
- 🔒 **旧数据/模型全保留**（用户指定）：out/ 的 `ei_r5_selfplay.npz`/`ei_r9_selfplay_large.npz`/`ei_r4_demos.npz`/`ei_r9_demos.npz`、模型 v1/v6/r9/r10、各 `ei_r*_eval_*.json`、入库 `ei_policy_v6.json`（r6 权重）**一律不覆盖不删**，作**旧规则参照**。
- ⚠️ 阶段1 改了规则 → 旧数据是**旧规则口径**（B3 作废 B2 同例，但物理保留）：先 `sim_engine_ab` 重标定 + **参照臂 v6/v1/beam/r9/r10 按新规则重评**（门基线随之重定，旧 98.6/98.1/305.3 是旧规则口径，不可直接比）。
- **P2-0 重采**：新规则下采 small+large 自对弈（当前最佳学生 argmax，**新 seed 块、新文件名**如 `ei_r11_selfplay_small.npz`/`_large.npz`，与评测段及旧块错开）+ 示范（新 seed 块新文件）。
- **P2-1 练新批**：r11 = 新采数据 + **small 上采样**（R9_ANALYSIS §6 候选②，能量→~66%）+ `--norm-by-scenario`（r10 已落地）→ 500 局双门（large vs v6 显著正 **且** small 不回退 + vs v1 原门保持，**基线用新规则重评值**）→ **双过入库**替换 `ei_policy_v6.json`（`data/_r10_promote.py` 改 r11 复用，meta 补溯源）。
- **P2-1b 新旧对比（用户指定，等新批练出来再做）**：新批学生 vs 旧 v6/r9/r10 同 seed 段配对——**分清「规则变化带来的分移」（旧模型在新 sim 下也变）与「学生本身改进」**；旧模型保留可随时复跑对照。对比结论写回 EXPECTIMAX。
- **P2-2+**：不过则 r12（教师←v6 消 v1 拉扯 / 调上采样倍数）续，直到 small+large 双过（**F 入场券**）。不硬凑显著，不过如实记负结果。

**阶段 3 · 真机（旧 T1/T2/T3/T6/D1/E0/C1 真机验收并入）**
- **T3** 实时考试验收（采集↔决策实时打通，`[exam-plan] verified`）→ **T1** 整局无人值守（`--ignore-user --max-minutes 30`，RUNS.md 记一局 ≥C+ ≤20min）→ **T2** 三引擎 A/B（rules/expectimax/beam+全知 + net 第四臂，large 可加 specialist 臂；同卡组同 seed）。
- **C1 真机验收**（tap 互验/提权/复盘在真机生效）随 T1/T2 一并验。
- **T6/D1 补采**：非 5 NPC produce 类型 / 11-20 期末 T9 回合内重洗 / 同局两次重洗（T6）；RNG 样本 / fresh buff 逐回合截图 / 真机培育侧 P 道具列表（D1）→ **回补阶段1 留下的建模缺口**（补完如需再重采重训，仍保留旧数据）。
- **T9-E0** 离线培育测试台（可选，需独立游戏副本 + 用户配合；验证作者包能否离线跑到考试，作 fresh buff 截图/T1 回归零账号风险来源）。

**阶段 4 · 网站（旧 F1/F2）**
- F1/F2 gkbench 公开对比（ranked 禁 seed，只能交不看 seed 的算法；public-safe 学生网**须阶段2 双过**；fixed/template 口径见 [GKBENCH.md](GKBENCH.md)）。

**阶段 5 · 收尾（旧 G）**
- 私有存档/私有仓库（[ARCHIVE.md](ARCHIVE.md)：bundle+裸仓库+采集数据备份，只能私有）；文档总收尾。

**旧路线图未完成项 → 本路线图映射（无遗漏）**：T5 剩余建模→阶段1（离线）+阶段3（需真机数据）；T7②③→阶段1 P1-6；T8→持续；T1/T2/T3/C1 真机验收→阶段3；T6/D1→阶段3；T9-E0→阶段3；B11 练学生（含继续降档候选）→阶段2；F1/F2→阶段4；G 收尾→阶段5。（A1–A5/B1–B10/B2-R/C0/C1 代码/F0 已完成，不重做。）

**纪律**：SKIP 只在真没体力；禁静默回退 rules；每会话 1–3 任务；旧学生/老师数据模型保留不覆盖；`data/_probe*`、`bench_local/REPORT.md`、`card_library.json` 不提交；每任务 feat + docs(handover) 哈希提交；**每会话结束发用户下一会话开场白（§8 步骤 6）**。

**环境变更（2026-11-24，Hindsight 记忆停用）**：用户发现阿里云余额莫名少了约 ¥10，排查确认是
Hindsight daemon 后台烧的——它用**普通 DASHSCOPE_API_KEY + 标准 dashscope 按量端点**跑
qwen-plus + text-embedding-v4，**不在千问 Token Plan 订阅覆盖内**（订阅 sk-sp- 只覆盖 token-plan
端点的 15 个对话模型，主 agent qwen4-max-preview 在内）；两天几千次 retain/extract/consolidation/
mental-model 调用（深化 300 commit diff + 吞 8 个长会话 + 维护 12 页）扣余额。用户删普通 key 止血
（daemon 转 401 空转），随后指定**直接停用**：plugin_manager 禁用 bundle
`@vectorize-io/hindsight-coding-agents` + 杀 daemon 进程树（uvx hindsight-api PID 36048 树）+
pg_ctl 停内嵌 PG，9077/5432 释放，hindsight_* 工具下线。**主 agent（订阅）不受影响**；qwen MCP
工具也用普通 key（一并失效，本就没在用）。跨会话上下文从此全靠 docs 交接。详见 HANDOVER 二·补四十八。

**最近交接记录（2026-11-24，P1-8 —— 阶段1 第八批：P 道具剩段 bounded batch：日文好調の%分 / 天生的才能，BSD-3 + DSL 三重核实；只改数据层标注 sim/ 零改动）**：
用户已选定本会话做 P 道具剩段（A 顺序，不用再问）。开工基线 ①–⑤ 全绿（HEAD a10a38a，
② 1612/1、1613 收集 / 98 文件，216.84s）；Hindsight 记忆已停用（不用 hindsight_* 工具，跨会话靠 docs）。
**本批挑「证据充分、离线可定、映射既有机制」的低风险段**（bounded batch，不贪多；per-card 成长等
新机制超出范围则 no-op 留后续），语义经 BSD-3 参考引擎 gakumas-tools + 主数据 + 参考 DSL `p_items.csv` 三重核实：
**① 日文好調の%分（天生的才能 pitem_01-3-346-0/1）→ 好调依赖换算**（2 段）：参考 DSL 天性の才能
493/494 `at:afterCardUsed { if:countCards[hand & baseId(23)]>=1 { score+=goodConditionTurns*0.3 } }`
（+ 变体 `genki+=1; score+=goodConditionTurns*0.5`，pIdol 158）。眠気卡张数条件 baseId(23)
（skill_cards.csv 23 眠気 trouble ↔ card_table/card_meta 睡意 p_card-00-acc-0_002，ja_aliases 眠気→睡意）
**已由 B10 zone_count 结构化解析**（hand≥1，trigger=card_played，condition_known/trigger_known=True）；
本批只补「好調の%分」→ parameter_buff 的**日文换算源标注**（build_p_items.CONVERSION_SOURCES_JA /
_CONVERSION_SOURCE_TEXT_JA「Xの%分」/ annotate_effects 日文分支），结算复用 P1-5 依赖换算渠道
（目标增量 int(condition_turns×N/100)，源段只作系数不消耗好调回合；取整/门槛/区域口径与初陣の証・佑芽同）。
**落地（纯数据层，sim/ 零改动）**：build_p_items.py（CONVERSION_SOURCES_JA + 日文 regex + annotate_effects
日文分支）；p_items.json 重建（逐条 diff 校验**仅 2 条记录**变化：天生的才能 -0/-1 源段 role=conversion_source/
percent1 移除，ExamLesson 目标 depends_on=parameter_buff + percent1=30/50）。换算/zone_count 双镜
P1-5/B10 就绪，sim/p_items.py、sim/lesson.py、sim/expectimax.py **零改动**。
implemented **1179→1181/1849**（+2），依赖换算 76→**78**（好调换算目标 11→**13**：9 ExamLesson + 4 ExamLessonBuff）。
**保持 no-op 如实记录（不猜）**：全力・强气效果卡打分（ExamFullPower/ExamConcentration「打分值增加+N」
**43 段** = per-card g.score 成长，DSL まあるい春色 target:effect(fullPowerCharge)&active{g.score+=11} /
はつぼしメダル黒 target:effect(strength){g.score+=10}，resolveScore growth[g.score]，**非** setFullPowerEffectBuff
（那是全力/强气指針倍率另一机制）；values 恒空需逐卡证据表 + per-card 成长新机制，超出 bounded）/
塔 gimmick（低谷 ExamGimmickSlump 11/紧张 ExamGimmickLessonDebuff 6/弱气 ExamGimmickSleepy 6/
体力回复无效 ExamStaminaRecoverRestriction 6 = **29 段**，参考引擎 ALL_FIELDS 无对应字段、全部 CSV 零用法）/
ExamParameterBuffReduce（**3 段** produce_start_lesson/buff_consume 触发未支持，buff_consume 依赖 buff-cost
卡机制 P1-4 ⑦ 已记卡模型不承载 buff 花费）。
**评测零影响 / 重标定**：sim_produce.py p_items 默认 ()、sim_engine_ab.py 不注入 P 道具（grep 0 命中）；
本批又只改数据层标注（sim/ 零改动）→ 非 P 道具路径不变。**sim_engine_ab 重标定：改前（git stash）/改后
64 局逐位相同（差异=0）**——seed 9000/9100 各 16 局 rules/expectimax budget 800ms，逐局非时间字段全等
（data/_p18_ab_compare.py，不提交）；expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，15/1/0 与 11/5/0，
C+ 100%，0 blocked / 0 error），B3 结论保持。**天生的才能 sense pIdol 158 不在 gkbench hif loadout**
（94 唯一 id 无 346）→ local_bench 零触达。**旧 B11 数据/模型是旧规则口径**（用户指定全保留不覆盖）：
阶段2 重采新 seed 块练新批再新旧对比。
**测试/基线**：tests/test_p18_ja_condition_conversion.py **32 条** + 既有断言随规则更新（test_p13/p14/p15/p17
implemented 1179→1181、test_p15 noop 670→668 / depends_on 76→78 / 好调换算 11→13、test_p15 日文
deferred-noop 改断言已实现）；ruff 通过；全量 pytest **1644/1（1645 收集 / 99 文件，214.43s）**；
①③④⑤ 复跑不变（① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155）。
重标定产物 out/_p18_ab_{before,after}_{9000,9100}.json（gitignore）；一次性脚本 data/_p18_*.py 不提交。
文档：RULES_REFERENCE §0/§5.10/§6/§7；WORKPLAN §0/P1-8/路线图；HANDOVER_NEXT §0/§2/§8.0/§8；INDEX；HANDOVER 二·补五十二。
提交 feat <HASH>（数据层标注+测试+数据重建+文档）+ docs(handover) 哈希记录。
**下一会话（先问用户）**：阶段1 剩 **P 道具后续批次**（塔 gimmick/全力・强气效果卡打分/
ExamParameterBuffReduce——证据充分但需新机制/真机，no-op 如实记；日文好調の%分 ✅ P1-8），
**或直接进阶段2 重采+练学生 r11**（small 上采样 + --norm-by-scenario，新 seed 块新文件，参照臂按新规则重评，
small+large 双过入库 + 新旧对比；旧数据模型全保留）。用户选定后按 §8 交接+再发开场白。

**上一轮交接记录（2026-11-24，P1-7 —— 阶段1 第七批：P 道具后续批次 bounded batch：好调增加量增加 / 元气增加无效 / 不安 / 通用延迟生效，BSD-3 + DSL 三重核实）**：
用户已选定本会话做 P 道具批次（A 顺序，不用再问）。开工基线 ①–⑤ 全绿（HEAD eb2dac5，
② 1564/1、1565 收集 / 97 文件，233.62s）；Hindsight 记忆已停用（不用 hindsight_* 工具，跨会话靠 docs）。
**本批挑「证据充分、离线可定、低风险」段**（bounded batch，不贪多），语义全部经 BSD-3 参考引擎
gakumas-tools + 主数据 + 参考 DSL `p_items.csv` 三重核实：
**① 好调增加量增加 ExamParameterBuffAdditive → condition_gain**（4 段）：参考 resolveGoodConditionTurns
先加 additionBuffs 再 ×(1+Σ goodConditionTurnsBuffs)（setGoodConditionTurnsBuff），乘在获得量上向上取整；
卡渠道（先加 condition_additive 再乘）+ P 道具 parameter_buff 渠道双镜（DSL 夜闇の星 313/314
setGoodConditionTurnsBuff(0.5,4/5)；主数据暗夜里的明星± percent1=50/turn=4/5 + N.I.A棒球帽/手包 percent1=25/turn=3）。
**② 元气增加无效 ExamBlockRestriction → nullify_genki_turns**（9 段非塔）/ **不安 ExamBlockAddDown →
unease_turns**（2 段非塔）：参考 resolveGenki `if(nullifyGenkiTurns)return;`（genki+= 整段不增）/
`genki += motivation×motivationMultiplier` 后 `if(uneaseTurns)genki*=0.67`（WHOLE_FIELDS 向上取整）；
两者 ∈ EOT_DECREMENT_FIELDS（回合末 -1）+ DEBUFF_FIELDS（nullifyDebuff 拦截施加）；N 在 turn 列；
`genki_gate` 纯函数双镜共用（DSL いたずらパペット 149/150、初陣の証・美鈴 302/303、雨上がりの花 253/254 delay:2）。
**③ ExamBlockFix 分离 fixed_vitality**（12 段）：参考 resolveFixedGenki 直接进元气，不吃干劲、不受闸门影响。
**④ 通用延迟生效机制**（34 段标注）：主数据 yaml originProduceExamEffectId 的
`e_effect-exam_effect_timer-NNNN-MM-e_effect-<inner>` 包装 → delay_turns=NNNN（↔ DSL 嵌套 at:turn /
delay:NNNN-1，EffectManager.decrementDelay 每回合末 -1，到 0 的下一回合开始结算）；触发回合登记增量
（条件/次数当时求值），到点结算。**修正已实现道具时序**：おさぼりタオル nullifyDebuff 下回合（P1-4 原立即）/
美铃干劲 3 回合后 / 超越太阳的歌声 score_buff 3 回合后 / 温存变更类（圆润的春色/命运的相遇/梦想中的星辉/
编织夏日的影子/研讨会卫衣）下回合 / 初星旗帜紫全力值・增益下回合 / 彼此许下的约定全力值增益下回合 /
初星灯光紫不調下回合 / 初星摆件银打分 5/6 回合后。
**落地（纯增量）**：p_items.py（CONDITION_GAIN/NULLIFY_GENKI/UNEASE/FIXED_VITALITY_EFFECTS /
TARGET_BY_EFFECT / PERCENT_TARGETS / DURATION_TARGETS / effect_value 读 turn / PItemSpec.delay_turns /
PItemDelta.nullify_genki_turns・unease_turns・fixed_vitality・delayed + freeze/thaw）；lesson.py/expectimax.py
（genki_gate + condition_gain 双渠道 + _apply_p_delta/_apply_p_delta_state 提取 + 延迟队列登记/倒计时/到点结算 +
canonical + 快照往返）；build_p_items.py（_timer_delay + extract_effects 标注）；p_items.json 重标注重建
（逐条 diff 校验 **49 条记录**变化：15 新目标段 + 34 延迟标注段，部分重叠；塔 ∞ 段 target 标注但 value=0 仍 no-op）。
implemented **1164→1179/1849**（+15），modifier 409→**442**。
**保持 no-op 如实记录（不猜）**：塔 gimmick（低谷 ExamGimmickSlump 11/紧张 ExamGimmickLessonDebuff 6/
弱气 ExamGimmickSleepy 6/体力回复无效 ExamStaminaRecoverRestriction 6，参考引擎 ALL_FIELDS 无对应字段、
全部 CSV 零用法）/塔 ∞ 段（ExamBlockRestriction 6/ExamBlockAddDown 12，values 恒空 value=0）/
全力・强气效果卡打分（ExamFullPower/ExamConcentration「打分值增加+N」段 = per-card g.score 成长，
DSL まあるい春色 target:effect(fullPowerCharge){g.score+=11}，values 恒空需逐卡证据表 + 成长机制）/
日文好調の%分（天生的才能 pitem_01-3-346，countCards[hand & baseId(23)]>=1 眠気卡条件、无中文）/
ExamParameterBuffReduce（produce_start_lesson/buff_consume 触发未支持）。
**评测零影响 / 重标定**：sim_produce.py 完全不引用 p_items（grep 0 命中）；genki_gate 在 nullify/unease=0
恒等、condition_gain 无 modifier 恒等 → 非 P 道具路径不变。**sim_engine_ab 重标定：改前（git stash）/改后
64 局逐位相同（差异=0）**——seed 9000/9100 各 16 局 rules/expectimax budget 800ms，逐局非时间字段全等
（data/_p17_ab_compare.py，不提交）；expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，15/1/0 与 11/5/0，
C+ 100%，0 blocked / 0 error），B3 结论保持。**gkbench 94 唯一 loadout id 无一件 timer/新目标道具** →
local_bench 零触达。**旧 B11 数据/模型是旧规则口径**（用户指定全保留不覆盖）：阶段2 重采新 seed 块练新批再新旧对比。
**测试/基线**：tests/test_p17_genki_condition_delay.py **48 条** + 既有断言随规则更新（test_p13/p14/p15
implemented 1164→1179、test_p15 两个 deferred-noop 改断言已实现、test_p_items_b9 ExamBlockFix 改断言
fixed_vitality）；ruff 通过；全量 pytest **1612/1（1613 收集 / 98 文件，218.08s）**；①③④⑤ 复跑不变
（① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155）。重标定产物
out/_p17_ab_{before,after}_{9000,9100}.json（gitignore）；一次性脚本 data/_p17_*.py 不提交。
文档：RULES_REFERENCE §5.8 注记/§5.9；WORKPLAN §0/P1-7/路线图；HANDOVER_NEXT §0/§2/§8.0/§8；INDEX；HANDOVER 二·补五十一。
提交 feat 6952c5e（规则代码+测试+数据标注+文档）+ docs(handover) 哈希记录。
**下一会话（先问用户）**：阶段1 剩 **P 道具后续批次**（塔 gimmick/全力・强气效果卡打分/日文好調の%分/
ExamParameterBuffReduce——证据充分但需新机制/真机，no-op 如实记），**或直接进阶段2 重采+练学生 r11**
（small 上采样 + --norm-by-scenario，新 seed 块新文件，参照臂按新规则重评，small+large 双过入库 + 新旧对比；
旧数据模型全保留）。用户选定后按 §8 交接+再发开场白。

**上一轮交接记录（2026-11-24，P1-6 —— 阶段1 第六批：T7②③ 离线可靠性工程，纯函数状态重放 + 自动复盘页 + 标注转回归闭环；不改考试规则、不作废 B11 数据）**：
用户已确认 A 顺序（不用再问）。开工基线 ①–⑤ 全绿（HEAD f98f6a8，② 1503/1、
1504 收集 / 94 文件，224.17s）；Hindsight 记忆已停用（不用 hindsight_* 工具，跨会话靠 docs）。
**⑨ 纯函数状态重放**：新 `src/gkagent/data/run_replay.py`——`apply_event(state, event)`
无副作用（深不可变 `RunState`/`ExamSnapshot`/`FinalSnapshot`，不读时钟/文件/随机数）；
事件 5 类 action/backfill/lesson/exam/final 与 note_* 一一对应（考试类型在 `exam_kind`，
不跟事件类型 `kind` 混）；null 观测不抹已知值（最后已知值优先=补写语义）；未知种类显式
ValueError（不静默丢观测）。`replay` 逐事件快照 + `fingerprint` sha256（**同观测序列两遍
重放指纹逐位相等**）+ `compare_replays` 逐步比对（首个分歧步+逐字段差异+长度差）+
`legacy_events` 旧格式汇总确定式重建 + `consistency_check` 三方对账（events 重放 vs 旧格式
重建 vs 记录汇总；`missing_fields`/`lesson_unread` 是观测级计数、合并视图不可比，排除在
对账外只作展示）。`RunRecorder` 增量 `events` 有序观测日志（每个 note_* 追加、随 flush
原子落盘；**旧格式文件续跑先把汇总重建成日志再续编号**，重放覆盖整局）；note_final 日志记
**兜底前**原始读数、重放独立重兜底——记录器/重放器互为独立实现，漂移可被抓（单测实证：
暂存覆盖丢分 → lesson_total 分歧；汇总篡改 → stamina 分歧）。新 `scripts/replay_run.py`：
逐事件状态推进+终态摘要+三方对账；`--verify` 退出码=DoD；`--compare` 两条序列逐步比对；
`--json`。**⑩ 自动复盘页+标注闭环**：新 `src/gkagent/report/review_page.py`——
`build_review_html` 纯函数渲染自包含 HTML（同输入同输出、全量 HTML 转义、内嵌 JSON
`<`/`>` Unicode 转义防逃逸）：周行动逐回合表（重复观测黄底/null 灰显）/考试/结算/重放
一致性（指纹+三方对账）/观测事件日志/C1 逐步轨迹表（lost/failed/stuck 红底；合成轨迹
显著 banner）/标注工具栏；行内 verdict（ok/bad/unsure）+评论+expected（k=v;k=v），
localStorage 自动保存（键含指纹前 8 位不串局），导出 `annotations_<ep>.json`/导入/清除。
新 `src/gkagent/report/annotations.py`：`parse_expected`/`normalize_annotations`（坏 schema
显式报错）/`cases_from_annotations`（**verdict=bad 且带 expected** 才转用例：周/考试/结算
修正→追加观测事件重放**整态冻结**；逐步修正→`summarize_traces` 分类结论冻结——期望在
转换时冻结，被测代码不给自己出题）/`merge_cases`（按 id 去重）。新 `scripts/review_page.py`
+ `scripts/annotations_to_regression.py`（原子写、幂等）；`tests/test_review_regressions.py`
逐条重算比对。**auto_produce 局末自动生成**（`[review]` 日志行 + summary `review_page` 键；
best-effort，失败只留痕不影响收尾/退出码）。
**样例/夹具**：docs/review_sample.html——记录=真机 ep-rule1（bot 最好 C+/5992，真实数据）；
轨迹=合成演示 6 步（本局跑在 C1 之前无真机 step_trace，`trace_source=synthetic-demo` 显著
标注，不当真机数据引用）。夹具 2 条演示用例 provenance=synthetic-demo（演示闭环，非真机
ground truth；真机标注后由转换脚本追加真实案例）。
**验证**：tests/test_run_replay.py **38 条** + test_review_page.py **20 条** +
test_review_regressions.py **3 条** = 61 条；ruff 通过；全量 pytest **1564/1（1565 收集 /
97 文件）**；①③④⑤ 复跑不变（① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、
⑤ 366/384 逐张 1125/1155）。**sim/ 零引用 run_record/run_replay/report（grep 0 命中）→
模拟器/评测零影响，无需 sim_engine_ab 重标定**；旧 B11 数据/模型全保留。真实记录端到端：
ep-kinami1/ep-rule1/ep-verify1 `--verify` 三方对账全一致；**ep-t1-g 卡屏局 28 次重复观测
被重放显式 surfaced**（duplicates 计数 + 复盘页黄底）。一次性脚本 data/_p16_*.py 不提交；
out/review/ gitignore。
文档：WORKPLAN §0/P1-6/C1 注记/开场白；HANDOVER_NEXT 开场白/§0/§2/§4 T7/§6/§8.0/§8；
LIVE_RUN §2/§2.1/§3；INDEX；HANDOVER 二·补五十。
提交 feat 5ea7c0e（代码+测试+夹具+样例页+文档）+ docs(handover) 哈希记录。
**下一会话（先问用户）**：阶段1 剩 **P 道具后续批次**（好调增加量增加 ExamParameterBuffAdditive /
元气增加无效 ExamBlockRestriction / 不安 ExamBlockAddDown / 塔 gimmick / 全力・强气效果卡打分 /
日文好調の%分 / ExamParameterBuffReduce——证据充分但需新机制，no-op 如实记），**或直接进
阶段2 重采+练学生 r11**（small 上采样 + --norm-by-scenario，新 seed 块新文件，参照臂按新规则
重评，small+large 双过入库 + 新旧对比；旧数据模型全保留）。用户选定后按 §8 交接+再发开场白。

**上一轮交接记录（2026-11-24，P1-5 —— 阶段1 第五批：P 道具剩余效果语义补全 bounded batch：层数减少 + 好调回合 + 好调依赖换算，BSD-3 + DSL 三重核实）**：
用户已确认 A 顺序（不用再问）。开工基线 ①–⑤ 全绿（HEAD edb65a6，② 1465/1、
1466 收集 / 93 文件，222.83s）；Hindsight 记忆已停用（不用 hindsight_* 工具，跨会话靠 docs）。
**本批挑「证据充分、离线可定、映射既有机制」的低风险段**（bounded batch，不贪多），语义全部经
BSD-3 参考引擎 gakumas-tools + 主数据 + 参考 DSL `p_items.csv` 三重核实：
**① 层数减少类**（资源 -= N，参考 `Executor.executeAssignment` op "-=" + `NON_NEGATIVE_FIELDS`
夹取 ≥0；资源不是 DEBUFF_FIELDS，nullifyDebuff 不拦截）：`ExamAggressiveReduce` 干劲减少
（DSL motivation-=1 スタイリッシュモード 139/140、初恋の証・麻央 152/153）/ `ExamLessonBuffReduce`
集中减少（concentration-=1 イケてるセーター 179、「Pっち」242/243）/ `ExamFullPowerPointReduce`
全力值减少（fullPowerCharge-=2 ユートピアへの誘い 399/400；引擎 decreaseFullPowerCharge
Math.max(0,…) 同口径）。**全力值减少走独立 `PItemDelta.full_power_point_reduce`**
（apply_full_power_point 只表达增加、负 delta 按 0），双镜 max(0, fp−N)、**不计累计全力值**；
aggressive/focus 负层数走既有夹取。**② 体力减少 `ExamStaminaDamage`** 并入 STAMINA_LOSS_EFFECTS
（DSL 私の「初」の楽譜 27/28 `cost-=1`，genki==0 时 resolveCost 穿透 stamina−1/consumedStamina+1；
主数据条件「元气为0的时候」）。**③ 好调N回合 `ExamParameterBuff`**：N 在 **turn 列**
（effect_value 读 turn，value1 优先）→ condition_turns += N（既有 parameter_buff 渠道、回合末 -1；
DSL goodConditionTurns+=N Dearリトルプリンス 31/32、共に戦うタオル 43/44 等 33 件）。
**④ 好调依赖换算**（「好调的N%数值变为打分上升/集中」）：好调 = condition_turns 整数（B8 曾以
「剩余回合数非可换算量」排除，现已建模）→ `CONVERSION_SOURCES` 加 `好调:parameter_buff`；
源段只作系数（**不消耗好调回合**），目标增量 int(condition_turns×N/100)（DSL
score+=goodConditionTurns*0.3 初陣の証・佑芽 304/305 / concentration+=goodConditionTurns*0.4
アニメイト装備 162/163）。
**落地（纯增量）**：p_items.py（AGGRESSIVE_REDUCE/FOCUS_REDUCE/FULL_POWER_POINT_REDUCE_EFFECTS /
TARGET_BY_EFFECT / effect_value 读 ExamParameterBuff turn / PItemDelta.full_power_point_reduce +
is_zero/as_dict/__iadd__/__add__ / _apply_modifier_target 负层数 / ExamStaminaDamage 并入
STAMINA_LOSS）+ lesson.py/expectimax.py（全力值减少 max(0,fp−N) 双镜，默认 0=旧行为）+
build_p_items.py（CONVERSION_SOURCES 好调）+ p_items.json 重标注重建（分类纯函数驱动；逐条 diff
校验仅 **24 条记录**变化：11 ExamParameterBuff 源段 role=conversion_source + 7 ExamLesson/
4 ExamLessonBuff 目标 depends_on=parameter_buff + 5 ExamAggressiveReduce/4 ExamLessonBuffReduce/
4 ExamFullPowerPointReduce target 标注；ExamStaminaDamage 代码驱动无数据变化）。
implemented **1067→1164/1849**（+97），依赖换算 65→**76 段**。
**留后续（证据充分但需新机制/真机，保持 no-op 如实记录，不猜）**：好调增加量增加
（ExamParameterBuffAdditive 4 段，setGoodConditionTurnsBuff 增益倍率接线）/ 元气增加无效
（ExamBlockRestriction 15 段，nullifyGenkiTurns，resolveGenki return）/ 不安（ExamBlockAddDown
14 段，uneaseTurns，resolveGenki ×0.67，delay:2 延迟生效）/ 塔 gimmick（低谷/紧张/弱气/体力回复
无效，参考无独立字段、gkbench 无 tower）/ 全力・强气效果卡打分（ExamFullPower 31/ExamConcentration
25 no_target，setFullPowerEffectBuff/setStrengthEffectBuff 卡级 modifier）/ 日文好調の%分
（天生的才能 2 段，眠気卡张数条件、无中文）/ ExamParameterBuffReduce（produce/buff_consume 触发未支持）。
**评测零 P 道具结算 / 重标定**：`sim_produce.py`（培育模拟）**完全不引用 p_items**（grep 0 命中）
→ sim_engine_ab 评测路径无 P 道具。**sim_engine_ab 重标定：改前（git stash）/改后 64 局逐位相同
（差异=0）**——seed 9000/9100 各 16 局 rules/expectimax budget 800ms，逐局非时间字段全等
（data/_p15_ab_compare.py，不提交）；expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，
15/1/0 与 11/5/0，C+ 100%，0 blocked / 0 error），B3 结论保持。**旧 B11 数据/模型是旧规则口径**
（用户指定全保留不覆盖）：阶段2 重采新 seed 块练新批再新旧对比；参照臂需按新规则重评。
**测试/基线**：tests/test_p15_reduce_condition.py **38 条**（分类/数值/apply_passive/PItemDelta/
LessonSim/双镜/数据层 no-op 记录）+ 既有断言随规则更新（test_p13/test_p14 implemented 1067→1164）；
ruff 通过；全量 pytest **1503/1（1504 收集 / 94 文件，223.75s）**；①③④⑤ 复跑不变（① 4/4+3/3、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155）。重标定产物
out/_p15_ab_{before,after}_{9000,9100}.json（gitignore）；一次性脚本 data/_p15_*.py 不提交。
文档：RULES_REFERENCE §0/§1/§5.8/§6/§7；WORKPLAN §0/P1-5/路线图；
HANDOVER_NEXT §0/§2/§8.0/§8；INDEX；HANDOVER 二·补四十九。
提交 feat 4a55cc8（规则代码+测试+数据标注+文档）+ docs(handover) 哈希记录。
**下一会话（P1-6，用户已确认 A 顺序，不用再问）**：T7②③ 纯函数状态重放（run_record 雏形 →
同观测序列→同状态→逐步比对）+ 自动复盘页（每局逐回合页 + 人工标注转回归；C1 已有
step_trace.jsonl + replay_steps.py，差页面/标注闭环）。**离线可靠性工程，不改考试规则、
不作废 B11 数据**。每项 DoD：代码+单测+文档；完成后按 §8 交接+发 P1-6 后续开场白。

**上一轮交接记录（2026-11-24，P1-4 —— 阶段1 第四批：nullifyDebuff 低下状态无效拦截 + ⑦ ExamBuffConsumptionAdd / countDebuffs 评估，BSD-3 有据）**：
用户已确认 A 顺序（不用再问）。开工基线 ①–⑤ 全绿（HEAD 2dca848，② 1435/1、
1436 收集 / 92 文件，233.88s）；Hindsight 记忆确认（synced=false 后台深化中属正常；
P1-2/P1-3 initiative 页已读；P1-4 initiative 页已建 kp-996e7f240ae64fdb9ae917bb9eecd0c0）。
**⑦ ExamBuffConsumptionAdd 评估保持 no-op**（BSD-3 `Executor/index.js` :463
`doubleBuffCostTurns>0 && BUFF_FIELDS.includes(lhs) → rhsValue*=2` + `CardManager.useCard`
:654 buffCostConsumed 触发 + `Executor.triggerChangeEffects` :345；主数据 4 段：不息的风暴
pitem_03-3-345-0/1、迷倒世界的模样 pitem_01-3-349-0/1 ↔ p_items.csv 488/489/500/501
`doubleBuffCostTurns+=1`；gkbench 22 loadout）：**为什么无落点**——参考有 88 张 buff-cost 卡
（skill_cards.csv cost 列 concentration-=3/motivation-=3/goodImpressionTurns-=2/
fullPowerCharge-=2 等），6 张在 build_pool（潮流领袖/行走步调/齐声应援±）、潮流领袖在
eval large、gkbench 牌组 340 条 buff-cost entry；**但我们的卡模型不承载 buff 花费**
（card_table 这些卡 cost=0 只提取体力费、CardSpec 无 buff_cost 字段、可用性/支付/
buffCostConsumed 触发未建模）→ 落地需先扩卡模型，超出本批 bounded 范围，保持 no-op 不猜，
语义/段数/loadout 写进 RULES_REFERENCE §5.7。
**nullifyDebuff 拦截落地**（P1-2 遗留；BSD-3 `Executor/index.js` executeAssignment :429 /
executeCallAction :507 / executeSpecialAction :545：nullifyDebuff>0 且 lhs∈DEBUFF_FIELDS
或动作∈DEBUFF_SPECIAL_ACTIONS → nullifyDebuff-- 整条跳过；`constants.js`
DEBUFF_SPECIAL_ACTIONS = setScoreDebuff/decreaseFullPowerCharge/setHandDecrease :379、
nullifyDebuff ∉ EOT_DECREMENT_FIELDS = 消耗式无回合倒计时；`BuffManager.initializeState`
:118 标量）：`LessonSim.nullify_debuff`/`ExpectState.nullify_debuff` + canonical +
state_from_sim/sim_from_state + end_turn_state 携带；`intercept_debuff_entries` 纯函数
逐条消耗，拦截已建模的两个 DEBUFF_SPECIAL_ACTIONS（setScoreDebuff/setHandDecrease，
列表逐条，顺序 score_debuffs→hand_decreases）。**来源 P 道具侧**：`ExamAntiDebuff`
values.count → nullify_debuff 目标，主数据 11 段（偷懒的毛巾 pitem_00-2-116-0
おさぼりタオル 舞蹈回合开始无效 1 次 limit1 ↔ p_items.csv 317 + 塔 gimmick 初星灯光/旗帜/
道具 10 段）。**卡侧 4 SSR 族延迟**（偶像之魂/精确无比的标牌制作/红叶下奔跑/甜蜜陷阱♡，
主数据 ExamAntiDebuff values 恒空需逐卡证据表、SSR 不进 pool）；**标量 DEBUFF_FIELDS
拦截**（delta 聚合丢失逐动作粒度）/decreaseFullPowerCharge（未建模）/lock_stance 卡路径
留后续。**countDebuffs 无落点**（低下状態の数，`BuffManager.countDebuffs` :331 标注
UNVERIFIED；参考全部 CSV + 主数据零使用，仅 removeDebuffs 用于「属于我的色彩」csv 534/535）。
**落地（纯增量）**：p_items.py（ANTI_DEBUFF_EFFECTS/TARGET_BY_EFFECT/effect_value 读 count/
PItemDelta.nullify_debuff/intercept_debuff_entries）+ lesson.py/expectimax.py（计数器+拦截+
canonical+快照往返，默认 0=旧行为）+ p_items.json 重标注重建（**无需改代码**，分类纯函数
驱动；逐条 diff 校验仅 **11 条记录**变化，全是 ExamAntiDebuff target None→nullify_debuff）。
implemented **1056→1067/1849**（+11），modifier 标注 385→396。
**评测牌组/gkbench loadout 组成不变 / 重标定**：nullifyDebuff 来源评测零落点（gkbench
688 loadout / 94 唯一道具 id 无 116/tower；build_pool 无 ExamAntiDebuff 卡）→
**sim_engine_ab 重标定：改前（git stash）/改后 64 局逐位相同（差异=0）**——seed 9000/9100
各 16 局 rules/expectimax budget 800ms，逐局非时间字段全等（data/_p14_ab_compare.py，
不提交）；expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，15/0/1 与 11/0/5，
C+ 100%，0 blocked / 0 error），B3 结论保持。**旧 B11 数据/模型是旧规则口径**（用户指定
全保留不覆盖）：阶段2 重采新 seed 块练新批再新旧对比；参照臂需按新规则重评。
**测试/基线**：tests/test_p14_nullify_debuff.py **30 条**（纯规则/P 道具解析/LessonSim/
双镜/数据层 no-op 记录）+ 既有断言随规则更新（test_p13 implemented 1056→1067）；ruff 通过；
全量 pytest **1465/1（1466 收集 / 93 文件）**；①③④⑤ 复跑不变（① 4/4+3/3、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155）。重标定产物
out/_p14_ab_{before,after}_{9000,9100}.json（gitignore）；一次性脚本 data/_p14_ab_compare.py /
_p14_probe.py / _p14_pitems_head.json 不提交。
文档：RULES_REFERENCE §0/§1/§5.5/§5.7/§6/§7；WORKPLAN §0/P1-4/开场白；
HANDOVER_NEXT §0/§2/§4 T5/§8.0/§8；INDEX；HANDOVER 二·补四十七。
提交 feat 1b58a0f（规则代码+测试+数据标注+文档）+ docs(handover) 哈希记录。
**下一会话（P1-5，用户已确认 A 顺序，不用再问）**：⑧ P 道具剩余效果语义补全（离线可做段，
1067/1849 往上推；bounded batch，别一口吃成胖子）。每项 DoD：参考证据+代码+单测+
RULES_REFERENCE 更新+sim_engine_ab 重标定；旧数据模型全保留；完成后按 §8 交接+发 P1-6 开场白。

**上一轮交接记录（2026-11-24，P1-3 —— 阶段1 第三批：hold 保留区建模 + lockStanceTurns 指針固定，BSD-3 有据）**：
用户已确认 A 顺序（不用再问）。开工基线 ①–⑤ 全绿（HEAD f444701，② 1389/1、
1390 收集 / 91 文件，195.95s）；Hindsight 记忆确认（synced=false 后台深化中属正常；
P1-1 initiative 页已读；P1-3 initiative 页已建 kp-410853af1f9b4630b8fb2cd350436ca3）。
**⑥ hold 保留区建模**（BSD-3 CardManager/index.js hold/enforceHoldLimit/holdCard/
holdThisCard/holdSelectedByTarget/moveHeldCardsToHand :959-1102 + useCard thisCardHeld
:639 + TurnManager.endTurn 只弃手牌 + constants FULL_POWER_EFFECTS/FULL_POWER_CHANGED_EFFECTS）：
新 sim/hold.py（HOLD_LIMIT=2 + **13 族卡逐卡证据表** HOLD_SOURCES + hold_pick 确定性选牌）。
主数据 ExamCardMove values 恒空 → 语义按 skill_cards.csv 行号逐卡交叉（card_meta 别名核对）：
冲刺/积累（holdThisCard 温存中，trigger preservation_up 交叉）、潜在能力/互动的基础
（holdSelected[hand],1）、切磋琢磨/觉悟/新的舞台/努力了，哦/那一天，在这里（base 1 张、
+/++/+++ 2 张，DSL 527 (2) + 主数据卡面文本）/对战请多指教！/让群星散落吧
（holdSelected[deck|discarded],1）、爱意彩虹（holdSelected[deck],1）、一点一滴的进步
（moveHeldCardsToHand）。**表外卡保留旧 +1 抽牌近似**（潮流领袖/展翅高飞/发挥本领：
全力值消耗/holdSelectedUpto/target:held 成长未建模；决不停歇：干扰卡计数条件；不猜）。
机制：上限 2（超限最旧 shift 进弃牌堆）/跨回合保留/holdThisCard 本牌不进弃牌除外/
holdSelected 移牌同步 known_draw（牌堆首张相等=known_draw 末张相等）与 discard_order/
moveHeldCardsToHand **LIFO**（P1-1 钩子对齐参考 pop()）/选牌按白值分降序稳定排序
（参考 HeuristicStrategy 全力预览分排序等价：全新状态依赖分恒 0）/再演不翻倍 hold
（参考 hold 按卡索引幂等）。
**lockStanceTurns 指針固定**（constants EOT_DECREMENT_FIELDS + FULL_POWER_EFFECTS
if:lockStanceTurns==0 & fullPowerCharge>=10 + BuffManager.setStance :262 +
Executor freshBuffs :271-279 + decrementBuffTurns）：切磋琢磨 StanceLock turn=1 ↔
DSL 424/425 lockStanceTurns+=1；stance_change_allowed/end_turn 加 locked 守卫
（纯增量默认 False）；回合末 -1 + **fresh 保护**（卡效果 0→正 当回合末不扣 → 锁下一回合，
卡面「指针固定1回合」确定语义；一般 buff fresh 缺口仍留真机核实）；全力进入门被锁时
全力值不消耗；全力解除（setStance(none)）不受守卫；再演翻倍（直接效果）。
**B10 遗留 trigger_unknown 3 件/6 段清零**：① hold 区张数条件——build_p_items _ZONE_MAP
hold→held + p_items PassiveState.held + _zone_count_matches；实现的觉悟/±
（pitem_03-3-078，魅力刚刚好 p_card-03-act-1_038 ↔ ジャストアピール csv 380 使用后 +
countCards[held]>=1 ↔ 叶える覚悟 pIdol 74 csv 212/213）→ 温存变更/温存阶段变更 +
全力值+2/+4（target:held 成长段 g.scoreTimes/g.cost 未建模保守 no-op，如实记）；
② hotfix——咲季营养餐・改（pitem_02-3-309-0）trigger 后缀 period810_hotfix **三源证实
非限定标记**（masterTrans ProduceCardSearch 描述表无此目标 + 中文触发句无卡限定 +
参考 p_items.csv 404 咲季の完全食・改 at:cardUsed turnCardsUsed%2==1 无卡过滤）→
_parse_search_filter 白名单；回合内每第 2 张卡好印象+2/好印象强化+25% limit1。
**温存 2 段階直给 preservation2**（「温存阶段变更」value1=2 ↔ setStance(preservation2)：
叶える覚悟+/はつぼしフィギュア/まあるい春色/夢見る星 交叉）：classify/FLAG_TARGETS/
delta.stances + _apply_direct_stances 双镜分支（过固定守卫）；7 段重标注。
**落地（纯增量）**：sim/hold.py（新）+ stance.py（locked 守卫）+ lesson.py/expectimax.py
（_apply_hold/_apply_hold_state/_enforce_hold_limit/lock_stance_turns+fresh 双镜 +
canonical + state_from_sim/sim_from_state + 叶子 LIFO + _passive_state held 投影）+
p_items.py（PassiveState.held/zone_count held/preservation2）+ build_p_items.py
（hold→held/period810 白名单）+ sim_produce.py（MODELED_EFFECTS 34→35 StanceLock、
CardRow 35→41 元组、ExamCardMove 逐卡证据表分支）+ play_choice.py（生产卡表同口径）+
leaf_data.py（回手 LIFO）+ p_items.json 重标注重建（**无需改代码**，分类纯函数驱动；
逐条 diff 校验仅 **9 条记录**变化：3 件 trigger_known/trigger_params/condition +
7 段 preservation2 target）。implemented 保持 **1056/1849**（机制本就支持，之前是触发
保守不解析→现在真实触发）；**trigger_unknown 3→0 件 / 6→0 段**；zone_count 27→29 件。
**评测牌组组成变化（与 P1-1/P1-2 不同，如实记录）/ 重标定**：冲刺/积累 的 ExamCardMove
从 +1 抽牌近似改为真实 holdThisCard（**保留不是抽牌**）→ draw 1→0；eval_expectimax
large 牌组抽牌签名槽改选决不停歇（表外保留近似），冲刺/积累让出槽位（保真度修正，
旧近似高估；**small 14 张不变**；新 hold 规则在 eval_expectimax 牌组零触达）。
**sim_engine_ab 重标定：改前（git stash）/改后 64 局逐位相同（差异=0）**——seed 9000/9100
各 16 局 rules/expectimax budget 800ms，逐局非时间字段全等（data/_p13_ab_compare.py，
不提交）：冲刺/积累 在这 64 局培育奖励选择中未被采到，池字段变化零触达（sim_engine_ab
用 14 张基础牌组+奖励池动态采牌，与 eval_expectimax 固定 large 牌组不同口径）；
expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，15/0/1 与 11/0/5，C+ 100%，
0 blocked / 0 error），B3 结论保持。**旧 B11 数据/模型是旧规则口径**（用户指定全保留
不覆盖）：阶段2 重采新 seed 块练新批再新旧对比；参照臂需按新规则重评。
**测试/基线**：tests/test_p13_hold_zone.py **46 条**（纯规则/LessonSim/双镜/P 道具/
数据层/解析）+ 既有断言随规则更新（test_sim_produce MODELED 35、test_p12 41 元组、
test_p_items_b8/b9/b10/db trigger_unknown 0 + preservation2、test_p1_stance large 牌组）；
ruff 通过；全量 pytest **1435/1（1436 收集 / 92 文件，230.80s）**；①③④⑤ 复跑不变
（① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155）。
重标定产物 out/_p13_ab_{before,after}_{9000,9100}.json（gitignore）；一次性脚本
data/_p13_ab_compare.py / _p13_pitems_head.json 不提交。
文档：RULES_REFERENCE §0/§1/§5.6/§6/§7；WORKPLAN §0/P1-3；
HANDOVER_NEXT §0/§2/§4 T5/§8.0/§8/开场白；INDEX；HANDOVER 二·补四十六。
提交 eat 81fcdc6（规则代码+测试+数据标注+文档）+ docs(handover) 哈希记录。
**下一会话（P1-4，用户已确认 A 顺序，不用再问）**：⑦ ExamBuffConsumptionAdd buff-cost 卡
（resolveCost 参考；强化状态花费卡机制不在模型里——证据不足保持 no-op 如实记，不猜；
nullifyDebuff 拦截/countDebuffs 相关）。每项 DoD：参考证据+代码+单测+RULES_REFERENCE
更新+sim_engine_ab 重标定；旧数据模型全保留；完成后按 §8 交接+发 P1-5 开场白。

**上一轮交接记录（2026-11-24，P1-2 —— 阶段1 第二批：handDecrease 抽牌修正 + pride 自尊，BSD-3 有据）**：
用户已确认 A 顺序（不用再问）。开工基线 ①–⑤ 全绿（HEAD 9e76323，② 1354/1、
1355 收集 / 90 文件，183.15s）；Hindsight 记忆确认（synced=false 后台深化中属正常；
P1-1 initiative 页 + 规则核验表已读）。
**④ handDecrease 抽牌修正**（BSD-3 `TurnManager.startTurn` :98-104 `cardsToDraw =
Math.max(3 - getHandDecrease, 0)` + `BuffManager.setHandDecrease(amount, turns?)/
getHandDecrease/decrementBuffTurns`（handDecreases ∈ BUFF_LIST_FIELDS，按 turns 分组
加算、回合末倒计时、turns=None 永久）+ 参考单测 BuffManager.test.mjs + wiki
`data/knowledge/buffs.json`「手札減少」（合算、≥3 抽 0、**只影响回合开始抽牌、不影响
效果抽牌**））：`LessonSim.hand_decreases` / `ExpectState.hand_decreases`（timed 列表，
-1 永久）+ `_draw_hand` / `turn_draw_count` / beam 下一手 / `sim_from_state` 补手牌
同口径 `max(hand_size−Σ,0)`；卡效果抽牌（ExamCardDraw）不受影响。来源=主数据
`ExamGimmickStartTurnCardDrawDown`（塔阶段 gimmick「手牌减少1（∞回合）」，exam_start，
12 段 / 6 件初星灯光紫 stage_023/026）；参考 DSL 无 setHandDecrease 用法（参考引擎标注
UNVERIFIED）——机制按参考引擎实现、来源/数值按主数据+wiki，不猜。**nullifyDebuff 拦截
未建模**（参考 nullifyDebuff blocks setHandDecrease；本模型 ExamAntiDebuff 本就 no-op，
留 P1-4 相关）；countDebuffs（低下状態の数）同未建模。
**⑤ pride 自尊**（BSD-3 `resolvers.js::resolveScore` f :178-184 `if (prideTurns)
scoreBuff += Math.min(Math.min(goodImpressionTurns, motivation) * 0.02, 0.5)` +
`constants.js` EOT_DECREMENT_FIELDS :331 / WHOLE_FIELDS :415）：`LessonSim.pride_turns` /
`ExpectState.pride_turns`；出牌分与回合末好印象在 f 段加算 `min(min(好印象,干劲)×20, 500)`
千分比（与 score_buffs 累加后一次乘，在メタモルフォーゼ披露之后、支度/不调之前，同 B9
口径）；prideTurns 回合末 -1（好印象结算之后）；score>0 门（纯 buff 牌不吃）。
**来源离线可确定**（主数据+参考 DSL 交叉，pIdol 117「初志貫徹」/118「理論武装して」=
雨夜燕 idolId 13）：卡「我、绝不」（p_card-02-ido-3_140，SSR/理性/偶像固有，4 强化变体）
`ExamLessonValueMultipleDependReviewOrAggressive` turn=5 ↔ skill_cards.csv 632/633
`if:motivation>=9, prideTurns+=5; cardUsesRemaining+=1; goodImpressionTurns+=8/9; drawCard`；
条件门=出牌前干劲>=9（主数据 trigger `e_trigger-none-card_play_aggressive_up-9` 结构化
解析 `pride_min_motivation_from_trigger`；未知 trigger 保守不给；本牌自己的干劲加成不算
进门槛；再演翻倍）+ P 道具「一笔入魂/+」（pitem_02-2-117-0/1，SR）turn=2/3 + 干劲+4/5 ↔
p_items.csv 354/355 `at:motivationIncreased { if:isDirectEffect & goodImpressionTurns>=6
{ prideTurns+=2/3; motivation+=4/5 }; limit:1 }`（status_gain aggressive & 好印象>=6 &
limit1 按道具计；isDirectEffect=本模型 STATUS_GAIN 只从卡直接效果发射，P 道具给的干劲不触发）。
**落地（纯增量）**：lesson.py/expectimax.py（hand_decreases/pride_turns 双镜 + canonical +
state_from_sim/sim_from_state + 叶子快照对齐 + beam turn_draw_count）+ p_items.py
（HAND_DECREASE_EFFECTS/PRIDE_EFFECTS → hand_decrease/pride_turns target +
PItemDelta.hand_decreases/pride_turns + _apply_modifier_target）+
CardSpec.pride_turns/pride_min_motivation（sim_produce MODELED_EFFECTS 33→34、
CardRow 33→35 元组；play_choice._effect_fields + pride_min_motivation_from_trigger）+
build_p_items.py 重标注重建 p_items.json（**无需改代码**，分类纯函数驱动；modifier
371→385 段，implemented **1042→1056/1849**；逐条 diff 校验仅 14 条记录标注变化：
2 pride + 12 hand_decrease）。既有断言随规则更新（test_sim_produce MODELED 34、
test_p_items no-op 参数表移除已实现类型）。
**评测牌组/gkbench loadout 组成不变 / 重标定**：自尊卡 score=0 且 SSR 本就不进 build_pool；
gkbench 688 loadout / 94 唯一道具 id 无「一笔入魂」（117）也无塔 gimmick（tower）→
**sim_engine_ab 重标定：改前/改后 64 局逐位相同（差异=0）**——seed 9000/9100 各 16 局
rules/expectimax budget 800ms，逐局非时间字段全等（`data/_p12_ab_compare.py`，不提交）；
expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，15/0/1 与 11/0/5，C+ 100%，
0 blocked / 0 error），B3 结论保持。**旧 B11 数据/模型是旧规则口径**（用户指定全保留
不覆盖）：阶段2 重采新 seed 块练新批再新旧对比；参照臂需按新规则重评。
**测试/基线**：tests/test_p12_hand_decrease_pride.py **36 条**（抽牌修正/自尊公式/来源/
双镜/解析/叶子）；ruff 通过；全量 pytest **1389/1（1390 收集 / 91 文件）**；①③④⑤ 复跑不变。
重标定产物 out/_p12_ab_{before,after}_{9000,9100}.json（gitignore）；一次性脚本
data/_p12_ab_compare.py / _p12_idol_map.json 不提交。
文档：RULES_REFERENCE §0/§1/§2/§5.5/§6/§7；WORKPLAN §0/P1-2/开场白；
HANDOVER_NEXT §0/§2/§4 T5/§8.0/§8/开场白；INDEX；HANDOVER 二·补四十五。
提交 `feat b8fc944`（规则代码+测试+数据标注+文档）+ docs(handover) 哈希记录。
**下一会话（P1-3，用户已确认 A 顺序，不用再问）**：⑥ hold 保留区建模（zone +
2 件张数条件 + hotfix 1；LessonSim/ExpectState 双镜；holdCard/holdThisCard/holdSelected
来源 + lockStanceTurns 随同；P1-1 回手钩子已就绪）。每项 DoD：参考证据+代码+单测+
RULES_REFERENCE 更新+sim_engine_ab 重标定；旧数据模型全保留；完成后按 §8 交接+发 P1-4 开场白。

**上一轮交接记录（2026-11-24，P1-1 —— 阶段1 首批：r10 行为探针 + 全力回合 + のんびり指針，BSD-3 有据）**：
用户已确认 A 顺序首批（不用再问）。开工基线 ①–⑤ 全绿（HEAD 63bbb1f，② 1318/1、
1319 收集 / 89 文件，216.82s）；Hindsight 记忆确认（synced=false 后台深化中属正常；
r10 过时记忆页已 ingest Correction 纠正为「复合门未过不入库」）。
**① r10 行为探针**（`data/_r10_behavior_probe.py`，复用 r9 口径，纯 net 确定性；
输出 `out/_r10_behavior_probe.json`）：small 500 局 v6/r10/v1 + large 120 局 v6/r10。
**判定：残留 small 回退（−0.256）已非 v1 风格贪即时分为主**——首分歧贪即时分偏置
r9 24:9（2.67×）→ r10 11:8（1.375×，近均衡）；r10 对 v1 耐心比 25:11（2.27×）恢复
v6 水平（29:13=2.23×），r9 当时被拉到 18:17（1.06×）；决策一致率 96.25%→97.25%、
整局相同 433→447/500、分歧局 67→53、CLEAR 翻转 0:5→1:1 对称。残留方向混合
（更低即时分 20/零换正 8/正换零 11）= 无方向漂移噪声（通道 2 输入侧场景漂移的行为级佐证）。
large 增益机制不变（+27.08/120 局、早回合 buff 86/110、0 次贪即时分分歧、CLEAR 25:1）。
→ **r11 small 上采样仍是对症变量；换教师消 v1 拉扯不再是首要杠杆**。详见 R9_ANALYSIS §9。
**② 全力回合**（BSD-3 constants.js FULL_POWER_EFFECTS/FULL_POWER_CHANGED_EFFECTS +
TurnManager.startTurn + BuffManager.setStance + contest-fidelity 美鈴回放）：以全力开始
的回合 extra_plays += 1（连续全力每回合都有；温存→全力边界后 = 解除1+全力1 = 2 次额外）；
held 保留区全部回手（moveHeldCardsToHand 无手牌上限检查；来源 holdCard/holdThisCard 留
P1-3，钩子用合成保留牌验证）；全力期间禁切指針（stance_change_allowed 守卫；全力值获得
不受影响，resolveFullPowerCharge 独立）。
**③ のんびり指針**（STANCE_CHANGED_EFFECTS leisure 三条 + resolveScore/resolveCost ×0 +
skill_cards.csv 540-545/834 + wiki 熱意 N=10 + contest-fidelity）：Stance.LEISURE 分数/费用 ×0；
解除 固定元気+5/+1 出牌/熱意+10，**→全力时熱意改为全体卡打分成长+10**（target:all g.score+=10
是 cardMap growth：score_growth_all 永久加算进白值、每次出牌生效、可叠加，不是即时分）；
温存→のんびり不触发温存解除（stance!=leisure 条件）；のんびり期间禁切温存；来源 = 卡预约
（ExamOverPreservation 4 族 13 行：のんびり屋さん/休み休み前へ/屋上からの景色 永久温存中触发 +
星々を見下ろす一番星 limit3 非温存触发；LEISURE_RESERVE_SOURCES 卡 id 证据表，card_meta
别名交叉）+ P 道具 stance_leisure 直给（夜空を従える花 2 件标注；触发时机
card_play_interval_after 是 B8 遗留未支持 → 仍保守不触发，目标机制本身就绪）。
**落地（纯增量）**：stance.py（LEISURE/守卫/证据表/leisure_reserve_for）+ enthusiasm.py
（release 扩 4 元组 + LEISURE_RELEASE_* 常量）+ lesson.py/expectimax.py（held/leisure_reserves/
score_growth_all 双镜 + canonical + state_from_sim/sim_from_state + _apply_leisure_reserves(_state)
+ 全力 enters_full 分支）+ leaf_data.py（叶子快照对齐）+ p_items.py（stance_leisure target/
classify/FLAG/STATUS_NAMES/delta）+ sim_produce.py（MODELED_EFFECTS 32→33、CardRow 31→33 元组、
ExamOverPreservation 预约解析）+ play_choice.py（旧 ExamOverPreservation→preservation 误映射
移除——values 恒空从未生效；inner 只认 ExamOverPreservation 不展开其它附魔）+
build_p_items.py 重标注重建 p_items.json（modifier 369→371 段；已实现计数仍 1042/1849：
2 段触发未支持）。release 6 调用点 + 既有测试断言随规则更新（test_t5_enthusiasm 边界 2 次、
test_b2_leaf 快照 2 次、test_sim_stance 倍率表 +leisure、test_sim_produce MODELED 33）。
**评测牌组组成不变 / 重标定**：のんびり来源卡 score=0 或 SSR/Legend 本就不进 build_pool；
small 牌组无全力值卡（全力规则零触达）、large 冲刺全力值 1 但 9 回合攒满 10 概率低 →
**sim_engine_ab 重标定：改前（git stash）/改后 64 局逐位相同（差异=0）**——seed 9000/9100
各 16 局 rules/expectimax budget 800ms，逐局非时间字段全等；expectimax 仍显著强于 rules
（Δ+372.2 / +219.1 评价点，15/0/1 与 11/0/5，C+ 100%，0 blocked / 0 error），B3 结论保持。
**旧 B11 数据/模型是旧规则口径**（用户指定全保留不覆盖）：阶段2 重采新 seed 块练新批再
新旧对比；参照臂需按新规则重评（门基线随之重定）。
**测试/基线**：tests/test_p1_stance_rules.py **36 条**（纯规则/全力/のんびり/P 道具/双镜/
解析/叶子）；ruff 通过；全量 pytest **1354/1（1355 收集 / 90 文件）**；①③④⑤ 复跑不变。
探针产物 out/_r10_behavior_probe.json（gitignore）；一次性脚本 data/_r10_behavior_probe.py /
_p1_probe*.py 不提交。
文档：RULES_REFERENCE §0/§1/§2/§5.2/§5.4/§6/§7；R9_ANALYSIS §9；WORKPLAN §0/P1-1/开场白；
HANDOVER_NEXT §0/§2/§4/§8.0/§8/开场白；INDEX；HANDOVER 二·补四十四；EXPECTIMAX B11 r10 注记。
提交 `feat f430451`（规则代码+测试+数据标注+文档）+ docs(handover) 哈希记录。
**下一会话（P1-2，用户已确认 A 顺序，不用再问）**：④ handDecrease 抽牌修正
（TurnManager.startTurn cardsToDraw=max(3−handDecrease,0)；来源 ExamHandDecrease 类效果/
P 道具，BSD-3 有据才做）⑤ pride 自尊（resolveScore f：min(好印象,やる気)×0.02 上限+0.5；
prideTurns 来源能离线确定才做，否则记缺口留阶段3）。每项 DoD：参考证据+代码+单测+
RULES_REFERENCE 更新+sim_engine_ab 重标定；旧数据模型全保留；完成后按 §8 交接+发 P1-3 开场白。

**上一轮交接记录（2026-11-23 晚，B11 r10 —— 按场景 std 归一化：small 回退收窄 39% 但仍显著、large 增益保持，复合门未过不入库）**：
用户已选定（r9 解释报告后「r10 按场景 std 归一化」，不用再问）。开工基线 ①–⑤ 全绿
（HEAD 7914171，② 1306/1、1307 收集 / 88 文件，208.38s）；Hindsight 记忆确认
（synced=false 后台深化中属正常；r9 门状态以 EXPECTIMAX + R9_ANALYSIS 为准）。
**落地（纯增量）**：`train_ei_policy --norm-by-scenario`（store_true，默认关）——只作用于
**多文件自对弈拼接**：各文件 y 先除**自身 std**（max(std,1e-6) 同原口径）再拼接，main 不再除
全局 std；scenario 取 npz `meta.args.scenario`（缺失记 unknown）；逐文件 std 按**加载时全量
文件**计算（下采样之前）；mix 记 `norm_by_scenario=True` + `scenario_std`（scenario→逐文件
std 列表）、`selfplay_adv_std=None`；multi_file 逐文件补 `norm_std`；**单文件路径/demos 不受
影响**。**默认逐位不变**：改前/改后 4 参照模型 sha256 一致（单文件 3 个与 r9 参照相同
28efed56…/b43dc14d…/e668547c… + 多文件全局 std 新 golden c5d48db7…，
`data/_r10_norm_baseline.py`）；X 侧 mean/scale 逐位不变（单变量=标签口径）。
**数据/训练（复用 r9 数据，无需新采集）**：320675 行（自对弈 272574 = small 145605 +
large 126969，示范 48101，占比精确 0.150）；192×96/1200ep/lr1e-3/l2 1e-4/seed 0 全同 r9；
逐场景 std small **12.2115** / large **24.0878**（vs 全局 18.7065）；**能量份额实测
small 20.9%→49.0% / large 70.9%→42.7% / demos 8.2% 不变**（R9_ANALYSIS §6 预测吻合）；
val 排序 0.823（r9 0.824，混合靶）；2047.9s（`OPENBLAS_NUM_THREADS=8`，复现命令带此 env）。
**评测（500 局修正协议；参照臂与 r9 JSON 逐位一致：small500 v6/beam、large500 v6/beam/greedy
全 500 局；large 前 120 水位 291.6083/305.3417/212.4083、v1 277.2417 复现文档数字）**：
- **large500（3000–3499，主门）：r10 314.9 vs v6 285.8，+29.1 CI[+25.8,+32.3] PASS**
  （W/T/L 371/46/83）；**vs beam 301.3：+13.6 CI[+10.3,+16.9] 仍显著超**（CLEAR 62.4% vs
  beam 50.6% / v6 39.0%）；新鲜块 6000：321.9 vs 298.8，+23.0 CI[+16.7,+29.4]；池化 620：
  +27.9 / vs beam +12.7；**r10−r9 同 seed −0.53 CI[−1.64,+0.57] 中性 → large 增益保持**；
- **small500（3000–3499，护栏）：r10 98.38 vs v6 98.64，−0.256 CI[−0.500,−0.012] 仍显著回退 ❌**
  （W/T/L 16/455/29；r9 −0.42 收窄 39%；r10−r9 +0.16 CI[−0.06,+0.38] 方向正未显著）；
  选择段 80：−0.34 CI[−1.2,+0.5] 中性；池化 580：−0.267 CI[−0.509,−0.026] 同显著；
  **vs v1（跨 JSON 同 seed 配对）：+0.322 CI[+0.032,+0.612] → 原 500 局门恢复**（r9 未保持）；
  vs beam：+1.90 CI[+1.09,+2.70] 绝对水位仍在；CLEAR 12.2%==v6（r9 11.2%，翻负局修回）。
**判定：复合门（large 显著改善 且 small 不回退）未过 → 不入库**（`data/_r10_promote.py`
程序化门校验：参照臂全过 → large 主门过 → small 护栏 CI 上界 −0.012 < 0 → 退出码 1，
未执行入库分支）：`data/knowledge/ei_policy_v6.json` 保持 r6 权重（sha256 33a80981… 未动），
engine=net 默认行为不变；r10 保留 `out/ei_r10_v10_mix.json`（不作 specialist 推荐——large
与 r9 统计不可分、small 略好但未过门）。**不硬凑显著**：−0.012 离 0 很近但预注册判据是
CI 上界 ≥ 0，差一点也是没过；池化 580 同样显著负，未换段捞显著。**F public-safe 仍被 small 挡**。
**结论：归一化口径修复有效但不充分**——标签稀释（通道 1）消掉大半，输入侧场景漂移（通道 2）
仍在（R9_ANALYSIS §8 预测证实）；v1 示范拉扯（通道 3）本轮未动（单变量纪律）。
**测试/基线**：`tests/test_ei_norm_scenario.py` **12 条**（多文件默认 golden 锚 / 开关单文件
逐位不变 / 逐文件 std 白盒 / meta 逐场景 std / 能量份额恢复 / X 侧不变 / 示范不受影响 /
下采样全量 std / 同场景多文件 / unknown 兜底 / 确定性 / 开关 golden）；ruff 通过；
全量 pytest **1318/1（1319 收集 / 89 文件，225.05s）**；①③④⑤ 复跑不变。
模型/数据/JSON 全在 out/（gitignore）：`ei_r10_v10_mix.json` /
`ei_r10_eval_v10_{large500,small500,small_select,large_fresh6000}.json`。
文档：EXPECTIMAX B11 r10；R9_ANALYSIS §8（预测 vs 实测）；WORKPLAN §0/B11/开场白；
HANDOVER_NEXT §0/§2/§4 T2/§8/开场白；INDEX；HANDOVER 二·补四十三。
提交 `feat ceb63ac`（开关代码+测试+文档）+ docs(handover) 哈希记录。
**下一候选（先问用户）**：r11 叠加 small 上采样（R9_ANALYSIS §6 候选②，能量 →~66%，
与①叠加；若仍差再考虑教师←v6 消通道 3）/ 继续降档（教师←v6、15→0）/ 收 loop 转 T7 剩余 /
D1 补采集 / E0 实验 / 直接阶段 E 真机（T3→T1→T2，T2 已含 net 第四臂 + r9 large specialist）。

**上一轮交接记录（2026-11-23，B11 r9-large —— small+large 混合训练：large 首超 beam，small 显著回退，复合门未过不入库）**：
用户授权安排（「按你想法给下一个对话安排」→ lead 选定 r9-large，进 F public-safe 前必须）。
开工基线 ①–⑤ 全绿（HEAD 8641fde，② 1294/1、1295 收集 / 87 文件）；Hindsight synced=true
（r3–r8 门状态以 EXPECTIMAX + Correction 为准：v6 已过 500 局门）。
**落地（纯增量）**：`train_ei_policy --selfplay/--demos` 均 `nargs="+"` 多文件——按给出顺序
拼接、group 偏移防跨文件碰撞、seed 保持原值（重叠告警）、全局 std 归一化、教师占比对拼接池
下采样、`meta.multi_file` 逐文件明细（scenario/seed 段/标签 std）、sources 全列；
**单文件默认逐位不变**（改前/改后 3 参照模型 sha256 一致：28efed56…/b43dc14d…/e668547c…，
`data/_r9_multifile_baseline.py`）。
**数据（seed 纪律：与评测段互不重叠）**：large 自对弈 5000 局 **126969 样本**（v6 学生 argmax，
seed 900000–904999，均分 287.8，标签 std 24.09，322.6s；probe 前 100 局逐位复现）+
small 保留 r5 全量 145605（防 small 回退）+ 补采 v1 示范 1600 局 **23050 样本**
（seed 420000–421599，教师均分 98.6，SKIP 剔除 0）→ 示范合计 51984 下采样 **48101**，
自对弈 272574 全保（max_s=294576 解锁），总 **320675 行**，占比精确 **0.150**。
训练 192×96 / 1200 epochs / lr 1e-3 / l2 1e-4 / seed 0（全同 r6，单变量=加 large 数据）；
全局优势 std **18.71**；val 排序 0.824（混合靶，不可与 v6 0.861 直接比）；1871s
（`OPENBLAS_NUM_THREADS=8` 本机最优，复现命令带此 env）。
**评测（500 局修正协议；参照臂与 r6 JSON 逐位一致；large 前 120 水位 291.61/305.34/277.24/212.41
复现文档数字）**：
- **large500（3000–3499，主门）：r9 315.4 vs v6 285.8，+29.6 CI[+26.2,+33.0] PASS**；
  **vs beam 301.3：+14.2 CI[+10.9,+17.5] —— 首个 large 显著超 beam 的学生网**
  （CLEAR 62.6% vs beam 50.6% / v6 39.0%）；新鲜块 6000–6119：r9 322.9 vs v6 298.8，
  +24.0 CI[+17.8,+30.2] 独立佐证；池化 620：+28.5 / vs beam +13.3；
- **small500（3000–3499，护栏）：r9 98.2 vs v6 98.6，−0.42 CI[−0.67,−0.17] 显著回退 ❌**
  （W/T/L 16/441/43）；选择段 80：−0.8 CI[−1.7,+0.1] 方向负；池化 580：−0.47 CI[−0.72,−0.22]；
  vs v1（跨 JSON 同 seed 配对）：+0.16 CI[−0.14,+0.46] → 原 500 局门未保持；
  vs beam：+1.73 CI[+0.92,+2.54] 绝对水位仍在。
**判定：复合门（large 显著改善 且 small 不回退）未过 → 不入库**（`data/_r9_promote.py`
程序化门校验，未执行入库分支）：`data/knowledge/ei_policy_v6.json` 保持 r6 权重，
engine=net 默认行为不变；r9 保留 `out/ei_r9_v9_mix.json` 作 **large specialist**
（T2 large A/B 可 `--net-model out\ei_r9_v9_mix.json` 换臂）。**F public-safe 仍被 small 回退挡**。
**诊断（假设，未验证）**：全局 std 归一化稀释 small 信号——混合 std 18.71 vs v6 的 12.21 →
small 自对弈标签缩到 65%；large 行占自对弈 46.6% 且尺度大 → 梯度偏 large；示范 ±1 相对变强
且教师=v1（98.1）→ r9 small 98.22 恰落 v1 98.06 与 v6 98.64 之间，与「稀释+v1 拉扯」一致。
**深入解释报告（用户要求，证据链完整）：[R9_ANALYSIS.md](R9_ANALYSIS.md)**——信号能量
small 91.8%→20.9% / 输入场景维度重映射 / 决策行为 small 96.2% 一致（433/500 整局相同，
67 分歧局更贪即时分 24:9）vs large 59.8% 一致（早回合 buff 90/112，24 CLEAR 翻正）。
**候选修复（下一轮单变量，先问用户）**：① 按场景 std 归一化（最外科，纯增量默认不变）；
② small 上采样/补采 v6 small 自对弈；③ 两段式微调（需测 large 遗忘）。
**测试/基线**：`tests/test_ei_multifile.py` **12 条**（含单文件 golden 权重逐位锚 ×2）；ruff 通过；
全量 pytest **1306/1（1307 收集 / 88 文件，206.53s）**；①③④⑤ 复跑不变。
模型/数据/JSON 全在 out/（gitignore）：`ei_r9_selfplay_large.npz` / `ei_r9_demos.npz` /
`ei_r9_v9_mix.json` / `ei_r9_eval_v9_{large500,small500,small_select,large_fresh6000}.json` /
`ei_r9_probe_large.npz` / `_r9_ref_*.json`（逐位参照）。
文档：EXPECTIMAX B11 r9-large；WORKPLAN §0/B11/开场白；HANDOVER_NEXT §0/§2/§4 T2/§8/开场白；
INDEX；HANDOVER 二·补四十二。提交 `feat 39c289b`（多文件代码+测试+文档）+ docs(handover)
哈希记录（哈希另见 HANDOVER 七）。
**下一候选（先问用户）**：r10 按场景 std 归一化（修 small 回退、保 large 增益，进 F 前必须）/
继续降档（教师←v6、15→0）/ 收 loop 转 T7 剩余 / D1 补采集 / E0 实验 /
直接阶段 E 真机（T3→T1→T2，T2 已含 net 第四臂 + r9 large specialist）。
**用户已选（2026-11-23 晚，看完解释报告后）：r10 按场景 std 归一化**。

**下一会话安排（2026-11-23 晚用户选定：B11 r10 —— 按场景 std 归一化，修 r9 small 回退）✅ 已完成（结果见上方最近交接记录：small 收窄 39% 但仍显著、large 保持，复合门未过不入库）**：
- **前置**：§2 基线（期望 ② **1306/1**，1307 收集 / 88 文件）；r9 数据/模型齐全在 out/
  （`ei_r5_selfplay.npz` / `ei_r9_selfplay_large.npz` / `ei_r4_demos.npz` / `ei_r9_demos.npz` /
  `ei_r9_v9_mix.json`）；解释报告 [R9_ANALYSIS.md](R9_ANALYSIS.md)（证据链 + 修复预测）；
- **做法（纯增量，默认逐位不变 + 回归测试）**：`train_ei_policy` 加开关（如
  `--norm-by-scenario`，默认关）：多文件拼接时**各文件按自身 std 归一化**（scenario 取
  npz meta.args.scenario；单文件路径不受影响）；mix/meta 记逐场景 std。用 r9 同数据配方
  重训 r10（320675 行 / 192×96 / 1200ep / 0.15 / `OPENBLAS_NUM_THREADS=8`，~31min）；
  **无需新采集**（复用 r9 数据，单变量=归一化口径）；
- **门（同 r3–r8 修正协议）**：large500（3000–3499）r10 vs v6 显著正 **且** small500
  不回退（vs v6 CI 上界≥0，且 vs v1 原门保持）→ 双过入库替换 `ei_policy_v6.json`
  （meta 补溯源；`data/_r9_promote.py` 门校验脚本改 r10 复用）；不过门如实记录，不硬凑；
- **预测（R9_ANALYSIS §6，代理估算，以实测为准）**：small 能量 20.9%→~49%、large
  70.9%→~43% → 大部分 small 回退修复、large 增益可能略缩但仍强；若 small 仍显著回退
  → r11 叠加 small 上采样（先问用户）；
- **参照臂**：beam 305.3 / v6 291.6 / v1 277.2 / greedy 212.4（large 前 120，seed 3000–3119）；
  small v6 98.6 / v1 98.1（500 局 3000–3499）；评测须无训练负载（beam 墙钟预算）；
- 规则见 §4 硬约束（SKIP 只在真没体力；禁静默回退 rules；一次会话只做 1 个任务）。
  完成后按 §8 交接：更新文档 + feat 提交 + docs(handover) 哈希提交，下一候选先问我。

**上一轮交接记录（2026-11-23，B11 v6 生产接线 —— engine=net opt-in，默认逐位不变）**：
开工基线 ①–⑤ 全绿（HEAD 3699403，② 1273/1、1274 收集 / 86 文件，202.74s）；
Hindsight bank 已播种（synced=false 后台深化中，属正常）；记忆页 B11 门状态过时
（仍写 r2 未过门）→ 已 ingest Correction 文档纠正（r3–r8 完成 / 500 局门 / v6 PASS）。
下一候选按约定先问用户，用户回「你推荐综合一下」→ lead 综合推荐并选定 **v6 生产接线**
（理由：T2 真机 A/B 的前置、模型无关管道不会因后续 large 训练返工、纯离线一会话可完成；
继续降档预期收益小——r3–r8 已证种子段结构；large 训练计算重且不阻塞接线）。
**落地（纯增量）**：`LessonPolicy` `_ALLOWED_VALUES["engine"]` +`net`、`DEFAULT_PARAMS`
+`net_model: None`、`__init__` +`net_model=` 关键字、`_decide_search` 分发 `_try_net`、
`_search_state` +`with_plan=True` 关键字（net 传 False，不注入采集全知 → public-safe；
expectimax/beam 逐位不变，回归测试锁定）、`_net_model()` 缓存加载（缺模型/坏格式抛错）、
`_try_net`（legal_cards argmax 优势分；有牌绝不 SKIP；全付不起 → SKIP/wait；
异常/失配 → None → RuleFallbackBlocked；reason 带优势分/候选数/ms）。
`auto_produce`：allowed_engines +net；`--net-model` > `produce.net_model` > 默认入库 v6；
缺模型起跑前 return 2；`[engine] net 模型 =` 日志；LessonPolicy 传 net_model。
**入库模型**：`data/knowledge/ei_policy_v6.json`（tracked，1013237 字节）=
out/ei_r6_v6_mix.json 逐权重拷贝 + meta.production 溯源（gate/fresh6000/pooled820/large）。
**如实记录**：生产 deck/discard 读不到 → 特征空集（与离线 state_from_sim 全牌库分布有差，
T2 才算数）；large 仍 −13.7 vs beam → large 生产候选仍是 beam；net 是 T2 第四臂不是默认。
**测试/基线**：`tests/test_ei_wiring.py` **21 条**；ruff 通过；全量 pytest
**1294/1（1295 收集 / 87 文件，202.95s）**；① 4/4+3/3、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155 复跑不变。
文档：EXPECTIMAX「B11 v6 生产接线」；WORKPLAN §0/开场白；HANDOVER_NEXT 开场白/§0/§2/§4 T2/§8；
INDEX；HANDOVER 二·补四十一。提交 `feat 9428aec`（接线代码+测试+文档）+ docs(handover)
哈希记录（哈希另见 HANDOVER 七）。
**下一候选（先问用户）**：继续降档（教师←v6、15→0）/ v6 large 训练评测（进 F 前必须）/
收 loop 转 T7 剩余 / D1 补采集 / E0 实验 / 直接阶段 E 真机（T3→T1→T2，T2 已含 net 第四臂）。
**下一会话安排（2026-11-23 晚用户授权「按你想法给下一个对话安排」→ lead 选定）**：
**B11 v6 large 训练评测（r9-large）**——补 large 泛化缺口（v6 large 确认段 291.6 vs
beam 305.3，−13.7；r3–r8 已证数据量+容量对 large 泛化有效），进 F public-safe 前必须；
产出更强网直接换 `data/knowledge/ei_policy_v6.json` 复用本次接线（模型无关管道）。
采集/评测脚本已支持 `--scenario large`（31 张/9 回合/体力 60/CLEAR 300/PERFECT 450）；
`train_ei_policy --selfplay` 目前单文件，small+large 混合（防 small 回退）预计需纯增量
多文件支持。门判据按 r3–r8 修正口径（500 局或多段池化，单段 120 局只作快速筛查）；
large 参照臂 beam 305.3 / v6 291.6 / v1 277.2 / greedy 212.4（确认段 seed 3000–3119）；
small 500 局门（3000–3499）不得回退（v6 98.6 vs v1 98.1）；seed 纪律：large 自对弈用
新种子块（如 900000+，与评测段互不重叠）。开场白见本条下方会话发送版。

**上一轮交接记录（2026-11-23，B11 r3–r8 继续扶 + 门协议修正 —— v6 过门，显著强于 v1）**：
用户指令「PUBG 已退，重新训到学生显著强于老师才结束」+「Hindsight 修好了，补播种历史」。
**Hindsight 播种修复**：19:02 的 gitlog retain 因 qwen-plus max_tokens bug 整体失败、
daemon 修复后未 recover；经 daemon API 重注入 gitlog 种子文档（300 commits，strategy=gitlog，
gitlog-head:c06bb9f 标签）→ 提取成功（10 事实单元覆盖全项目历史），**synced=true**；
页面下次刷新重建；300 commit diff 深化由插件下次会话自动补。一次性脚本
`data/_hindsight_seed_gitlog.py`（不提交）。
**澄清**：训练/评测是确定性计算，不受游戏负载影响（beam 参照臂已验证逐位一致）；
同配方重跑结果相同，破平台须换变量。
**r3–r8 迭代（教师始终 v1@0.15，门基线 v1）**：r3 新学生数据（v2 自对弈 500000+）→
r4 数据×5（v3 自对弈 600000+ 5000 局 + 补采 v1 示范 2000 局 410000+ 解锁占比上限）→
r5 数据×10（v4 自对弈 700000+ 10000 局）→ r6 容量×2（192×96，1200 epochs）→
r7/r8 ε-greedy 探索（**新设计变量**：`play_selfplay explore_eps` / `--explore-eps`，
采集时概率 ε 随机选可出牌扩覆盖，标签仍精确重放 on-policy，硬规矩禁跳不变，
ε=0 逐位不变，net_action 生产语义不动；+7 条单测）。
**结果**：val 排序 0.818→0.862 饱和；确认段 3000（120 局）七轮恒 +0.2~0.6 未单独显著，
稳健段同样低，选择段恒 +0.9，未触碰块 6000 恒 +1.3~1.7 显著 → **差异由种子段决定
（该段 v1 可改进状态多少），非模型问题**；探索变量中性（覆盖假设否证）。
池化 440 局 v5/v6 +0.80 CI[+0.36,+1.21] 显著。
**门协议修正（用户批准，非事后捞显著）**：120 局门为 r1 检测 +2.6 设计、对 +0.5 效应
检验力 ~50%；确认段扩 **500 局（3000–3499）、判据不变（CI 下界>0）**：
**v6 98.6 vs v1 98.1：Δ=+0.6 CI[+0.2,+0.9] → PASS**（W/L 62/27）；独立佐证
fresh6000 **+1.7 CI[+0.6,+2.8] PASS**；池化 820 局 **+0.71 CI[+0.40,+1.02]**（W/L 101/41）。
vs beam：确认 500 局 98.6 vs 96.5（+2.1）。**v6（192×96，171300 样本）= 当前最佳学生**。
**处置**：用户任务「显著强于老师」达成；按设计下一轮可教师←v6、占比 15→0，**是否继续
先问用户**；生产接线仍未做（过门后才谈）；T2 候选暂不变；**large 泛化显著改善**：
v6 large 确认段 291.6 vs v1 277.2：+14.4 CI[+6.5,+22.2] PASS（CLEAR 45.0% vs 36.7%），
vs beam 305.3 缺口 −28.1→−13.7（收窄一半）；large 生产候选仍是 beam，v6 进 F 前
建议补 large 训练数据。
**后续轮次门协议**：确认门 = 500 局（3000–3499）或多段池化；单段 120 局只作快速筛查。
**测试/基线**：`tests/test_ei_explore.py` **7 条**；ruff 通过；全量 pytest
**1273/1（1274 收集 / 86 文件，205.92s）**；①③④⑤ 复跑不变。模型/数据/JSON 全在 out/。
文档：EXPECTIMAX B11 r3–r8 续；WORKPLAN §0/B11/开场白；HANDOVER_NEXT §0/§2/§8/开场白；
INDEX；HANDOVER 二·补四十。提交 `feat 47c1afa`（探索代码+测试+文档）+ docs(handover)
哈希记录（哈希另见 HANDOVER 七）。

**上一轮交接记录（2026-11-23，B11 渐退式专家迭代 第 2 轮 —— 教师←v1、占比 15%、large 首测：平台期 CONTINUE）**：
纯离线研究+代码任务（用户按「先问我」约定选定；一次会话 1 个任务 = 第 2 轮）。
开工基线 ①③④⑤ 全绿（HEAD 8768296）；② 首跑遇 drink_search 延迟守卫受游戏负载（TslGame）
抖动失败（11.8–12.4ms > 10ms，同搜索 5 轮 6.6–12.1ms 随负载波动、同 HEAD 19:0x 全绿、
r2 代码不碰搜索）→ 用户确认「继续做，绿基线后补」，负载回落复跑 **1266/1 全绿**，未改门槛。
**落地（纯增量，默认行为逐位不变）**：`build_ei_dataset.py --teacher-net <model>`（demos
教师=学生网，`net_action` 逐决策记录，软目标同口径 +1/−1/(k−1)，硬规矩禁跳 → 教师 SKIP
剔除恒 0；selfplay 模式拒收；meta.teacher_kind）+ `eval_ei.py --baseline-net <model>`
（门基线=上一轮学生 `teacher_net` 臂，beam 臂保留作绝对水位；verdict 记 baseline/
baseline_model/beam_mean；缺省基线=beam 第 1 轮口径不变）+ `train_ei_policy.py --round N`
（meta.task 轮次，默认 1）。large 无需新代码（`--scenario large` r1 已支持，本轮首用）。
**数据/训练**（small；seed 纪律：示范 400000–400399 / 自对弈 300000–300999，与 r1 错开；
评测段 2000–2079/3000–3119/4000–4119 + 新鲜块 5000–5119）：v1 教师示范 400 局 / 1981 决策 /
**5773 样本**（剔除强制 40 / 教师 SKIP **0**；教师均分 98.1；2.1s）→ v1 自对弈 1000 局 /
4946 决策 / **14526 优势样本**（std 12.00，v1 均分 98.0；37.3s）→ **v2 85/15**（17089 样本，
教师占比精确 0.150，train MSE 0.196 / val MSE 0.254 / 排序 0.818）+ 消融 **v2_bc**
（纯 v1 示范自蒸馏 5773 样本，val 排序 0.933）。
**评测（B1 修正 harness 配对，unknown，--no-within；门基线=v1）**：
small 选择段 v2 99.2 vs v1 99.2（−0.0 CI[−0.9,+0.9]）；**确认段 120 局 v2 97.9 vs v1 97.5：
+0.4 CI[−0.4,+1.2] → CONTINUE（平台期）**；稳健 4000 −0.2 CI[−0.8,+0.3]；新鲜块 5000
（两轮未触碰）−0.1 CI[−1.2,+1.1]——四段全中性、确认段 98/120 局逐位相同。
消融：v2_mix−v2_bc=**+0.54 CI[−0.40,+1.48]**（on-policy 成分连续两轮方向正、未独立证明）；
v2_bc−v1=−0.13 CI[−0.87,+0.60]（纯自蒸馏中性）；v2−beam=+2.99 CI[+1.37,+4.62]、
v1−beam=+2.58 CI[+1.07,+4.10]（与 r1 逐位一致；beam 参照臂 94.9/97.3/97.8 逐位复现）。
**large 首测（31 张/9 回合/体力 60/CLEAR 300/PERFECT 450）**：选择段 v2 266.6 / v1 281.4 /
beam 302.5（v2−v1 **−14.8 CI[−21.3,−8.3]** 显著）；确认段 v2 270.8 / v1 277.2 / beam 305.3
（v2−v1 −6.5 CI[−13.2,+0.3]；**v1−beam −28.1 CI[−36.0,−20.2]**，CLEAR 36.7% vs 53.3%）；
greedy 212–220（两学生 +58~65 显著强）。large beam 臂另跑复核逐位复现（recheck JSON）。
**结论**：small 训练不泛化 large（9 回合长 horizon 天花板是 beam 跨回合规划）；
v2 的 small 平台期训练还轻微损害 large 泛化。
**处置**：按设计**教师占比不降（保持 0.15）**、如实记录平台期（渐退节奏是超参不是定律）；
生产接线未做、T2 候选暂不变（beam+全知/tiebreak）；v1 仍是 small 最佳学生（+2.6 vs beam）。
**下一会话候选（先问用户再启动）**：① B11 第 3 轮继续扶——同配方再采边际收益存疑，
建议换变量（large 场景训练数据 / 更大学生网 / 每动作多延续优势标签）；② 收 loop 于 v1，
转 T7 剩余（纯函数状态重放/自动复盘页）/ D1 补采集 / E0 实验 / 直接阶段 E 真机。
学生网要进 F 阶段 public-safe 候选必须先过 large 训练/评测（gkbench hif 本戦 9–12 回合）。
**测试/基线**：`tests/test_ei_policy_r2.py` **15 条**（teacher-net 示范/确定性/拒收/峰值/
beam 默认不变；baseline-net 门/默认仍 beam/同模型自比中性；0.15 精确占比/round meta；
large 配置/net 确定/重放优势/CLI 冒烟）；ruff 通过；全量 pytest **1266/1（1267 收集 /
85 文件，372.30s）**；①③④⑤ 复跑不变。模型/数据/JSON 全在 out/（gitignore）：
`ei_r2_demos.npz` / `ei_r2_selfplay.npz` / `ei_r2_v2_mix.json` / `ei_r2_v2_bc.json` /
`ei_r2_eval_v2_select/confirm/robust4000/fresh5000/large_select/large_confirm/large_confirm_recheck.json` /
`ei_r2_eval_v2bc_confirm.json`。
文档：EXPECTIMAX B11 第 2 轮（结论先行/代码/数据训练/评测/处置风险/复现命令/测试基线）；
WORKPLAN §0/B11/开场白；HANDOVER_NEXT §0/§2 期望值（1251→1266）/§8/开场白；INDEX；
HANDOVER 二·补三十九。提交 `feat e307fc6`（代码+测试+文档）+ docs(handover) 哈希记录；
开工基线复核 `c25509d`（哈希另见 HANDOVER 七）。

**上一轮交接记录（2026-11-23，B11 渐退式专家迭代 第 1 轮 —— policy/advantage 学生，确认段评测门 PASS）**：
纯离线研究+代码任务（用户按「先问我」约定选定启动；一次会话 1 个任务 = 第 1 轮）。
开工基线 ①②③④⑤ 全绿（② **1223/1**，1224 收集 / 83 文件，195.97s；HEAD=1376d21 核对一致，
C1 定稿 1ac8bb2 之后两条文档提交）。**落地**：新 `src/gkagent/sim/policy_mlp.py`
（137 维 = B2 104 状态特征 + 33 动作特征 → 96→48→1 优势分；`net_action` 编码用户硬规矩：
有牌绝不 SKIP、推理异常直接抛出无静默回退；save/load 格式 `gkagent.policy_mlp.v1`）+
`src/gkagent/sim/policy_data.py`（`DecisionRecordingSim` 只记真实决策；**精确重放分支**
优势标签：同 (deck,config,seed) 重放动作前缀 → `state_from_sim` 逐字段全等校验（失配抛错）
→ 打候选牌 → 当前学生打完 → A=R−mean(R)；不走搜索镜像，无 B2-R 式快照口径坑）+
`scripts/build_ei_dataset.py`（demos/selfplay）/ `train_ei_policy.py`（BC/混合、seed 分组 9:1、
教师占比确定性下采样）/ `eval_ei.py`（配对评测门，复用 `eval_t4_b1._table`，退出码 0=PASS）；
`eval_known_draw.play` 加 `policy="net"/"greedy"` + `net_model`（纯增量，默认逐位不变，测试锁定）。
**第 1 轮数据/训练**（small；seed 纪律：采集 100000+/200000+，选择 2000–2079，确认 3000–3119，
稳健 4000–4119）：教师示范 400 局 / 1985 决策 / **5747 样本**（beam width4/100ms+tiebreak1e-3，
unknown；剔除强制 37 / 教师有牌却 SKIP 23；教师均分 96.3）→ **v0 BC**（val MSE 0.204 /
排序命中 0.889）→ v0 自对弈 1000 局 / 4905 决策 / **14314 优势样本**（std 12.09，v0 均分 96.0，
含全部分支重放仅 17s）→ **v1 70/30**（19156 样本，教师占比 0.300，val 排序命中 0.822，
val 靶与 v0 不同不可直接比）。**评测（B1 修正 harness 配对）**：选择段 v0 +0.1（中性）/
v1 +1.9 CI[−0.2,+4.0]；**确认段 120 局 v0 97.3 / v1 97.5 vs 教师 94.9：
v0 +2.4 CI[+0.7,+4.1] / v1 +2.6 CI[+1.1,+4.1] → 双双 PASS**；稳健块 v1 101.6 vs 97.8
+3.8 CI[+1.6,+6.0]（CLEAR 17.5% vs 13.3%）；学生 **0.40ms/决策**（500 局探针）。
**消融（如实，本轮最重要结论）**：纯 BC v0 也过门、v1−v0=+0.2 不显著 → 第 1 轮红利主力 =
**逐决策蒸馏 + 硬规矩禁跳**（学生每步重评估 ≈ 每决策重规划的 beam，且绝不提前 SKIP；
教师每回合规划一次会过期、400 局里 23 次有牌却 SKIP）；on-policy 优势成分方向正
（选择段 +0.1→+1.9、确认段 +2.4→+2.6、CLEAR 同向）**但未独立证明**。
**处置**：按设计**放手**——第 2 轮教师←v1、占比 30→15；生产接线未做（T2 候选暂不变：
beam+全知/tiebreak）；学生只看可观测状态（不用 seed/known_draw）→ 未来 gkbench ranked
public-safe 候选；模型/数据/JSON 全在 out/（gitignore）：`ei_r1_demos.npz` / `ei_r1_selfplay.npz` /
`ei_r1_v0_bc.json` / `ei_r1_v1_mix.json` / `ei_r1_eval_*.json`。**风险**：模拟器保真度天花板
（fresh buff/随机生成卡 RNG 未建模）、仅 small 场景（large 9 回合未测）、离线增益要过 T2 真机才算数。
**测试/基线**：`tests/test_ei_policy.py` **28 条**；ruff 通过；全量 pytest
**1251/1（1252 收集 / 84 文件，190.62s）**；①③④⑤ 复跑不变。
**下一会话任务（先问用户再启动）：B11 第 2 轮**——
- 前置：§2 基线（期望 ② **1251/1**，1252 收集 / 84 文件）；v1 模型在 `out/ei_r1_v1_mix.json`
  （若被清掉按 EXPECTIMAX B11 复现命令重建，约 1 分钟）。
- 做法：教师←v1（`build_ei_dataset.py --mode demos` 需支持「教师=学生网」——第 1 轮 demos
  只接 beam，第 2 轮加 `--teacher-net <model>` 走 net_action 逐决策记录，软目标同口径）；
  教师占比 0.15；自对弈用 v1 采新数据（seed 另起 300000+）；训练 v2 → 配对评测门
  （基线=**v1 学生**，不再是 beam；同时报 vs beam 的绝对水位）；**加 large 场景配对**
  （9 回合真机口径，`--scenario large`，教师/学生同场景）。
- 判定：v2 显著强于 v1 → 继续降档（15→0 需再一轮）；不显著 → 继续扶或如实记录平台期
  （渐退节奏是超参不是定律）。过门后才谈生产接线（engine= 口径 + 可观测性 + 红线）。
- 备选候选（用户未选时）：T7 剩余 / D1 补采集 / E0 实验 / 直接阶段 E 真机。
文档：EXPECTIMAX B11（结论先行/设计/实现/数据训练/处置风险/复现命令/测试基线）；
WORKPLAN §0/B11/开场白；HANDOVER_NEXT §0/§2 期望值（1223→1251）/§8/开场白；INDEX；
HANDOVER 二·补三十七。
提交 `feat e26387b`（代码+测试+文档）+ docs(handover) 哈希记录；开工基线复核 `7689a2e`
（哈希另见 HANDOVER 七）。
**同会话附带（环境，用户指定「开一下 hindsight」）**：Hindsight 本地记忆启用——daemon 模式
（hindsight-embed 1.2.3，profile coding-agent，127.0.0.1:9077，内嵌 PostgreSQL 18），
LLM=百炼 qwen-plus（DashScope 兼容端点，key 取自 DSH 凭据库 DASHSCOPE_API_KEY，启动实测 200）/
embeddings=text-embedding-v4（1024 维）/ reranker=本地 hs-rerank-1（hf-mirror 下载）；
`~/.hindsight/coding-agent.json` = serverMode daemon + mapPathToBank
`D:\Games\gakumas-agent → coding-agent::gakumas-agent`；用户环境变量持久化
HINDSIGHT_API_LLM_*（重启自愈）+ UV_DEFAULT_INDEX/UV_INDEX_URL（清华镜像，修 PyPI 超时）。
**坑**：DSH 常驻插件配置加载时读一次，改配置后**老会话工具客户端钉死旧值**（plugin_manager
热重载也不重建会话级客户端）——必须开新会话；bank 按会话工作目录解析，新会话开在
`D:\Games\gakumas-agent` 才进对 bank；daemon 首次启动含 reranker 下载，CLI 等待窗可能超时
但进程继续初始化，轮询 /health 即可。下一会话记忆工具可用（先 search_pages）；
详见 HANDOVER 二·补三十八。

**上一轮交接记录（2026-11-23，C1 执行层可靠性 —— tap 确认/重试 + 提权检查 + 帧预算 + 每步可复盘）**：
纯离线代码任务（用户指定本会话唯一任务；真机验收留阶段 E）。开工基线 ①②③④⑤ 全绿
（① 4/4+3/3、② **1155/1**（1156 收集 / 79 文件，197.90s）、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 逐张 1125/1155=97.4%）；HEAD=92eea36 核对一致。
**落地**：新 `src/gkagent/runtime/tapguard.py`（TapExpectation 动作前预算下一帧 +
TapGuard 互验：confirmed / **moved 不重试**（rev254）/ 同屏 retap≤2 / **lost 上报绝不静默 SKIP** /
加载暂停帧 postpone（rev135）；PickerGuard 两段式选牌：选中后只重试确认不重点卡位、
selected=None 保守按已选中、failed 重置重新选卡）+ `src/gkagent/device/privilege.py`
（游戏 elevated/本进程 non-elevated → UIPI 静默丢点击：启动 blocked 拒跑 +
`elevation-blocked` failure + 管理员提示；unknown 只告警；假 API 可注入）+
`src/gkagent/runtime/trace.py`（StepTrace 每步 screen/action/point/**reason**/engine_note/
预算/互验 outcome/tries）+ `scripts/replay_steps.py`（离线复盘 CLI）。
接线：`TickResult` 补 point/reason/expect（向后兼容）；`decide()` 每击自动预算
（弹窗确认/回合结束「是」/通信错误=dialog-gone，其余=画面应变化）+ 关键分支动作理由；
card-reward 接 PickerGuard（同屏只重试「领取」）；`auto_produce` 启动提权检查、
非课程分支每步先互验再决策（retap/lost/confirmed/moved，**连续 3 次 lost 止损停局**）、
饮料换 `attempt_drink`（对话未开重试槽位≤2，失败写 `drink-dialog-lost`）、
每步 `data/step_trace.jsonl`、局末 `[tap]` 汇总。参考 GKMSMAA follow/winpriv 架构
**全部自写不拷贝**（AGPL）。**DoD**：失败场景单测 68 条（tapguard 28 / privilege 18 /
trace 12 / wiring 10）+ 每步日志可离线复盘 ✅；用户规则不变（SKIP 只在所有牌付不起、
禁静默回退 rules、lost 升级=停局修 root cause）。**如实记录**：picker 选中态无可靠离线探针
（未归档真机奖励选卡帧），阶段 E 可补读回；runas 自动提权未做（约定管理员终端手动跑）；
T7 剩②纯函数状态重放/③自动复盘页。**测试/基线**：ruff 通过；全量 pytest
**1223/1（1224 收集 / 83 文件）**；①③④⑤ 不变。**下一候选（先问用户再启动）**：
渐退式专家迭代（学 policy/advantage、摸索 70%+老师 30% 逐轮放手、学生过评测门后当下一轮老师，
EXPECTIMAX B2-R 末段）；或 T7 剩余 / D1 补采集 / E0 实验（需独立副本）→ 真机 T3→T1→T2。
文档：WORKPLAN §0/C1/开场白；HANDOVER_NEXT §0/§2/§4 T7/§8/开场白；INDEX；HANDOVER 二·补三十六；
LIVE_RUN（真机手册 C1 入口：起跑自检第 7 条提权、跑完第 ④ 件 replay_steps 复盘、
日志/失败标记速查表、已知坑第 6 条 UIPI）。
提交 `feat 6a47185`（代码+测试+文档）+ `docs(handover) 9a4e054`（哈希记录）+ 交接定稿 `1ac8bb2`
（LIVE_RUN 真机手册 C1 入口；哈希另见 HANDOVER 七）。
**阶段 E 真机验收 C1 时看**：日志首行 `[priv]`、每步 `data/step_trace.jsonl`、
`replay_steps.py --episode <ep> [--anomalies]`、局末 `[tap]` 汇总；
新 failure 种类：`elevation-blocked` / `tap-lost` / `drink-dialog-lost`。

**上一轮交接记录（2026-11-23，B2-R 高预算验证 —— 仍 FAIL，学习叶子路线关闭）**：
纯离线任务（用户指定本会话唯一任务）。开工基线 ①②③④⑤ 全绿（① 4/4+3/3、② **1155/1**
（1156 收集 / 79 文件，202.32s）、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384
逐张 1125/1155=97.4%）；HEAD=b2b786e 核对一致；候选模型 `out/b2r_leaf_mlp_small.json`
在位（val r²=0.906 / σ=11.14，26,500 样本）。
**命令**（选择段 80 局 seed 2000–2079，unknown，width8/300ms 同预算配对）：
`eval_b2.py --leaf-model out\b2r_leaf_mlp_small.json --games 80 --seed 2000 --info unknown
--width 8 --beam-budget-ms 300 --within-budget-ms 300 --ensembles 0.75
--json out\b2r_eval_highbudget_select.json`。
**结果（FAIL）**：beam 解析式 **93.9** → learned **89.4（−4.4 CI[−8.8,−0.0] ❌ 显著负，
32胜/14平/34负）** / ensemble 0.75 **93.9（+0.0 CI[−1.9,+2.0] 中性）**；within 家族
89.1 / learned 69.7（−19.4 ❌）/ ens 0.75 +0.1（中性），与 200ms 基线**逐位相同**；
全部 0 fallbacks。**判定：不显著正 → 按用户规则不跑确认段，学习叶子路线关闭，转 C1**。
**三个事实**：① 伤害 −7.0（width4/100ms）→ −4.4（width8/300ms）收窄但没转正——teacher 级
预算也兑现不了 teacher return，失配不是预算能消掉的；② **收窄主因是解析式基线自己变差**
（97.3→93.9，CLEAR 11.2%→7.5%），learned 绝对分几乎不动（90.3→89.4）——更强搜索对解析式
叶子也不是免费午餐（width8 更深优化悲观启发式；T2 候选仍 width4/100ms+tiebreak，不受影响）；
③ small 场景搜索提前收敛、300ms 预算很少触顶（评测墙钟 <80s，远低于 15–25 分钟预估；
within 逐位相同佐证）——小场景的约束是宽度不是预算。
**处置**：生产 leaf_model 保持关闭、beam 默认解析式叶子、T2 候选不含 learned leaf（均不变）；
**学习叶子（状态价值 MLP 叶子）路线正式关闭**——B3+ 规则下重训 FAIL（−7.2）、高预算 FAIL
（−4.4）、σ 校准 FAIL（×2/×4 更差），根因 = 锐利 σ 放大 + 价值-策略失配（目标量本身不对），
加数据/改特征/提拟合度/加预算均已证伪或判定无效，不再投入。负结果写回 EXPECTIMAX B2-R
「高预算验证」小节；候选模型与 JSON 保留 out/（gitignore）作证据。
**下一会话任务：C1 执行层可靠性**（用户指定「不显著 → 转 C1」；**2026-11-23 已按「先问我」
约定询问用户，用户明确选 C1**；tap 确认/重试、提权检查、动作前预算下一帧、每步可复盘，
见 WORKPLAN C1）。**再下一候选（未启动，先问用户再启动）**：
渐退式专家迭代——学技巧不学答案（policy/advantage 而非状态价值）、摸索 70%+老师 30%
逐轮放手、学生过配对评测门后当下一轮老师（EXPECTIMAX B2-R「再下一候选方向」）。
**测试/基线**：本会话无代码改动（纯评测+文档）；pytest **1155/1（1156 收集 / 79 文件）**、
①③④⑤ 不变。JSON（out/ gitignore）：`b2r_eval_highbudget_select.json`。
文档：EXPECTIMAX B2-R（结论先行/根因诊断/高预算验证/结论与假设/复现命令）；WORKPLAN §0/
阶段 B/开场白；HANDOVER_NEXT §0/§2 期望值修正（1154→1155）/§4 T4/§8/开场白；INDEX；
HANDOVER 二·补三十五。
提交 `docs 814c422` + 哈希记录 `7c2798d` + 交接定稿 `366fd2f`（另见 HANDOVER 七）。

**上一轮交接记录（2026-11-23，B2-R / B2 学习叶子按 B3+ 规则重训 —— 可复现负结果）**：
纯离线任务（用户二选一选了 B）。开工基线 ①②③④⑤ 全绿（② 1154/1，HEAD=7b57343 核对一致）。
① 旧模型 FAIL 复现：选择段 seed 2000–2079 beam 97.3→learned 71.2（−26.1 CI[−31.4,−20.8]），
与 B3 重测**逐位一致** → B4–B10 对 small harness（无 P 道具/属性倍率/熱意卡）零影响，
解析式基线稳定（within 89.1 / beam 97.3/94.9/96.8）。② 训练/推理分布等价性探针
（`data/_probe_b2_leaf_equiv.py`，未跟踪不提交）：greedy 300 局 + beam 全知 200 局共 2000 叶子
快照 vs `end_turn_state` 逐字段等价；修掉潜在口径差——B5 温存→全力**回合边界**解除收益
在 sim 里 `_draw_hand` 之后结算、搜索叶子却含这块：`RecordingLessonSim` 记录回合结束前指針
（`_pre_end_turn_stance`）、`leaf_state_at_draw` 补上解除收益（small 场景 0 次边界，数据不受影响；
修长回合场景重采学歪的隐患）；+1 强制边界回归测试（`test_b2_leaf.py` 11→12 条）。
③ 重采 3 批 beam 全知自对弈（width4/100ms ×1500+×3000、width8/300ms ×800；seed
100000/600000/500000 与评测段错开；**顺序跑**避免 CPU 争用扭曲墙钟预算）→ **26,500 样本、
0 fallbacks**，teacher 最终分 97.4–97.7；标签 = 纯 on-policy 后续得分，**不加 PBRS 塑形**
（auto-gakumas −26,884 负结果同向，AUTO_GAKUMAS_NOTES §2.4/§5）。④ 重训 MLP 104→96→48、
700 epochs、seed 分组 9:1 → val r²=0.906 / MAE 7.0 / corr 0.952（ridge 0.896）、σ=11.1；
特征保持 104 维（save_cards_used 仍废弃；熱意特征未加——small 0 熱意事件；large 重训先更新特征）。
⑤ 配对评测（eval_b2，B1 修正 harness）：选择段 80 局 beam 97.3→learned 90.3（−7.0 ❌）/
ens 0.75 +0.1（中性）；**确认段 120 局 seed 3000–3119：unknown 94.9→87.7（−7.2 CI[−9.5,−5.0] ❌）/
known 96.8→85.3（−11.5 ❌）/ ens 0.75 −0.5/−0.6（中性）；within_learned −19.9 ❌**；
σ 敏感性：learned σ×2/×4 → −9.0/−12.1（更差）→ μ 排序本身有害，非 σ 校准。
**结论/处置**：B2 DoD 走「可复现负结果 + 结论」分支达成；口径对齐消掉大部分伤害（−26~−28→−7）
但未转正；**生产 leaf_model 保持默认关闭、beam 默认解析式叶子、T2 真机 A/B 候选去掉 learned leaf**；
`data/knowledge/b2_leaf_mlp_small.json` **按用户指定回退为旧版**（重训候选保留
`out/b2r_leaf_mlp_small.json`，gitignore；两版都 FAIL、生产关闭故行为无差）；下一步先诊断
μ 排序有害根因（信息条件漂移假设）再定重训变量。**诊断已完成（2026-11-23）**：
信息漂移假设被推翻（y_known≈y_unknown、learned μ 近无偏且排序更好、分歧时 71.6% 对）；
确证根因 = ① 锐利 σ≈11 把准确 μ 推进档位效用饱和/尾部（σ 换 60 恢复 −7→−2，analytic μ 对 σ 免疫）
② 剩余 −2 是价值-策略失配（teacher return ≠ 100ms beam 可执行价值；tiebreak ×100 不改决策）。
**推论：加数据/改特征/提拟合度救不了；建议关闭学习叶子路线**（要正增益需换目标：优势标签/
动作排序蒸馏，或每战在线自适应——需真机）。详见 EXPECTIMAX「B2 重训（B2-R）·根因诊断」。

**下一会话任务（用户 2026-11-23 指定）：高预算验证——「更强的 bot 能不能兑现学习叶子」**
（**已完成：FAIL，路线关闭，见上方最近交接记录**）
- 背景：根因诊断后用户问「为什么不提高 bot 能力让它打出来」；可验证：把搜索拉到 teacher 级
  （width8/300ms）再配对。若 learned 在高预算下显著转正 → 路线改「强搜索+学习叶子」；
  若仍平/负 → 关闭路线（当前最好配置 muL+σ60 也只是平手 95.2 vs 97.3）。
- 前置：§2 基线（期望 ② **1155/1**，1156 收集 / 79 文件）；HEAD=37c59dc。
  重训候选在 `out/b2r_leaf_mlp_small.json`（gitignore，若被清掉按 EXPECTIMAX B2-R 复现命令重建）。
- 命令（选择段 80 局，同预算配对；eval_b2 自动跑同预算解析式基线）：
  ```powershell
  .venv\Scripts\python.exe scripts\eval_b2.py --leaf-model out\b2r_leaf_mlp_small.json --games 80 --seed 2000 --info unknown --width 8 --beam-budget-ms 300 --within-budget-ms 300 --ensembles 0.75 --json out\b2r_eval_highbudget_select.json
  ```
  墙钟约 15–25 分钟（within 家族也跑，可忽略或改探针只跑 beam）。
- 判定：选择段显著正 → 确认段 `--games 120 --seed 3000 --info unknown known` 复核；
  仍要过「真机实时预算」关（每步 300ms×局长 vs T1 ≤20 分钟）才谈生产。不显著 → 关闭路线，
  负结果写回 EXPECTIMAX B2-R，转 C1。一次会话只做这 1 个任务。
- **再下一候选（用户设计意图，先问用户再启动）**：「学技巧不学答案；自己摸索 70% +
  老师教 30%」，并**像扶小孩走路：教师占比逐轮渐退到 0，学生过配对评测门后当下一轮老师，
  循环几轮**（专家迭代/迭代自蒸馏，AlphaZero 同族）；学策略/优势而非状态价值
  （绕开价值-策略失配）；放手以评测门为准不按轮数硬退；模拟器保真度是天花板、真机 T2 才算数。
  多会话研究任务，轮廓/风险见 EXPECTIMAX「B2 重训（B2-R）」末段。
不做：第二轮专家迭代/档位头（B2 已知负结果）、large 重采（预算外，需先更新特征）。
备选路线：auto-gakumas 每战在线 PPO 自适应（需真机/独立副本，先问用户）。
测试/基线：ruff 通过；全量 pytest **1155/1（1156 收集 / 79 文件）**；① 4/4+3/3、③ 86/86+24/24、
④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。JSON（out/ gitignore）：b2r_eval_old_select /
b2r_train_report / b2r_eval_select / b2r_eval_confirm。下一项候选：**C1 执行层可靠性**
（tap 确认/重试、提权检查、动作前预算下一帧、每步可复盘）或 T5 剩余（fresh buff 需真机截图 /
随机生成卡 RNG 需 T6 补采）→ 真机 T3→T1→T2。详见 [EXPECTIMAX「B2 重训（B2-R）」](EXPECTIMAX.md) /
[HANDOVER 二·补三十四](HANDOVER.md)。提交 `feat 99e88fc` + `docs ae945dc` + `revert 432135b`
（模型按用户指定回退旧版）+ `docs 73b12a4`（根因诊断）（哈希另见 HANDOVER 七）。

**上一轮交接记录（2026-11-23，B10 / T5 剩余机制①② ExamCardCreateId 生成卡 + 指定卡名/手牌张数映射）**：
纯离线代码任务。语义来源 = masterTrans `ProduceCardSearch.json` 描述表 + 主数据
`ProduceCard.effectGroupIds`/`originIdolCardId`/`originCharacterId` + BSD-3 参考引擎
gakumas-tools（`usedCardBaseId` base id 不限强化 / `countCards` 区域 / `addCardToHand`
手牌≥5 不生成 / `limit:N` 按道具计次；生成卡 id 交叉验证 111/131/421/23）。
新 `scripts/build_card_meta.py` → `data/knowledge/card_meta.json` +
`src/gkagent/data/card_meta.py`（idol_unique 判据与参考 pIdol 交叉 **340/342、0 误报**；
effect_groups 取卡面 effectGroupIds；日文别名 1753；1817/1829 卡名命中）。
`build_p_items.py` `parse_card_search`（play_filter 234 件 / zone_count 27 件）+
`annotate_create_effects`（create 11 段 / create_random 6 段）；`sim/p_items.py`
`CardFilter`/`ZoneCount`/`CreateCard` + `exam_start_after` + **次数按道具计**（limit:N
口径修正，多段道具不再提前用完）；`lesson.py`/`expectimax.py` 生成卡落牌双镜
（known_draw/discard_order 同步）+ `play_choice.spec_from_name`。
触发未知 **103→3 件 / 185→6 段**（hold 2 + hotfix 1）、条件未知 **6→0**；数据层
**1025→1042/1849 段**；gkbench 103/153 段（loadout 4 件/8 段原 trigger 未知道具现在真实触发）。
离线 A/B（同 B8/B9 harness）greedy 3840.7→**4638.2（+797.5，+20.76%，
CI[+399.0,+1250.1]，31胜/3负/26平）** / expectimax 3665.8→**4466.9（+801.1，
CI[+66.3,+1697.9]）**；off 与 B9 逐位相同，不可直接比 B9 auto（触发映射+次数口径修正）；
确定式生成卡不在 hif loadout → ① A/B 贡献 0（单测覆盖）。新增 `tests/test_p_items_b10.py`
38 条（含参考交叉验证，缺 data/dl 自动 skip）、旧测试按新口径更新；全量 pytest
**1154/1（1155 收集 / 79 文件）**；基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、
⑤ 366/384 不变。**保持 no-op 并如实记录**：`ExamBuffConsumptionAdd`（强化状态花费卡，
用户指定不猜）、随机生成卡（H.I.F应援棒 6 段 / gkbench 172 段权重，考试 RNG 流未知）、
hold 保留区张数条件（2 件）、微熱ノスタルジー♡ 无 origin 字段不算偶像固有。
下一项候选：**B2 按 B3 规则重训**（旧模型 FAIL）或 T5 剩余（fresh buff 需真机截图 /
随机生成卡 RNG 需 T6 补采）→ 真机 T3→T1→T2。详见 [HANDOVER 二·补三十三](HANDOVER.md) /
[RULES_REFERENCE §5.3](RULES_REFERENCE.md)。提交 `feat fdcfe44` + `docs 56e8f95`（哈希见 HANDOVER 七、最近提交记录）。

**上一轮交接记录（2026-11-22，B9 / T5④ P 道具持久倍率 / modifier 类效果）**：纯离线代码任务。
语义来源 = gakumas-tools（BSD-3）`Executor/resolvers.js::resolveScore` f/g、`resolveCost`、
`BuffManager.js`（`setScoreBuff(amount, turns)` 列表 + 回合末倒计时）与 `p_items.csv` DSL。
`scripts/build_p_items.py` 新增 `annotate_modifier_effects`（effect_type + 效果文本 →
`target`/`duration`；**20 类 target / 369 段 / 298 件道具**；percent1→千分比、`values.turn`=持续
回合、缺省永久）+ 描述里的「（训练内N次）/（培育中N次）/（レッスン内N回）」→ 记录级
`max_uses` **9→896 件**（不解析会让持续倍率每回合重复触发；也修正 B6–B8 期生效效果可无限
触发的口径 → B9 auto 与 B8 auto 不可直接比）。
`sim/p_items.py`：`PItemDelta` 新字段（`score_buffs/score_debuffs/modifiers/cost_reduction/
cost_increase/half_cost_turns/double_cost_turns/extra_turns/stances/perfect_condition_turns/
poor_condition_turns`）+ 定时列表纯函数 `add_timed/total_timed/tick_timed/timed_dict_*/normalize_turns`
+ 「消耗体力减少状态」条件（`half_cost_state`）+ 指針直给文本判定。
`sim/lesson.py`/`sim/expectimax.py`：持久分数倍率（出牌分与回合末好印象都按 f/g 顺序）、
好印象强化（共用卡渠道）/追加发动、热意/集中/好印象/干劲/全力值增益倍率（获得量 ×(1+N%)、
safe_ceil）、绝好调/不调、费用修正（两引擎同式）、回合追加（`turns_left−1` 后补、total_turns
同步）、温存/强气指針直给（升级 2 段階、触发解除收益、`stance_change` 递归 ≤3）；
`LessonSim`/`ExpectState` 新字段 + `canonical` + `state_from_sim`/`sim_from_state` 全镜像。
数据层已实现 **676→1025/1849 段**（no-op 1173→824、modifier 337 段）；gkbench hif 83 唯一 id
**59→103/153 段**。新增 `tests/test_p_items_b9.py` 49 条、旧 `test_p_items.py` 更新；全量 pytest
**1116/1（1117 收集 / 78 文件）**；基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、
⑤ 366/384 不变。离线 A/B（同 B8 harness）greedy 3840.7→**3951.0（+110.3，+2.87%，
CI[+39.6,+193.3]，20胜/2负/38平）** / expectimax 3666.5→**3822.8（+156.2，CI 含 0，墙钟噪声）**。
**保持 no-op 并如实记录**：`ExamBuffConsumptionAdd`（强化状态花费卡机制不在模型里）、
`ExamCardCreateId` 生成卡、指定卡名/手牌限定、增益倍率整数取整与 fresh buff 差一回合近似。
下一项候选：**T5 剩余**（生成卡 / fresh buff 差一回合需真机截图）或 **B2 按 B3 规则重训** →
真机 T3→T1→T2。详见 [HANDOVER 二·补三十二](HANDOVER.md) / [RULES_REFERENCE §5.3](RULES_REFERENCE.md)。
提交 `feat` b956123 + `docs` de40f15（哈希见 HANDOVER 七、最近提交记录）。

**上一轮交接记录（2026-11-22，B8 / T5④ P 道具条件/效果语义第一批）**：纯离线代码任务。
`scripts/build_p_items.py` 新增 `parse_exam_trigger_id` / `trigger_id_has_unparsed_condition`
（新语法 id 后缀 → 参数/条件：`remaining_turn-N`、`parameter_buff_up-N`、
`stamina_up_multiple-N`、`stamina_less_multiple-N`、`full_power_point_get_sum_up-N`、
`card_play_aggressive_up-N`、`exam_review_up_interval-N`、`lesson_*`；条件未知 **22→6 件**，
16 件从 id 恢复；指定卡名/手牌张数 → `trigger_known=False` **103 件/185 段**保守跳过）+
`annotate_effects`（依赖换算「X 的 N% 数值变为 Y」→ `depends_on`+`percent` 65 段、
「X 变为 0」→ `zero_stack` 3 段、最大体力百分比 → `percent_max` 9 段）。
`sim/p_items.py`：`PItemSpec` 新字段 + 依赖换算/零层/固定与百分比体力结算 + 5 类新触发
（`turn_start_after`/`turn_interval`/`status_gain_interval`/`stance_change`/`stamina_reduce`）；
`sim/lesson.py`/`sim/expectimax.py` 发对应事件并维护 `full_power_point_total` /
`consumed_stamina_total` / `status_gain_counts`，`state_from_sim`/`sim_from_state`/`canonical`
全镜像。数据层已实现 **445→676/1849 段**（no-op 1404→1173）；gkbench hif 83 唯一 id
**34→59/153 段**。新增 `tests/test_p_items_b8.py` 19 条、旧测试按新口径更新；全量 pytest
**1067/1（1068 收集 / 77 文件）**；基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、
⑤ 366/384 不变。离线 A/B（同 B7 harness）greedy 3840.7→**4065.9（+225.2，+5.86%，
CI[+86.7,+363.6]，17胜/1负/42平）** / expectimax 3726.4→**3921.8（+195.4，CI 含 0，墙钟噪声）**。
下一项候选：**T5 剩余**（持续倍率 `ExamLessonValueMultiple` / 生成卡 / modifier 类 / 指定卡名
映射）或 **fresh buff 差一回合**（需真机截图）→ **B2 按 B3 规则重训** → 真机 T3→T1→T2。
详见 [HANDOVER 二·补三十一](HANDOVER.md) / [RULES_REFERENCE §5.3](RULES_REFERENCE.md)。
提交 `feat` + `docs`（哈希见 HANDOVER 七、最近提交记录）。

**上一轮交接记录（2026-11-22，T9-C0 采集/更新断链排障判据吸收）**：纯文档任务，把作者 11-22
整合包里「游戏更新后采集/更新断链」踩过的坑整理成可执行判据——[TROUBLESHOOTING §四](TROUBLESHOOTING.md)
新增 **13 条清单**（触发→症状/证据→处理→参考）：`System/Check` 200 空体 + `x-error-code=2004`
= 客户端旧；DMM 更新还原 hook DLL（模式判定别用 SameFile）；协议变更关键词 + 停止自动更新；
master 清单结构/长度/SQLCipher 判据（64-hex version、pack 名/文件名/key/size/URL host、pack≥100）；
版本哈希不透明（不按文件时间判新旧/单份回退槽/别动 `Master_Get` 夹具）；`http1_bridge` 丢客户端
版本/平台/会话头与业务错误头；`Auth/Login` `req_body_len` 865 正常 / 833→1003 与 `x-p-s` 需 DMM
常驻；上游端口写死 7897 → 10061/`OFFLINE-FALLBACK`；停服务顺序（先还原系统代理再停进程，反序
= 全机断网事故）；CA 精确指纹+有效期/TLS 回退直连；代理残留/更新后自清理；诊断脱敏；更新互斥。
另加 §4.2 与本文 1.3–1.9 的对应表（哪些已踩过、哪些是我们待验证的）。[CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md)
新增「游戏客户端大版本更新后自检」**8 步**，并修正「离线培育/作者暂不做」的过期说法（包内已有
`produce_runtime.py`，无考试结算 → 仅 E0 候选）。**外部经验、本项目待验证**；只写结论，未拷
代码/未加依赖/未动数据；复跑基线全绿（pytest **1054/1（1055 收集 / 76 文件）**、① 4/4+3/3、
③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384）。下一项：**T5 剩余机制**（fresh buff
差一回合需真机截图；P 道具条件/效果语义）或 **T9-E0**（离线培育测试台，需独立副本+用户配合，
先问用户）→ 阶段 C1/D → 真机 T3→T1→T2。详见 [HANDOVER 二·补三十](HANDOVER.md)。提交 `docs`
（哈希见 [HANDOVER.md](HANDOVER.md) 七、最近提交记录）。

**更早交接记录（2026-11-22，T9-B7 P 道具 47 条补全）**：`scripts/build_p_items.py` 改为
「本地中文 masterTrans 1068（逐段对齐）+ gakumasu-diff `ProduceItem.yaml` 独有 47 条」合并
生成，重建 `data/knowledge/p_items.json` **1068→1115 件**（spec 1764→1849、已实现 421→445；
条件未知 46 段另计）；47 条新增卡名用仓库自译表 `data/i18n/translation_new.json`（47/47）、
**中文描述缺失**处 `text_zh=""` + `text_ja` 日文 + 显式标记 `i18n_text_source="ja"`；
新触发 id 没有中文触发句 → `condition_known=False`（22 件），`PItemSpec.condition_known`
让 `apply_passive` **保守跳过**（不猜条件）、`summarize`/`local_bench` 单列计数。
gkbench 505 题模板 83 唯一 id 从 72 已知/11 未知 → **83 已知/0 未知**；A/B（hif 30 题×2 seed，
同 harness）greedy **3840.7→3969.7（+128.9，+3.36%，CI[+9.5,+248.4]）**——与 B6 逐位相同
（新道具目前 0 分贡献：条件未知/效果未实现/育成期触发），expectimax 3732.0→3953.6
（+221.5，CI[−71.4,+514.4]，墙钟抖动）。基线复跑全绿（**1054/1（1055 收集 / 76 文件）**、
4/4+3/3、86/86+24/24、36/36+3/3+29/29+beam 28、⑤ 366/384）。下一项：**T5 剩余机制**
（fresh buff 差一回合，需真机逐回合截图；P 道具**条件/效果语义**——数据缺口已清）→ 阶段 C/D
（T9 剩 C0 低成本纯文档 / E0 需真机实验）。详见 [HANDOVER 二·补二十九](HANDOVER.md) 与
[RULES_REFERENCE §5.3](RULES_REFERENCE.md)。提交 `feat` + `docs` 两个提交（哈希见
[HANDOVER.md](HANDOVER.md) 七、最近提交记录）。

**更早（2026-11-22，B6 / T5③）**：P 道具数据接入完成——新增
`src/gkagent/data/p_items_db.py`（对局 loadout `produce_item_ids` → `PItemSpec`，未知/重复
id 显式上报，缺数据抛错）+ `sim/p_items.py` 新增 **`exam_start`** 触发时机（288 段素材；
`LessonSim` 构造时先于 turn_start 结算一次）与 **`ExamPlayableValueAdd → extra_plays`**
（51 段，N 在 `count` 列；旧解析会退化成 0 值 no-op）；`LessonSim`/`ExpectState` 镜像；
`local_bench` 从 gkbench 题模板 `loadout.produce_item_ids` 接入（`--p-items auto/off`，
505 题 / 83 唯一 id / 72 已知 / 11 未知）+ gkbench 提交适配器从 `ctx.loadout`（公开配置、
不含种子）接入；离线 A/B（hif 30 题×2 seed 配对）：greedy **+128.9（+3.36%，
CI[+9.5,+248.4]）** / expectimax +149.6（+3.98%），其余局逐位不变（33/174 段已实现）。
基线复跑全绿（**1051/1（1052 收集 / 76 文件）**、4/4+3/3、86/86+24/24、
36/36+3/3+29/29+beam 28、⑤ 366/384）。下一项：**fresh buff 差一回合**（需真机逐回合截图；
P 道具效果覆盖/真机培育侧列表随后）→ 阶段 C/D。详见 [HANDOVER 二·补二十七](HANDOVER.md) 与
[RULES_REFERENCE §5.3](RULES_REFERENCE.md)。提交 `f531d20`（代码 + 测试 + 文档）/
哈希记录 `639f0b0`。

**2026-11-23 追加（外部情报，不是任务）**：用户 B 站发现 **tactfullotto/auto-gakumas**
（GitHub 公开仓库，2026-11-22 新建，无许可证）——零 LLM 全本地 H.I.F 本戦自动培育：
Android 模拟器（MuMu）ADB + WinRT OCR + MaaFramework；**每战现场训练 2000 eps Maskable PPO
（纯 NumPy ~60s）+ 每步 64 次 SO-ISMCTS**；AST 执行 gakumas-data DSL（四区守恒/费用修正/
P 道具触发/**回忆 Stage 级限 1**）；数据同源 gakumas-tools `a82c3a3`（926 卡/28 饮料）。
实机 live7 2回戦 **+1,594,997**、smoke_v7 W9 第 1（T13 前 962,352 / simQ 1,554,892）；
B 站标题宣称 S4+（待核）；PBRS 塑形负结果 −26,884（纯分最佳）。**口径不可与我们/gkbench/hiro
直接比**；其算法只看 UI 理论上可交 ranked，关注后续。分析落
[AUTO_GAKUMAS_NOTES.md](AUTO_GAKUMAS_NOTES.md)（未运行未拷贝；**无许可证禁止拷代码/数据**，
吸收须用我们主数据重验）；COMPARE/PROVENANCE/INDEX 同步。提交 `docs`（哈希见 HANDOVER 七）。

**2026-11-22 追加（外部情报，不是任务）**：用户提供作者新的**四游戏整合启动器包**
（215 MB，11-22 构建）→ 已解包静态分析并归档（7z 在 `data/dl/`、解包在仓库外），新增
[LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)，提交 `ddf221f`。结论：**有帮助但
属参考级**——工程排障/更新兼容经验、Produce API 语义参考、P 道具 47 条 id 线索；**不能**
拿考试算分公式、**不能**替换我们的采集安装、**不能**把代码/数据直接入库。由此新增候选任务
**T9**（B7 / C0 / E0 三选一，见 §4）；用户要求「开新对话做」，默认建议先 **B7**（纯离线、
收益明确）。候选任务本身的交接记录提交 `508aa34`。

**新会话开场白（复制）**

```
工作目录 D:\Games\gakumas-agent。当前 HEAD 以 git log -1 为准。
读 docs/INDEX.md → docs/WORKPLAN.md（总计划）→ docs/HANDOVER_NEXT.md §2 跑基线
（四条必跑 + ⑤ F0 gkbench 核对可选）。
期望：洗牌 4/4 场 + 3/3 重洗；pytest 1306 passed / 1 skipped（1307 条收集 / 88 文件）；
exam_setup 4/4 场 86/86 张 + 重洗 24/24；wiring 36/36 手牌 + 3/3 重洗 + known_draw 29/29 + beam 28；
⑤（可选）scripts/verify_gkbench_shuffle.py = 366/384 精确 / 97.4% 逐张（缺 data/bench_local 数据则跳过）。
（进度/对手对比先看 docs/COMPARE.md；现状看 docs/HANDOVER.md。）
A1（OCR 换日文模型）已于 2026-11-22 完成（官方 PP-OCRv6 Apache-2.0，见 WORKPLAN A1 / HANDOVER 二·补十四）；
A2（F#42 课程硬打必须得分）也已完成（HUD 语义 + 每回合 1 张 + 硬打保分，见 WORKPLAN A2 / HANDOVER 二·补十五）；
A3（F#43 结果页空转）也已完成（真根因：日文饮料选择事件屏 + P 费标签被当飘字；见 WORKPLAN A3 / HANDOVER 二·补十六）；
A4（离线回放素材）也已完成（8 张真机帧归档 + 9 条真机帧回放测试 + scan_frames 挑帧工具，见 WORKPLAN A4 / HANDOVER 二·补十七）。
A5（T3 离线预演）也已完成（--current 3 候选第 2 回合锁定 config_turns=12、四场 sweep T1–T2 锁定且选对真值；
见 WORKPLAN A5 / HANDOVER 二·补十八）。
B1（T4 修正）已于 2026-11-22 完成：评测执行器 `_execute_plan` 白丢回合 bug；修正后 60 局配对
beam unknown 164.0 / known 165.5 vs within 143.1（+20.9/+22.4，CI 全正；决策门 PASS），
受控 frontier 叶子中性（见 WORKPLAN B1 / HANDOVER 二·补十九）。
B2（全知数据训练 MLP 叶子）已于 2026-11-22 完成：beam 全知自对弈 26.5k 叶子样本 → 104 维
MLP（val r²=0.943）；B1 修正 harness 确认段 120 局 beam 157.8 → 165.5（+7.7 CI[+4.2,+11.2]）/
ensemble 0.5 166.9（+9.0），CLEAR 95→98.3%、PERFECT 33.3→50%；within 用 learned 变差为已记录
负结果（只对 engine=beam 有益；生产 leaf_model 默认 None 未打开）。
B3（T5 机制建模）已于 2026-11-22 完成：模拟器对齐真机「每回合基础 1 张 + 打完自动结束回合 +
SKIP 回 2 体力 + 取整 safeCeil」，RULES_REFERENCE 重写为逐条核验表，真机 39 回合配对回归；
重标定后整局 A/B 里 expectimax 显著强于 rules（+342~+429 评价点），B1 60 局 within 89.1→beam
95.7（+6.6，决策门 PASS）；**B2 旧模型重测 FAIL，必须按 B3 规则重采数据重训**。
见 WORKPLAN B3 / HANDOVER 二·补二十一 / RULES_REFERENCE / SIMULATOR §11。
F 阶段数据 + F0 预检已于 2026-11-22 完成：用户登录 gkbench 并给了命令行令牌（存在
~/.config/gkbench/token，仓库外）；scripts/bench_download.py 批量下 hif 80 run/36,350 条路线、
329 题官方种子+check、505 题存档、fixed/template 榜单；见 HANDOVER 二·补二十二 / GKBENCH.md。
**F0 收尾也已于 2026-11-22 完成**：scripts/verify_gkbench_shuffle.py 用 384 组官方 check.hand
核洗牌模型——initial 按 base id（含强化变体）+ initial_add、npc 按 idol 卡（本戦 jsna 4 人制/
fktn 2 人制/其余 3 人制）+ round 兜底 → **366/384=95.3% 精确 / 97.4% 逐张**（選抜 100%；逐题
311/329 全中；剩余 18 组全是考试开始加牌机制、无一洗牌错误）；起点校准 turn=1/score=0/
stamina 96.1%=starting_stamina/rules=55（见 HANDOVER 二·补二十四 / GKBENCH §4.5）。
**B4（T5① 审查倍率分段+联动惩罚）也已于 2026-11-22 完成**：sim/exam_multiplier.py（分数表
分段折线 + 审查基准联动惩罚 + 单精度取整）+ data/exam_bonus.py（主数据解析）+ 模拟器按回合
属性乘 + 生产读屏倍率进搜索（日志 attr=2.07）；真机夹具期中 4.09/2.20/2.60×、期末
6.97/2.85/4.96×；tests/test_exam_multiplier.py 21 条，全量 pytest 1006/1（1007 收集 / 73 文件）。
见 WORKPLAN B4 / HANDOVER 二·补二十五 / RULES_REFERENCE §5.1。
**B5（T5② 熱意 + 温存解除）也已于 2026-11-22 完成**：sim/enthusiasm.py 纯规则 + LessonSim/
ExpectState 熱意独立整数资源（集中之后加算、获得时 ceil、回合末清零/熱意延長）；温存解除
1 段 +5 熱意 / 2 段 +8 熱意 +5 固定元気 + 解除当回合 +1 出牌次数（同回合可重复、温存→全力
回合边界也触发）；卡牌熱意追加/増加/延長/本牌適用倍数 ×2 接入 sim_produce（MODELED_EFFECTS
29→32）与生产卡表；tests/test_t5_enthusiasm.py 16 条，全量 pytest 1023/1（1024 收集 / 74 文件）。
见 WORKPLAN B5 / HANDOVER 二·补二十六 / RULES_REFERENCE §5.2。
**B6（T5③ P 道具数据接入）也已于 2026-11-22 完成**：新增 src/gkagent/data/p_items_db.py
（对局 loadout `produce_item_ids` → PItemSpec，未知 id 显式上报、缺数据抛错）+ sim/p_items.py
新增 exam_start 触发时机（288 段素材，LessonSim 构造时先于 turn_start 结算）与
ExamPlayableValueAdd → extra_plays（51 段，取 count 列）；local_bench 从 gkbench 题模板
loadout 接入（--p-items auto/off）+ gkbench 提交从 ctx.loadout（公开配置、不含种子）接入；
离线 A/B（hif 30 题×2 seed 配对）greedy +128.9（+3.36%，CI[+9.5,+248.4]）/ expectimax
+149.6（+3.98%）；新增 29 条测试，全量 pytest 1051/1（1052 收集 / 76 文件）。
见 WORKPLAN B6 / HANDOVER 二·补二十七 / RULES_REFERENCE §5.3。
**T9-B7（P 道具 47 条补全）已于 2026-11-22 完成**：build_p_items.py 合并本地中文 master
1068 + gakumasu-diff yaml 新增 47 → data/knowledge/p_items.json **1068→1115 件**
（spec 1764→1849、已实现 421→445；条件未知 46 段保守不触发）；gkbench 505 题模板
83 唯一 id **全已知 / 未知 0**；A/B hif 30 题×2 seed greedy 3840.7→3969.7
（+128.9，CI[+9.5,+248.4]，与 B6 逐位相同——新道具目前 0 分贡献）/ expectimax
3732.0→3953.6（+221.5，CI[−71.4,+514.4]）；新增 3 条测试，全量 pytest 1054/1
（1055 收集 / 76 文件）。见 WORKPLAN B7 / HANDOVER 二·补二十九 / RULES_REFERENCE §5.3。
**B8（T5④ P 道具条件/效果语义第一批）已于 2026-11-22 完成**：新语法 trigger id 结构化解析
（条件未知 22→**6 件**；指定卡名/手牌张数 → `trigger_known=False` 103 件/185 段保守跳过）+
依赖换算「X 的 N% 数值变为 Y」（65 段）+ 固定/最大体力百分比体力（9 段）+「X 变为 0」（3 段）+
`turn_start_after`/`turn_interval`/`status_gain_interval`/`stance_change`/`stamina_reduce`
五类新触发（LessonSim/ExpectState 事件与累计量双镜）；数据层 **445→676/1849 段**、
gkbench 已实现 **34→59/153 段**；离线 A/B greedy 3840.7→**4065.9（+225.2，+5.86%，
CI[+86.7,+363.6]）**；全量 pytest **1067/1（1068 收集 / 77 文件）**。
见 WORKPLAN B8 / HANDOVER 二·补三十一 / RULES_REFERENCE §5.3。
**B9（T5④ P 道具持久倍率 / modifier 类效果，第二批）已于 2026-11-22 完成**：参考引擎
`resolveScore` f/g、`resolveCost`、`BuffManager` 列表语义——20 类 target / **369 段 / 298 件**
（打分上升量增加/减少、好印象强化/追加发动、热意/集中/好印象/干劲/全力值增益倍率、
绝好调/不调、费用修正、回合追加、温存/强气指針直给）+ 描述解析次数上限 **9→896 件**
（修正 B6–B8 期生效效果可无限触发）；数据层 **676→1025/1849 段**（no-op 1173→824）、
gkbench **59→103/153 段**；`LessonSim`/`ExpectState` 新字段 + canonical + 双镜；
新增 49 条测试，全量 pytest **1116/1（1117 收集 / 78 文件）**；A/B greedy 3840.7→
**3951.0（+110.3，+2.87%，CI[+39.6,+193.3]）** / expectimax +156.2（CI 含 0）。
见 WORKPLAN B9 / HANDOVER 二·补三十二 / RULES_REFERENCE §5.3。**保持 no-op**：
`ExamBuffConsumptionAdd`（强化状态花费卡机制不在模型里）、`ExamCardCreateId` 生成卡。
**B10（T5 剩余①② 生成卡 + 指定卡名/手牌张数映射）已于 2026-11-23 完成**：card_meta
（idol_unique 参考交叉 340/342 零误报 + effectGroupIds）+ parse_card_search（play_filter
234 件 / zone_count 27 件）+ 生成卡确定式 11 段（手牌≥5 不生成/牌堆顶/弃牌堆）+
exam_start_after + 次数按道具计（limit:N 修正）；触发未知 103→3 件、条件未知 6→0；
数据层 1025→1042/1849 段；greedy A/B +797.5（+20.76%，CI[+399.0,+1250.1]）/ expectimax
+801.1（CI[+66.3,+1697.9]）；38 条测试，全量 pytest 1154/1（1155 收集 / 79 文件）。
见 WORKPLAN B10 / HANDOVER 二·补三十三 / RULES_REFERENCE §5.3。**保持 no-op**：
随机生成卡（H.I.F应援棒，RNG 未知）、ExamBuffConsumptionAdd、hold 保留区（2 件）。
**2026-11-22 追加（外部情报）**：用户提供了作者新的**四游戏整合启动器包**（215 MB，
11-22 构建）→ 已解包静态分析，文档 [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)
（提交 ddf221f）。帮助属参考级：可吸收其更新/代理/TLS 排障经验、核对 Produce API 语义、
拿到 P 道具 47 条 id 清单；但**不能**拿算分公式/替换采集安装/直接拷数据。由此新增候选
**T9**（B7 P 道具 47 条补全 / C0 可靠性经验吸收 / E0 离线培育测试台实验，见 §4）；
**B7 已完成**（P 道具补全），**C0 也已完成**（2026-11-22：更新/协议/代理/TLS 排障判据进
TROUBLESHOOTING §四 13 条 + CAPTURE_PIPELINE 更新后自检 8 步，纯文档不改代码，见 HANDOVER
二·补三十）；只剩 **E0**（需真机/独立副本实验，先问用户）。
**B2-R（B2 按 B3+ 规则重训）已于 2026-11-23 完成：仍 FAIL（确认段 120 局 unknown beam
94.9→learned 87.7，−7.2 CI[−9.5,−5.0]，ens 0.75 中性）；同日高预算验证（width8/300ms
选择段 80 局 seed 2000）也 FAIL：93.9→89.4（−4.4 CI[−8.8,−0.0]）/ ens 0.75 中性——收窄主因
是解析式基线自己变差（97.3→93.9），learned 绝对分几乎不动（90.3→89.4）→ 学习叶子路线
关闭**（生产 leaf_model 保持关闭、beam 默认解析式、T2 候选去掉 learned leaf；见 EXPECTIMAX
「B2 重训（B2-R）」/ HANDOVER 二·补三十四/三十五）。
**C1 执行层可靠性已于 2026-11-23 完成（用户指定；纯离线代码+单测，真机验收留阶段 E）**：
tap 确认/重试（TapGuard：动作前预算下一帧→互验 confirmed/moved 不重试/同屏 retap≤2/
lost 上报绝不静默 SKIP；PickerGuard 两段式选牌选中后只重试确认）、提权检查
（游戏 elevated/本进程 non-elevated → UIPI 静默丢点击，启动 blocked 拒跑+管理员提示）、
每步可复盘（data/step_trace.jsonl 含动作理由/预算/互验结果 + scripts/replay_steps.py 离线复盘）、
饮料对话未开重试（attempt_drink）；参考 GKMSMAA 架构自写不拷贝（AGPL）；
68 条失败场景单测，pytest 1223/1（1224 收集 / 83 文件）；见 WORKPLAN C1 / HANDOVER 二·补三十六。
**B11 渐退式专家迭代第 1 轮已于 2026-11-23 完成（用户选定启动）**：学 policy/advantage
（137 维学生网）+ 精确重放分支 on-policy 优势标签 + 70/30 混合；确认段 120 局 v1 97.5 vs
beam 教师 94.9：+2.6 CI[+1.1,+4.1] 评测门 PASS（放手）；消融：纯 BC v0 也过门（+2.4）→
红利主力=逐决策蒸馏+禁跳；28 条单测；见 EXPECTIMAX B11 / HANDOVER 二·补三十七。
**B11 第 2 轮也已完成（用户选定）**：教师←v1（--teacher-net）、占比 0.15、large 首测；
确认段 v2 97.9 vs v1 97.5：+0.4 CI[−0.4,+1.2] → CONTINUE（平台期，四段全中性）；
消融 v2−v2_bc=+0.54 CI[−0.40,+1.48] on-policy 仍未独立证明；large：v1 比 beam −28.1
CI[−36.0,−20.2]（CLEAR 36.7% vs 53.3%），v2 比 v1 还略差 → small 训练不泛化 large；
处置：占比不降、生产接线未做、T2 候选不变；15 条新单测。
**r3–r8 继续扶也已完成（用户指令「显著强于老师才结束」）**：数据×10/epochs×3/容量×2/
ε-greedy 探索（--explore-eps，+7 测试）全试过，确认段恒 +0.2~0.6（种子段结构）；
**门协议修正（用户批准）扩 500 局 → v6 98.6 vs v1 98.1：+0.6 CI[+0.2,+0.9] PASS**，
新鲜块 6000 +1.7 佐证，池化 820 局 +0.71 CI[+0.40,+1.02]；**v6=最佳学生**；
pytest 1273/1（1274 收集 / 86 文件）；见 EXPECTIMAX B11 r3–r8 续 / HANDOVER 二·补四十。
**B11 v6 生产接线也已完成（2026-11-23，用户授权综合推荐后选定；opt-in 默认逐位不变）**：
LessonPolicy engine=net（可观测状态 argmax 优势分，无搜索，public-safe；有牌绝不 SKIP；
缺模型/异常 → [engine][BLOCKED] 禁回退 rules）；auto_produce --net-model > produce.net_model >
默认入库 v6（data/knowledge/ei_policy_v6.json）；T2 增第四臂 --engine net；21 条单测，
pytest 1294/1（1295 收集 / 87 文件）；见 EXPECTIMAX「B11 v6 生产接线」/ HANDOVER 二·补四十一。
**B11 r9-large 也已完成（2026-11-23，用户授权安排）**：train_ei_policy --selfplay/--demos
多文件混合（单文件 sha256 逐位不变，12 条新单测）；large 自对弈 5000 局 126969 样本
（v6 学生，seed 900000+）+ small r5 全量 + 示范补量 = 320675 行，192×96/1200ep 同 r6；
**large500 r9 315.4 vs v6 285.8：+29.6 CI[+26.2,+33.0] PASS，vs beam +14.2——首个 large
超 beam 学生网**（新鲜块 +24.0 佐证）；**small500 −0.42 CI[−0.67,−0.17] 显著回退 →
复合门未过，不入库**（生产保持 r6；r9 留 out/ 作 large specialist，--net-model 可换）；
诊断假设=全局 std 稀释 small 信号（18.71 vs 12.21）；pytest 1306/1（1307 收集 / 88 文件）；
见 EXPECTIMAX B11 r9-large / HANDOVER 二·补四十二。
T5 剩余（随机生成卡 RNG / ExamBuffConsumptionAdd 保持 no-op / hold 保留区 / fresh buff
需真机截图）均低价值或需真机/补采。**下一会话任务（用户 2026-11-23 晚已选定，不用再问）：
B11 r10 按场景 std 归一化**（修 r9 small 回退、保 large 增益，进 F 前必须；做法/门/预测见 §8 安排）。
其他候选（先问用户）：继续降档（教师←v6、占比 15→0）/ 收 loop 转 T7 剩余（纯函数状态重放/自动复盘页）/
D1 补采集 / E0 实验（需独立副本）/ 直接阶段 E 真机（T2 已含 net 第四臂 + r9 large specialist）。
之后真机（T3→T1→T2，含 E0 实验）→ F1/F2 gkbench 公开对比（学生网 public-safe 候选须 small+large 双过）。
用户规则：SKIP 只在真没体力；禁止静默回退 rules（搜索失败=[engine][BLOCKED] 中止+修 root cause）；
真机整局 --ignore-user。一次会话只做 1 个任务。data/_probe*、bench_local/REPORT.md、
card_library.json 不提交。纯离线（真机验收留到阶段 E）。
```

---

## 9. 对手情报速查（写作这份文档时的状态，2026-11-22）

> 完整的一页对照（含我们的最新 B1/B2/B3 数字、口径陷阱、唯一两条可比路径）见
> **[COMPARE.md](COMPARE.md)**；本表只做速查。

| 项目 | 他们强在哪 | 他们弱在哪（我们的机会） |
|---|---|---|
| **hiro-gakumas-hero**（matto49，AGPL，[HIRO_VIDEO_NOTES](HIRO_VIDEO_NOTES.md)） | Mac+PlayCover 40+ 局稳定；初 REGULAR A/10428；H.I.F. 本战最高 130 万；三层架构 + 规则/LLM 权衡；互验 + 自动复盘页；~120 模块/600+ 测试 | **Windows DMM 不成熟**（只到第 2/3 名）；没有 seed/牌序途径；LLM 有 token 成本 |
| **QQ 群「初星学园情报处理部」**（[QQ_GROUP_NOTES](QQ_GROUP_NOTES.md)） | seed 反推（2^31 枚举+观测剪枝）信息论口径清晰（3 回合收敛 ~1000 候选）；nodejs 实现 | 自己定规矩**实战不用 seed**；uihorizon/uinet "到头了"（10× 训练量反而倒退）；无公开成绩 |
| **官方 AI**（GKMS 私有，[OFFICIAL_AI_NOTES](OFFICIAL_AI_NOTES.md)） | 真实牌序 + 50+ 特征评估 + 计划重放 + 限深/命令预算；考试机制覆盖最全 | 私有、不可移植、需 GKMS 原生核心；我们拿不到权重 |
| **MaaGakumasu**（[MAA_INTEGRATION](MAA_INTEGRATION.md)） | 手和眼：截屏/识别/点击/日常/汉化完整 | 出牌只到启发式；我们只做决策层（ADR-001） |
| **我们** | **唯一**把 MITM 采集→seed→整段牌序（含弃牌重洗）做成生产接口并经实机逐张验证；纯 Python/Windows 原生；0 token；B3 把模拟器回合规则/取整对齐真机后，整局 A/B 里 expectimax 显著强于 rules（+342~+429 评价点）；B1 修正后 beam 显著强于 within；B4 把考试审查倍率（分段+联动惩罚）对齐客户端公式并改用屏幕真实倍率；B6 把 P 道具（loadout `produce_item_ids`）接进模拟器/评测/提交（exam_start + extra_plays，离线 A/B greedy +3.36%）；B7 把 P 道具 catalog 补到上游 1115 件、gkbench 未知 id 清零；**B8 做了 P 道具条件/效果语义第一批**（新语法 trigger id 解析、依赖换算「X 的 N% 数值变为 Y」、固定/百分比体力、5 类新触发；数据层 676/1849 段、gkbench 已实现 59/153 段；greedy A/B +225.2）；**B9 做了持久倍率/modifier 第二批**（打分上升量增加/减少、好印象强化/追加发动、热意/集中/好印象/干劲/全力值增益倍率、绝好调/不调、费用修正、回合追加、温存/强气指針直给；20 类 target/369 段/298 件；数据层 **1025/1849 段**、gkbench **103/153 段**；greedy A/B +110.3） | 自动化最后一公里（T1）、无 A/B（T2）、全知未实时接通（T3）；B2 学习叶子旧模型在 B3 规则下失效待重训；机制覆盖仍缺 P 道具**生成卡/强化状态花费卡**、指定卡名/手牌映射、附魔、fresh buff（T5 剩余） |

**定位一句话**：信息维度我们领先，执行与策略强度落后 hiro；先把"能无人值守跑完整局 + 真机 A/B"做出来，故事才完整。
