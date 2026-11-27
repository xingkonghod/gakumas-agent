from pathlib import Path

p = Path("data/_v6_tail3.py")
s = p.read_text(encoding="utf-8")

s = s.replace(
    "def calibrate():\n    nat = engine.native()[0]\n    TN._bind(nat)\n    return nat",
    'class _Cal:\n'
    '    """借用 v6 algo 的 tail 时钟纪元校准（DLL steady_clock 纪元随编译器不同）。"""\n'
    '    def __init__(self):\n'
    '        self.algo = V6.ExSeedV6Algo(report=0)\n'
    '        self.algo._load()\n'
    '\n'
    '    def bind(self, session):\n'
    '        self.algo._calibrate_tail(TN, session)\n'
    '\n'
    '\n'
    'def calibrate():\n    nat = engine.native()[0]\n    TN._bind(nat)\n    return nat',
)
s = s.replace(
    "def tail(session, nat, threads, seconds, node_cap):\n    t0 = time.perf_counter()",
    "def tail(session, nat, threads, seconds, node_cap, cal=None):\n"
    "    if cal is not None:\n        cal.bind(session)\n"
    "    t0 = time.perf_counter()",
)
s = s.replace("def main():\n    nat = calibrate()", "def main():\n    nat = calibrate()\n    cal = _Cal()")
s = s.replace("r = tail(session.clone(), nat, threads, seconds, cap)",
              "r = tail(session.clone(), nat, threads, seconds, cap, cal)")
p.write_text(s, encoding="utf-8")
import ast
ast.parse(s)
print("patched ok")
for k in ("_Cal", "cal.bind", "cap, cal"):
    print(k, s.count(k))