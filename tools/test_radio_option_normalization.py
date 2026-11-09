#!/usr/bin/env python3
"""Test the generated radio CGI against the boolean spelling used by QCSAPI."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CGI = ROOT / "versions/openmitrastar-0.7-radio-control/overlay/var/www/api/radio"


def wsl_path(path: Path) -> str:
    drive = path.drive[0].lower()
    return f"/mnt/{drive}/{path.as_posix()[3:]}"


def main() -> int:
    source = CGI.read_text(encoding="utf-8")
    match = re.search(r"^qopt\(\) \{.*?\}$", source, flags=re.MULTILINE)
    assert match, "qopt function not found in generated radio CGI"
    with tempfile.TemporaryDirectory(prefix="openmitrastar-qopt-test-") as tmp:
        script = Path(tmp) / "qopt.sh"
        script.write_text(
            "#!/bin/sh\nqcs() { echo \"$QOPT_RAW\"; }\n"
            + match.group(0)
            + "\nqopt test\n",
            encoding="utf-8",
            newline="\n",
        )
        for raw, expected in (("TRUE", "1"), ("FALSE", "0"), ("Enabled (1)", "1"), ("Disabled (0)", "0"), ("garbage", "unknown")):
            result = subprocess.run(
                ["wsl.exe", "--exec", "env", f"QOPT_RAW={raw}", "sh", wsl_path(script)],
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=os.environ.copy(),
                check=True,
            )
            assert result.stdout.strip() == expected, (raw, result.stdout, expected)
    print("radio option normalization tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
