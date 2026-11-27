# 草稿：GKBENCH §12.1 追加节（门数字待填）+ v2h RESULTS 骨架

## 已确认事实（诊断探针 data/_hajime_diag.py / _hajime_diag_scan.json / _hajime_diag_game_k0.json）

### hajime 48 题结构
- 33/48 课程局（round=lesson，stage hajime.2–33，produce-001/006）；15/48 audition（7 final + 8 mid1）。
- turns 6–12（6:6 / 7:6 / 8:16 / 9:9 / 10:3 / 11:2 / 12:6）；score_cap 课程局 50–800、audition 900/null。
- hif 505 题 turns 9/10/12（170/57/278），produce-007/008 → fp 判定必须按 produce（题集），不能按回合数
  （hif 也有 9–10 回合短局，按 turns≤12 判会误翻 227/505 hif 题）。

### 根因①：课程局无属性池 = 引擎事实，非 v2 实现缺失
- v2 opening.turn_pool 与 seedlock _turn_pool 同式（audition_parameter_values → ceil/round f32 配额）。
- 课程局引擎 values=None / exam.types=[] / k=segment_start_rng_advances=0 → 两者都无属性过滤。
- audition 题两者都有池过滤：实测 AS-X8NXKZXW scan 2.7s（seen3→69,985 / seen6→36 / seen9→3），
  AS-DDCRRSTM scan 3s（seen2→17,045 / seen5→3 / seen8→1），v2 锁定正常。
- 课程局候选爆炸（重牌小 deck）：AS-GZP54V4T（10 卡 7 distinct，cap50 t6）seen2→65,618,642 / seen5→752,913 /
  seen8→94,660；AS-WNAX63AN（28 卡 27 distinct，cap800 t8）seen3→130,712 / seen6→30 / seen9→1。
  候选随抽牌数指数塌缩 → 重扫（更长 seen）比 FastCut 几万候选便宜一个量级。
- v2 单次扫描 6 张起 + 只 FastCut（0.4ms×94k≈38s ≫ 步预算 7.5s）+ 短局打完未筛完 → 整局 worlds 兜底。

### 根因②（关键新发现）：worlds 投票早期出牌触发 deck-modify 使抽牌模型丢真种子
- AS-X8NXKZXW（audition mid1）：v2fp0/v2fp1 scan 2 候选均 hand[0] 不符 → failed，整局 worlds，900（cap）。
  seedlock 贪心早期出牌保住模型 → turn4 锁定，884。
- AS-DDCRRSTM（audition final）：v2 scan 0 候选（真种子不在 hits）→ failed，5,870；
  seedlock turn4 锁定 21,734（3.7×）。v2h short_greedy 后 turn3 锁定 19,069（3.2× v2）。
- 机制：抽牌序模型（Draws seen/skip）依赖早期出牌不改动牌堆；worlds 投票选的牌与贪心不同，
  某些牌触发 deck-modify（创建/洗回/移除）→ 模型失效 → scan 找不到真种子。
  与 hif WDKWQYW5「锁定对早期打法敏感」同源（v3 RESULTS 已记）。
- seedlock 不失锁的真正机制 = 课程局早扫(3张)+多等(0.85)+重扫(256)+少量候选核对锁定 + **锁定前贪心 fp1**。

### 根因③（首批门负结果，修正 §12 猜测）：fp1 锁定后反效
- AS-2AYFMJMR s1：v2fp0=250（=ub2M 最优），v2h-fp1-locked=135（hard_rule 1 次，tail 证 135 为偏离后最优）；
  AS-35BS9YF4 s0：v2=166，v2h-fp1-locked=114（hard_rule 1 次）。
- 强搜索路线的 end 是最优蓄力；强制出牌偏离最优路线 → 分数下降。短考试 fp1 收益在锁定前贪心，不在锁定后硬规矩。
- 等价早锁（lock_equiv_max=8）负结果：AS-2AYFMJMR s0 turn3 锁 1220681179≠真种子 1543353470 → turn4 lost
  hand[1]，160 vs v2 250。重牌 deck 等价种子未来抽牌序分叉；v2「恰剩 1 才锁」靠继续出牌自然消歧更稳。缺省回退 1。

### v2h 最终设计（copy v2 后改）
| 杠杆 | 参数 | 触发条件 | 语义 |
|---|---|---|---|
| 锁定前贪心 | short_greedy=1 | short_exam | 不走 worlds/候选投票，引擎卡表即时分贪心（seedlock 同语义自写）；保抽牌模型早锁 |
| 短考试 fp1 | short_forced_play=1 | short_exam 锁定前 | 有牌必出（贪心天然满足）；worlds/兜底 end 改出即时分最高 play |
| 锁定后信路线 | short_fp_locked=0 | 锁定后 | 承 v2 fp0（RoutePool 路线 end 尊重）；=1 消融复现 seedlock 全 fp1 |
| 课程局早扫 | scan_min_eff=3 | pool_attr None | 3 张起扫（seedlock 同语义） |
| 步内多等 | wait_frac 0.85 | pool_attr None | 扫描无早拒慢一个量级（seedlock 同语义） |
| 重扫 | rescan_above=8000 | short_exam + tr.open + seen+3 + cands>8000 | 更长 seen 重扫压候选；阈值按 v2 FastCut 0.4ms 自调（seedlock 3ms 用 256；256 在 v2 下推迟锁定 2AYFMJMR turn3→4） |
| 等价早锁 | lock_equiv_max=1 | （缺省关） | 负结果回退；>1 消融才启用 |
| short_exam 判定 | produce ∈ {001,002,003,006} 或 pool_attr None | begin() | hif/nia（007/008/004/005）全部杠杆不触发，行为=v2 |

### hif core8 抽查（data/_hajime_pair_hif.json，dev 种子）
- 6/8 精确同分同路线（323ADZVK 4,469,935 / 8MY3XH4R 463,331 / 227HBGHS 8,061 / 23D5RE8A 21,893 /
  33JYSHDF 806,846 / 93WKA9BK 328,603）；2/8 墙钟搜索方差非负（2AXJNW8X +89,357 / ADDTACFE +3,090,593，
  v2h 摸到 6.2M 盆地 = v2 published monster 口径）。
- v2h mean 1,719,643 vs v2 1,322,149，Δ+397,494 CI[0,+1,170,142]，2 胜 0 负 6 平，崩局 0，lock 8/8，over 0。
- 全 8 题 short_exam=false / fp_eff=false → 机制全关，误投 hif 不回归。

### pytest
- 全量（排队友未提交 WIP tests/test_drinks_m6.py）：1705 passed，exit 0（--basetemp=out/_pytest_tmp_hajime 绕 Temp ACL）。
- 含该 WIP 文件：6 失败全在该文件（队友 M6 drinks 进行中工作：src/gkagent/sim/drinks.py 等未提交）；本任务 src/gkagent 零改动。
- 基线 1681/1 → 1705 漂移来自队友近期提交（454e2c7/2ad411d 等加测试），非本任务。

## 待填：门数字（_hajime_pair_gate.json / summary）
- v2 / v2h / seedlock 均分、分布、锁定率、失锁、崩局、over、bad_routes
- v2h vs v2：overall / lesson / audition Δ + CI + 胜负平
- v2h vs seedlock：同上
- 托管建议