"""Invoke only Windows PowerShell5.1; --execute is the physical boundary."""
from pathlib import Path
import argparse,subprocess
import f346_powershell as ps
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--plan',required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 args=[ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_suffix('.ps1')),'-PlanPath',a.plan,'-PlanSha256',a.plan_sha256]
 if a.execute:args.append('-Execute')
 return subprocess.run(args,env=ps.environment()).returncode
if __name__=='__main__':raise SystemExit(main())
