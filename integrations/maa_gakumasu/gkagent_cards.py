"""GDE 的 MAA 出牌钩子（drop-in，复制到 MaaGakumasu 的 agent/custom/action/）。

只接管 ProduceCardsAuto 的决策，截屏/识别/点击全部走 MAA。
- GkAgentCoach：只读，记录推荐，不点击。
- GkAgentCardsAuto：按推荐点击，异常/低置信度返回 False，由 pipeline 回退。
"""

from __future__ import annotations

import json
from pathlib import Path

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_action import CustomAction

from gkagent.integration.maa import MaaCardHit, observation_from_maa
from gkagent.policy.router import RuleCardPolicy

try:
    from utils import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("gde")

POLICY = RuleCardPolicy()
CONFIG = Path("config/cards_policy.json")


def _policy_mode() -> str:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        return str(data.get("policy", "coach"))
    except Exception:
        return "coach"


def _build_observation(context: Context, image):
    reco = context.run_recognition("ProduceRecognitionCards", image)
    hits: list[MaaCardHit] = []
    if reco is not None and getattr(reco, "hit", False):
        for result in reco.all_results:
            hits.append(
                MaaCardHit(
                    label=str(getattr(result, "label", "cards")),
                    box=tuple(int(v) for v in result.box),
                    score=float(getattr(result, "score", 0.0)),
                )
            )
    return observation_from_maa(hits, screen="produce_card")


def _run(context: Context, click: bool) -> bool:
    mode = _policy_mode()
    if mode == "maa":
        return False

    image = context.tasker.controller.post_screencap().wait().get()
    obs = _build_observation(context, image)
    rec = POLICY.recommend(obs)
    if rec is None:
        logger.info("[GDE] 无可出牌")
        return False

    box = obs.raw["boxes"][rec.index]
    x = box[0] + box[2] // 2
    y = box[1] + box[3] // 2
    logger.info(
        f"[GDE] mode={mode} hand={len(obs.hand)} pick={rec.index} "
        f"score={rec.confidence} reason={rec.reason} point=({x},{y})"
    )
    if click and mode == "plugin":
        context.tasker.controller.post_click(x, y).wait()
        return True
    return True


@AgentServer.custom_action("GkAgentCoach")
class GkAgentCoach(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return _run(context, click=False)


@AgentServer.custom_action("GkAgentCardsAuto")
class GkAgentCardsAuto(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return _run(context, click=True)
