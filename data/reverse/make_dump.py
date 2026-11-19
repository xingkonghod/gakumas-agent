"""Generate a metadata-only dump.cs for Gakumas (Unity 6 / IL2CPP metadata v31).

The native GameAssembly.dll code sections are encrypted/packed on this build, so
Il2CppDumper cannot recover RVAs.  This tool emits everything that *is* present in
global-metadata.dat: namespaces, types, fields, properties, methods, parameters,
enum constants.  Field/method types are resolved only when the corresponding
Il2CppType index is reachable through a type definition's byvalTypeIndex; other
indices are printed as `type#N`.
"""
import hashlib
import os
import struct
import time

from metadata_parse import Meta
from detail import m, tds, type_label, resolve_type, full_name, read_default_value
from metadata_parse import META

OUT = r"D:\Games\gakumas-agent\data\reverse\out\dump.cs"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "dump.cs")

imgs = m.images()
asm = m.assemblies()
img_of_type = {}
asm_of_type = {}
for im in imgs:
    aname = m.s(asm[im["asm_i"]]["name_i"]) if im["asm_i"] < len(asm) else "?"
    for t in range(im["tstart"], im["tstart"] + im["tcount"]):
        img_of_type[t] = m.s(im["name_i"])
        asm_of_type[t] = aname

ACCESS = {0: "private", 1: "public", 2: "private", 3: "internal", 4: "protected",
          5: "internal", 6: "protected internal", 7: "private protected"}


def type_mods(td):
    flags = td["flags"]
    vis = flags & 0x7
    mods = [ACCESS.get(vis, "internal")]
    if flags & 0x20:
        mods.append("")
    elif flags & 0x80:
        mods.append("abstract")
    if flags & 0x100 and not (flags & 0x20):
        mods.append("sealed")
    if flags & 0x1000:
        mods.append("interface" if (flags & 0x20) else "")
    return " ".join(x for x in mods if x)


def method_mods(md, is_iface=False):
    f = md["flags"]
    mods = []
    vis = f & 0x7
    mods.append(ACCESS.get(vis, "private"))
    if f & 0x10:
        mods.append("static")
    if f & 0x400:
        mods.append("abstract")
    elif f & 0x40 and not (f & 0x800):
        mods.append("virtual")
    if f & 0x800:
        mods.append("special")
    return " ".join(mods)


def prop_type(pd, methods):
    if pd["get"] >= 0:
        return type_label(methods[pd["get"]]["ret"])
    if pd["set"] >= 0:
        p = m.params(methods[pd["set"]]["param_start"], methods[pd["set"]]["pcount"])
        return type_label(p[0]["type_i"]) if p else "?"
    return "?"


def emit_type(w, td):
    name = m.s(td["name_i"])
    ns = m.s(td["ns_i"])
    is_enum = (td["bitfield"] >> 1) & 1
    is_value = bool(td["bitfield"] & 1)
    is_iface = bool(td["flags"] & 0x20)
    fname = full_name(td)
    kind = "enum" if is_enum else ("interface" if is_iface else ("struct" if is_value else "class"))
    parent = type_label(td["parent"]) if td["parent"] >= 0 else None
    mods = type_mods(td)

    w.write(f"// index={td['index']} image={img_of_type.get(td['index'], '?')} "
            f"assembly={asm_of_type.get(td['index'], '?')} token=0x{td['token']:X}\n")
    decl = f"{mods} {kind} {fname}"
    if parent and not is_enum and parent != "System.Object":
        decl += f" : {parent}"
    w.write(decl + "\n{\n")

    fields = m.fields(td["field_start"], td["fcount"]) if td["fcount"] else []
    if is_enum:
        cur = -1
        members = []
        for f in fields:
            fn = m.s(f["name_i"])
            if fn == "value__":
                continue
            fdv = m.fdv_map.get(f["index"])
            if fdv:
                v = read_default_value(fdv[0], fdv[1])
                if v is not None:
                    cur = v
            else:
                cur = cur + 1
            members.append((fn, cur))
        for n, v in members:
            w.write(f"    {n} = {v},\n")
    else:
        if fields:
            w.write("    // Fields\n")
            for f in fields:
                fdv = m.fdv_map.get(f["index"])
                init = ""
                if fdv:
                    v = read_default_value(fdv[0], fdv[1])
                    if v is not None:
                        if isinstance(v, str):
                            init = ' = "' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
                        elif isinstance(v, bool):
                            init = " = " + ("true" if v else "false")
                        else:
                            init = f" = {v}"
                w.write(f"    {type_label(f['type_i'])} {m.s(f['name_i'])}{init}; "
                        f"// field#{f['index']} token=0x{f['token']:X}\n")

        methods = m.methods(td["method_start"], td["mcount"]) if td["mcount"] else []
        props = m.properties(td["property_start"], td["pcount"]) if td["pcount"] else []
        events = m.events(td["event_start"], td["ecount"]) if td["ecount"] else []
        if props:
            w.write("    // Properties\n")
            for pd in props:
                ptype = prop_type(pd, methods) if methods else "?"
                accessors = []
                if pd["get"] >= 0:
                    accessors.append("get;")
                if pd["set"] >= 0:
                    accessors.append("set;")
                w.write(f"    {ptype} {m.s(pd['name_i'])} {{ {' '.join(accessors)} }}\n")
        if events:
            w.write("    // Events\n")
            for ed in events:
                w.write(f"    {type_label(ed['type_i'])} {m.s(ed['name_i'])}\n")
        if methods:
            w.write("    // Methods\n")
            for md in methods:
                ps = m.params(md["param_start"], md["pcount"]) if md["pcount"] else []
                psig = ", ".join(f"{type_label(p['type_i'])} {m.s(p['name_i'])}" for p in ps)
                mods2 = method_mods(md, is_iface)
                w.write(f"    {mods2} {type_label(md['ret'])} {m.s(md['name_i'])}({psig}); "
                        f"// method#{md['index']} token=0x{md['token']:X} flags=0x{md['flags']:X}\n")
    w.write("}\n\n")


def main():
    t0 = time.time()
    h = hashlib.sha256(open(META, "rb").read()).hexdigest()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as w:
        w.write("// =============================================================================\n")
        w.write("// GAKUMAS - METADATA-ONLY IL2CPP DUMP (dump.cs)\n")
        w.write("// =============================================================================\n")
        w.write("// PROVENANCE\n")
        w.write(f"//   global-metadata.dat : {META}\n")
        w.write(f"//   size / sha256       : {os.path.getsize(META)} / {h}\n")
        w.write(f"//   metadata version    : {m.version}\n")
        w.write(f"//   generated (local)   : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        w.write("//\n")
        w.write("// WHY THERE ARE NO RVAs / METHOD BODIES\n")
        w.write("//   GameAssembly.dll on this PC build is packed by the DMM launcher: only a\n")
        w.write("//   4 KiB .text stub and a 114 MB encrypted blob are present on disk.  The real\n")
        w.write("//   .text/.il2cpp/.data sections are zero-filled.  Il2CppDumper therefore cannot\n")
        w.write("//   locate CodeRegistration/MetadataRegistration (and LoadLibrary fails with\n")
        w.write("//   Win32 1114).  This file is generated directly from the unencrypted\n")
        w.write("//   global-metadata.dat, so it contains every name/signature/enum constant but\n")
        w.write("//   no native addresses and no method bodies.\n")
        w.write("//\n")
        w.write("// TYPE LABELS\n")
        w.write("//   `type#N` = index N of the native Il2CppType[] array (lives in GameAssembly\n")
        w.write("//   .data, not in metadata).  An index is resolved when it equals some type\n")
        w.write("//   definition's byvalTypeIndex; otherwise the C# type name cannot be recovered\n")
        w.write("//   from metadata alone.\n")
        w.write("// =============================================================================\n\n")
        w.write(f"// counts: typeDefs={m.type_n} methods={m.method_n} fields={m.field_n} "
                f"parameters={m.param_n} properties={m.prop_n} images={m.image_n}\n\n")

        for im in imgs:
            aname = m.s(asm[im["asm_i"]]["name_i"]) if im["asm_i"] < len(asm) else "?"
            iname = m.s(im["name_i"])
            w.write(f"// ===== ASSEMBLY {aname} ({iname}) types {im['tstart']}..{im['tstart']+im['tcount']-1} =====\n\n")
            for ti in range(im["tstart"], im["tstart"] + im["tcount"]):
                emit_type(w, tds[ti])
    print("wrote", OUT, os.path.getsize(OUT), "bytes in", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
