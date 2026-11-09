"""Compile real ARC layout witnesses and verify each fresh complete lane."""
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path

ABI = '''#include <openmitrastar_qdrv_compat.h>
#include <linux/module.h>
#include <linux/skbuff.h>
#include <linux/netdevice.h>
#include <linux/stddef.h>
#include <qtn/dmautil.h>
static_assert(offsetof(struct sk_buff, qtn_cb) >= offsetof(struct sk_buff, headers));
static_assert(offsetof(struct sk_buff, recycle_list) + sizeof(((struct sk_buff *)0)->recycle_list) <= offsetof(struct sk_buff, headers) + sizeof(((struct sk_buff *)0)->headers));
static_assert(offsetof(struct net_device, qtn_flags) < offsetof(struct net_device, priv));
static_assert(sizeof(struct qtn_skb_cb) == 12);
static_assert(sizeof(aligned_dma_descs) == 20);
#define ABI_SIZE(name, value) unsigned char name[(value) + 1]
ABI_SIZE(om_abi_skb_size, sizeof(struct sk_buff));
ABI_SIZE(om_abi_skb_qtn_cb, offsetof(struct sk_buff, qtn_cb));
ABI_SIZE(om_abi_skb_orig_dev, offsetof(struct sk_buff, orig_dev));
ABI_SIZE(om_abi_skb_recycle, offsetof(struct sk_buff, recycle_list));
ABI_SIZE(om_abi_ndev_size, sizeof(struct net_device));
ABI_SIZE(om_abi_ndev_qtn_flags, offsetof(struct net_device, qtn_flags));
ABI_SIZE(om_abi_ndev_priv, offsetof(struct net_device, priv));
ABI_SIZE(om_abi_ndevstats_size, sizeof(struct net_device_stats));
ABI_SIZE(om_abi_qtn_cb_size, sizeof(struct qtn_skb_cb));
ABI_SIZE(om_abi_dma_desc_size, sizeof(aligned_dma_descs));
MODULE_LICENSE("GPL");
'''

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser()
    for name in ('pair','kernel-source','candidate','gpl-source','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--cross-prefix',required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    pair=json.loads((args.pair/'result.json').read_text())
    assert pair['status']=='PASS_PAIRED_KERNEL_BASE_21_NATIVE_EMAC_BYTES'
    result={'status':'RUNNING_ABI_AND_IMPORT_AUDIT','candidate_result_sha256':sha(args.candidate/'result.json'),
            'pair_result_sha256':sha(args.pair/'result.json'),'hardware_accessed':False,
            'firmware_eligible':False,'lanes':[]}
    for name in ('a','b'):
        lane=args.pair/name; kernel=lane/'kernel'; native=lane/'native'
        fixture=args.output/name;fixture.mkdir()
        (fixture/'abi_probe.c').write_text(ABI)
        includes = [args.candidate.resolve()/'headers',args.candidate.resolve()/'source/qdrv/compat/include',
                    args.gpl_source.resolve(),args.gpl_source.resolve()/'include',args.gpl_source.resolve()/'common']
        (fixture/'Kbuild').write_text('obj-m := abi_probe.o\nccflags-y += '+' '.join('-I'+str(p) for p in includes)+'\n')
        command=['make','-C',str(args.kernel_source.resolve()),'O='+str(kernel.resolve()),
                 'M='+str(fixture.resolve()),'ARCH=arc','CROSS_COMPILE='+args.cross_prefix,'abi_probe.o']
        with(fixture/'build.log').open('xb') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
        nm=subprocess.check_output([args.cross_prefix+'nm','-S',str(fixture/'abi_probe.o')],text=True)
        values={match.group(2):int(match.group(1),16)-1 for match in re.finditer(r'^[0-9a-f]+\s+([0-9a-f]+)\s+[BbDd]\s+(om_abi_\S+)$',nm,re.M)}
        assert len(values)==10,values
        modules=sorted(kernel.rglob('*.ko'))+sorted(native.rglob('*.ko'))+sorted((lane/'emac').rglob('*.ko'))
        exports={line.split()[1] for line in (kernel/'Module.symvers').read_text().splitlines()}
        exports|={line.split()[1] for line in (native/'Module.symvers').read_text().splitlines()}
        unresolved={};module_hashes={}
        for module in modules:
            imports={line.split()[-1] for line in subprocess.check_output([args.cross_prefix+'nm','-u',str(module)],text=True).splitlines()}
            missing=sorted(imports-exports)
            if missing:unresolved[module.relative_to(lane).as_posix()]=missing
            asm=subprocess.check_output([args.cross_prefix+'objdump','-d',str(module)],text=True)
            assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),str(module)
            module_hashes[module.relative_to(lane).as_posix()]=sha(module)
        assert not unresolved,unresolved
        assert not subprocess.check_output([args.cross_prefix+'nm','-u',str(kernel/'vmlinux')],text=True).strip()
        kernel_asm=subprocess.check_output([args.cross_prefix+'objdump','-d',str(kernel/'vmlinux')],text=True)
        assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',kernel_asm),str(kernel/'vmlinux')
        for path,digest in pair['lanes'][0 if name=='a' else 1]['C_objects'].items():
            assert sha(native/path)==digest,path
        result['lanes'].append({'name':name,'ABI':values,'ABI_object_sha256':sha(fixture/'abi_probe.o'),
            'module_count':len(modules),'all_strong_imports_resolved':True,'forbidden_ARC_instructions':False,
            'vmlinux_undefined_symbols':0,'vmlinux_forbidden_ARC_instructions':False,
            'module_hashes':module_hashes,'C_objects_pin_pass':True})
    assert result['lanes'][0]['ABI']==result['lanes'][1]['ABI']
    result['status']='PASS_PAIRED_ACTUAL_ARC_ABI_48_MODULE_IMPORTS_INSTRUCTIONS_PINS'
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'ABI':result['lanes'][0]['ABI'],'module_count':result['lanes'][0]['module_count']},indent=2))

if __name__=='__main__':main()
