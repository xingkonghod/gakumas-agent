# gkagent（GDE + MAA 补缺）

两条线并行，互不替代：

1. **GDE 决策层**：不重写 MAA 的截屏/识别/点击/日常，只接管“出牌决策”。
2. **补齐 MAA 在中文 UI 下失败的 work / challenge / society**：用独立状态机跑，底层复用 MaaFramework 的 FramePool 截屏和 SendMessage 点击。

目标：低 token、低延迟、可回放，后续接模拟器搜索/RL。

## GDE（MAA 出牌钩子）

已安装到 MaaGakumasu：

- `agent/custom/action/gkagent_cards.py`
  - `GkAgentCoach`：只读，复用 `ProduceRecognitionCards` 的框，记录推荐，不点击。
  - `GkAgentCardsAuto`：按推荐点击，点击走 `context.tasker.controller.post_click`。
- `config/cards_policy.json`：`coach` | `plugin` | `maa`
- `python/Lib/site-packages/gkagent.pth`：让 MAA 的 Python 能 import `gkagent`

接法：用脚本切换出牌节点（会备份 `*.bak-gde`）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\switch_cards_policy.ps1 -Mode coach   # 只记录，行为不变
powershell -ExecutionPolicy Bypass -File scripts\switch_cards_policy.ps1 -Mode plugin  # GDE 点击，失败回退
powershell -ExecutionPolicy Bypass -File scripts\switch_cards_policy.ps1 -Mode maa     # 完全回原版
```

`GkAgentCoach` 记录推荐后会调用原 `ProduceCardsAuto`，所以教练模式零行为变化；插件模式没有推荐时也会回退。

## 补齐 MAA 失败任务

独立任务（不依赖 MAA pipeline 运行时）：

| 任务 | 修掉的 MAA 失败点 |
|---|---|
| `activity_fee` | 活动费入口/关闭弹窗 |
| `work` | `WorkHomeFlag` 认不到、工作入口/时长卡住 |
| `challenge` | 打完不返回、次数用完弹窗挡主页 |
| `society` | `SocietyCommitAlready` 阈值 0.95、`SocietyRequestAuto` 中文 UI 崩溃、卡请求弹窗 |
| `daily` | 依次跑上面四个，单个失败不影响后续 |

```powershell
uv run pytest -q        # 87 passed
uv run ruff check src tests
```

## 设备命令（需管理员）

游戏是管理员进程，设备命令也要提权；否则 `PostMessage`/`SetCursorPos` 返回 error 5。

```powershell
# 用 MaaGakumasu 自带的 Python（含 maa 包和 MaaFramework 原生库）
& 'D:\Games\MaaGakumasu\python\python.exe' 'D:\Games\gakumas-agent\run.py' capture --out shot.png
& 'D:\Games\MaaGakumasu\python\python.exe' 'D:\Games\gakumas-agent\run.py' task activity_fee
& 'D:\Games\MaaGakumasu\python\python.exe' 'D:\Games\gakumas-agent\run.py' task daily

# 或提权包装
powershell -ExecutionPolicy Bypass -File D:\Games\gakumas-agent\run_admin.ps1 task daily
```

## 模板

- 主页/通用：`home.png`、`home_tab.png`、`activity_fee.png`、`close.png`、`decide.png`、`shop.png`
- `work_*`、`challenge_*`、`society_*`：从 MAA `resource/base/image` 复制的中文 UI 模板

新增模板用 `capture` 截图 + `find` 验证分数。

## 目录

```
src/gkagent/
  device/win32.py     MaaFramework Win32Controller 封装 + 找窗口
  vision/matcher.py   OpenCV 模板匹配
  agent.py            ensure_home / click / close_popup / claim_activity_fee
  policy/router.py    L1 出牌规则策略（GDE）
  tasks/              activity_fee / work / challenge / society / daily
  cli.py              capture / find / home / click / task
integrations/maa_gakumasu/gkagent_cards.py   GDE 的 MAA CustomAction
templates/            中文 UI 模板
tests/                matcher / policy / 各任务离线测试
```

## 真机待验证

游戏和 MAA 当前未运行，以下需要开机后验证：

1. `capture` / `home` / `task activity_fee` 的设备链路。
2. `work` 的默认偶像/时长是否可直接确定、开始后是否回主页。
3. `challenge` 的竞技场入口固定点、runout 弹窗按钮、战斗结束返回。
4. `society` 的捐赠面板是否可直接确定、关闭募集页后能否回主页。
5. GDE 教练模式：切 `GkAgentCoach` 后看日志推荐是否合理，再切 `GkAgentCardsAuto`。
