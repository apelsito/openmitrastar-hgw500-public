"""Prepare isolatedWindowsREA ARC700 staticlab using existing tools only.

Noinstalledtool/config/service modifications. CopyexistingGhidra andREAruntime
to newworkspaceout; linkexistingnode_modules. ARC languagecompiledSLA is copied
from provenLinuxlab viareadonlyUNC, preservingoriginalXMLexceptobsoleteemulator
property removed. AdmitgenuineARC ELF32LE ET_REL/ET_EXEC flags0/3/303/403 only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


ROOT=Path(__file__).resolve().parents[1]
REA=Path('D:/Tools/REA/npm/node_modules/rea-agents')
GHIDRA=Path('D:/Tools/REA/ghidra_12.1.4_PUBLIC')
JAVA=Path('D:/Tools/REA/jdk-21.0.12.1+1')
NODE=Path('D:/Tools/REA/node-v24.16.0-win-x64/node.exe')
LANG=Path(r'\\wsl.localhost\REA-Linux\home\rea\openmitrastar-arc700-lab-20261021-r2\ghidra_12.1.4_PUBLIC\Ghidra\Processors\ARCompact')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 for path in(REA/'package.json',GHIDRA/'support/analyzeHeadless.bat',JAVA/'bin/java.exe',NODE,LANG/'data/languages/ARCompact.sla'):assert path.is_file(),path
 a.output.mkdir(parents=True,exist_ok=False)
 view=a.output/'ghidra_12.1.4_PUBLIC';shutil.copytree(GHIDRA,view)
 module=view/'Ghidra/Processors/ARCompact';shutil.copytree(LANG,module)
 runtime=a.output/'rea-agents';runtime.mkdir()
 for name in('dist','bridge','scripts'):shutil.copytree(REA/name,runtime/name)
 shutil.copytree(REA/'native/windows/build',runtime/'native/windows/build')
 for name in('package.json','LICENSE','README.md'):shutil.copyfile(REA/name,runtime/name)
 # Windowsjunction/symlink creation viajunctioncommand handledcaller; no config.
 patches=[]
 for path in(runtime/'dist').rglob('*.js'):
  original=path.read_text(encoding='utf-8');text=original
  text=re.sub(r'(case 164:\s*(?://[^\n]*\n\s*)?return "hexagon";)','case 93: return "arc700";\n'+r'\1',text)
  text=re.sub(r'("hexagon")(\s*,?\s*\])',r'\1, "arc700"\2',text)
  if 'architecture: elfArchitecture(machine) ?? null'in text:
   needle='const machine = readU16(18);';assert needle in text
   gate='''
    if (machine === 93 && (elfClass !== 32 || !littleEndian ||
        ![1, 2].includes(readU16(16)) ||
        ![0x0, 0x3, 0x303, 0x403].includes(readU32(36))))
        return err("ARC700Windowslocalstaticlane requires genuineELF32LE ET_REL/ET_EXEC supportedARCflags");
''';text=text.replace(needle,needle+gate)
  needle='inspectWindowsP0TargetSupport = (target, diagnostics) => {'
  if needle in text:
   admission='''
            if (target.kind === "executable" && target.format === "elf" && target.architecture === "arc700")
                return { status: "supported", code: null, reason: null, diagnostics };
'''
   text=text.replace(needle,needle+admission)
  if text!=original:
   before=sha(path);path.write_text(text,encoding='utf-8');patches.append(dict(path=str(path.relative_to(runtime)),parent_sha256=before,derived_sha256=sha(path)))
 assert any('peMachine-'in x['path']for x in patches)and any('binary-'in x['path']for x in patches)
 pspec=module/'data/languages/ARCompact.pspec';original=pspec.read_text();pspec.write_text(re.sub(r'\s*<properties>.*?</properties>','',original,flags=re.S))
 result=dict(status='PREPARED_WINDOWS_ARC_STATIC_LAB_NEEDS_VALIDATION',runtime=str(runtime),ghidra=str(view),java=str(JAVA),node=str(NODE),language_id='ARCompact:LE:32:default',compiler_spec_id='default',patches=patches,compiled_sla_sha256=sha(module/'data/languages/ARCompact.sla'),compiled_sla_source_sha256=sha(LANG/'data/languages/ARCompact.sla'),existing_node_modules=str(REA/'node_modules'),hardware_accessed=False,installed_runtime_modified=False,codex_config_modified=False,limitations=['Isolatedlocalrecognitionlane notupstreamsupport','Noemulation/loader/radio/deviceexecution','ExactARCdecoderverificationagainstpinnedartifact required'])
 (a.output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in('status','runtime','ghidra','compiled_sla_sha256')}))


if __name__=='__main__':main()
