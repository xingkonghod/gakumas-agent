"""M1 pytest 计数 runner（不提交）：用插件可靠记录 passed/failed/skipped。"""
import pytest, sys, json
from pathlib import Path

class Counter:
    def __init__(self):
        self.counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
        self.failed = []
    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            if report.passed: self.counts["passed"] += 1
            elif report.failed:
                self.counts["failed"] += 1
                self.failed.append(report.nodeid)
            elif report.skipped: self.counts["skipped"] += 1
        elif report.when in ("setup", "teardown") and report.failed:
            self.counts["error"] += 1
            self.failed.append(report.nodeid + " (" + report.when + ")")
        elif report.when == "setup" and report.skipped:
            self.counts["skipped"] += 1

c = Counter()
rc = pytest.main(["--basetemp=out/_pytest_tmp_m1", "-p", "no:cacheprovider", "--tb=no", "-q"], plugins=[c])
out = {"counts": c.counts, "failed": c.failed, "exit": int(rc)}
Path("out/_m1_pytest_counts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("COUNTS", json.dumps(c.counts), "exit", int(rc))
print("FAILED", c.failed)
