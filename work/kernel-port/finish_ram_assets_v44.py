"""Remove only exact temporary uploader and MIME trial server after their gates."""
from pathlib import Path
import json
from ssh_radio73 import execute,ROOT
def main():
 out=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-temporary-tools-cleanup-v44'
 if out.exists():raise ValueError('Immutable evidence exists')
 out.mkdir()
 command=r'''if [ -e /proc/2288/comm ]; then test "$(cat /proc/2288/comm)" = uhttpd && kill -TERM 2288; fi
if [ -e /www/__assets.cgi ]; then test "$(sha256sum /www/__assets.cgi | cut -d ' ' -f 1)" = '74128b573bf0a9e007862a50fdd5ee0747a41d6e380a7f476fd70d47ed62b06f' && rm /www/__assets.cgi; fi
test ! -e /www/__assets.cgi && echo TEMPORARY_UPLOAD_REMOVED
cat /proc/uptime'''
 result=execute(command,timeout=15)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
