# 真机检查清单

前提：游戏已启动并停在主页，MAA 未占用窗口（或已关闭），命令以管理员运行。

## 一键脚本

```powershell
# 右键“以管理员身份运行”，或双击桌面 gkagent-live
D:\Games\gakumas-agent\scripts\live_check.cmd
```

脚本按顺序执行：

1. `capture`：验证窗口/FramePool 截图
2. `home`：验证主页识别 + 主页 tab
3. `task activity_fee`
4. `task work`
5. `task challenge`
6. `task society`

任何一步失败会停下，并保留 `data\live_before.png` 和任务返回的 message。

## 单独排查

```powershell
$env:PYTHONPATH='D:\Games\gakumas-agent\src'
$py='D:\Games\MaaGakumasu\python\python.exe'
$run='D:\Games\gakumas-agent\run.py'

& $py $run capture --out data\shot.png
& $py $run find --image data\shot.png --template home
& $py $run home
& $py $run task activity_fee
```

## GDE 教练模式

1. 确认 `config/cards_policy.json` 是 `{"policy":"coach"}`。
2. 确认 `Produce.json` 的出牌节点是 `GkAgentCoach`。
3. 跑一次培育，检查 MAA 日志里的 `[GDE]` 行：
   - `hand=... pick=... score=... reason=...`
4. 教练模式会继续调用原 `ProduceCardsAuto`，所以点击行为不变。

切插件：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\switch_cards_policy.ps1 -Mode plugin
```

回原版：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\switch_cards_policy.ps1 -Mode maa
```
