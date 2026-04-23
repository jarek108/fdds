import os
import sys
import pytest

class IntegrityPlugin:
    def __init__(self):
        self.passed = 0
        self.model_failed = 0
        self.engine_failed = 0
        self.skipped = 0
        self.results = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            if report.passed:
                self.passed += 1
                self.results.append((report.nodeid, "[PASSED]", None))
            elif report.failed:
                # Differentiate based on explicit [MODEL_EVAL] tag in the assertion message
                if "[MODEL_EVAL]" in str(report.longrepr):
                    self.model_failed += 1
                    self.results.append((report.nodeid, "[MODEL FAIL]", str(report.longrepr).split('\n')[-2:]))
                else:
                    self.engine_failed += 1
                    self.results.append((report.nodeid, "[ENGINE FAIL]", str(report.longrepr).split('\n')[-2:]))
            elif report.skipped:
                self.skipped += 1
                self.results.append((report.nodeid, "[SKIPPED]", None))
        elif report.when == "setup" and report.failed:
             self.engine_failed += 1
             self.results.append((report.nodeid, "[ENGINE FAIL - SETUP]", str(report.longrepr).split('\n')[-2:]))

def run_tests():
    print("="*80)
    print("FDDS INTEGRITY BATTERY")
    print("="*80)
    
    plugin = IntegrityPlugin()
    
    # Ensure project root is in sys.path for pytest collection
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Run pytest quietly, injecting our plugin
    retcode = pytest.main(["-q", "--tb=short", "tests/integration"], plugins=[plugin])
    
    print("\n" + "="*80)
    print("BATTERY RESULTS SUMMARY")
    print("="*80)
    
    for nodeid, status, details in plugin.results:
        print(f"{status.ljust(15)} {nodeid}")
        if details:
            print(f"                {details[0].strip()}")
            if len(details) > 1:
                print(f"                {details[1].strip()}")
    
    print("\n" + "="*80)
    print(f"FINAL: {plugin.passed} PASSED, {plugin.model_failed} MODEL FAIL, {plugin.engine_failed} ENGINE FAIL, {plugin.skipped} SKIPPED")
    print("="*80)
    
    if plugin.engine_failed > 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    # Ensure we run from fdds root
    if not os.path.exists("tests/integration"):
        print("Please run from the fdds directory.")
        sys.exit(1)
    run_tests()
