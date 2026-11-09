"""Run retained actual Linux73 generic AES primitives plus CCMP block wrapper on host."""
import argparse,hashlib,json,subprocess,ctypes
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--kernel-aes',type=Path,required=True);p.add_argument('--overlay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);t=a.kernel_aes.read_text();tables=[]
 for label in['static const u8 ____cacheline_aligned aes_sbox[]','const u32 ____cacheline_aligned aes_enc_tab[256]']:
  start=t.index(label);end=t.index('\n};',start)+3;tables.append(t[start:end])
 funcs=[]
 for sig in['static __always_inline void aes_prefetch(','static u32 mul_by_x(','static u32 mul_by_x2(','static u32 mix_columns(','static u32 inv_mix_columns(','static u32 subw(','static void aes_expandkey_generic(','static __always_inline u32 enc_quarterround(','static __always_inline u32 enclast_quarterround(','static void __maybe_unused aes_encrypt_generic(','static void aes_preparekey_arch(','static void aes_encrypt_arch(','static int __aes_preparekey(','int aes_prepareenckey(','void aes_encrypt(']:funcs.append(function(t,sig))
 wrapper=function((a.overlay/'source/wlan/ieee80211_crypto_ccmp.c').read_text(),'static void\nrijndael_encrypt(')
 pre=r'''#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;typedef uint32_t u32;
#define ____cacheline_aligned
#define __always_inline inline
#define __maybe_unused
#define L1_CACHE_BYTES 64
#define AES_KEYSIZE_128 16
#define AES_KEYSIZE_192 24
#define AES_KEYSIZE_256 32
#define AES_BLOCK_SIZE 16
#define barrier() __asm__ __volatile__("":::"memory")
union aes_enckey_arch{u32 rndkeys[60];};union aes_invkey_arch{u32 inv_rndkeys[60];};struct aes_enckey{u32 len,nrounds,padding[2];union aes_enckey_arch k;};typedef union{const struct aes_enckey*enc_key;}aes_encrypt_arg __attribute__((__transparent_union__));
static int aes_check_keylen(size_t n){return(n==16||n==24||n==32)?0:-EINVAL;}
static u32 rol32(u32 x,unsigned n){return(x<<n)|(x>>(32-n));}static u32 ror32(u32 x,unsigned n){return(x>>n)|(x<<(32-n));}
static u32 get_unaligned_le32(const void*p){u32 x;memcpy(&x,p,4);return x;}static void put_unaligned_le32(u32 x,void*p){memcpy(p,&x,4);}
'''
 f=a.output/'actual-aes-block.c';f.write_text(pre+'\n'.join(tables+funcs)+wrapper+'\n__declspec(dllexport) int test_block(const u8*k,const u8*in,u8*out,int same){struct aes_enckey key;int rc=aes_prepareenckey(&key,k,16);if(rc)return rc;if(same){memcpy(out,in,16);rijndael_encrypt(&key,out,out);}else rijndael_encrypt(&key,in,out);memset(&key,0,sizeof(key));return 0;}\n');compiler=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/clang.exe';dll=a.output/'actual-aes.dll';r=subprocess.run([str(compiler),'-shared','-O2','-std=gnu11',str(f),'-o',str(dll)],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();lib=ctypes.CDLL(str(dll.resolve()));fn=lib.test_block;fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int];cases=0
 vectors=[(bytes.fromhex('000102030405060708090a0b0c0d0e0f'),bytes.fromhex('00112233445566778899aabbccddeeff'))]
 vectors.extend((hashlib.sha256(('key'+str(i)).encode()).digest()[:16],hashlib.sha256(('data'+str(i)).encode()).digest()[:16])for i in range(4096))
 for key,block in vectors:
  enc=Cipher(algorithms.AES(key),modes.ECB()).encryptor();expected=enc.update(block)+enc.finalize()
  for inplace in[0,1]:
   out=ctypes.create_string_buffer(16);assert fn(key,block,out,inplace)==0 and out.raw==expected;cases+=1
 pins={str(x):sha(x)for x in[Path(__file__),a.kernel_aes,a.overlay/'source/wlan/ieee80211_crypto_ccmp.c',compiler,f,dll]};r={'status':'PASS_ACTUAL_LINUX73_GENERIC_AES_AND_CCMP_BLOCK_WRAPPER_8194_CASES','hardware_accessed':False,'firmware_eligible':False,'cases':cases,'pins':pins,'limits':'ActualretainedLinux73AESgenericfunctions/tables+CCMPforwardwrapper vscryptographylibrary, in/outplace. Minimalhoststruct/unaligned macros; notARC/module/fullCCMPMIC/radio proof.'};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
