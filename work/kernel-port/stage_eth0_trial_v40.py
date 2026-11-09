"""Wait for owner cable move, bound eth0 test, automatically restore eth1."""
from pathlib import Path
import hashlib,json
from ssh_radio73 import execute,ROOT

SCRIPT=r'''set -eu
stage=/run/om73-eth0-v40
restore() {
 /bin/busybox ifconfig eth0 down
 /bin/busybox ifconfig eth1 192.168.1.91 netmask 255.255.255.0 up
 printf 'RESTORE_RC=%s\n' "$?" > "$stage/restore.txt"
}
trap restore EXIT
printf 'WAITING_OWNER_CABLE\n' > "$stage/state"
counter=0
while [ "$counter" -lt 300 ]; do
 [ "$(cat /sys/class/net/eth1/carrier)" = 0 ] && break
 /bin/busybox sleep 1
 counter=$((counter+1))
done
[ "$counter" -lt 300 ] || exit 3
/bin/busybox ifconfig eth1 down
/bin/busybox ifconfig eth0 192.168.1.90 netmask 255.255.255.0 up
printf 'ETH0_TRIAL_ACTIVE\n' > "$stage/state"
/bin/busybox sleep 210
printf 'RESTORING_ETH1\n' > "$stage/state"
'''
def main():
 output=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-eth0-stage-v40'
 if output.exists():raise ValueError('Immutable evidence exists')
 output.mkdir();(output/'trial.sh').write_bytes(SCRIPT.encode())
 digest=hashlib.sha256(SCRIPT.encode()).hexdigest()
 command="test \"$(uname -r)\" = '7.3.0-openmitrastar-radio73-v1' && test ! -e /run/om73-eth0-v40 && mkdir /run/om73-eth0-v40 && cat > /run/om73-eth0-v40/trial.sh"
 staged=execute(command,SCRIPT.encode(),timeout=15)
 if staged['exit_code']!=0:raise RuntimeError('Exact trial stage refused')
 verify=execute("sha256sum /run/om73-eth0-v40/trial.sh",timeout=10)
 if verify['exit_code']!=0 or not verify['stdout'].startswith(digest):raise RuntimeError('Staged script digest differs')
 launch=execute("/bin/busybox sh /run/om73-eth0-v40/trial.sh >/run/om73-eth0-v40/trial.log 2>&1 </dev/null & echo ETH0_WATCH_PID=$!",timeout=10)
 state=execute("cat /run/om73-eth0-v40/state",timeout=10)
 result={'status':'ARMED_OWNER_ETH0_CABLE_MOVE','script_sha256':digest,'staged':staged,'launch':launch,'state':state,'automatic_restore':'eth0down,eth1.91up after210s; waits300s for eth1carrier0','flash':False,'bootenv':False}
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
