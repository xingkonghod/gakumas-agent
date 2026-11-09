# 与 MaaGakumasu 集成

目标：**不重写感知/点击**，只替换“出牌决策”这一层。

MaaGakumasu 的扩展点是 MaaFramework 的 `CustomAction` / `CustomRecognition`：

```python
from maa.context import Context
from maa.custom_action import CustomAction
from maa.agent.agent_server import AgentServer
```

现有 `ProduceCardsAuto`（`agent/custom/action/produce.py:518`）的流程：

1. `post_screencap()` 截图；
2. `run_recognition("ProduceRecognitionCards", image)` 得到手牌框，label 只有
   `suggestions` / `cards` / `useless`；
3. `_get_card_info()` 选一张；
4. `post_click(box 中心)` 点击；
5. 无牌时 `run_task("ProduceRecognitionSkipRound")`。

GDE 只接管第 3 步。

---

## 方式 A：教练模式（只读，先做）

新增一个 custom action，只记录、不点击：

```python
@AgentServer.custom_action("GkAgentCoach")
class GkAgentCoach(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        image = context.tasker.controller.post_screencap().wait().get()
        reco = context.run_recognition("ProduceRecognitionCards", image)
        obs = observation_from_maa(reco, context)      # gkagent.integration.maa
        action = gde.act(obs)                           # 本地策略
        logger.info(f"[GDE] state={obs} recommend={action}")
        return True                                     # 不点击
```

把流水线里的 `ProduceCardsAuto` 临时换成 `GkAgentCoach`，就能在真实对局里收集
“MAA 会怎么打 / GDE 会怎么打”的对照数据，零风险。

---

## 方式 B：插件模式（接管出牌）

```python
@AgentServer.custom_action("GkAgentCardsAuto")
class GkAgentCardsAuto(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        while not context.tasker.stopping:
            if not is_playing_card(context):
                break
            image = context.tasker.controller.post_screencap().wait().get()
            reco = context.run_recognition("ProduceRecognitionCards", image)
            obs = observation_from_maa(reco, context)
            action = gde.act(obs)                       # 返回 card_index / skip
            if action.kind == "play_card":
                box = obs.raw["boxes"][action.index]
                x, y = box_center(box)
                context.tasker.controller.post_click(x, y).wait()
                time.sleep(0.3)
                context.tasker.controller.post_click(x, y).wait()
                wait_until_playable(context)
            elif action.kind == "end_turn":
                context.run_task("ProduceRecognitionSkipRound")
                wait_until_playable(context)
            else:
                time.sleep(0.2)
        return True
```

### 需要改的地方

1. `agent/custom/action/gkagent_cards.py`：新增上面的类。
2. `agent/custom/action/__init__.py`：import 它，确保注册。
3. `resource/` 里把出牌节点的 `custom_action` 从 `ProduceCardsAuto` 改成
   `GkAgentCardsAuto`（或复制一份 pipeline，用配置切换）。
4. 配置开关：`config/cards_policy.json` → `{"policy": "maa" | "gde"}`；
   `gde` 异常时自动回退 `maa`。

### 不建议做的事

- 不要让 GDE 自己 `post_click`：会绕开 MAA 的限速/停止/异常处理。
- 不要改 MAA 的识别节点：`ProduceRecognitionCards` 继续用，保证坐标一致。
- 不要在插件里再截一次屏：直接用 `image`，避免两次截图不同步。

---

## 数据映射

`maa.py` 只做纯函数转换，不 import `maa`，方便单测：

| MAA 字段 | Observation 字段 |
|---|---|
| `result.label` | `Card.kind`（先粗分） |
| `result.box` | `raw["boxes"][i]` |
| `result.score` | `raw["scores"][i]` |
| `reco_detail.hit` | `confidence` 的粗代理 |
| 屏幕 ID（节点名） | `screen` |

卡 ID 识别是 L2 的事：先用卡图模板/分类器把 `cards` 框映射到 `card_id`，
再补 `cost/kind`。没有卡 ID 之前，策略只能做“框级”决策。

---

## 点击映射

```python
def box_center(box: list[int]) -> tuple[int, int]:
    x, y, w, h = box
    return x + w // 2, y + h // 2
```

坐标必须来自同一张截图；MAA 的 `post_click` 使用客户区坐标，和识别结果一致。

---

## 回退与安全

- `gde` 超时/异常/低置信度 → 返回 `None`，调用方回退 `ProduceCardsAuto`。
- 每局最多 N 次回退；超过则停任务。
- 教练模式永远不点击，适合长期挂着收集数据。

---

## 许可证

MaaGakumasu 是 **AGPL-3.0**。如果修改它的代码并分发，整体需按 AGPL 开源；
个人本地使用不受影响。GDE 本体的 MIT 许可不适用于“修改后的 MaaGakumasu 分发物”。
