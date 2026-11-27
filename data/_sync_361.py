# -*- coding: utf-8 -*-
"""一次性脚本：把 D 盘今天（2026-11-24）的 v3.6.1 更新集同步到 C 盘采集副本。

- 只复制今天修改过的游戏文件（排除 gakumas-local 运行时产物与 gakumas.exe._ 备份）
- 先备份 C 盘旧版关键二进制到 C:\\GakumasLocal\\_backup_pre_361（可回滚）
- 逐文件 sha256 校验
- 最后把新版官方 Native.dll 立为 .orig.dll（hook 转发真身），旧 .orig 备份
不提交（data/_* 纪律）。
"""
import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path

D = Path(r"D:\Games\Gakumas\gakumas")
C = Path(r"C:\GakumasLocal")
BAK = C / "_backup_pre_361"
CUTOFF = datetime(2026, 11, 24, 0, 0, 0)
NATIVE_REL = Path("gakumas_Data/Plugins/x86_64/Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll")

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    # 1. 枚举今天的更新集
    files = []
    for p in D.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(D)
        s = str(rel).replace("\\", "/")
        if s.startswith("gakumas-local/") or s == "gakumas.exe._":
            continue
        try:
            mt = datetime.fromtimestamp(p.stat().st_mtime)
        except OSError:
            continue
        if mt >= CUTOFF:
            files.append(rel)
    files.sort(key=lambda r: str(r))
    print(f"更新集: {len(files)} 个文件")

    # 2. 备份 C 盘旧版关键二进制
    key_rels = [
        Path("gakumas.exe"),
        Path("GameAssembly.dll"),
        Path("gakumas_Data/boot.config"),
        Path("gakumas_Data/il2cpp_data/Metadata/global-metadata.dat"),
        NATIVE_REL,
        NATIVE_REL.with_name(NATIVE_REL.name.replace(".dll", ".orig.dll")),
    ]
    BAK.mkdir(exist_ok=True)
    for rel in key_rels:
        src = C / rel
        if src.exists():
            dst = BAK / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copy2(src, dst)
                print(f"备份旧版: {rel} ({src.stat().st_size} bytes)")

    # 3. 逐文件复制 + 校验
    ok = fail = skip = 0
    total = 0
    for rel in files:
        src, dst = D / rel, C / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dst.exists() and dst.stat().st_size == src.stat().st_size and sha(dst) == sha(src):
                skip += 1
                continue
            shutil.copy2(src, dst)
            if sha(dst) != sha(src):
                print(f"!! 哈希不一致: {rel}")
                fail += 1
                continue
            ok += 1
            total += src.stat().st_size
        except OSError as e:
            print(f"!! 复制失败 {rel}: {e}")
            fail += 1
    print(f"复制完成: ok={ok} skip(已一致)={skip} fail={fail} 新增字节={total/1e6:.1f}MB")

    # 4. 新官方 Native.dll → .orig.dll（hook 转发真身）
    new_stock = C / NATIVE_REL
    orig = C / NATIVE_REL.with_name(NATIVE_REL.name.replace(".dll", ".orig.dll"))
    if new_stock.exists():
        # 确认现在 Native.dll 是官方新版（internal name yaha_native.dll 由 hook_check 已验证）
        shutil.copy2(new_stock, orig)
        print(f".orig.dll 已更新为新版官方 ({orig.stat().st_size} bytes, sha={sha(orig)[:16]}…)")
    else:
        print("!! 新版 Native.dll 不存在")
        fail += 1

    # 5. 关键文件终态
    for rel in [Path("gakumas.exe"), Path("GameAssembly.dll"), Path("gakumas_Data/boot.config"),
                Path("gakumas_Data/il2cpp_data/Metadata/global-metadata.dat"), NATIVE_REL]:
        p = C / rel
        print(f"终态: {rel} size={p.stat().st_size} sha={sha(p)[:16]}…")
    return 1 if fail else 0

if __name__ == "__main__":
    sys.exit(main())