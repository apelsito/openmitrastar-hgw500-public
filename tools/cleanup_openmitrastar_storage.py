"""Local OpenMitraStar storage inventory. Does not access the router."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import argparse, json, os, stat

ROOT = Path(__file__).resolve().parents[1]
ROOTS = [ROOT, Path.home()/'.openmitrastar', Path('/workspace/OpenMitraStar'),
         Path('/workspace/OpenMitraStar-build'), Path.home()/'DesktopMitraStar']

def inventory(root):
    stack = [root]
    rows, errors, links = [], [], []
    while stack:
        parent = stack.pop()
        try:
            with os.scandir(parent) as entries:
                for entry in entries:
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                            links.append(entry.path)
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            rows.append(dict(path=entry.path, bytes=st.st_size,
                                mtime_ns=st.st_mtime_ns, inode=st.st_ino,
                                device=st.st_dev, links=st.st_nlink))
                    except OSError as exc:
                        errors.append(dict(path=entry.path,error=str(exc)))
        except OSError as exc:
            errors.append(dict(path=str(parent),error=str(exc)))
    return rows, errors, links

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inventory', action='store_true')
    ap.add_argument('--root', action='append', type=Path)
    args=ap.parse_args()
    if not args.inventory:
        ap.error('select --inventory')
    out=ROOT/'outputs'/'cleanup'/('openmitrastar-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True,exist_ok=False)
    all_rows=[]; summaries=[]
    for root in args.root or ROOTS:
        if not root.exists():
            continue
        rows, errors, links=inventory(root); all_rows.extend(rows)
        groups=defaultdict(lambda: [0,0])
        groups2=defaultdict(lambda: [0,0])
        unique={}
        for row in rows:
            rel=Path(row['path']).relative_to(root)
            groups[rel.parts[0]][0]+=row['bytes']; groups[rel.parts[0]][1]+=1
            groups2['/'.join(rel.parts[:2])][0]+=row['bytes']; groups2['/'.join(rel.parts[:2])][1]+=1
            unique[(row['device'],row['inode']) if row['inode'] else row['path']]=row['bytes']
        summary=dict(root=str(root),files=len(rows),logical_bytes=sum(r['bytes'] for r in rows),
            unique_inode_bytes=sum(unique.values()),errors=errors,reparse_paths=links,
            top=[dict(path=k,bytes=v[0],files=v[1]) for k,v in sorted(groups.items(),key=lambda x:-x[1][0])],
            top2=[dict(path=k,bytes=v[0],files=v[1]) for k,v in sorted(groups2.items(),key=lambda x:-x[1][0])])
        summaries.append(summary)
        print(json.dumps({**{k:summary[k] for k in ('root','files','logical_bytes','unique_inode_bytes')},'top':summary['top'][:12]},ensure_ascii=False),flush=True)
    (out/'inventory.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(output=str(out),files=len(all_rows),errors=sum(len(x['errors']) for x in summaries))),flush=True)

if __name__=='__main__':
    main()
