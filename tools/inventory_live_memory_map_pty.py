#!/usr/bin/env python3
"""Read-only inventory of the live Topaz DDR and coprocessor memory map."""
from __future__ import annotations

import os

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    user, password = credentials()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    proc = PtyProcess.spawn([
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@192.168.1.90",
    ], cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)
    probe = r'''
echo '=== MEMINFO ==='; cat /proc/meminfo
echo '=== IOMEM ==='; cat /proc/iomem 2>/dev/null
echo '=== MAP_DMESG ==='; dmesg | grep -Ei 'memory|reserved|dram|ddr|muc|dsp|auc|hbm|fwt|kernel.*base|mem=' | head -240
echo '=== QTN_PROC_FILES ==='; find /proc/qtn -maxdepth 3 -type f 2>/dev/null | sort
echo '=== QTN_SYS_MODULE_PARAMS ==='; find /sys/module -path '*qdrv*parameters*' -type f 2>/dev/null | sort
echo '=== MEMORY_KALLSYMS ==='; grep -E ' ([ABbDdRrTt]) (_text|_stext|_etext|_sdata|_edata|_end|end_mem|min_low_pfn|max_low_pfn|high_memory|mem_map|init_mm|qtn_shared_params|shared_params)$' /proc/kallsyms 2>/dev/null
echo '=== MODULES ==='; cat /proc/modules
'''.strip()
    print(command(proc, probe, "__MEMORY_MAP_INVENTORY__", 90).strip())
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
