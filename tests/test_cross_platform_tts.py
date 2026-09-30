from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("prepare_narration", ROOT / "scripts" / "prepare_narration.py")
assert SPEC and SPEC.loader
prepare_narration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_narration)


class CrossPlatformTtsTests(unittest.TestCase):
    def test_windows_uses_powershell_system_speech(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            prepare_narration.platform, "system", return_value="Windows"
        ), patch.object(prepare_narration.shutil, "which", side_effect=lambda name: "powershell.exe" if name == "powershell" else None), patch.object(
            prepare_narration.subprocess, "check_call"
        ) as call:
            prepare_narration.system_tts("测试口播", Path(directory) / "voice.wav", "", 230)
        command = call.call_args.args[0]
        self.assertEqual(command[0], "powershell.exe")
        self.assertIn("-File", command)

    def test_unsupported_platform_has_clear_error(self):
        with patch.object(prepare_narration.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(RuntimeError, "macOS and Windows"):
                prepare_narration.system_tts("test", Path("voice.wav"), "", 230)


if __name__ == "__main__":
    unittest.main()
