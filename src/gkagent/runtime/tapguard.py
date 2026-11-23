"""C1 执行层可靠性：tap 确认/重试 + 动作前预算下一帧（纯状态机，离线可测）。

架构参考 GKMSMAA（AGPL-3.0）``follow.py`` rev184/rev254/rev265 与 hiro 三条工程原则
（[docs/HIRO_VIDEO_NOTES.md] / [docs/GROUP_FILES_ANALYSIS.md] §3.3），**全部自写，不拷代码**：

- **动作前预算下一帧**（hiro 原则 3「记账 + 互验」）：每个 tap 先登记
  :class:`TapExpectation`——「点完之后下一帧应该读到什么」；
- **动作后互验**：下一帧拿实际观测对照期望——
  - 期望满足 → ``confirmed``；
  - 画面已推进（签名变了）但期望没满足 → ``moved``：游戏响应了别的东西，
    重新决策，**绝不重试**（rev254 教训：六次 unconfirmed 停机里五次是
    「tap 其实已生效、画面已离开原屏」，再等/再点都是错的）；
  - 画面没变且期望没满足 → tap 丢失：``retry_after`` 秒后同坐标重试，
    最多 ``max_retries`` 次（rev184）；重试预算用尽 → ``lost``，上报调用方
    记日志/failure，交给既有同屏兜底——**绝不静默 SKIP**（用户规则：
    SKIP 只在所有牌都付不起时允许）；
- **加载/暂停/空白帧不判**：:meth:`TapGuard.postpone` 把重试时钟重启
  （rev135：暂停不是游戏的沉默，确认时钟要等它结束再走）。

:class:`PickerGuard` 是两段式选牌（卡位 → 确认/领取）的分级重试：
选中确认后**只重试确认，不再点卡位**（重点已选中的卡可能取消选中）；
选不中才重试卡位；读不到选中态（``selected=None``）时第一次确认发出后
按「已选中」保守处理（宁多重试确认，不重点卡位）。

与截图/点击/Win32 完全解耦：时钟注入，真机与单测共用同一套状态机。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

# 期望类型：点完之后下一帧应该发生什么
KIND_CHANGE = "change"  # 画面（语义签名）应该变化
KIND_DIALOG_OPEN = "dialog-open"  # 对话/弹窗应该出现（words 命中）
KIND_DIALOG_GONE = "dialog-gone"  # 弹窗应该消失（words 全部不再出现）
KIND_OVERLAY_OPEN = "overlay-open"  # 卡片详情浮层应该打开
KIND_OVERLAY_GONE = "overlay-gone"  # 浮层应该关闭
KIND_ANY = "any"  # 只记账，不判生效（无法预算具体期望的兜底 tap）


@dataclass(frozen=True)
class TapExpectation:
    """一次 tap 的「下一帧预算」：kind + 锚点词 + 点击前的语义签名。"""

    kind: str = KIND_CHANGE
    words: tuple[str, ...] = ()
    before: str | tuple | None = None

    def met(self, text: str, signature: str | tuple | None, overlay_open: bool | None) -> bool:
        """实际观测是否满足预算。读不到的观测（None）不算满足。"""
        if self.kind == KIND_ANY:
            return True
        if self.kind == KIND_CHANGE:
            return self.before is not None and signature != self.before
        if self.kind == KIND_DIALOG_OPEN:
            return bool(self.words) and any(word in text for word in self.words)
        if self.kind == KIND_DIALOG_GONE:
            return bool(self.words) and not any(word in text for word in self.words)
        if self.kind == KIND_OVERLAY_OPEN:
            return overlay_open is True
        if self.kind == KIND_OVERLAY_GONE:
            return overlay_open is False
        return False

    def describe(self) -> str:
        """日志用的人类可读期望描述。"""
        words = "/".join(self.words)
        if self.kind == KIND_CHANGE:
            return "画面变化"
        if self.kind == KIND_DIALOG_OPEN:
            return f"弹窗出现（{words}）"
        if self.kind == KIND_DIALOG_GONE:
            return f"弹窗消失（{words}）"
        if self.kind == KIND_OVERLAY_OPEN:
            return "浮层打开"
        if self.kind == KIND_OVERLAY_GONE:
            return "浮层关闭"
        return "任意响应"


def expect_change(before: str | tuple | None) -> TapExpectation:
    return TapExpectation(KIND_CHANGE, before=before)


def expect_dialog_open(words: tuple[str, ...], before: str | tuple | None = None) -> TapExpectation:
    return TapExpectation(KIND_DIALOG_OPEN, tuple(words), before)


def expect_dialog_gone(words: tuple[str, ...], before: str | tuple | None = None) -> TapExpectation:
    return TapExpectation(KIND_DIALOG_GONE, tuple(words), before)


def expect_overlay(opened: bool, before: str | tuple | None = None) -> TapExpectation:
    return TapExpectation(KIND_OVERLAY_OPEN if opened else KIND_OVERLAY_GONE, before=before)


def expect_any(before: str | tuple | None = None) -> TapExpectation:
    return TapExpectation(KIND_ANY, before=before)


@dataclass(frozen=True)
class TapVerdict:
    """一次互验的结论。``outcome`` ∈ none/wait/confirmed/retap/moved/lost。"""

    outcome: str
    action: str = ""
    point: tuple[int, int] | None = None
    screen: str = ""
    reason: str = ""
    tries: int = 0
    expect_kind: str = ""


@dataclass
class _PendingTap:
    action: str
    point: tuple[int, int]
    expect: TapExpectation
    screen: str
    tapped_at: float
    tries: int = 0


class TapGuard:
    """通用 tap 确认/重试状态机（课程出牌另有 LessonPlayGuard，不重复管）。

    用法（auto_produce 主循环）：
    1. 决策产生点击后 ``budget(action, point, expect, screen=...)``；
    2. 下一帧 ``observe(text, signature)``——retap 就同坐标再点一次，
       lost 就记 ``[tap][LOST]`` + failure（连续 lost 由调用方止损停局），
       confirmed/moved 正常重新决策；
    3. 加载/暂停/空白帧 ``postpone()``；进入课程分支 ``cancel()``。
    """

    def __init__(
        self,
        retry_after: float = 1.0,
        max_retries: int = 2,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.retry_after = float(retry_after)
        self.max_retries = int(max_retries)
        self.clock = clock
        self._pending: _PendingTap | None = None
        self.confirmed = 0
        self.retaps = 0
        self.lost = 0
        self.moved = 0

    @property
    def pending(self) -> _PendingTap | None:
        return self._pending

    def budget(
        self,
        action: str,
        point: tuple[int, int],
        expect: TapExpectation,
        *,
        screen: str = "",
        now: float | None = None,
    ) -> None:
        """动作前预算下一帧：登记这次 tap 的期望。新决策覆盖旧预算。"""
        self._pending = _PendingTap(
            action=action,
            point=(int(point[0]), int(point[1])),
            expect=expect,
            screen=screen,
            tapped_at=self.clock() if now is None else float(now),
        )

    def cancel(self) -> None:
        """离开当前屏（例如进入课程分支）：旧预算作废，不参与互验。"""
        self._pending = None

    def postpone(self, now: float | None = None) -> None:
        """加载/暂停/空白帧：不判生效，重试时钟重启（rev135）。"""
        if self._pending is not None:
            self._pending.tapped_at = self.clock() if now is None else float(now)

    def observe(
        self,
        text: str,
        signature: str | tuple | None,
        *,
        overlay_open: bool | None = None,
        now: float | None = None,
    ) -> TapVerdict:
        """拿这一帧的观测互验上一次 tap 的预算。"""
        pending = self._pending
        if pending is None:
            return TapVerdict("none")
        expect = pending.expect
        if expect.met(text, signature, overlay_open):
            self._pending = None
            self.confirmed += 1
            return TapVerdict(
                "confirmed",
                action=pending.action,
                point=pending.point,
                screen=pending.screen,
                reason=f"{pending.action} 生效（期望：{expect.describe()}）",
                tries=pending.tries,
                expect_kind=expect.kind,
            )
        if expect.before is not None and signature != expect.before:
            # 画面已推进到别的屏：tap 大概率已生效（或游戏自己动了），
            # 重新决策，绝不重试（rev254）。
            self._pending = None
            self.moved += 1
            return TapVerdict(
                "moved",
                action=pending.action,
                point=pending.point,
                screen=pending.screen,
                reason=(
                    f"{pending.action} 后画面已推进但期望（{expect.describe()}）未满足，"
                    "重新决策（不重试）"
                ),
                tries=pending.tries,
                expect_kind=expect.kind,
            )
        moment = self.clock() if now is None else float(now)
        if moment - pending.tapped_at < self.retry_after:
            return TapVerdict(
                "wait",
                action=pending.action,
                point=pending.point,
                screen=pending.screen,
                reason=f"{pending.action} 后动画/响应未 settle，等下一帧再判",
                tries=pending.tries,
                expect_kind=expect.kind,
            )
        if pending.tries < self.max_retries:
            pending.tries += 1
            pending.tapped_at = moment
            self.retaps += 1
            return TapVerdict(
                "retap",
                action=pending.action,
                point=pending.point,
                screen=pending.screen,
                reason=(
                    f"上一击 {pending.action} 未生效（期望：{expect.describe()}），"
                    f"同屏重试第 {pending.tries}/{self.max_retries} 次"
                ),
                tries=pending.tries,
                expect_kind=expect.kind,
            )
        self._pending = None
        self.lost += 1
        return TapVerdict(
            "lost",
            action=pending.action,
            point=pending.point,
            screen=pending.screen,
            reason=(
                f"{pending.action} 重试 {self.max_retries} 次仍未生效"
                f"（期望：{expect.describe()}），判为 tap 丢失"
            ),
            tries=pending.tries,
            expect_kind=expect.kind,
        )

    def summary(self) -> str:
        return (
            f"confirmed={self.confirmed} retaps={self.retaps} "
            f"lost={self.lost} moved={self.moved}"
        )


@dataclass(frozen=True)
class PickerVerdict:
    """两段式选牌的一步指令。outcome ∈ none/wait/tap-confirm/retap-slot/retap-confirm/done/failed。"""

    outcome: str
    point: tuple[int, int] | None = None
    reason: str = ""


class PickerGuard:
    """两段式选牌（卡位 → 确认/领取）的分级重试状态机。

    - 卡位点了没选中（``selected=False``）→ 重试卡位（``retap-slot``）；
    - 选中了（``selected=True``）→ 发确认（``tap-confirm``），此后**只重试确认**；
    - 确认点了屏没关 → ``retap-confirm``（绝不回头重点卡位——重点已选中的卡
      可能取消选中，GKMSMAA rev194/rev254 同类教训）；
    - ``selected=None``（读不到选中态）：第一次确认发出后按已选中保守处理；
    - 任一级重试预算用尽 → ``failed``（调用方重置后可重新走完整选牌，
      既有同屏兜底仍然封顶）；屏关了 → ``done``。
    """

    def __init__(
        self,
        max_retries: int = 2,
        retry_after: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_retries = int(max_retries)
        self.retry_after = float(retry_after)
        self.clock = clock
        self.active = False
        self.signature: str = ""
        self.slot_point: tuple[int, int] | None = None
        self.confirm_point: tuple[int, int] | None = None
        self.name = ""
        self.stage = "slot"
        self.slot_tries = 0
        self.confirm_tries = 0
        self.selected_seen = False
        self._last_tap_at = 0.0

    def start(
        self,
        slot_point: tuple[int, int],
        confirm_point: tuple[int, int],
        *,
        name: str = "",
        signature: str = "",
        now: float | None = None,
    ) -> None:
        """进入一个新的 picker 屏：登记卡位/确认落点，状态清零。"""
        self.active = True
        self.signature = signature
        self.slot_point = (int(slot_point[0]), int(slot_point[1]))
        self.confirm_point = (int(confirm_point[0]), int(confirm_point[1]))
        self.name = name
        self.stage = "slot"
        self.slot_tries = 0
        self.confirm_tries = 0
        self.selected_seen = False
        self._last_tap_at = self.clock() if now is None else float(now)

    def reset(self) -> None:
        self.active = False
        self.slot_point = None
        self.confirm_point = None
        self.stage = "slot"
        self.slot_tries = 0
        self.confirm_tries = 0
        self.selected_seen = False

    def slot_tapped(self, now: float | None = None) -> None:
        """卡位点击已发出。"""
        self.stage = "slot"
        self._last_tap_at = self.clock() if now is None else float(now)

    def confirm_tapped(self, now: float | None = None) -> None:
        """确认/领取点击已发出：此后只重试确认，不回头点卡位。"""
        self.stage = "confirm"
        self._last_tap_at = self.clock() if now is None else float(now)

    def observe(
        self,
        *,
        selected: bool | None,
        screen_gone: bool,
        now: float | None = None,
    ) -> PickerVerdict:
        """喂这一帧的 picker 观测（选中态 + 屏是否已关），返回下一步指令。"""
        if not self.active:
            return PickerVerdict("none")
        if screen_gone:
            self.reset()
            return PickerVerdict("done", reason=f"{self.name or 'picker'} 已关闭，选牌完成")
        if selected is True:
            self.selected_seen = True
        elif selected is False:
            self.selected_seen = False
            if self.stage == "confirm":
                # 选中态丢了（被取消/读回不一致）：回到卡位阶段重选
                self.stage = "slot"
        moment = self.clock() if now is None else float(now)
        if self.stage == "slot":
            if self.selected_seen:
                return PickerVerdict(
                    "tap-confirm",
                    point=self.confirm_point,
                    reason=f"{self.name or 'picker'} 已选中，点确认/领取",
                )
            if moment - self._last_tap_at < self.retry_after:
                return PickerVerdict("wait", reason="选卡点击后等动画/选中态 settle")
            if self.slot_tries < self.max_retries:
                self.slot_tries += 1
                self._last_tap_at = moment
                return PickerVerdict(
                    "retap-slot",
                    point=self.slot_point,
                    reason=(
                        f"{self.name or 'picker'} 卡位未选中，重试第 "
                        f"{self.slot_tries}/{self.max_retries} 次"
                    ),
                )
            self.reset()
            return PickerVerdict(
                "failed",
                reason=f"选卡点击 {self.max_retries} 次重试仍未选中（tap 丢失）",
            )
        # stage == "confirm"
        if moment - self._last_tap_at < self.retry_after:
            return PickerVerdict("wait", reason="确认点击后等响应 settle")
        if self.confirm_tries < self.max_retries:
            self.confirm_tries += 1
            self._last_tap_at = moment
            return PickerVerdict(
                "retap-confirm",
                point=self.confirm_point,
                reason=(
                    f"{self.name or 'picker'} 确认后屏未关，只重试确认第 "
                    f"{self.confirm_tries}/{self.max_retries} 次（不重点卡位）"
                ),
            )
        self.reset()
        return PickerVerdict(
            "failed",
            reason=f"确认/领取点击 {self.max_retries} 次重试仍未推进（tap 丢失）",
        )
