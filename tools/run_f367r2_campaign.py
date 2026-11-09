"""Use pinned Windows PowerShell 5.1 and its own module path for exact F367r2 with protected preamble."""
from pathlib import Path
import argparse,subprocess
import f346_powershell as desktop_ps
def main():
    ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    command=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_suffix('.ps1')),'-PlanPath',args.plan,'-PlanSha256',args.plan_sha256]
    if args.execute:command.append('-Execute')
    return subprocess.run(command,env=desktop_ps.environment()).returncode
if __name__=='__main__':raise SystemExit(main())
