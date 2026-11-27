# -*- coding: utf-8 -*-
"""一次性：D 盘 vs C 盘副本文件清单差集 + 新 exe 导入表。"""
import struct
from pathlib import Path

D = Path(r"D:\Games\Gakumas\gakumas")
C = Path(r"C:\GakumasLocal")
SKIP_DIRS = {"octo", "gakumas-local", "_backup_pre_361", "GakumasUnlock"}

def relset(root: Path):
    out = set()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if parts[0] in SKIP_DIRS:
            continue
        s = str(rel).lower()
        if s.endswith((".dmp", ".log", ".bak")) or ".bak-" in s or s.endswith(".orig.dll"):
            continue
        out.add(str(rel))
    return out

dset, cset = relset(D), relset(C)
missing = sorted(dset - cset)
extra = sorted(cset - dset)
print(f"D files={len(dset)} C files={len(cset)}")
print(f"== in D but NOT in C ({len(missing)}) ==")
for m in missing[:80]:
    print("  MISSING:", m)
print(f"== in C but not in D ({len(extra)}) ==")
for e in extra[:20]:
    print("  extra:", e)

# PE imports of new exe
def imports(path: Path):
    data = open(path, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec, = struct.unpack_from("<H", data, pe + 6)
    optsz, = struct.unpack_from("<H", data, pe + 20)
    opt = pe + 24
    magic, = struct.unpack_from("<H", data, opt)[0]
    is64 = magic == 0x20B
    ddoff = opt + (112 if is64 else 96)
    imp_rva, imp_size = struct.unpack_from("<II", data, ddoff + 8)
    secs = []
    secoff = opt + optsz
    for i in range(nsec):
        off = secoff + i * 40
        va, vsz, raw, rsz = struct.unpack_from("<IIII", data, off + 12)
        secs.append((va, vsz, raw, rsz))
    def r2o(rva):
        for va, vsz, raw, rsz in secs:
            if va <= rva < va + max(vsz, rsz):
                return raw + (rva - va)
        return None
    def cstr(off):
        e = data.find(b"\x00", off)
        return data[off:e].decode("latin-1")
    names = []
    off = r2o(imp_rva)
    while True:
        ilt, ts, fc, name_rva, iat = struct.unpack_from("<IIIII", data, off)
        if name_rva == 0:
            break
        names.append(cstr(r2o(name_rva)))
        off += 20
    return names

print("== new gakumas.exe imports ==")
for n in imports(C / "gakumas.exe"):
    print("  ", n)