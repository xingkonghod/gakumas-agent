# gkagent（自建自动化）

独立于 MAA pipeline 的《学园偶像大师》自动化 agent。

- **只把 MaaFramework 当“手和眼”**：FramePool 截屏 + SendMessage 点击。
- 逻辑、模板、任务、回放全部自己控制，不再受 MAA 的 `base/zh_CN` 图片覆盖问题影响。
- 目标是低 token、低延迟、可回放，后续接模拟器搜索/RL。

## 当前能力

| 命令 | 作用 |
|---|---|
| `capture` | 截取游戏窗口（720×1280） |
| `find` | 离线模板匹配，输出 box/center/score |
| `home` | 认主页 + 点底部主页 tab |
| `click` | 按坐标点击 |
| `task activity_fee` | 主页 → 活动经费 → 关闭弹窗 |

## 环境

- 逻辑/测试：项目自己的 `.venv`（`uv`）
- 设备命令：用 **MaaGakumasu 自带的 Python**（已含 `maa` 包和 MaaFramework 原生库）

```powershell
cd D:\Games\gakumas-agent
uv run pytest -q

# 设备命令走 run.py（自动把 src 加进 sys.path，绕开 embedded python 忽略 PYTHONPATH 的问题）
& 'D:\Games\MaaGakumasu\python\python.exe' 'D:\Games\gakumas-agent\run.py' capture --out shot.png
& 'D:\Games\MaaGakumasu\python\python.exe' 'D:\Games\gakumas-agent\run.py' home
& 'D:\Games\MaaGakumasu\python\python.exe' 'D:\Games\gakumas-agent\run.py' task activity_fee
```

> 游戏是管理员进程，设备命令也要**以管理员运行**；否则 `PostMessage`/`SetCursorPos` 返回 error 5。

## 模板

`templates/`：

- `home.png`：主页「プロデュース」区域（0.979）
- `home_tab.png`：底部「主页」tab
- `activity_fee.png`：左侧「活动经费」按钮（1.0）
- `close.png` / `decide.png`：通用关闭/确定
- `shop.png`：右侧「商店」按钮

新增模板用 `capture` 截图 + `find` 验证分数。

## 目录

```
src/gkagent/
  device/win32.py     MaaFramework Win32Controller 封装 + 找窗口
  vision/matcher.py   OpenCV 模板匹配
  agent.py            ensure_home / click / close_popup / claim_activity_fee
  tasks/              activity_fee + 后续 work/challenge/society
  cli.py              capture / find / home / click / task
templates/            中文 UI 模板
tests/                matcher 单测
```

## 下一步

1. 游戏开着时跑 `task activity_fee` 验证设备链路。
2. 按同样方式加 `work`、`challenge`、`society` 三个任务：先 `capture` 截界面、`find` 定模板，再写状态机。
3. 接 replay：每步存截图 hash + 动作 + 结果，为后续搜索/RL 准备数据。
