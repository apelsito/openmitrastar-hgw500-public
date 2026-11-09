"""Keep firmware multicast wire ABI independent from host IPv6 stack config."""
from pathlib import Path
import hashlib,json,shutil,subprocess
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OLD=BASE/'quantenna73-providers-v7';OUT=BASE/'quantenna73-fwt-wire-v8'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 OUT.mkdir(mode=0o700);shutil.copytree(OLD/'compat',OUT/'compat')
 header=OUT/'compat/qtn/br_types.h';text=header.read_text()
 assert text.count('#if IS_ENABLED(CONFIG_IPV6)')==1
 text=text.replace('#if IS_ENABLED(CONFIG_IPV6)\n\t\tstruct in6_addr ip6;\n#endif','\t\tstruct in6_addr ip6;')
 text=text.replace('struct br_ip {','/* Firmware wire union always reserves IPv6 space, even without host IPv6. */\n#include <linux/in6.h>\nstruct br_ip {')
 header.write_text(text)
 cmd=json.loads((OLD/'objects/topaz/fwt_if.command.json').read_text())
 cmd=[x.replace(str(OLD/'compat'),str(OUT/'compat')) for x in cmd]
 cmd[cmd.index('-o')+1]=str(OUT/'fwt_if.o')
 with (OUT/'build.log').open('xb') as log:r=subprocess.run(cmd,cwd=BASE/'quantenna73-providers-v6/kernel-context',stdout=log,stderr=subprocess.STDOUT)
 witness=OUT/'wire-witness.c';witness.write_text('#include <qtn/br_types.h>\n#include <linux/stddef.h>\n_Static_assert(sizeof(struct br_ip)==20,"firmware multicast IPv4/IPv6 ABI");\n_Static_assert(offsetof(struct br_ip,proto)==16,"firmware protocol offset");\n_Static_assert(sizeof(((struct br_ip *)0)->u.ip6)==16,"IPv6 wire payload");\n')
 wc=list(cmd);wc[wc.index('-o')+1]=str(OUT/'wire-witness.o');wc[-1]=str(witness)
 with (OUT/'witness.log').open('xb') as log:w=subprocess.run(wc,cwd=BASE/'quantenna73-providers-v6/kernel-context',stdout=log,stderr=subprocess.STDOUT)
 result={'status':'PASS_FWT_FIRMWARE_WIRE_AND_C_UNIT' if r.returncode==w.returncode==0 else 'FWT_WIRE_COMPILE_INCOMPLETE','compile_exit':r.returncode,'wire_witness_exit':w.returncode,'wire_br_ip_size':20,'wire_proto_offset':16,'header_sha256':sha(header),'fwt_object_sha256':sha(OUT/'fwt_if.o') if r.returncode==0 else None,'hardware_accessed':False,'firmware_eligible':False,'limits':['Actual ARC compiler layout witness; not firmware traffic or IPv6 host-stack acceptance.','Shared wire type must be used by all consumers and complete kernel/module closure before use.']}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
