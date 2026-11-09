"""Local EMAC reset fallback after a proven stop timeout, with failure quarantine.
Derived from OEM reset_dma write/release order; no runtime access.
"""
from pathlib import Path
import argparse,hashlib,json,shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 baseline=ROOT/'work/kernel-port/linux-7.3-ethernet-v1/candidate'
 shutil.copytree(baseline,a.output)
 driver=a.output/'driver/qtn-topaz-emac-eth73.c';text=driver.read_text()
 assert sha(driver)=='cf9441d47c168a050d6df9fefb834bfd5697e7340a33739d33b56b1ccbe9220a'
 text=text.replace('\tbool dma_unsafe;','\tbool dma_unsafe;\n\tu32 stop_reset_attempts;\n\tu32 stop_reset_successes;')
 text=text.replace('"schema=1\\n"','"schema=2\\n"\n\t\t"dma_unsafe=%u\\nstop_reset_attempts=%u\\nstop_reset_successes=%u\\n"')
 text=text.replace('\t\temac->irq, READ_ONCE(emac->irq20_count),','\t\tREAD_ONCE(emac->dma_unsafe), READ_ONCE(emac->stop_reset_attempts),\n\t\tREAD_ONCE(emac->stop_reset_successes),\n\t\temac->irq, READ_ONCE(emac->irq20_count),')
 start=text.index('static int qtn_emac_quiesce(');end=text.index('\nstatic void qtn_emac_program_address',start)
 before=text[start:end]
 replacement=before.replace('\tu32 value;','\tu32 value;\n\tu32 config;\n\tint ret;')
 replacement=replacement.replace('\treturn readl_poll_timeout(', '\tret = readl_poll_timeout(')
 anchor='\t\t\t\t  10, QTN_TOPAZ_EMAC_QUIESCE_US);\n}'
 assert replacement.count(anchor)==1
 replacement=replacement.replace(anchor,'''\t\t\t\t  10, QTN_TOPAZ_EMAC_QUIESCE_US);
\tif (!ret)
\t\treturn 0;

\t/* OEM arasan_emac_ahb.c stop_traffic/reset_dma forces a LOCAL reset
\t * if DMA state never reaches stopped. Disable native parsers first.
\t * No SYSCTL/PHY/TQE reset, no access to the other EMAC's register bank.
\t * The OEM erratum forbids MMIO reads between reset and release writes.
\t */
\tconfig = qtn_emac_read(emac, QTN_EMAC_DMA_CONFIG);
\tqtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL, 0);
\tqtn_emac_write(emac, QTN_TOPAZ_EMAC_TXP_CTRL, 0);
\temac->stop_reset_attempts++;
\tqtn_emac_write(emac, QTN_EMAC_DMA_CONFIG,
\t\t       QTN_EMAC_DMA_CONFIG_SOFT_RESET);
\tqtn_emac_write(emac, QTN_EMAC_DMA_CONFIG,
\t\t       config & ~QTN_EMAC_DMA_CONFIG_SOFT_RESET);
\tudelay(1000);
\tqtn_emac_write(emac, QTN_EMAC_DMA_CTRL, 0);
\tqtn_emac_disable_irqs(emac);
\t/* A reset write alone never permits DMA memory to be released. */
\tret = readl_poll_timeout(emac->regs + QTN_EMAC_DMA_STATUS_IRQ, value,
\t\t\t\t !(value & (QTN_EMAC_DMA_TX_STATE_MASK |
\t\t\t\t            QTN_EMAC_DMA_RX_STATE_MASK)),
\t\t\t\t 10, QTN_TOPAZ_EMAC_QUIESCE_US);
\tif (!ret)
\t\temac->stop_reset_successes++;
\treturn ret;
}''')
 text=text[:start]+replacement+text[end:];driver.write_text(text,newline='\n')
 manifest={'schema':'openmitrastar.eth73-local-reset/v2','base_driver_sha256':'cf9441d47c168a050d6df9fefb834bfd5697e7340a33739d33b56b1ccbe9220a',
  'hardware_accessed':False,'scope':'Single EMAC reset only after stop timeout, stopped-state validation before release; quarantine on failure',
  'files':[{'path':p.relative_to(a.output).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(a.output.rglob('*')) if p.is_file() and p.name!='manifest.json']}
 (a.output/'RESET_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');print(driver)
if __name__=='__main__':main()
