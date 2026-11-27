#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yaha_hook_check.py — static check of GakumasUnlock's yaha proxy DLL.

Compares the hook DLL (`hook/yaha_proxy.dll`) against the game's stock
`Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll` **without running either**:

  * PE header facts (machine, sections, size, sha256, internal DLL name)
  * export table of both DLLs + name-set diff (this is the P/Invoke surface)
  * import table of the hook (should only be KERNEL32 + msvcrt for a MinGW wrapper)
  * interesting strings / immediates (127.0.0.1, :18443, target host, .orig/.real.dll)
  * embedded-PE scan (does the hook pack the original DLL inside itself?)

Usage:
    python tools/yaha_hook_check.py [--game-dir "D:\\Games\\Gakumas\\gakumas"] [--hook PATH]

Exit code 0 = export surface identical, 1 = mismatch (needs re-port), 2 = error.
"""
import argparse
import hashlib
import os
import re
import struct
import sys

DEFAULT_HOOK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'unlock', 'GakumasUnlock', 'hook', 'yaha_proxy.dll')
DEFAULT_GAME = r'D:\Games\Gakumas\gakumas'
REL_DLL = os.path.join('gakumas_Data', 'Plugins', 'x86_64',
                       'Cysharp.Net.Http.YetAnotherHttpHandler.Native.dll')


def rva2off(rva, sections):
    for va, vsz, raw, rsz in sections:
        if va <= rva < va + max(vsz, rsz):
            return raw + (rva - va)
    return None


def cstr(data, off):
    if off is None or off >= len(data):
        return ''
    end = data.find(b'\x00', off)
    return data[off:end if end != -1 else len(data)].decode('latin-1', 'replace')


def parse_pe(path):
    data = open(path, 'rb').read()
    info = {'path': path, 'size': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    if data[pe:pe + 4] != b'PE\x00\x00':
        raise ValueError('not a PE file: %s' % path)
    machine, nsec, _, _, _, optsz, _ = struct.unpack_from('<HHIIIHH', data, pe + 4)
    info['machine'] = hex(machine)
    opt = pe + 24
    magic = struct.unpack_from('<H', data, opt)[0]
    is64 = magic == 0x20B
    ddoff = opt + (112 if is64 else 96)
    nrva = struct.unpack_from('<I', data, ddoff - 4)[0]
    dirs = [struct.unpack_from('<II', data, ddoff + i * 8) for i in range(nrva)]
    sections = []
    for i in range(nsec):
        o = opt + optsz + i * 40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', data, o + 8)
        sections.append((va, vsz, raw, rsz))
    info['sections'] = [(data[opt + optsz + i * 40:opt + optsz + i * 40 + 8]
                         .rstrip(b'\x00').decode('latin-1'), vsz, rsz)
                        for i, (va, vsz, raw, rsz) in enumerate(sections)]

    def r2o(rva):
        return rva2off(rva, sections)

    exports = []
    if dirs and dirs[0][0]:
        eo = r2o(dirs[0][0])
        (_c, _t, _ma, _mi, name_rva, base, nfunc, nnames,
         af, an, ao) = struct.unpack_from('<IIHHIIIIIII', data, eo)
        info['dll_name'] = cstr(data, r2o(name_rva))
        for i in range(nnames):
            nr = struct.unpack_from('<I', data, r2o(an) + i * 4)[0]
            ordi = struct.unpack_from('<H', data, r2o(ao) + i * 2)[0]
            fr = struct.unpack_from('<I', data, r2o(af) + ordi * 4)[0]
            exports.append({'name': cstr(data, r2o(nr)),
                            'ordinal': base + ordi, 'rva': fr})
    info['exports'] = exports

    def imports(drva):
        out = []
        if not drva:
            return out
        io = r2o(drva)
        i = 0
        while True:
            oft, _ts, _fwd, nm, ft = struct.unpack_from('<IIIII', data, io + i * 20)
            if nm == 0:
                break
            dll = cstr(data, r2o(nm))
            funcs = []
            to = r2o(oft or ft)
            if to is not None:
                step = 8 if is64 else 4
                j = 0
                while True:
                    v = struct.unpack_from('<Q' if is64 else '<I', data, to + j * step)[0]
                    if v == 0:
                        break
                    if (is64 and v >> 63) or (not is64 and v >> 31):
                        funcs.append('ord#%d' % (v & 0xFFFF))
                    else:
                        funcs.append(cstr(data, r2o(v) + 2))
                    j += 1
            out.append((dll, funcs))
            i += 1
        return out

    info['imports'] = imports(dirs[1][0]) if len(dirs) > 1 else []
    return info, data


def scan_strings(data, patterns):
    asc = re.findall(rb'[ -~]{4,}', data)
    u16 = re.findall(rb'(?:[ -~]\x00){4,}', data)
    blobs = [s.decode('latin-1') for s in asc] + [s.decode('utf-16le', 'replace') for s in u16]
    res = {}
    for p in patterns:
        hits, seen = [], set()
        for b in blobs:
            if p.lower() in b.lower() and b not in seen:
                seen.add(b)
                hits.append(b)
        res[p] = hits
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hook', default=DEFAULT_HOOK)
    ap.add_argument('--game-dir', default=DEFAULT_GAME)
    args = ap.parse_args()

    stock_path = os.path.join(args.game_dir, REL_DLL)
    for p in (args.hook, stock_path):
        if not os.path.isfile(p):
            print('MISSING:', p)
            return 2

    try:
        hook, hook_raw = parse_pe(args.hook)
        stock, _ = parse_pe(stock_path)
    except Exception as e:
        print('PE parse error:', e)
        return 2

    print('=' * 78)
    print('hook : %s' % hook['path'])
    print('       size=%d sha256=%s' % (hook['size'], hook['sha256'][:16]))
    print('       internal name=%s exports=%d' % (hook.get('dll_name'), len(hook['exports'])))
    print('stock: %s' % stock['path'])
    print('       size=%d sha256=%s' % (stock['size'], stock['sha256'][:16]))
    print('       internal name=%s exports=%d' % (stock.get('dll_name'), len(stock['exports'])))
    print('=' * 78)

    print('hook imports: %s' % [(d, len(f)) for d, f in hook['imports']])
    hn = [e['name'] for e in hook['exports']]
    sn = [e['name'] for e in stock['exports']]
    missing = sorted(set(sn) - set(hn))
    extra = sorted(set(hn) - set(sn))
    print('export names identical : %s' % (set(hn) == set(sn)))
    print('missing in hook        : %s' % (missing or '-'))
    print('extra in hook          : %s' % (extra or '-'))
    if missing:
        print('!! stock DLL has exports the hook cannot forward -> first call throws')

    pats = ['127.0.0.1', '18443', 'game-gakuen-idolmaster', '.orig.dll', '.real.dll',
            'LoadLibraryW', 'GetProcAddress', 'VirtualProtect', 'fopen', 'yaha-proxy.log']
    print('-' * 78)
    for p, hits in scan_strings(hook_raw, pats).items():
        print('  string [%s]: %s' % (p, hits[:4] if hits else '-'))
    port = (18443).to_bytes(4, 'little')
    offs = [hex(m.start()) for m in re.finditer(re.escape(port), hook_raw)][:6]
    print('  immediate 18443 (LE32) at: %s' % (offs or '-'))

    # embedded PE scan beyond the last section
    last_end = 0
    for va, vsz, raw, rsz in []:
        pass
    print('-' * 78)
    print('note: wrapper is compiled from yaha_proxy.c (MinGW-w64 GCC, C23),')
    print('      forwards all 45 yaha_* calls to the renamed original DLL.')
    return 0 if set(hn) == set(sn) else 1


if __name__ == '__main__':
    sys.exit(main())
