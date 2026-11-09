#!/usr/bin/env python3
"""Measure the controller HTTP path from AELITA without changing Wi-Fi."""
from __future__ import annotations

import json
import sys


sys.path.insert(0, "tools")
import run_qtn_5g_aelita_one_shot as aelita  # noqa: E402


def main() -> int:
    server = aelita.start_server("192.168.1.43", 8081, 4)
    try:
        command = r'''$ErrorActionPreference='Stop'
$download = (& curl.exe --silent --show-error --max-time 60 --output NUL --write-out 'http=%{http_code};bytes=%{size_download};speed_Bps=%{speed_download};seconds=%{time_total}' http://192.168.1.43:8081/speed.bin 2>&1 | Out-String).Trim()
$path = Join-Path $env:TEMP 'om-controller-baseline.bin'
$stream = [IO.File]::Open($path,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $stream.SetLength(4MB) } finally { $stream.Dispose() }
$upload = (& curl.exe --silent --show-error --request PUT --upload-file $path --max-time 60 --output NUL --write-out 'http=%{http_code};bytes=%{size_upload};speed_Bps=%{speed_upload};seconds=%{time_total}' http://192.168.1.43:8081/upload.bin 2>&1 | Out-String).Trim()
Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
[ordered]@{download=$download;upload=$upload} | ConvertTo-Json -Compress'''
        output = aelita.oracle_ps(
            aelita.ORACLE_HOST, aelita.ORACLE_USER, command, 150
        )
        result = json.loads(output.lstrip("\ufeff"))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        aelita.stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
