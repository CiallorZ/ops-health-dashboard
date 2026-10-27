import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DashboardBehaviorTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_scheduler_state_rendering(self):
        subprocess.run(["node", "tests/dashboard_behavior.cjs"], cwd=ROOT, check=True, timeout=10)
