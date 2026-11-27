"""matto OCR 测试集回归基准（自写 harness，可提交；**数据集本身不入库**）。

来源：https://hiro.matto.top/ocr-dataset/check.html（matto 2026-11-26 群分享；
49 帧真值 = Claude/Codex 交叉读，5 后端横比 vision/rapidocr/simd/ppocr5/winocr，
逐字段 对/错/没读）。**许可判定**：页面/README/NOTICE 均无许可声明 → 按 hiro
先例（docs/PROVENANCE.md）只本地参考不入库：数据放 ``data/_ocr_dataset/``
（gitignore），本脚本不含任何数据，缺失即退出（测试侧缺失即 skip）。

用法::

    python scripts/ocr_bench.py                     # 全 49 帧
    python scripts/ocr_bench.py --scene exam --limit 6
    python scripts/ocr_bench.py --threads 4 --md report.md --json report.json

两层测量（缺口报告口径）：

- **engine**：``OcrEngine.read`` 整屏（**原生 540x960**，与 matto 后端同分辨率）
  + 位置先验正则抽字段 → 「我们的 OCR 读不读得到这格像素」；
- **prod**：生产读屏路径（帧放大到 720x1280，我们 ROI 的标定分辨率）：
  ``read_fast`` / ``exam_mode`` / ``LessonReader`` / ``read_attrs`` / ``decide``
  → 「生产代码解不解析这个字段」。

字段键名与 matto 真值表一致（``params[0]`` / ``shelf[3].price`` / ``button:削除`` …），
逐字段判 对/错/没读；``pending``（Claude/Codex 不一致待定 8 项）不参与打分。
屏幕读不到的三类字段（deck_left / card_effect statuses / multiplier_pct 兜底）
见 ``gkagent.vision.ocr_complete``（opt-in 引擎补全，默认关）；本报告只标
「可补全」，不拿假 sim 状态冒充实测。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

from gkagent.tasks.produce_ui import (  # noqa: E402
    FAST_P_BOX,
    FAST_STAMINA_BOX,
    _STAMINA_RE,
    ProduceDriver,
    parse_stamina,
)
from gkagent.vision.lesson import LessonReader  # noqa: E402
from gkagent.vision.ocr import OcrEngine, OcrLine  # noqa: E402

DATASET = ROOT / "data" / "_ocr_dataset"
BACKENDS = ("vision", "rapidocr", "simd", "ppocr5", "winocr")
# 中文规范属性名 → matto 真值口径（vocal/dance/visual）
_ATTR_EN = {"歌唱": "vocal", "舞蹈": "dance", "视觉": "visual"}
_JA_ATTR = {"ボーカル": "vocal", "ダンス": "dance", "ビジュアル": "visual"}


# ---------------------------------------------------------------- 工具
def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text)).strip()


def digits(text: str) -> list[int]:
    return [int(m) for m in re.findall(r"\d+", nfkc(text))]


def center(line: OcrLine) -> tuple[float, float]:
    x, y, w, h = line.box
    return x + w / 2.0, y + h / 2.0


def in_box(line: OcrLine, x0: float, y0: float, x1: float, y1: float) -> bool:
    cx, cy = center(line)
    return x0 <= cx <= x1 and y0 <= cy <= y1


def as_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = nfkc(str(value)).replace("%", "").replace("％", "")
    try:
        return float(text)
    except ValueError:
        return None


def judge(truth: object, ours: object) -> str:
    """对/错/没读（truth 为 None 的字段不参与，调用方先过滤）。"""
    if ours is None:
        return "没读"
    if isinstance(truth, str) and truth in ("true", "false"):
        return "对" if bool(ours) == (truth == "true") else "错"
    tn, on = as_number(truth), as_number(ours)
    if tn is not None and on is not None:
        return "对" if abs(tn - on) < 1e-6 else "错"
    return "对" if nfkc(str(truth)) == nfkc(str(ours)) else "错"


# ---------------------------------------------------------------- engine 层抽字段
# 位置先验按 matto 原生 540x960 标定（= 我们 720x1280 设计坐标 × 0.75）。
# 整屏检测偶尔把相邻数字合并成一行（star+params / 两个 top_score / 划线价+现价），
# 合并行用「列宽拆分」启发式；关键小数字另走 engine.line 定向框（与生产 ROI 同源）。
def _line_text(engine: OcrEngine, image, roi: tuple[int, int, int, int]) -> str:
    try:
        line = engine.line(image, roi, digits_only=False)
    except Exception:  # noqa: BLE001 - 测量探针失败按没读
        return ""
    return nfkc(line.text) if line is not None else ""


def extract_common(lines: list[OcrLine], out: dict) -> None:
    for line in lines:
        cx, cy = center(line)
        if cy > 130:
            continue
        m = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})", nfkc(line.text))
        if m and "hp" not in out and int(m.group(2)) <= 60 and int(m.group(1)) <= int(m.group(2)):
            out["hp"], out["hp_max"] = int(m.group(1)), int(m.group(2))
        if "p_points" not in out:
            pm = re.search(r"P\s*(\d{1,4})", nfkc(line.text))
            if pm:
                out["p_points"] = int(pm.group(1))
            elif re.fullmatch(r"\d{2,4}", nfkc(line.text)) and 230 <= cx <= 340 and 70 <= cy <= 115:
                out["p_points"] = int(nfkc(line.text))


def extract_exam(engine: OcrEngine, image, lines: list[OcrLine], out: dict) -> None:
    # 定向框（原生坐标）：圆环回合 / 属性倍率 / 属性名 / 体力 / 三列分数 / 选中预览
    turns = digits(_line_text(engine, image, (28, 48, 40, 40)))
    if turns:
        out.setdefault("turns_left", turns[0])
    mult = digits(_line_text(engine, image, (82, 56, 72, 38)))
    if mult:
        out.setdefault("multiplier_pct", mult[0])
    attr_text = _line_text(engine, image, (72, 36, 70, 28))
    for ja, en in _JA_ATTR.items():
        if ja in attr_text:
            out.setdefault("exam_attr", en)
    hp = digits(_line_text(engine, image, (420, 150, 60, 36)))
    if hp:
        out.setdefault("hp", hp[0])
    for i, roi in enumerate(((163, 98, 62, 24), (222, 98, 62, 24), (280, 98, 48, 24))):
        nums = digits(_line_text(engine, image, roi))
        if nums:
            out.setdefault(f"top_scores[{i}]", nums[0])
    preview = digits(_line_text(engine, image, (374, 656, 66, 40)))
    if preview:
        out.setdefault("selected_preview", preview[0])
    # 整屏行补充：牌库小数字 / 元气 / 状态栏数值 / 手牌名（按 x 排序）/ SKIP
    names: list[tuple[float, str]] = []
    status_vals: list[tuple[float, object]] = []
    for line in lines:
        text = nfkc(line.text)
        cx, cy = center(line)
        if re.fullmatch(r"\d{1,2}", text) and cx > 470 and 150 <= cy <= 225:
            out.setdefault("deck_left", int(text))
        if re.fullmatch(r"\d{1,2}", text) and cx > 440 and 120 <= cy <= 160:
            out.setdefault("genki", int(text))
        if cx < 75 and 150 <= cy <= 320:
            mm = re.search(r"(\d{1,3})", text)
            if mm:
                status_vals.append((cy, int(mm.group(1))))
        if 820 <= cy <= 870 and len(text) >= 3 and not any(ch.isdigit() for ch in text):
            if any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in text):
                names.append((cx, text))
        if text == "SKIP":
            out.setdefault("button:SKIP", "SKIP")
    for i, (_x, raw) in enumerate(sorted(names)):
        out.setdefault(f"hand[{i}].name", re.sub(r"[+＋⁺]$", "", raw))
        out.setdefault(f"hand[{i}].plus", raw != re.sub(r"[+＋⁺]$", "", raw))
    # 状态栏位置先验：上两格普通状态（やる気/好印象图标），第三格起 card_effect
    # （图标无文字，matto 5 后端也全没读；这里只抽数值，kind 按格位标注）。
    for i, (_y, value) in enumerate(sorted(status_vals)):
        out.setdefault(f"statuses[{i}].value", value)
        out.setdefault(f"statuses[{i}].kind", "status" if i < 2 else "card_effect")


def extract_action(engine: OcrEngine, image, lines: list[OcrLine], out: dict) -> None:
    caps: list[tuple[float, int]] = []
    growth: list[tuple[float, float]] = []
    merged: tuple[int, int, int, int] | None = None
    for line in lines:
        text = nfkc(line.text)
        cx, cy = center(line)
        x, y, w, h = line.box
        if cy < 60 and cx < 170 and ("本戦" in text or "選抜" in text):
            out.setdefault("exam_name", text.replace("まで", "").strip())
        m = re.search(r"(\d{1,2})\s*日", text)
        if m and cy < 110 and cx < 170:
            out.setdefault("days_left", int(m.group(1)))
        # star+三维被检测合并成一行（matto 00058：731147323361207）→ 3+4+4+4 拆分
        if 500 <= cy <= 548 and x < 100 and x + w > 400:
            mm = re.fullmatch(r"(\d{3})(\d{4})(\d{4})(\d{4})", text)
            if mm:
                merged = tuple(int(g) for g in mm.groups())
        m = re.search(r"/\s*(\d{3,4})", text)
        if m and 540 <= cy <= 570:
            caps.append((cx, int(m.group(1))))
        m = re.search(r"(\d{1,3}\.\d)\s*[%％]", text)
        if m and 558 <= cy <= 595:
            growth.append((cx, float(m.group(1))))
        for label in ("おでかけ", "差し入れ", "休む"):
            if label in text and cy > 580:
                out.setdefault(f"button:{label}", label)
                out.setdefault(f"actions[{label}].label", label)
        if "P手帳" in text:
            out.setdefault("button:P手帳", "P手帳")
        if re.fullmatch(r"\d{1,2}", text) and cx > 430 and 585 <= cy <= 630:
            out.setdefault("actions[休む].hp_change", int(text))
    if merged is not None:
        out.setdefault("star", merged[0])
        for i, value in enumerate(merged[1:]):
            out.setdefault(f"params[{i}]", value)
    else:
        # 定向框兜底（vo 框左移避开麦克风图标混读）
        star = digits(_line_text(engine, image, (8, 505, 62, 42)))
        if star:
            out.setdefault("star", star[0])
        for i, roi in enumerate(((138, 505, 92, 42), (232, 505, 96, 42), (348, 505, 92, 42))):
            nums = digits(_line_text(engine, image, roi))
            if nums:
                out.setdefault(f"params[{i}]", nums[0])
    for i, (_x, v) in enumerate(sorted(caps)):
        out.setdefault(f"param_caps[{i}]", v)
    for i, (_x, v) in enumerate(sorted(growth)):
        out.setdefault(f"growth_pct[{i}]", f"{v}%")


def extract_shop(engine: OcrEngine, image, lines: list[OcrLine], out: dict) -> None:
    rows: dict[int, list[tuple[float, list[int]]]] = {0: [], 1: []}
    sold: list[tuple[float, float]] = []
    for line in lines:
        text = nfkc(line.text)
        cx, cy = center(line)
        nums = digits(text)
        if nums:
            if 455 <= cy <= 495 and cx > 40:
                rows[0].append((cx, nums))
            elif 595 <= cy <= 635 and cx > 40:
                rows[1].append((cx, nums))
            elif 705 <= cy <= 750:
                # 強化/削除 按钮里的价格常单独成行（「150」/「次125」）
                if cx < 260:
                    out.setdefault("upgrade_price", nums[-1])
                else:
                    out.setdefault("delete_price", nums[-1])
        if ("交換済" in text or "交换済" in text) and cy > 650:
            if cx < 260:
                out["upgrade_used"] = True
            else:
                out.setdefault("delete_used", True)
        if ("交換済" in text or "交换済" in text) and cy <= 650:
            sold.append((cx, cy))
    for row, kind in ((0, "card"), (1, "drink")):
        for i, (_x, nums) in enumerate(sorted(rows[row])):
            idx = row * 4 + i
            out.setdefault(f"shelf[{idx}].kind", kind)
            if len(nums) == 1 and nums[0] >= 1000:
                # 划线原价+现价被合并成 4 位（7753 = 77|53）：matto 商店价均 2-3 位，
                # 4 位单数按 2+2 拆（测量启发式，报告注明）。
                out.setdefault(f"shelf[{idx}].sale_from", nums[0] // 100)
                out.setdefault(f"shelf[{idx}].price", nums[0] % 100)
            else:
                out.setdefault(f"shelf[{idx}].price", nums[-1])
                if len(nums) >= 2:
                    out.setdefault(f"shelf[{idx}].sale_from", nums[0])
            out.setdefault(f"shelf[{idx}].purchased", False)
    for cx, cy in sold:
        row = 0 if cy < 550 else 1
        slot = min(range(4), key=lambda i: abs((i + 0.5) * 135 - cx))
        out[f"shelf[{row * 4 + slot}].purchased"] = True
    out.setdefault("upgrade_used", False)
    out.setdefault("delete_used", False)
    for label in ("強化", "削除", "交換する", "終了"):
        for line in lines:
            if label in nfkc(line.text):
                out.setdefault(f"button:{label}", label)
                break


EXTRACTORS = {
    "exam": extract_exam,
    "action_select": extract_action,
    "consult": extract_shop,
    "round_interval": extract_shop,
}


# ---------------------------------------------------------------- prod 层
def prod_fields(driver: ProduceDriver, engine: OcrEngine, image, scene: str) -> dict:
    """生产解析器**尝试过**的字段都建键（读不到 = None → 没读）；没尝试的字段不建键（—）。"""
    out: dict = {}
    if scene == "exam":
        state = LessonReader(engine).read(image, kind="audition")
        out["turns_left"] = state.turns_left
        out["hp"] = state.stamina
        out["exam_attr"] = _ATTR_EN.get(state.attribute) if state.attribute else None
        out["multiplier_pct"] = int(state.multiplier) if state.multiplier is not None else None
        for i, card in enumerate(state.cards):
            # matto 真值 name/plus 分开：名字去掉尾「+」再比（+ 是强化标记，不是卡名）
            raw = nfkc(card.name) if card.name else ""
            name = re.sub(r"[+＋]$", "", raw)
            out[f"hand[{i}].name"] = name or None
            out[f"hand[{i}].plus"] = (raw != name) if raw else None
            out[f"hand[{i}].cost"] = card.cost
    elif scene == "action_select":
        attrs = driver.read_attrs(image, text_hint=None)
        for i in range(3):
            out[f"params[{i}]"] = attrs[i] if attrs is not None else None
        stamina_text = driver._probe_text(image, FAST_STAMINA_BOX)
        # parse_stamina 只回当前体力；hp_max 用同一条生产正则/同一过滤取第二组
        hp_max = None
        for m in _STAMINA_RE.finditer(stamina_text or ""):
            cur, mx = int(m.group(1)), int(m.group(2))
            if mx <= 60 and cur <= mx:
                hp_max = mx
                break
        out["hp"] = parse_stamina(stamina_text)
        out["hp_max"] = hp_max
        p_text = driver._probe_text(image, FAST_P_BOX)
        nums = digits(p_text)
        out["p_points"] = nums[-1] if nums else None
    return out


# ---------------------------------------------------------------- 主流程
def load_dataset() -> dict | None:
    truth = DATASET / "truth.json"
    if not truth.is_file():
        return None
    doc = json.loads(truth.read_text(encoding="utf-8"))
    frames = [f for f in doc["frames"] if (DATASET / f["img"]).is_file()]
    if not frames:
        return None
    doc["frames"] = frames
    return doc


def make_engine(threads: int) -> OcrEngine | None:
    config = ROOT / "configs" / "ocr_jp.yaml"
    if not config.is_file():
        config = ROOT / "configs" / "ocr_jp.example.yaml"
    if not config.is_file():
        return None
    model_dir = ROOT / "data" / "models" / "ocr_jp"
    if not all((model_dir / n).is_file() for n in ("det.onnx", "rec.onnx", "keys.txt")):
        return None
    return OcrEngine(config_path=config, threads=threads)


class _Device:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))

    def click_force(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))

    def swipe(self, *args) -> None:
        pass


class _Agent:
    def __init__(self) -> None:
        self.device = _Device()


def bench_frame(engine: OcrEngine, frame: dict, *, decide: bool) -> dict:
    path = DATASET / frame["img"]
    native = cv2.imread(str(path))
    if native is None:
        return {"id": frame["id"], "error": "imread-failed"}
    image = cv2.resize(native, (720, 1280), interpolation=cv2.INTER_CUBIC)
    scene = frame["scene"]
    started = time.perf_counter()
    lines_engine = engine.read(native)
    engine_ms = (time.perf_counter() - started) * 1000.0
    driver = ProduceDriver(ocr=engine, sleep=lambda _s: None)
    lines_fast = driver.read_fast(image)
    eng: dict = {}
    extract_common(lines_engine, eng)
    EXTRACTORS.get(scene, lambda _e, _i, _l, _o: None)(engine, native, lines_engine, eng)
    prod = prod_fields(driver, engine, image, scene)
    tick = None
    if decide:
        result = driver.decide(_Agent(), lines_fast, image)
        tick = {"screen": result.screen, "action": result.action}
    rows = []
    for field in frame["fields"]:
        if field["pending"]:
            continue
        truth = field["truth"]
        name = field["field"]
        if truth is None or str(truth) in ("null", "_null_"):
            continue  # 真值空字段不参与打分（matto 口径「—」）
        if name.startswith("button:"):
            truth = str(truth).split(" @ ")[0].strip()
        rows.append({
            "field": name,
            "truth": truth,
            "engine": judge(truth, eng.get(name)),
            "engine_value": eng.get(name),
            "prod": judge(truth, prod[name]) if name in prod else "—",
            "prod_value": prod.get(name),
            "backends": {b: field["backends"][b]["status"] for b in BACKENDS},
        })
    return {
        "id": frame["id"],
        "scene": scene,
        "engine_ms": round(engine_ms, 1),
        "tick": tick,
        "rows": rows,
    }


def aggregate(results: list[dict]) -> dict:
    by_field: dict[str, dict] = {}
    for res in results:
        for row in res["rows"]:
            agg = by_field.setdefault(row["field"], {
                "engine": {"对": 0, "错": 0, "没读": 0},
                "prod": {"对": 0, "错": 0, "没读": 0, "—": 0},
                "backends": {b: {"对": 0, "错": 0, "没读": 0} for b in BACKENDS},
                "scenes": set(),
            })
            agg["engine"][row["engine"]] += 1
            agg["prod"][row["prod"]] += 1
            for b in BACKENDS:
                status = row["backends"][b]
                if status in agg["backends"][b]:
                    agg["backends"][b][status] += 1
            agg["scenes"].add(res["scene"])
    for agg in by_field.values():
        agg["scenes"] = sorted(agg["scenes"])
    return by_field


def render_md(doc: dict, results: list[dict], by_field: dict) -> str:
    lines = [
        "# matto OCR 基准缺口报告（我们 vs 5 后端）",
        "",
        f"- 来源：{doc['source']}（49 帧真值 = Claude/Codex 交叉读；待定 8 项不参与打分）",
        "- 许可判定：页面/README/NOTICE 无许可声明 → 只本地参考不入库（hiro 先例，data/_ocr_dataset/ gitignore）",
        "- engine 层 = OcrEngine.read 原生 540x960 + 位置先验正则；prod 层 = 生产读屏（720x1280）",
        "- prod「—」= 生产代码无此字段解析器（非 OCR 问题）",
        "",
        "## 逐字段汇总（对/错/没读）",
        "",
        "| 字段 | 场景 | 我们 engine | 我们 prod | vision | rapidocr | simd | ppocr5 | winocr |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def fmt(counts: dict) -> str:
        return f"{counts.get('对', 0)}/{counts.get('错', 0)}/{counts.get('没读', 0)}"

    def gap_score(agg: dict) -> int:
        return agg["engine"]["错"] + agg["engine"]["没读"] + agg["prod"]["错"] + agg["prod"]["没读"]

    for name, agg in sorted(by_field.items(), key=lambda kv: -gap_score(kv[1])):
        scenes = ",".join(agg["scenes"])
        cells = [fmt(agg["backends"][b]) for b in BACKENDS]
        lines.append(
            f"| {name} | {scenes} | {fmt(agg['engine'])} | {fmt(agg['prod'])} | " + " | ".join(cells) + " |"
        )
    lines += ["", "## 逐帧 decide（生产判定，720x1280）", "", "| 帧 | 场景 | engine ms | decide |", "|---|---|---|---|"]
    for res in results:
        tick = res.get("tick") or {}
        lines.append(
            f"| {res['id']} | {res['scene']} | {res.get('engine_ms', '-')} | "
            f"{tick.get('screen', '-')}/{tick.get('action', '-')} |"
        )
    lines += [
        "",
        "## opt-in 引擎补全（gkagent.vision.ocr_complete，默认关）",
        "",
        "- deck_left：屏幕卡背小数字 5 后端全没读 → len(LessonSim.deck)（sources_from_sim）",
        "- statuses card_effect：图标状态无文字 → sim 状态镜（调用方投影 card_effects）",
        "- multiplier_pct：OCR 读不到时 → B4 calculate_bonus(屏幕三维, 审查基准, 分数表).permil//10",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", default="", help="只跑某场景（exam/action_select/consult/round_interval）")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--no-decide", action="store_true")
    parser.add_argument("--md", default=str(DATASET / "_bench_report.md"))
    parser.add_argument("--json", default=str(DATASET / "_bench_report.json"))
    args = parser.parse_args(argv)
    doc = load_dataset()
    if doc is None:
        print("matto 数据集缺失（data/_ocr_dataset/truth.json + img/）——本地参考数据不入库，跳过基准。")
        return 0
    engine = make_engine(args.threads)
    if engine is None:
        print("缺少日文 OCR 模型/配置（configs/ocr_jp*.yaml + data/models/ocr_jp）——跳过基准。")
        return 0
    frames = doc["frames"]
    if args.scene:
        frames = [f for f in frames if f["scene"] == args.scene]
    if args.limit:
        frames = frames[: args.limit]
    print(f"matto 基准：{len(frames)} 帧（engine={engine.describe_model()}，threads={args.threads}）", flush=True)
    results = []
    for i, frame in enumerate(frames):
        res = bench_frame(engine, frame, decide=not args.no_decide)
        results.append(res)
        rows = res.get("rows", [])
        eng_ok = sum(1 for r in rows if r["engine"] == "对")
        prod_ok = sum(1 for r in rows if r["prod"] == "对")
        tick = res.get("tick") or {}
        print(
            f"[{i + 1}/{len(frames)}] {frame['id']} {frame['scene']:14s} "
            f"engine {eng_ok}/{len(rows)} prod {prod_ok}/{len(rows)} "
            f"decide={tick.get('screen', '-')}/{tick.get('action', '-')} {res.get('engine_ms', 0):.0f}ms",
            flush=True,
        )
    by_field = aggregate(results)
    md = render_md(doc, results, by_field)
    Path(args.md).write_text(md, encoding="utf-8")
    Path(args.json).write_text(
        json.dumps({"results": results, "by_field": by_field}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    total = sum(len(r.get("rows", [])) for r in results)
    eng_ok = sum(1 for r in results for row in r.get("rows", []) if row["engine"] == "对")
    prod_ok = sum(1 for r in results for row in r.get("rows", []) if row["prod"] == "对")
    print(f"\n总计 {total} 字段：engine 对 {eng_ok}（{eng_ok / max(total, 1):.1%}），prod 对 {prod_ok}")
    print(f"报告：{args.md}\nJSON：{args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
