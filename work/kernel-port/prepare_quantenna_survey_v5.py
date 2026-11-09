"""Version the corrected public-stats conversion without changing failedv4."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 target=ROOT/'survey_quantenna73_v5.py'
 if target.exists():raise RuntimeError('Version exists')
 code=(ROOT/'survey_quantenna73_v4.py').read_text().replace("OUT=BASE/'quantenna73-api-survey-v4'","OUT=BASE/'quantenna73-api-survey-v5'")
 needle=' netdevice.write_text(text)\n'
 addition=''' netdevice.write_text(text)
 # Public rtnetlink conversion copies only the upstream prefix. Quantenna's
 # appended counters stay private; never overwrite newer standard counters.
 core=kernel/'net/core/dev.c'
 t=core.read_text()
 old='size_t i, n = sizeof(*netdev_stats) / sizeof(atomic_long_t);'
 assert t.count(old)==1
 t=t.replace(old,'size_t i, n = offsetof(struct net_device_stats, rx_unicast_packets) / sizeof(atomic_long_t);',1)
 core.write_text(t)
'''
 assert code.count(needle)==1
 code=code.replace(needle,addition,1)
 # Avoid freeing an obsolete table node which is now a real sysctl entry.
 # The original cleanup uses [2].procname; both spellings are captured here.
 code=code.replace("t=t.replace('kfree(vap->iv_sysctls[2].procname);','/* net/<ifname> path copied by registration; no table node owner. */')","t=t.replace('kfree(vap->iv_sysctls[2].procname);','/* Path owner released after registration. */').replace('kfree((void *)vap->iv_sysctls[2].procname);','/* Path owner released after registration. */')")
 target.write_text(code)
 print(str(target))
if __name__=='__main__':main()
