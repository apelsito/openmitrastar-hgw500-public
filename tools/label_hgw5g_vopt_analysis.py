"""Label two exact stripped OEM VOPT entries in an analysis-only derivative.

Entry offsets follow original ARC objdump and its direct-call constants. No
allocated bytes or original source are changed; labels are analyst metadata.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from label_oem_qdrv_analysis_callbacks import allocated


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--objcopy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--assembly', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    digest = sha(args.input)
    assert digest == '79fbcbd4634a9fc32fdf8ac0c997f3bd0329131162a1ea4948794e4986c7e40a'
    assembly = args.assembly.read_text()
    assert '71164:\tc0f1' in assembly and '76b68:\tc0f1' in assembly
    assert 'mov\tgp,0x71164' in assembly
    assert 'add\tr3,r0,0x4df5' in assembly
    args.output.mkdir(parents=True)
    target = args.output / 'wlan-VOPT-EXPLICIT-ENTRIES-ANALYSIS_ONLY.elf'
    labels = {'om_oem_vopt_effective_apply': 0x61164,
              'om_oem_vopt_peer_policy': 0x66b68}
    command = [str(args.objcopy)]
    for name, offset in labels.items():
        command += ['--add-symbol', f'{name}=.text:{offset:#x},global,function']
    command += [str(args.input), str(target)]
    result = subprocess.run(command, capture_output=True, check=True)
    assert allocated(args.input) == allocated(target)
    assert sha(args.input) == digest
    receipt = {'classification': 'ANALYSIS_ONLY_NEVER_LOAD_OR_FLASH',
               'hardware_accessed': False, 'original_unchanged': True,
               'allocated_sections_byte_identical': True,
               'source_sha256': digest, 'derived_sha256': sha(target),
               'derived': str(target), 'labels_text_offsets': labels,
               'assembly_sha256': sha(args.assembly), 'objcopy_sha256': sha(args.objcopy),
               'command': command,
               'limits': 'Analyst names from exact ARC entries/calls; not recovered original names or runtime proof.'}
    (args.output / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
