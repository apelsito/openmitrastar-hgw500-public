"""Create a read-only direct-boot contract from exact F321 local artifacts."""
from pathlib import Path
import argparse
import hashlib
import json
import lzma
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
F321 = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound'
PREFIX = 'openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
BACKUP = ROOT/'outputs/flash-backups/f159-physical-new-dump-20260831T2359/current-unit/hgw500_mtdblock0.bin'
RESTORE = ROOT/'outputs/recovery/f334-after-reset-20260921T120202Z-fd02977b/restore'
BOOTARGS = 'earlycon=uart8250,mmio32,0xf0000000 console=ttyS0,115200n8 root=31:3 rootfstype=squashfs ro rootwait init=/sbin/init panic=10'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    out = ap.parse_args().output
    out.mkdir(parents=True, exist_ok=False)
    image_path = F321/(PREFIX+'.webformat.bin')
    image = image_path.read_bytes()
    header = struct.unpack_from('>7I4B32s', image)
    decoded = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(image[0x2000:])
    bootbase = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(BACKUP.read_bytes()[0xf34:])
    contract_path = F321/'bootbase-contract.json'
    contract = json.loads(contract_path.read_text())
    verified_path = RESTORE/'verified-writer.json'
    verified = json.loads(verified_path.read_text(encoding='utf-8-sig'))
    dtb_path = F321/(PREFIX+'.dtb')
    dtb_linux = '/mnt/c'+dtb_path.as_posix()[2:]
    actual_args = subprocess.check_output(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','fdtget',dtb_linux,'/chosen','bootargs'],text=True).strip()
    history = (RESTORE/'writer/bootbase-flash-uart.log').read_text(errors='replace')
    checks = {
        'image_exact_sha256': digest(image) == 'eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18',
        'image_exact_size': len(image) == 0x517000,
        'image_crc32': zlib.crc32(image) == 0xbd1135df,
        'erased_tail_reference_crc32': zlib.crc32(image+b'\xff'*(0x7a0000-len(image))) == 0x6ed8e483,
        'uimage_at_offset_zero': image[:4] == bytes.fromhex('27051956'),
        'ras_payload_at_0x2000': zlib.crc32(image[0x2000:0x2000+header[3]]) == header[6],
        'lzma_matches_exact_kernel': decoded == (F321/(PREFIX+'.kernel.raw.bin')).read_bytes(),
        'kernel_load_entry': header[4:6] == (0x8493a000,0x8493e000),
        'decoded_kernel_size_and_hash': len(decoded) == 3724768 and digest(decoded) == '9782548e817d15975746b17a90e68c282001376182a75f58235f63888f8f60ae',
        'source_ram_disjoint_from_output': 0x83000000+0x7a0000 <= header[4],
        'crc_scratch_disjoint': 0x837a0000 <= 0x84000000 and 0x84000004 < header[4],
        'bootbase_code_exact': bootbase == (ROOT/'work/bootbase-decoded.bin').read_bytes(),
        'bootbase_contract_pass': contract['result'] == 'PASS' and contract['candidate']['accepted_by_contract'],
        'dtb_bootargs_exact': actual_args == BOOTARGS,
        'last_restore_full_slot_readback': verified.get('full_slot_crc32_observed') == '6ed8e483',
        'direct_read_boot_already_used_inside_bootselect': 'do_bootselect: spi_flash read 0x007e0000 0x83000000 0x007a0000' in history and 'do_bootselect: bootm 0x83000000' in history,
    }
    ranges = {'read_handler':(0x88022c7c,0x88022cdc),'read_op_check':(0x88022650,0x880226cc),
              'software_lock_fill':(0x88022548,0x880225b4),'command_dispatch':(0x88022fdc,0x88023734),
              'linux_handoff':(0x8802cbc4,0x8802cd18)}
    lines = (ROOT/'work/bootbase-decoded.disasm.txt').read_text().splitlines()
    for name,(start,end) in ranges.items():
        selected=[]
        for line in lines:
            try: address=int(line[:8],16)
            except ValueError: continue
            if start<=address<end:selected.append(line)
        (out/(name+'.disasm.txt')).write_text('\n'.join(selected)+'\n')
    result = {
        'schema':'openmitrastar.f337-direct-f321-return/v1',
        'status':'PASS_OFFLINE_DIRECT_RETURN_CONTRACT' if all(checks.values()) else 'FAIL_OFFLINE_CONTRACT',
        'hardware_actions':[], 'checks':checks,
        'image':{'path':str(image_path),'bytes':len(image),'sha256':digest(image),'crc32':'bd1135df','uimage_offset':0,'payload_offset':0x2000},
        'spi_slot':{'offset':0x7e0000,'bytes':0x7a0000,'historical_full_slot_crc32':'6ed8e483',
                    'full_slot_crc_fresh_now':False,'mutable_store_starts_at_slot_offset':0x5e0000},
        'ram':{'source_start':0x83000000,'source_end_exclusive':0x837a0000,'crc_scratch':0x84000000,
               'kernel_load':header[4],'kernel_decompressed_end_exclusive':header[4]+len(decoded),
               'entry':header[5],'kernel_bss_end_exclusive':0x84d00000},
        'dtb_bootargs':actual_args,
        'review_only_commands_individually_gated':[
            'spi_flash read 0x007e0000 0x83000000 0x007a0000',
            'crc32 0x83000000 0x00517000 0x84000000',
            'md.l 0x84000000 1',
            'crc32 0x83000000 0x007a0000 0x84000000',
            'md.l 0x84000000 1',
            'iminfo 0x83000000',
            'setenv bootargs '+BOOTARGS,
            'printenv bootargs',
            'bootm 0x83000000'],
        'full_slot_gate':'Bind the full-slot CRC to a fresh snapshot. 6ed8e483 is historical physical readback and FF-tail reference, not a current-state assertion. Do not silently accept a changed full-slot CRC.',
        'flash_safety':'The read branch checks bounds/readiness, copies flash bytes to RAM and deasserts CS. Common lock preparation only fills a heap bitmap. No sf probe, write-enable, erase, write, hardware unlock, run, saveenv, bootselect or qtnboot is requested.',
        'bootm_return_policy':'STOP at prompt, preserve evidence, no automatic alternate slot or environment persistence; host state machine must not invoke bootcmd.',
        'acceptance':'Exact F321 SSH/release identity and platform gates after boot; command dispatch alone is not return PASS.',
        'sources':{str(p):{'bytes':p.stat().st_size,'sha256':digest(p.read_bytes())} for p in [image_path,contract_path,dtb_path,verified_path,BACKUP,Path(__file__)]},
    }
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'pass':sum(checks.values()),'total':len(checks),'output':str(out),'result_sha256':digest((out/'result.json').read_bytes())}))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
