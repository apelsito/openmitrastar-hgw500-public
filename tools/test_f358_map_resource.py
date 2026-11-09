"""Reproduce real physmap NO_XIP initialization against old/fixed map_rom C."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess
import f340_watchdog_contract as contract
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/kernel-port/versions/f350-spi-journal/kernel-overlay'
NEW=ROOT/'work/kernel-port/versions/f358-map-resource-fix'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def function(text,name):
 m=re.search(r'static int '+name+r'\([^;]*?\)\s*\{',text);assert m
 start=m.start();i=m.end();depth=1
 while depth:
  if text[i]=='{':depth+=1
  elif text[i]=='}':depth-=1
  i+=1
 return text[start:i]
def main():
 out=ROOT/'outputs/preflight'/('f358-map-resource-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 physmap='/home/user/openmitrastar-build/f350-flash-arbitration-20260921T155949Z/linux/drivers/mtd/maps/physmap-core.c'
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cat',str(physmap)],capture_output=True,check=True)
 (out/'physmap-core.c').write_bytes(p.stdout)
 stubs=(OLD/'tests/maprom_stubs.h').read_text().replace('struct map_info {','struct map_info {\n int swap;unsigned bankwidth;')
 extra=r'''
#define NO_XIP (~0UL)
#define CFI_BIG_ENDIAN 1
#define CFI_LITTLE_ENDIAN 2
struct resource {u64 start,end;};
struct device_node {const char *name;u64 start,size;bool noxip;};
struct physmap_flash_info {unsigned nmaps;struct map_info *maps;const char *probe_type;const char **part_types;};
struct platform_device {struct {struct device_node *of_node;}dev;struct physmap_flash_info *info;};
static struct physmap_flash_info *platform_get_drvdata(struct platform_device*d){return d->info;}
static const char *of_select_probe_type(struct platform_device*d){(void)d;return "map_rom";}
static const char **of_get_part_probes(struct platform_device*d){static const char *list[]={"cmdlinepart",NULL};(void)d;return list;}
static int of_property_read_string(struct device_node*d,const char*k,const char**v){assert(!strcmp(k,"linux,mtd-name"));*v=d->name;return 0;}
static int of_property_read_u32(struct device_node*d,const char*k,u32*v){(void)d;assert(!strcmp(k,"bank-width"));*v=4;return 0;}
static bool of_property_read_bool(struct device_node*d,const char*k){return !strcmp(k,"no-unaligned-direct-access")&&d->noxip;}
#define of_flash_probe_bt1_rom(...) 0
#define of_flash_probe_gemini(...) 0
#define of_flash_probe_ixp4xx(...) 0
#define of_flash_probe_versatile(...) 0
#define dev_err(...) ((void)0)
static int of_address_to_resource(void *node,int index,struct resource*r){struct device_node*d=node;if(!d||index)return -EINVAL;r->start=d->start;r->end=d->start+d->size-1;return 0;}
static u64 resource_size(const struct resource*r){return r->end-r->start+1;}
'''
 main_c=r'''
int main(void){
 struct map_info maps[5]={0};struct mtd_info *mtds[5];
 const char *names[]={"uboot_env","uboot_env_bak","data","rootfs_live","lyoko_store"};
 u64 starts[]={0x90020000,0x90030000,0x90f80000,0x90960000,0x90dc0000};
 u64 sizes[]={0x10000,0x10000,0x80000,0x460000,0x1c0000};struct device_node nodes[5];unsigned i;u64 cookie;unsigned char value;size_t n;
 assert(!map_rom_init());
 for(i=0;i<5;i++){
  struct physmap_flash_info info={1,&maps[i],NULL,NULL};struct platform_device dev;
  nodes[i]=(struct device_node){names[i],starts[i],sizes[i],true};dev.dev.of_node=&nodes[i];dev.info=&info;
  assert(!physmap_flash_of_init(&dev));assert(maps[i].phys==NO_XIP&&!strcmp(maps[i].name,names[i]));
  /* Actual physmap_probe preserves nonzero NO_XIP, sets size from resource. */
  if(!maps[i].phys)maps[i].phys=nodes[i].start;
  maps[i].size=nodes[i].size;maps[i].virt=calloc(1,maps[i].size);assert(maps[i].virt);
  mtds[i]=map_rom_probe(&maps[i]);assert(mtds[i]);
  if(EXPECT_FIXED)assert(!mtds[i]->_point&&!mtds[i]->_unpoint);
  else assert(mtds[i]->_point&&mtds[i]->_unpoint);
 }
 registered_store=mtds[4];assert(!strcmp(registered_store->name,"lyoko_store"));
 if(EXPECT_FIXED){assert(!qtn_topaz_flash_claim(&cookie));assert(!qtn_topaz_flash_read_store(cookie,0,&value,1));assert(mtds[3]->_read(mtds[3],0,1,&n,&value)==-EDEADLK);assert(!qtn_topaz_flash_release(cookie));}
 else assert(qtn_topaz_flash_claim(&cookie)==-ENODEV&&!mtd_refs);
 for(i=0;i<5;i++){maprom_f348_destroy(mtds[i]);free(mtds[i]);free(maps[i].virt);}registered_store=NULL;
 /* A correct name at the wrong physical resource cannot acquire ownership. */
 nodes[4].start=0x907e0000;maps[4].size=nodes[4].size;maps[4].phys=NO_XIP;maps[4].virt=calloc(1,maps[4].size);
 mtds[4]=map_rom_probe(&maps[4]);assert(mtds[4]);registered_store=mtds[4];assert(qtn_topaz_flash_claim(&cookie)==-ENODEV&&!mtd_refs);
 maprom_f348_destroy(mtds[4]);free(mtds[4]);free(maps[4].virt);registered_store=NULL;
 map_rom_exit();printf("F358_REGRESSION_PASS fixed=%d views=5 actual_physmap_init=1 old_enodev_reproduced=%d hardware=0\n",EXPECT_FIXED,!EXPECT_FIXED);return 0;
}
'''
 for name,source,fixed in [('old',OLD,0),('fixed',NEW,1)]:
  text=(source/'drivers/mtd/chips/map_rom.c').read_text();text=re.sub(r'^#include.*$','',text,flags=re.M)
  text=text.replace('EXPORT_SYMBOL_GPL(qtn_topaz_flash_claim);',(source/'drivers/mtd/chips/qtn_topaz_flash_guard_core.inc').read_text()+'\nEXPORT_SYMBOL_GPL(qtn_topaz_flash_claim);')
  (out/(name+'.c')).write_bytes((stubs+extra+function(p.stdout.decode(),'physmap_flash_of_init')+f'\n#define EXPECT_FIXED {fixed}\n'+text+main_c).encode())
 script=f'''set -eu
out={shlex.quote(linux(out))}
for variant in old fixed; do
 cc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -Wno-unused-function -pthread "$out/$variant.c" -o "$out/$variant"
 "$out/$variant" > "$out/$variant.log"
done
'''
 (out/'test.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'test.sh')],capture_output=True)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr)
 result={'schema':'openmitrastar.f358-map-resource-regression/v1','status':'PASS' if not run.returncode else 'FAIL','hardware_actions':False,'cause':'physmap NO_XIP sentinel substituted for real physical resource','sources':{str(p):sha(p) for p in NEW.rglob('*') if p.is_file()},'physmap_source_sha256':sha(out/'physmap-core.c'),'logs':{n:(out/(n+'.log')).read_text() for n in ['old','fixed'] if (out/(n+'.log')).exists()}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json')}));return run.returncode
if __name__=='__main__':raise SystemExit(main())
