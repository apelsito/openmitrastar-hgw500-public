"""Run actual MAC init against independent OEM values and two fake MMIO banks."""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    driver = a.candidate / 'driver/qtn-topaz-emac-eth73.c'
    header = a.candidate / 'driver/topaz-ethernet.h'
    oem = ROOT / 'work/sources/Quantenna-GPL/drivers/ruby/emac_lib.c'
    oem_header = ROOT / 'work/sources/Quantenna-GPL/common/ruby_arasan_emac_ahb.h'
    spec = importlib.util.spec_from_file_location('extract', ROOT / 'work/kernel-port/linux-7.3-ethernet-v1/test_lifecycle.py')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    helper = base.extract(driver.read_text(), 'qtn_emac_oem_mac_limits')
    names = re.findall(r'qtn_emac_write\(emac, (QTN_EMAC_MAC_\w+),', helper)
    assert len(names) == len(set(names)) == 12
    body = oem.read_text().split('void emac_lib_init_mac(')[1].split('EXPORT_SYMBOL(emac_lib_init_mac)')[0]
    offsets = dict(re.findall(r'#define\s+(EMAC_MAC_\w+)\s+(0x[0-9a-fA-F]+)', oem_header.read_text()))
    definitions = dict(re.findall(r'#define\s+(QTN_EMAC_MAC_\w+)\s+(0x[0-9a-fA-F]+)', header.read_text()))
    constants = dict(re.findall(r'emac_wr\(privc, (EMAC_MAC_\w+),\s*(0x[0-9a-fA-F]+|[0-9]+)\);', body))
    expected = []
    for name in names:
        original = name.removeprefix('QTN_')
        assert int(offsets[original], 16) == int(definitions[name], 16)
        offset = int(offsets[original], 16)
        if original in constants:
            value = str(int(constants[original], 0))
        else:
            m = re.search(r'emac_wr\(privc, ' + original + r', \*\(u16 \*\)&dev->dev_addr\[([024])\]\);', body)
            assert m, original
            index = int(m[1])
            value = f'(uint32_t)n.dev_addr[{index}] | ((uint32_t)n.dev_addr[{index+1}] << 8)'
        expected.append(f'expected[{offset // 4}] = {value};')
    definitions_c = '\n'.join(f'#define {name} {definitions[name]}' for name in names)
    fixture = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
struct net_device { u8 dev_addr[6]; };
struct qtn_topaz_emac { struct net_device *ndev; u32 *regs; };
static unsigned checks, writes;
#define CHECK(c) do { checks++; if (!(c)) { fprintf(stderr,"FAIL line %u\n",__LINE__); exit(1); } } while (0)
static u32 get_unaligned_le16(const void *pointer) {
 const u8 *p=pointer; return (u32)p[0] | ((u32)p[1]<<8);
}
static void qtn_emac_write(struct qtn_topaz_emac *e, u32 reg, u32 value) {
 CHECK(reg < 0x400 && (reg & 3)==0); e->regs[reg/4]=value; writes++;
}
'''
    fixture += definitions_c + '\n' + helper + '\n'
    fixture += r'''
int main(void) {
 u32 banks[2][256], before[2][256], expected[256];
 struct net_device n; struct qtn_topaz_emac e={.ndev=&n};
 for (unsigned trial=0; trial<128; trial++) {
  for (unsigned active=0; active<2; active++) {
   for (unsigned b=0; b<2; b++) for(unsigned i=0;i<256;i++)
    banks[b][i]=0xa53c0000U ^ (trial<<12) ^ (b<<8) ^ i;
   memcpy(before,banks,sizeof(banks)); memcpy(expected,banks[active],sizeof(expected));
   for (unsigned i=0;i<6;i++) n.dev_addr[i]=(u8)(trial*13+i*37+active);
   e.regs=banks[active]; writes=0;
'''
    fixture += '\n'.join(expected)
    fixture += r'''
   qtn_emac_oem_mac_limits(&e); CHECK(writes==12);
   for(unsigned i=0;i<256;i++) {
    CHECK(banks[active][i]==expected[i]); CHECK(banks[1-active][i]==before[1-active][i]);
   }
  }
 }
 printf("MAC_INIT_PASS cases=256 checks=%u\n",checks); return 0;
}
'''
    outcomes = []
    mutations = [('original', fixture),
                 ('threshold_wrong', fixture.replace('QTN_EMAC_MAC_TX_START_THRESHOLD, 1518', 'QTN_EMAC_MAC_TX_START_THRESHOLD, 1517')),
                 ('pause_identity_wrong', fixture.replace('get_unaligned_le16(address + 4)', 'get_unaligned_le16(address + 2)')),
                 ('jabber_write_missing', fixture.replace('qtn_emac_write(emac, QTN_EMAC_MAC_TX_JABBER_SIZE, 0xca0);', '/* intentionally missing for negative control */'))]
    for name, source in mutations:
        path = a.output / (name + '.c')
        path.write_text(source, newline='\n')
        executable = a.output / name
        c = subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined', str(path), '-o', str(executable)], capture_output=True)
        assert c.returncode == 0, c.stderr.decode()
        r = subprocess.run([str(executable)], capture_output=True)
        assert (r.returncode == 0) == (name == 'original'), name
        outcomes.append({'case': name, 'exit_code': r.returncode, 'stdout': r.stdout.decode(), 'stderr': r.stderr.decode(), 'source_sha256': sha(path)})
    result = {'schema': 'openmitrastar.eth73-oem-mac-fixture/v3', 'status': 'PASS_OEM_REGISTER_CONTRACT_AND_THREE_NEGATIVE_CONTROLS',
              'hardware_accessed': False, 'physical': 'UNRUN', 'driver_sha256': sha(driver),
              'oem_sha256': sha(oem), 'oem_header_sha256': sha(oem_header), 'cases': outcomes,
              'limits': ['Fake MMIO verifies local writes and OEM values; does not establish physical TX recovery.']}
    (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
