"""自动推进培育：OCR 导航 + 出牌策略 + 指标记录，一次跑 N 步。

用法（管理员或经 agent daemon shell 调用）：
    python scripts/auto_produce.py 40 [episode_id]

产物：
- data/auto/step_NNN.png        每步截图
- data/auto_log.txt             人类可读日志
- data/metrics.jsonl            每步指标（时延/点击回执）
- data/replays/produce.sqlite3  出牌回放（训练数据）

退出条件：回到主页 / 步数用尽 / 连续 5 步无动作 / F12 / data/STOP。
"""

from __future__ import annotations

import ctypes
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

import cv2

from gkagent.agent import Agent
from gkagent.data.card_costs import CardCosts
from gkagent.data.cards_db import CardLibrary
from gkagent.data.items_db import ItemLibrary
from gkagent.data.master import MasterData
from gkagent.data.run_record import RunRecorder, action_of
from gkagent.device.win32 import USER32, Win32Device, find_game_hwnd, user_idle_ms
from gkagent.nav import Navigator
from gkagent.policy.lesson import LessonPolicy, RuleFallbackBlocked
from gkagent.policy.lesson_pick import decide_lesson_pick
from gkagent.policy.ocr_cards import OcrCardPolicy
from gkagent.policy.search import SearchPolicy
from gkagent.runtime.metrics import EpisodeRecord, MetricsLog, StepRecord
from gkagent.runtime.replay import ReplayDB
from gkagent.sim.exam_estimate import SimCard, estimate_score
from gkagent.sim.exam_plan import ExamDrawPlan, load_exam_setups
from gkagent.sim.lesson import CardSpec
from gkagent.sim.play_choice import MAX_APPROX_DECK, plan_pick
from gkagent.tasks.produce import ProduceTask
from gkagent.tasks.produce_ui import (
    LESSON_SKIP_POINT,
    LESSON_WORDS,
    SETTLE_CENTER_TAP,
    TURN_END_YES,
    LessonPlayGuard,
    ProduceDriver,
    SameScreenGuard,
    clean_card_name,
    clean_lesson_state,
    has_selected_ui,
    lesson_hand_signature,
    lesson_stamina_gate,
    lesson_turn_signature,
    parse_stamina,
    pick_lesson_card,
)
from gkagent.vision.cards import scan_hand
from gkagent.vision.hand_names import HandPick, pick_hand_card
from gkagent.vision.lesson import LessonReader, read_stamina_preview
from gkagent.vision.matcher import TemplateMatcher
from gkagent.vision.ocr import OcrEngine

LOG = ROOT / "data" / "auto_log.txt"
SHOT_DIR = ROOT / "data" / "auto"
METRICS = ROOT / "data" / "metrics.jsonl"
FAILURES = ROOT / "data" / "failures.jsonl"


def log_failure(episode: str, step: int, kind: str, detail: str, extra: dict | None = None) -> None:
    """失败日志：每出现一次失败（课程 FAILED / 局未完成 / 卡死自停）都落一条。"""
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "episode": episode,
        "step": step,
        "kind": kind,
        "detail": detail[:300],
    }
    if extra:
        record.update(extra)
    with FAILURES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

PRODUCE_MARKERS = (
    "定期公演",
    "请选择行动",
    "选择偶像",
    "选择支援卡",
    "选择回忆",
    "开始确认",
    "剩余回合数",
)
HOME_MARKERS = ("亲密度", "活动经费", "商店", "扭蛋")

# 暂停门参数：点击注入的光标移动/还原会被 GetLastInputInfo 当成"用户输入"，而且真机
# 实测**还原输入会晚于 note_self_input 落盘**，0.6s 窗口不够（ep-sup1 奖励屏连点后
# 3 次误触发，每次卡 8-30s）。窗口放到 3s：bot 点完 3s 内的输入都算自己的。
# 如果"判定有人在操作"但画面 digest 与上一步完全相同，也直接放行（bot 自身卡住）。
SELF_INPUT_EXCLUDE_S = 3.0
USER_IDLE_GATE_MS = 800
PAUSE_REFUSAL_BACKOFF_S = 1.0

# ---- 窗口前置检查（F#9）：每步开始前确保能截图/点击 -------------------------
# 真机正确 client 尺寸就是 540x960；720x1280 是截图内部缩放后的尺寸（F#10），
# 把窗口改成 720x1280 会多出 1 行（shape=(1281,720,3)），所以只恢复 540x960。
PRODUCE_CLIENT_SIZE = (540, 960)
SW_RESTORE = 9
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
WINDOW_RESTORE_ATTEMPTS = 3
WINDOW_RESTORE_FAIL_LIMIT = 5

# 加载帧快速路径连续多少步后强制完整 OCR（F#27：通信错误弹窗会被加载模板盖住）
LOADING_FAST_OCR_EVERY = 12
# 课程帧快速路径（模板命中 skip_round/health，省整屏 OCR）连续多少步后强制完整 OCR。
# 必须定期回看：SKIP 后的「回合结束」确认框盖在课程上时，两个模板仍然命中，
# 若一直用 text="剩余回合" 就永远看不到弹框 → card/force-skip 死循环（ep-finish4）。
LESSON_FAST_OCR_EVERY = 5


def client_size(hwnd: int, user32=None) -> tuple[int, int]:
    """当前窗口 client 尺寸；拿不到返回 ``(0, 0)``（调用方按异常处理）。"""
    api = USER32 if user32 is None else user32
    rect = wintypes.RECT()
    if not api.GetClientRect(int(hwnd), ctypes.byref(rect)):
        return (0, 0)
    return int(rect.right), int(rect.bottom)


def window_frame(hwnd: int, user32=None) -> tuple[int, int]:
    """窗口边框+标题栏占的宽/高：``SetWindowPos`` 设的是外框，client 要减掉这一圈。"""
    api = USER32 if user32 is None else user32
    window = wintypes.RECT()
    client = wintypes.RECT()
    if not api.GetWindowRect(int(hwnd), ctypes.byref(window)):
        return (0, 0)
    if not api.GetClientRect(int(hwnd), ctypes.byref(client)):
        return (0, 0)
    frame_w = (window.right - window.left) - (client.right - client.left)
    frame_h = (window.bottom - window.top) - (client.bottom - client.top)
    return (max(int(frame_w), 0), max(int(frame_h), 0))


def ensure_window(
    hwnd: int,
    *,
    user32=None,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = WINDOW_RESTORE_ATTEMPTS,
) -> str:
    """每步前置：窗口最小化 → 还原；client 不是 540x960 → 用 SetWindowPos 改回来。

    F#9：窗口被最小化后所有点击都落到不存在的地方，之前只在截图失败（RuntimeError）
    后才补救，已经空转 12 次。这里在**决策/点击之前**检查，异常先恢复再继续。

    返回 ``"ok"``（本来就正常）/ ``"restored"``（发生过恢复且现在正常）/
    ``"failed"``（多次尝试后仍最小化或尺寸不对，调用方应等待而不是继续点击）。
    """
    api = USER32 if user32 is None else user32
    target_w, target_h = PRODUCE_CLIENT_SIZE
    changed = False
    for _ in range(max(1, int(attempts))):
        if int(api.IsIconic(int(hwnd))):
            api.ShowWindow(int(hwnd), SW_RESTORE)
            changed = True
            sleep(0.4)
            if int(api.IsIconic(int(hwnd))):
                continue  # 还原失败：重试，别把"还是最小化"当成正常
        width, height = client_size(hwnd, user32=api)
        if (width, height) == (target_w, target_h):
            return "restored" if changed else "ok"
        if width <= 0 or height <= 0:
            sleep(0.4)
            continue
        frame_w, frame_h = window_frame(hwnd, user32=api)
        api.SetWindowPos(
            int(hwnd),
            0,
            0,
            0,
            target_w + frame_w,
            target_h + frame_h,
            SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE,
        )
        changed = True
        sleep(0.4)
    if int(api.IsIconic(int(hwnd))) or client_size(hwnd, user32=api) != (target_w, target_h):
        return "failed"
    return "restored" if changed else "ok"


class PauseGate:
    """暂停门：判断"用户是否真的在操作"，并排除 bot 自己注入的输入。

    背景：点击走 SendMessageWithCursorPos（光标移到目标→发消息→还原），Windows 的
    ``GetLastInputInfo`` 会把这类注入算成"用户刚有输入"；下一次点击前的
    ``user_idle_ms()`` 就只剩几百毫秒，于是误判"用户正在操作"，出牌暂停空转。

    这里在每次 bot 自己点击后记录 ``self_last_input_ts``；如果最后一次输入发生在该
    时间戳之后 ``self_exclude_s`` 的窗口内（真机实测光标还原的输入会晚于记账落盘，
    0.6s 不够，所以默认 3.0s），就认为那是 bot 自己的输入，不算用户操作。
    ``last_input_ts <= self_last_input_ts + 3.0s`` 正是这个窗口。

    记时间戳分两次（点击前 + 点击后）：MAA 的点击消息是排队的，注入输入可能落在
    ``post_click().wait()`` 返回之后，点击前先记一次能把这段"在途输入"也盖住。

    最后一道兜底（F#11）：如果仍判定"用户在操作"，但画面 digest 与上一步**完全
    相同**，那就不是用户在玩（真实操作会翻页/选牌/换镜头），而是 bot 自己卡住 →
    直接放行。真机 ep-cplus13 在结算页连刷 5 次 ``[pause] user-active`` 后停机，
    就是缺这道兜底。
    """

    def __init__(
        self,
        idle_ms: Callable[[], int] = user_idle_ms,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        gate_ms: int = USER_IDLE_GATE_MS,
        self_exclude_s: float = SELF_INPUT_EXCLUDE_S,
        refusal_backoff_s: float = PAUSE_REFUSAL_BACKOFF_S,
    ) -> None:
        self.idle_ms = idle_ms
        self.clock = clock
        self.sleep = sleep
        self.gate_ms = int(gate_ms)
        self.self_exclude_s = float(self_exclude_s)
        self.refusal_backoff_s = float(refusal_backoff_s)
        self.self_last_input_ts: float | None = None
        self._last_digest: str | None = None
        # 统计：暂停门生效次数 / 因"同一画面"直接放行次数（真机复盘用）
        self.pause_hits = 0
        self.same_digest_passes = 0
        self.last_reason = ""

    def note_self_input(self, at: float | None = None) -> None:
        """记录一次 bot 自己点击完成的时间（点击返回后调用）。"""
        self.self_last_input_ts = self.clock() if at is None else float(at)

    def user_operating(self) -> bool:
        """最近 gate_ms 内有输入，且该输入不是 bot 自己注入的 → 用户正在操作。"""
        idle = int(self.idle_ms())
        if idle >= self.gate_ms:
            return False
        if self.self_last_input_ts is not None:
            # 最后一次输入发生的时间戳（系统 tick 换算到 monotonic 轴）
            last_input_ts = self.clock() - idle / 1000.0
            if last_input_ts <= self.self_last_input_ts + self.self_exclude_s:
                return False
        return True

    def observe(self, digest: str | None) -> bool:
        """每步开头登记画面；返回是否要无视暂停门继续点击。

        F#11 兜底：判定"用户在操作"、但这一帧 digest 与上一步**完全相同**时，不可能
        是真的有人在玩（真实操作会翻页/选牌/换镜头），更像 bot 自己上一次点击注入的
        光标移动被算成了用户输入，或者画面已经僵住。此时直接放行，避免像 ep-cplus13
        那样连刷 ``[pause] user-active`` 空转到停机。

        画面只要有变化就保持暂停（用户可能正在操作），返回 ``False``。
        """
        previous = self._last_digest
        self._last_digest = digest
        if not self.user_operating():
            self.last_reason = ""
            return False
        self.pause_hits += 1
        if digest is not None and previous is not None and digest == previous:
            # 与上一步同一画面：判定为 bot 自身输入/画面僵住 → 直接放行
            self.same_digest_passes += 1
            self.last_reason = "same-digest"
            return True
        self.last_reason = "user-operating"
        return False

    def guarded_click(
        self,
        click_fn: Callable[..., bool],
        x: int,
        y: int,
        delay: float = 0.4,
        force: bool = False,
    ) -> bool:
        """带暂停门的点击：真实用户操作时不点（退避后返回 False）。

        ``force=True`` 是 ``observe`` 判定"同一画面/bot 自身输入"后的放行：无视暂停门
        继续执行。点击**前后各记一次** ``self_last_input_ts``（真机实测光标还原的输入
        会晚于点击返回落盘，只记点击后仍会漏），让下一步把这次注入从"用户输入"里排除。
        """
        if not force and self.user_operating():
            self.sleep(self.refusal_backoff_s)
            return False
        self.note_self_input()  # 先记：盖住排队中的注入（光标移动到目标的输入）
        result = click_fn(int(x), int(y), delay=delay, respect_user=False)
        self.note_self_input()  # 再记：盖住点击过程中的光标还原输入
        return result is not False


class SelfInputClickGuard:
    """把暂停门装到设备上：接管 ``click`` / ``click_force`` / ``swipe`` 三个入口。

    ``Win32Device.click`` 自带的 respect_user 门只读 ``GetLastInputInfo``，分不清
    bot 自己注入的输入，还会先空等 1.2s 才返回 False。只覆盖 ``click_force`` 不够：
    ``ProduceTask``/``Navigator`` 走的是 ``device.click(...)``，``device.swipe(...)``
    也会移动光标刷新 ``GetLastInputInfo``——这些路径都会让下一步误判"用户正在操作"，
    也就是 F#11 在真机上仍然复现的原因。install() 把三个入口全部接管，并保存**原始
    方法**（调用时从 ``self._raw_click`` 取，不做局部缓存，避免补丁被旧引用绕过）。
    """

    def __init__(self, device, gate: PauseGate) -> None:
        self.device = device
        self.gate = gate
        self.force = False
        self._raw_click: Callable[..., bool] | None = None
        self._raw_swipe: Callable[..., object] | None = None

    def click(self, x: int, y: int, delay: float = 0.4, respect_user: bool = False) -> bool:
        """暂停门点击入口；``respect_user`` 只为兼容旧调用签名，统一由 PauseGate 判断。"""
        raw = self._raw_click
        if raw is None:
            raise RuntimeError("SelfInputClickGuard not installed; call install() first")
        return self.gate.guarded_click(raw, x, y, delay=delay, force=self.force)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> bool:
        """滑动也走暂停门，并把这次注入记成 bot 自身输入（否则下一步又误判用户操作）。"""
        if self._raw_swipe is None:
            raise RuntimeError("SelfInputClickGuard not installed; call install() first")
        if not self.force and self.gate.user_operating():
            self.gate.sleep(self.gate.refusal_backoff_s)
            return False
        result = self._raw_swipe(int(x1), int(y1), int(x2), int(y2), int(duration_ms))
        self.gate.note_self_input()
        return result is not False

    def install(self) -> SelfInputClickGuard:
        device = self.device
        self._raw_click = device.click
        self._raw_swipe = getattr(device, "swipe", None)
        device.click = self.click
        device.click_force = self.click
        if self._raw_swipe is not None:
            device.swipe = self.swipe
        return self


def build_task(episode: str, engine: OcrEngine, card_library: CardLibrary | None = None) -> ProduceTask:
    def _hand_reader(image):
        scan = scan_hand(image)
        return list(scan.cards), [tuple(card.box) for card in scan.cards]

    # 按卡名/效果文本查卡库打分（权重已改成打分优先），决定出哪张
    # 用绝对路径加载 master：进程 cwd 不一定在项目根目录（supervisor/daemon 启动时踩过坑）
    master_root = ROOT / "data" / "master"
    card_library = card_library or CardLibrary(MasterData(master_root))
    item_library = ItemLibrary()
    ocr_policy = OcrCardPolicy(
        engine,
        card_library,
        detail_roi=(0, 480, 720, 400),
        extra_libraries=[item_library],
    )
    replay = ReplayDB(str(ROOT / "data" / "replays" / "produce.sqlite3"), run_id=episode)
    return ProduceTask(
        enable_lessons=True,
        hand_reader=_hand_reader,
        card_policy=SearchPolicy(),
        replay_db=replay,
        ocr_policy=ocr_policy,
    )


def is_home(text: str) -> bool:
    return "主页" in text and any(word in text for word in HOME_MARKERS)


def run_exam_estimate(agent, task, driver, image):
    """期末前估分：逐张点开手牌 → OCR 读卡名/价值 → 15 局蒙特卡洛。"""
    policy = getattr(task, "ocr_policy", None)
    if policy is None:
        return None
    hand = scan_hand(image)
    if not hand.boxes:
        return None
    cards: list[SimCard] = []
    for index, box in enumerate(hand.boxes[:4]):
        cx = box[0] + box[2] // 2
        cy = box[1] + box[3] // 2
        agent.device.click_force(cx, cy)
        time.sleep(0.35)
        detail = agent.shot()
        cost = hand.cards[index].cost if index < len(hand.cards) else None
        reading = policy.read(detail, cost)
        cards.append(SimCard(reading.name or f"card{index}", float(reading.value or 0), int(cost or 1)))
    if not cards:
        return None
    return estimate_score(cards, turns=6, trials=15, seed=11)


def should_retry(score: float | None, mean: float) -> bool:
    """第一把打完：分数不到期望的 90% 就免费重开。"""
    if score is None or mean <= 0:
        return False
    return score < mean * 0.9


def stop_requested() -> bool:
    """F12 是急停键；data/STOP 文件也能停。"""
    if (ROOT / "data" / "STOP").exists():
        return True
    return bool(USER32.GetAsyncKeyState(0x7B) & 0x8000)


def arg_value(name: str, default: str | None = None) -> str | None:
    """从 ``sys.argv`` 里取 ``--name value`` / ``--name=value``（这个脚本一直用裸 argv）。"""
    prefix = name + "="
    for index, item in enumerate(sys.argv):
        if item == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        if item.startswith(prefix):
            return item[len(prefix) :]
    return default


def restore_window() -> None:
    """最小化/黑屏时恢复游戏窗口（本进程已是管理员）。"""
    script = ROOT / "scripts" / "force_show_game.ps1"
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            timeout=30,
            capture_output=True,
            check=False,
        )
    except Exception:  # noqa: BLE001, S110 - 窗口恢复失败不阻断跑局
        pass
    time.sleep(2.0)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    crash_log = ROOT / "data" / "crash.log"

    def _hook(exc_type, exc_value, exc_tb):
        import traceback

        with crash_log.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] crash\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=handle)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    episode = sys.argv[2] if len(sys.argv) > 2 else time.strftime("ep-%Y%m%d-%H%M%S")
    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window", file=sys.stderr)
        return 2
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    # 暂停门：排除 bot 自己点击注入的"用户输入"；点击统一走 click_force 补丁
    pause_gate = PauseGate()
    click_guard = SelfInputClickGuard(agent.device, pause_gate).install()
    # --ignore-user：无人值守跑完整局时无视"用户正在操作"门限（否则用户在电脑前
    # 打字/挪鼠标会让所有点击被拒 → 画面僵住 → 同屏强制 SKIP 死循环）。
    ignore_user = "--ignore-user" in sys.argv
    if ignore_user:
        pause_gate.gate_ms = 0
    engine = OcrEngine()
    card_lib = CardLibrary(MasterData(ROOT / "data" / "master"))
    task = build_task(episode, engine, card_lib)
    driver = ProduceDriver(ocr=engine)
    # 出牌"眼睛"和"脑子"：读游戏给的分数预览/体力/回合，按分数÷体力出牌
    cost_cache = CardCosts()
    lesson_reader = LessonReader(engine, cards=card_lib, costs=cost_cache)
    # 真机出牌引擎：--engine 优先，其次 policy.json 的 produce.engine。
    # 用户规则（2026-11-21）：**bot 不许回退 rules**。入口默认 expectimax（不再
    # 默认 rules）；只有显式 `--engine rules` 才用规则引擎（仅 A/B 对照/离线复现）。
    engine_override = (arg_value("--engine") or "").strip().lower()
    produce_engine = str(driver._produce_params().get("engine") or "").strip().lower()
    allowed_engines = ("rules", "expectimax", "beam", "uinet")
    requested_engine = engine_override or produce_engine
    engine_source = (
        "--engine"
        if engine_override
        else ("policy.json produce.engine" if produce_engine else "默认(expectimax)")
    )
    lesson_engine = requested_engine or "expectimax"
    if lesson_engine not in allowed_engines:
        print(
            f"invalid engine {lesson_engine!r}（可选 {', '.join(allowed_engines)}）"
            "；用户规则禁止静默回退 rules",
            file=sys.stderr,
        )
        return 2
    lesson_policy = LessonPolicy(buffs=lesson_reader.buffs, engine=lesson_engine)
    # 搜索引擎（非 rules）一旦无法决策就中止本局，绝不接老规则路径。
    strict_engine = lesson_policy.engine != "rules"
    # 考试牌序计划（完全信息搜索数据源）：--exam-setup 指向 build_exam_setup.py 的产物。
    # 计划挂到策略后，每回合会拿采集推出来的牌序跟实机手牌核对；核对不上自动停用，
    # 行为退回期望搜索（没有采集数据时也完全等价于现状）。
    exam_setup_path = arg_value("--exam-setup", str(ROOT / "out" / "exam_setup.json"))
    # 开局先回主页：上一轮可能停在支援卡/偶像/强化页面，否则前 8 步全是 unknown-tap
    # --skip-home：已经手动摆好在"选择偶像/支援卡"界面时跳过，否则会被拽回主页
    if "--skip-home" not in sys.argv:
        try:
            Navigator(agent, engine).ensure_home()
        except Exception:  # noqa: BLE001, S110 - 回主页失败交给后续 unknown-tap
            pass
    metrics = MetricsLog(METRICS)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []
    log_lines.append(f"[engine] 出牌引擎 = {lesson_policy.engine}（来源：{engine_source}）")
    if strict_engine:
        log_lines.append(
            "[engine] 用户规则：规则回退已禁用——搜索无法决策会记 [engine][BLOCKED] "
            "并中止本局，不再静默退回 rules"
        )
    else:
        log_lines.append(
            "[engine] ⚠️ 显式 rules 引擎：仅用于 A/B 对照/离线复现；正常整局跑局不要用"
        )
    if ignore_user:
        log_lines.append("[engine] --ignore-user：忽略暂停门（无人值守跑完整局用）")
    idle = 0
    # 连续「无可用决策」计数（ep-t1-k：手牌读不到时点中位卡兜底会无限空转）
    no_decision_streak = 0
    pause_streak = 0
    last_stamina: int | None = None
    burst_count = 0
    bad_cards: set[str] = set()
    last_pick_name: str | None = None
    same_pick_count = 0
    # 课程出牌防死循环：详情浮层挡路时关浮层换牌，同一坐标 3 次没推进就 SKIP
    lesson_guard = LessonPlayGuard()
    # 同屏兜底：课程状态连续 5 步没变 → 强制 SKIP；连续 10 步 → 记 [stuck] 退出本局。
    # 像素 digest 不能用（角色呼吸/卡面闪光/视频噪点每帧都变），喂语义签名。
    same_screen = SameScreenGuard()
    lesson_sig_before_pick: tuple | None = None
    action_key: tuple[str, str] | None = None
    action_streak = 0
    final_phase = False
    done = False
    stuck_exit = False
    seen_produce = False
    produce_end_seen = False
    started_at = time.time()
    prev_digest: str | None = None
    pending: StepRecord | None = None
    markers: list[str] = []
    unknown_streak = 0
    last_signature: tuple[str, str, str] | None = None
    same_action_count = 0
    lesson_pending: tuple[tuple[int, int], tuple] | None = None
    drink_used = False
    # 窗口前置检查（F#9）：连续恢复失败就停，不带着"点击全落空"的状态空转到超时
    window_fail_streak = 0
    # 加载帧快速路径连续计数（F#27）：超过阈值强制 OCR，避免漏看通信错误弹窗
    loading_fast_streak = 0
    # 课程帧快速路径连续计数：超过阈值强制整屏 OCR，避免漏看「回合结束」确认框
    lesson_fast_streak = 0
    # 考试/试镜模式（F#17）：本局是否已进入过考试（只打一次 [exam-mode] 进入日志）
    exam_seen = False
    # 考试牌序计划（T3 实时接线）：启动时先读一次候选；真正的场次在进入考试时由
    # ExamPlanSelector 用第一回合实机手牌挑（见循环里的 [exam-plan] 分支）。
    exam_plans = (
        [ExamDrawPlan(item) for item in load_exam_setups(exam_setup_path)]
        if exam_setup_path
        else []
    )
    exam_plan_selector = None
    exam_setup_mtime: float | None = None
    prev_exam_turns: int | None = None
    prev_exam_mode = False
    if exam_plans:
        log_lines.append(
            f"[exam-plan] 载入 {len(exam_plans)} 个候选：{exam_setup_path}"
            f"（进入考试时按首回合手牌自动挑，engine={lesson_policy.engine}）"
        )
    # sim 实时出牌的近似牌库（真机拿不到完整牌组，把见过的手牌并进来，最多 12 张）
    sim_deck: list[CardSpec] = []
    # 期末估分（run_exam_estimate）先停用：它要逐张点开手牌，一局多花 10-20s，等速度达标再接回来
    # ---- 跑局数据管道（data/runs/<episode>.json）：周/课/考/结算增量落盘 ----------
    # 每写一条就原子 flush；被超时 kill 也保住已跑完的周，模拟器标定才有真机锚点。
    recorder = RunRecorder(episode)
    last_attrs: tuple[int, int, int] | None = None
    pending_week: dict | None = None
    pending_action_advanced = False
    last_recorded_week = 0
    phase = "mid"  # 行动页看到「最终截止」后置 final，考试记录 kind 用它
    lesson_active = False
    last_lesson_score: int | None = None
    last_exam_signature: str | None = None
    last_final_signature: tuple | None = None
    log_lines.append(f"[record] 数据文件 {recorder.path}")

    def flush_pending(changed: bool | None) -> None:
        nonlocal pending
        if pending is not None:
            pending.changed = changed
            metrics.write(pending)
            pending = None

    def _log_record(message: str) -> None:
        log_lines.append(f"[record] {message}")

    def end_lesson() -> int | None:
        """课程帧消失的瞬间：把本课得分落盘（读不到写 null，不拿属性增量顶替）。

        课程结束时先把周记录以 attrs_after=null 落盘（保住 lesson_score），
        下一周行动页读到三维后再补写同一 (week, action)，不追加第二条。
        """
        nonlocal lesson_active, last_lesson_score
        if not lesson_active:
            return last_lesson_score
        score = last_lesson_score
        pending = pending_week
        if pending is None or pending["action"] != "lesson" or not pending_action_advanced:
            # 没有对应的周行动：宁可丢弃也不把分数记到别的周/别的行动上
            _log_record(f"课程结束 lesson_score={score}（无对应周行动，丢弃）")
            lesson_active = False
            last_lesson_score = None
            return score
        # 先把本周记录落下来（attrs 稍后补），再挂 lesson_score：note_lesson
        # 只补最后一条 lesson，保证上一周缺分记录不会被这一周填错。
        if not pending.get("recorded"):
            recorder.note_action(pending["week"], "lesson", None, None)
            pending["recorded"] = True
        recorder.note_lesson(score)
        _log_record(f"课程结束 lesson_score={score}")
        lesson_active = False
        last_lesson_score = None
        return score

    def finalize_week(attrs, stamina, *, why: str) -> dict | None:
        """在下一个行动页/考试/结算处补全上一周行动的 attrs_after / stamina。"""
        nonlocal pending_week, pending_action_advanced, last_recorded_week
        pending = pending_week
        if pending is None or not pending_action_advanced:
            return None
        record = recorder.note_action(pending["week"], pending["action"], attrs, stamina)
        if pending["week"] is not None:
            last_recorded_week = pending["week"]
        _log_record(
            f"周 {pending['week']} {pending['action']} "
            f"attrs={list(attrs) if attrs else None} stamina={stamina} ({why})"
        )
        pending_week = None
        pending_action_advanced = False
        return record

    def start_week_action(action: str, week: int | None, week_phase: str | None) -> None:
        """行动页点下行动时登记本周行动；同一屏重复点只更新意图，不重复开周。"""
        nonlocal pending_week, pending_action_advanced, last_recorded_week, phase
        if week_phase == "final":
            phase = "final"
        if pending_week is not None:
            if pending_week["action"] != action:
                pending_week["action"] = action
                pending_week["week"] = week or pending_week["week"]
            return
        if week is None:
            week = last_recorded_week + 1
        pending_week = {"week": week, "action": action, "recorded": False}
        pending_action_advanced = False
        _log_record(f"周行动开始 week={week} action={action}")

    def record_exam(image, text: str) -> None:
        """考试结算屏：整屏 OCR 解析 1st..6th + Pt，记 kind/rank/score/others。

        同一屏只尝试一次（签名去重）；解析失败只记日志，绝不编造名次/分数。
        """
        nonlocal last_exam_signature
        signature = re.sub(r"\d+", "#", text)[:120]
        if signature == last_exam_signature:
            return
        last_exam_signature = signature
        result = driver.read_exam_result(image)
        if result is None:
            _log_record("考试结算屏未解析出分数行，跳过")
            return
        if pending_week is not None:
            end_lesson()
            finalize_week(attrs_now, parse_stamina(text), why="exam-result")
        last_exam = recorder.data["exams"][-1] if recorder.data["exams"] else None
        if (
            last_exam is not None
            and last_exam.get("kind") == phase
            and last_exam.get("rank") == result.get("rank")
            and last_exam.get("score") == result.get("score")
        ):
            # 同一场考试的结算屏可能停留多步；文本微变时别重复追加
            _log_record("考试结算屏重复，跳过")
            return
        exam = recorder.note_exam(
            phase, result.get("rank"), result.get("score"), result.get("others")
        )
        _log_record(
            f"{phase} 考试 rank={exam.get('rank')} score={exam.get('score')} "
            f"others={exam.get('others')}"
        )

    def record_final(image, text: str) -> None:
        """最终结算屏：固定小框读 grade/eval_points，三维用最后一次采样。"""
        nonlocal last_final_signature
        result = driver.read_final_result(image)
        if result is None:
            return
        signature = (result.get("grade"), result.get("eval_points"))
        if signature == last_final_signature:
            return
        last_final_signature = signature
        if pending_week is not None:
            end_lesson()
            finalize_week(None, None, why="final")
        # 结算页一般不显示三维；先试读一次，读不到才退回最后一次采样（并在 note 里标 stale）
        final_attrs = None
        try:
            final_attrs = driver.read_attrs(image, allow_full=False)
        except Exception:  # noqa: BLE001 - 结算页读不到不影响流程
            final_attrs = None
        final = recorder.note_final(
            attrs=final_attrs or last_attrs,
            rank=None,
            exam_score=None,
            eval_points=result.get("eval_points"),
            grade=result.get("grade"),
        )
        _log_record(
            f"最终结算 grade={final.get('grade')} eval_points={final.get('eval_points')} "
            f"attrs={final.get('attrs')} rank={final.get('rank')} "
            f"exam_score={final.get('exam_score')}"
        )

    for step in range(1, steps + 1):
        if stop_requested():
            log_lines.append(f"{step:03d} [stop] 急停触发")
            break
        # F#9：窗口最小化/尺寸被改后，点击全部落到不存在的地方（真机空转 12 次才发现）。
        # 每步决策之前先校验并恢复；恢复不了就等待，绝不带着坏窗口继续点。
        window_state = ensure_window(hwnd)
        if window_state == "restored":
            window_fail_streak = 0
            log_lines.append(f"{step:03d} [window] 已恢复（之前最小化/尺寸不对）")
        elif window_state == "failed":
            window_fail_streak += 1
            log_lines.append(
                f"{step:03d} [window] 恢复失败（最小化/尺寸不对），等待后重试"
                f"（{window_fail_streak}/{WINDOW_RESTORE_FAIL_LIMIT}）"
            )
            time.sleep(1.5)
            if window_fail_streak >= WINDOW_RESTORE_FAIL_LIMIT:
                log_lines.append(
                    f"{step:03d} [window] 连续 {window_fail_streak} 步恢复不了窗口，停止"
                )
                break
            continue
        else:
            window_fail_streak = 0
        try:
            t_start = time.perf_counter()
            image = agent.shot()
            capture_ms = (time.perf_counter() - t_start) * 1000
        except RuntimeError as exc:
            log_lines.append(f"{step:03d} [capture] {exc}; 尝试恢复窗口")
            idle += 1
            restore_window()
            continue
        digest = str(hash(image[::17, ::17].tobytes()))
        flush_pending(prev_digest is not None and digest != prev_digest)
        prev_digest = digest
        cv2.imwrite(str(SHOT_DIR / f"step_{step:03d}.png"), image)
        # 暂停门兜底（F#11）：判定"用户在操作"但画面 digest 与上一步完全一样 →
        # bot 自身输入/画面僵住，直接放行（本步起点击无视暂停门），不再空转。
        force_continue = pause_gate.observe(digest)
        click_guard.force = force_continue
        if force_continue:
            log_lines.append(
                f"{step:03d} [pause] 画面与上一步相同（bot 自身输入/卡住），直接放行"
            )

        t_ocr = time.perf_counter()
        # 卡住兜底：上一屏与这一屏相同（same_screen.repeats>=1）时，课程/加载快速路径
        # 和两段式确认都不可信——强制整屏 OCR，并清掉卡住的两段式确认态。
        # 真机 ep-finish4/5/6：SKIP 后弹「回合结束」确认框，快速路径仍命中课程模板 →
        # text 永远只有「剩余回合」，弹框没人点「是」，拍死在同一个屏上。
        stuck_fast = same_screen.repeats >= 1
        force_full_ocr = stuck_fast
        if stuck_fast:
            lesson_pending = None
        if lesson_pending is not None:
            # 两段式出牌的确认步：不需要任何 OCR，直接点上一张卡确认（省 3-5s/步）
            corner_lines = []
            corner_text = ""
            corner_lesson = True
            lesson_fast = False
            loading_fast = False
            lines = []
            text = "剩余回合"
            ocr_ms = 0.0
        else:
            # 快速路径 1（先做，~10ms）：模板命中「跳过回合/体力」→ 课程帧。
            # 课程帧的剩余回合/体力由 LessonReader 的快路径读，这里不再整屏 OCR（省 ~3.7s/步）。
            lesson_fast = (
                agent.matcher.find("produce_skip_round", image, threshold=0.85) is not None
                or agent.matcher.find("produce_health", image, threshold=0.70) is not None
            )
            # 快速路径 2：加载帧模板命中 → 直接当 loading 等待，不 OCR。
            # 真机 ep-t1-d（F#27）：通信错误弹窗（获取资产失败 E203）盖在加载帧上时模板
            # 仍然命中，于是每步只走 loading 快速路径、从不 OCR，永远看不到「重试」按钮，
            # 白烧 200+ 步。连续加载超过 LOADING_FAST_OCR_EVERY 步就强制走一次完整 OCR。
            loading_fast = (not lesson_fast) and (
                agent.matcher.find("produce_loading", image, threshold=0.90) is not None
            )
            if loading_fast:
                loading_fast_streak += 1
                if loading_fast_streak >= LOADING_FAST_OCR_EVERY:
                    loading_fast = False
                    loading_fast_streak = 0
            else:
                loading_fast_streak = 0
            if lesson_fast:
                lesson_fast_streak += 1
                if force_full_ocr or lesson_fast_streak >= LESSON_FAST_OCR_EVERY:
                    # 定期回看整屏：SKIP 后的「回合结束」确认框盖在课程上时，
                    # produce_skip_round / produce_health 模板仍然命中；一直用
                    # text="剩余回合" 就永远看不到弹框（ep-finish4 死循环）。
                    lesson_fast_streak = 0
                    lines = driver.engine().read(image)
                    text = driver.text_of(lines)
                    corner_lines = lines
                    corner_text = text
                    corner_lesson = True
                    ocr_ms = (time.perf_counter() - t_ocr) * 1000
                else:
                    corner_lines = []
                    corner_text = ""
                    corner_lesson = True
                    lines = []
                    text = "剩余回合"
                    ocr_ms = 0.0
            else:
                lesson_fast_streak = 0
                if loading_fast:
                    # 模板已经命中加载帧：连左上角状态条都不用读。
                    corner_lines = []
                    corner_text = ""
                    corner_lesson = False
                    lines = []
                    text = "LOADING"
                else:
                    # 快速路径 0：先只读左上角状态条（~6% 面积）。认出「剩余回合/CLEAR/PERFECT」= 课程帧
                    corner_lines = driver.engine().read(image, driver.corner_roi)
                    corner_text = driver.text_of(corner_lines)
                    corner_lesson = any(
                        word in corner_text for word in ("剩余回合", "CLEAR", "PERFECT")
                    )
                    if corner_lesson and force_full_ocr:
                        # 画面卡住时不能只读左上角：整屏 OCR 才能看到遮罩弹窗
                        lines = driver.engine().read(image)
                        text = driver.text_of(lines)
                        corner_lines = lines
                        corner_text = text
                    elif corner_lesson:
                        lines = corner_lines
                        text = corner_text
                    else:
                        # 常用屏走固定小框分区识别（加载/剧情/事件/行动/训练/外出/领奖）；
                        # 只有认不出的屏才整屏 OCR。旧实现每步都对底部 60% + 顶部做检测，
                        # 真机 6-14s/步里 80% 耗在这里。
                        lines = driver.read_fast(image)
                        text = driver.text_of(lines)
                ocr_ms = (time.perf_counter() - t_ocr) * 1000

        # 课程帧消失 = 本课结束：立刻把 lesson_score 落盘（拿不到分数写 null）。
        # 放在读三维之前，课程数据在下一周行动页/考试页出现前就已安全写盘。
        in_lesson_frame = (
            lesson_pending is not None
            or lesson_fast
            or any(word in text for word in LESSON_WORDS)
        )
        if lesson_active and not in_lesson_frame:
            end_lesson()

        if any(word in text for word in PRODUCE_MARKERS):
            seen_produce = True
            markers.append(text[:40])
        # 期末试镜之后进入「结算期」：评分/评价画面常常一闪而过，
        # 每步先连拍几张再动作，确保能抓到最终评价
        # 全程记录三维：固定小框直接读大数字（/1000 小字 OCR 常读不出，整屏正则抓不到）
        t_attrs = time.perf_counter()
        attrs_now = None
        try:
            attrs_now = driver.read_attrs(image, text_hint=text)
            if attrs_now is not None:
                last_attrs = attrs_now
                from gkagent.data.calibration import record as _record_attrs

                _record_attrs(attrs_now, tag="run")
        except Exception:  # noqa: BLE001, S110 - 标定失败不影响培育
            pass
        finally:
            ocr_ms += (time.perf_counter() - t_attrs) * 1000

        # 只有同时出现「评价字母 + 3位以上分数」才算真结算；
        # 只匹配「合否条件」会在考试介绍页误触发，导致每步连拍空转。
        looks_final = bool(
            re.search(r"(?:評価|评价)[^A-Za-z0-9]{0,6}([SABCDE][+\-－]?)", text)
            and re.search(r"(\d{3,6})\s*(?:pt|Pt|PT|点)", text)
        )
        # 跑局数据：最终结算屏（真机 190647 =「最终培育评价」C+/5577）。
        # 结算页一闪而过，每步都试一次固定小框读取（两项都读不到会立刻返回）。
        if looks_final or "最终培育评价" in text or ("最终" in text and "评价" in text):
            record_final(image, text)
        if not final_phase and looks_final:
            final_phase = True
            burst_count = 0
            log_lines.append(f"{step:03d} [final] 检测到最终评价，进入连拍模式")
        if final_phase and burst_count < 6:
            for burst in range(2):
                time.sleep(0.7)
                try:
                    extra = agent.shot()
                except RuntimeError:
                    # 窗口被最小化/黑屏时不值得让整局崩掉，结算帧抓不到就算了
                    log_lines.append(f"{step:03d} [final] burst 抓帧失败，跳过")
                    break
                burst_count += 1
                burst_path = SHOT_DIR / f"final_{episode}_{step:03d}_{burst}.png"
                cv2.imwrite(str(burst_path), extra)
                extra_text = driver.text_of(driver.engine().read(extra))
                grade = None
                grade_match = re.search(
                    r"(?:评级|评价|評価|判定)[^A-Za-z0-9]{0,6}([SABCDE][+＋]?)", extra_text
                )
                if grade_match:
                    grade = grade_match.group(1)
                score_match = re.search(r"(\d{3,6})\s*(?:pt|Pt|PT|分|点)", extra_text)
                if grade is None and "评价" not in extra_text and "評価" not in extra_text:
                    continue
                record = {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "episode": episode,
                    "step": step,
                    "grade": grade,
                    "score": score_match.group(1) if score_match else None,
                    "text": extra_text[:200],
                    "screenshot": str(burst_path),
                }
                with (ROOT / "data" / "final_grades.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                log_lines.append(
                    f"{step:03d} [final] 评价 grade={grade} score={record['score']} {burst_path}"
                )
        # 失败画面（课程/考试 FAILED、不合格）：落失败日志 + 截图
        if "FAILED" in text or "不合格" in text:
            fail_path = SHOT_DIR / f"fail_{episode}_{step:03d}.png"
            cv2.imwrite(str(fail_path), image)
            log_failure(
                episode,
                step,
                "lesson-failed" if "FAILED" in text else "exam-failed",
                text,
                {
                    "attribute": driver.lesson_attribute,
                    "stamina": last_stamina,
                    "screenshot": str(fail_path),
                },
            )
            log_lines.append(f"{step:03d} [fail] FAILED/不合格 已记录 {fail_path}")
        # 试镜/考试排名结果：把 1st..6th + Pt 写进 exam_results.jsonl；同时跑局记录
        if re.search(r"\d(?:st|nd|rd|th)", text) and re.search(r"\d+\s*Pt", text):
            record_exam(image, text)
            ranks = []
            for line in lines:
                if re.fullmatch(r"\d(?:st|nd|rd|th)", line.text.strip()):
                    ranks.append((line.text.strip(), line.box))
            if len(ranks) >= 2:
                entry = {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "episode": episode,
                    "step": step,
                    "ranks": [r[0] for r in ranks],
                    "text": text[:200],
                }
                with (ROOT / "data" / "exam_results.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                log_lines.append(f"{step:03d} [exam-rank] {' '.join(r[0] for r in ranks)}")
        # 最终评价画面单独存档（轮转 step_NNN 会覆盖）
        if (
            "最终培育评价" in text
            or ("最终" in text and "评价" in text)
            or ("最終" in text and "評価" in text)
        ):
            final_path = SHOT_DIR / f"final_eval_{episode}.png"
            if not final_path.exists():
                cv2.imwrite(str(final_path), image)
                log_lines.append(f"{step:03d} [final] 最终评价/倍率截图已存 {final_path}")
        # 培育结束的强信号：最终评价 / 结算后成就页（粉丝数）
        if "最终培育评价" in text or ("粉丝" in text and "成就" in text):
            produce_end_seen = True
        if produce_end_seen and (
            is_home(text) or "定期公演" in text or "プロデュース" in text
        ):
            log_lines.append(f"{step:03d} [home] 培育结束，回到入口/主页")
            done = True
            break
        if seen_produce and is_home(text):
            log_lines.append(f"{step:03d} [home] 培育结束，已回主页")
            done = True
            break

        status_text = text
        # 课程帧不再补读左上角状态条：剩余回合/体力由 LessonReader 的快路径读（~20ms）
        # 原来这里每次多一次整屏 OCR（3.7s/步），一局能省十几分钟。

        t_decide = time.perf_counter()
        clicked: bool | None = None
        # 1.5) 「回合结束」确认框（SKIP 后必出）——lesson_fast 分支不走 driver.decide，
        # 必须在这里先处理，否则 SKIP 后弹框没人点「是」→ 同屏计数→强制 SKIP→再弹框，
        # 整个课程变成 card/force-skip 死循环（真机 ep-finish3 第 47-94 步）。
        if "结束回合" in text and (
            "尚可使用技能卡" in text
            or "确定要结束回合" in text
            or "下次起不再显示" in text
        ):
            action_name, screen_name = "end-turn-yes", "lesson"
            exam_mode = False
            clicked = agent.device.click_force(*TURN_END_YES)
            time.sleep(0.8)
            result = "[training] 回合结束确认框 → 点「是」"
            idle = 0
            same_screen.reset()
        elif lesson_fast or any(word in text for word in LESSON_WORDS):
            action_name, screen_name = "card", "lesson"
            unknown_streak = 0
            if pending_week is not None:
                # 已经离开行动页：上一周行动确实开始执行了
                pending_action_advanced = True
            # F#17：考试/试镜页顶部有 1st..6th 排名条。考试里 SKIP = 白送回合
            # （ep-sup1 期中 4th/228Pt，1st=597 直接不合格），所以先识别，再把
            # 体力门 / 同屏兜底 / 策略的 SKIP 全部禁掉，强制每回合出一张牌。
            exam_mode = driver.exam_mode(image, lines)
            if exam_mode and not exam_seen:
                exam_seen = True
                log_lines.append(
                    f"{step:03d} [exam-mode] 顶部排名条命中：考试/试镜，"
                    "本场禁止 SKIP（体力门/同屏兜底/策略）"
                )
            if exam_mode and pending_week is not None:
                # 考试开始前把「考试周之前的最后一个周行动」结掉（期中、期末各一次）：
                # 考试周没有行动页，不在这里补全会丢最后一周的 attrs/stamina。
                if lesson_active:
                    end_lesson()
                exam_stamina = parse_stamina(text)
                if exam_stamina is None:
                    exam_stamina = last_stamina
                finalize_week(attrs_now, exam_stamina, why="exam-start")
            # 出牌策略开关（policy.json produce.sim_play，默认 false）：开着才跑模拟器 rollout
            sim_play = bool(driver._produce_params().get("sim_play"))
            # 课程分支不重置防死循环签名（否则课程卡死永远不触发），交给通用签名计数
            # 体力管理：低于 8 且还有回合，用一次饮料（每节课最多一次）
            stamina = parse_stamina(status_text or text)
            if stamina is not None:
                last_stamina = stamina
            turns_match = re.search(r"剩余回合数\s*(\d+)", text)
            turns = int(turns_match.group(1)) if turns_match else None
            # 读一次局面（剩余回合/体力/分数预览/手牌名），后面出牌不再重复 OCR。
            # 考试页顶部多了排名条，数值位置和课程不同（vision.lesson.LAYOUTS），必须传 kind。
            lesson_state = lesson_reader.read(image, kind="audition" if exam_mode else "lesson")
            if lesson_state.stamina is not None:
                stamina = lesson_state.stamina
                last_stamina = stamina
            if lesson_state.turns_left is not None:
                turns = lesson_state.turns_left
            # 课程帧：记录本课实时总分（右上角），课程结束/CLEAR 时用作 lesson_score。
            # 考试帧不记（exam_mode=True），考试得分走考试结算屏。
            if not exam_mode:
                lesson_active = True
                if lesson_state.score is not None and lesson_state.score > 0:
                    last_lesson_score = lesson_state.score
            # 考试牌序计划（T3 实时接线）：不在启动时锁定场次——进入考试时把候选
            # 交给 ExamPlanSelector，用第一回合实机手牌自动挑对上的那一份；
            # out/exam_setup.json 更新（build_exam_setup --current）会在考试入口自动重载。
            if exam_mode:
                turns_now = lesson_state.turns_left
                new_exam = prev_exam_turns is None or (
                    turns_now is not None and turns_now > prev_exam_turns
                )
                if turns_now is not None:
                    prev_exam_turns = turns_now
                if new_exam and exam_plan_selector is not None:
                    # 上一场（期中/期末）的候选先收尾，换新的一批
                    try:
                        log_lines.append(f"[exam-plan] {exam_plan_selector.summary()}")
                    except Exception as exc:  # noqa: BLE001 - 复盘日志不能影响跑局
                        log_lines.append(f"[exam-plan] summary 失败：{exc}")
                    lesson_policy.attach_draw_plan(None)
                    exam_plan_selector = None
                if exam_setup_path:
                    try:
                        mtime = Path(exam_setup_path).stat().st_mtime
                    except OSError:
                        mtime = None
                    if mtime is not None and mtime != exam_setup_mtime:
                        # out/exam_setup.json 更新了（考试前跑 build_exam_setup --current）
                        exam_setup_mtime = mtime
                        exam_plans = [
                            ExamDrawPlan(item)
                            for item in load_exam_setups(exam_setup_path)
                        ]
                        if exam_plan_selector is not None:
                            lesson_policy.attach_draw_plan(None)
                            exam_plan_selector = None
                        log_lines.append(
                            f"{step:03d} [exam-plan] 重载 {len(exam_plans)} 个候选：{exam_setup_path}"
                        )
                if exam_plans and exam_plan_selector is None:
                    from gkagent.sim.exam_plan import ExamPlanSelector

                    exam_plan_selector = ExamPlanSelector(exam_plans)
                    lesson_policy.attach_draw_plan(exam_plan_selector)
                    log_lines.append(
                        f"{step:03d} [exam-plan] 挂上 {len(exam_plans)} 个候选"
                        f"（逐回合按实机手牌收窄，engine={lesson_policy.engine}）"
                    )
            else:
                if prev_exam_mode and exam_plan_selector is not None:
                    # 考试结束：停用计划，并把本次挑中的场次/核对结果写进日志
                    exam_plan_selector.finish()
                    lesson_policy.attach_draw_plan(None)
                    log_lines.append(f"[exam-plan] {exam_plan_selector.summary()}")
                    exam_plan_selector = None
                prev_exam_turns = None
            prev_exam_mode = exam_mode
            # 同屏兜底（ep-cplus10：SKIP 点空后同一画面连拍 169 步，25 分钟超时）。
            # 用语义签名而不是像素 digest——角色呼吸/卡面闪光/视频噪点让每帧 hash 都不同。
            turn_signature = lesson_turn_signature(lesson_state)
            stall_action = same_screen.observe(turn_signature)
            if stall_action == "stuck":
                detail = (
                    f"课程同一屏连续 {same_screen.repeats} 步无变化："
                    f"{lesson_state.summary()}，SKIP 也推不动，退出本局"
                )
                log_lines.append(f"{step:03d} [stuck] {detail}")
                log_failure(
                    episode,
                    step,
                    "lesson-stuck",
                    detail,
                    {
                        "attribute": driver.lesson_attribute,
                        "stamina": last_stamina,
                        "turns": turns,
                    },
                )
                stuck_exit = True
                break
            force_skip = stall_action == "force-skip" and not exam_mode
            if stall_action == "force-skip" and exam_mode:
                log_lines.append(
                    f"{step:03d} [exam-mode] 同屏 {same_screen.repeats} 步无变化，"
                    "但考试禁止 SKIP，继续出牌"
                )
            elif force_skip:
                log_lines.append(
                    f"{step:03d} [training] 同一屏连续 {same_screen.repeats} 步无变化，"
                    f"强制 SKIP 结束回合"
                )
            # 体力门：体力 0 / 体力 < 最低手牌费用 → 一张牌都打不出。立刻按 SKIP
            # 结束本回合，不要一回合一点地磨（真机 0 体力进课程后连按 SKIP 白送回合）。
            # 体力读不到时用上一帧兜底，绝不假设充足。
            # 考试模式例外：SKIP 等于白送回合，永远不放行体力门（F#17）。
            stamina_gate = (
                None
                if exam_mode
                else lesson_stamina_gate(
                    lesson_state,
                    stamina=stamina,
                    last_stamina=last_stamina,
                    exam=exam_mode,
                )
            )
            if stamina_gate is None and force_skip:
                stamina_gate = (
                    lesson_state.skip_point or LESSON_SKIP_POINT,
                    f"同一屏连续 {same_screen.repeats} 步无变化，强制 SKIP",
                )
            # 卡片详情浮层状态机：浮层开着时点同一坐标只会开关浮层/反复「不满足使用条件」。
            # pick=正常选牌；confirm=同一点确认一次；close=点空白关浮层换牌；skip=3 次没推进。
            # 浮层识别：小框单行 OCR（「打分+/Active/可以使用」）+ 选牌过程中「读到 SELECT」兜底。
            # 「读到 SELECT」只在分数/手牌完全没变（还没出牌）时才算浮层，避免出牌动画里误判。
            was_awaiting = lesson_guard.awaiting_confirm
            sig_changed = True
            if lesson_sig_before_pick is not None:
                sig_changed = lesson_hand_signature(lesson_state) != lesson_sig_before_pick
            selection_active = lesson_guard.pending_point is not None or was_awaiting
            overlay_open = driver.card_detail_open(image) or (
                selection_active and has_selected_ui(lesson_state.cards) and not sig_changed
            )
            progressed = True
            if was_awaiting and not overlay_open and lesson_sig_before_pick is not None:
                # 浮层关掉不等于出牌成功：分数/手牌完全没变说明这一下只是开关浮层
                progressed = sig_changed
            guard_action, guard_point = lesson_guard.observe(
                overlay_open, progressed=progressed, allow_skip=not exam_mode
            )
            guard_done = guard_action != "pick"
            failure = lesson_guard.take_failure()
            if failure is not None:
                failed_point, failed_name = failure
                if failed_point is not None and not failed_name:
                    failed_name = driver.card_detail_name(image)
                if failed_name:
                    bad_cards.add(failed_name)
                bad_cards.update(lesson_guard.failed_names)
                lesson_policy.reset_turn()
                log_lines.append(
                    f"{step:03d} [training] {failed_name or '这张牌'} 确认后分数/手牌没变"
                    "或浮层仍在，判为打不出去，换一张"
                )
            if stamina_gate is not None:
                skip_point, skip_reason = stamina_gate
                guard_done = True
                if lesson_guard.skip_done(turn_signature) and not force_skip:
                    # 本回合已经点过 SKIP、画面却没推进：同一回合不再重复点，
                    # 交给同屏兜底（5 步强制 / 10 步退出），避免每 7 秒一次的连点。
                    action_name = "lesson-skip-wait"
                    result = (
                        "[training] 本回合已 SKIP 过且画面未推进，不重复点"
                        f"（同屏 {same_screen.repeats}/{same_screen.exit_after}）"
                    )
                    idle = 0
                else:
                    clicked = agent.device.click_force(*skip_point)
                    time.sleep(0.9)
                    if clicked is False:
                        result = "[pause] 用户正在操作，暂停出牌"
                        idle = 0
                    else:
                        lesson_guard.skip_sent(turn_signature)
                        lesson_policy.reset_turn()
                        lesson_pending = None
                        lesson_sig_before_pick = None
                        bad_cards.clear()
                        last_pick_name = None
                        same_pick_count = 0
                        action_name = "lesson-skip"
                        result = f"[training] {skip_reason}，直接 SKIP"
                        idle = 0
            elif guard_action == "confirm" and guard_point is not None:
                pending_name = lesson_guard.pending_name
                if pending_name:
                    # 选中后右上角显示「体力 X / -Y」：顺手学这张卡的体力费用，
                    # 卡面爱心上的小字 OCR 认不出来也能靠这里补齐。
                    stamina_now, stamina_cost = read_stamina_preview(engine, image)
                    # 2026-11-21：真机日志出现「体力消耗=29 (当前体力 29)」——
                    # 这是把右上角体力条读了两次（两个框都读到当前体力），不是费用。
                    # 费用必须严格小于当前体力才写入缓存；等于当前体力的一律视为读歪，
                    # 避免把 4 费的牌记成 29 费（ep-finish7 的 [cost] 记录）。
                    plausible = (
                        stamina_now is not None
                        and stamina_cost is not None
                        and 0 <= stamina_cost < stamina_now
                    )
                    if plausible and cost_cache.record(pending_name, stamina_cost):
                        log_lines.append(
                            f"{step:03d} [cost] {pending_name} 体力消耗={stamina_cost} "
                            f"(当前体力 {stamina_now})"
                        )
                    # 不再因为"预览读歪"就丢牌：真机出现过把分数 23 当费用、体力 3 当上限的
                    # 反向读数，导致能打的牌被放弃。费用只在不大于当前体力时才写入缓存。
                # 两段式的第二击：同一坐标只点这一次，间隔由循环 sleep(0.9) 保证 >0.4s
                clicked = agent.device.click_force(*guard_point)
                time.sleep(0.9)
                if clicked is False:
                    result = "[pause] 用户正在操作，暂停出牌"
                    idle = 0
                else:
                    lesson_guard.confirm_clicked()
                    lesson_pending = None
                    action_name = "lesson-confirm"
                    result = f"[training] confirm card at {guard_point}"
                    idle = 0
            elif guard_action == "close" and guard_point is not None:
                clicked = agent.device.click_force(*guard_point)
                time.sleep(0.6)
                if clicked is False:
                    result = "[pause] 用户正在操作，暂停出牌"
                    idle = 0
                else:
                    lesson_guard.close_sent()
                    lesson_pending = None
                    lesson_sig_before_pick = None
                    action_name = "lesson-close-overlay"
                    result = f"[training] 卡片详情浮层挡路，点空白 {guard_point} 关闭后重选"
                    idle = 0
            elif guard_action == "skip" and guard_point is not None:
                clicked = agent.device.click_force(*guard_point)
                time.sleep(0.9)
                if clicked is False:
                    result = "[pause] 用户正在操作，暂停出牌"
                    idle = 0
                else:
                    lesson_guard.reset_turn()
                    lesson_policy.reset_turn()
                    lesson_pending = None
                    lesson_sig_before_pick = None
                    # 新回合条件会变（好调/集中等），上一回合打不出去的牌重新参与选择
                    bad_cards.clear()
                    last_pick_name = None
                    same_pick_count = 0
                    action_name = "lesson-skip"
                    result = (
                        f"[training] 同一坐标连续 {lesson_guard.skip_after} 次未推进，"
                        f"点 SKIP {guard_point}"
                    )
                    idle = 0
            elif guard_action == "wait":
                lesson_pending = None
                lesson_sig_before_pick = None
                action_name = "lesson-wait"
                result = "[training] 选牌点击已生效，等下一帧"
                idle = 0
            if (
                stamina is not None
                and stamina <= 8
                and not drink_used
                and (turns is None or turns > 1)
                and lesson_pending is None
                and not guard_done
            ):
                drink_used = True
                agent.device.click_force(75, 1182)
                time.sleep(1.0)
                shot2 = agent.shot()
                lines2 = driver.read(shot2)
                use = driver.find(lines2, "使用")
                if use is not None:
                    agent.device.click_force(*driver.center(use))
                time.sleep(0.8)
                result = f"[training] drink at stamina={stamina}"
                clicked = True
                action_name = "drink"
                hand = scan_hand(image)
                boxes = tuple(tuple(card.box) for card in hand.cards)
                lesson_pending = None
            elif not guard_done:
                hand = scan_hand(image)
                boxes = tuple(tuple(card.box) for card in hand.cards)
            # 两段式出牌的确认/关闭已由上面的 LessonPlayGuard 分流，这里只负责选牌。
            if action_name != "drink" and not guard_done:
                lesson_pending = None
                # 出牌：LessonReader 已经 OCR 过手牌区（卡名/预览/费用），这里不再重复整屏 OCR
                # 卡名清洗 + 剔除已确认打不出去的牌；脏名清空后仍按分数/费用参与选择
                state_clean = clean_lesson_state(
                    lesson_state,
                    exclude_names=bad_cards,
                    exclude_points=lesson_guard.failed_points,
                )
                costs = [card.cost for card in hand.cards] if hand.cards else None
                lesson_skip = False
                try:
                    name_pick, lesson_done = decide_lesson_pick(
                        image,
                        lesson_reader,
                        lesson_policy,
                        stamina=stamina,
                        exclude=bad_cards,
                        click=agent.device.click_force,
                        state=state_clean,
                        allow_skip=not exam_mode,
                        # 用户规则（2026-11-21）：搜索引擎禁止回退老规则路径；
                        # 只有显式 --engine rules 才保留 pick_hand_card 兜底。
                        fallback=(
                            None
                            if strict_engine
                            else (
                                lambda lines=lines, boxes=boxes, stamina=stamina, costs=costs, image=image: pick_hand_card(
                                    lines if lines else driver.engine().read(image, (0, 780, 720, 420)),
                                    boxes,
                                    card_lib,
                                    stamina=stamina,
                                    costs=costs,
                                    attribute=driver.lesson_attribute,
                                    exclude=bad_cards,
                                )
                            )
                        ),
                    )
                except RuleFallbackBlocked as exc:
                    # 用户规则：**bot 不许回退 rules**。搜索引擎无法决策时不许悄悄
                    # 改用规则打，也不许用 SKIP 补偿——记 BLOCKED 并中止本局，暴露
                    # OCR/卡表问题。
                    log_lines.append(
                        f"{step:03d} [engine][BLOCKED] {exc}（用户规则：不许回退 rules）"
                    )
                    log_failure(
                        episode,
                        step,
                        "rule-fallback-blocked",
                        str(exc),
                        {
                            "engine": lesson_policy.engine,
                            "attribute": driver.lesson_attribute,
                            "stamina": last_stamina,
                            "exam": exam_mode,
                        },
                    )
                    stuck_exit = True
                    break
                # 决策可观测性：本步到底用哪个引擎、搜索有没有静默退回规则
                decision_note = lesson_policy.decision_note()
                if lesson_done:
                    lesson_skip = True
                    name_pick = None
                    clicked = True
                    idle = 0
                    lesson_guard.reset_turn()
                    lesson_sig_before_pick = None
                    bad_cards.clear()
                    last_pick_name = None
                    same_pick_count = 0
                    action_name = "lesson-skip"
                    result = f"[training] SKIP 结束回合（剩下的牌不值得体力） | {decision_note}"
                if name_pick is not None:
                    # 卡名只剩 SELECT/SEECT/S/A/M 时不能沿用脏名字：按分数/费用重选
                    cleaned_name = clean_card_name(name_pick.name)
                    if not cleaned_name:
                        if strict_engine:
                            # 用户规则：不许回退 rules。卡名读不全不代表引擎选错牌：
                            # 保留引擎选的点位，只换占位名，不再用规则另选一张。
                            name_pick = HandPick(
                                point=name_pick.point,
                                index=name_pick.index,
                                name=f"card{name_pick.index}",
                                value=name_pick.value,
                            )
                        else:
                            fallback_card = pick_lesson_card(
                                state_clean.cards,
                                stamina=stamina,
                                exclude_points=lesson_guard.failed_points,
                            )
                            if fallback_card is not None:
                                name_pick = HandPick(
                                    point=fallback_card.point,
                                    index=fallback_card.index,
                                    name=clean_card_name(fallback_card.name)
                                    or f"card{fallback_card.index}",
                                    value=float(fallback_card.total_score or name_pick.value),
                                )
                            else:
                                name_pick = HandPick(
                                    point=name_pick.point,
                                    index=name_pick.index,
                                    name=f"card{name_pick.index}",
                                    value=name_pick.value,
                                )
                    elif cleaned_name != name_pick.name:
                        name_pick = HandPick(
                            point=name_pick.point,
                            index=name_pick.index,
                            name=cleaned_name,
                            value=name_pick.value,
                        )
                    if tuple(name_pick.point) in lesson_guard.failed_points:
                        name_pick = None
                # sim 实时出牌（policy.json produce.sim_play，默认 false）：
                # 对每张手牌 rollout「打这张 + 剩余回合 greedy 打完」，期望分最高者覆盖策略选择；
                # 模拟器返回 None/异常时保留策略结果，绝不让出牌退化。
                if sim_play and not lesson_skip and state_clean.cards:
                    sim_candidates = [
                        card
                        for card in state_clean.cards
                        if card.name not in bad_cards
                        and tuple(card.point) not in lesson_guard.failed_points
                    ]
                    if sim_candidates:
                        sim_index, sim_estimates = plan_pick(
                            sim_candidates,
                            turns_left=max(int(turns or lesson_state.turns_left or 3), 1),
                            stamina=int(
                                stamina
                                if stamina is not None
                                else (lesson_state.stamina or 0)
                            ),
                            deck=sim_deck or None,
                            kind="audition" if exam_mode else "lesson",
                        )
                        sim_best = next(
                            (item for item in sim_estimates if item.index == sim_index), None
                        )
                        if sim_best is not None and sim_best.point is not None:
                            # 量纲：sim_best.expected 是模拟器口径（含 buff/审查加成后的期望总分），
                            # 不能和屏幕上的「打分」直接比较，只用于排序；所以两边都同时打印
                            # 「屏幕分」（卡面宝石/DPS 预览）和「模拟口径期望/规则估值」。
                            screen_by_point = {
                                tuple(card.point): float(card.total_score)
                                for card in state_clean.cards
                            }
                            rule_screen = (
                                screen_by_point.get(tuple(name_pick.point), 0.0)
                                if name_pick is not None
                                else None
                            )
                            rule_label = (
                                f"{name_pick.name}(屏幕 {rule_screen:.0f}分、"
                                f"策略估值 {name_pick.value:.1f})"
                                if name_pick is not None
                                else "无"
                            )
                            if name_pick is None or sim_best.point != name_pick.point:
                                log_lines.append(
                                    f"{step:03d} [training] sim-pick {sim_best.name} "
                                    f"(屏幕 {sim_best.score:.0f}分/{sim_best.cost}费、"
                                    f"模拟口径期望 {sim_best.expected:.1f}) vs 策略选 {rule_label}"
                                )
                                name_pick = HandPick(
                                    point=sim_best.point,
                                    index=sim_best.index,
                                    name=sim_best.name,
                                    value=sim_best.expected,
                                )
                            else:
                                log_lines.append(
                                    f"{step:03d} [training] sim-pick 与策略一致 {sim_best.name} "
                                    f"(屏幕 {sim_best.score:.0f}分、模拟口径期望 "
                                    f"{sim_best.expected:.1f}、策略估值 {name_pick.value:.1f})"
                                )
                        # 近似牌库：真机拿不到完整牌组，把见过的手牌并进来（最多 12 张）
                        for item in sim_estimates:
                            if len(sim_deck) < MAX_APPROX_DECK and all(
                                item.name != spec.name for spec in sim_deck
                            ):
                                sim_deck.append(
                                    CardSpec(name=item.name, cost=item.cost, score=item.score)
                                )
                # 同一张卡连点 4 次手牌都没变 → 认为不可用，标记跳过、换一张
                if name_pick is not None:
                    if name_pick.name == last_pick_name:
                        same_pick_count += 1
                    else:
                        last_pick_name = name_pick.name
                        same_pick_count = 1
                    if same_pick_count >= 4:
                        bad_cards.add(name_pick.name)
                        log_lines.append(f"{step:03d} [training] {name_pick.name} 连点不动，标记跳过")
                        last_pick_name = None
                        same_pick_count = 0
                        if strict_engine:
                            # 用户规则：不许回退 rules。下一帧 state_clean 会剔除这张卡，
                            # 让搜索引擎重新决策；本帧不点，也不接老规则路径。
                            name_pick = None
                        else:
                            name_pick = pick_hand_card(
                                lines,
                                boxes,
                                card_lib,
                                stamina=stamina,
                                costs=costs,
                                attribute=driver.lesson_attribute,
                                exclude=bad_cards,
                            )
                if name_pick is not None:
                    clicked = agent.device.click_force(*name_pick.point)
                    time.sleep(0.9)
                    if clicked is False:
                        result = "[pause] 用户正在操作，暂停出牌"
                        idle = 0
                    else:
                        lesson_pending = (name_pick.point, boxes, name_pick.name)
                        lesson_guard.picked(name_pick.point, name_pick.name)
                        lesson_sig_before_pick = lesson_hand_signature(lesson_state)
                        result = (
                            f"[training] name-pick {name_pick.name} "
                            f"({name_pick.value:.1f}) at {name_pick.point} | {decision_note}"
                        )
                        no_decision_streak = 0
                        idle = 0
                    action_name = "name-pick"
                elif not lesson_skip and strict_engine:
                    # 用户规则（2026-11-21）：**bot 不许回退 rules**。搜索引擎没产出
                    # 可点的牌（状态没读全/等下一帧）时原地等待，不接老规则路径；
                    # 考试不能干等，点中央推进（关浮层/等下一帧），也绝不 SKIP。
                    if exam_mode:
                        clicked = agent.device.click_force(*SETTLE_CENTER_TAP)
                        time.sleep(0.9)
                        if clicked is False:
                            result = "[pause] 用户正在操作，暂停出牌"
                            idle = 0
                        else:
                            action_name = "exam-tap"
                            result = (
                                "[exam-mode] 策略无牌可出（真没体力/状态未就绪），点中央推进"
                                f"（不回退 rules） | {decision_note}"
                            )
                            idle += 1
                    else:
                        action_name = "engine-wait"
                        result = (
                            "[training] 等待下一帧重读（禁止回退 rules）"
                            f" | {decision_note}"
                        )
                        idle += 1
                elif not lesson_skip:
                    with (ROOT / "data" / "pick_debug.log").open("a", encoding="utf-8") as handle:
                        detail = []
                        for box in boxes:
                            bx, by, bw, bh = box
                            candidates = []
                            for line in lines:
                                lx, ly, lw, _lh = line.box
                                cx = lx + lw // 2
                                in_y = by + bh * 0.5 <= ly <= by + bh + 50
                                in_x = bx - 10 <= cx <= bx + bw + 10
                                if in_y or in_x:
                                    candidates.append(
                                        {
                                            "text": line.text,
                                            "cx": cx,
                                            "ly": ly,
                                            "in_y": in_y,
                                            "in_x": in_x,
                                            "known": card_lib.find(line.text.strip()) is not None,
                                        }
                                    )
                            detail.append({"box": list(box), "candidates": candidates[:8]})
                        handle.write(
                            json.dumps(
                                {
                                    "episode": episode,
                                    "step": step,
                                    "boxes": [list(box) for box in boxes],
                                    "detail": detail,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    screen = task.observe(agent, image)
                    play = task.decide_card(agent, image, screen=screen, stamina=stamina)
                    if play is not None and tuple(play.point) in lesson_guard.failed_points:
                        play = None  # 这张已确认打不出去（浮层关掉后重选）
                    if play is None and lesson_guard.failed_points and not exam_mode:
                        # 剩下的牌都确认打不出去：别在卡片详情浮层里空转，SKIP 结束回合
                        clicked = agent.device.click_force(*LESSON_SKIP_POINT)
                        time.sleep(0.9)
                        if clicked is False:
                            result = "[pause] 用户正在操作，暂停出牌"
                            idle = 0
                        else:
                            lesson_guard.reset_turn()
                            lesson_policy.reset_turn()
                            lesson_pending = None
                            lesson_sig_before_pick = None
                            bad_cards.clear()
                            last_pick_name = None
                            same_pick_count = 0
                            action_name = "lesson-skip"
                            result = "[training] 剩余牌都确认打不出去，点 SKIP 结束回合"
                            idle = 0
                    elif play is None and exam_mode:
                        # 考试：绝不能 SKIP。换一张还没确认打不出去的牌硬出（分数没读到也点）；
                        # 全都被确认打不出去时点中央推进（关浮层/等下一帧），仍不 SKIP。
                        exam_card = pick_lesson_card(
                            state_clean.cards,
                            stamina=stamina,
                            exclude_names=bad_cards,
                            exclude_points=lesson_guard.failed_points,
                        )
                        point = exam_card.point if exam_card is not None else SETTLE_CENTER_TAP
                        clicked = agent.device.click_force(*point)
                        time.sleep(0.9)
                        if clicked is False:
                            result = "[pause] 用户正在操作，暂停出牌"
                            idle = 0
                        elif exam_card is not None:
                            lesson_pending = (point, boxes, exam_card.name)
                            lesson_guard.picked(point, exam_card.name)
                            lesson_sig_before_pick = lesson_hand_signature(lesson_state)
                            action_name = "exam-card"
                            result = f"[exam-mode] 换牌再出 {exam_card.name or 'card'} at {point}"
                            idle = 0
                        else:
                            action_name = "exam-tap"
                            result = "[exam-mode] 没有可点的牌，点中央推进（绝不 SKIP）"
                            idle += 1
                    elif play is not None:
                        task._record(image, play)
                        clicked = agent.device.click_force(*play.point)
                        time.sleep(0.9)
                        if clicked is False:
                            result = "[pause] 用户正在操作，暂停出牌"
                            idle = 0
                        else:
                            lesson_pending = (play.point, boxes, "")
                            lesson_guard.picked(play.point, "")
                            lesson_sig_before_pick = lesson_hand_signature(lesson_state)
                            result = f"[training] play card#{play.index} {play.source} at {play.point} | {decision_note}"
                            no_decision_streak = 0
                            idle = 0
                    else:
                        no_decision_streak += 1
                        if not exam_mode and no_decision_streak >= 2:
                            # 连续读不到可出的牌：别无限点中位卡（ep-t1-k 空手牌空转），
                            # 课程允许 SKIP —— 直接结束回合，下一回合重新读屏。
                            clicked = agent.device.click_force(
                                *(lesson_state.skip_point or LESSON_SKIP_POINT)
                            )
                            time.sleep(0.8)
                            lesson_policy.reset_turn()
                            lesson_guard.reset_turn()
                            same_screen.reset()
                            action_name = "force-skip"
                            result = (
                                f"[training] 连续 {no_decision_streak} 步无可出牌，点 SKIP 结束回合"
                                f" | {decision_note}"
                            )
                            no_decision_streak = 0
                            idle = 0
                        else:
                            clicked = agent.device.click_force(360, 1000)
                            time.sleep(0.9)
                            result = f"[training] 无可用决策，点击中位卡兜底 | {decision_note}"
                            idle += 1
            # 考试模式给每一步打标记，真机日志里一眼能看出"这步在考试里做了什么"
            if exam_mode and not result.startswith("[exam-mode]"):
                result = f"[exam-mode] {result}"
            # 暂停帧不算「同屏卡死」：用户操作/自身输入误判暂停时，画面本来就不该变化，
            # 若继续累计 same_screen 计数，会从 [pause] 直接滑到 [stuck] 退出（ep-t1-l）。
            if result.startswith("[pause]"):
                same_screen.reset()
        else:
            lesson_pending = None
            drink_used = False
            bad_cards.clear()
            last_pick_name = None
            same_pick_count = 0
            lesson_guard.reset()
            lesson_sig_before_pick = None
            parsed_stamina = parse_stamina(text)
            if parsed_stamina is not None:
                last_stamina = parsed_stamina
            driver.stamina_hint = last_stamina
            tick = driver.decide(agent, lines, image)
            result = tick.describe()
            screen_name, action_name = tick.screen, tick.action
            clicked = None if screen_name in ("pause", "loading", "blank") else True
            # ---- 跑局数据：行动页 = 上一周行动结束 + 新一周行动开始 ----------
            # 这里的 attrs_now 是行动页当前三维（即上一周行动之后的值），
            # stamina 也从同帧读；读不到写 null，不用上一帧顶替。
            if tick.screen == "action":
                if pending_week is not None and pending_action_advanced:
                    finalize_week(attrs_now, parse_stamina(text), why="next-action")
                mapped_action = action_of(tick.action)
                if mapped_action is not None:
                    week_value, week_phase = driver.read_week(image, text)
                    start_week_action(mapped_action, week_value, week_phase)
            elif tick.screen not in ("pause", "loading", "blank"):  # noqa: SIM102 - 保持原逻辑
                if pending_week is not None:
                    pending_action_advanced = True
            if tick.screen == "stuck":
                # 兜底分支自己判定死循环（F#15）：scenario 同屏点不动 10 次以上，
                # 直接记 [stuck] 退出本局并返回失败，不再等到 12 次停机/30 分钟超时。
                detail = tick.detail or result
                log_lines.append(f"{step:03d} [stuck] {detail}")
                log_failure(
                    episode,
                    step,
                    "scenario-stall",
                    detail,
                    {
                        "attribute": driver.lesson_attribute,
                        "stamina": last_stamina,
                        "screen": tick.screen,
                    },
                )
                stuck_exit = True
                break
            if tick.screen == "pause":
                pause_streak += 1
                # 用户在操作时逐步拉长退避，避免每 2s 空烧一步
                time.sleep(min(2.0 + pause_streak * 0.5, 6.0))
                idle = 0
                if pause_streak >= 30:
                    log_lines.append(f"{step:03d} 用户持续操作 {pause_streak} 步，暂停本局")
                    break
            else:
                pause_streak = 0
                idle = 0 if tick.ok and tick.screen not in ("unknown", "unknown-tap") else idle + 1
                unknown_streak = (
                    0
                    if tick.ok and tick.screen not in ("unknown", "unknown-tap")
                    else unknown_streak + 1
                )
                # 防死循环：同一 (screen, action, 文本) 连续出现才计数；
                # 数字全部归一化（P/体力/回合每步都在变，否则签名永远不同）；
                # 剧情「快进」每步台词都变，仍不会误杀。
                signature = (
                    tick.screen,
                    tick.action,
                    re.sub(r"\d+", "#", text[:80]),
                )
                if signature == last_signature:
                    same_action_count += 1
                else:
                    last_signature = signature
                    same_action_count = 1
                if (
                    same_action_count >= 10
                    and tick.screen not in ("loading", "blank", "pause")
                ):
                    log_lines.append(
                        f"{step:03d} 同一动作 {tick.screen}/{tick.action} 连续 {same_action_count} 次，停止"
                    )
                    break
                # 兜底：同一 (screen, action) 即使文本每步微变，连续 12 次也判卡死
                # （剧情/等待类屏不参与，避免误杀长对话）
                key = (tick.screen, tick.action)
                if tick.screen in ("story", "pause", "loading", "blank", "unknown", "unknown-tap"):
                    action_key = None
                    action_streak = 0
                elif key == action_key:
                    action_streak += 1
                else:
                    action_key = key
                    action_streak = 1
                if action_streak >= 12:
                    log_lines.append(
                        f"{step:03d} 同一屏/动作 {tick.screen}/{tick.action} 连续 {action_streak} 次（文本微变），停止"
                    )
                    log_failure(
                        episode,
                        step,
                        "same-screen-stall",
                        f"{tick.screen}/{tick.action} x{action_streak}",
                        {"attribute": driver.lesson_attribute, "stamina": last_stamina},
                    )
                    break

        decide_ms = (time.perf_counter() - t_decide) * 1000
        total_ms = capture_ms + ocr_ms + decide_ms
        pending = StepRecord(
            episode=episode,
            step=step,
            screen=screen_name,
            action=action_name,
            capture_ms=round(capture_ms, 1),
            ocr_ms=round(ocr_ms, 1),
            decide_ms=round(decide_ms, 1),
            total_ms=round(total_ms, 1),
            clicked=clicked,
        )
        log_lines.append(f"{step:03d} {result}")
        if idle >= 8:
            log_lines.append(f"{step:03d} 连续 8 步无可执行动作，停止")
            break

    # 收尾：结算页没认出来时，最后一整周行动也要落盘（字段缺失写 null + note）。
    # 只在本局正常结束（done）时补；中途超时/急停的当周行动可能没做完，不猜。
    if done and pending_week is not None and pending_action_advanced:
        end_lesson()
        finalize_week(None, None, why="episode-end")
    flush_pending(None)
    ended_at = time.time()
    metrics.write(
        EpisodeRecord(
            episode=episode,
            started_at=started_at,
            ended_at=ended_at,
            steps=len(log_lines),
            done=done,
            progress_markers=markers[:10],
        )
    )
    # 考试牌序计划复盘：核对了几回合 / 是否因不符停用 / 重洗几次
    try:
        if exam_plan_selector is not None:
            log_lines.append(f"[exam-plan] {exam_plan_selector.summary()}")
        elif exam_plans:
            log_lines.append(
                f"[exam-plan] 本局没进入考试（{len(exam_plans)} 个候选未使用）"
            )
    except Exception as exc:  # noqa: BLE001 - 复盘日志不能影响收尾
        log_lines.append(f"[exam-plan] summary 失败：{exc}")
    LOG.write_text("\n".join(log_lines), encoding="utf-8")
    # 每局单独留一份，避免被下一局/手工测试覆盖
    (SHOT_DIR / f"auto_log_{episode}.log").write_text("\n".join(log_lines), encoding="utf-8")
    if not done:
        log_failure(
            episode,
            len(log_lines),
            "episode-not-done",
            log_lines[-1] if log_lines else "no log",
            {"steps": len(log_lines), "attribute": driver.lesson_attribute},
        )
    summary = metrics.summary(episode)
    print(
        json.dumps(
            {
                "episode": episode,
                "steps": len(log_lines),
                "done": done,
                "stuck": stuck_exit,
                "duration_s": round(ended_at - started_at, 1),
                "avg_total_ms": summary.get("avg_total_ms"),
                "changed_rate": summary.get("changed_rate"),
                "run_record": str(recorder.path),
                "log": log_lines[-12:],
            },
            ensure_ascii=False,
        )
    )
    # 卡死退出（同一屏 10 步无变化）也算失败，哪怕步数刚好用完
    return 1 if stuck_exit else (0 if done or len(log_lines) >= steps else 1)


if __name__ == "__main__":
    raise SystemExit(main())
