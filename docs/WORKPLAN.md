# 总作战计划（2026-11-22 起，新会话照此执行）

> 用户定的顺序：**先把所有离线工作全部做完 → 再跑真机 → 最后去 gkbench 比算法**。
> 本文件是唯一的总清单；具体任务细节在 [HANDOVER_NEXT.md](HANDOVER_NEXT.md)、
> [GROUP_FILES_ANALYSIS.md](GROUP_FILES_ANALYSIS.md)、[EXPECTIMAX.md](EXPECTIMAX.md) 等文档里。
> 新会话开场：`读 docs/INDEX.md → docs/WORKPLAN.md → docs/HANDOVER_NEXT.md §2 跑基线 → 按 WORKPLAN 顺序做`。

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
| B2 全知数据训练 MLP 叶子 | `scripts/build_b2_dataset.py` + `train_b2_leaf.py` + `eval_b2.py`；beam 全知自对弈 26.5k 叶子样本 → MLP 104→96→48（val r²=0.943）；**确认段 120 局配对：beam 157.8 → 165.5（learned，+7.7 CI[+4.2,+11.2]）/ 166.9（ensemble 0.5，+9.0 CI[+5.8,+12.2]）**；CLEAR 95→98.3%、PERFECT 33.3→50%；within 用 learned 变差 −3.3（负结果记录）；`tests/test_b2_leaf.py` 11 条；全量 pytest **975/1（976 收集 / 71 文件）**；`docs/EXPECTIMAX` B2 学习叶子（**B3 后旧模型失效，待重训**） |
| B3 T5 机制建模（回合规则 + 核验表） | 模拟器对齐真机：每回合基础 **1 张** + 打完自动结束回合 + SKIP 回 2 体力 + 取整 `safeCeil`（`sim/lesson`、`sim/expectimax`、`sim/uiobs` 等）；真机 39 回合配对回归（`tests/fixtures/t5_exam_turn_rules.json` + `scripts/export_t5_turn_rules.py`）；`RULES_REFERENCE.md` 重写逐条核验表；实机回放黄金值 12 条；重标定：`sim_engine_ab` expectimax 显著强于 rules（+342~+429 评价点）、B1 60 局 within 89.1→beam 95.7（+6.6，门 107.4% PASS）、B2 旧模型 FAIL 待重训；全量 pytest **985/1（986 收集 / 72 文件）**；`docs/HANDOVER` 二·补二十一 |
| B4 T5① 审查倍率分段 + 联动惩罚 | `src/gkagent/sim/exam_multiplier.py`（分段折线 + 联动惩罚 + 客户端 f32/ceil 取整）+ `src/gkagent/data/exam_bonus.py`（主数据 → 配置）+ `LessonConfig.attribute_bonuses/turn_attributes`（模拟器按回合属性乘，含依赖分与回合末好印象）+ `policy.audition_coefficient`（真机屏幕「舞蹈 207%」→ 搜索倍率，日志 `attr=2.07`）；夹具 `tests/fixtures/t5_exam_multipliers.json`（11-20 采集局期中 Vo/Da/Vi **4.09/2.20/2.60×**、期末 **6.97/2.85/4.96×**；Vi/Vo/Da 低于审查基准的联动惩罚已对上）；`tests/test_exam_multiplier.py` 21 条；全量 pytest **1006 passed / 1 skipped（1007 收集 / 73 文件）**；`docs/RULES_REFERENCE` §5.1 |
| B5 T5② 熱意 + 温存解除 | `src/gkagent/sim/enthusiasm.py`（熱意获得/回合末清零/延長/温存解除纯规则）+ `LessonSim`/`ExpectState` 熱意字段与算分（集中之后、好调/指針之前；整数获得时 ceil）；温存解除 1 段 +5 熱意/2 段 +8 熱意 +5 固定元気 + 解除当回合 **+1 出牌次数**（同回合可重复）；卡牌效果 `ExamEnthusiasticAdditive/Multiple`（熱意追加/増加 buff）、`ExamEnthusiasticTurnAdd`（延長）、`ExamMultipleEnthusiasticLesson`（本牌熱意適用倍数 ×2）接入 `sim_produce`（MODELED_EFFECTS 29→32）与生产卡表 `play_choice`；回合边界 温存→全力 也结算解除收益；`tests/test_t5_enthusiasm.py` 16 条 + sim_produce/play_choice/mechanism 更新；全量 pytest **1023 passed / 1 skipped（1024 收集 / 74 文件）**；`docs/RULES_REFERENCE` §5.2 |
| B6 T5③ P 道具数据接入 | 新增 `src/gkagent/data/p_items_db.py`（`produce_item_ids` → `PItemSpec`，未知/重复 id 显式上报，缺数据抛错）+ `sim/p_items.py` 新增 **`exam_start`** 触发时机（288 段素材）与 **`ExamPlayableValueAdd` → `extra_plays`**（51 段，取 `count` 列）；`LessonSim` 构造时结算考试开始效果（先于 turn_start、额外出牌保第 1 回合）、`ExpectState` 镜像；`scripts/local_bench.py` 从 `loadout.produce_item_ids` 接入 + `--p-items auto/off` + 报告 `p_items` 覆盖率；`submissions/expectimax/algo.py` 从 `ctx.loadout`（公开配置、不含种子）接入；gkbench 505 题模板 83 唯一 id（72 已知/11 未知）；离线 A/B hif 30 题×2 seed：greedy **+128.9（+3.36%，CI[+9.5,+248.4]）** / expectimax +149.6（+3.98%）；新增 29 条测试；全量 pytest **1051 passed / 1 skipped（1052 收集 / 76 文件）**；`docs/RULES_REFERENCE` §5.3 |
| 作者 2026-11-22 四游戏整合包分析（外部情报，只读参考） | [LOCAL_LAUNCHER_20261122.md](LOCAL_LAUNCHER_20261122.md)（包结构/11-22 新版本变化与修复/采集安装边界；7z 归档 `data/dl/`、解包在仓库外，1457 条 sha256 校验通过） | 不能替换采集安装、拿不到考试算分公式；可用的：更新/代理/TLS 排障经验、Produce API 语义参考、P 道具 47 条 id 清单（含 B6 的 11 个未知 gkbench id）；候选任务 **B7 ✅ / C0 ✅ / E0（T9，剩 E0 需独立副本）**，用户要求开新对话做；提交 `ddf221f` |
| T9-C0 采集/更新断链排障判据吸收（纯文档） | [TROUBLESHOOTING §四](TROUBLESHOOTING.md) 13 条清单（2004 / 协议 hash/master 结构 / http1_bridge 头丢失 / 票据 865-833 / 上游端口 / 停服务顺序 / CA 指纹 / 诊断脱敏 / 互斥）+ [CAPTURE_PIPELINE「游戏客户端更新后自检」](CAPTURE_PIPELINE.md) 8 步 | 外部经验，本项目待验证；纯文档不改代码，pytest 仍 1054/1；见 HANDOVER 二·补三十 |
| B8 T5④ P 道具条件/效果语义（第一批） | `scripts/build_p_items.py`（新语法 trigger id 解析 + 依赖换算标注）+ `sim/p_items.py`（`depends_on`/`percent`/`percent_max`/`zero_stack` + 5 类新触发）+ `sim/lesson.py`/`sim/expectimax.py`（事件/累计量双镜） | 数据层已实现 **445→676/1849 段**；条件未知 22→**6 件**；trigger 未知 103 件/185 段单列保守跳过；gkbench 已实现 34→**59/153 段**；greedy A/B **+225.2（CI [+86.7,+363.6]）**；pytest **1067/1（1068 收集 / 77 文件）**；见 HANDOVER 二·补三十一 / RULES_REFERENCE §5.3 |
| B9 T5④ P 道具持久倍率/modifier（第二批） | `scripts/build_p_items.py`（`annotate_modifier_effects`：20 类 target / 369 段 + 文本次数上限 9→896 件）+ `sim/p_items.py`（`PItemDelta` 新字段 + `add_timed/tick_timed/timed_dict_*` 纯规则）+ `sim/lesson.py`/`sim/expectimax.py`（分数倍率 f/g、费用修正、回合追加、指針直给、增益倍率、倒计时、canonical/双镜） | 数据层已实现 **676→1025/1849 段**（no-op 1173→824，modifier **337 段**）；gkbench 已实现 **59→103/153 段**；greedy A/B **+110.3（+2.87%，CI [+39.6,+193.3]，20胜/2负/38平）** / expectimax +48.2（CI 含 0）；新增 `tests/test_p_items_b9.py` 49 条；pytest **1116/1（1117 收集 / 78 文件）**；见 HANDOVER 二·补三十二 / RULES_REFERENCE §5.3 |
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

### C1. 执行层可靠性（参考 GKMSMAA 架构，**自写代码不拷贝**）
- tap 确认/重试（tap 丢失、对话未开、picker 选牌、同屏循环）；
- 提权检查（游戏 elevated / 本进程 non-elevated 的失败提示）；
- 动作前预算下一帧（hiro 原则）、每步可复盘（日志已有 `eng/fallback`，补动作理由）；
- DoD：对应失败场景单测；真机日志能复盘每一步。

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
未建模：のんびり指針、全力回合額外出牌/保留牌、P 道具/附魔来源、生产读屏未读熱意。
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
下一步继续 **T5 剩余机制**（**B8 条件/效果语义第一批 + B9 持久倍率/modifier 类已完成**；
剩 `ExamCardCreateId` 生成卡、`ExamBuffConsumptionAdd`（强化状态花费卡机制不在模型里）、
指定卡名/手牌限定（需卡名→id 映射）；**fresh buff 差一回合**仍需真机逐回合截图）
→ 阶段 C1（执行层可靠性）/ D（补采集）离线做完 → 真机 T3→T1→T2（含 E0 实验）
→ F1/F2 gkbench 公开对比（ranked 禁 seed，只能交不看 seed 的算法）。
```
