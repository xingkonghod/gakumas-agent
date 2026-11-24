# 总作战计划（2026-11-22 起，新会话照此执行）

> 用户定的顺序：**先把所有离线工作全部做完 → 再跑真机 → 最后去 gkbench 比算法**。
> **2026-11-23 晚用户确认多会话路线图（A 顺序）：阶段1 离线补未知 → 阶段2 重采+练学生+新旧对比 → 阶段3 真机 → 阶段4 gkbench → 阶段5 收尾；每会话 1–3 任务，旧学生/老师数据模型全保留——逐项队列见 [HANDOVER_NEXT.md §8.0](HANDOVER_NEXT.md)（旧路线图未完成项已全并入）。**
> 本文件是唯一的总清单；具体任务细节在 [HANDOVER_NEXT.md](HANDOVER_NEXT.md)、
> [GROUP_FILES_ANALYSIS.md](GROUP_FILES_ANALYSIS.md)、[EXPECTIMAX.md](EXPECTIMAX.md) 等文档里。
> 新会话开场：`读 docs/INDEX.md → docs/WORKPLAN.md → docs/HANDOVER_NEXT.md §2 跑基线 → 按 §8.0 路线图做`。

---

## 0. 已完成，不要重做（新会话先确认这些仍然成立）

| 能力 | 验证 |
|---|---|
| MITM 采集链路（本地副本+代理+traffic） | 采集服务 18443/18444，可随时重启 |
| 洗牌模型（xorshift32+Fisher-Yates+支援强化+重洗） | `verify_shuffle.py` 4/4 场、重洗 3/3 |
| 牌序全知数据链路 `ExamSetup/ExamDrawPlan/known_draw/discard_order/beam` | `verify_exam_wiring.py` 36/36、3/3、29/29 |
| 决策可观测性 + 引擎接线（`--engine`/`produce.engine`，禁静默回退 rules） | 日志 `[engine]` / `| eng=… fallback=…`；单测 |
| 用户规则：SKIP 只在真没体力；禁止规则回退 | 全量 pytest 全绿 |
| known_draw **事前检测**（额外 RNG 机制卡 → 不启用全知） | `exam_risk.py` + 单测；169/1829 机制卡、四场牌组 0 命中 |
| T4 平手项/beam 采样实验（+19.9 旧数字已作废；B1 修正后 beam 已超 within；B2 学习叶子再 +7.7） | `EXPECTIMAX.md`；rollout 叶子负结果也记录在案 |
| T1 真机流程 10+ 类卡点 + F#41（日文剧情二选一）修复 | `FAILURES.md` #27-41；`584f742` |
| A1 OCR 换日文/多语言模型（官方 PP-OCRv6，Apache-2.0） | `tests/test_ocr_jp_model.py` 真图 4 条 + `test_ocr_config.py` 17 条；全量 pytest 926/1；`docs/HANDOVER` 二·补十四 |
| A2 课程硬打必须得分（F#42：HUD 语义 + 每回合 1 张 + 硬打保分） | `tests/test_lesson_play_f42.py` 真图回放 3 条 + `test_lesson.py` HUD 换算 4 条 + `test_hardplay_prefers_scoring_card_on_flat_tie`；全量 pytest 934/1（935 收集 / 66 文件）；`docs/HANDOVER` 二·补十五 |
| A3 F#43 结果页空转（真根因：日文饮料选择事件屏 + P 费标签命中飘字正则） | `tests/test_produce_ui_f43.py` 7 条（真机帧回放 3 + 合成 4）；全量 pytest 941/1（942 收集 / 67 文件）；`docs/HANDOVER` 二·补十六 |
| A4 离线回放素材（六类关键屏真机帧归档 + 回放测试 + 挑帧工具） | `tests/fixtures/` 8 张真机帧 + `README.md` 溯源表；`tests/test_frames_replay_a4.py` 9 条；`scripts/scan_frames.py`；顺带修 `_checkbox_bands` 真机 TypeError（F#44）；全量 pytest **950/1（951 收集 / 68 文件）**；`docs/HANDOVER` 二·补十七 |
| A5 T3 离线预演（`--current` 候选 + `ExamPlanSelector` 逐回合锁定） | `scripts/verify_exam_plan_offline.py`：最新场 3 候选第 2 回合锁定 `config_turns=12`（真值 12），四场 sweep 全部 T1–T2 锁定且选对真值；候选收敛到 1、`locked_turn<=3`；`tests/test_exam_plan_offline.py` 8 条；全量 pytest **958/1（959 收集 / 69 文件）**；`docs/HANDOVER` 二·补十八 |
| B1 T4 修正（评测执行器 bug + 受控 frontier 叶子） | `tests/test_beam_frontier.py` 6 条；`scripts/eval_t4_b1.py` 60 局配对：beam unknown **164.0** / known **165.5** vs within **143.1**（+20.9 / +22.4，CI 全正；决策门 114.6%/115.7% PASS）；frontier 叶子中性；全量 pytest **964/1（965 收集 / 70 文件）**；`docs/EXPECTIMAX` T4 修正 |
| B2 全知数据训练 MLP 叶子 | `scripts/build_b2_dataset.py` + `train_b2_leaf.py` + `eval_b2.py`；beam 全知自对弈 26.5k 叶子样本 → MLP 104→96→48（val r²=0.943）；**确认段 120 局配对：beam 157.8 → 165.5（learned，+7.7 CI[+4.2,+11.2]）/ 166.9（ensemble 0.5，+9.0 CI[+5.8,+12.2]）**；CLEAR 95→98.3%、PERFECT 33.3→50%；within 用 learned 变差 −3.3（负结果记录）；`tests/test_b2_leaf.py` 11 条；全量 pytest **975/1（976 收集 / 71 文件）**；`docs/EXPECTIMAX` B2 学习叶子（**B3 后旧模型失效；B2-R 已重训，仍 FAIL，见下**） |
| B2-R B2 按 B3+ 规则重训（2026-11-23，**负结果；高预算验证后路线关闭**） | 同配方重采 26.5k beam 全知叶子样本（B10 后模拟器）→ MLP val r²=0.906/MAE 7.0；确认段 120 局 unknown beam 94.9→learned 87.7（**−7.2 CI[−9.5,−5.0]**）/ known −11.5 / ensemble 0.75 中性；σ×2/×4 更差（非校准问题）；旧模型 −26.1/−27.9 → 重训收窄到 −7 但未转正；**高预算验证（width8/300ms）选择段 80 局仍 FAIL：93.9→89.4（−4.4 CI[−8.8,−0.0]）/ ens 0.75 中性，收窄主因是解析式基线自己变差（97.3→93.9）→ 学习叶子路线关闭**；**生产 leaf_model 保持关闭、beam 默认解析式叶子、T2 候选去掉 learned leaf**；快照口径修正（温存解除回合边界）+1 测试；pytest **1155/1（1156 收集 / 79 文件）**；`docs/EXPECTIMAX`「B2 重训（B2-R）」/ HANDOVER 二·补三十四/三十五 |
| B3 T5 机制建模（回合规则 + 核验表） | 模拟器对齐真机：每回合基础 **1 张** + 打完自动结束回合 + SKIP 回 2 体力 + 取整 `safeCeil`（`sim/lesson`、`sim/expectimax`、`sim/uiobs` 等）；真机 39 回合配对回归（`tests/fixtures/t5_exam_turn_rules.json` + `scripts/export_t5_turn_rules.py`）；`RULES_REFERENCE.md` 重写逐条核验表；实机回放黄金值 12 条；重标定：`sim_engine_ab` expectimax 显著强于 rules（+342~+429 评价点）、B1 60 局 within 89.1→beam 95.7（+6.6，门 107.4% PASS）、B2 旧模型 FAIL 待重训；全量 pytest **985/1（986 收集 / 72 文件）**；`docs/HANDOVER` 二·补二十一 |
| B4 T5① 审查倍率分段 + 联动惩罚 | `src/gkagent/sim/exam_multiplier.py`（分段折线 + 联动惩罚 + 客户端 f32/ceil 取整）+ `src/gkagent/data/exam_bonus.py`（主数据 → 配置）+ `LessonConfig.attribute_bonuses/turn_attributes`（模拟器按回合属性乘，含依赖分与回合末好印象）+ `policy.audition_coefficient`（真机屏幕「舞蹈 207%」→ 搜索倍率，日志 `attr=2.07`）；夹具 `tests/fixtures/t5_exam_multipliers.json`（11-20 采集局期中 Vo/Da/Vi **4.09/2.20/2.60×**、期末 **6.97/2.85/4.96×**；Vi/Vo/Da 低于审查基准的联动惩罚已对上）；`tests/test_exam_multiplier.py` 21 条；全量 pytest **1006 passed / 1 skipped（1007 收集 / 73 文件）**；`docs/RULES_REFERENCE` §5.1 |
| B5 T5② 熱意 + 温存解除 | `src/gkagent/sim/enthusiasm.py`（熱意获得/回合末清零/延長/温存解除纯规则）+ `LessonSim`/`ExpectState` 熱意字段与算分（集中之后、好调/指針之前；整数获得时 ceil）；温存解除 1 段 +5 熱意/2 段 +8 熱意 +5 固定元気 + 解除当回合 **+1 出牌次数**（同回合可重复）；卡牌效果 `ExamEnthusiasticAdditive/Multiple`（熱意追加/増加 buff）、`ExamEnthusiasticTurnAdd`（延長）、`ExamMultipleEnthusiasticLesson`（本牌熱意適用倍数 ×2）接入 `sim_produce`（MODELED_EFFECTS 29→32）与生产卡表 `play_choice`；回合边界 温存→全力 也结算解除收益；`tests/test_t5_enthusiasm.py` 16 条 + sim_produce/play_choice/mechanism 更新；全量 pytest **1023 passed / 1 skipped（1024 收集 / 74 文件）**；`docs/RULES_REFERENCE` §5.2 |
| B6 T5③ P 道具数据接入 | 新增 `src/gkagent/data/p_items_db.py`（`produce_item_ids` → `PItemSpec`，未知/重复 id 显式上报，缺数据抛错）+ `sim/p_items.py` 新增 **`exam_start`** 触发时机（288 段素材）与 **`ExamPlayableValueAdd` → `extra_plays`**（51 段，取 `count` 列）；`LessonSim` 构造时结算考试开始效果（先于 turn_start、额外出牌保第 1 回合）、`ExpectState` 镜像；`scripts/local_bench.py` 从 `loadout.produce_item_ids` 接入 + `--p-items auto/off` + 报告 `p_items` 覆盖率；`submissions/expectimax/algo.py` 从 `ctx.loadout`（公开配置、不含种子）接入；gkbench 505 题模板 83 唯一 id（72 已知/11 未知）；离线 A/B hif 30 题×2 seed：greedy **+128.9（+3.36%，CI[+9.5,+248.4]）** / expectimax +149.6（+3.98%）；新增 29 条测试；全量 pytest **1051 passed / 1 skipped（1052 收集 / 76 文件）**；`docs/RULES_REFERENCE` §5.3 |
| 作者 2026-11-22 四游戏整合包分析（外部情报，只读参考） | [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)（包结构/11-22 新版本变化与修复/采集安装边界；7z 归档 `data/dl/`、解包在仓库外，1457 条 sha256 校验通过） | 不能替换采集安装、拿不到考试算分公式；可用的：更新/代理/TLS 排障经验、Produce API 语义参考、P 道具 47 条 id 清单（含 B6 的 11 个未知 gkbench id）；候选任务 **B7 ✅ / C0 ✅ / E0（T9，剩 E0 需独立副本）**，用户要求开新对话做；提交 `ddf221f` |
| T9-C0 采集/更新断链排障判据吸收（纯文档） | [TROUBLESHOOTING §四](TROUBLESHOOTING.md) 13 条清单（2004 / 协议 hash/master 结构 / http1_bridge 头丢失 / 票据 865-833 / 上游端口 / 停服务顺序 / CA 指纹 / 诊断脱敏 / 互斥）+ [CAPTURE_PIPELINE「游戏客户端更新后自检」](CAPTURE_PIPELINE.md) 8 步 | 外部经验，本项目待验证；纯文档不改代码，pytest 仍 1054/1；见 HANDOVER 二·补三十 |
| B8 T5④ P 道具条件/效果语义（第一批） | `scripts/build_p_items.py`（新语法 trigger id 解析 + 依赖换算标注）+ `sim/p_items.py`（`depends_on`/`percent`/`percent_max`/`zero_stack` + 5 类新触发）+ `sim/lesson.py`/`sim/expectimax.py`（事件/累计量双镜） | 数据层已实现 **445→676/1849 段**；条件未知 22→**6 件**；trigger 未知 103 件/185 段单列保守跳过；gkbench 已实现 34→**59/153 段**；greedy A/B **+225.2（CI [+86.7,+363.6]）**；pytest **1067/1（1068 收集 / 77 文件）**；见 HANDOVER 二·补三十一 / RULES_REFERENCE §5.3 |
| B9 T5④ P 道具持久倍率/modifier（第二批） | `scripts/build_p_items.py`（`annotate_modifier_effects`：20 类 target / 369 段 + 文本次数上限 9→896 件）+ `sim/p_items.py`（`PItemDelta` 新字段 + `add_timed/tick_timed/timed_dict_*` 纯规则）+ `sim/lesson.py`/`sim/expectimax.py`（分数倍率 f/g、费用修正、回合追加、指針直给、增益倍率、倒计时、canonical/双镜） | 数据层已实现 **676→1025/1849 段**（no-op 1173→824，modifier **337 段**）；gkbench 已实现 **59→103/153 段**；greedy A/B **+110.3（+2.87%，CI [+39.6,+193.3]，20胜/2负/38平）** / expectimax +48.2（CI 含 0）；新增 `tests/test_p_items_b9.py` 49 条；pytest **1116/1（1117 收集 / 78 文件）**；见 HANDOVER 二·补三十二 / RULES_REFERENCE §5.3 |
| B10 T5 剩余①② 生成卡 + 指定卡名/手牌张数映射 | 新 `scripts/build_card_meta.py` + `data/knowledge/card_meta.json` + `src/gkagent/data/card_meta.py`（idol_unique 参考交叉 340/342 零误报 + effectGroupIds + 日文别名）+ `build_p_items.py`（`parse_card_search` play_filter/zone_count + `annotate_create_effects`）+ `sim/p_items.py`（CardFilter/ZoneCount/CreateCard + exam_start_after + 次数按道具计）+ `sim/lesson.py`/`sim/expectimax.py`（生成卡落牌双镜）+ `play_choice.spec_from_name` | 触发未知 **103→3 件**、条件未知 **6→0**；play_filter 234 件 / zone_count 27 件；生成卡 **11 段确定 + 6 段随机 no-op**；数据层 **1025→1042/1849 段**；greedy A/B **+797.5（+20.76%，CI [+399.0,+1250.1]）** / expectimax +801.1（CI [+66.3,+1697.9]）；新增 `tests/test_p_items_b10.py` 38 条；pytest **1154/1（1155 收集 / 79 文件）**；见 HANDOVER 二·补三十三 / RULES_REFERENCE §5.3 |
| C1 执行层可靠性（tap 确认/重试 + 提权检查 + 帧预算 + 每步可复盘，2026-11-23，**纯离线代码+单测；真机验收留阶段 E**） | 新 `runtime/tapguard.py`（TapExpectation 动作前预算下一帧 + TapGuard 互验：confirmed/moved 不重试/同屏 retap≤2/lost 上报绝不静默 SKIP + PickerGuard 两段式选牌分级重试）+ `device/privilege.py`（游戏 elevated/本进程 non-elevated → UIPI 静默丢点击，启动 blocked 拒跑+`elevation-blocked` failure）+ `runtime/trace.py`（StepTrace 每步 reason/预算/互验结果）+ `scripts/replay_steps.py` 离线复盘 CLI；`produce_ui.decide()` 每击自动预算（弹窗确认/回合结束「是」/通信错误=dialog-gone）+ card-reward 接 PickerGuard（只重试领取不重点卡位）；`auto_produce` 接 tap 互验（retap/lost/连续 3 次 lost 止损停局）+ `attempt_drink`（对话未开重试槽位≤2，失败留痕）+ 每步 `data/step_trace.jsonl` + 局末 `[tap]` 汇总；参考 GKMSMAA follow/winpriv 架构**自写不拷贝**（AGPL）；新增 4 测试文件 **68 条**；pytest **1223/1（1224 收集 / 83 文件）**；基线 ①③④⑤ 不变；见 HANDOVER 二·补三十六 |
| B11 渐退式专家迭代 第 1–2 轮（policy/advantage 学生 + 评测门渐退，2026-11-23，**纯离线；r1 确认段 PASS / r2 平台期 CONTINUE**） | 新 `sim/policy_mlp.py`（137 维特征=104 状态+33 动作 → 96→48→1 优势分；`net_action` 硬规矩禁跳/禁回退）+ `sim/policy_data.py`（决策记录+**精确重放分支** on-policy 优势标签 A=R−mean(R)，逐字段全等校验不走搜索镜像）+ `build_ei_dataset.py`/`train_ei_policy.py`/`eval_ei.py`；`eval_known_draw.play` 加 net/greedy（默认逐位不变）；r1：示范 400 局 5747 样本→v0 BC→自对弈 1000 局 14314 样本→v1 70/30；**确认段 120 局 v1 97.5 vs beam 教师 94.9：+2.6 CI[+1.1,+4.1] PASS**（稳健块 +3.8 CI[+1.6,+6.0]；0.40ms/决策）；消融：纯 BC v0 也过门（+2.4），红利主力=逐决策蒸馏+禁跳。**r2（教师←v1、占比 0.15、large 首测）**：`--teacher-net`/`--baseline-net`/`--round` 纯增量；v1 示范 5773 + v1 自对弈 14526（seed 400000+/300000+）→ v2 17089 样本；**确认段 v2 97.9 vs v1 97.5：+0.4 CI[−0.4,+1.2] CONTINUE（平台期，四段全中性，新鲜块 5000 同样中性）**；消融 v2−v2_bc=+0.54 CI[−0.40,+1.48] on-policy 仍未独立证明；**large：v1 比 beam −28.1 CI[−36.0,−20.2]（CLEAR 36.7% vs 53.3%），v2 比 v1 还略差（选择段 −14.8 显著）→ small 训练不泛化 large**；v2−beam small +2.99 CI[+1.37,+4.62] 绝对水位保持；处置：占比不降、生产接线未做、T2 候选不变；新增 15 条测试（r2）。**r3–r8 继续扶（用户指令「显著强于老师才结束」）**：数据×10/epochs×3/容量×2/ε-greedy 探索（`--explore-eps`，+7 测试）全试过，val 饱和 0.862、确认段恒 +0.2~0.6（种子段结构）；**门协议修正（用户批准）扩 500 局 → v6 98.6 vs v1 98.1：+0.6 CI[+0.2,+0.9] PASS**，新鲜块 6000 +1.7 佐证，池化 820 局 +0.71 CI[+0.40,+1.02]；**v6=最佳学生**；large 泛化显著改善（+14.4 vs v1）但仍低于 beam（−13.7）；生产接线仍未做；pytest **1273/1（1274 收集 / 86 文件）**；基线 ①③④⑤ 不变；见 EXPECTIMAX B11 / HANDOVER 二·补三十七/三十九/四十 |
| B11 v6 生产接线（2026-11-23，**纯增量代码+单测；opt-in，默认逐位不变**） | `LessonPolicy(engine="net", net_model=…)`：可观测状态 `legal_cards` 里 argmax 优势分（无搜索）；`with_plan=False` 不注入采集全知（public-safe 口径）；硬规矩有牌绝不 SKIP / 全付不起才 SKIP；缺模型/推理异常/失配 → `RuleFallbackBlocked`（**禁回退 rules**）；`eng=net` + 优势分进 reason；auto_produce `--net-model` > `produce.net_model` > 默认入库 v6，缺模型起跑前 return 2；`data/knowledge/ei_policy_v6.json`（tracked，gate 溯源 meta）；T2 增第四臂 `--engine net`（large 生产候选仍是 beam） | `tests/test_ei_wiring.py` 21 条；pytest **1294/1（1295 收集 / 87 文件）**；基线 ①③④⑤ 不变；见 EXPECTIMAX「B11 v6 生产接线」/ HANDOVER 二·补四十一 |
| B11 r9-large（2026-11-23，**small+large 混合训练；large 首超 beam，small 显著回退 → 复合门未过，不入库**） | `train_ei_policy --selfplay/--demos` 多文件（`nargs="+"`，按序拼接/group 偏移/全局 std/meta.multi_file；**单文件 sha256 逐位不变**）；large 自对弈 5000 局 126969 样本（v6 学生，seed 900000+）+ small r5 全量 145605 + 示范 48101（补采 v1 1600 局解锁 0.15 上限）= 320675 行，192×96/1200ep 同 r6 | **large500 r9 315.4 vs v6 285.8：+29.6 CI[+26.2,+33.0] PASS，vs beam +14.2（首个 large 超 beam 学生网）**，新鲜块 +24.0 佐证；**small500 r9 98.2 vs v6 98.6：−0.42 CI[−0.67,−0.17] 显著回退**（池化 580 −0.47；vs v1 原门未保持）→ 不入库，生产保持 r6；r9 留 out/ 作 large specialist（--net-model 可换）；诊断假设=全局 std 稀释 small 信号（18.71 vs 12.21）；`tests/test_ei_multifile.py` 12 条；pytest **1306/1（1307 收集 / 88 文件）**；见 EXPECTIMAX B11 r9-large / HANDOVER 二·补四十二 |
| B11 r10（2026-11-23，**按场景 std 归一化；small 回退收窄 39% 但仍显著、large 增益保持 → 复合门未过，不入库**） | `train_ei_policy --norm-by-scenario` 纯增量（默认关=逐位不变，4 参照 sha256 改前/改后一致；多文件各文件按自身 std，scenario 取 npz meta.args.scenario，mix/meta 记逐场景 std）；复用 r9 数据 320675 行重训（单变量=归一化口径，small std 12.2115 / large 24.0878 vs 全局 18.7065）；能量份额 small 20.9%→49.0% / large 70.9%→42.7% | **large500 r10 314.9 vs v6 285.8：+29.1 CI[+25.8,+32.3] PASS，vs beam +13.6 仍超**（r10−r9 中性，增益保持）；**small500 r10 98.38 vs v6 98.64：−0.256 CI[−0.500,−0.012] 仍显著回退**（收窄 39%；vs v1 原门恢复 +0.32 CI[+0.03,+0.61]）→ 不入库，生产保持 r6；r10 留 out/；`tests/test_ei_norm_scenario.py` 12 条；pytest **1318/1（1319 收集 / 89 文件）**；见 EXPECTIMAX B11 r10 / R9_ANALYSIS §8 / HANDOVER 二·补四十三 |
| P1-1 全力回合 + のんびり指針 + r10 行为探针（2026-11-24，**阶段1 首批规则；BSD-3 有据；评测牌组组成不变**） | `stance.py`（LEISURE ×0/×0 + `stance_change_allowed` 守卫 + `LEISURE_RESERVE_SOURCES` 4 族卡证据表）+ `enthusiasm.py`（解除 4 元组：温存→のんびり不触发；のんびり→全力 = 全体卡打分成长+10）+ `lesson.py`/`expectimax.py`（全力回合 +1 出牌/保留牌回手双镜 + `held`/`leisure_reserves`/`score_growth_all` + canonical/快照/叶子）+ `p_items.py`（stance_leisure 直给）+ `sim_produce`/`play_choice`（ExamOverPreservation 预约解析，MODELED_EFFECTS 32→33，旧误映射移除）+ p_items.json 重标注（modifier 369→371） | r10 探针（R9_ANALYSIS §9）：**残留 small 回退已非 v1 风格贪即时分**（首分歧贪即时分偏置 24:9→11:8，对 v1 耐心比恢复 v6 水平），残留 −0.256 是无方向漂移噪声 → r11 small 上采样仍是对症变量；规则：全力回合 +1（连续全力每回合）/held 回手钩子（来源留 P1-3）/全力禁切指針/のんびり解除收益/预约来源；`tests/test_p1_stance_rules.py` **36 条**；pytest **1354/1（1355 收集 / 90 文件）**；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；见 RULES_REFERENCE §5.4 / HANDOVER 二·补四十四 |
| P1-2 handDecrease 抽牌修正 + pride 自尊（2026-11-24，**阶段1 第二批规则；BSD-3 有据；评测牌组/loadout 组成不变**） | `lesson.py`/`expectimax.py`（`hand_decreases` timed 列表 + `pride_turns` 双镜 + canonical/快照/叶子；`_draw_hand`/`turn_draw_count`/beam 下一手 `max(hand_size−Σ,0)`；resolveScore f 加算 `min(min(好印象,干劲)×20,500)` 千分比、回合末 -1）+ `p_items.py`（hand_decrease/pride_turns target + delta）+ `CardSpec.pride_turns/pride_min_motivation`（sim_produce MODELED 33→34、35 元组；play_choice + trigger 门槛解析）+ p_items.json 重标注（modifier 371→385，implemented 1042→1056/1849） | ④ cardsToDraw=max(3−handDecrease,0)（TurnManager/BuffManager + wiki；塔 gimmick 12 段来源；nullifyDebuff 拦截未建模）；⑤ pride min(好印象,やる気)×0.02 上限+0.5（resolveScore f；来源卡「我、绝不」turn=5 门槛干劲>=9 + P 道具「一笔入魂」turn=2/3 status_gain&好印象>=6&limit1，主数据↔skill_cards.csv 632/633、p_items.csv 354/355 交叉，pIdol 117/118=雨夜燕）；`tests/test_p12_hand_decrease_pride.py` **36 条**；pytest **1389/1（1390 收集 / 91 文件）**；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；见 RULES_REFERENCE §5.5 / HANDOVER 二·补四十五 |
| P1-3 hold 保留区建模 + lockStanceTurns 指針固定（2026-11-24，**阶段1 第三批规则；BSD-3 有据；B10 遗留 trigger_unknown 清零**） | 新 `sim/hold.py`（HOLD_LIMIT=2 + 13 族卡证据表 HOLD_SOURCES + hold_pick 确定性选牌）+ `stance.py`（stance_change_allowed/end_turn locked 守卫）+ `lesson.py`/`expectimax.py`（_apply_hold(_state)/_enforce_hold_limit/lock_stance_turns+fresh 双镜 + canonical + 快照往返 + 叶子 LIFO + known_draw/discard_order 同步）+ `p_items.py`（PassiveState.held + zone_count held + preservation2 直给）+ `build_p_items.py`（hold→held 映射 + period810_hotfix 非限定标记白名单）+ `sim_produce`/`play_choice`（ExamCardMove 逐卡证据表 + StanceLock，MODELED 34→35、41 元组）+ p_items.json 重建（9 条记录变化） | ⑥ hold 保留区（上限 2/跨回合保留/holdThisCard 不进弃牌除外/holdSelected 选牌/moveHeldCardsToHand LIFO；冲刺/积累/切磋琢磨/潜在能力/互动的基础/觉悟/新的舞台/努力了，哦/那一天，在这里/对战请多指教！/让群星散落吧/爱意彩虹/一点一滴的进步 13 族，表外保留旧近似）+ lockStanceTurns（切磋琢磨 StanceLock turn=1，EOT+fresh 锁下一回合+setStance 守卫+全力进入门）+ hold 区张数条件（实现的觉悟 countCards[held]>=1 ↔ 叶える覚悟）+ hotfix（咲季营养餐・改 period810_hotfix 三源证实非限定）+ preservation2（7 段）；**trigger_unknown 3→0 件**、implemented 保持 1056/1849；**large 评测牌组组成变化**（冲刺/积累 draw 近似移除，保真度修正；small 不变）；`tests/test_p13_hold_zone.py` **46 条**；见 RULES_REFERENCE §5.6 / HANDOVER 二·补四十六 |
| P1-4 nullifyDebuff 低下状态无效拦截 + ⑦ ExamBuffConsumptionAdd / countDebuffs 评估（2026-11-24，**阶段1 第四批；BSD-3 有据；评测零落点**） | `p_items.py`（ANTI_DEBUFF_EFFECTS / nullify_debuff 目标 / effect_value 读 count / PItemDelta.nullify_debuff / intercept_debuff_entries 纯函数）+ `lesson.py`/`expectimax.py`（nullify_debuff 计数器 + score_debuffs/hand_decreases 逐条拦截 + canonical + 快照往返 + end_turn 携带）+ p_items.json 重建（11 条记录变化） | nullifyDebuff 消耗式计数器（无回合倒计时）拦截 setScoreDebuff/setHandDecrease（P 道具侧 ExamAntiDebuff count 11 段：偷懒的毛巾 + 塔 gimmick）；**⑦ ExamBuffConsumptionAdd 保持 no-op**（doubleBuffCostTurns 语义/主数据 4 段/gkbench 22 loadout 如实记；卡模型不承载 buff 花费，88 张参考 buff-cost 卡 card_table cost=0）；**countDebuffs 无落点**（参考+主数据零使用）；卡侧 4 SSR 族来源/标量 DEBUFF_FIELDS 拦截延迟；implemented **1056→1067/1849**；`tests/test_p14_nullify_debuff.py` **30 条**；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；见 RULES_REFERENCE §5.7 / HANDOVER 二·补四十七 |
| P1-5 P 道具剩余效果语义补全（bounded batch：层数减少 + 好调回合 + 好调依赖换算）（2026-11-24，**阶段1 第五批；BSD-3 + DSL 三重核实；评测零 P 道具结算**） | `p_items.py`（3 REDUCE frozenset / TARGET_BY_EFFECT / effect_value 读 ExamParameterBuff turn 列 / PItemDelta.full_power_point_reduce / _apply_modifier_target 负层数 / ExamStaminaDamage 并入 STAMINA_LOSS）+ `lesson.py`/`expectimax.py`（全力值减少 max(0,fp−N) 双镜）+ `build_p_items.py`（CONVERSION_SOURCES 好调:parameter_buff）+ p_items.json 重建（24 条记录变化） | 层数减少（干劲/集中/全力值 -= N 夹取 ≥0，DSL motivation-=1/concentration-=1/fullPowerCharge-=2；全力值独立字段不计累计）+ 体力减少（cost-=1 genki==0 穿透）+ 好调N回合（turn 列 → condition_turns，DSL goodConditionTurns+=N）+ 好调依赖换算（好调的N%数值变为打分/集中，DSL score+=goodConditionTurns*0.3）；**留后续**：好调增加量增加/元气增加无效/不安/塔 gimmick/全力・强气效果卡打分/日文好調の%分（证据充分需新机制，no-op 如实记）；implemented **1067→1164/1849**（+97）、依赖换算 65→76；`tests/test_p15_reduce_condition.py` **38 条**；pytest **1503/1（1504 收集 / 94 文件）**；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0，sim_produce 不引用 p_items）；见 RULES_REFERENCE §5.8 / HANDOVER 二·补四十九 |
| P1-6 T7②③ 离线可靠性工程（纯函数状态重放 + 自动复盘页 + 标注转回归闭环）（2026-11-24，**阶段1 第六批；不改考试规则、不作废 B11 数据**） | 新 `data/run_replay.py`（apply_event 纯函数 + RunState 深不可变 + replay/legacy_events/fingerprint/compare_replays 逐步比对 + consistency_check 三方对账）+ `run_record.py` 增量 events 观测日志（note_* 追加、旧文件续跑先重建）+ 新 `report/review_page.py`（自包含 HTML：逐回合/考试/结算/重放一致性/观测日志/C1 逐步轨迹/标注工具栏）+ `report/annotations.py`（标注 → 回归用例冻结）+ `scripts/replay_run.py`（--verify/--compare）/`scripts/review_page.py`/`scripts/annotations_to_regression.py`；auto_produce 局末自动生成复盘页（[review]，best-effort） | ⑨ 同观测序列→同状态（两遍重放指纹逐位相等）→逐步比对（首个分歧步+字段差异）；旧格式汇总确定式重建与 events 日志终态语义一致；ep-t1-g 真实卡屏 28 次重复观测被显式 surfaced；⑩ 每局逐回合页 + 行内标注（verdict/comment/expected）→ 导出 JSON → 转回归夹具（tests/fixtures/review_regressions.json，2 条 synthetic-demo 演示用例）；样例页 docs/review_sample.html（ep-rule1 真实记录 + 合成演示轨迹显著标注）；`tests/test_run_replay.py` **38 条** + `test_review_page.py` **20 条** + `test_review_regressions.py` **3 条**；pytest **1564/1（1565 收集 / 97 文件）**；sim/ 零引用 run_record/run_replay/report → 评测零影响、无需重标定；基线 ①③④⑤ 不变；见 LIVE_RUN §2.1 / HANDOVER 二·补五十 |
| P1-7 P 道具后续批次（好调增加量增加 / 元气增加无效 / 不安 / 通用延迟生效）（2026-11-24，**阶段1 第七批；BSD-3 + DSL 三重核实；评测零 P 道具结算**） | `p_items.py`（CONDITION_GAIN/NULLIFY_GENKI/UNEASE/FIXED_VITALITY_EFFECTS / TARGET_BY_EFFECT / effect_value 读 turn / PItemSpec.delay_turns / PItemDelta.nullify_genki_turns・unease_turns・fixed_vitality・delayed + freeze/thaw）+ `lesson.py`/`expectimax.py`（`genki_gate` 闸门 + condition_gain 双渠道 + 延迟队列登记/倒计时/到点结算 + canonical/快照）+ `build_p_items.py`（`_timer_delay` yaml timer 包装标注 34 段）+ p_items.json 重建（49 条记录变化） | 好调增加量增加 condition_gain（resolveGoodConditionTurns ×(1+Σbuffs)，夜闇の星 313/314）+ 元气增加无效 nullify_genki_turns / 不安 unease_turns（resolveGenki return / ×0.67，∈ EOT_DECREMENT+DEBUFF_FIELDS；いたずらパペット/初陣の証・美鈴/雨上がりの花）+ ExamBlockFix 分离 fixed_vitality（resolveFixedGenki 不受闸门）+ **通用延迟生效**（yaml exam_effect_timer-NNNN ↔ DSL delay:N-1/嵌套 at:turn，EffectManager.decrementDelay；修正おさぼりタオル/美铃/温存变更类等已实现道具时序）；**保持 no-op**：塔 gimmick（参考无字段）/塔 ∞ 段（value=0）/全力・强气效果卡打分（per-card g.score 成长）/日文好調の%分/ExamParameterBuffReduce；implemented **1164→1179/1849**（+15）、modifier 409→442、delay 标注 34 段；`tests/test_p17_genki_condition_delay.py` **48 条**；pytest **1612/1（1613 收集 / 98 文件）**；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0，sim_produce 不引用 p_items + genki_gate/condition_gain 无来源恒等）；见 RULES_REFERENCE §5.9 / HANDOVER 二·补五十一 |
| P1-8 P 道具剩段 bounded batch（日文好調の%分 / 天生的才能）（2026-11-24，**阶段1 第八批；BSD-3 + DSL 三重核实；只改数据层标注 sim/ 零改动；评测零 P 道具结算**） | `build_p_items.py`（`CONVERSION_SOURCES_JA={"好調":"parameter_buff"}` / `_CONVERSION_SOURCE_TEXT_JA`「Xの%分」/ `annotate_effects` 日文分支）+ p_items.json 重建（**仅 2 条记录**变化：天生的才能 -0/-1 源段 role=conversion_source、ExamLesson 目标 depends_on=parameter_buff+percent1=30/50）；**sim/ 零改动**（换算/zone_count 双镜 P1-5/B10 就绪） | 日文好調の%分（天生的才能 pitem_01-3-346-0/1）：DSL 天性の才能 493/494 `at:afterCardUsed { if:countCards[hand & baseId(23)]>=1 { score+=goodConditionTurns*0.3 } }`（+ genki+=1; ×0.5）；眠気 baseId(23)↔card_table/card_meta 睡意 p_card-00-acc-0_002（B10 zone_count 已解析）；复用 P1-5 依赖换算渠道 int(condition_turns×N/100)；**保持 no-op**：全力・强气效果卡打分（per-card g.score 成长 43 段，values 恒空需逐卡证据表+新机制）/塔 gimmick（29 段参考无字段）/ExamParameterBuffReduce（3 段 produce/buff_consume 触发未支持）；implemented **1179→1181/1849**（+2）、依赖换算 76→78（好调换算 11→13）；`tests/test_p18_ja_condition_conversion.py` **32 条**；pytest **1644/1（1645 收集 / 99 文件）**；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；见 RULES_REFERENCE §5.10 / HANDOVER 二·补五十二 |
| 私有存档/私有仓库（bundle+裸仓库+Gitee private） | `docs/ARCHIVE.md`，`scripts/archive_private.ps1 -Push` |
| 群情报归档（论文/2B run/GKMSMAA/手机实验版） | `GROUP_FILES_ANALYSIS.md`、`QQ_GROUP_NOTES.md` |

**明确先不做（低优先/不必要）**：手机 APK 的 gadget 协议逆向、Localify 反编译、公开任何工具细节、gkbench ranked 提交（规则禁 seed）。

---

## 阶段 A：离线收尾（P0，全部做完才碰真机）

### A1. OCR 换日文模型（最高优先，一次修好大量文本分支）✅ 2026-11-22 完成
- 根因证据/方案：见 [GROUP_FILES_ANALYSIS.md](GROUP_FILES_ANALYSIS.md) §1–2（我们默认中文字典无假名；
  魔改 MAA 的日文模型实测完整读出日文）。
- 做法：
  1. `OcrEngine` 支持 `config_path`/环境变量 `GKAGENT_OCR_CONFIG`；
  2. 先本地加载 `D:\GakumasAgentArchive\group_files\GKMSMAA\resource\base\model\ocr\*`（AGPL，仅本地验证）；
  3. 正式方案换 **PaddleOCR 日文模型（Apache-2.0）**，模型放 `data/models/`（`.gitignore` 里）或下载脚本；
  4. 加 `configs/ocr_jp.example.yaml`；**不得**把 AGPL 模型提交进仓库/Gitee。
- DoD：同一张 `step_025.png` 能读出 `ヨーグルトパフェ/つくねハンバーグ/ドリンクバー` 与完整对白；
  全量 pytest 绿；用日文文本重新跑一遍剧情/事件/课程的相关单测（可去掉布局兜底的强依赖，但兜底保留）。

**落地（2026-11-22）**
- `OcrEngine` 配置优先级：显式 `config_path=` > `GKAGENT_OCR_CONFIG` > 本地 `configs/ocr_jp.yaml`
  （下载脚本生成，gitignore；删掉即回内置中文模型）> 内置中文模型。配置/模型文件缺失**直接报错**，不静默回退。
  两阶段主引擎与单行 `_line_core` 引擎共用同一套模型配置；路径支持 `%VAR%`/`$VAR`、相对 YAML 目录解析。
- 正式模型 = 官方 **PP-OCRv6_small_det + PP-OCRv6_small_rec（Apache-2.0，多语言）**：
  `scripts/download_ocr_models.py` 下载（URL+sha256 锁定）、校验、导出 18,708 行字典到
  `data/models/ocr_jp/`（gitignore）、生成 `configs/ocr_jp.yaml`；模板 `configs/ocr_jp.example.yaml`；
  `scripts/ocr_probe.py` 单图验字。AGPL 的 MAA 模型只本地对照（输出逐行相同），未入库。
- 实测 `data/auto/step_025.png`（720x1280，全屏 ≈1.0s）：读出 `ヨーグルトパフェ / つくねハンバーグ /
  ドリンクバー / そこまで真剣だと慰労を超えますが…… / 倉本さんのお気に入りは……`，中文 UI
  （`外出/审查基准/快进`）同时可读；`ProduceDriver` 同帧决策 `event-choice/last-row` 点 (360,935) 选项，
  不再点「快进」（F#41 类剧情/事件原地循环的直接影响）。
- 测试：`tests/test_ocr_config.py`（17 条，配置/路径/报错/单行引擎接线）+ `tests/test_ocr_jp_model.py`
  （4 条真图回归，模型缺失自动 skip）；修复基线过期断言
  `test_read_fast_event_page_uses_option_rows`（事件快速路径补读对话区后应允许区域 OCR）；
  真机日志新增 `[ocr] 模型 = …` 一眼确认是否日文模型。
- 中文 UI/性能回归（`scripts/bench_ocr.py --after --verify --threads 8`）：关键词 **5/5**；
  行动页单步 ≈189ms、课程页读屏 ≈402ms、全屏 read ≈752ms（目标 ≤1500ms）。
- 全量 pytest：**926 passed, 1 skipped**（927 条收集 / 65 个测试文件；见 HANDOVER_NEXT §2）。

### A2. F#42 课程策略：硬打必须保证得分（用户现场发现）✅ 2026-11-22 完成
- 现象：舞蹈课程连续打 buff（表情的基础 2.0）→ `lesson_score=90` → FAILED。
- 修法：禁跳规则下"强制出牌"必须优先 `score>0` 且付得起的牌；buff 与打分按剩余回合/缺口平衡；
  连续 N 张 0 分牌降级为"直接补 CLEAR 的牌"；用真机课程截图做离线回放单测。
- DoD：用 ep-t3-4 课程截图回放不再选 buff；单测覆盖"buff 多/分数少"场景。

**落地（2026-11-22）**
- **真根因比初判更深**（两层，都是"模型以为"和"屏幕实际"不一致）：
  1. **课程 HUD 语义读错**：右上角是**培育属性值**（不是课程分）；正中圆环
     「CLEAR截止 / PERFECT截止 N」是**还差 N 分**（过了 CLEAR 换成 PERFECT）。旧读法把
     属性值当课程分、把还差分当过关线：真机帧「属性 90 / CLEAR截止 30」被当成
     "分数 90 ≥ 过关线 30 → 已经 PERFECT" → expectimax 档位效用封顶（全部动作 2.00
     平手）→ 每回合建议 SKIP → 禁跳规则按动作价值硬打 → 稳定挑 buff 牌。
  2. **每回合出牌上限写死 3**：游戏**默认每回合只能出 1 张牌**（一手 3 张是"选 1 张"；
     额外出牌次数来自卡效果/P 道具）。证据：四场采集考试共 39 个实战回合，32 回合正好
     1 张、7 回合 2 张（2 张的都是卡效果 `ExamPlayableValueAdd`）；课程实拍同样"打 1 张
     回合数 -1"；社区/维基口径一致。旧搜索写死 `play_limit=3`（"手牌 3 张"的误读），
     于是"buff + 两刀"在模型里永远划算 → 每回合先铺 buff，整节课 0 分。
- 修法：
  - `vision/lesson.py`：`LessonReader` 读圆环档位（`CLEAR截止` / `PERFECT截止`）+ 按
    "属性值 − 开课属性值"换算课程分；过关线 = 已得分 + 圆环还差分；满分线查档位表
    （普通/SP = 2× 过关线；追い込み 90→360、165→600）。`LessonState` 新增
    `perfect/goal/attr`，`score` 语义改为"本课已得分"；`reset_lesson()` 每课重置属性基线。
  - `policy/lesson.py`：`_search_state` 改 `play_limit=1`（额外出牌走 `extra_plays`），
    满分线用读屏换算值；**硬打保证得分**——搜索建议 SKIP 时，先筛"屏幕分数预览 > 0"的
    牌（buff 牌记 0）按（搜索价值, 屏幕分）排序硬打（搜索在"反正到不了 CLEAR"的回合会
    把动作打成平手，旧排序会挑中 buff）。
  - `auto_produce.py`：每节课开始 `lesson_reader.reset_lesson()`；`lesson_score` 现在记
    **真课程分**（0 分也记，不再把属性值 90 写成 `lesson_score=90`）。
- 测试：`tests/test_lesson_play_f42.py` 3 条（真机帧 HUD 换算 + DoD 回放"最后一回合必须
  选魅力的基础 29、不选 buff" + "buff 多/分数少"合成场景）+
  `test_policy_engine.py::test_hardplay_prefers_scoring_card_on_flat_tie` +
  `test_lesson.py` 4 条假 OCR HUD 换算（属性基线/新开课重置/档位读不到沿用/满分线档位表）。
- **遗留（不属于 A2，已记 FAILURES #42 与 T5/B3）**：`sim/lesson.py` 的
  `plays_per_turn` 默认 3 也要对齐真机规则（默认 1 张 + 额外出牌），模拟器整局 A/B
  数字要重新标定；考试侧同样受影响（不是只课程）。

### A3. F#43 静态结果页空转 ✅ 2026-11-22 完成
- 现象：`result-tap/gain` 连点 10 次被自保护停局。
- 修法：静态页第 3 次起找「下一步/继续/完成/领取」按钮，找不到再点中央；补回归测试。
- DoD：真机/离线截图回放能推进到下一屏。

**落地（2026-11-22）**
- **真根因和最初判断不同**（看 `data/auto/step_020..029.png` 才查清）：那 10 帧不是结果页，是
  **日文饮料选择事件屏**（ヨーグルトパフェ -100P / つくねハンバーグ -50P / ドリンクバー 免费）：
  1. 旧中文 OCR 字典无假名 → 三条选项行一条都读不出 → `option_rows=0`，事件屏识别不出来；
  2. 飘字正则 `[+\-]\s*\d+` 把右侧 P 费标签「-100 / -50」当成 +N 飘字 → 走 `result-tap/gain`
     点屏幕中央 (360,1000)（对话区）→ 连续 10 步空转停机。
- **修法**（F#43）：
  - `_GAIN_RE` 只认正收益（`+45`/`＋45`），负数是 P 费/体力消耗，绝不当飘字；
  - 事件屏退化兜底：`option_rows=0` 但读得到 P 费标签时，用「最后一个费用标签中心 +138px」
    点免费项；`_EVENT_ROW_COST_RE` 放宽到 3 位（`-100`）；
  - 静态结果页：第 3 次飘字起每帧找「下一步/继续/确定/完成/关闭/领取/了解」，找不到才继续点中央；
  - A1 日文 OCR 后该屏本身已能读出选项 → 走 `event-choice/last-row` 点第 3 行免费项。
- **测试**：`tests/test_produce_ui_f43.py` 7 条（3 条真机帧回放：`tests/fixtures/event_ep_t3_4_drink_choice.png`
  → `event-choice/last-row` 点 (360,935)、同帧第二次 = 确认、同屏连续 10 步无 `result-tap`；
  4 条合成单测：P 费不是飘字 / 无选项文字时用费用标签 / 静态页第 3 下点「下一步」/ 没按钮保持计数）。
- **基线复核**：全量 pytest **941 passed / 1 skipped**（942 收集 / 67 个测试文件；A3 当时口径，
  A4 后为 950/1、951 收集 / 68 文件，见下方 A4）；①②③④ 其余数字不变
  （④ 仍 36/36、3/3、29/29、beam 28）。
- **DoD（离线）**：真机帧回放从 `result-tap/gain` 空转变成 `event-choice/last-row` → `confirm`
  两步推进；真机整局验收留到阶段 E（T1）。细节见 [FAILURES #43](FAILURES.md) / HANDOVER 二·补十六。

### A4. 离线回归素材（为"全部离线做完再跑真机"服务）✅ 2026-11-22 完成
- 把本次真机截图（`data/auto/step_*.png`、`fail_*`）挑关键屏归档成 `tests/fixtures/*.png`（或 `data/replays/`，
  `.gitignore` 已有 `data/replays/*`），做**截图回放测试**：OCR→decide→期望动作；
- 挑帧工具（A3 已随手落地）：`scripts/scan_event_frames.py` 扫截图找事件选项屏；
  `scripts/probe_frame_decide.py <step>` 把单帧走一遍生产链路（read_fast→decide）看判定/点击；
- DoD：至少覆盖：日文剧情二选一、课程 buff 场景、结果页、外出事件、考试浮层、回合结束确认框。

**落地（2026-11-22）**
- **归档**：`tests/fixtures/` 新增 6 张真机帧（另沿用 A2/A3 已归档的 2 张），新增
  `tests/fixtures/README.md` 记录每张的屏型/episode/step/时间/测什么/怎么再挑帧：
  日文剧情二选一（ep-t3-3 step49）、课程 buff（ep-t3-4 step1）、结果页（ep-t3-4 step4）、
  外出三选一（ep-full1 step49）、考试浮层（11-15 实拍）、真机确认弹窗（ep-t3-4 step19）、
  持有上限保留饮料（11-14 实拍）、外出饮料事件（A3 ep-t3-4 step21）。
- **回放测试**：`tests/test_frames_replay_a4.py` 9 条，全部是「真像素 → 真 OCR（A1 日文模型）→ 生产
  `read_fast`/`decide`」：剧情二选一（读得出两条假名选项、点气泡不点快进 F#41）、课程 buff 全链路
  （`decide` 交给 `LessonPolicy` → 打「魅力的基础」29 分，F#42）、结果页（`result-tap` → 第 3 次
  `next`，A3 修法）、外出三选一（`event-choice/last-row` → `confirm`，负 P 费不是飘字）、考试浮层
  （`exam_mode` + `card_detail_open` + audition 手牌 + 考试永不禁跳 F#17/F#32）、真机确认弹窗
  （点 OCR 读到的「确定」）、**回合结束确认框**（真机课程帧 OCR 行 + F#36 真实弹窗文案）、
  **持有上限保留饮料**（`_checkbox_bands` 勾选框扫描 + 点勾选框）。
- **工具**：新增 `scripts/scan_frames.py`——目录/glob/单帧批量走 `read_fast→decide`，输出
  `screen/action/点击坐标/OCR 文本`，支持 `--screen/--contains/--json/--limit`（A4 挑帧真源；
  `scan_event_frames.py` 仍是廉价小框预扫）；`probe_frame_decide.py` 的假 device 补 `click/swipe`。
- **回放抓到并修掉的真机 bug（F#44）**：`ProduceDriver._checkbox_bands` 漏 `@staticmethod`，
  真机「持有上限/还可选择 N 个」弹窗带 image 进分支会 `TypeError`（合成单测不传 image 所以此前没红）；
  修后 `data/drink3.png` 回放 → `drink-keep/check-row` 点勾选框列 (632,897)。已记 [FAILURES #44](FAILURES.md)。
- **缺口（如实记录）**：**回合结束确认框的真机帧已不存在**——`step_NNN.png` 轮转覆盖，含该弹窗的
  旧局（ep-cplus11 / ep-finish3/4/5 / ep-exp4）截图被后续 ep-t3 跑局盖掉。`scan_frames.py` 扫了
  1352 张归档截图（data/auto step+fail 487、data/manual/arun/bench/video/ssr 511、data 根目录 354）
  + data/bench 26 张，**0 帧**命中「结束回合/尚可使用技能卡」。该分支用「真机课程帧 OCR 行 +
  FAILURES #36 真实弹窗文案」回放；**下次真机跑局出现该弹窗时补拍**
  `tests/fixtures/turn_end_confirm_<episode>_stepNNN.png`（挑帧命令已写进 fixtures README）。
- **DoD 对照**：六类屏全部有回放；5 类用真机帧，回合结束确认框用「真机课程帧文字 + 同 UI 组件的
  真机确认弹窗帧」兜底（原因见上，等真机补拍补成纯真机帧）。
- **基线复核**：全量 pytest **950 passed / 1 skipped**（951 收集 / 68 个测试文件，含 A4 新增 9 条）；
  ① 洗牌 4/4 + 重洗 3/3、③ exam_setup 4/4 场 86/86 + 24/24、④ wiring 36/36 + 3/3 + known_draw 29/29 +
  beam 28 全部不变（A4 只加素材/测试 + 一个漏装饰器修复，不动数据链路）。

### A5. T3 离线预演（不碰真机）✅ 2026-11-22 完成
- 用新采集的 `traffic.jsonl` 跑 `build_exam_setup.py --current --allow-finished`，用 `ExamPlanSelector` 离线核对
  `locked_turn/verified`；把流程写成脚本（若需要）。
- DoD：候选收敛到 1、`locked_turn<=3`；结论写回 EXPECTIMAX/HANDOVER。

**落地（2026-11-22）**
- **脚本** `scripts/verify_exam_plan_offline.py`：一条命令跑两条路径——① `--current --allow-finished`
  候选（`--refresh` 时现场重建，等价 CLI）用最近一场考试 truth 驱动 selector；② 四场已结束考试
  各造 9/11/12 候选的 sweep。输出 `locked_turn` / 选中 `config_turns` / 锁定后逐回合核对 /
  `known_draw` 覆盖下一手；退出码 = DoD 是否通过，`--json` 给明细。
- **结果**（最新场 = 11-21 17:38 期末 seed=0x1E1A740D、牌堆 27 张）：
  - `--current` 3 候选（9/11/12）**第 2 回合锁定 `config_turns=12`（真值 12）**，锁定后手牌核对
    11/11（T2–T12），`known_draw` 覆盖下一手 9/9；T12 打出考试内生成卡 → 按数据限制提前停下
    （不算失败，与 `verify_exam_wiring` 同口径）。
  - 四场 sweep：考试0/1/2 第 1 回合锁定、考试3 第 2 回合锁定；选中 `config_turns` = 9/11/9/12，
    全部等于真值；候选 3→1；`locked_turn` 最大 2（DoD ≤3）。第 1 回合分不出的场是 isInitial 卡
    相同，第 2 回合收敛，与 QQ 群「2–3 回合锁定 seed」口径一致。
- **DoD 对照**：候选收敛到 1 ✅、`locked_turn<=3` ✅；结论写回
  [EXPECTIMAX §④](EXPECTIMAX.md) 与 [HANDOVER 二·补十八](HANDOVER.md)。
- **测试**：`tests/test_exam_plan_offline.py` 8 条（候选复制 / truth 驱动统计 / 真实与错误候选 /
  生成卡提前停止 / DoD 判定 / CLI 全链路）；ruff 通过；全量 pytest **958 passed / 1 skipped**
  （959 收集 / 69 文件）。
- 真机 T3 验收（考试进行中跑 `--current` + bot 运行时重载 + `[exam-plan] summary`）留到阶段 E。

---

## 阶段 B：策略强度与机制（离线，可与 A 并行）

### B1. T4 受控 policy-evaluation 叶子 ✅ 2026-11-22 完成
- 只对 beam 最深端点 rollout、用执行同策略（within）+ 缓存 + 小预算；决策门：真实牌组 beam ≥ within 的 90% 再谈生产。
- DoD：配对评测数字（60 局）+ `EXPECTIMAX.md` 更新 + 单测。

**落地（2026-11-22）**
- **先查出并修掉真正的瓶颈：评测执行器 bug**。`LessonSim.step` 在「手牌打空」时自动结束
  本回合；旧 `eval_known_draw._execute_plan` 在按 beam 计划打光 3 张后又补了一个 SKIP，
  把**下一整个回合**白丢 → 旧 beam 数字（111.2）被系统性低估；within 不走该执行器所以
  一直是真实的 143.1。修法：记 `start_turns_left`，同回合才补 SKIP（回归测试 2 条）。
- **受控 policy-evaluation 叶子**：`search_beam(frontier_value=...)` 只对预算截断后的最深
  端点用 `within` rollout（每回合 5ms、`canonical` 缓存）重排，终局端点用精确档位效用、
  不 rollout；默认 `None` 行为逐位不变（测试 4 条）。
- **60 局配对**（small，同牌组同 seed；`scripts/eval_t4_b1.py --games 60`）：
  within 143.1；beam **unknown 164.0**（+20.9，CI [+14.4,+27.3]）、
  **known 165.5**（+22.4，CI [+16.5,+28.4]）；决策门 **114.6% / 115.7% → PASS**（≥90%）。
  `beam+frontier` 与普通 beam 逐位相同（前沿收敛到同状态，叶子中性）。
- **消融**：起作用的是 `score_tiebreak=1e-3`（+15.4 / +11.8），branching=10 修正后无显著
  收益（旧 +19.9 是 bug 副产物）。生产默认（expectimax / tiebreak=0）本任务不改，T2 真机
  A/B 时再把 `beam + tiebreak` 作为候选。
- 测试 `tests/test_beam_frontier.py` 6 条；全量 pytest **964 passed / 1 skipped**
  （965 收集 / 70 文件）；`EXPECTIMAX.md` 新增「T4 修正」并给旧 beam 表加作废标注。
- 下一步：**B2**（rollout/全知数据训练叶子，必须用修正后的 harness 重测）。

### B2. T4 数据驱动：用全知数据训练叶子/小模型（新增方向）✅ 2026-11-22 完成
- 用采集的 exact（state, action, score, deck/seed）数据构造监督样本；teacher = 全知搜索/真值；
  student = V_leaf 或小 policy；离线配对评估；可行再接 `engine=`。
- 参考：群论文的 Bellman/在线搜索 + 2B 模型培育决策（只学思路）。
- DoD：离线配对显著优于解析式 leaf（或给出可复现负结果+结论），文档记录。

**落地（2026-11-22）**
- **数据**：`scripts/build_b2_dataset.py` + `RecordingLessonSim`（`src/gkagent/sim/leaf_data.py`）：
  beam **全知**自对弈，在 `_draw_hand` 入口记录**叶子状态**（与 `_Search.leaf` 的
  `end_turn_state` 同形态：手牌进弃牌堆、好印象 -1、buff 倒计时、回合 -1），标签 = 最终分 −
  叶子分。三批 teacher（width4/100ms 1500+3000 局、width8/300ms 800 局）→ **26,500 样本**。
- **模型**：`src/gkagent/sim/leaf_mlp.py`：104 维结构化特征（状态/分数缺口/体力、buff、指針、
  饮料/P 道具、**牌库 vs 弃牌堆拆分**、效果聚合、交互项）+ MLP 104→96→48（μ MSE + σ 残差头
  NLL），实现 `LeafValue` 协议；`scripts/train_b2_leaf.py` 按 seed 分组 9:1 切分；
  held-out r²=0.943 / MAE 8.8。模型 `data/knowledge/b2_leaf_mlp_small.json`（335KB，tracked）。
- **评测**：`scripts/eval_b2.py` 复用 B1 修正 harness（同牌组同 seed 配对 + 95% CI）：
  - 选择段 seed 2000–2079（80 局 unknown）：beam 解析式 166.8 → **learned 173.7（+6.8
    CI[+3.2,+10.4]）/ ensemble 0.25 174.4（+7.5 CI[+3.7,+11.4]）**；
  - **确认段 seed 3000–3119（120 局，未参与选择）unknown**：157.8 → **165.5（+7.7
    CI[+4.2,+11.2]）/ ensemble 0.5 166.9（+9.0 CI[+5.8,+12.2]）**；known：159.9 → **167.1
    （+7.2）/ ensemble 0.25 167.7（+7.8）**；CLEAR 95.0→98.3%、PERFECT 33.3→50.0%。
  - **DoD 达成**（beam 离线配对显著优于解析式叶子）；B1 基线逐位复现（within 143.1 /
    beam 164.0/165.5，seed 0–59）。
- **负结果**（写进 EXPECTIMAX）：within 用 learned 叶子显著变差（−3.3，教师策略收益偏乐观）；
  within 自对弈叶子 ≈ 中性（+0.9 n.s.）；档位概率头在 beam 上灾难性变差（P(CLEAR) 饱和）；
  第二轮专家迭代未超过第一轮。**结论：B2 叶子只对 `engine=beam` 有益**。
- **生产接线**：`LessonPolicy` 新增可选 `leaf_model`/`leaf_model_weight`（默认 None = 行为不变，
  `_leaf_value` 加缓存）；**不默认打开**，T2 真机 A/B 候选（仅 beam 引擎）。
- **测试/基线**：`tests/test_b2_leaf.py` 11 条；全量 pytest **975/1（976 收集 / 71 文件）**；
  ①③④ 基线全部不变。细节见 [EXPECTIMAX](EXPECTIMAX.md)「B2 学习叶子」与 HANDOVER 二·补二十。

### B3. T5 机制建模（真机回合规则对齐 + RULES_REFERENCE 核验表）✅ 2026-11-22 完成
- 逐条对照 `RULES_REFERENCE`：好调 `1.5+0.1g`、好印象年金 `W(r,T)`、审查倍率分段/联动惩罚、
  单精度舍入、支援强化尝试/成功/层数分布、牌组/轨迹计数；
- P 道具/回忆/附魔/选牌/减益：按官方 AI 对比表挑性价比补；
- 额外 RNG 机制（panic/search/generate/move）：现在只做**事前检测停机**；能否建模取决于新采集数据。
- DoD：差异表 + 补丁 + 配对回归（模拟器 vs 实机逐分）。

**落地（2026-11-22）**
- **真机回合规则核实**：每回合基础 **1 张**（gakumas-tools `TurnManager.startTurn`
  的 `cardUsesRemaining=1` + 真机 4 场考试 39 回合日志：32 回合 1 张、7 回合 2 张，
  每回合手牌都 3 张）；打完最后一张**自动结束回合**（`CardManager.useCard` 末尾）；
  回合末还有剩余次数（SKIP）**回 2 体力封顶**（`TurnManager.endTurn`）。
- **补丁（4 项）**：① `plays_per_turn`/`play_limit`/`DEFAULT_PLAY_LIMIT` 默认 3→1
  （`sim/lesson`、`sim/expectimax`、`sim/play_choice`、`sim/uiobs`、`sim/v_leaf`、
  `scripts/local_bench.py`）；② 出牌次数用尽/手牌空自动结束回合；③ SKIP 回 2 体力
  （`_end_turn` / `end_turn_state`）；④ 取整对齐 `safeCeil`（buff 段一次 + 回合倍率一次；
  旧课程 floor / 考试 round 一次）。实机回放黄金值：考试 250% 9→23、好调→35、愛嬌 13→50、
  情熱ターン 11 集中 0/3/6→28/35/43；课程好调 10→15、5→8、2→3；温存 9→5、2→1、15→8。
- **配对回归**：`scripts/export_t5_turn_rules.py` → `tests/fixtures/t5_exam_turn_rules.json`
  （真机 39 回合摘要 + 溯源）；`tests/test_t5_turn_rules.py` 9 条；`test_sim_lesson.py`
  实机黄金值 2 条（课程 6 值 + 考试 6 值）。
- **核验表**：`RULES_REFERENCE.md` 重写为逐条核验（回合规则 / `resolveScore` 顺序与取整 /
  buff 生命周期与好印象年金 / 牌序 4/4+3/3 ✅ / 审查倍率 ❌ 仍常量 4.11 / 熱意、温存解除
  额外次数、P 道具、fresh buff 差一回合等差距及证据）。
- **重标定**（旧数字全部不可混比）：`sim_engine_ab` 76 局 0 blocked/0 异常/C+ 100%，
  expectimax 从噪声内变**显著更强**（rules vs expectimax P50 5170→5566 / 5176→5505 /
  5152→5513，配对 Δmean +372/+342/+429）；B1 60 局 within 89.1 → beam 95.7（+6.6，
  CI [+2.2,+11.1]，决策门 107.4% PASS）；**B2 旧模型重测 FAIL**（确认段 beam 94.9→learned
  67.1，−27.9，ensemble 0.75 −5.3）→ 必须按 B3 规则重采数据重训；400 局培育标定带
  650–1100→950–1450。
- **测试/基线**：全量 pytest **985 passed / 1 skipped**（986 收集 / 72 文件）；
  ① 洗牌 4/4+3/3、③ 4/4 场 86/86+24/24、④ 36/36+3/3+29/29+beam 28 全部不变。
- **下一步（T5 剩余）**：~~审查倍率分段+联动惩罚~~ ✅ B4；~~熱意（独立资源）~~ ✅ B5；
  ~~温存解除 +1 出牌/元气~~ ✅ B5；~~P 道具数据接入（离线 loadout 侧）~~ ✅ B6；
  ~~P 道具条件/效果语义第一批~~ ✅ B8；~~P 道具持久倍率/modifier 类~~ ✅ B9；
  剩 fresh buff 差一回合（需真机截图核实）+ 生成卡/强化状态花费卡 + 真机培育侧列表；然后阶段 C/D。

### B4. T5① 审查倍率分段 + 联动惩罚 ✅ 2026-11-22 完成
- 目标：把「考试每回合属性倍率」从常量 4.11 换成客户端真实公式（分数表分段折线 + 审查基准
  **联动惩罚** + 单精度取整），并让生产搜索用屏幕读到的真实倍率。
- **公式**（原生客户端语义，参考 BSD-3 的 gakumas-tools `typeMultipliers.js` 与 AGPL 参考仓库
  `gakumas_produce/attributes.py` 的客户端还原实现，**按语义重写、不拷代码**）：
  ① 每项属性在自己的参数值上按 `ProduceExamBattleScoreConfig` 节点表**折线插值** →
  `component_permil`；② 低于本场 `ProduceExamBattleConfig` 三项审查基准时按 `GetPenaltyPermil`
  线性罚分（`Setting` 100~250‰）；③ **联动惩罚** `common=1000−Σpenalties`，三项共用；
  ④ `bonus = 1000 + component×common/1000` 归一化到 10；⑤ 出牌/回合末好印象
  `ceil(f32(f32(bonus/1000)×amount) − f32(1e-4))`。
- **落地**：`src/gkagent/sim/exam_multiplier.py`（纯公式）+ `src/gkagent/data/exam_bonus.py`
  （主数据：IdolCard → ProduceStepAuditionDifficulty → ProduceExamBattleConfig →
  ProduceExamBattleScoreConfig + Setting，缺数据显式抛错不猜）；
  `LessonConfig.attribute_bonuses` + `turn_attributes`（模拟器按 `ExamTurnEndLog.parameterType`
  乘；出牌分含好印象/元气/全力值依赖分、回合末好印象都吃）；`policy.audition_coefficient`
  （真机屏幕「舞蹈 207%」→ `ExpectState.attribute_coefficient`，日志 `eng=… attr=2.07 …`）。
- **真机配对夹具**：`scripts/export_exam_multipliers.py` → `tests/fixtures/t5_exam_multipliers.json`：
  11-20 采集局（`i_card-hmsz-3-018` / produce-002）期中 Vo373/Da218/Vi187 →
  **4.09 / 2.20 / 2.60×**（Vi 187<基准 192 → 罚 103‰、common 897 把三项一起压低＝联动惩罚）；
  期末 Vo842/Da350/Vi629 → **6.97 / 2.85 / 4.96×**（Vo/Da 两项不达标）。11-21 的
  `i_card-hkne-3-000` 不在主数据快照 → 夹具显式 `skipped`（生产只用屏幕倍率）。
- **测试/基线**：`tests/test_exam_multiplier.py` 21 条；全量 pytest **1006 passed / 1 skipped
  （1007 收集 / 73 文件）**；① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28 全部不变。
- **如实记录的剩余差距**：真机逐分回放仍差 P 道具考试开始附魔 / `ExamStatusEnchant` 附魔触发 /
  考试内生成卡 / `ExamReviewMultiple`「次数」语义；本轮只锁「倍率本身与客户端公式一致」。
- 细节见 [RULES_REFERENCE §5.1](RULES_REFERENCE.md) / HANDOVER 二·补二十五。

### B5. T5② 熱意（enthusiasm）+ 温存解除额外次数/元气 ✅ 2026-11-22 完成
- 目标：把「温存解除≈好调回合」的旧近似换成参考引擎的真实机制——熱意是独立整数分数资源
  （出牌分加算），温存解除给 5/8 熱意 + 1 次出牌 + 2 段固定元気 5，回合末清零（有熱意延長则延長）；
  并接入卡牌的熱意追加/増加/延長/本牌適用倍数效果。
- **机制**（参考引擎 gakumas-tools BSD-3 `constants.js`/`resolvers.js`/`TurnManager.js`
  + 官方 wiki 温存条）：熱意 1 点 = 本牌分数 +1（集中之后、好调/指針倍率之前）；
  获得量 `(熱意追加 + N) × (1 + 熱意増加‰)`，`WHOLE_FIELDS` 获得时 ceil；温存 1 段解除
  熱意+5 / 2 段 +8 + 固定元気+5，都会 **出牌次数+1**（同回合可重复解除叠加）；温存→温存2 升级不触发；
  回合末熱意归 0（有熱意延長则 -1 保留）；温存→全力的回合边界切换也触发解除收益。
- **落地**：`src/gkagent/sim/enthusiasm.py`（纯规则：`release_on_stance_change` / `enthusiasm_gain` /
  `turn_end_enthusiasm`）；`LessonSim.enthusiasm/enthusiasm_extension_turns` + `Buffs` 熱意 buff；
  `_card_award` 加熱意（含本牌 `enthusiasm_multiplier`）；`_apply_card_buffs` 登记熱意追加/増加/延長；
  `_end_turn` 好印象加熱意后清零/延長 + 回合边界解除；`ExpectState` 镜像（字段/canonical/
  `_card_award`/`_apply_card_effects`/`end_turn_state`/`state_from_sim`/`sim_from_state`）；
  `CardSpec` 新增 5 个熱意字段；`sim_produce._effect_fields` + `play_choice._effect_fields`
  把 `ExamEnthusiasticAdditive`（熱意追加）/`ExamEnthusiasticMultiple`（熱意増加）/
  `ExamEnthusiasticTurnAdd`（延長）/`ExamMultipleEnthusiasticLesson`（本牌熱意適用倍数 ×2）
  映射成字段，`MODELED_EFFECTS` 29→32。
- **测试**：`tests/test_t5_enthusiasm.py` 16 条（纯规则/温存1/2解除/+1出牌/固定元気不吃やる気/
  同回合重复解除/熱意算分/纯 buff 牌不加/回合末好印象加熱意/熱意追加/増加 buff/延長跨回合/
  回合边界解除/本牌適用倍数/ExpectState 镜像）；`test_sim_produce.py` / `test_play_choice.py` /
  `test_mechanism_corrections.py` 同步更新（旧「解除温存给好调回合」断言删除）。
- **未建模（如实记录）**：のんびり（leisure）指針及其解除规则、全力回合額外出牌/保留牌回手、
  P 道具/附魔来源的熱意、生产读屏未读熱意图标（每步从 0 估，同现有 buff 口径）。
- 细节见 [RULES_REFERENCE §5.2](RULES_REFERENCE.md) / HANDOVER 二·补二十六。

### B6. T5③ P 道具数据接入（gkbench loadout → 模拟器/评测/提交）✅ 2026-11-22 完成
- 目标：把「真实对局带哪些 P 道具」接进管线——接口/模板早就有（`sim/p_items.py`
  1068 件模板、6 个触发时机），缺的是 loadout → `PItemSpec` 的绑定与报告。
- **离线数据源**：真机 `traffic.jsonl` 没有 produce 编成字段（全文件扫 0 命中）→ 真机
  培育侧等 T6/D1 补采；离线完整数据源 = gkbench 505 题模板的
  `saves.jsonl[].loadout.produce_item_ids`（2686 个 id / 83 唯一；`ctx.loadout` 是
  base.py 明说的「开局配置（不含种子）」，公平可用）。
- 机制补丁：**新增 `exam_start` 触发时机**（288 段素材；训练/考试开始时，`LessonSim`
  构造时先于 turn_start 结算一次）和 **`ExamPlayableValueAdd → extra_plays`**
  （51 段，N 在 `count` 列，旧解析会退化成 0 值 no-op）。
- 落地：`data/p_items_db.py`（catalog + 解析 + 未知显式 + 缺文件抛错）、
  `sim/p_items.py`、`sim/lesson.py`、`sim/expectimax.py`、`sim/leaf_data.py`、
  `scripts/local_bench.py`（报告 `p_items` 覆盖率 + `--p-items auto/off`）、
  `submissions/expectimax/algo.py`（`ctx.loadout` 接入 + 缺数据 meta 记原因）。
- 覆盖率（如实）：catalog 1764 段 spec 已实现 421 段；gkbench 72 个已知道具 →
  131 段 spec，已实现 **31 段**；11 个未知 id（快照后新道具）不猜。
  F0 起点体力 15 组偏差里的 5 组（shro-3-016 −28）可用 `pitem_02-3-293-0`
  考试开始「最大体力 80% 变体力消耗」解释（`floor(36×0.8)=28`）。
- 离线 A/B（local_bench hif 30 题 × 2 seed 配对）：greedy 3840.7 → **3969.7**
  （+128.9，+3.36%，CI95 [+9.5,+248.4]，8/60 局变化、8 胜 0 负）；expectimax
  3759.3 → **3908.9**（+149.6，+3.98%，CI95 [−171.0,+470.2]，12/60 变化）；
  其余局逐位不变（覆盖 33/174 段，未实现的仍是 no-op）。
- 测试/基线：新增 29 条（`test_p_items_db.py` 10 / `test_gkbench_submission_p_items.py` 6 /
  `test_p_items.py` +5 / `test_p_items_integration.py` +4 / `test_local_bench.py` +4，
  并从 old unsupported trigger 列表移除 exam_start）；全量 pytest
  **1051 passed / 1 skipped（1052 收集 / 76 文件）**；① 4/4+3/3、③ 86/86+24/24、
  ④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。
- 剩余（下一段）：真机培育侧 P 道具列表（T6/D1 补采）、效果覆盖
  （ExamLessonValueMultiple/ExamParameterBuff/ExamStaminaReduceFix/生成卡/指針类
  需要参考引擎语义与主数据文本重解析）、主道具附魔/回忆、gkbench obs 无已用次数。
- 细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) / HANDOVER 二·补二十七。

### B7.（可选，2026-11-22 新增）P 道具 47 条补全（更新 master 快照重建 p_items.json）✅ 2026-11-22 完成
- **背景**：B6 接入了 P 道具数据管线，但 `p_items.json` 是 2026-09-16 快照（1068 件），
  上游结构已 1115 件；作者 11-22 整合包里的 `masterTrans/ProduceItem.json` 给出了完整
  1115 个 id（含 gkbench 的 11 个未知 id），但只有 id、没有效果数据。
- **完成**：`scripts/build_p_items.py` 改为「本地中文 master 1068（逐段对齐）+ yaml 独有
  47 条」合并生成——新增 id 的结构化字段/日文文本来自 gkumasu-diff
  `data/cache/ProduceItem.yaml`（已是最新 1115），卡名用仓库自译表
  `data/i18n/translation_new.json`（47/47 命中），**中文描述缺失**处 `text_zh=""`、
  `text_ja` 保留日文并标 `i18n_text_source="ja"`（不猜、不臆造）；新触发 id 没有中文
  触发句 → `condition_known=False`（22 件），`apply_passive` **保守不触发**（不把带条件
  的道具当无条件结算）。重建 `data/knowledge/p_items.json`：**1068 → 1115 件**，
  specs 1764 → **1849 段**、已实现 421 → **445 段**；gkbench 505 题模板未知 id
  **11 → 0**（83 唯一 id 全已知；其中 10 段条件未知不触发，如实记录）。
- **DoD**：catalog 1115 件 ✅；gkbench 未知 id = 0 ✅；pytest 全绿 ✅（见下）；
  A/B 新数字见 HANDOVER 二·补二十八；文档同步（RULES_REFERENCE §5.3 / README / INDEX /
  HANDOVER / HANDOVER_NEXT / SIMULATOR / GKBENCH / COMPARE / PROVENANCE / I18N_TODO）。
  纯离线，不碰真机/账号。
- 细节/为什么这是首选见 [HANDOVER_NEXT §4 T9](HANDOVER_NEXT.md) / [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)。

### B8. T5④ P 道具条件/效果语义（第一批，纯离线）✅ 2026-11-22 完成
- **目标**：B7 清了「数据缺口」后的下一段——把 P 道具的**条件**与**效果语义**从文本猜测
  推进到结构化、可验证、可回归的实现（不猜）。
- **完成**：
  1. **新语法 trigger id 结构化解析**（`scripts/build_p_items.py`）：
     上游 2026-11 新触发的条件编码在 id 后缀（`remaining_turn-N`、`parameter_buff_up-N`、
     `stamina_up_multiple-N`、`stamina_less_multiple-N`、`full_power_point_get_sum_up-N`、
     `card_play_aggressive_up-N`、`exam_review_up_interval-N`、`lesson_*`）→ 解析成
     `trigger_params` + 条件串；**条件未知 22→6 件**（16 件从 id 恢复）。指定卡名 /
     手牌指定卡张数缺卡名→id 映射 → `trigger_known=False`（103 件 / 185 段）保守跳过。
  2. **效果语义**（`sim/p_items.py`）：依赖换算「X 的 N% 数值变为 Y」（65 段，
     `depends_on` + `percent`，`int(源层数×N/100)`；源=好印象/元气/干劲/集中/累计全力值/
     消耗过的体力）、「X 变为 0」（3 段 `zero_stack` 清零）、`ExamStaminaReduceFix`
     固定/最大体力百分比体力消耗 + `ExamStaminaRecoverFix` 百分比回复（9 段 `percent_max`）。
  3. **新触发时机 + 双镜**（`sim/lesson.py` + `sim/expectimax.py`）：`turn_start_after`、
     `turn_interval`、`status_gain_interval`、`stance_change`、`stamina_reduce`；
     `full_power_point_total` / `consumed_stamina_total` / `status_gain_counts` 随事件维护，
     `state_from_sim`/`sim_from_state`/`canonical` 全镜像。
- **数据/结果**：catalog spec **1849** 不变；数据层已实现 **445→676 段**（no-op 1404→1173）；
  条件未知 22→**6 件**（46→10 段）；trigger 未知 103 件/185 段（新口径，单列）；
  依赖换算 65 / 百分比体力 9 / 归零 3 段；gkbench hif 83 唯一 id 已实现 **34→59 段**。
- **测试/基线**：新增 `tests/test_p_items_b8.py` 19 条 + 旧测试按新口径更新；全量 pytest
  **1067 passed / 1 skipped（1068 收集 / 77 文件）**；基线 ① 4/4+3/3、③ 86/86+24/24、
  ④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。
- **离线 A/B**（与 B7 同 harness：hif 30 题×2 seed=1000/1001、`--budget-ms 100`、配对）：
  greedy off 3840.7 → **auto 4065.9（+225.2，+5.86%，CI95 [+86.7,+363.6]，17胜/1负/42平，
  18/60 局变化）**；expectimax(analytic) 3726.4 → **3921.8（+195.4，+5.24%，
  CI95 [−125.3,+516.2]，墙钟噪声，仅方向记录）**。
- **DoD**：条件/效果语义有结构化字段 + 单测 + 真数据覆盖数字 ✅；A/B 有配对数字 ✅；
  文档同步（RULES_REFERENCE §5.3/§6、WORKPLAN、HANDOVER_NEXT、HANDOVER 二·补三十一、
  INDEX/README）✅；纯离线，不碰真机/账号 ✅。
- **剩余（下一段候选）**：持续倍率类 `ExamLessonValueMultiple`（需持久分数倍率字段与取整
  顺序证据）、`ExamCardCreateId` 生成卡、`ExamExtraTurn`/`ExamBuffConsumptionAdd`/
  `ExamReviewMultiple` 等 modifier、指定卡名/手牌张数（需卡名→id 映射）、好调依赖换算
  （量纲不同不猜）。

### B9. T5④ P 道具持久倍率 / modifier 类效果（第二批，纯离线）✅ 2026-11-22 完成
- **目标**：B8 清了条件/第一批效果后的下一段——把**持续若干回合、影响分数/费用/回合数**的
  modifier 类效果按参考引擎语义实现（不猜）。
- **语义来源**：gakumas-tools（BSD-3）`Executor/resolvers.js::resolveScore` f/g、`resolveCost`、
  `BuffManager.js`（`setScoreBuff(amount, turns)` 列表 + 回合末倒计时 + fresh）、
  `p_items.csv` DSL（`setScoreBuff(0.5,1)` / `setStance(preservation)` / `costReduction+=N` /
  `halfCostTurns` 等）——只按语义重写，不拷代码。
- **数据层**（`scripts/build_p_items.py`）：`annotate_modifier_effects` 把 effect_type（+效果文本）
  标成 `target`/`duration`（20 类 target、**369 段 / 298 件道具**；percent1 → 千分比、
  `values.turn` = 持续回合、缺省永久）；从描述解析「（训练内N次）」等次数上限 →
  `max_uses` **9→896 件**（不解析会让持续倍率每回合重复触发；也修正了 B6–B8 期
  「生效效果可无限触发」的口径，所以 B9 auto 与 B8 auto 不可直接比）。
- **纯规则**（`sim/p_items.py`）：`PItemDelta` 新增 `score_buffs/score_debuffs/modifiers/
  cost_reduction/cost_increase/half_cost_turns/double_cost_turns/extra_turns/stances/
  perfect_condition_turns/poor_condition_turns` + 定时列表纯函数
  `add_timed/total_timed/tick_timed/timed_dict_*/normalize_turns`。
- **落地效果**（20 类 target）：`ExamLessonValueMultiple(+Down)` 持久分数倍率/减益
  （加算、f/g 顺序）；`ExamReviewMultiple` 好印象强化（共用卡渠道）；`ExamReviewCountAdd`
  好印象追加发动（回合末结算重复 N+1 次）；`ExamEnthusiasticMultiple/Additive` 热意增益/
  追加（共用 T5② 渠道）；`ExamLessonBuffMultiple/Additive` 集中强化/增加量增加；
  `ExamReviewAdditive` / `ExamAggressiveAdditive` / `ExamFullPowerPointAdditive`
  好印象/干劲/全力值增加量增加（获得量 ×(1+N%)、ceil）；`ExamParameterBuffMultiplePerTurn` /
  `ExamGimmickParameterDebuff` 绝好调/不调回合；`ExamStaminaConsumptionDownFix/AddFix/Down/Add`
  费用永久加减 + 「接下来 N 回合 ×0.5/×2」；`ExamExtraTurn` 回合追加（回合末
  `turns_left−1` 后补上、`total_turns` 同步增长）；`ExamPreservation/ExamConcentration`
  直给式（文本判定「温存变更/强气变更」，同指針升级 2 段階、触发温存解除收益）；
  `ExamBlockFix` 固定元气 / `ExamReviewReduce` 好印象减少（层数夹 ≥0）；
  「消耗体力减少状态」条件（`half_cost_state` 伪 stack）。
- **双镜**：`LessonSim` / `ExpectState` 新字段 + `canonical` + `state_from_sim`/`sim_from_state` +
  出牌分/回合末好印象/费用/回合末倒计时/指針直给事件全镜像（含递归深度 ≤3 防链式）。
- **数据/结果**：catalog spec 1849 不变、已实现 **676→1025 段**（no-op 1173→824）、
  modifier **337 段**；gkbench hif 83 唯一 id 已实现 **59→103/153 段**；
  新增 `tests/test_p_items_b9.py` **49 条**、旧 `test_p_items.py` 更新；
  全量 pytest **1116 passed / 1 skipped（1117 收集 / 78 文件）**；
  基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。
- **离线 A/B**（同 harness：hif 30 题×2 seed=1000/1001、`--budget-ms 100`、配对，
  bootstap CI 按题重采样）：greedy 3840.7 → **3951.0（+110.3，+2.87%，
  CI [+39.6,+193.3]，20胜/2负/38平）**；expectimax(analytic) 3666.5 → **3822.8**
  （+156.2，+4.26%，CI [−137.4,+435.4]，墙钟噪声、只作方向记录）。
- **如实记录（保持 no-op / 未建模）**：`ExamBuffConsumptionAdd`（强化状态花费卡机制不在
  我们的卡牌模型里，无落点）、`ExamCardCreateId` 生成卡（17 段 catalog，需考试内生成卡模型）、
  指定卡名/手牌张数（trigger 未知 103 件/185 段，缺卡名→id 映射）、
  增益倍率的整数取整（`safe_ceil` 近似参考引擎浮点）、fresh buff 差一回合（§RULES §3）、
  真机培育侧 P 道具列表（T6/D1）、主道具附魔/回忆。
- 细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) / HANDOVER 二·补三十二。

### B10. T5 剩余机制①② ExamCardCreateId 生成卡 + 指定卡名/手牌张数映射（纯离线）✅ 2026-11-23 完成
- **目标**：B9 之后 T5 剩余里纯离线可做的两块——① 生成卡（确定式）；② 触发限定结构化
  （卡名→id 映射，103 件 trigger 未知）。③ `ExamBuffConsumptionAdd` 保持 no-op（用户指定不猜）；
  ④ fresh buff 差一回合需真机截图，不在本会话。
- **语义来源**：masterTrans `ProduceCardSearch.json` 描述表 + 主数据 `ProduceCard.effectGroupIds` /
  `originIdolCardId` / `originCharacterId` + BSD-3 参考引擎 gakumas-tools（`usedCardBaseId`
  base id 不限强化 / `countCards` 区域 / `addCardToHand` 手牌≥5 不生成 / `limit:N` 按道具计次；
  生成卡 id 交叉验证 111=静かな意志+ / 131=本番前夜+ / 421=プライド+ / 23=眠気）。
- **落地**：新 `scripts/build_card_meta.py` → `data/knowledge/card_meta.json` +
  `src/gkagent/data/card_meta.py`（idol_unique 判据与参考 pIdol 交叉 **340/342、0 误报**；
  effect_groups 取卡面 effectGroupIds；日文别名 1753）；`build_p_items.py` `parse_card_search`
  （play_filter / zone_count）+ `annotate_create_effects`（create / create_random）；
  `sim/p_items.py` `CardFilter`/`ZoneCount`/`CreateCard` + `exam_start_after` 新时机 +
  **次数上限按道具计**（limit:N 口径修正）；`lesson.py`/`expectimax.py` 生成卡落牌双镜
  （known_draw/discard_order 同步）+ `play_choice.spec_from_name`。
- **数据/结果**：触发未知 **103→3 件 / 185→6 段**（hold 2 + hotfix 1）、条件未知 **6→0**；
  play_filter 234 件 / zone_count 27 件；生成卡 **11 段确定 + 6 段随机（no-op）**；
  数据层已实现 **1025→1042/1849 段**；gkbench 103/153 段（loadout 4 件/8 段原 trigger
  未知道具现在真实触发）。
- **离线 A/B**（同 harness：hif 30 题×2 seed=1000/1001、`--budget-ms 100`、配对）：
  greedy 3840.7→**4638.2（+797.5，+20.76%，CI [+399.0,+1250.1]，31胜/3负/26平）** /
  expectimax 3665.8→**4466.9（+801.1，CI [+66.3,+1697.9]）**。off 与 B9 逐位相同；
  不可直接比 B9 auto（触发映射 + 次数口径修正）；确定式生成卡不在 hif loadout → ① A/B 贡献 0。
- **测试/基线**：新增 `tests/test_p_items_b10.py` **38 条**（含参考交叉验证，缺 data/dl 自动 skip）；
  旧测试按新口径更新；全量 pytest **1154 passed / 1 skipped（1155 收集 / 79 文件）**；
  基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。
- **如实记录**：随机基础卡（H.I.F应援棒 6 段 / gkbench 172 段权重）RNG 未知保持 no-op；
  hold 保留区 2 件 + hotfix 1 件保守不解析；微熱ノスタルジー♡ 无 origin 字段不算偶像固有；
  `ExamBuffConsumptionAdd` 保持 no-op。
- 细节见 [RULES_REFERENCE §5.3](RULES_REFERENCE.md) / HANDOVER 二·补三十三。

### B2-R. B2 学习叶子按 B3+ 规则重训（纯离线）✅ 2026-11-23 完成（**可复现负结果；高预算验证后路线关闭**）
- **目标**：T5 机制（B4–B10）补齐后，按 EXPECTIMAX「B2 学习叶子」同配方重采/重训/配对评测，
  回答「B3 每回合 1 张规则下学习叶子还有没有收益」。
- **完成**：① 旧模型 FAIL 复现（选择段 −26.1，与 B3 重测逐位一致 → B4–B10 对 small harness
  零影响、基线稳定）；② 训练/推理分布等价性探针（2000 叶子逐字段等价）+ 修掉温存→全力
  回合边界解除收益的快照口径差（`RecordingLessonSim._pre_end_turn_stance`，+1 回归测试）；
  ③ 重采 3 批 beam 全知自对弈 **26,500 样本、0 fallbacks**（纯 on-policy 分数标签、
  **不加 PBRS 塑形**——auto-gakumas −26,884 负结果同向）；④ 重训 MLP 104→96→48
  （val r²=0.906 / MAE 7.0 / σ=11.1，特征保持 104 维）；⑤ eval_b2 选择段 80 局 +
  确认段 120 局（unknown/known）+ σ 敏感性诊断。
- **结果（负）**：确认段 unknown beam 94.9→learned **87.7（−7.2 CI[−9.5,−5.0]）** /
  known 96.8→85.3（−11.5）；ensemble 0.75 两段中性（−0.5/−0.6，CI 含 0）；
  within_learned −19.9；learned σ×2/×4 更差（−9.0/−12.1）→ μ 排序本身有害，非 σ 校准。
  旧模型 −26~−28 → 重训 −7：**口径对齐消掉大部分伤害，但没转正**。
- **高预算验证（2026-11-23 同日，用户指定「更强的 bot 能不能兑现学习叶子」）**：
  width8/300ms（teacher 级）选择段 80 局 seed 2000 配对：beam 解析式 93.9→learned **89.4
  （−4.4 CI[−8.8,−0.0] 显著负）** / ensemble 0.75 +0.0（中性）→ **FAIL，不跑确认段**。
  伤害 −7.0→−4.4 收窄，但**主因是解析式基线自己在高预算下变差（97.3→93.9，CLEAR
  11.2%→7.5%），learned 绝对分几乎不动（90.3→89.4）**——加预算兑现不了学习叶子；
  within 家族与 200ms 逐位相同、评测墙钟 <80s（small 场景搜索提前收敛，预算很少触顶）。
- **处置（路线关闭）**：生产 `leaf_model` 默认关闭不变；beam 默认 = 解析式叶子；**T2 真机 A/B 候选
  去掉 learned leaf**；重训候选保留 `out/b2r_leaf_mlp_small.json`（gitignore），tracked 模型
  按用户指定回退旧版（两版都 FAIL、生产关闭故行为无差）；根因诊断已完成：锐利 σ 放大 + 价值-策略失配；
  **高预算验证也 FAIL → 学习叶子（状态价值 MLP 叶子）路线正式关闭，不再投入**
  （EXPECTIMAX B2-R「高预算验证」）。**下一步转 C1 执行层可靠性**（用户指定）。
  不做第二轮专家迭代/档位头（B2 已知负结果）；large 场景重采需先更新特征（熱意/score_buffs/
  modifier），预算外。再下一候选：渐退式专家迭代（学 policy/advantage 而非状态价值，
  换目标量的新路线，**启动前先问用户**）；备选：auto-gakumas 每战在线自适应（需真机/独立副本，先问用户）。
- **测试/基线**：`tests/test_b2_leaf.py` 12 条；全量 pytest **1155 passed / 1 skipped
  （1156 收集 / 79 文件）**；基线 ①③④⑤ 全部不变。
- 细节见 [EXPECTIMAX「B2 重训（B2-R）」](EXPECTIMAX.md) / HANDOVER 二·补三十四/三十五。

### B11. 渐退式专家迭代（学 policy/advantage，评测门渐退）🟡 第 1–2 轮 + r3–r8 续 + v6 接线 + r9-large + r10 + r11 双过入库 + r12 降档 + **r13 完整渐退入库**（2026-11-24，**v6 过门并接线；r9/r10 large 超 beam 但 small 回退 → 不入库；r11 新规则重采 + small 上采样 → 双过入库；r12 去 v1 示范 small 中性 → 通道 3 关闭不入库；r13 教师←r11 占比渐退 0.075 → large 显著超 r11 +2.882 入库、small 维持天花板**）
- **目标**：B2-R 关闭学习叶子（状态价值）路线后换目标量——学「该打哪张牌 / 这张比
  平均好多少」（policy/advantage），标签来自学生自己的对局（on-policy，绕开价值-策略
  失配）；摸索 70%+老师 30%，教师占比逐轮渐退（30→15→0），**学生过配对评测门
  （显著强于教师）后当下一轮老师**（用户设计意图，见 EXPECTIMAX B2-R 末段）。
- **第 1 轮落地（纯离线代码+单测）**：`sim/policy_mlp.py`（137 维 = B2 104 状态特征 +
  33 动作特征 → 96→48→1 优势分；`net_action` 编码硬规矩：有牌绝不 SKIP、无静默回退）+
  `sim/policy_data.py`（决策记录 + **精确重放分支**优势标签：同 seed 重放前缀逐字段全等
  校验 → 打候选牌 → 当前学生打完 → A=R−mean(R)，不走搜索镜像）+
  `build_ei_dataset.py` / `train_ei_policy.py`（BC/70-30 混合、seed 分组 9:1）/
  `eval_ei.py`（配对评测门）；`eval_known_draw.play` 加 net/greedy 分支（默认逐位不变）。
- **第 1 轮结果**：教师示范 400 局 5747 样本（beam width4/100ms+tiebreak，unknown）→
  v0 BC（val 排序命中 0.889）→ v0 自对弈 1000 局 14314 优势样本 → v1 混合（教师占比 0.300）。
  **确认段 120 局（seed 3000–3119）v1 97.5 vs 教师 94.9：Δ=+2.6 CI[+1.1,+4.1] 显著正 →
  评测门 PASS（放手）**；稳健块 4000–4119 +3.8 CI[+1.6,+6.0]；学生 0.40ms/决策（纯策略无搜索）。
  **消融（如实）**：纯 BC v0 也过门（+2.4 CI[+0.7,+4.1]），v1−v0=+0.2 不显著 →
  第 1 轮红利主力 = 逐决策蒸馏 + 硬规矩禁跳（教师每回合规划一次会过期/提前 SKIP），
  on-policy 优势成分方向正但未独立证明。
- **第 2 轮落地（2026-11-23，用户选定；纯增量代码+单测）**：`build_ei_dataset --teacher-net`
  （教师=学生网逐决策示范，软目标同口径，教师 SKIP 剔除恒 0）+ `eval_ei --baseline-net`
  （门基线=上一轮学生，beam 臂保留作绝对水位）+ `train_ei_policy --round`；默认行为逐位不变。
  v1 示范 400 局 5773 样本（seed 400000+，教师均分 98.1）+ v1 自对弈 1000 局 14526 优势样本
  （seed 300000+，std 12.0）→ **v2 85/15**（17089 样本，教师占比精确 0.150，val 排序 0.818）
  + 消融 **v2_bc**（纯 v1 示范自蒸馏，val 排序 0.933）。
- **第 2 轮结果（平台期 + large 泛化缺口）**：small 确认段 120 局 **v2 97.9 vs v1 97.5：
  +0.4 CI[−0.4,+1.2] → CONTINUE**（选择/稳健 4000/新鲜块 5000 四段全中性，98/120 局逐位相同）；
  消融 v2_mix−v2_bc=+0.54 CI[−0.40,+1.48]（on-policy 成分连续两轮方向正、未独立证明）；
  纯自蒸馏 v2_bc−v1 中性。**large 首测（31 张/9 回合）**：v1 比 beam **−28.1 CI[−36.0,−20.2]**
  （277.2 vs 305.3，CLEAR 36.7% vs 53.3%），v2 比 v1 还略差（选择段 −14.8 显著）→
  small 训练不泛化 large，large 天花板是 beam 跨回合规划；两学生仍显著强于 greedy（+58~65）。
  绝对水位：v2−beam small +2.99 CI[+1.37,+4.62]；beam 参照臂 94.9/97.3/97.8 与 r1 逐位一致。
- **处置**：按设计**教师占比不降（保持 0.15）**、如实记录平台期（渐退节奏是超参不是定律）；
  生产接线未做（T2 候选暂不变：beam+全知/tiebreak）；v1 仍是 small 最佳学生。
  **下一轮候选（先问用户）**：继续扶（换变量：large 训练数据/更大学生网/多延续标签，
  同配方再采边际收益存疑）/ 收 loop 于 v1 转 T7/D1/E0/E。学生网要进 F 阶段 public-safe
  候选必须先过 large 训练/评测（gkbench hif 本戦 9–12 回合口径）。
- **第 2 轮续（r3–r8 继续扶，用户指令「显著强于老师才结束」）**：六轮换变量
  （新学生数据/数据×10/epochs×3/容量×2/ε-greedy 探索两体量），val 排序饱和 0.862，
  确认段 3000 七轮恒 +0.2~0.6（种子段结构，非模型问题）；**门协议修正（用户批准）：
  确认段扩 500 局 3000–3499、判据不变 → v6 98.6 vs v1 98.1：+0.6 CI[+0.2,+0.9] PASS**；
  新鲜块 6000 +1.7 CI[+0.6,+2.8] 独立佐证；池化 820 局 +0.71 CI[+0.40,+1.02]（W/L 101/41）。
  **v6（192×96）= 当前最佳学生，显著强于 v1**。探索变量中性（覆盖假设否证）；
  **large 泛化显著改善**（v6 large 291.6 vs v1 277.2：+14.4 CI[+6.5,+22.2]，
  vs beam 缺口 −28.1→−13.7）但仍低于 beam；生产接线仍未做。
- **r9-large（2026-11-23，用户授权安排；small+large 混合训练，单变量=加 large 数据）**：
  `train_ei_policy --selfplay/--demos` 多文件纯增量（**单文件 sha256 逐位不变** + 12 条回归测试）；
  large 自对弈 5000 局 126969 样本（v6 学生，seed 900000–904999）+ small r5 全量 145605 +
  示范 48101（补采 v1 1600 局 23050 解锁 0.15 上限）= 320675 行，192×96/1200ep 全同 r6。
  **large500（3000–3499）r9 315.4 vs v6 285.8：+29.6 CI[+26.2,+33.0] PASS；vs beam 301.3
  +14.2 CI[+10.9,+17.5] —— 首个 large 显著超 beam 的学生网**（CLEAR 62.6% vs beam 50.6%）；
  新鲜块 6000 +24.0 独立佐证，池化 620 +28.5。**但 small500 r9 98.2 vs v6 98.6：
  −0.42 CI[−0.67,−0.17] 显著回退**（选择段 −0.8 方向负，池化 580 −0.47；vs v1 +0.16 不显著，
  原门未保持）→ **复合门（large 改善且 small 不回退）未过 → 不入库**，生产 ei_policy_v6.json
  保持 r6 权重；r9 留 out/ 作 large specialist（T2 可 --net-model 换臂）。诊断假设：全局 std
  归一化稀释 small 信号（混合 18.71 vs v6 的 12.21 → 65%）+ v1 示范拉扯；候选修复=按场景 std
  归一化（下一轮单变量，先问用户）。**F public-safe 仍被 small 回退挡**。
- **r10（2026-11-23 晚，用户选定；按场景 std 归一化，单变量=归一化口径）**：
  `train_ei_policy --norm-by-scenario` 纯增量（默认关=逐位不变：4 参照模型 sha256 改前/改后
  一致，含 r9 单文件 3 参照；多文件各文件按自身 std，scenario 取 npz meta.args.scenario，
  mix/meta 记逐场景 std；单文件路径/demos 不受影响）+ 12 条回归测试。复用 r9 数据
  320675 行重训（192×96/1200ep/0.15 全同 r9；small std 12.2115 / large 24.0878 vs 全局
  18.7065）；能量份额实测 small 20.9%→**49.0%** / large 70.9%→**42.7%**（与 R9_ANALYSIS
  预测吻合）。**large500 r10 314.9 vs v6 285.8：+29.1 CI[+25.8,+32.3] PASS，vs beam +13.6
  仍显著超**（r10−r9 同 seed −0.53 CI[−1.64,+0.57] 中性 → 增益保持）；新鲜块 6000 +23.0。
  **small500 r10 98.38 vs v6 98.64：−0.256 CI[−0.500,−0.012] 仍显著回退**（r9 −0.42 收窄
  39%；池化 580 −0.267 同显著；**vs v1 原门恢复 +0.322 CI[+0.032,+0.612]**；CLEAR 12.2%==v6）
  → **复合门未过 → 不入库**，生产 ei_policy_v6.json 保持 r6 权重；r10 留 out/。
  **结论：归一化口径修复有效但不充分**（输入侧场景漂移仍在，R9_ANALYSIS §8 预测证实）。
  **下一候选（先问用户）**：r11 叠加 small 上采样（能量 →~66%）/ 其他候选见 HANDOVER_NEXT §8。
- **r11（2026-11-24，阶段2 用户选定；新规则重采 + small 上采样，单变量=上采样 + 新数据）**：
  `train_ei_policy --upsample-small N` 纯增量（默认 1=逐位不变：r9/r10 24 条回归全过；small 行重复 N 份
  提升能量份额，教师占比下采样之后调用，重复行保持 seed/group 不泄漏，mix 记 upsample_small）+ 13 条回归测试。
  **P2-0 新规则重采**（v6 argmax，新 seed 块）：small 10000 局 145565（1100000+，std 12.172）+ large 5000 局
  128103（1200000+，std 24.301）+ v1 示范 3600 局 51985（1300000+，0 教师-SKIP）；训练 467527 行
  （small ×2=291130 / large 128103 / demos 48294，教师行占比 0.103），192×96/1200ep 全同 r10；
  能量份额 small **65.6%** / large 28.9% / demos 5.5%（§6 候选② 预测 ~66% 吻合）；val 排序 0.822。
  **前置重标定 + 参照臂新规则重评**：sim_engine_ab 与 P1-8 逐位一致（Δ+372.2/+219.1）；small 规则零分移
  （v6 98.640/v1 98.062 不变）、large 分移 ±2（v6 285.8→287.818、beam 301.3→301.612），门基线重定。
  **large500 r11 313.92 vs v6 287.82：+26.10 CI[+23.06,+29.14] PASS，vs beam +12.31 仍超**（新鲜块 6000
  +20.81）；**small500 r11 98.648 vs v6 98.640：+0.008 CI[−0.253,+0.269] 不回退（上界≥0）✅**；
  **vs v1 +0.586 CI[+0.245,+0.927] 原门保持 ✅** → **复合门首次双过 → 入库**：ei_policy_v6.json 替换 r11
  权重（1004369 字节，参照臂逐位校验 6/6，旧 r6 权重保留 out/）。**P2-1b 新旧对比**：large headline
  r11 vs 旧 v6 +28.08 = 学生改进 +26.10（93%）+ 规则分移 +1.98（7%）；small 规则零分移；r11 small 显著优于
  r9（+0.426，修复 r9 回退）、large 与 r9/r10 中性（增益保持）。**F public-safe 入场券拿到**（首个双过学生）。
- **r12（2026-11-24，用户选定 ② r12 续 → A 降档 15→0；单变量=去 v1 示范，零代码改动）**：
  r11 配方去掉 v1 示范（`--teacher-frac 0`，无 `--demos`，纯自对弈），同新规则数据 + `--norm-by-scenario
  --upsample-small 2`。419233 行（small ×2=291130 / large 128103 / demos 0），能量 small **69.4%** / large 30.6%
  （r11 65.6/28.9/5.5）；val 排序 0.817，训练 3226.5s。**500 局双门（参照臂逐位 6/6）**：large500 r12 314.670
  vs v6 287.818 **+26.852 CI[+23.834,+29.870] 主门 PASS**（vs beam +13.058，新鲜块 6000 +21.125）；
  **small500 r12 98.656 vs v6 98.640 +0.016 CI[−0.286,+0.318] 中性（目的门「显著超 v6」下界<0 未达）**；
  vs v1 +0.594 CI[+0.188,+1.000] 原门保持；r12−r11 small +0.008 / large +0.750 均中性（统计不可分）。
  → **目的门未过 → 不入库，生产保持 r11**（ei_policy_v6.json 未动，r12 留 out/）。**通道 3（v1 示范拉扯）
  正式关闭**：去教师对 small/large 均无显著影响（与 §9 行为探针一致）；small 平台期非教师相关，是通道 2
  修复后的「学生≈教师」蒸馏天花板。不硬凑显著；若仍需 small 超 v6 剩候选③两段式微调/探索增量（非必需）。
- **r13（2026-11-24，用户追问渐退协议后选定 A；完整渐退迭代，教师←r11，占比渐退 0.15→0.075）**：
  采 r11 argmax 新自对弈 small 10000 局 145578（1400000+，std 12.058，均分 99.2）+ large 5000 局 135679
  （1500000+，std 24.591，**均分 317.8≫v6 288.9**）+ r11 示范 3600 局 51912（1600000+，0 教师-SKIP）；
  `--teacher-frac 0.075`（渐退减半）+ `--norm-by-scenario --upsample-small 2`，449639 行（small ×2=291156 /
  large 135679 / demos 22804），能量 small 66.4%/large 31.0%/demos 2.6%，val 排序 0.829，训练 3213.4s。
  **门基线换 r11**。**500 局复合门（参照臂逐位 6/6）**：large500 r13 316.802 vs r11 313.920
  **+2.882 CI[+1.309,+4.455] 主门 PASS（显著超最新老师）**（vs v6 +28.984、vs beam +15.190，新鲜块 6000 +2.783
  方向正）；small500 r13 98.620 vs r11 98.648 **−0.028 CI[−0.265,+0.209] 不回退 ✅**；vs v1 +0.558
  CI[+0.172,+0.944] 原门保持 → **复合门通过 → 入库**：ei_policy_v6.json 替换 r13 权重（1004426 字节，
  旧 r11 保留 out/）。**「让最新当老师」对 large 有效**（r11 更优 large 数据→r13 再超）；**small 维持蒸馏天花板**
  （r3–r8 平台期 + r12 通道 3 关闭 + r13 换最新老师仍中性，三重佐证）。目的（small 显著超 r11）未达但不门。
- **测试/基线**：`tests/test_ei_policy.py` **28 条** + `tests/test_ei_policy_r2.py` **15 条**
  + `tests/test_ei_explore.py` **7 条** + `tests/test_ei_wiring.py` **21 条**（入库断言随 r13 更新）
  + `tests/test_ei_multifile.py` **12 条** + `tests/test_ei_norm_scenario.py` **12 条**
  + `tests/test_ei_upsample_small.py` **13 条**；
  全量 pytest **1657 passed / 1 skipped（1658 收集 / 100 文件）**；基线 ①③④⑤ 全部不变。
  环境备注：首跑曾遇 drink_search 延迟守卫受游戏负载（TslGame）抖动失败，负载回落后
  复跑全绿，未改门槛（详见 EXPECTIMAX B11 第 2 轮「测试/基线」）。
- 细节见 [EXPECTIMAX「B11 渐退式专家迭代（第 1/2 轮 + r3–r8 续 + r9-large + r10 + r11 + r12 + r13）」](EXPECTIMAX.md) /
  HANDOVER 二·补三十七/三十九/四十/四十一/四十二/四十三/五十三/五十四/五十五。

---

### P1-1. 阶段1 首批：r10 行为探针 + 全力回合 + のんびり指針（纯离线）✅ 2026-11-24 完成

**来源**：HANDOVER_NEXT §8.0 多会话路线图 P1-1（用户 2026-11-23 晚确认 A 顺序）。
**DoD**：参考引擎证据（规则项）+ 代码 + 单测 + RULES_REFERENCE 核验表更新 + sim_engine_ab 重标定。

**① r10 决策行为探针**（`data/_r10_behavior_probe.py`，复用 r9 口径，纯分析；输出
`out/_r10_behavior_probe.json`）：small 500 局 v6/r10/v1 + large 120 局 v6/r10。
**判定：残留 small 回退（−0.256）已非 v1 风格贪即时分为主**——首分歧贪即时分偏置
r9 24:9 → r10 11:8（近均衡），r10 对 v1 耐心比 25:11 恢复 v6 水平（29:13），CLEAR 翻转
1:1 对称（r9 0:5 全负）；残留是无方向漂移噪声（通道 2 输入侧场景漂移的行为级佐证）。
large 增益机制不变（早回合 buff、0 次贪即时分分歧）。→ r11 small 上采样仍是对症变量；
换教师消 v1 拉扯不再是首要杠杆。详见 [R9_ANALYSIS §9](R9_ANALYSIS.md)。

**② 全力回合 +1 出牌/保留牌回手**（BSD-3 `constants.js FULL_POWER_EFFECTS /
FULL_POWER_CHANGED_EFFECTS` + `TurnManager.startTurn` + `BuffManager.setStance` +
contest-fidelity 美鈴回放）：以全力开始的回合 `extra_plays += 1`（连续全力每回合都有；
温存→全力边界后 = 解除 1 + 全力 1 = 2 次额外）；`held` 保留区全部回手（无手牌上限检查，
同 `moveHeldCardsToHand`；来源 holdCard/holdThisCard 留 P1-3，钩子用合成保留牌验证）；
**全力期间禁切指針**（`stance_change_allowed` 守卫，全力值获得不受影响）。

**③ のんびり指針**（`STANCE_CHANGED_EFFECTS` leisure 三条 + `resolveScore/resolveCost` ×0 +
`skill_cards.csv` 540-545/834 预约语义 + wiki 熱意 N=10 + contest-fidelity）：
`Stance.LEISURE` 分数/费用 ×0；解除 固定元気+5 / +1 出牌 / 熱意+10，**→全力时熱意改为
全体卡打分成长+10**（`target:all g.score+=10` 是 cardMap growth，`score_growth_all`
永久加算进白值、可叠加，不是即时分）；**温存→のんびり不触发温存解除**；のんびり期间禁切温存；
来源=卡预约（`ExamOverPreservation` 4 族 13 行，`LEISURE_RESERVE_SOURCES` 卡 id 证据表，
回合开始条件触发/次数扣减/永久不扣）+ P 道具 `stance_leisure` 直给（2 件标注；触发时机
`card_play_interval_after` 未支持仍保守不触发）。`sim_produce` MODELED_EFFECTS 32→33、
`play_choice` 旧 `ExamOverPreservation→preservation` 误映射移除（values 恒空从未生效）。

**双镜/兼容**：`LessonSim`/`ExpectState` 新字段（held/leisure_reserves/score_growth_all）+
canonical + state_from_sim/sim_from_state + 叶子快照（leaf_data）对齐；`release_on_stance_change`
扩 4 元组（6 调用点 + 既有测试断言更新）。**评测牌组组成不变**（のんびり卡 score 0/SSR/Legend
本就不进 build_pool；small 无全力值卡、large 冲刺 9 回合攒满 10 概率低）→ 重标定改前/改后
64 局逐位相同（差异=0）。
**旧 B11 数据/模型是旧规则口径，全保留不覆盖**（阶段2 重采新 seed 块练新批再新旧对比）。

**验证**：`tests/test_p1_stance_rules.py` **36 条**（纯规则/全力/のんびり/P 道具/双镜/解析/叶子）；
全量 pytest **1354/1（1355 收集 / 90 文件）**；ruff 通过；sim_engine_ab 重标定（seed 9000/9100
各 16 局 rules/expectimax，budget 800ms）**改前/改后 64 局逐位相同（差异=0**，新规则路径
未触达；expectimax 仍显著强于 rules Δ+372.2/+219.1，C+ 100%，0 blocked）；基线 ①③④⑤ 不变。
见 [RULES_REFERENCE §5.4](RULES_REFERENCE.md) / HANDOVER 二·补四十四。

### P1-2. 阶段1 第二批：handDecrease 抽牌修正 + pride 自尊（纯离线）✅ 2026-11-24 完成

**来源**：HANDOVER_NEXT §8.0 多会话路线图 P1-2（用户确认 A 顺序，不用再问）。
**DoD**：参考引擎证据（BSD-3 有据才做、不猜）+ 代码 + 单测 + RULES_REFERENCE 核验表更新 +
sim_engine_ab 重标定（改前/改后逐局对照）。

**④ handDecrease 抽牌修正**（BSD-3 `TurnManager.startTurn` :98-104
`cardsToDraw = max(3 − getHandDecrease, 0)` + `BuffManager.setHandDecrease/getHandDecrease/
decrementBuffTurns` + wiki `buffs.json`「手札減少」）：`LessonSim.hand_decreases` /
`ExpectState.hand_decreases`（timed 列表：按 turns 分组加算、回合末倒计时、∞ 永久）；
回合开始抽牌 `max(hand_size − Σ, 0)`（`_draw_hand` / `turn_draw_count` / beam 下一手 /
`sim_from_state` 补手牌同口径）；**只减回合开始抽牌，卡效果抽牌不受影响**（wiki 口径）。
来源=主数据 `ExamGimmickStartTurnCardDrawDown`（塔阶段 gimmick「手牌减少1（∞回合）」，
exam_start，12 段 / 6 件初星灯光紫；参考 DSL 无 setHandDecrease 用法、参考引擎标注
UNVERIFIED——机制按参考引擎、来源/数值按主数据+wiki，不猜）。nullifyDebuff 拦截未建模
（本模型 ExamAntiDebuff 本就 no-op，留 P1-4 相关）。

**⑤ pride 自尊**（BSD-3 `resolvers.js::resolveScore` f :178-184 + `constants.js`
EOT_DECREMENT_FIELDS/WHOLE_FIELDS）：`prideTurns>0` 时出牌分/回合末好印象在 f 段加算
`min(min(好印象,干劲)×0.02, 0.5)`（千分比 `min(min×20, 500)`，与 score_buffs 累加后一次乘）；
`prideTurns` 回合末 -1（好印象结算之后）；score>0 门。**来源离线可确定**（主数据+参考 DSL
交叉，pIdol 117/118 = 雨夜燕）：卡「我、绝不」（p_card-02-ido-3_140，4 变体，
`ExamLessonValueMultipleDependReviewOrAggressive` turn=5 ↔ skill_cards.csv 632/633
`prideTurns+=5`；条件门出牌前干劲>=9，主数据 trigger `…aggressive_up-9` 结构化解析，
未知 trigger 保守不给；再演翻倍）+ P 道具「一笔入魂/+」（pitem_02-2-117-0/1，turn=2/3 +
干劲+4/5 ↔ p_items.csv 354/355 `at:motivationIncreased { if:isDirectEffect &
goodImpressionTurns>=6 {…}; limit:1 }`；isDirectEffect=本模型 STATUS_GAIN 只从卡直接效果发射）。

**双镜/兼容**：`LessonSim`/`ExpectState` 新字段 + canonical + state_from_sim/sim_from_state +
叶子快照对齐；`CardSpec.pride_turns/pride_min_motivation`（sim_produce MODELED_EFFECTS
33→34、35 元组；play_choice 同口径 + `pride_min_motivation_from_trigger`）；
`PItemDelta.hand_decreases/pride_turns`；p_items.json 重标注（modifier 371→385，
implemented **1042→1056/1849 段**，仅 14 条记录标注变化，逐条 diff 校验）。
**评测牌组/gkbench loadout 组成不变**（自尊卡 score 0/SSR 不进池；688 loadout / 94 唯一 id
无 117/tower）→ 重标定改前/改后 64 局逐位相同（差异=0）。
**旧 B11 数据/模型是旧规则口径，全保留不覆盖**（阶段2 重采新 seed 块练新批再新旧对比）。

**验证**：`tests/test_p12_hand_decrease_pride.py` **36 条**（抽牌修正/自尊公式/来源/双镜/
解析/叶子）+ 既有断言随规则更新（test_sim_produce MODELED 34、test_p_items no-op 参数表）；
全量 pytest **1389/1（1390 收集 / 91 文件）**；ruff 通过；sim_engine_ab 重标定（seed 9000/9100
各 16 局 rules/expectimax，budget 800ms）**改前/改后 64 局逐位相同（差异=0**，新规则路径
未触达；expectimax 仍显著强于 rules Δ+372.2/+219.1，C+ 100%，0 blocked）；基线 ①③④⑤ 不变。
见 [RULES_REFERENCE §5.5](RULES_REFERENCE.md) / HANDOVER 二·补四十五。

### P1-3. 阶段1 第三批：hold 保留区建模 + lockStanceTurns 指針固定（纯离线）✅ 2026-11-24 完成

**来源**：HANDOVER_NEXT §8.0 多会话路线图 P1-3（用户确认 A 顺序，不用再问）。
**DoD**：参考引擎证据（BSD-3 有据才做、不猜）+ 代码 + 单测 + RULES_REFERENCE 核验表更新 +
sim_engine_ab 重标定（改前/改后逐局对照）。

**⑥ hold 保留区建模**（BSD-3 `CardManager/index.js` hold/enforceHoldLimit/holdThisCard/
holdSelectedByTarget/moveHeldCardsToHand :959-1102 + useCard thisCardHeld :639 +
`TurnManager.endTurn` 只弃手牌）：`LessonSim.held`/`ExpectState.held`（P1-1 已有字段）
来源接通——**上限 2**（超限最旧进弃牌堆）、**跨回合保留**、holdThisCard 本牌不进弃牌/除外、
holdSelected 从目标区选牌移入（known_draw/discard_order 同步）、moveHeldCardsToHand
**LIFO** 回手（P1-1 钩子对齐参考 pop()）。主数据 `ExamCardMove`（values 恒空）语义按
**13 族卡逐卡证据表** `hold.HOLD_SOURCES`（skill_cards.csv 行号交叉，card_meta 别名核对）：
冲刺/积累（holdThisCard 温存中）、潜在能力/互动的基础（holdSelected[hand]）、切磋琢磨/
觉悟/新的舞台/努力了，哦/那一天，在这里（+/++/+++ 2 张）/对战请多指教！/让群星散落吧
（holdSelected[deck|discarded]）、爱意彩虹（holdSelected[deck]）、一点一滴的进步
（moveHeldCardsToHand）。**表外卡保留旧 +1 抽牌近似**（潮流领袖/展翅高飞/发挥本领/
决不停歇：全力值消耗/holdSelectedUpto/target:held 成长/干扰卡计数未建模，不猜）。
选牌是玩家选择——按白值分降序确定性选（参考 HeuristicStrategy 全力预览分排序等价）。

**lockStanceTurns 指針固定**（`constants.js` EOT_DECREMENT_FIELDS + FULL_POWER_EFFECTS
`lockStanceTurns==0` 门 + `BuffManager.setStance` :262 + `Executor` freshBuffs :271-279）：
`StanceLock` turn=1（切磋琢磨 ↔ DSL 424/425 `lockStanceTurns+=1`）；>0 禁切指針 +
全力进入门不满足（全力值不消耗）；回合末 -1，**fresh 保护**（获得当回合末不扣 → 锁下一
回合，卡面「指针固定1回合」确定语义）；再演翻倍（直接效果）；全力解除不受守卫。

**B10 遗留 trigger_unknown 3 件清零**：hold 区张数条件（`p_card_search-hold` → zones
["held"]）——实现的觉悟/±（pitem_03-3-078，魅力刚刚好使用后 + countCards[held]>=1 ↔
叶える覚悟 pIdol 74 csv 212/213）→ 温存变更/温存阶段变更 + 全力值+2/+4；hotfix 1 件
（咲季营养餐・改 pitem_02-3-309-0，`period810_hotfix` 证实为非限定标记：masterTrans
描述表无此目标 + 中文触发句无卡限定 + 参考 DSL 无卡过滤三源一致 ↔ 咲季の完全食・改
csv 404 turnCardsUsed%2==1）→ 回合内每第 2 张卡好印象+2/好印象强化+25% limit1。
**温存 2 段階直给 preservation2**（「温存阶段变更」value1=2 ↔ setStance(preservation2)，
7 段重标注：实现的觉悟+/初星手办/圆润的春色/±/梦想中的星辉/±/强化滚轮桃）。

**双镜/兼容**：`LessonSim`/`ExpectState` lock_stance_turns(+fresh) 字段 + canonical +
state_from_sim/sim_from_state + 叶子快照对齐；`stance_change_allowed(locked=…)`/
`end_turn(locked=…)` 纯增量（默认 False = 旧行为）；`CardSpec` 6 新字段（hold_this/
hold_this_when_save/hold_select_zones/hold_select_count/hold_move_to_hand/
lock_stance_turns）；sim_produce MODELED_EFFECTS 34→35（StanceLock）、41 元组；
play_choice 生产卡表同口径；p_items.json 重建仅 9 条记录变化（3 件 trigger_known +
7 段 preservation2，逐条 diff 校验）；**implemented 保持 1056/1849**（机制本就支持，
之前是触发保守不解析），**trigger_unknown 3→0 件 / 6→0 段**。

**评测牌组组成变化（与 P1-1/P1-2 不同，如实记录）**：冲刺/积累 的 ExamCardMove 从
+1 抽牌近似改为真实 holdThisCard（**保留不是抽牌**）→ draw 1→0；eval_expectimax
large 牌组抽牌签名槽改选决不停歇，冲刺/积累让出槽位（保真度修正，旧近似高估）；
**small 牌组不变**。sim_engine_ab 重标定（seed 9000/9100 各 16 局 rules/expectimax
budget 800ms）改前（git stash）/改后逐局对照——**64 局逐位相同（差异=0）**：冲刺/积累
在这 64 局的培育奖励选择中未被采到，池字段变化零触达（sim_engine_ab 用 14 张基础牌组
+ 奖励池动态采牌，与 eval_expectimax 的固定 large 牌组不同口径）；expectimax 仍显著强于
rules（Δ+372.2 / +219.1 评价点，15/0/1 与 11/0/5，C+ 100%，0 blocked / 0 error），
B3 结论保持。**旧 B11 数据/模型是旧规则口径，全保留不覆盖**（阶段2 重采新 seed 块练新批
再新旧对比）。

**验证**：`tests/test_p13_hold_zone.py` **46 条**（纯规则/LessonSim/双镜/P 道具/数据层/
解析）+ 既有断言随规则更新（MODELED 35 / 41 元组 / trigger_unknown 0 / preservation2 /
large 牌组组成）；全量 pytest **1435/1（1436 收集 / 92 文件）**；ruff 通过；基线 ①③④⑤ 不变。
见 [RULES_REFERENCE §5.6](RULES_REFERENCE.md) / HANDOVER 二·补四十六。

### P1-4. 阶段1 第四批：nullifyDebuff 低下状态无效拦截 + ⑦ ExamBuffConsumptionAdd / countDebuffs 评估（纯离线）✅ 2026-11-24 完成

**来源**：HANDOVER_NEXT §8.0 多会话路线图 P1-4（用户确认 A 顺序，不用再问）。
**DoD**：参考引擎证据（BSD-3 有据才做、不猜）+ 代码 + 单测 + RULES_REFERENCE 核验表更新 +
sim_engine_ab 重标定（改前/改后逐局对照）。

**nullifyDebuff 拦截**（P1-2 遗留；BSD-3 `Executor/index.js` executeAssignment :429 /
executeCallAction :507 / executeSpecialAction :545：`nullifyDebuff>0` 且 lhs∈DEBUFF_FIELDS
或动作∈DEBUFF_SPECIAL_ACTIONS → nullifyDebuff-- 并整条跳过；`constants.js`
DEBUFF_SPECIAL_ACTIONS = setScoreDebuff/decreaseFullPowerCharge/setHandDecrease；
nullifyDebuff ∉ EOT_DECREMENT_FIELDS = 消耗式计数器无回合倒计时）：
`LessonSim.nullify_debuff`/`ExpectState.nullify_debuff` + canonical + state_from_sim/
sim_from_state + end_turn_state 携带；`intercept_debuff_entries` 纯函数逐条消耗。
本批拦截已建模的两个 DEBUFF_SPECIAL_ACTIONS：**setScoreDebuff**（score_debuffs 列表逐条）/
**setHandDecrease**（hand_decreases 列表逐条），顺序 score_debuffs → hand_decreases。
**来源（P 道具侧）**：`ExamAntiDebuff` values.count → nullify_debuff 目标，主数据 11 段
（偷懒的毛巾 pitem_00-2-116-0 おさぼりタオル 舞蹈回合开始无效 1 次 limit1 ↔ p_items.csv 317
`at:turn { nullifyDebuff+=1; limit:1 }` + 塔 gimmick 初星灯光/旗帜/道具 10 段）。

**⑦ ExamBuffConsumptionAdd 保持 no-op**（强化状态花费卡机制无落点）：参考语义 =
`doubleBuffCostTurns`（processCost/checkCost 时 BUFF_FIELDS 花费 ×2，EOT 递减；
`CardManager.useCard` :654 buffCostConsumed 触发 + `Executor.triggerChangeEffects` :345）；
主数据 4 段（不息的风暴 pitem_03-3-345-0/1、迷倒世界的模样 pitem_01-3-349-0/1 ↔ p_items.csv
488/489/500/501 `doubleBuffCostTurns+=1`），gkbench 22 loadout。**为什么无落点**：参考有
88 张 buff-cost 卡（cost 列 concentration-=3/motivation-=3/goodImpressionTurns-=2/
fullPowerCharge-=2 等），6 张在 build_pool、潮流领袖在 eval large、gkbench 牌组 340 条；
**但我们的卡模型不承载 buff 花费**（card_table cost=0、CardSpec 无 buff_cost 字段、
可用性/支付/buffCostConsumed 触发未建模）→ 落地需先扩卡模型，超出本批 bounded 范围，
**保持 no-op 不猜**，语义/段数/loadout 如实记录。

**countDebuffs 保持未建模**（低下状態の数，无落点）：参考 `BuffManager.countDebuffs` :331
（DEBUFF_FIELDS>0 计数 + scoreDebuffs/handDecreases 条目数，标注 UNVERIFIED）；参考全部
CSV + 主数据**零使用**（仅 removeDebuffs 用于「属于我的色彩」わたしらしい色 csv 534/535）。

**双镜/兼容**：p_items.py（ANTI_DEBUFF_EFFECTS / TARGET_BY_EFFECT / effect_value 读 count /
PItemDelta.nullify_debuff / intercept_debuff_entries）；lesson.py/expectimax.py 计数器 +
拦截 + canonical + 快照往返（纯增量默认 0 = 旧行为）；p_items.json 重建仅 **11 条记录**
标注变化（逐条 diff 校验，全是 ExamAntiDebuff target None→nullify_debuff）；
**implemented 1056→1067/1849**（+11），modifier 标注 385→396。**卡侧 4 SSR 族来源延迟**
（偶像之魂/精确无比的标牌制作/红叶下奔跑/甜蜜陷阱♡，主数据 ExamAntiDebuff values 恒空需
逐卡证据表、SSR 不进 pool）；**标量 DEBUFF_FIELDS 拦截**（delta 聚合丢失逐动作粒度）/
**decreaseFullPowerCharge**（未建模）/ lock_stance 卡路径留后续。

**评测牌组 / gkbench loadout 组成不变**：nullifyDebuff 来源评测零落点（gkbench 94 唯一
道具 id 无 116/tower；build_pool 无 ExamAntiDebuff 卡）。sim_engine_ab 重标定（seed
9000/9100 各 16 局 rules/expectimax budget 800ms）改前（git stash）/改后逐局对照——
**64 局逐位相同（差异=0）**；expectimax 仍显著强于 rules（Δ+372.2 / +219.1 评价点，
15/0/1 与 11/0/5，C+ 100%，0 blocked / 0 error），B3 结论保持。**旧 B11 数据/模型是旧规则
口径，全保留不覆盖**（阶段2 重采新 seed 块练新批再新旧对比）。

**验证**：`tests/test_p14_nullify_debuff.py` **30 条**（纯规则/P 道具解析/LessonSim/双镜/
数据层 no-op 记录）+ 既有断言随规则更新（test_p13 implemented 1056→1067）；全量 pytest
**1465/1（1466 收集 / 93 文件）**；ruff 通过；基线 ①③④⑤ 不变。
见 [RULES_REFERENCE §5.7](RULES_REFERENCE.md) / HANDOVER 二·补四十七。

### P1-5. 阶段1 第五批：P 道具剩余效果语义补全（bounded batch：层数减少 + 好调回合 + 好调依赖换算，纯离线）✅ 2026-11-24 完成

**来源**：HANDOVER_NEXT §8.0 多会话路线图 P1-5（用户确认 A 顺序，不用再问）。
**DoD**：参考引擎证据（BSD-3 有据才做、不猜）+ 代码 + 单测 + RULES_REFERENCE 核验表更新 +
sim_engine_ab 重标定（改前/改后逐局对照）。**bounded batch**：挑证据充分、离线可定、
映射既有机制的低风险段，不贪多。

**本批三块**（语义全部经 BSD-3 参考引擎 + 主数据 + 参考 DSL `p_items.csv` 三重核实）：

1. **层数减少类**（资源 -= N，夹取 ≥0；参考 `executeAssignment` op "-=" + `NON_NEGATIVE_FIELDS`；
   资源不是 DEBUFF_FIELDS，nullifyDebuff 不拦截）：`ExamAggressiveReduce` 干劲减少
   （DSL motivation-=1 スタイリッシュモード/初恋の証・麻央）/ `ExamLessonBuffReduce` 集中减少
   （concentration-=1 イケてるセーター/「Pっち」）/ `ExamFullPowerPointReduce` 全力值减少
   （fullPowerCharge-=2 ユートピアへの誘い；引擎 decreaseFullPowerCharge Math.max(0,…) 同口径）。
   全力值减少走**独立 `PItemDelta.full_power_point_reduce`**（apply_full_power_point 只表达增加，
   负 delta 按 0），双镜 max(0, fp−N)，不计累计全力值。aggressive/focus 负层数走既有夹取。
2. **体力减少 `ExamStaminaDamage`**：并入 STAMINA_LOSS_EFFECTS（固定扣体力 + 计累计消耗）。
   DSL 私の「初」の楽譜 `cost-=1`（genki==0 时 resolveCost 穿透 stamina−1/consumedStamina+1），
   主数据条件「元气为0的时候」。
3. **好调回合 `ExamParameterBuff`「好调N回合」**：N 在 **turn 列**（effect_value 读 turn）→
   condition_turns += N（既有 parameter_buff 渠道，回合末 -1）。DSL goodConditionTurns+=N
   （Dearリトルプリンス/共に戦うタオル 等 33 件）。
4. **好调依赖换算**（「好调的N%数值变为打分上升/集中」）：好调 = condition_turns 整数
   （B8 曾排除，现已建模）→ CONVERSION_SOURCES 加 `好调:parameter_buff`；源段只作系数
   （不消耗好调回合），目标增量 int(condition_turns×N/100)。DSL score+=goodConditionTurns*0.3
   （初陣の証・佑芽）/ concentration+=goodConditionTurns*0.4（アニメイト装備）。

**双镜/兼容**：p_items.py（3 个 REDUCE frozenset / TARGET_BY_EFFECT / effect_value 读 turn /
PItemDelta.full_power_point_reduce / _apply_modifier_target 负层数）；lesson.py/expectimax.py
全力值减少双镜（纯增量默认 0 = 旧行为）；build_p_items.py CONVERSION_SOURCES 好调；
p_items.json 重建仅 **24 条记录**标注变化（逐条 diff 校验：11 源段 conversion_source +
11 目标 depends_on=parameter_buff + 13 reduce target 标注；ExamStaminaDamage 代码驱动无数据变化）；
**implemented 1067→1164/1849**（+97），依赖换算 65→76 段。

**留后续（证据充分但需新机制/真机，保持 no-op 如实记录）**：好调增加量增加
（ExamParameterBuffAdditive，setGoodConditionTurnsBuff 增益倍率接线）/ 元气增加无效
（ExamBlockRestriction，nullifyGenkiTurns）/ 不安（ExamBlockAddDown，uneaseTurns，delay:2）/
塔 gimmick（低谷/紧张/弱气/体力回复无效，参考无独立字段）/ 全力・强气效果卡打分
（setFullPowerEffectBuff/setStrengthEffectBuff，卡级 modifier）/ 日文好調の%分（眠気卡条件、
无中文）/ ExamParameterBuffReduce（produce/buff_consume 触发未支持）。

**评测零 P 道具结算**：`sim_produce.py`（培育模拟）**完全不引用 p_items**（grep 0 命中）→
sim_engine_ab 评测路径无 P 道具。重标定（seed 9000/9100 各 16 局 rules/expectimax budget 800ms）
改前（git stash）/改后逐局对照——**64 局逐位相同（差异=0）**；expectimax 仍显著强于 rules
（Δ+372.2 / +219.1 评价点，15/1/0 与 11/5/0，C+ 100%，0 blocked / 0 error），B3 结论保持。
**旧 B11 数据/模型是旧规则口径，全保留不覆盖**（阶段2 重采新 seed 块练新批再新旧对比）。

**验证**：`tests/test_p15_reduce_condition.py` **38 条**（分类/数值/apply_passive/PItemDelta/
LessonSim/双镜/数据层 no-op 记录）+ 既有断言随规则更新（test_p13/test_p14 implemented
1067→1164）；全量 pytest **1503/1（1504 收集 / 94 文件）**；ruff 通过；基线 ①③④⑤ 不变。
见 [RULES_REFERENCE §5.8](RULES_REFERENCE.md) / HANDOVER 二·补四十九。

### P1-6. 阶段1 第六批：T7②③ 离线可靠性工程（纯函数状态重放 + 自动复盘页 + 标注转回归闭环）✅ 2026-11-24 完成
- **目标**（HANDOVER_NEXT §4 T7②③ / §8.0 P1-6，用户确认 A 顺序）：照 hiro 三原则补剩余两条——
  ② 纯函数状态 + 离线重放（`run_record` 雏形 → 同观测序列→同状态→可逐步比对）；
  ③ 自动复盘页（每局逐回合页 + 人工标注转回归用例；C1 已有 step_trace.jsonl + replay_steps.py，
  差自动页面/标注闭环）。**不改考试规则、不作废 B11 数据**（纯可靠性工程）。
- **DoD**：新增测试（假观测序列重放/逐步比对）✅ 61 条；一局自动复盘页样例 ✅
  [docs/review_sample.html](review_sample.html)；LIVE_RUN.md 更新 ✅ §2.1。

**落地（2026-11-24，纯增量）**
- **⑨ 纯函数状态重放**：新 `src/gkagent/data/run_replay.py`——`apply_event(state, event)`
  无副作用（深不可变 `RunState`/`ExamSnapshot`/`FinalSnapshot`，不读时钟/文件/随机数）；
  事件 5 类 action/backfill/lesson/exam/final（与 note_* 一一对应；考试类型在 `exam_kind`，
  不跟事件类型 `kind` 混）；null 观测不抹已知值（最后已知值优先，与补写语义一致）；
  未知事件种类显式 ValueError（不静默丢观测）。`replay` 逐事件快照 + `fingerprint`
  sha256（同序列两遍重放逐位相等）+ `compare_replays` 逐步比对（首个分歧步 + 逐字段差异 +
  长度差）+ `legacy_events` 旧格式汇总确定式重建 + `consistency_check` 三方对账
  （events 重放 vs 旧格式重建 vs 记录汇总；`missing_fields`/`lesson_unread` 是观测级计数，
  合并视图不可比，排除在对账外只作展示）。`RunRecorder` 增量 `events` 有序观测日志
  （每个 note_* 追加、随 flush 原子落盘；**旧格式文件续跑先把汇总重建成日志再续编号**，
  重放覆盖整局）；note_final 日志记**兜底前**原始读数，重放独立重兜底——记录器/重放器
  互为独立实现，漂移可被抓（单测实证：暂存覆盖丢分/汇总篡改都能定位）。
  新 `scripts/replay_run.py`：逐事件状态推进 + 终态摘要 + 三方对账；`--verify` 退出码=DoD
  （两遍指纹相等 + 对账一致）；`--compare` 两条序列逐步比对；`--json` 机器可读。
- **⑩ 自动复盘页 + 标注闭环**：新 `src/gkagent/report/review_page.py`——`build_review_html`
  纯函数渲染自包含 HTML（同输入同输出、全量 HTML 转义、内嵌 JSON `<`/`>` Unicode 转义防逃逸）：
  周行动逐回合表（重复观测黄底/null 灰显）/ 考试表 / 结算 / 重放一致性（指纹+三方对账）/
  观测事件日志 / C1 逐步轨迹表（lost/failed/stuck 红底；合成轨迹显著 banner）/ 标注工具栏。
  行内标注 verdict（ok/bad/unsure）+ 评论 + expected（k=v;k=v），localStorage 自动保存
  （键含指纹前 8 位不串局），导出 `annotations_<ep>.json` / 导入 / 清除。
  新 `src/gkagent/report/annotations.py`：`parse_expected`/`normalize_annotations`（坏 schema
  显式报错）/`cases_from_annotations`（**verdict=bad 且带 expected** 才转用例：周/考试/结算
  修正 → 追加观测事件重放**整态冻结**；逐步修正 → `summarize_traces` 分类结论冻结）/
  `merge_cases`（按 id 去重合并）。新 `scripts/review_page.py`（CLI 生成）+
  `scripts/annotations_to_regression.py`（标注 JSON → `tests/fixtures/review_regressions.json`，
  原子写、幂等）；`tests/test_review_regressions.py` 逐条重算比对（期望在转换时冻结，
  被测代码不给自己出题）。**auto_produce 局末自动生成**（`[review]` 日志行 + summary
  `review_page` 键；best-effort，失败只留痕不影响收尾/退出码）。
- **样例**：[docs/review_sample.html](review_sample.html)——记录 = 真机 ep-rule1（bot 最好
  C+/5992，真实数据）；轨迹 = 合成演示 6 步（本局跑在 C1 之前无真机 step_trace，页面
  `trace_source=synthetic-demo` 显著标注，不当真机数据引用）。夹具 2 条演示用例
  provenance=synthetic-demo（演示闭环，非真机 ground truth；真机标注后追加真实案例）。
- **验证**：`tests/test_run_replay.py` 38 条 + `tests/test_review_page.py` 20 条 +
  `tests/test_review_regressions.py` 3 条 = **61 条**；ruff 通过；全量 pytest
  **1564/1（1565 收集 / 97 文件）**；基线 ①③④⑤ 复跑不变。**sim/ 零引用
  run_record/run_replay/report（grep 0 命中）→ 模拟器/评测零影响，无需 sim_engine_ab 重标定**；
  旧 B11 数据/模型全保留。真实记录端到端：ep-kinami1/ep-rule1/ep-verify1 `--verify` 全一致；
  ep-t1-g 卡屏局 28 次重复观测被重放显式 surfaced。一次性脚本 data/_p16_*.py 不提交。
- 细节见 HANDOVER_NEXT §4 T7 / §8.0 P1-6 / LIVE_RUN §2.1 / HANDOVER 二·补五十。

### P1-7. 阶段1 第七批：P 道具后续批次（好调增加量增加 / 元气增加无效 / 不安 / 通用延迟生效，纯离线）✅ 2026-11-24 完成

**来源**：HANDOVER_NEXT §8.0 多会话路线图 P1-7（用户确认 A 顺序，本会话选定 P 道具批次）。
**DoD**：参考引擎证据（BSD-3 有据才做、不猜）+ 代码 + 单测 + RULES_REFERENCE 核验表更新 +
sim_engine_ab 重标定（改前/改后逐局对照）。**bounded batch**：挑证据充分、离线可定、低风险段。

**本批四块**（语义全部经 BSD-3 参考引擎 + 主数据 + 参考 DSL `p_items.csv` 三重核实）：

1. **好调增加量增加 `ExamParameterBuffAdditive` → condition_gain**（4 段）：参考
   `resolveGoodConditionTurns` 先加 additionBuffs 再 `×(1+Σ goodConditionTurnsBuffs)`
   （`setGoodConditionTurnsBuff`），乘在获得量上向上取整；卡渠道（先加 condition_additive
   再乘）+ P 道具 parameter_buff 渠道双镜。DSL 夜闇の星 313/314 setGoodConditionTurnsBuff(0.5,4/5)。
2. **元气增加无效 `ExamBlockRestriction` → nullify_genki_turns**（9 段非塔）/ **不安
   `ExamBlockAddDown` → unease_turns**（2 段非塔）：参考 `resolveGenki` `if(nullifyGenkiTurns)
   return;` / `if(uneaseTurns) genki*=0.67`（向上取整）；两者 ∈ EOT_DECREMENT_FIELDS（回合末 -1）
   + DEBUFF_FIELDS（nullifyDebuff 拦截施加）；N 在 turn 列。`genki_gate` 纯函数双镜共用。
   DSL いたずらパペット 149/150、初陣の証・美鈴 302/303、雨上がりの花 253/254（delay:2）。
3. **固定元气分离 `ExamBlockFix` → fixed_vitality**（12 段）：参考 resolveFixedGenki 直接进元气，
   不吃干劲、不受无效/不安闸门影响（与 ExamBlock genki+= 区分）。
4. **通用延迟生效机制**（34 段标注）：主数据 yaml `e_effect-exam_effect_timer-NNNN-…` 包装 ↔
   参考 DSL 嵌套 `at:turn`/`delay:NNNN-1`（EffectManager.decrementDelay 每回合末 -1，到 0 的
   下一回合开始结算）。触发回合登记增量（条件/次数当时求值），到点结算。**修正已实现道具时序**：
   おさぼりタオル nullifyDebuff 下回合（P1-4 原立即）/ 美铃干劲 3 回合后 / 温存变更类下回合等。

**双镜/兼容**：p_items.py（4 frozenset / TARGET_BY_EFFECT / effect_value 读 turn /
PItemSpec.delay_turns / PItemDelta 新字段 + freeze/thaw）；lesson.py/expectimax.py（genki_gate +
condition_gain 双渠道 + 延迟队列 + canonical + 快照往返）；build_p_items.py（_timer_delay）；
p_items.json 重建 **49 条记录**变化（15 新目标 + 34 延迟标注，部分重叠；塔 ∞ 段 value=0 仍 no-op）。
implemented **1164→1179/1849**（+15），modifier 409→442。

**保持 no-op 如实记录**：塔 gimmick（低谷/紧张/弱气/体力回复无效，参考引擎无独立字段、全部 CSV
零用法）/ 塔 ∞ 段（values 恒空 value=0）/ 全力・强气效果卡打分（per-card g.score 成长，values 恒空，
DSL まあるい春色 target:effect(fullPowerCharge){g.score+=11}）/ 日文好調の%分（天生的才能眠気卡
张数条件、无中文）/ ExamParameterBuffReduce（produce/buff_consume 触发未支持）。

**评测零 P 道具结算 / 重标定**：`sim_produce.py` 完全不引用 p_items（grep 0 命中）；genki_gate
在 nullify/unease=0 恒等、condition_gain 无 modifier 恒等 → 非 P 道具路径不变。**sim_engine_ab
重标定：改前（git stash）/改后 64 局逐位相同（差异=0）**——seed 9000/9100 各 16 局 rules/expectimax
budget 800ms，逐局非时间字段全等（data/_p17_ab_compare.py，不提交）；expectimax 仍显著强于 rules
（Δ+372.2 / +219.1 评价点，15/1/0 与 11/5/0，C+ 100%，0 blocked / 0 error），B3 结论保持。
**gkbench 94 唯一 loadout id 无一件 timer/新目标道具** → local_bench 零触达。
**旧 B11 数据/模型是旧规则口径**（用户指定全保留不覆盖）：阶段2 重采新 seed 块练新批再新旧对比。

**验证**：`tests/test_p17_genki_condition_delay.py` **48 条** + 既有断言随规则更新
（test_p13/p14/p15 implemented 1164→1179、test_p15 两个 deferred-noop 改断言已实现、
test_p_items_b9 ExamBlockFix 改断言 fixed_vitality）；ruff 通过；全量 pytest
**1612/1（1613 收集 / 98 文件，218.08s）**；基线 ①③④⑤ 不变。
见 [RULES_REFERENCE §5.9](RULES_REFERENCE.md) / HANDOVER 二·补五十一。

### P1-8. 阶段1 第八批：P 道具剩段 bounded batch（日文好調の%分 / 天生的才能，纯离线）✅ 2026-11-24 完成

**来源**：HANDOVER_NEXT §8.0 多会话路线图 P1-8（用户确认 A 顺序，本会话选定 P 道具剩段）。
**DoD**：参考引擎证据（BSD-3 有据才做、不猜）+ 代码 + 单测 + RULES_REFERENCE 核验表更新 +
sim_engine_ab 重标定（改前/改后逐局对照）。**bounded batch**：挑证据充分、离线可定、
**映射既有机制**的低风险段（不贪多；per-card 成长等新机制超出范围则 no-op 留后续）。

**本批只做一块**（语义经 BSD-3 参考引擎 + 主数据 + 参考 DSL `p_items.csv` 三重核实）：

1. **日文好調の%分（天生的才能 pitem_01-3-346-0/1）→ 好调依赖换算**（2 段）：参考 DSL
   天性の才能 493/494 `at:afterCardUsed { if:countCards[hand & baseId(23)]>=1 {
   score+=goodConditionTurns*0.3 } }`（+ 变体 `genki+=1; score+=goodConditionTurns*0.5`）。
   眠気卡张数条件 baseId(23)（skill_cards.csv 23 眠気 trouble ↔ card_table/card_meta 睡意
   `p_card-00-acc-0_002`，ja_aliases 眠気→睡意）**已由 B10 zone_count 结构化解析**（hand≥1）；
   本批只补「好調の%分」→ parameter_buff 的**日文换算源标注**（`CONVERSION_SOURCES_JA`），
   结算复用 P1-5 依赖换算渠道（目标增量 `int(condition_turns×N/100)`，源段只作系数不消耗好调回合）。

**落地（纯数据层，sim/ 零改动）**：build_p_items.py（CONVERSION_SOURCES_JA /
_CONVERSION_SOURCE_TEXT_JA「Xの%分」/ annotate_effects 日文分支）；p_items.json 重建
**仅 2 条记录**变化（逐条 diff 校验：天生的才能 -0/-1 源段 role=conversion_source/percent1 移除，
ExamLesson 目标 depends_on=parameter_buff + percent1=30/50）。换算/zone_count 双镜 P1-5/B10 就绪，
sim/lesson.py、sim/expectimax.py、sim/p_items.py **零改动**。implemented **1179→1181/1849**（+2），
依赖换算 76→78（好调换算目标 11→13：9 ExamLesson + 4 ExamLessonBuff）。

**保持 no-op 如实记录（证据充分但需新机制/真机，留后续）**：
- **全力・强气效果卡打分**（ExamFullPower/ExamConcentration「打分值增加+N」**43 段**）：参考 DSL
  `target:effect(fullPowerCharge) & active { g.score+=11 }`（まあるい春色 234/235）= **per-card
  g.score 成长**（按效果组过滤，resolveScore growth[g.score]），非 setFullPowerEffectBuff（那是
  全力/强气指針倍率，另一机制）；主数据 values 恒空需**逐卡证据表 + per-card 成长新机制**
  （同 P1-3 target:held 成长），超出 bounded 范围，本批不做。
- **塔 gimmick**（低谷 ExamGimmickSlump 11 / 紧张 ExamGimmickLessonDebuff 6 / 弱气
  ExamGimmickSleepy 6 / 体力回复无效 ExamStaminaRecoverRestriction 6 = **29 段**）：参考引擎
  **无对应独立字段**（constants.js ALL_FIELDS 无 slump/tension/sleepy/staminaRecover；全部 CSV
  零用法），语义需真机核实；gkbench loadout 无 tower → 评测零触达。
- **ExamParameterBuffReduce**（好调减少 **3 段**）：触发 produce_start_lesson / buff_consume
  未支持（buff_consume 依赖强化状态花费卡机制，P1-4 ⑦ 已记卡模型不承载 buff 花费）→ 无落点 no-op。

**评测零 P 道具结算 / 重标定**：`sim_produce.py` p_items 默认 ()、`sim_engine_ab.py` 不注入
P 道具（grep 0 命中）；本批又只改数据层标注（sim/ 零改动）→ 非 P 道具路径不变。**sim_engine_ab
重标定：改前（git stash）/改后 64 局逐位相同（差异=0）**——seed 9000/9100 各 16 局 rules/expectimax
budget 800ms，逐局非时间字段全等（data/_p18_ab_compare.py，不提交）；expectimax 仍显著强于 rules
（Δ+372.2 / +219.1 评价点，15/1/0 与 11/5/0，C+ 100%，0 blocked / 0 error），B3 结论保持。
**天生的才能是 sense pIdol 158 道具，不在 gkbench hif loadout**（94 唯一 id 无 346）→ local_bench 零触达。
**旧 B11 数据/模型是旧规则口径**（用户指定全保留不覆盖）：阶段2 重采新 seed 块练新批再新旧对比。

**验证**：`tests/test_p18_ja_condition_conversion.py` **32 条** + 既有断言随规则更新
（test_p13/p14/p15/p17 implemented 1179→1181、test_p15 noop 670→668 / depends_on 76→78 /
好调换算 11→13、test_p15 日文 deferred-noop 改断言已实现）；ruff 通过；全量 pytest
**1644/1（1645 收集 / 99 文件，214.43s）**；基线 ①③④⑤ 不变。
见 [RULES_REFERENCE §5.10](RULES_REFERENCE.md) / HANDOVER 二·补五十二。

---

### P2. 阶段2：重采 + 练学生 r11 + 新旧对比 + r12 降档 + r13 完整渐退（r13 入库为生产）✅ 2026-11-24 完成

> 用户 2026-11-24 选定阶段2（A 顺序，不用再问）。🔒 旧数据/模型全保留不覆盖不删（用户指定）。
> 详见 [HANDOVER_NEXT §8.0 阶段2](HANDOVER_NEXT.md) / [EXPECTIMAX「B11 r11」](EXPECTIMAX.md) /
> [R9_ANALYSIS §10](R9_ANALYSIS.md) / HANDOVER 二·补五十三。

- **前置（重标定 + 参照臂新规则重评，门基线重定）**：阶段1（P1-1…P1-8）改规则 → 旧 B11 数据/模型旧规则口径。
  `sim_engine_ab` 重标定 seed 9000/9100 与 P1-8 **逐位一致（0/32）**，expectimax−rules Δ+372.2/+219.1；
  参照臂 v6/v1/beam/r9/r10 按新规则重评（500 局）：**small 规则零分移**（v6 98.640/v1 98.062/beam 96.488 不变）、
  **large 分移 ±2**（v6 285.8→287.818、r9 315.4→313.446、r10 314.9→313.612、beam 301.3→301.612）。
  新门基线：large v6 287.818/beam 301.612；small v6 98.640/v1 98.062（旧 98.6/98.1/305.3 不可直接比）。
- **P2-0 重采**（v6 argmax，新 seed 块新文件，与评测段及旧块错开）：`ei_r11_selfplay_small.npz`
  small 10000 局 145565（1100000+，std 12.172）+ `ei_r11_selfplay_large.npz` large 5000 局 128103
  （1200000+，std 24.301）+ `ei_r11_demos.npz` v1 示范 3600 局 51985（1300000+，0 教师-SKIP）。
- **P2-1 练 r11**（`--upsample-small 2` 纯增量 + `--norm-by-scenario`，13 条回归测试默认逐位不变）：
  467527 行（small ×2=291130 / large 128103 / demos 48294），能量份额 small **65.6%**（§6 候选② ~66% 吻合）；
  192×96/1200ep，val 排序 0.822。**500 局双门**：large r11 313.92 vs v6 287.82 **+26.10 CI[+23.06,+29.14] PASS**
  （vs beam +12.31，新鲜块 6000 +20.81）；small r11 98.648 vs v6 98.640 **+0.008 CI[−0.253,+0.269] 不回退 ✅**；
  vs v1 **+0.586 CI[+0.245,+0.927] 原门保持 ✅** → **复合门首次双过 → 入库**：`data/_r11_promote.py`
  程序化门校验（参照臂逐位 6/6）→ `ei_policy_v6.json` 替换 r11 权重（1004369 字节，meta.production 溯源
  revision r11-new-rules-upsample-small；旧 r6 权重保留 out/ei_r6_v6_mix.json）。
- **P2-1b 新旧对比**（`data/_r11_compare.py`，同 seed 配对分解）：small 规则零分移；large 规则分移 ±2；
  large headline r11 vs 旧 v6 **+28.08 = 学生改进 +26.10（93%）+ 规则分移 +1.98（7%）**；r11 small 显著优于
  r9（+0.426 CI[+0.159,+0.693]，修复 r9 回退）、large 与 r9/r10 中性（增益保持）。**学生改进真实、规则分移很小**。
- **P2-2 r12 降档 15→0**（2026-11-24，用户选定 ② r12 续 → A；单变量=去 v1 示范，零代码改动）：r11 配方
  `--teacher-frac 0` 无 `--demos` 纯自对弈重训（419233 行，能量 small 69.4%）。**small500 r12−v6 +0.016
  CI[−0.286,+0.318] 中性（目的门「显著超 v6」未达）**；large500 +26.852 CI[+23.834,+29.870] 主门 PASS、
  vs v1 +0.594 保持、r12−r11 small/large 均中性 → **不入库，生产保持 r11**。**通道 3（v1 拉扯）正式关闭**
  （去教师无显著影响，与 §9 一致）；small 平台期非教师相关。不硬凑显著；剩候选③两段式微调/探索增量非必需。
  详见 EXPECTIMAX B11 r12 / R9_ANALYSIS §11 / HANDOVER 二·补五十四。
- **P2-3 r13 完整渐退迭代**（2026-11-24，用户追问「逐渐调占比、让最新当老师」后选定 A；教师←r11，占比渐退
  0.15→0.075）：采 r11 argmax 新自对弈 small 145578（1400000+）/ large 135679（1500000+，**均分 317.8≫v6 288.9**）
  + r11 示范 51912（1600000+），449639 行（能量 small 66.4%/large 31.0%/demos 2.6%），val 排序 0.829。
  **门基线换 r11**。**500 局复合门（参照臂逐位 6/6）**：large500 r13−r11 **+2.882 CI[+1.309,+4.455] 主门 PASS**
  （vs v6 +28.984、vs beam +15.190）；small500 r13−r11 **−0.028 CI[−0.265,+0.209] 不回退**；vs v1 +0.558 保持
  → **复合门通过 → 入库 ei_policy_v6.json=r13**（旧 r11 保留 out/）。**「让最新当老师」对 large 有效**（更优 large
  数据→再超）；**small 维持蒸馏天花板**（三重佐证）。目的（small 显著超 r11）未达但不门。详见 EXPECTIMAX B11 r13 /
  R9_ANALYSIS §12 / HANDOVER 二·补五十五。
- **DoD**：代码（--upsample-small）+ 单测（13 条 + wiring 更新）+ 重标定/重评数字 + 文档更新；
  旧 B11 数据/模型全保留；不改 SKIP 红线、禁静默回退 rules；全量 pytest **1657/1（1658 收集 / 100 文件）**，
  基线 ①③④⑤ 不变。**F public-safe 入场券拿到**（首个 small+large 双过学生）。
- **下一步**：r13 完整渐退入库（生产，large 显著超 r11）+ r12 通道 3 关闭 → **阶段3 真机 T3→T1→T2**
  （+T6/D1 补采 + E0 + C1 真机验收，net 第四臂用入库 r13）。可选 r14 教师←r13 继续渐退（large 或再进、small 预期仍中性）；
  如仍需 small 显著超老师剩候选③两段式微调/探索增量（非必需）。

---

## 阶段 C：可靠性（离线）

### C0.（可选，2026-11-22 新增）采集/更新可靠性经验吸收 ✅ 2026-11-22 完成
- 从作者整合包（[LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)）吸收游戏更新/
  协议变化/代理/TLS 的排障判据：`x-error-code=2004`、协议 hash/master 表结构判据、
  `http1_bridge` 丢失客户端版本/平台/会话头、TLS 回退直连、CA 精确指纹、系统代理恢复、
  只停本目录服务。写进 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) 新小节 +
  [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md) 补充；只写结论，不拷代码。
- **DoD**：检查清单（触发条件→症状→处理→参考）落文档；pytest 不变。预算 ~10–20k token。

**落地（2026-11-22，纯文档、不碰真机/代码）**
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) 新增 **§四「游戏更新 / 协议 / 代理 / TLS 断链
  （外部经验吸收，2026-11-22，本项目待验证）」**：先给「先分清操作再读错误码」（更新 1–5 /
  启动 1–7 / 官方 2004 / Windows / gRPC / HTTP 码），再给 **13 条清单**（触发条件 → 症状/证据 →
  处理 → 参考）：① System/Check 200 空体 + `x-error-code=2004`=客户端太旧；② DMM 更新还原 hook
  DLL（模式判定别用 SameFile）；③ 协议变更关键词 + 停止自动更新；④ master 清单结构/长度/
  SQLCipher 判据（64-hex version、pack 名/文件名/key/size/URL host 规则、pack≥100）；⑤ 版本哈希
  不透明（不按文件时间判新旧、单份回退槽、别动 Master_Get 夹具）；⑥ `http1_bridge` 丢客户端
  版本/平台/会话头 + 不透传业务错误头 + 缺 `grpc-status` 当成功；⑦ `Auth/Login` `req_body_len`
  865 正常 / 833 → 1003、`x-p-s` 需 DMM 常驻；⑧ 上游端口写死 7897 → 10061/`OFFLINE-FALLBACK`；
  ⑨ 停服务顺序（先还原系统代理再停进程，反序 = 全机断网事故）；⑩ CA 精确指纹+有效期、
  TLS 回退直连两条都校验证书/不重复 POST；⑪ 代理残留不被后台监视器覆盖/更新后自清理；
  ⑫ 诊断收集与脱敏（网络诊断只做握手+代理/证书元信息）；⑬ 更新/采集互斥与「停止服务」优先级。
  另加 **§4.2 与我们采集链路对应表**（1.3–1.9 已踩过的 vs 本条待验证的）与通用教训。
- [CAPTURE_PIPELINE.md](CAPTURE_PIPELINE.md) 新增 **「游戏客户端大版本更新后自检」8 步**
  （先 DMM 更新 → 核对 hook/traffic → 证书/TLS → 上游代理 → 票据 → 协议/主表变化即停 →
  `build_exam_setup`+`verify_exam_wiring` 重建核对 → 自清理），并修正「离线培育/作者暂不做」
  的过期说法（11-22 包已有 `produce_runtime.py`，无考试结算，仅 E0 候选）。
- [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md) §5 同步 B7/C0 完成、剩 E0。
- **DoD 对照**：检查清单落文档 ✅；不新增依赖/数据 ✅；纯文档 **pytest 仍 1054/1**（复跑见
  HANDOVER 二·补三十）；一次会话只做 1 个任务 ✅。细节见 HANDOVER 二·补三十。

### C1. 执行层可靠性（参考 GKMSMAA 架构，**自写代码不拷贝**）✅ 2026-11-23 完成（纯离线代码+单测；真机验收留阶段 E）
- tap 确认/重试（tap 丢失、对话未开、picker 选牌、同屏循环）；
- 提权检查（游戏 elevated / 本进程 non-elevated 的失败提示）；
- 动作前预算下一帧（hiro 原则）、每步可复盘（日志已有 `eng/fallback`，补动作理由）；
- DoD：对应失败场景单测；真机日志能复盘每一步。

**落地（2026-11-23）**
- **新模块**：`src/gkagent/runtime/tapguard.py`（`TapExpectation` 下一帧预算：
  change/dialog-open/dialog-gone/overlay-open/overlay-gone/any + 锚点词 + 点击前签名；
  `TapGuard` 互验：满足=confirmed、**画面已推进=moved 重新决策绝不重试**（rev254）、
  同屏未生效=1s 后同坐标 retap≤2 次、预算用尽=lost 上报**绝不静默 SKIP**、
  加载/暂停帧 postpone 重启时钟（rev135）；`PickerGuard` 两段式选牌：选中后只重试确认
  不重点卡位、selected=None 保守按已选中、failed 重置后重新选卡）；
  `src/gkagent/device/privilege.py`（纯判定矩阵 + Win32 探测：IsUserAnAdmin /
  OpenProcess+TokenElevation，denied=令牌读不到按 blocked；unknown 只告警不拦；
  假 API 可注入）；`src/gkagent/runtime/trace.py`（StepTrace/TraceLog/format_trace/
  summarize_traces）；`scripts/replay_steps.py`（离线复盘 CLI：--episode/--anomalies/--json）。
- **接线**：`TickResult` 补 point/reason/expect（向后兼容）；`decide()` 每击自动预算
  （弹窗确认/回合结束「是」/通信错误重试=dialog-gone，其余=画面应变化）+ 关键分支动作理由；
  card-reward（4.6）接 PickerGuard（同屏只重试「领取」，预算用尽才重新选卡）；
  `auto_produce` 启动提权检查（blocked→`elevation-blocked` failure+return 2，日志首行 `[priv]`）、
  非课程分支每步先互验再决策（retap/lost/confirmed/moved；**连续 3 次 lost 止损停局**）、
  回合结束「是」预算 dialog-gone、饮料换 `attempt_drink`（对话未开重试槽位≤2 次，
  失败写 `drink-dialog-lost`）、每步 `data/step_trace.jsonl`、局末 `[tap]` 汇总。
- **DoD 对照**：失败场景单测 68 条（4 个新测试文件：tapguard/privilege/trace/wiring）✅；
  每步日志含 reason+预算+互验结果，`replay_steps.py` 离线逐步复盘 ✅（真机验收留阶段 E）。
  用户规则不变：SKIP 只在所有牌付不起、禁静默回退 rules、lost 升级=停局修 root cause。
- **如实记录**：picker 选中态无可靠离线探针（未归档真机奖励选卡帧），selected=None 保守处理，
  阶段 E 可补读回；runas 自动提权启动未做（约定管理员终端手动跑，先给明确提示）；
  ~~T7 剩余（纯函数状态重放/自动复盘页）不在本任务~~ ✅ **P1-6 已完成（2026-11-24）**。
- **测试/基线**：全量 pytest **1223 passed / 1 skipped（1224 收集 / 83 文件）**；ruff 通过；
  基线 ① 4/4+3/3、③ 86/86+24/24、④ 36/36+3/3+29/29+beam 28、⑤ 366/384 全部不变。
- 细节见 HANDOVER 二·补三十六 / HANDOVER_NEXT §8。

---

## 阶段 D：数据（离线准备，真机时执行）

### D1. 采集扩展
- 目标：① 同卡组多局（T2 A/B 用）；② 牌组含额外 RNG 机制卡的考试（建 panic/search/generate/move 数据）；
- 产出：`traffic.jsonl` / `out/exam_setup*.json` 入私有存档（不入库）。

---

## 阶段 E：真机（A–D 全做完后再做）

### E0.（可选实验，2026-11-22 新增）离线培育测试台 ⬜
- **目标**：验证作者 11-22 整合包的离线培育（Selection Exam / produce-007）能否推进到
  **考试**；若可 → 作为 fresh buff 逐回合截图 / T1 UI 回归的**零账号风险**来源
  （考试机制与 produce 类型无关）。已知代码只处理 lesson/event/shop/rest，没有
  Audition/Exam 处理 → 很可能卡在考试日，本实验就是确认。
- **约束**：独立游戏副本（第 3 份），**勿动 `D:\Games\Gakumas` 和 `C:\GakumasLocal`
  采集安装**；先问用户是否投入（要碰 GUI/DMM）。
- **DoD**：明确结论（能/不能到考试，卡在哪屏/日志/截图证据）；能则标注能服务哪些离线
  素材需求；更新 [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md) 与 HANDOVER。
- 说明见 [HANDOVER_NEXT §4 T9](HANDOVER_NEXT.md) / [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)。

### E1. T3 实战验收
- 开采集 → bot 起局 → 考试中 `build_exam_setup --current` → 验收：
  `[exam-plan] locked_turn=2~3`、`verified == 实战回合数`、无错误牌序；
- DoD：真机日志 + HANDOVER/RUNS 记录。

### E2. T1 整局验收
- 严格引擎（expectimax）、`--ignore-user`、`--max-minutes 30`、禁静默回退；
- DoD：≥ C+、≤20 分钟、无"有牌却 SKIP"、无 `[engine][BLOCKED]`；写 RUNS。

### E3. T2 三引擎真机 A/B
- 同卡组/同 setup：rules（仅对照）/ expectimax / beam+全知，各一局；
- 记录考试分/评价/时长/fallback；结论写 EXPECTIMAX.md。

---

## 阶段 F：gkbench 算法对比（最后）

> 已确认：就是 **gkbench（`hiro.matto.top/gkbench`）**；本地克隆 `data/bench_repo`（MIT）。
> **2026-11-22 用户已登录 gkbench，可以下载公开的「固定种子题」（开发集种子，含 `loadout.seed`
> 和起点核对 `check`）——这改变了 F 的做法**：以前只能拿题模板（无种子）本地跑，现在可以
> 用官方种子做**独立交叉验证 + 理论上限分母**。

- **规则红线**：gkbench ranked **禁止 seed/牌序**（ranked 用保密种子，只托管跑、算法只看画面）；
  我们能提交的是"只看 UIObs 的算法"（rules/expectimax/学习模型），**不能**带 MITM/known_draw；
  下载到的固定种子题（开发集）**只用于本地跑/理论上限当分母**，官方页面也不把它单列排行
  （`privileged` = 看种子的理论上限，只作分母）。
- **F0（先做）✅ 已完成（2026-11-22）：官方种子交叉验证 + 口径校准**
  1. 下载固定种子题/开发种子（`/api/sets/<set>/seeds` + `check`）；公开 API / 批量下载工具 /
     参考分见 [GKBENCH.md](GKBENCH.md)（`scripts/bench_download.py`）；
  2. **用洗牌模型从 `seed`+牌组预测开局手牌，和 `check.hand` 逐张对照** → `scripts/verify_gkbench_shuffle.py`：
     **286/384（74.5%）→ 366/384=95.3% 精确 / 97.4% 逐张**（initial 按 base id 含强化变体 +
     initial_add；**npc 按 idol 卡**：本戦 jsna 4 人制/fktn 2 人制/其余 3 人制；round 兜底），
     選抜 100%、逐题 311/329 全中；剩余 18 组全是考试开始加卡机制（`ExamInitialDeck` 15 +
     kllj 开局 +1 手牌 3），无一洗牌错误；
  3. 用 `check` 的 `turn/score/stamina/rules/commit` 校准起点：turn=1、score=0、
     stamina 96.1%=starting_stamina（15 组差=偶像卡 P 道具考试开始附魔常量，基准复算用
     `check.stamina` 覆盖）、rules=55（commit `f4d9e6e6148d`）；见 GKBENCH §4.5 / HANDOVER 二·补二十四；
  4. ~~对照榜上参考分/oracle 分母~~ → 留给 F1/F2（本节任务 4）。
- 任务：
  1. 读 `data/bench_repo`（MIT 本地克隆）确认提交协议（动作 `p<i>/d<i>/e/s<i,j>`、UIObs 字段、裁判口径）；
  2. 写一个 **public-safe 适配器**（自包含、不用 seed、不读本公司私有数据），本地裁判跑分；
  3. 对齐公开数字：UIHorizon ≈631k（0.511×oracle）、UINet ≈579k（0.455×）、官方 AI ≈233k（0.213×），
     oracle 基准 ≠ 最优（1.45M 为多起点 best-known 分母）；
  4. 若托管提交（需账号/token/规则确认）：提交并记录 host 返回；否则写本地对照报告并注明口径差异；
- DoD：本地/托管的同口径分数 + 一页对照表（我们 vs UIHorizon vs UINet vs 官方 AI；标注是否用 seed）。

---

## 阶段 G：收尾

- 更新 HANDOVER/EXPECTIMAX/RULES_REFERENCE/RUNS/PROVENANCE；`pytest` 全绿；提交 + 私有仓库 Push；
- 情报更新（群/论文/封堵动态）；对外继续不公开细节。

---

## 新会话开场白（复制）

```
工作目录 D:\Games\gakumas-agent。
读 docs/INDEX.md → docs/WORKPLAN.md（总计划）→ docs/HANDOVER_NEXT.md §2 跑基线（四条必跑 + ⑤ 可选），
然后按 WORKPLAN 的 阶段 B→C→D 离线推进；全部离线做完后再做 阶段 E 真机（T3→T1→T2），
最后 阶段 F 去 gkbench 比算法（ranked 禁 seed，只能交不看 seed 的算法）。
用户规则：SKIP 只在真没体力；禁止静默回退 rules；真机整局 --ignore-user。
A1（OCR 换日文模型）已于 2026-11-22 完成（官方 PP-OCRv6；见 WORKPLAN A1 / HANDOVER 二·补十四）。
A2（F#42 课程硬打必须得分）已于 2026-11-22 完成（HUD 语义 + 每回合 1 张 + 硬打保分；
见 WORKPLAN A2 / HANDOVER 二·补十五）。
A3（F#43 结果页空转）已于 2026-11-22 完成（真根因是日文饮料选择事件屏 + P 费标签被当飘字；
见 WORKPLAN A3 / HANDOVER 二·补十六）。
A4（离线回放素材）也已完成（8 张真机帧归档 + 9 条真机帧回放测试 + scan_frames 挑帧工具；
见 WORKPLAN A4 / HANDOVER 二·补十七）。
A5（T3 离线预演）也已完成：`scripts/verify_exam_plan_offline.py`——最新场 3 候选第 2 回合锁定
config_turns=12（真值 12），四场 sweep 全部 T1–T2 锁定且选对真值，候选收敛到 1、locked_turn≤3；
见 WORKPLAN A5 / HANDOVER 二·补十八。
B1（T4 修正）已于 2026-11-22 完成：查出评测执行器 `_execute_plan` 白丢回合 bug；
修正后 60 局配对 beam unknown 164.0 / known 165.5 vs within 143.1（+20.9/+22.4，CI 全正；
决策门 114.6%/115.7% PASS），受控 frontier 叶子中性；见 WORKPLAN B1 / HANDOVER 二·补十九。
B2（全知数据训练 MLP 叶子）已于 2026-11-22 完成：B1 修正 harness 上，beam 全知自对弈 26.5k
叶子样本训练 104 维 MLP（val r²=0.943）；确认段 120 局配对 beam 157.8 → 165.5（learned，
+7.7 CI[+4.2,+11.2]）/ 166.9（ensemble 0.5，+9.0），CLEAR 95→98.3%、PERFECT 33.3→50%；
within 用 learned 变差为已记录负结果（只对 engine=beam 有益）；见 WORKPLAN B2 /
HANDOVER 二·补二十 / EXPECTIMAX「B2 学习叶子」。
B3（T5 机制建模）已于 2026-11-22 完成：模拟器对齐真机「每回合基础 1 张 + 打完自动结束回合
+ SKIP 回 2 体力 + 取整 safeCeil」，`RULES_REFERENCE.md` 重写为逐条核验表，真机 39 回合
回合规则配对回归；重标定后 sim_engine_ab 里 expectimax 显著强于 rules（+342~+429 评价点，
B3 前是噪声内），B1 60 局 within 89.1→beam 95.7（+6.6，决策门 PASS），**B2 旧模型失效
（重测显著负）需按新规则重训**；全量 pytest 985/1（986 收集 / 72 文件）；见 WORKPLAN B3 /
HANDOVER 二·补二十一 / RULES_REFERENCE / SIMULATOR §11。
**F0 gkbench 官方种子校准也已完成（2026-11-22）**：`scripts/verify_gkbench_shuffle.py` 用 384 组
官方 `check.hand` 核洗牌模型 → initial 按 base id（含强化变体）+ initial_add、**npc 按 idol 卡**
（本戦 jsna 4 人制/fktn 2 人制/其余 3 人制）+ round 兜底 → **286/384 → 366/384=95.3% 精确、
97.4% 逐张**（選抜 100%；剩余 18 组全是考试开始加卡机制、无一洗牌错误）；起点校准
turn=1/score=0/stamina 96.1%=starting_stamina/rules=55；见 GKBENCH §4.5 / HANDOVER 二·补二十四。
**B4（T5① 审查倍率分段 + 联动惩罚）也已完成（2026-11-22）**：客户端真实公式（分数表分段折线 +
审查基准联动惩罚 + 单精度取整）落地成 `sim/exam_multiplier.py` + 主数据解析 `data/exam_bonus.py`，
模拟器按回合属性乘（含依赖分/回合末好印象），生产搜索改用屏幕真实倍率（日志 `attr=2.07`）；
真机采集局夹具：期中 Vo/Da/Vi **4.09/2.20/2.60×**、期末 **6.97/2.85/4.96×**（联动惩罚已对上）；
`tests/test_exam_multiplier.py` 21 条，全量 pytest **1006/1（1007 收集 / 73 文件）**；
见 WORKPLAN B4 / HANDOVER 二·补二十五 / RULES_REFERENCE §5.1。
**B5（T5② 熱意 + 温存解除）也已完成（2026-11-22）**：`sim/enthusiasm.py` 纯规则 + `LessonSim`/
`ExpectState` 熱意独立资源（出牌分加算、获得时 ceil、回合末清零/熱意延長）；温存解除
1 段 +5 熱意 / 2 段 +8 熱意 +5 固定元気 + 解除当回合 **+1 出牌次数**（同回合可重复、温存→全力
回合边界也触发）；卡牌效果 `ExamEnthusiasticAdditive/Multiple/TurnAdd` 与
`ExamMultipleEnthusiasticLesson`（本牌熱意適用倍数 ×2）接入 `sim_produce`（MODELED_EFFECTS 29→32）
与生产卡表；`tests/test_t5_enthusiasm.py` 16 条；全量 pytest **1023 passed / 1 skipped
（1024 收集 / 74 文件）**（见 HANDOVER 二·补二十六）。
未建模（P1-4 后更新）：~~のんびり指針、全力回合額外出牌/保留牌~~ ✅ P1-1 已建模；
~~handDecrease 抽牌修正、pride 自尊~~ ✅ P1-2 已建模；~~nullifyDebuff 拦截~~ ✅ P1-4 已建模
（P 道具侧 ExamAntiDebuff 11 段；卡侧 4 SSR 族/标量 DEBUFF_FIELDS 拦截留后续）；
~~hold 保留区来源、lockStanceTurns 指針固定~~ ✅ P1-3 已建模（13 族卡证据表 + fresh 锁下一回合；
剩 target:held 保留区卡成长 / holdCard P 道具来源）；**⑦ ExamBuffConsumptionAdd / countDebuffs
保持 no-op**（P1-4 评估：卡模型不承载 buff 花费 / 低下状態の数零使用，无落点）；
P 道具/附魔熱意来源、生产读屏未读熱意仍缺。
**B6（T5③ P 道具数据接入）也已完成（2026-11-22）**：新增 `src/gkagent/data/p_items_db.py`
（loadout `produce_item_ids` → `PItemSpec`，未知 id 显式上报、缺数据抛错）+
`sim/p_items.py` 新增 **`exam_start`** 触发时机（288 段素材）与
**`ExamPlayableValueAdd → extra_plays`**（51 段，取 `count` 列）；`LessonSim` 构造时
结算考试开始效果（先于 turn_start、额外出牌保第 1 回合）、`ExpectState` 镜像；
`local_bench` 从 gkbench 题模板的 `loadout.produce_item_ids` 接入（`--p-items auto/off`，
505 题 / 83 唯一 id / 72 已知 / 11 未知）；gkbench 提交从 `ctx.loadout`（公开配置，
不含种子）接入；离线 A/B（hif 30 题×2 seed）greedy **+128.9（+3.36%，CI[+9.5,+248.4]）** /
expectimax +149.6（+3.98%）；新增 29 条测试，全量 pytest **1051/1（1052 收集 / 76 文件）**。
仍缺：真机培育侧 P 道具列表（T6/D1 补采）、效果覆盖（已知 72 道具 131 段 spec 只实现
31 段）、主道具附魔/回忆（见 HANDOVER 二·补二十七 / RULES_REFERENCE §5.3）。
**2026-11-22 外部情报**：用户提供了作者新的四游戏整合启动器包（215 MB，11-22 构建）→ 已解包
静态分析，文档 docs/LOCAL_LAUNCHER_20261122.md（提交 ddf221f）。帮助属参考级（工程排障/更新
兼容经验、Produce API 语义、P 道具 47 条 id 清单；不能拿算分公式/替换采集安装/直接拷数据）。
由此新增候选任务 **T9：B7（P 道具 47 条补全，默认首选）/ C0（采集更新可靠性经验吸收）/
E0（离线培育测试台实验）**，用户要求开新对话做，一次会话三选一，见 HANDOVER_NEXT §4 T9。
**T9 进度：B7 ✅（P 道具 47 条补全）、C0 ✅（2026-11-22 排障判据吸收进 TROUBLESHOOTING §四 +
CAPTURE_PIPELINE 更新后自检 8 步，纯文档不改代码），剩 E0**（离线培育测试台，需独立副本 + 用户配合）。
下一步继续 **T5 剩余机制**（**B8 条件/效果语义第一批 + B9 持久倍率/modifier 类 +
B10 生成卡确定式/指定卡名映射已完成**；剩 `ExamBuffConsumptionAdd`（强化状态花费卡机制
不在模型里，保持 no-op）、**随机生成卡**（H.I.F应援棒，考试 RNG 流未知）、hold 保留区
张数条件（2 件）；**fresh buff 差一回合**仍需真机逐回合截图）。
**B2 按 B3+ 规则重训（B2-R）已于 2026-11-23 完成：仍 FAIL（确认段 −7.2，ensemble 0.75 中性）；
同日高预算验证（width8/300ms 选择段 80 局）也 FAIL（−4.4 CI[−8.8,−0.0]，ens 0.75 中性）→
学习叶子路线关闭**，负结果记录在案；生产 leaf_model 保持关闭、T2 候选去掉 learned leaf
（见 EXPECTIMAX「B2 重训（B2-R）」）。**C1 执行层可靠性已于 2026-11-23 完成**（用户指定；
tap 确认/重试 TapGuard+PickerGuard、提权检查 privilege、动作前预算下一帧、每步 step_trace.jsonl
+ replay_steps.py 离线复盘；68 条失败场景单测，pytest 1223/1（1224 收集 / 83 文件）；
真机验收留阶段 E；见 WORKPLAN C1 / HANDOVER 二·补三十六）。
**B11 渐退式专家迭代第 1 轮已于 2026-11-23 完成（用户选定启动）**：学 policy/advantage
（137 维学生网）+ 精确重放分支 on-policy 优势标签 + 70/30 混合；**确认段 120 局
v1 97.5 vs beam 教师 94.9：+2.6 CI[+1.1,+4.1] 评测门 PASS（放手）**，稳健块 +3.8；
消融：纯 BC v0 也过门（+2.4）→ 红利主力=逐决策蒸馏+禁跳，on-policy 成分待第 2 轮验证；
28 条单测；见 EXPECTIMAX B11 / HANDOVER 二·补三十七。
**B11 第 2 轮也已于 2026-11-23 完成（用户选定）**：教师←v1（--teacher-net）、占比 0.15、
large 首测；**确认段 v2 97.9 vs v1 97.5：+0.4 CI[−0.4,+1.2] → CONTINUE（平台期，四段全中性，
新鲜块 5000 同样中性）**；消融 v2−v2_bc=+0.54 CI[−0.40,+1.48] on-policy 仍未独立证明；
**large：v1 比 beam −28.1 CI[−36.0,−20.2]（CLEAR 36.7% vs 53.3%），v2 比 v1 还略差
（选择段 −14.8 显著）→ small 训练不泛化 large**；v2−beam small +2.99 CI[+1.37,+4.62]；
处置：占比不降、生产接线未做、T2 候选不变；15 条新单测。
**r3–r8 继续扶也已完成（用户指令「显著强于老师才结束」）**：数据×10/epochs×3/容量×2/
ε-greedy 探索（--explore-eps，+7 测试）全试过，确认段恒 +0.2~0.6（种子段结构、非模型问题）；
**门协议修正（用户批准）：确认段扩 500 局 3000–3499 → v6 98.6 vs v1 98.1：+0.6 CI[+0.2,+0.9]
PASS**，新鲜块 6000 +1.7 CI[+0.6,+2.8] 佐证，池化 820 局 +0.71 CI[+0.40,+1.02]；
**v6（192×96）= 当前最佳学生，显著强于 v1**；pytest 1273/1（1274 收集 / 86 文件）；
见 EXPECTIMAX B11 r3–r8 续 / HANDOVER 二·补四十。
**B11 v6 生产接线也已完成（2026-11-23，用户授权综合推荐后选定；纯增量，opt-in 默认逐位不变）**：
`LessonPolicy(engine="net", net_model=…)` 可观测状态 argmax 优势分（无搜索、不用 known_draw，
public-safe）；有牌绝不 SKIP / 全付不起才 SKIP；缺模型/推理异常 → [engine][BLOCKED]（禁回退 rules）；
auto_produce `--net-model` > `produce.net_model` > 默认入库 v6（data/knowledge/ei_policy_v6.json）；
T2 增第四臂 `--engine net`（large 生产候选仍是 beam）；21 条新单测，pytest 1294/1（1295 收集 / 87 文件）；
见 EXPECTIMAX「B11 v6 生产接线」/ HANDOVER 二·补四十一。
**B11 r9-large 也已完成（2026-11-23，用户授权安排）**：train_ei_policy 多文件混合（单文件逐位不变，
12 条新单测）；large 自对弈 5000 局 + small 全量 + 示范补量，192×96/1200ep 同 r6；
**large500 r9 315.4 vs v6 285.8（+29.6 CI[+26.2,+33.0]）且超 beam +14.2 —— 首个 large 超 beam
学生网**；**small500 −0.42 CI[−0.67,−0.17] 显著回退 → 复合门未过，不入库**（生产保持 r6；
r9 留 out/ 作 large specialist）；诊断假设=全局 std 稀释 small 信号；pytest 1306/1（1307 收集 / 88 文件）；
见 EXPECTIMAX B11 r9-large / HANDOVER 二·补四十二。
**B11 r10 也已完成（2026-11-23 晚，用户选定）**：--norm-by-scenario 按场景 std 归一化（纯增量，
默认逐位不变，12 条新单测）；复用 r9 数据重训（单变量=归一化口径）；能量份额 small 20.9%→49.0%；
**large500 +29.1 CI[+25.8,+32.3] 增益保持（vs beam +13.6 仍超）；small500 −0.256 CI[−0.500,−0.012]
仍显著回退（收窄 39%，vs v1 原门恢复）→ 复合门未过，不入库**（生产保持 r6；r10 留 out/）；
归一化修复有效但不充分（输入侧场景漂移仍在）；pytest 1318/1（1319 收集 / 89 文件）；
见 EXPECTIMAX B11 r10 / R9_ANALYSIS §8 / HANDOVER 二·补四十三。
**P1-1 也已完成（2026-11-24，阶段1 首批：r10 行为探针 + 全力回合 + のんびり指針）**：
r10 探针（复用 r9 口径，R9_ANALYSIS §9）判定**残留 small 回退已非 v1 风格贪即时分**
（首分歧贪即时分偏置 24:9→11:8、对 v1 耐心比恢复 v6 水平 25:11≈29:13、CLEAR 翻转 1:1 对称）
→ 残留 −0.256 是无方向漂移噪声（通道 2），r11 small 上采样仍是对症变量；规则按 BSD-3
参考引擎 + contest-fidelity 真机回放证据补全：全力回合 +1 出牌（连续全力每回合都有）/
保留牌回手钩子（held 来源留 P1-3）/全力期间禁切指針/のんびり ×0 倍率 + 解除收益
（元気+5/次数+1/熱意+10，→全力时改为全体卡打分成长+10）/温存→のんびり不触发温存解除/
のんびり预约来源（4 族卡 ExamOverPreservation，CSV 逐卡证据表）/P 道具 stance_leisure 直给
（2 件标注，触发时机 card_play_interval_after 未支持仍保守不触发）；LessonSim/ExpectState
双镜 + 叶子快照对齐；评测牌组组成不变（のんびり卡 score 0/SSR/Legend 本就不进池）；
36 条新单测，pytest 1354/1（1355 收集 / 90 文件）；sim_engine_ab 重标定改前/改后 64 局
逐位相同（差异=0）；见 RULES_REFERENCE §5.4 / R9_ANALYSIS §9 / HANDOVER 二·补四十四。
**P1-2 也已完成（2026-11-24，阶段1 第二批：handDecrease 抽牌修正 + pride 自尊）**：
④ cardsToDraw=max(3−handDecrease,0)（BSD-3 TurnManager/BuffManager + wiki；timed 列表
合算/倒计时/∞永久；只减回合开始抽牌、卡效果抽牌不受影响；来源=塔 gimmick
ExamGimmickStartTurnCardDrawDown 12 段；nullifyDebuff 拦截未建模如实记）；⑤ pride
resolveScore f min(好印象,やる気)×0.02 上限+0.5（prideTurns 回合末 -1；来源离线可确定：
卡「我、绝不」turn=5 门槛干劲>=9 + P 道具「一笔入魂」turn=2/3 status_gain&好印象>=6&limit1，
主数据↔skill_cards.csv 632/633、p_items.csv 354/355 交叉，pIdol 117/118=雨夜燕）；
LessonSim/ExpectState 双镜 + canonical + 叶子对齐；sim_produce MODELED 33→34、
p_items.json implemented 1042→1056/1849（modifier 371→385）；评测牌组/gkbench loadout
组成不变（自尊卡 score 0/SSR 不进池；94 唯一 loadout id 无 117/tower）；36 条新单测，
pytest 1389/1（1390 收集 / 91 文件）；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；
见 RULES_REFERENCE §5.5 / HANDOVER 二·补四十五。
**P1-4（阶段1 第四批）也已完成（2026-11-24）**：nullifyDebuff 低下状态无效拦截（消耗式计数器，
无回合倒计时）拦截 setScoreDebuff/setHandDecrease（P 道具侧 ExamAntiDebuff count 11 段：
偷懒的毛巾 + 塔 gimmick；参考 Executor :429/:507/:545）；**⑦ ExamBuffConsumptionAdd 保持
no-op**（doubleBuffCostTurns 语义/主数据 4 段/gkbench 22 loadout 如实记；卡模型不承载 buff
花费，88 张参考 buff-cost 卡 card_table cost=0、CardSpec 无 buff_cost 字段）；**countDebuffs
无落点**（低下状態の数参考+主数据零使用）；卡侧 4 SSR 族来源/标量 DEBUFF_FIELDS 拦截延迟；
implemented 1056→1067/1849（modifier 385→396）；评测零落点；30 条新单测，pytest 1465/1
（1466 收集 / 93 文件）；sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；
见 RULES_REFERENCE §5.7 / HANDOVER 二·补四十七。
**P1-5（阶段1 第五批）也已完成（2026-11-24）**：P 道具剩余效果语义补全（bounded batch）——
层数减少类（干劲/集中/全力值 -= N 夹取 ≥0，DSL motivation-=1/concentration-=1/fullPowerCharge-=2；
全力值独立 PItemDelta.full_power_point_reduce 不计累计）+ 体力减少（ExamStaminaDamage 并入
STAMINA_LOSS，cost-=1 genki==0 穿透）+ 好调N回合（ExamParameterBuff turn 列 → condition_turns，
DSL goodConditionTurns+=N）+ 好调依赖换算（好调的N%数值变为打分/集中，CONVERSION_SOURCES 加
好调:parameter_buff，DSL score+=goodConditionTurns*0.3）；**留后续**（证据充分需新机制，no-op
如实记）：好调增加量增加/元气增加无效/不安/塔 gimmick/全力・强气效果卡打分/日文好調の%分；
implemented 1067→1164/1849（+97）、依赖换算 65→76；**sim_produce 不引用 p_items → 评测零 P 道具
结算**；38 条新单测，pytest 1503/1（1504 收集 / 94 文件）；sim_engine_ab 重标定改前/改后 64 局
逐位相同（差异=0）；见 RULES_REFERENCE §5.8 / HANDOVER 二·补四十九。
**P1-6（阶段1 第六批：T7②③ 离线可靠性工程）也已完成（2026-11-24）**：⑨ 纯函数状态重放——
新 data/run_replay.py（apply_event 无副作用 + 深不可变 RunState + 同观测序列两遍重放指纹逐位
相等 + compare_replays 逐步比对首个分歧步 + legacy_events 旧格式确定式重建 + consistency_check
三方对账）；RunRecorder 增量 events 观测日志（旧文件续跑先重建）；scripts/replay_run.py
--verify/--compare。⑩ 自动复盘页——report/review_page.py 自包含 HTML（逐回合/考试/结算/
重放一致性/C1 逐步轨迹/行内标注导出导入）+ report/annotations.py 标注转回归（verdict=bad 带
expected → 整态/分类结论冻结进 tests/fixtures/review_regressions.json）+ scripts/review_page.py
+ scripts/annotations_to_regression.py；auto_produce 局末自动生成（[review]）；样例页
docs/review_sample.html（ep-rule1 真实记录 + 合成演示轨迹显著标注）。**不改考试规则、不作废
B11 数据**；sim/ 零引用新模块 → 评测零影响、无需重标定；61 条新单测，pytest 1564/1
（1565 收集 / 97 文件）；基线 ①③④⑤ 不变；见 WORKPLAN P1-6 / LIVE_RUN §2.1 / HANDOVER 二·补五十。
**P1-7（阶段1 第七批：P 道具后续批次）也已完成（2026-11-24）**：好调增加量增加 condition_gain
（resolveGoodConditionTurns ×(1+Σbuffs)，夜闇の星 313/314）+ 元气增加无效 nullify_genki_turns /
不安 unease_turns（resolveGenki return / ×0.67，∈ EOT_DECREMENT+DEBUFF_FIELDS；いたずらパペット/
初陣の証・美鈴/雨上がりの花）+ ExamBlockFix 分离 fixed_vitality（resolveFixedGenki 不受闸门）+
**通用延迟生效**（yaml exam_effect_timer-NNNN ↔ DSL delay:N-1/嵌套 at:turn，EffectManager.decrementDelay；
34 段标注，修正おさぼりタオル/美铃/温存变更类等已实现道具时序）；**保持 no-op**：塔 gimmick（参考无字段）/
塔 ∞ 段（value=0）/全力・强气效果卡打分（per-card g.score 成长）/日文好調の%分/ExamParameterBuffReduce；
implemented 1164→1179/1849（+15）、modifier 409→442；**sim_produce 不引用 p_items + genki_gate/
condition_gain 无来源恒等 → 评测零影响**；48 条新单测，pytest 1612/1（1613 收集 / 98 文件）；
sim_engine_ab 重标定改前/改后 64 局逐位相同（差异=0）；见 RULES_REFERENCE §5.9 / HANDOVER 二·补五十一。
**P1-8（阶段1 第八批：P 道具剩段 bounded batch）也已完成（2026-11-24）**：日文好調の%分
（天生的才能 pitem_01-3-346-0/1）——DSL 天性の才能 493/494 `score+=goodConditionTurns*0.3/0.5`
+ `countCards[hand & baseId(23)]>=1`（眠気卡张数条件 B10 zone_count 已解析，baseId 23↔睡意
p_card-00-acc-0_002）；本批只补日文换算源标注 CONVERSION_SOURCES_JA（**sim/ 零改动**，复用 P1-5
换算渠道）；**保持 no-op**：全力・强气效果卡打分（per-card g.score 成长 43 段，values 恒空需逐卡
证据表+新机制）/塔 gimmick（29 段参考无字段）/ExamParameterBuffReduce（3 段 produce/buff_consume
触发未支持）；implemented 1179→1181/1849（+2）、依赖换算 76→78（好调换算 11→13）；**评测零 P 道具
结算 + sim/ 零改动**；32 条新单测，pytest 1644/1（1645 收集 / 99 文件）；sim_engine_ab 重标定
改前/改后 64 局逐位相同（差异=0）；见 RULES_REFERENCE §5.10 / HANDOVER 二·补五十二。
**阶段2 r11（P2-0/P2-1/P2-1b：新规则重采 + small 上采样）也已完成（2026-11-24，small+large 双过入库，
首个双过学生）**：前置 sim_engine_ab 重标定与 P1-8 逐位一致（0/32，Δ+372.2/+219.1）+ 参照臂 v6/v1/beam/r9/r10
新规则重评（small 规则零分移 v6 98.640/v1 98.062；large 分移 ±2 v6 287.818/beam 301.612，门基线重定）；
P2-0 v6 argmax 新 seed 块重采 small 145565（1100000+）/large 128103（1200000+）/v1 示范 51985（1300000+）；
P2-1 `--upsample-small 2` 纯增量（13 条回归默认逐位不变）+ `--norm-by-scenario` → 467527 行（small 能量 65.6%）；
**500 局双门首次双过**：large r11 313.92 vs v6 287.82 +26.10 CI[+23.06,+29.14] PASS（vs beam +12.31）/
small r11 98.648 vs v6 98.640 +0.008 CI[−0.253,+0.269] 不回退 / vs v1 +0.586 CI[+0.245,+0.927] 保持 →
入库 ei_policy_v6.json=r11（参照臂逐位 6/6，旧 r6 保留 out/）；P2-1b 新旧对比 large headline r11 vs 旧 v6
+28.08 = 学生改进 +26.10（93%）+ 规则分移 +1.98（7%），small 规则零分移，r11 small 显著优于 r9（+0.426 修复回退）；
**F public-safe 入场券拿到**；13 条新单测 + wiring 更新，pytest 1657/1（1658 收集 / 100 文件）；
见 EXPECTIMAX B11 r11 / R9_ANALYSIS §10 / WORKPLAN P2 / HANDOVER 二·补五十三。
**下一会话起按多会话路线图推进（用户 2026-11-23 晚确认 A 顺序，详见 HANDOVER_NEXT §8.0）**：
阶段1 离线补未知（~~全力回合额外次数/保留牌/のんびり + r10 行为探针~~ ✅ P1-1；
~~handDecrease 抽牌修正 + pride 自尊~~ ✅ P1-2；~~hold 保留区 + lockStanceTurns~~ ✅ P1-3；
~~nullifyDebuff 拦截 + ⑦ buff-cost/countDebuffs 评估~~ ✅ P1-4；~~P 道具剩余效果语义补全
（层数减少 + 好调回合 + 好调依赖换算）~~ ✅ P1-5；~~T7②③ 纯函数状态重放/自动复盘页~~ ✅ P1-6；
~~P 道具后续批次（好调增加量增加/元气增加无效/不安/通用延迟生效）~~ ✅ P1-7；
~~P 道具剩段 bounded batch（日文好調の%分 / 天生的才能）~~ ✅ P1-8；
**阶段1 剩 P 道具后续批次**（塔 gimmick/全力・强气效果卡打分/ExamParameterBuffReduce
——证据充分需新机制/真机，no-op 如实记，留阶段3）；~~阶段2 重采+练学生 r11（small 上采样，
small+large 双过入库）+ 新旧对比（旧学生/老师数据模型全保留不覆盖）~~ ✅ P2-0/P2-1/P2-1b；
**r11 双过入库后先问用户**：阶段3 真机 T3→T1→T2（+T6/D1 补采 + E0 + C1 真机验收），或如需 small
显著超 v6 可 r12 续（教师←v6/降档/两段式微调，非必需））→ 阶段4 gkbench F1/F2 → 阶段5 收尾 G。
**每会话 1–3 任务（小任务合并），开新对话做；旧路线图未完成项已全并入 §8.0**。
需真机数据的建模缺口（考试 RNG 流/fresh buff/附魔/真机 P 道具列表）留阶段3。
→ F1/F2 gkbench 公开对比（ranked 禁 seed，只能交不看 seed 的算法；B11 学生网只看
可观测状态，是未来 public-safe 候选，**r11 已 small+large 双过 → F 入场券拿到，仍须真机 T2 验证**）。
```
