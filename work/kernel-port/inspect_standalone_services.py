"""Read-only standalone service prerequisites; no radio/network mutations."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ssh_radio73 import execute
cmd="/bin/busybox --list | /bin/busybox grep -E '^(udhcpd|udhcpc|timeout|stty|pidof|brctl)$'; cat /proc/sys/kernel/random/entropy_avail; cat /proc/mtd 2>/dev/null"
print(json.dumps(execute(cmd,host='192.168.1.90',timeout=15),indent=2))
