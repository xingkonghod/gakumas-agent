"""下载官方日文/多语言 OCR 模型（PP-OCRv6 small det + rec，Apache-2.0）。

为什么需要：RapidOCR 内置的是中文模型（ch_PP-OCRv4，字典无假名），日文剧情/选项只能
读出汉字碎片；换成官方的 PP-OCRv6 small 多语言模型后完整日文可读（A1，见
docs/GROUP_FILES_ANALYSIS.md §1–2）。

产出（都不入库，data/models/* 已 gitignore）：
    data/models/ocr_jp/det.onnx        PP-OCRv6_small_det（ONNX）
    data/models/ocr_jp/rec.onnx        PP-OCRv6_small_rec（ONNX）
    data/models/ocr_jp/keys.txt        18,708 行字符字典（从 rec 的 inference.yml 导出）
    data/models/ocr_jp/downloads/      原始 tar（离线重装用；可手动删）
    configs/ocr_jp.yaml                本机配置（从 configs/ocr_jp.example.yaml 复制；gitignore）

生成 configs/ocr_jp.yaml 后，``OcrEngine()`` 默认就会加载日文模型；删掉该文件即回到
内置中文模型。也可以 ``set GKAGENT_OCR_CONFIG=...`` 或显式传 ``config_path=``。

用法::

    .venv\\Scripts\\python.exe scripts\\download_ocr_models.py            # 下载 + 校验 + 生成配置
    .venv\\Scripts\\python.exe scripts\\download_ocr_models.py --check    # 只校验已有文件（新会话自检）
    .venv\\Scripts\\python.exe scripts\\download_ocr_models.py --force    # 忽略缓存重新下载
    .venv\\Scripts\\python.exe scripts\\download_ocr_models.py --skip-hash-shas  # 上游换包时临时跳过 sha256

下载完可验证：``.venv\\Scripts\\python.exe scripts\\ocr_probe.py data/auto/step_025.png``
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tarfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "models" / "ocr_jp"
DOWNLOAD_DIR = TARGET / "downloads"
CONFIG_EXAMPLE = ROOT / "configs" / "ocr_jp.example.yaml"
CONFIG_LOCAL = ROOT / "configs" / "ocr_jp.yaml"

BASE_URL = (
    "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
)

# 模型包固定版本 + sha256（下载后校验；官方 tar 换包/被替换时能立刻发现）。
PACKAGES: dict[str, dict[str, str]] = {
    "det": {
        "tar": "PP-OCRv6_small_det_onnx_infer.tar",
        "tar_sha256": "d218f6fbf0f1c23d2161bd6ac7f5eaa6104fa89955c09290497e31008e2618e4",
        "onnx_sha256": "d73e0058b7a8086bbd57f3d10b8bcd4ff95363f67e06e2762b5e814fe9c9410e",
    },
    "rec": {
        "tar": "PP-OCRv6_small_rec_onnx_infer.tar",
        "tar_sha256": "d267ab077a44a0eedb1ea8f8c542d263f211de8e9d7a029bf9fcfff7e5a88fb1",
        "onnx_sha256": "5435fd747c9e0efe15a96d0b378d5bd157e9492ed8fd80edf08f30d02fa24634",
    },
}
EXPECTED_KEYS = 18_708
# keys.txt 内容固定（从按 sha256 锁定的 rec inference.yml 导出），顺手校验。
KEYS_SHA256 = "769e7fa79bb297b5f18d8dbd149e364a45bc61f2b3f574e5ea836f0b261c23a6"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _progress_hook(started: float, total: int):
    """简单下载进度：每 ~5MB 打一行（stdout 被重定向时也不刷屏）。"""

    state = {"next": 5 << 20}

    def report(done: int) -> None:
        if done >= state["next"] or (total and done >= total):
            elapsed = max(time.perf_counter() - started, 1e-3)
            speed = done / elapsed / (1 << 20)
            total_text = f"/{total / (1 << 20):.1f}MB" if total else ""
            print(f"    {done / (1 << 20):.1f}MB{total_text}  {speed:.1f}MB/s", flush=True)
            state["next"] = done + (5 << 20)

    return report


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  下载 {url}")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=60) as response, tmp.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            report = _progress_hook(started, total)
            done = 0
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                report(done)
    except Exception as exc:  # 统一给可操作的提示
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"下载失败：{exc}\n"
            f"  URL: {url}\n"
            "  检查网络/代理；离线机器可手动用 curl/浏览器下载后放到 "
            f"{dest.parent}（文件名不变），再重跑本脚本（会校验 sha256）。"
        ) from exc
    tmp.replace(dest)
    print(f"  已保存 {dest}（{dest.stat().st_size / (1 << 20):.1f}MB）")


def _tar_member_bytes(tar_path: Path, filename: str) -> bytes:
    """安全读取 tar 里的一个文件（拒绝绝对路径/.. 穿越，不落盘解压）。"""
    with tarfile.open(tar_path) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            parts = PurePosixPath(member.name).parts
            if any(part in ("..", "") for part in parts) or member.name.startswith("/"):
                continue
            if PurePosixPath(member.name).name != filename:
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            return extracted.read()
    raise SystemExit(f"tar 包里找不到 {filename}：{tar_path}")


def ensure_package(key: str, *, force: bool, skip_hash: bool) -> None:
    spec = PACKAGES[key]
    tar_path = DOWNLOAD_DIR / spec["tar"]
    onnx_path = TARGET / f"{key}.onnx"

    tar_ok = (
        tar_path.is_file()
        and (skip_hash or sha256_file(tar_path) == spec["tar_sha256"])
    )
    if tar_ok and not force:
        print(f"[{key}] 用已有下载包 {tar_path.name}")
    else:
        download(f"{BASE_URL}/{spec['tar']}", tar_path)
        actual = sha256_file(tar_path)
        if not skip_hash and actual != spec["tar_sha256"]:
            raise SystemExit(
                f"[{key}] 下载包 sha256 不匹配（模型可能更新/被替换）\n"
                f"  期望 {spec['tar_sha256']}\n  实际 {actual}\n"
                "  确认来源可信后可用 --skip-hash-shas 重新下载并更新脚本里的 sha256。"
            )

    payload = _tar_member_bytes(tar_path, "inference.onnx")
    actual = hashlib.sha256(payload).hexdigest()
    if not skip_hash and actual != spec["onnx_sha256"]:
        raise SystemExit(
            f"[{key}] inference.onnx sha256 不匹配：期望 {spec['onnx_sha256']} 实际 {actual}"
        )
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    onnx_path.write_bytes(payload)
    print(f"[{key}] ✅ {onnx_path}（{len(payload) / (1 << 20):.1f}MB）")


def ensure_key_dict(*, skip_hash: bool) -> None:
    """从 rec 包的 inference.yml 导出 RapidOCR 用的逐行字典 keys.txt。"""
    import yaml

    tar_path = DOWNLOAD_DIR / PACKAGES["rec"]["tar"]
    raw = _tar_member_bytes(tar_path, "inference.yml")
    meta = yaml.safe_load(raw.decode("utf-8"))
    try:
        chars = meta["PostProcess"]["character_dict"]
    except (KeyError, TypeError) as exc:
        raise SystemExit(f"rec 的 inference.yml 里找不到 PostProcess.character_dict：{exc}") from exc
    if not isinstance(chars, list) or len(chars) != EXPECTED_KEYS:
        raise SystemExit(
            f"字符字典条数不对：期望 {EXPECTED_KEYS}，实际 {len(chars) if isinstance(chars, list) else 'N/A'}"
        )
    text = "\n".join(str(char) for char in chars) + "\n"
    keys_path = TARGET / "keys.txt"
    keys_path.write_text(text, encoding="utf-8")
    actual = sha256_file(keys_path)
    if not skip_hash and actual != KEYS_SHA256:
        raise SystemExit(f"keys.txt sha256 不匹配：期望 {KEYS_SHA256} 实际 {actual}")
    print(f"[rec] ✅ {keys_path}（{len(chars)} 个字符）")


def ensure_local_config(*, force: bool) -> None:
    if not CONFIG_EXAMPLE.is_file():
        raise SystemExit(f"缺少模板配置：{CONFIG_EXAMPLE}")
    if CONFIG_LOCAL.is_file() and not force:
        print(f"[config] 已存在，保持不动：{CONFIG_LOCAL}（--force 可重置）")
        return
    shutil.copyfile(CONFIG_EXAMPLE, CONFIG_LOCAL)
    print(f"[config] ✅ {CONFIG_LOCAL}（从 example 复制；OcrEngine 默认加载）")


def check() -> int:
    print("== 校验日文 OCR 模型 ==")
    failures = 0
    for key, spec in PACKAGES.items():
        path = TARGET / f"{key}.onnx"
        if not path.is_file():
            print(f"[{key}] ❌ 缺少 {path}")
            failures += 1
            continue
        actual = sha256_file(path)
        ok = actual == spec["onnx_sha256"]
        print(f"[{key}] {'✅' if ok else '❌'} {path.name} sha256={actual[:16]}…")
        failures += 0 if ok else 1
    keys_path = TARGET / "keys.txt"
    if not keys_path.is_file():
        print(f"[keys] ❌ 缺少 {keys_path}")
        failures += 1
    else:
        count = len(keys_path.read_text(encoding="utf-8").splitlines())
        ok = count == EXPECTED_KEYS and sha256_file(keys_path) == KEYS_SHA256
        print(f"[keys] {'✅' if ok else '❌'} {count} 个字符")
        failures += 0 if ok else 1
    if CONFIG_LOCAL.is_file():
        print(f"[config] ✅ {CONFIG_LOCAL}")
    else:
        print(f"[config] ❌ 缺少 {CONFIG_LOCAL}（用本脚本不带 --check 运行可生成）")
        failures += 1
    print(f"\n结果：{'全部就绪' if failures == 0 else f'{failures} 项待修复'}")
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="只校验已有模型，不下载")
    parser.add_argument("--force", action="store_true", help="强制重新下载/覆盖配置")
    parser.add_argument(
        "--skip-hash-shas",
        action="store_true",
        help="跳过 sha256 校验（仅上游换包且确认来源可信时临时用）",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check()

    print(f"目标目录：{TARGET}")
    TARGET.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for key in ("det", "rec"):
        ensure_package(key, force=args.force, skip_hash=args.skip_hash_shas)
    ensure_key_dict(skip_hash=args.skip_hash_shas)
    ensure_local_config(force=args.force)

    print("\n下一步：")
    print("  1) 校验：.venv\\Scripts\\python.exe scripts\\download_ocr_models.py --check")
    print("  2) 试读：.venv\\Scripts\\python.exe scripts\\ocr_probe.py data/auto/step_025.png")
    print("  3) 之后所有脚本（auto_produce / 离线回放 / pytest 真机帧用例）默认用日文模型。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
