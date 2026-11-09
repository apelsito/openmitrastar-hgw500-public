"""Replace only the unavailable rmdir cleanup with a guarded owned empty-dir release."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'versions/lyoko-foundation-6.11.1-f367r2-protected-preamble/overlay'
DST=ROOT/'versions/lyoko-foundation-6.11.2-f367r3-owned-lock-release/overlay'
CAP=ROOT/'outputs/handoff-live/f367-rm-capability-20260922T142813Z/result.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 if (DST.parent/'source-manifest.json').exists():raise ValueError('immutable F367r3 revision exists')
 capability=json.loads(CAP.read_text())
 if sha(CAP)!='621f3254a3ff9fc06e80da4247d84b491edb46f20af71b7f48c79341dd05c452' or capability.get('passed') is not True or capability.get('exit_code')!=0 or capability.get('radio_or_mtd_actions') is not False or capability.get('preexisting_data_removed') is not False:raise ValueError('real rm capability not qualified')
 shutil.copytree(SRC,DST,dirs_exist_ok=True);p=DST/'usr/sbin/om-f367-stage';s=p.read_text()
 old=r'''i=0
while ! mkdir "$state/ipc-lock" 2>/dev/null; do i=$((i+1)); [ "$i" -lt 4 ] || { printf 'OMF367_WDT_REJECT operation=lock client_rc=73 owner_state=unqueried\n' >&2; exit 73; }; sleep 1; done
trap 'rmdir "$state/ipc-lock" 2>/dev/null || true' EXIT'''
 new=r'''# The HGW has /bin/rm -r but no rmdir command or BusyBox rmdir applet.
# Only this fixed child, acquired by this process, may be released.
case "$state" in /*) ;; *) printf 'OMF367_LOCK_REJECT reason=nonabsolute-state\n' >&2; exit 73;; esac
lock_dir="${state%/}/ipc-lock"
lock_owner=$$
i=0
while ! mkdir "$lock_dir" 2>/dev/null; do i=$((i+1)); [ "$i" -lt 4 ] || { printf 'OMF367_WDT_REJECT operation=lock client_rc=73 owner_state=unqueried\n' >&2; exit 73; }; sleep 1; done
lock_owned=1
release_lock()
{
 [ "$lock_owned" = 1 ] || return 0
 lock_owned=0
 [ -d "$lock_dir" ] && [ ! -L "$lock_dir" ] || { lock_error=directory-replaced; return 1; }
 [ -f "$lock_dir/.owner" ] && [ ! -L "$lock_dir/.owner" ] || { lock_error=owner-marker-missing; return 1; }
 [ "$(cat "$lock_dir/.owner")" = "$lock_owner" ] || { lock_error=owner-mismatch; return 1; }
 # Refuse unexpected visible/hidden entries. Never recursively clear content.
 for lock_entry in "$lock_dir"/* "$lock_dir"/.[!.]* "$lock_dir"/..?*; do
  [ "$lock_entry" != "$lock_dir/.owner" ] || continue
  if [ -e "$lock_entry" ] || [ -L "$lock_entry" ]; then lock_error=unexpected-entry; return 1; fi
 done
 /bin/rm -f "$lock_dir/.owner" || { lock_error=owner-marker-remove; return 1; }
 # The directory was checked empty apart from our removed marker. Its parent
 # is private, and competing stage processes only attempt mkdir, never write.
 /bin/rm -r "$lock_dir" || { lock_error=empty-directory-remove; return 1; }
 return 0
}
finish_stage()
{
 stage_rc=$?
 trap - EXIT
 if ! release_lock; then printf 'OMF367_LOCK_RELEASE_FAILED reason=%s exit_code=74\n' "$lock_error" >&2; exit 74; fi
 exit "$stage_rc"
}
trap finish_stage EXIT
printf '%s\n' "$lock_owner" >"$lock_dir/.owner" || exit 74'''
 if s.count(old)!=1:raise ValueError('sealed R2 lock block changed')
 p.write_bytes(s.replace(old,new,1).encode())
 report={'schema':'openmitrastar.f367r3-owned-lock-source/v1','status':'PREPARED_FOR_PATH_AND_CONCURRENCY_TEST','capability':{'path':str(CAP),'sha256':sha(CAP)},'files':{p.relative_to(DST).as_posix():sha(p) for p in DST.rglob('*') if p.is_file()},'changed_files':['usr/sbin/om-f367-stage'],'rmdir_required':False,'recursive_force_delete':False,'requires_mkdir_ownership_and_only_own_marker':True,'cleanup_failure_exit_code':74,'hardware_actions':False}
 (DST.parent/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'revision':str(DST),'stage_sha256':sha(p),'capability_sha256':sha(CAP)}))
if __name__=='__main__':main()
