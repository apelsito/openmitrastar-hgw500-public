#!/usr/bin/env python3
"""Compose and compile Topaz PCIe plus ported RTL8192EE against Linux7.3.
Local source and fresh outputs only; no hardware or downloads.
"""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,path,env):
 print('RUN '+path.name,flush=True)
 with path.open('xb') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1792365298',KBUILD_BUILD_TIMESTAMP='@1792365298',KBUILD_BUILD_USER='openmitrastar',KBUILD_BUILD_HOST='radio73',KBUILD_BUILD_VERSION='1')
 source=a.output/'source';run(['cp','-a','--reflink=auto',str(a.source),str(source)],a.output/'copy-source.log',env)
 manifest=json.loads((a.candidate/'RESOLUTION.json').read_text())
 for row in manifest['files']:
  f=a.candidate/row['path'];assert sha(f)==row['sha256'];target=source/Path(row['path']).relative_to('overlay');shutil.copyfile(f,target)
 # Host driver inherits Bootbase link/config; no reset or iATU rewrites.
 host=(ROOT/'work/kernel-port/linux-5.10/drivers/pci/controller/pcie-qtn-topaz.c').read_text()
 host=host.replace('#include <linux/bitfield.h>','#include <linux/bitfield.h>\n#include <linux/irq.h>\n#include <linux/irqdomain.h>\n#include <linux/sizes.h>')
 host=host.replace('int irq;\n\tint ret;','int irq;\n\tint ret;\n\tstruct irq_data *irqdata;')
 fragment='\tbridge = devm_pci_alloc_host_bridge(dev, sizeof(*pcie));'
 assert host.count(fragment)==1
 host=host.replace(fragment,'''\tirqdata = irq_get_irq_data(irq);
\tif (!irqdata || irqdata->hwirq != 28 || !irqdata->domain ||
\t    !of_device_is_compatible(irq_domain_get_of_node(irqdata->domain),
\t                             "snps,arc700-intc"))
\t\treturn -EINVAL;

'''+fragment)
 host=host.replace('if (resource_size(cfg_res) < SZ_64K ||\n\t    resource_size(sysctl_res) < TOPAZ_SYSCTL_PCIE_STAT + sizeof(u32))','if (cfg_res->start != 0xcf000000 || resource_size(cfg_res) != SZ_64K ||\n\t    sysctl_res->start != 0xe0000000 || resource_size(sysctl_res) != 0x200)')
 (source/'drivers/pci/controller/pcie-qtn-topaz.c').write_text(host)
 kconfig=source/'arch/arc/plat-topaz-basic/Kconfig'
 with kconfig.open('a') as f:f.write('\nconfig PCIE_QTN_TOPAZ\n    bool "HGW500 Topaz PCIe host"\n    depends on ARC_PLAT_TOPAZ_BASIC && PCI && OF\n\nconfig QTN_TOPAZ_RADIO73\n    bool "HGW500 PCIe and RTL8192EE port"\n    depends on ARC_PLAT_TOPAZ_BASIC\n    select HAVE_PCI\n')
 make=source/'drivers/pci/controller/Makefile'
 with make.open('a') as f:f.write('\nobj-$(CONFIG_PCIE_QTN_TOPAZ) += pcie-qtn-topaz.o\n')
 gate=source/'arch/arc/kernel/intc-compact.c';text=gate.read_text()
 text=text.replace('static void __iomem *topaz_basic_sysctl;','static void __iomem *topaz_basic_sysctl;\nstatic void __iomem *topaz_radio73_intx_mask;')
 text=text.replace('if (!topaz_basic_sysctl || (hwirq != TOPAZ_BASIC_UART_PARENT &&\n        (!IS_ENABLED(CONFIG_QTN_TOPAZ_ETH73) || (hwirq != 19 && hwirq != 20))))','if (!topaz_basic_sysctl || (hwirq != TOPAZ_BASIC_UART_PARENT &&\n        !(IS_ENABLED(CONFIG_QTN_TOPAZ_ETH73) && (hwirq == 19 || hwirq == 20)) &&\n        !(IS_ENABLED(CONFIG_PCIE_QTN_TOPAZ) && hwirq == 28)))')
 anchor='    raw_spin_lock_irqsave(&topaz_basic_gate_lock, flags);'
 assert text.count(anchor)==1
 text=text.replace(anchor,anchor+'''
    if (hwirq == 28 && topaz_radio73_intx_mask) {
        value = readl(topaz_radio73_intx_mask);
        if (enable)
            value |= BIT(11);
        else
            value &= ~BIT(11);
        writel(value, topaz_radio73_intx_mask);
        readl(topaz_radio73_intx_mask);
    }''')
 anchor='        panic("Topaz BASIC UART gate mapping failed\\n");'
 assert text.count(anchor)==1
 text=text.replace(anchor,anchor+'''
    /* Separate map: retain the validated 0x5c UART controller aperture. */
    if (IS_ENABLED(CONFIG_PCIE_QTN_TOPAZ)) {
        topaz_radio73_intx_mask = ioremap(0xe00000c0, 4);
        if (!topaz_radio73_intx_mask)
            panic("Topaz PCIe INTx gate mapping failed\\n");
    }''')
 gate.write_text(text)
 dt=source/'arch/arc/boot/dts/topaz_mitrastar_eth73.dts'
 dttext=dt.read_text();anchor='\n\t\tuart0: serial@f0000000 {';assert dttext.count(anchor)==1
 dttext=dttext.replace(anchor,'''
\t\tpcie@cf000000 {
\t\t\tcompatible = "qtn,topaz-pcie-host";
\t\t\tdevice_type = "pci";
\t\t\t#address-cells = <3>;
\t\t\t#size-cells = <2>;
\t\t\t#interrupt-cells = <1>;
\t\t\treg = <0xcf000000 0x10000>, <0xe0000000 0x200>;
\t\t\treg-names = "config", "sysctl";
\t\t\tbus-range = <0 0>;
\t\t\tranges = <0x02000000 0 0xc0000000 0xc0000000 0 0x02000000>;
\t\t\tinterrupt-parent = <&core_intc>;
\t\t\tinterrupts = <28>;
\t\t\tstatus = "okay";
\t\t};
'''+anchor)
 dt.write_text(dttext)
 ir=a.output/'initramfs';ir.mkdir();shutil.copyfile(a.base/'initramfs/init',ir/'init')
 listing=ir/'list';listing.write_text('dir /dev 755 0 0\ndir /proc 755 0 0\ndir /sys 755 0 0\nnod /dev/console 600 0 0 c 5 1\nfile /init '+str(ir/'init')+' 755 0 0\n')
 config=(a.base/'a/.config').read_text()
 settings={'LOCALVERSION':'"-openmitrastar-radio73-v1"','INITRAMFS_SOURCE':'"'+str(listing)+'"','PCI':'y','QTN_TOPAZ_RADIO73':'y','PCIE_QTN_TOPAZ':'y','GENERIC_PCI_IOMAP':'y','PCI_QUIRKS':'y','CFG80211':'m','MAC80211':'m','WLAN':'y','WLAN_VENDOR_REALTEK':'y','RTL_CARDS':'m','RTL8192EE':'m','RTLWIFI':'m','RTLWIFI_PCI':'m','RTLBTCOEXIST':'m','CRYPTO':'y','RFKILL':'y','PACKET':'y','UNIX':'y','VGA_ARB':'n','PCI_MSI':'n','CFG80211_REQUIRE_SIGNED_REGDB':'n','CFG80211_USE_KERNEL_REGDB_KEYS':'n'}
 for key,val in settings.items():
  config=re.sub(r'(?m)^(?:CONFIG_'+key+r'=.*|# CONFIG_'+key+r' is not set)\n','',config)
  config+=('# CONFIG_'+key+' is not set\n') if val=='n' else 'CONFIG_'+key+'='+val+'\n'
 changed=['drivers/pci/controller/pcie-qtn-topaz.c','drivers/pci/controller/Makefile','arch/arc/plat-topaz-basic/Kconfig','arch/arc/kernel/intc-compact.c','arch/arc/boot/dts/topaz_mitrastar_eth73.dts']
 (a.output/'COMPOSED_SOURCE.json').write_text(json.dumps({'hardware_accessed':False,'changes':[{'path':x,'sha256':sha(source/x)} for x in changed],'realtek_resolution_sha256':sha(a.candidate/'RESOLUTION.json')},indent=2)+'\n')
 lanes=[]
 for lane in ['a','b']:
  out=a.output/lane;out.mkdir();(out/'.config').write_text(config)
  cmd=['make','-C',str(source),'O='+str(out),'ARCH=arc','CROSS_COMPILE='+tc]
  run(cmd+['olddefconfig'],a.output/('config-'+lane+'.log'),env)
  conf=(out/'.config').read_text()
  for key in ['PCI','QTN_TOPAZ_RADIO73','PCIE_QTN_TOPAZ','ARC_CPU_750D','ARC_PAGE_SIZE_8K','PREEMPT_NONE']:
   assert 'CONFIG_'+key+'=y' in conf,key
  for key in ['RTL8192EE','RTLWIFI','RTLWIFI_PCI','RTLBTCOEXIST','CFG80211','MAC80211']:
   assert 'CONFIG_'+key+'=m' in conf,key
  run(cmd+['KCFLAGS=-ffile-prefix-map='+str(out)+'=/radio73-build','-j6','vmlinux','dtbs','modules'],a.output/('build-'+lane+'.log'),env)
  files=[out/'vmlinux']+sorted(out.rglob('*.ko'))
  records=[]
  for f in files:
   asm=subprocess.check_output([tc+'objdump','-d',str(f)],text=True)
   assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),f
   records.append({'path':f.relative_to(out).as_posix(),'sha256':sha(f),'bytes':f.stat().st_size})
  assert not subprocess.check_output([tc+'nm','-u',str(out/'vmlinux')],text=True).strip()
  lanes.append({'lane':lane,'config_sha256':sha(out/'.config'),'files':records})
 assert lanes[0]['files']==lanes[1]['files'] and lanes[0]['config_sha256']==lanes[1]['config_sha256']
 report={'schema':'openmitrastar.radio2g73-paired-build/v1','status':'PASS_PAIRED_BUILD_RADIO_PHYSICAL_UNRUN','hardware_accessed':False,'lanes':lanes,'realtek_resolution_sha256':sha(a.candidate/'RESOLUTION.json'),'radio_association':'UNRUN','pcie_physical':'UNRUN','persistent':'UNRUN'}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
