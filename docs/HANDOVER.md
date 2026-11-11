# GDE × MaaGakumasu 交接文档

> 最后更新：2026-11-11 23:30（Asia/Shanghai）
> 仓库：`D:\Games\gakumas-agent`（branch `master`）
> 游戏：DMM 学园偶像大师（本地化中文），管理员进程

---

## 0. 一句话现状

**代码、卡库、OCR、回放/BC/ONNX 管线都已可用；真机自动化卡在“游戏窗口被最小化 + Windows 前台锁”这一层，produce 入口点击还不稳定。**

---

## 1. 定位

- **MAA（MaaGakumasu）**：负责截屏/识别/点击、日常、商店、启动
- **GDE（本项目）**：MAA 的**决策层**，卡牌/道具/事件/考试/升级的决策 + 训练闭环
- 原则：能用规则/搜索解决的，不调模型；能用小模型解决的，不调 LLM

---

## 2. 已完成模块

| 模块 | 路径 | 说明 |
|---|---|---|
| 设备层 | `src/gkagent/device/win32.py` | MaaFramework Win32Controller；默认 `PostMessage` 点击（不动光标）；`click_force` 物理点击（光标恢复）；`capture()` 在窗口最小化时直接报错 |
| 感知-模板 | `src/gkagent/vision/matcher.py` | OpenCV `TM_CCOEFF_NORMED` |
| 感知-OCR | `src/gkagent/vision/ocr.py` | RapidOCR；2x 放大、置信度过滤（0.4）、去重、坐标还原 |
| 感知-界面 | `src/gkagent/vision/recognize.py` | 关键词规则 → 屏幕类型 + 置信度 |
| 感知-手牌 | `src/gkagent/vision/cards.py` | 卡框/费用/AP/推荐位识别 |
| 卡库 | `src/gkagent/data/cards_db.py` + `data/card_library.json` | 1724 张培育卡，效果文本 → 价值分 |
| 道具库 | `src/gkagent/data/items_db.py` + `data/item_library.json` | 697 个道具/饮料，同样打分 |
| Tier | `src/gkagent/data/tier.py` | game8 H.I.F（2026-11）SS 档；升级优先级排序 |
| 导航 | `src/gkagent/nav.py` | OCR 找文字 → 点击 → 回主页；`click_verified` 点击后校验+偏移重试 |
| 产出任务 | `src/gkagent/tasks/produce.py` | 培育状态机（SSR/场景/支援/主界面/出牌/事件/考试/结算），15s 阶段兜底，回放记录 |
| 升级任务 | `src/gkagent/tasks/upgrade.py` | OCR 列表 → Tier 规划 → 强化/特训；遇「付费/购买」中止 |
| 其他任务 | `activity_fee/work/challenge/society/daily.py` | 日常任务骨架（真机未全部验证） |
| 策略 | `policy/search.py`、`policy/ocr_cards.py`、`policy/router.py` | 贪心搜索、OCR 读卡详情、规则路由 |
| 训练 | `runtime/replay.py`、`training/bc.py`、`scripts/train_bc.py` | replay → BC → ONNX（已验证管线，数据少） |
| MAA 集成 | `integration/maa.py` + MaaGakumasu 内 CustomAction | 教练/插件模式已装 |

---

## 3. 关键运行方式

### 3.1 常驻 agent（推荐，免 UAC）

```powershell
# 启动（计划任务，最高权限，不弹 UAC）
schtasks /Run /TN GDEAgent

# 发送命令（非管理员即可）
python D:\Games\gakumas-agent\.venv\Scripts\python.exe scripts\agent_cmd.py home
... agent_cmd.py produce
... agent_cmd.py click --x 360 --y 1005 --force
... agent_cmd.py shell --command "D:\Games\gakumas-agent\scripts\force_show_game.ps1"
... agent_cmd.py quit
```

命令通道：`data/agent_cmd.json` → 结果 `data/agent_result.json`。
**改代码后必须**：`agent_cmd.py quit` → `schtasks /Run /TN GDEAgent`，否则跑的是旧进程。

### 3.2 管理员终端直跑

```powershell
cd D:\Games\gakumas-agent
$env:PYTHONPATH='D:\Games\gakumas-agent\src'
& 'D:\Games\MaaGakumasu\python\python.exe' run.py task produce --ocr-cards
& 'D:\Games\MaaGakumasu\python\python.exe' run.py task upgrade --kind support --limit 3 --dry-run
```

### 3.3 截图

```powershell
# 管理员（推荐，能抓管理员游戏窗口）
python scripts/agent_cmd.py shell --command "D:\Games\gakumas-agent\scripts\cap_game.cmd"
# 结果：data/new_account.png，正常应为 720x1280、mean > 100
```

---

## 4. 环境配置（已做）

| 项 | 值/命令 |
|---|---|
| Clash Verge TUN | `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\verge.yaml` → `enable_tun_mode: true`；系统代理 127.0.0.1:7897 |
| UAC 免弹窗 | `ConsentPromptBehaviorAdmin=0`、`PromptOnSecureDesktop=0`（**需重启生效**） |
| DMM 自动管理员 | `HKCU\...\AppCompatFlags\Layers` → `D:\DMM\GamePlayer\DMMGamePlayer.exe = ~ RUNASADMIN` |
| 常驻任务 | `GDEAgent`（RunLevel Highest）→ `python agent_daemon.py` |
| OCR | rapidocr 已装在项目 venv（3.11）和 MaaGakumasu python（3.12） |
| 游戏窗口 | `UnityWndClass`，标题 `gakumas`；窗口句柄重启会变 |

---

## 5. 当前真机状态与阻塞

### 5.1 游戏窗口被最小化（已定位）

- 现象：截图全黑（720x1396、mean 12），produce 报“没回主页/进不了培育”
- 实际：`UnityWndClass 'gakumas'` 处于 `IsIconic=True`、`rect=-16000`
- 恢复：管理员执行 `scripts/force_show_game.ps1`，恢复后截图 720x1280、mean≈226
- 已加保护：`Win32Device.capture()` 在最小化时直接抛错，不再默默返回黑图

### 5.2 前台锁（当前主要问题）

- 前台是 Edge/DMM，游戏在后台
- Windows 前台锁使 `SetForegroundWindow` 失效 → 物理点击落到别的窗口，produce 点不到「プロデュース」
- 已尝试并回退：最小化→恢复（会搞坏游戏渲染，**不要再用**）
- 已加：`AttachThreadInput` 绕过前台锁（commit `d5273b3`，`GetCurrentThreadId` 已改 kernel32）
- **尚未在最新 daemon 上验证**

### 5.3 produce 入口识别

- `_go_home` 依赖模板 `home`/`home_tab`/`produce_entry`，当前本地化主页**匹配不稳定**
- `_enter_produce` 有固定点兜底 `(360,1005)`，但只有游戏在前台时才有效
- 最近失败信息：`进入培育失败：主页未识别到「プロデュース」入口，或点击后未进入培育页面`

---

## 6. 已知 Bug / 待验证

1. `AttachThreadInput` 前台修复未真机验证（需重启 daemon）
2. 支援卡强化界面入口文字未实测（`Navigator` 按「支援卡」匹配）
3. 日文支援卡名 → 中文卡库**没有对照表**，Tier 表暂时匹配不上中文 UI
4. 回放只有 7 条且动作全为 index 0，BC 模型退化
5. 道具/饮料选择界面尚未接进 FSM
6. UAC 设置需**重启**才生效；DMM 的 RUNASADMIN 在重启前仍可能弹窗

---

## 7. 下一步优先级

| 优先级 | 事项 |
|---|---|
| P0 | 重启 daemon 验证 AttachThreadInput；游戏前置时跑通 produce 入口 |
| P0 | 用 OCR 找「プロデュース」文字定位，替代模板/固定点（`Navigator` 已具备文字点击） |
| P1 | 实测支援卡界面：`upgrade --kind support --limit 3 --dry-run`，校准入口/按钮文字 |
| P1 | 补日→中支援卡名对照（本地化字典/社区表） |
| P2 | 收集多样回放 → 重训 BC → ONNX |
| P2 | 写 supervisor 循环：检测最小化→恢复、daemon 掉线→重启、空闲→重跑 produce |
| P3 | 完整培育/考试/结算；活动/打榜/课题 |

---

## 8. 安全与回退

- **付费钻**：升级任务遇「付费/钻石/购买」文本会中止；不要主动花
- **UAC 回退**：
  ```powershell
  reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v ConsentPromptBehaviorAdmin /t REG_DWORD /d 5 /f
  reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v PromptOnSecureDesktop /t REG_DWORD /d 1 /f
  reg delete "HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" /v "D:\DMM\GamePlayer\DMMGamePlayer.exe" /f
  ```
- **不要**对游戏窗口做最小化→恢复（会黑屏）
- 游戏重启后窗口句柄会变，截图/点击前先确认 `IsIconic=False`

---

## 9. 测试与提交

```powershell
cd D:\Games\gakumas-agent
uv run pytest            # produce 57 + vision/upgrade/tier/items 等
uv run ruff check src tests
```

最近提交：

```text
d5273b3 fix(click): attach input thread to bypass foreground lock
3049a25 fix(device): reject capture when game window is minimized
72c8880 revert(click): remove minimize/restore trick that broke game rendering
078a16c fix(click): force foreground via minimize/restore before physical click
d3ab2c5 fix(produce): best-effort home then enter produce with fallback
c98bc68 fix(produce): fixed-point force-click fallback for produce entry
4b76ca3 fix(produce): graceful force-click fallback for fake devices
115b253 fix(produce): skip go_home when produce entry visible; force-click entry
bbf5084 feat(vision): OCR upscale/confidence/dedupe, screen recognizer, verified clicks
42547bd feat(upgrade): unified Navigator + UpgradeTask using card/item library + tier plan
0426780 feat(tier): game8 H.I.F tier table + upgrade priority planner
f1c6dfa feat(items): item/drink value library + OCR policy matches cards or items
```

---

## 10. 关键路径速查

```text
D:\Games\gakumas-agent\                 仓库
  src\gkagent\                          库代码
  scripts\agent_daemon.py              常驻 agent（计划任务）
  scripts\agent_cmd.py                 发命令（非管理员）
  scripts\cap_game.cmd / shot_dmm.cmd  截图
  scripts\force_show_game.ps1          恢复最小化窗口
  data\agent_cmd.json / agent_result.json   命令/结果
  data\new_account.png                 最近游戏截图
  data\replays\produce.sqlite3         回放库
  data\models\bc_produce.npz / .onnx   BC/ONNX
  templates\                           MAA/识图模板
D:\Games\MaaGakumasu\                   MAA（资源/自定义动作）
D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans   112 个本地化 JSON
```
