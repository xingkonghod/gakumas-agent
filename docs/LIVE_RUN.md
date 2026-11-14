# 真机验证一局（C+）操作手册

> 目标：按模拟器选出的策略跑一局感性培育，拿到 **C+ 以上评价**，并记录三维用于标定。
> 前提：模拟器已就绪（`data/knowledge/policy.json` 的 produce 段生效）。

## 0. 开跑前 3 分钟自检

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
```

## 3. 回来要改什么

| 观察 | 改哪里 |
|---|---|
| `calibrate.py` 给出真实 `周增长/得分` | `src/gkagent/sim/produce.py` 的 `lesson_gain_ratio` |
| 期末名次/评价 | 复核 `exam_base`（现在 85/205，按真机标定） |
| 某类界面卡住/空转 | `data/auto/auto_log_<ep>.log` 里 `[lesson]`/`[action]` 行 + 截图 |
| 出牌明显不合理 | 先看 `[lesson]` 行里的 `分数/体力` 是否读对，再动 `policy.json` |

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
