"""Adapt remaining provider APIs; keep failedv6 and originalGPL immutable."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,re,shutil,subprocess
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OLD=BASE/'quantenna73-providers-v6';OUT=BASE/'quantenna73-providers-v7'
REPO=Path('/workspace/user-home/Desktop/MitraStar/repos/openmitrastar-hgw500-quantenna-5ghz-driver')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 OUT.mkdir(mode=0o700)
 for folder in ['source','headers','compat','legacy','port-context','platform']:shutil.copytree(OLD/folder,OUT/folder)
 f=OUT/'platform/ruby/gpio.c';t=f.read_text()
 t=t.replace('static void arc_gpio_set(', 'static int arc_gpio_set(')
 needle='\tgpio_output(g, offset, value);\n}\n';assert t.count(needle)==1;t=t.replace(needle,'\tgpio_output(g, offset, value);\n\treturn 0;\n}\n',1)
 t=t.replace('\tgpiochip_add(&arc_gpio.chip);\n\n\treturn 0;', '\treturn gpiochip_add_data(&arc_gpio.chip, NULL);')
 f.write_text(t)
 f=OUT/'platform/topaz/switch_tqe.c';f.write_text(f.read_text().replace('netif_napi_add(', 'netif_napi_add_weight('))
 f=OUT/'platform/topaz/switch_vlan.c';f.write_text(f.read_text().replace('../../qdrv/qdrv_dma_wire.h','qdrv_dma_wire.h'))
 f=OUT/'platform/topaz/switch_emac.c';t=f.read_text()
 t=t.replace('\tconst u8 *mac;\n','\tu8 mac[ETH_ALEN];\n',1)
 t=t.replace('\tmac = of_get_mac_address(np);\n\tif (!mac || !is_valid_ether_addr(mac)) {','\tif (of_get_mac_address(np, mac) || !is_valid_ether_addr(mac)) {',1)
 t=t.replace('\tmemcpy(dev->dev_addr, mac, ETH_ALEN);\n','',1)
 a=t.index('static int topaz_emac_set_eth_addr(');b=t.index('\n}\n',a)
 body=t[a:b].replace('dev->dev_addr[','mac[')
 body=body.replace('\n\treturn 0;', '\n\teth_hw_addr_set(dev, mac);\n\treturn 0;')
 t=t[:a]+body+t[b:];f.write_text(t)
 # fwt_if has an unconditional IPv6 parser, while the actual kernel currently
 # selects noIPv6. Guard its IPv6 source paths explicitly; keep IPv4 functional.
 f=OUT/'platform/topaz/fwt_if.c';t=f.read_text()
 # This provider remains a reported error until its IPv6 path is typed and
 # tested. Do not substitute an empty ip6 storage or stub parser here.
 headers=OUT/'platform/ruby/rtl8367b'
 src=REPO/'vendor/legacy-gpl/drivers/ruby/rtl8367b'
 if src.is_dir():shutil.copytree(src,headers)
 # Modern cipher definitions moved to crypto/internal/cipher.h. The preserved
 # CCMP implementation uses the same sync cipher API.
 f=OUT/'source/wlan/ieee80211_crypto_ccmp.c';t=f.read_text();t='#include <crypto/internal/cipher.h>\n'+t;f.write_text(t)
 jobs=json.loads((OLD/'result.json').read_text())['rows']
 rows=[]
 def compile(record):
  folder,name=record['folder'],record['module'];target=OUT/'objects'/folder;target.mkdir(parents=True,exist_ok=True)
  cmd=json.loads((OLD/'objects'/folder/(name+'.command.json')).read_text())
  cmd=[x.replace(str(OLD),str(OUT)) for x in cmd]
  cmd=[x.replace(str(OUT/'kernel'),str(OLD/'kernel')).replace(str(OUT/'kernel-context'),str(OLD/'kernel-context')) for x in cmd]
  (target/(name+'.command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  r=subprocess.run(cmd,cwd=OLD/'kernel-context',capture_output=True,text=True,timeout=120);(target/(name+'.stderr')).write_text(r.stderr)
  errors=[l for l in r.stderr.splitlines() if re.search('error:|fatal error:',l)]
  row={'folder':folder,'module':name,'exit':r.returncode,'errors':errors[:24]}
  if not r.returncode:row.update(bytes=(target/(name+'.o')).stat().st_size,sha256=sha(target/(name+'.o')))
  print(json.dumps({'module':name,'compiled':r.returncode==0,'first_error':errors[:1]}),flush=True);return row
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(compile,jobs))
 result={'status':'QUANTENNA73_PROVIDER_API_ADAPTATION_ONLY','rows':rows,'compiled':sum(x['exit']==0 for x in rows),'failed':sum(x['exit']!=0 for x in rows),'hardware_accessed':False,'firmware_eligible':False,'fwt_ipv6':'UNRESOLVED_EXPLICIT_NO_STUB','semantic_tests':'PENDING'}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['status','compiled','failed']}))
if __name__=='__main__':main()
