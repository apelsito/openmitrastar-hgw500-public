#!/usr/bin/env python3
"""Integration-test the generated WiFi CGI with fake OEM backends under WSL."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CGI = ROOT / "versions/openmitrastar-0.7-radio-control/overlay/var/www/api/wifi"

LIB = r'''#!/bin/sh
json_escape() { awk 'BEGIN{ORS=""}{gsub(/\\/,"\\\\");gsub(/"/,"\\\"");if(NR>1)printf " ";printf "%s",$0}'; }
header_json() { echo "Content-Type: application/json"; echo; }
url_decode() { sed 's/+/ /g;s/%20/ /g;s/%2F/\//Ig;s/%3A/:/Ig;s/%2E/./Ig;s/%2D/-/Ig;s/%5F/_/Ig;s/%40/@/Ig;s/%23/#/Ig;s/%25/%/Ig;s/%2B/+/Ig'; }
read_body() { BODY="$(dd bs=1 count="$CONTENT_LENGTH" 2>/dev/null)"; }
safe_text() { echo "$1" | grep -Eq '^[A-Za-z0-9 ._:@#%+=,/-]{1,96}$'; }
qcs() { [ "$1" = get_channel ] && echo 100; }
'''

STUB = r'''#!/bin/sh
echo "$(basename "$0") $*" >> "$TEST_CALLS"
if [ "$(basename "$0")" = call_qcsapi ] && [ "$TEST_QCS_FAIL" = 1 ]; then
  echo "QCS API error 1001: injected"
  exit 1
fi
if [ "$(basename "$0")" = qweaction ] && [ "$TEST_COMMIT_FAIL" = 1 ]; then
  echo "injected commit failure"
  exit 1
fi
exit 0
'''


def wsl_path(path: Path) -> str:
    drive = path.drive[0].lower()
    return f"/mnt/{drive}/{path.as_posix()[3:]}"


def run_case(root: Path, body: str, **env_overrides: str) -> tuple[dict, list[str]]:
    calls = root / "calls.log"
    calls.write_text("", encoding="utf-8")
    variables = {
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body.encode("utf-8"))),
        "TEST_CALLS": wsl_path(calls),
        "PATH": f"{wsl_path(root / 'bin')}:/usr/bin:/bin",
        **env_overrides,
    }
    command = ["wsl.exe", "--exec", "env"]
    command.extend(f"{key}={value}" for key, value in variables.items())
    command.extend(["sh", wsl_path(root / "wifi")])
    result = subprocess.run(
        command,
        input=body,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=os.environ.copy(),
        check=True,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    return payload, calls.read_text(encoding="utf-8").splitlines()


def main() -> int:
    source_cgi = CGI.read_text(encoding="utf-8")
    assert " tr " not in source_cgi and "| tr" not in source_cgi, (
        "OEM rootfs does not ship tr; POST parsing must use an available tool"
    )
    with tempfile.TemporaryDirectory(prefix="openmitrastar-wifi-test-") as tmp:
        root = Path(tmp)
        (root / "bin").mkdir()
        script = source_cgi.replace(
            ". /var/www/api/_lib", f'. "{wsl_path(root / "_lib")}"', 1
        )
        (root / "wifi").write_text(script, encoding="utf-8", newline="\n")
        (root / "_lib").write_text(LIB, encoding="utf-8", newline="\n")
        for name in ("qweconfig", "qweaction", "call_qcsapi"):
            (root / "bin" / name).write_text(STUB, encoding="utf-8", newline="\n")

        payload, calls = run_case(root, "unsupported.key=1")
        assert payload["ok"] is False and calls == [], (payload, calls)

        payload, calls = run_case(root, "ssid.wlan1=TestNet&channel.wlan1=6")
        assert payload["ok"] is True, payload
        assert sum(line.startswith("qweconfig ") for line in calls) == 2, calls
        assert calls.count("qweaction wlan1 commit") == 1, calls

        payload, calls = run_case(root, "vht.wifi0=1")
        assert payload["ok"] is True, payload
        assert any("set_vht wifi0 1" in line for line in calls), calls
        assert not any(line.startswith("qweaction ") for line in calls), calls

        payload, calls = run_case(root, "vht.wifi0=1", TEST_QCS_FAIL="1")
        assert payload["ok"] is False, payload

        payload, calls = run_case(root, "channel.wlan1=6", TEST_COMMIT_FAIL="1")
        assert payload["ok"] is False, payload

        payload, calls = run_case(
            root,
            "band.wlan1=11&bcnint.wlan1=100&dtimperiod.wlan1=3&fragthres.wlan1=2346",
        )
        assert payload["ok"] is True, payload
        assert calls.count("qweaction wlan1 commit") == 1, calls
        assert sum(line.startswith("qweconfig ") for line in calls) == 4, calls

        payload, calls = run_case(root, "bcnint.wlan1=19")
        assert payload["ok"] is False and calls == [], (payload, calls)

        payload, calls = run_case(root, "beamforming.wifi0=1")
        assert payload["ok"] is True, payload
        assert any("set_option wifi0 beamforming 1" in line for line in calls), calls

    print("wifi CGI validation/apply integration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
