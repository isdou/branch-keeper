import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PLUGIN_ROOT / "scripts" / "branch_keeper_launcher.mjs"
MCP_SERVER = PLUGIN_ROOT / "scripts" / "branch_keeper_mcp.py"


class LauncherTests(unittest.TestCase):
    def test_launcher_forwards_mcp_request(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")

        with tempfile.TemporaryDirectory() as home:
            environment = os.environ.copy()
            environment["BRANCH_KEEPER_HOME"] = home
            environment["BRANCH_KEEPER_PYTHON"] = sys.executable
            process = subprocess.run(
                [node, str(LAUNCHER), str(MCP_SERVER)],
                input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n",
                text=True,
                capture_output=True,
                check=True,
                timeout=10,
                env=environment,
            )

        response = json.loads(process.stdout.strip())
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"], {})


if __name__ == "__main__":
    unittest.main()
