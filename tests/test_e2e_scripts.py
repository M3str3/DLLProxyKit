from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dllproxykit.core.common import PAYLOAD_NAME

ROOT = Path(__file__).resolve().parents[1]


def _kit(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dllproxykit", *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


class ScriptProxyE2E(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dllproxykit_e2e_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.marker = self.tmp / "ran.txt"
        self.payload_out = self.tmp / "payload_out.txt"
        py = sys.executable.replace("\\", "\\\\")
        out = str(self.payload_out).replace("\\", "\\\\")
        self.payload = f'{py} -c "open(r\'{out}\', \'w\').write(\'payload\\n\')"'

    def _proxy(self, include: str) -> None:
        result = _kit(
            "proxy",
            str(self.tmp),
            "--command",
            self.payload,
            "-i",
            include,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        _write(self.tmp / PAYLOAD_NAME, self.payload + "\n")

    def test_bat_runs_payload_then_orig(self) -> None:
        _write(self.tmp / "hello.bat", f'@echo orig>> "{self.marker}"\r\n')
        self._proxy("bat")
        self.assertTrue((self.tmp / "hello.original.bat").is_file())
        ran = subprocess.run(
            ["cmd", "/c", str(self.tmp / "hello.bat")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertIn("payload", self.payload_out.read_text(encoding="utf-8"))
        self.assertIn("orig", self.marker.read_text(encoding="utf-8"))

    def test_py_runs_payload_then_orig(self) -> None:
        _write(
            self.tmp / "hello.py",
            f"from pathlib import Path\nPath({str(self.marker)!r}).write_text('orig\\n')\n",
        )
        self._proxy("py")
        self.assertTrue((self.tmp / "hello.original.py").is_file())
        ran = subprocess.run(
            [sys.executable, str(self.tmp / "hello.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr + ran.stdout)
        self.assertIn("payload", self.payload_out.read_text(encoding="utf-8"))
        self.assertIn("orig", self.marker.read_text(encoding="utf-8"))

    def test_ps1_runs_payload_then_orig(self) -> None:
        _write(self.tmp / "hello.ps1", f"Set-Content -LiteralPath '{self.marker}' -Value orig\n")
        self._proxy("ps1")
        self.assertTrue((self.tmp / "hello.cmd").is_file())
        ran = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.tmp / "hello.ps1"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr + ran.stdout)
        self.assertIn("payload", self.payload_out.read_text(encoding="utf-8"))
        self.assertIn("orig", self.marker.read_text(encoding="utf-8"))
        self.payload_out.write_text("", encoding="utf-8")
        self.marker.write_text("", encoding="utf-8")
        ran = subprocess.run(
            ["cmd", "/c", str(self.tmp / "hello.cmd")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr + ran.stdout)
        self.assertIn("payload", self.payload_out.read_text(encoding="utf-8"))
        self.assertIn("orig", self.marker.read_text(encoding="utf-8"))

    def test_pl_runs_payload_then_orig(self) -> None:
        perl = shutil.which("perl")
        if not perl:
            self.skipTest("perl not on PATH")
        marker = str(self.marker).replace("\\", "\\\\")
        _write(self.tmp / "hello.pl", f'open my $f, ">", "{marker}"; print $f "orig\\n";\n')
        self._proxy("pl")
        ran = subprocess.run(
            [perl, str(self.tmp / "hello.pl")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr + ran.stdout)
        self.assertIn("payload", self.payload_out.read_text(encoding="utf-8"))
        self.assertIn("orig", self.marker.read_text(encoding="utf-8"))

    def test_include_skips_other_kinds(self) -> None:
        _write(self.tmp / "hello.bat", "echo bat\n")
        _write(self.tmp / "hello.py", "print('py')\n")
        self._proxy("py")
        self.assertTrue((self.tmp / "hello.original.py").is_file())
        self.assertFalse((self.tmp / "hello.original.bat").exists())

    def test_revert_restores_script(self) -> None:
        original = b"@echo original\r\n"
        (self.tmp / "hello.bat").write_bytes(original)
        self._proxy("bat")
        result = _kit("revert", str(self.tmp), "-i", "bat")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse((self.tmp / "hello.original.bat").exists())
        self.assertEqual((self.tmp / "hello.bat").read_bytes(), original)
        self.assertFalse((self.tmp / PAYLOAD_NAME).exists())


if __name__ == "__main__":
    unittest.main()
