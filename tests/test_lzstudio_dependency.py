from __future__ import annotations

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workbuddy_preflight", ROOT / "scripts" / "workbuddy_preflight.py")
assert SPEC and SPEC.loader
workbuddy_preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workbuddy_preflight)


class LzstudioDependencyTests(unittest.TestCase):
    def preflight(self, system: str, machine: str) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with patch.object(workbuddy_preflight.platform, "system", return_value=system), patch.object(
            workbuddy_preflight.platform, "machine", return_value=machine
        ), patch.object(workbuddy_preflight.shutil, "which", return_value="/usr/bin/tool"), patch.object(
            workbuddy_preflight, "find_lzstudio", return_value=""
        ), redirect_stdout(output):
            code = workbuddy_preflight.main()
        return code, json.loads(output.getvalue())

    def test_macos_missing_cli_blocks_fallback_and_returns_installer(self):
        code, result = self.preflight("Darwin", "arm64")
        self.assertEqual(code, 1)
        self.assertFalse(result["fallbackAllowed"])
        self.assertEqual(result["blockingDependency"], "lzstudio")
        self.assertEqual(result["install"]["command"], "python3 scripts/install_lzstudio_download.py")
        self.assertTrue(result["install"]["requiresUserConfirmation"])
        self.assertTrue(any("video-use" in step for step in result["nextSteps"]))

    def test_windows_missing_cli_returns_windows_installer(self):
        code, result = self.preflight("Windows", "AMD64")
        self.assertEqual(code, 1)
        self.assertFalse(result["fallbackAllowed"])
        self.assertEqual(result["install"]["command"], r"py -3 scripts\install_lzstudio_download.py")


if __name__ == "__main__":
    unittest.main()
