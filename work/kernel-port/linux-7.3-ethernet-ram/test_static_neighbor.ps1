param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
$taskOutput=[IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path $taskOutput -ErrorAction Stop | Out-Null
$taskDtb='/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f367r9-f365-transition-observation-device-bound\openmitrastar-linux510-f367r9-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.dtb'
$taskParse=@'
from pathlib import Path
import struct
d=Path(r"/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f367r9-f365-transition-observation-device-bound\openmitrastar-linux510-f367r9-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.dtb").read_bytes()
magic,total,start,strings,*_=struct.unpack_from('>10I',d)
assert magic==0xd00dfeed and total==len(d)
cursor=start;stack=[];found=[]
while True:
 t=struct.unpack_from('>I',d,cursor)[0];cursor+=4
 if t==1:
  end=d.index(0,cursor);stack.append(d[cursor:end].decode());cursor=(end+4)&~3
 elif t==2:stack.pop()
 elif t==3:
  n,offset=struct.unpack_from('>II',d,cursor);cursor+=8;end=d.index(0,strings+offset);name=d[strings+offset:end].decode();value=d[cursor:cursor+n];cursor=(cursor+n+3)&~3
  if stack[-1]=='ethernet@e8000000' and name=='local-mac-address':found.append(value)
 elif t==4:pass
 elif t==9:break
 else:raise ValueError('Bad DT token')
assert len(found)==1 and len(found[0])==6
m=bytearray(found[0]);assert not m[0]&1 and m[0]<=253;m[0]+=2
print('-'.join(format(x,'02x') for x in m))
'@
$taskMac=(& python -c $taskParse).Trim()
if($LASTEXITCODE -ne 0 -or $taskMac -notmatch '^([0-9a-f]{2}-){5}[0-9a-f]{2}$'){throw 'Per-unit address parsing refused'}
$taskPrevious=Get-NetNeighbor -InterfaceIndex 16 -IPAddress 192.168.1.91 -ErrorAction SilentlyContinue
if($taskPrevious -and $taskPrevious.State -notin @('Unreachable','Incomplete')){throw 'Existing useful neighbor; preserve it'}
$taskCreated=$false
try{
 if($taskPrevious){Remove-NetNeighbor -InterfaceIndex 16 -IPAddress 192.168.1.91 -Confirm:$false}
 New-NetNeighbor -InterfaceIndex 16 -IPAddress 192.168.1.91 -LinkLayerAddress $taskMac -State Permanent -ErrorAction Stop | Out-Null
 $taskCreated=$true
 $taskPing=& 'C:\Windows\System32\ping.exe' -n 4 -w 1000 192.168.1.91
 $taskExit=$LASTEXITCODE
 $taskReplies=@($taskPing | Where-Object {$_ -match 'TTL=64'}).Count
 $taskResult=[ordered]@{schema='openmitrastar.eth73-static-neighbor/v1';ping_exit_code=$taskExit;replies_ttl64=$taskReplies;requests=4;raw_mac_saved=$false;router_mutated=$false;host_entry_removed=$false}
}finally{
 if($taskCreated){Remove-NetNeighbor -InterfaceIndex 16 -IPAddress 192.168.1.91 -Confirm:$false -ErrorAction Stop}
 if($taskResult){$taskResult.host_entry_removed=$true;$taskResult | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskOutput 'result.json');$taskResult | ConvertTo-Json}
}
