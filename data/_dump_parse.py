# -*- coding: utf-8 -*-
"""一次性：minidump 栈扫描 + 异常参数 + exe 导入表。"""
import struct
import sys
from pathlib import Path
from minidump.minidumpfile import MinidumpFile

path = sys.argv[1]
mf = MinidumpFile.parse(path)

mods = [(m.baseaddress, m.size, m.name.split("\\")[-1]) for m in mf.modules.modules]
print("modules:", [(hex(b), hex(s), n) for b, s, n in mods])

rec = mf.exception.exception_records[0]
er = rec.ExceptionRecord
print("ExceptionCode:", er.ExceptionCode)
print("ExceptionAddress:", hex(er.ExceptionAddress))
print("NumberParameters:", er.NumberParameters)
try:
    print("ExceptionInformation:", [hex(x) for x in er.ExceptionInformation])
except Exception as e:
    print("info err:", e)
print("exception thread id:", rec.ThreadId)

# thread contexts + stack scan
segs = []
try:
    for s in mf.memory_segments_64.memory_segments:
        segs.append((s.start_virtual_address, s.size, s.start_file_address))
except Exception as e:
    print("seg err:", e)

def read_mem(addr, size):
    for start, sz, foff in segs:
        if start <= addr < start + sz:
            with open(path, "rb") as f:
                f.seek(foff + (addr - start))
                return f.read(min(size, start + sz - addr))
    return None

for t in mf.threads.threads:
    if t.ThreadId != rec.ThreadId:
        continue
    ctx = t.ContextObject
    rip = getattr(ctx, "Rip", None)
    rsp = getattr(ctx, "Rsp", None)
    print(f"thread {t.ThreadId}: Rip={hex(rip) if rip else '?'} Rsp={hex(rsp) if rsp else '?'}")
    if rsp:
        stack = read_mem(rsp, 4096)
        if stack:
            print("stack scan (values in module ranges):")
            seen = 0
            for i in range(0, len(stack) - 8, 8):
                v = struct.unpack_from("<Q", stack, i)[0]
                for b, s, n in mods:
                    if b <= v < b + s:
                        print(f"  rsp+0x{i:03x}: 0x{v:016x} = {n}+0x{v-b:x}")
                        seen += 1
                        break
                if seen > 40:
                    break

# exe imports
def imports(p: Path):
    data = open(p, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    is64 = magic == 0x20B
    ddoff = opt + (112 if is64 else 96)
    imp_rva = struct.unpack_from("<I", data, ddoff + 8)[0]
    secs = []
    for i in range(nsec):
        off = opt + optsz + i * 40
        va, vsz, raw, rsz = struct.unpack_from("<IIII", data, off + 12)
        secs.append((va, vsz, raw, rsz))
    def r2o(rva):
        for va, vsz, raw, rsz in secs:
            if va <= rva < va + max(vsz, rsz):
                return raw + (rva - va)
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

print("== C-copy gakumas.exe imports ==")
print(imports(Path(r"C:\GakumasLocal\gakumas.exe")))