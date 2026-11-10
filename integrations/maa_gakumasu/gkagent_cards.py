"""GDE 的 MAA 出牌钩子（drop-in，复制到 MaaGakumasu 的 agent/custom/action/）。

- GkAgentCoach：只记录推荐，然后调用原 ProduceCardsAuto（行为不变，零风险）。
- GkAgentCardsAuto：按 GDE 推荐点击；没有推荐时回退原 ProduceCardsAuto。
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


def _fallback(context: Context, argv: CustomAction.RunArg) -> bool:
    """回退 MAA 原出牌逻辑（教练模式也走这里，保证行为不变）。"""
    try:
        from custom.action.produce import ProduceCardsAuto

        return ProduceCardsAuto().run(context, argv)
    except Exception:
        logger.exception("[GDE] fallback ProduceCardsAuto failed")
        return False


def _recommend(context: Context):
    image = context.tasker.controller.post_screencap().wait().get()
    obs = _build_observation(context, image)
    return POLICY.recommend(obs), obs


def _run(context: Context, argv: CustomAction.RunArg, click: bool) -> bool:
    mode = _policy_mode()
    if mode == "maa":
        return _fallback(context, argv)

    rec, obs = _recommend(context)
    if rec is None:
        logger.info("[GDE] 无可出牌，回退 ProduceCardsAuto")
        return _fallback(context, argv)

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

    # coach：只记录，实际点击仍由原逻辑执行
    return _fallback(context, argv)


@AgentServer.custom_action("GkAgentCoach")
class GkAgentCoach(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return _run(context, argv, click=False)


@AgentServer.custom_action("GkAgentCardsAuto")
class GkAgentCardsAuto(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        return _run(context, argv, click=True)
