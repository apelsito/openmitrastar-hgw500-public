"""Preserve exact OEM private468 getter command spelling in a new candidate."""
import argparse, hashlib, json, shutil
from pathlib import Path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    shutil.copytree(args.parent, args.output)
    rel = 'source/wlan/ieee80211_wireless.c'
    path = args.output / rel
    text = path.read_text()
    old = '{468,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"g_rbsdfs_endtx"}'
    new = '{468,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"g_rbsdfs_end_tx"}'
    assert text.count(old) == 1
    text = text.replace(old, new, 1)
    path.write_text(text, newline='\n')
    proof = json.loads((args.parent / 'result.json').read_text())
    proof.update(status='SOURCE_ONLY_LINUX73_RBS468_EXACT_OEM_GETTER_ALIAS_PENDING_BUILD',
                 parent=str(args.parent), changed_sources={rel: sha(path)}, firmware_eligible=False,
                 rbs468_command_fix={'old': 'g_rbsdfs_endtx', 'new': 'g_rbsdfs_end_tx',
                                     'handler_and_type_unchanged': True})
    proof['files'] = {str(p.relative_to(args.output)): sha(p) for group in ('source','headers','kernel-overlay','providers') for p in (args.output / group).rglob('*') if p.is_file()}
    (args.output / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'status': proof['status'], 'changed_sources': proof['changed_sources']}, indent=2))

if __name__ == '__main__':
    main()
