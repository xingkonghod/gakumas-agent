# 真机验证一局（C+）操作手册

> 目标：按模拟器选出的策略跑一局感性培育，拿到 **C+ 以上评价**，并记录三维用于标定。
> 前提：模拟器已就绪（`data/knowledge/policy.json` 的 produce 段生效）。

## 0. 先把游戏开起来（当前是关着的）

```powershell
# 1) TUN 模式（不是系统代理）；2) 只开一个 DMM；3) DMM → マイゲーム → 点游戏卡片
Get-Process gakumas, DMMGamePlayer -ErrorAction SilentlyContinue | Select-Object Id, ProcessName
```

**游戏重启过 → 必须重启 daemon**（它缓存窗口句柄，否则会点空气）：

```powershell
.venv\Scripts\python.exe scripts\agent_cmd.py quit
schtasks /Run /TN GDEAgent
```

## 0.0 一键自检（2026-11-26 新增，只读不改游戏）

```powershell
.venv\Scripts\python.exe scripts\live_preflight.py   # exit 0=READY / 2=BLOCKED+原因清单
```

覆盖 §0.1 清单 1-7：游戏在跑/单进程/急停标记/daemon/接线/截帧/提权。**BLOCKED 不起跑**；
用户不在机前时游戏未开属预期阻塞，开游戏+管理员终端后重跑。

## 0.1 开跑前 3 分钟自检

### 起跑前检查清单（每次必做，2026-11-15 踩过双进程互抢窗口）

1. **没有别的 auto_produce 在跑**：
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
     Where-Object { $_.CommandLine -like '*auto_produce*' } |
     Select-Object ProcessId, CommandLine
   ```
   有就等它结束，**一局只能一个进程**（两个进程会同时点同一窗口、同目录 step_NNN 互相覆盖）。
2. **清急停标记**：`Remove-Item data\STOP -ErrorAction SilentlyContinue`。
3. **窗口正常**：`agent_cmd.py shell --command "...data\restore_win.py"`，输出
   `client 540x960 iconic=False`；**不要改成 720x1280**（会截 720x999 直接崩，F#10）。
4. **daemon 在线**：`schtasks /Query /TN GDEAgent` 应为 Running；
   `agent_cmd.py quit` + `schtasks /Run /TN GDEAgent` 可重启（游戏重启后必须重启 daemon，否则句柄失效）。
5. **上次的局已收尾**：`data/agent_result.json` 里没有未完成的 ep；`data/auto/step_*.png` 最新时间戳距今 >10s。
6. **记录开始时间**：`Get-Date -Format HH:mm:ss`，写进 `docs/RUNS.md`（每局要能回答"这局用了多少分钟、每个阶段多久"，
   用 `scripts/episode_report.py <ep>` 生成阶段分解）。
7. **提权一致（C1）**：DMM 版游戏以管理员运行，**跑局终端也必须是管理员**——否则 Windows UIPI
   静默丢弃点击（截屏正常、点击全落空）。`auto_produce` 启动会自查并在日志首行写 `[priv]`；
   判 `blocked` 直接拒跑（exit 2 + `elevation-blocked` failure），按提示换管理员终端。

```powershell
.venv\Scripts\python.exe scripts\check_wiring.py --live    # 配置接线 + 游戏窗口一次过
```


```powershell
cd D:\Games\gakumas-agent

# 1) 游戏窗口尺寸必须是标准 720x1280（被拉宽/缩小会截出 720x999 直接崩）
.venv\Scripts\python.exe scripts\agent_cmd.py shell --command "D:\Games\gakumas-agent\.venv\Scripts\python.exe D:\Games\gakumas-agent\scripts\fix_game_window.py" --timeout 60
.venv\Scripts\python.exe scripts\cap_game.py     # 期望 captured (1280, 720, 3), mean > 100

# 2) daemon 在跑
Get-ScheduledTask -TaskName GDEAgent | Select-Object State
```

- **不要最小化游戏窗口**（会黑屏、截帧失败，整局会崩）。
- 清理停止标记：`Remove-Item data\STOP -ErrorAction SilentlyContinue`。

## 0.2 考试不合格：先「再挑战」，不要结束培育

- 最终审查没考好时，结果页左下是 再挑战（旁边显示「今天免费剩余1次」/再挑战票据 361 张）。
- 点 再挑战 会弹第二段 **再挑战确认**（消耗再挑战道具，重新挑战考试吗？）——这屏只有
  取消 / 确定，**点确定**重打（6405b46 起 bot 会自动点确定，日志 [dialog] retry-confirm）。
- 券用完后才走正常结束流程；结束培育直接判负，所以有券必须重打。
- 再挑战会重新抽技能卡顺序和对手行动，考试表现可能完全不同；建议重打时开 sim_play。

## 1. 起一局

从**主页**开跑（daemon 会先 ensure_home 回主页）：

```powershell
.venv\Scripts\python.exe scripts\agent_cmd.py shell --command "D:\Games\gakumas-agent\.venv\Scripts\python.exe D:\Games\gakumas-agent\scripts\auto_produce.py 300 ep-cplus3" --timeout 2400
```

如果已经手动停在「选择偶像」界面（要确认是**感性**偶像）：

```powershell
... auto_produce.py 300 ep-cplus3 --skip-home ...   # 从当前编成界面接管
```

超时给 2400s（40 分钟），一局目标 ≤20 分钟；到 20 分钟还没结束就记下卡在哪一步。

## 2. 跑完立刻做三件事

```powershell
# ① 一局体检：步数/时长/屏幕耗时分布/课程动作
.venv\Scripts\python.exe scripts\episode_report.py ep-cplus3

# ② 属性标定：每周三维增长（训练确认屏自动记录）
.venv\Scripts\python.exe scripts\calibrate.py

# ③ 最终评价：截图 final_eval_ep-cplus3.png（或看游戏结算屏）

# ④ 逐步复盘（C1）：每步点了哪/为什么/预算下一帧是什么/兑现了没有
.venv\Scripts\python.exe scripts\replay_steps.py --episode ep-cplus3
.venv\Scripts\python.exe scripts\replay_steps.py --episode ep-cplus3 --anomalies   # 只看 lost/failed/stuck

# ⑤ 自动复盘页（P1-6）：auto_produce 局末已自动生成 out/review/<ep>.html（日志 [review] 行）；
#    补生成/换局：
.venv\Scripts\python.exe scripts\review_page.py --episode ep-cplus3

# ⑥ 纯函数状态重放（P1-6）：同观测序列→同状态→三方对账；--verify 退出码=DoD
.venv\Scripts\python.exe scripts\replay_run.py --episode ep-cplus3 --verify
```

## 2.1 自动复盘页与标注闭环（P1-6，T7②③）

**每局一个自包含 HTML**（`out/review/<ep>.html`，gitignore；浏览器直接打开，无外部资源）：

| 区块 | 内容 | 看什么 |
|---|---|---|
| ① 周行动（逐回合） | 周/行动/课程分/三维/体力/note | **黄底 = 同周同行动重复观测**（疑似卡屏/轮转，ep-t1-g 真实故障形态）；null = 没读到（不编造） |
| ② 考试 / ③ 结算 | 期中/期末名次分数全员 / 最终评价 | 缺字段 note 如实显示 |
| ④ 重放一致性 | 指纹 + 三方对账（events 重放 vs 旧格式重建 vs 记录汇总） | **不一致 = 记录器/重放器漂移**，逐字段列出 |
| ⑤ 逐步轨迹 | C1 step_trace（屏幕/动作/坐标/理由/预算/互验/重试） | **红底 = lost/failed/stuck**；合成演示轨迹有显著 banner（不当真机数据） |
| ⑥ 人工标注 | 每行 verdict（ok/bad/unsure）+ 评论 + expected（k=v;k=v） | 见下闭环 |

**标注 → 回归闭环**（人工判断变成永久防线）：

```powershell
# 1) 浏览器打开复盘页，在可疑行打 verdict=bad + expected 修正值（如 lesson_score=152 / outcome=moved），
#    点「导出标注 JSON」→ annotations_<ep>.json（localStorage 自动保存，键含重放指纹前 8 位不串局）
# 2) 转回归用例（只转 verdict=bad 且带 expected 的；期望在转换时冻结，被测代码不给自己出题）
.venv\Scripts\python.exe scripts\annotations_to_regression.py annotations_ep-cplus3.json
# 3) 用例进 tests/fixtures/review_regressions.json，tests/test_review_regressions.py 逐条守：
#    以后重放语义/复盘口径变了（同观测不再同状态），全量 pytest 立刻红
.venv\Scripts\python.exe -m pytest tests/test_review_regressions.py
```

- 周/考试/结算修正 → 作为**新观测事件**追加到该局观测序列，重放**整态冻结**为期望；
  逐步修正 → `summarize_traces` 分类结论（是否异常/outcome 计数）冻结。
- 样例：[docs/review_sample.html](review_sample.html)（记录 = 真机 ep-rule1 C+/5992；
  轨迹 = 合成演示 6 步，页面显著标注 `synthetic-demo`——本局跑在 C1 之前无真机轨迹）。
  夹具里 `provenance=synthetic-demo` 的条目是演示闭环用合成样例，**不是真机 ground truth**；
  真机跑局标注后追加真实案例。
- 重放 CLI 也能独立用：`replay_run.py --episode ep-a --compare data\runs\ep-b.json`
  逐步比对两条观测序列（首个分歧步 + 字段差异）；`--json` 机器可读。

**C1 日志/失败标记速查**（`data/auto_log_<ep>.log` + `data/failures.jsonl` + `data/step_trace.jsonl`）：

| 标记 | 含义 | 怎么办 |
|---|---|---|
| `[priv] …blocked` / `elevation-blocked` | 游戏提权/本进程没有，点击会被 UIPI 丢弃 | 换管理员终端重跑 |
| `[tap] retap …` | 上一击未生效，同坐标重试（≤2 次） | 偶发正常；密集出现查坐标/弹窗识别 |
| `[tap][LOST]` / `tap-lost` | 重试预算用尽仍没生效 | 连续 3 次会主动停局；复盘该步截图+期望，修 root cause |
| `drink-dialog-lost` | 饮料槽位点了 2 次对话没开 | 查槽位坐标 (75,1182)/提权；本课不喝 |
| 局末 `[tap] confirmed=… retaps=… lost=… moved=…` | 本局 tap 互验汇总 | lost>0 逐条复盘 |

## 3. 回来要改什么

| 观察 | 改哪里 |
|---|---|
| `calibrate.py` 给出真实 `周增长/得分` | `src/gkagent/sim/produce.py` 的 `lesson_gain_ratio` |
| 期末名次/评价 | 复核 `exam_base`（现在 85/205，按真机标定） |
| 某类界面卡住/空转 | 先开复盘页 `out/review/<ep>.html`（周重复黄底 + 轨迹异常红底一眼定位）；`data/auto/auto_log_<ep>.log` 里 `[training]`/`[action]` 行 + 截图；C1 起先跑 `replay_steps.py --anomalies` 看 lost/stuck 步的预算与理由；定位后在复盘页标注 → 转回归（§2.1） |
| 出牌明显不合理 | 先看 `[training]` 行里的 `分数/体力` 是否读对，再动 `policy.json` |

## 4. 判定标准

- **成功**：评价 C+ 以上（课题完成）+ 时长 ≤20 分钟。
- **部分成功**：评价到 C+ 但时长超 → 只优化速度（读屏/等待）。
- **失败**：期末仍不合格 → 看 `calibrate.py` 的周增长，和模拟器对比，判断是属性不够还是考试模型偏了。

## 5. 已知坑（都踩过）

1. 窗口被拉宽 → 截 720x999 → `capture()` 抛错；用 `fix_game_window.py` 还原。
2. 窗口最小化 → 黑帧 → 期末连拍崩（已加保护，但仍会缺结算截图）。
3. daemon `shell` 有超时（默认 120s），跑整局必须 `--timeout 2400`。
4. 从非主页起跑要加 `--skip-home`，否则会被 ensure_home 拽回主页打断编成。
5. `policy.json` 的 lesson 参数是**真机默认值**；模拟器扫出的候选在 `policy_sim.json`，验证过再换。
6. **游戏提权/本进程没有（C1 新增检查）**：症状是「截屏读得到、点击全落空、画面一动不动」，
   根因是 UIPI 静默丢消息（GKMSMAA HIF-112 同根因）。启动自查 `[priv]` 会拦；手动跑局务必管理员终端。
