from pathlib import Path

p = Path("data/bench_repo/submissions/gkagent-ex-seed-v6/algo.py")
s = p.read_text(encoding="utf-8")

# 1) __init__ body: partial_tail / partial_min
old = '        self.expect_init = max(0.1, float(expect_init))\n'
new = ('        self.expect_init = max(0.1, float(expect_init))\n'
       '        self.partial_tail = bool(int(partial_tail))   # 预算尾巴发 anytime 短搜（不越界）\n'
       '        self.partial_min = max(0.05, float(partial_min))\n')
assert s.count(old) == 1, s.count(old)
s = s.replace(old, new)

# 2) _note_search_time: deadline-hit censoring
old = ('    def _note_search_time(self, trans, st):\n')
new = ('    def _note_search_time(self, trans, st, sec=None):\n')
assert s.count(old) == 1
s = s.replace(old, new)
old = ('        if per <= 0.0:\n            return\n        key = int(trans)\n')
new = ('        if per <= 0.0:\n            return\n'
       '        try:\n'
       '            hit = bool(sec) and float(st.get("elapsed_seconds") or 0.0) >= float(sec) * 0.95\n'
       '        except Exception:  # noqa: BLE001\n'
       '            hit = False\n'
       '        if hit:\n'
       '            per *= 1.25                          # 撞 deadline：真实需要更长 → 预期上调\n'
       '        key = int(trans)\n')
assert s.count(old) == 1
s = s.replace(old, new)
s = s.replace("self._note_search_time(trans, st)", "self._note_search_time(trans, st, sec)")

# 3) describe(): partial_tail/partial_min
old = ('                       "expect_init": self.expect_init,\n')
new = ('                       "expect_init": self.expect_init,\n'
       '                       "partial_tail": int(self.partial_tail), "partial_min": self.partial_min,\n')
assert s.count(old) == 1
s = s.replace(old, new)

p.write_text(s, encoding="utf-8")
import ast
ast.parse(s)
print("patched + syntax OK; lines", s.count("\n"))
for k in ("partial_tail", "partial_min", "_note_search_time(trans, st, sec)", "pool_partial", "next_spec"):
    print(k, s.count(k))