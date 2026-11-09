"""Resolve only disjoint WEXT case insertions in a new aggregate revision."""
import argparse
import re
import subprocess
import sys
from pathlib import Path
import prepare_hgw5g_all_ops_source as parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run=subprocess.run
    def merge(command,*positional,**keywords):
        result=run(command,*positional,**keywords)
        if command[:3]!=['git','merge-file','-p']or not result.returncode:return result
        raw=result.stdout
        def resolve(match):
            ours,theirs=match[1],match[2]
            if (command[-1].replace('\\','/').endswith('/headers/net80211/ieee80211_var.h')and
                b'/* OEM481 host-private worker and retained482 transaction. */'in ours and
                theirs==b'\t/* OEM466/468 host state append; whole enclosing ABI rebuild required. */\n\tstruct om_rbsdfs_kernel_state om_rbsdfs;\n'):
                return ours+theirs
            # Explicitly limited to independent switch-case insertions. Each
            # block begins with case and uses distinct command expressions.
            is_cases=ours.lstrip().startswith(b'case ')and theirs.lstrip().startswith(b'case ')
            is_records=ours.lstrip().startswith(b'{')and theirs.lstrip().startswith(b'{')
            if not is_cases and not is_records:return match[0]
            labels=(lambda block:set(re.findall(rb'(?m)^\s*case ([^:\n]+):',block)))if is_cases else(lambda block:set(re.findall(rb'"([A-Za-z0-9_]+)"',block)))
            if is_records and (not labels(ours)or not labels(theirs)):return match[0]
            if labels(ours)&labels(theirs):return match[0]
            return ours+theirs
        merged=re.sub(rb'<<<<<<< [^\n]+\n(.*?)=======\n(.*?)>>>>>>> [^\n]+\n',resolve,raw,flags=re.S)
        if b'<<<<<<< 'not in merged:
            return subprocess.CompletedProcess(command,0,merged,result.stderr)
        return subprocess.CompletedProcess(command,result.returncode,merged,result.stderr)
    parent.subprocess.run=merge
    sys.argv=[str(Path(parent.__file__)),'--output',str(args.output)]
    parent.main()


if __name__=='__main__':main()
