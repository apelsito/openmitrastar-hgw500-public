#!/usr/bin/env python3
"""Build the offline UART-only Linux7.3 BASIC candidate in a fresh directory.
Run within Linux/WSL. No download, router access, UART, reboot or firmware write.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parent
ARCHIVE_SHA="87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953"
PATCH_SHA="d36ed090cdcb9470eb301933c066b2c7cde12de3af5c1cf3d02d9a7509088192"
GCC_SHA="3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263"
def sha(path):
    with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()
def run(command,log,env=None):
    with log.open("xb") as f:
        subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--toolchain",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--plan-only",action="store_true")
    a=p.parse_args()
    assert sha(a.archive)==ARCHIVE_SHA,"Upstream archive changed"
    assert sha(ROOT/"basic73.patch")==PATCH_SHA,"Patch changed"
    tc=str(a.toolchain.resolve()/"bin/arc-snps-linux-uclibc-")
    assert sha(Path(tc+"gcc"))==GCC_SHA,"Compiler changed"
    assert not a.output.exists(),"Select a new output directory"
    summary={"schema":"openmitrastar.basic73-build-recipe/v1","hardware_accessed":False,
        "source_archive_sha256":ARCHIVE_SHA,"patch_sha256":PATCH_SHA,"compiler_sha256":GCC_SHA,
        "output":str(a.output.resolve()),"lanes":["a","b"],"mode":"PLAN_ONLY" if a.plan_only else "BUILD",
        "physical_boot":"UNRUN"}
    if a.plan_only:
        print(json.dumps(summary,indent=2));return
    a.output.mkdir(parents=True,exist_ok=False)
    source_root=a.output/"source";source_root.mkdir()
    with tarfile.open(a.archive) as tar:tar.extractall(source_root,filter="data")
    source=source_root/"linux-7.3"
    run(["patch","--batch","--fuzz=0","-p1","-d",str(source),"-i",str(ROOT/"basic73.patch")],a.output/"patch.log")
    ir=a.output/"initramfs";ir.mkdir()
    init=ir/"init"
    # ELF STT_FILE retains the source basename from the accepted PID1 build.
    init_source=ir/"basic73_init_nolibc_time64_nonce.c"
    init_source.write_bytes((ROOT/"init.c").read_bytes())
    run([tc+"gcc","-mcpu=arc700","-mno-lock","-mno-atomic","-mno-swape","-static","-nostdlib",
         "-nostartfiles","-ffreestanding","-fno-builtin","-fno-stack-protector","-fno-pic","-Os",
         "-Wall","-Wextra","-Wl,-e,_start","-Wl,--build-id=none","-o",str(init),str(init_source)],
        a.output/"init-build.log")
    assert sha(init)=="9380f5c7b85231ae9320fc70b7b6a922316978c61f69d473907271168ca36194","PID1 changed"
    irlist=ir/"initramfs.list"
    irlist.write_text("dir /dev 755 0 0\ndir /proc 755 0 0\ndir /sys 755 0 0\n"
                     "nod /dev/console 600 0 0 c 5 1\nnod /dev/ttyS0 600 0 0 c 4 64\n"
                     "file /init "+str(init)+" 755 0 0\n")
    env=os.environ.copy()
    env.update(SOURCE_DATE_EPOCH="1792365298",KBUILD_BUILD_TIMESTAMP="@1792365298",
        KBUILD_BUILD_USER="openmitrastar",KBUILD_BUILD_HOST="basic73",KBUILD_BUILD_VERSION="1")
    lanes=[]
    for lane in ["a","b"]:
        out=a.output/lane;out.mkdir()
        (out/".config").write_text((ROOT/"basic73.config.template").read_text().replace("@INITRAMFS_LIST@",str(irlist)))
        make=["make","-C",str(source),"O="+str(out),"ARCH=arc","CROSS_COMPILE="+tc]
        run(make+["olddefconfig"],a.output/("config-"+lane+".log"),env)
        run(make+["KCFLAGS=-ffile-prefix-map="+str(out)+"=/basic73-build","-j6","vmlinux","dtbs"],
            a.output/("build-"+lane+".log"),env)
        asm=subprocess.check_output([tc+"objdump","-d",str(out/"vmlinux")],text=True)
        bad=[l for l in asm.splitlines() if re.search(r"\t(?:swape|llock|scond)(?:\t| )",l)]
        assert not bad,bad[:5]
        assert not subprocess.check_output([tc+"nm","-u",str(out/"vmlinux")],text=True).strip()
        lanes.append({"lane":lane,"vmlinux_sha256":sha(out/"vmlinux"),"config_sha256":sha(out/".config"),
            "dtb_sha256":sha(out/"arch/arc/boot/dts/topaz_mitrastar_basic73.dtb"),"forbidden_instructions":len(bad)})
    summary.update(status="PASS_PAIRED_BUILD_BOOT_UNRUN",lanes=lanes,
        paired_identical=all(lanes[0][k]==lanes[1][k] for k in ["vmlinux_sha256","config_sha256","dtb_sha256"]))
    assert summary["paired_identical"],"Builds differ"
    (a.output/"result.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()

