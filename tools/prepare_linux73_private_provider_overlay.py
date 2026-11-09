"""Owned Linux73 provider/source API overlay; original sources unchanged."""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);changes={};pins={};patch=[]
 def write(before,rel,text):
  f=a.output/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(text,newline='\n');pins[str(before)]=sha(before);changes[rel]=sha(f);patch.extend(difflib.unified_diff(before.read_text().splitlines(True),text.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 relative='source/wlan/ieee80211_crypto_ccmp.c';before=a.parent/relative;t=before.read_text();t=t.replace('#include <linux/crypto.h>','#include <crypto/aes.h>\n#include <linux/slab.h>');assert 'struct crypto_cipher *cc_tfm;'in t;t=t.replace('struct crypto_cipher *cc_tfm;','struct aes_enckey *cc_tfm;');t=t.replace('crypto_free_cipher(ctx->cc_tfm);','kfree_sensitive(ctx->cc_tfm);')
 old='''			ctx->cc_tfm = crypto_alloc_cipher("aes", 0,
							  CRYPTO_ALG_ASYNC);''';assert old in t;t=t.replace(old,'\t\t\tctx->cc_tfm = kzalloc(sizeof(*ctx->cc_tfm), GFP_ATOMIC);',1)
 old='\t\tcrypto_cipher_setkey(ctx->cc_tfm, k->wk_key, k->wk_keylen);';assert old in t;t=t.replace(old,'''\t\t/* Linux73 AES block library; CCMP only uses the forward AES primitive. */
\t\tif (aes_prepareenckey(ctx->cc_tfm, k->wk_key, k->wk_keylen)) {
\t\t\tkfree_sensitive(ctx->cc_tfm);
\t\t\tctx->cc_tfm = NULL;
\t\t\treturn 0;
\t\t}''',1)
 t=t.replace('struct crypto_cipher *tfm','struct aes_enckey *tfm').replace('crypto_cipher_encrypt_one(tfm, dst, src);','aes_encrypt(tfm, dst, src);');assert 'crypto_cipher'not in t;write(before,relative,t)
 relative='source/qdrv/compat/include/openmitrastar_qdrv_compat.h';before=a.parent/relative;t=before.read_text();anchor='#include <linux/openmitrastar_bridge.h>';assert anchor in t;t=t.replace(anchor,anchor+'''\n#include <linux/proc_fs.h>
#include <linux/string.h>
#include <linux/unaligned.h>

/* Removed legacy APIs, preserving strlcpy return length rather than strscpy's
 * negative truncation result. Inputs obey the existing C-string contract. */
static inline size_t om_linux73_strlcpy(char *dst, const char *src, size_t size)
{
    size_t len = strlen(src);
    if (size) {
        size_t copy = len < size - 1 ? len : size - 1;
        memcpy(dst, src, copy);
        dst[copy] = '\\0';
    }
    return len;
}
#define strlcpy om_linux73_strlcpy
#ifndef PDE_DATA
#define PDE_DATA(inode) pde_data(inode)
#endif
''',1);write(before,relative,t)
 before=a.parent/'source/qdrv/compat/include/asm/unaligned.h'
 if before.exists():write(before,'source/qdrv/compat/include/asm/unaligned.h','#include <linux/unaligned.h>\n')
 else:
  f=a.output/'source/qdrv/compat/include/asm/unaligned.h';f.parent.mkdir(parents=True,exist_ok=True);f.write_text('#include <linux/unaligned.h>\n');changes[str(f.relative_to(a.output))]=sha(f)
 provider=ROOT/'work/linux510-radio-port/quantenna/platform/ruby'
 for name in['qtn_pm_qos_compat.c','qtn_platform_support.c','board_compat.c','runtime_compat.c']:
  before=provider/name;t=before.read_text()
  if name=='qtn_platform_support.c':
   assert t.count('if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2"))')==1;t=t.replace('if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2"))','if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&\n\t    !of_machine_is_compatible("openmitrastar,hgw500-topaz-basic"))',1)
  if name=='board_compat.c':
   assert t.count('target_ok = of_machine_is_compatible("mitrastar,hgw-500bna-qcv2");')==1;t=t.replace('target_ok = of_machine_is_compatible("mitrastar,hgw-500bna-qcv2");','target_ok = of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") ||\n\t\tof_machine_is_compatible("openmitrastar,hgw500-topaz-basic");',1)
  write(before,'providers/'+name,t)
 # Exact copied private class header; native CPU latency/frequency QoS differs.
 before=a.parent/'source/qdrv/compat/include/linux/pm_qos_params.h';write(before,'providers/include/linux/pm_qos_params.h',before.read_text())
 before=ROOT/'work/sources/Quantenna-GPL/common/ruby_pm.h';write(before,'providers/include/common/ruby_pm.h',before.read_text())
 (a.output/'providers/Kbuild').write_text('ccflags-y += -I$(src)/include\nobj-m += qtn_pm_qos_compat.o\n',newline='\n')
 (a.output/'linux73-private-provider.patch').write_text(''.join(patch),newline='\n');pins[str(Path(__file__))]=sha(__file__);r={'status':'SOURCE_ONLY_LINUX73_CCMPLIBAES_PROC_STRING_AND_PRIVATE_PROVIDERS_PENDING_COMPILE','hardware_accessed':False,'firmware_eligible':False,'parent':str(a.parent),'files':changes,'pins':pins,'provider_compile_scope':'qtn_pm_qos_compatstandalone first;platform/board/runtime require fullcustompacket/provider dependencyclosure','limits':['AES forwardonly128bitCCMP usesmodernlibaes; bytefunctional comparison andactualfullccmpcompilepending.','PMQoS privatePowerSaveclass semantics retained; noCPULatencyQoSmapping.','DTmatchupdatedtoexactHGW500BASIC; noauto-load/MMIOexecution.','SRAMfallback andphysicalprobesremainexistingoptincontrols, defaultsfalse; sourceonlynotradioacceptance.','No5.10objects/Git/hardware/download/configmutation.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json'),'files':len(changes)},indent=2))
if __name__=='__main__':main()
