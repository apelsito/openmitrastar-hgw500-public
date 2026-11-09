"""Offline parser and cleanup tests; no UART, SSH or device access."""
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'tools/hgw_uart_rx_integrity_probe.ps1'
RUN='OM_RX_OFFLINE_0123456789'


def quote(value):
    return "'"+str(value).replace("'","''")+"'"


def ps(code, shell='powershell.exe'):
    p=subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',code],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr or p.stdout
    return p.stdout.strip()


def functions():
    return f"""$ErrorActionPreference='Stop';$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile({quote(SCRIPT)},[ref]$tokens,[ref]$errors)
if($errors.Count){{throw 'parse errors'}}
foreach($node in $ast.EndBlock.Statements){{if($node -is [Management.Automation.Language.FunctionDefinitionAst]){{. ([scriptblock]::Create($node.Extent.Text))}}}}
"""


def frame(payload, prefix=b'', suffix=b''):
    return prefix+(RUN+'_BEGIN:').encode()+payload+(':'+RUN+'_END').encode()+suffix


def parse(data, size=8, run=RUN, shell='powershell.exe'):
    code=functions()+f"$b=[Convert]::FromBase64String({quote(base64.b64encode(data).decode())});try{{Test-HgwRxFrame -Bytes $b -RunId {quote(run)} -ExpectedBytes {size} | ConvertTo-Json -Compress}}catch{{'REFUSED'}}"
    out=ps(code,shell)
    return out if out=='REFUSED' else json.loads(out)


@pytest.mark.parametrize('shell',['powershell.exe','pwsh.exe'])
def test_exact_pattern_and_noise_outside_frame(shell):
    value=parse(frame(b'\x06C'*4,b'not saved',b'not saved either'),shell=shell)
    assert value['payload_matches'] is True and value['received_bytes']==8
    assert value['ignored_prefix_bytes']==9 and value['ignored_suffix_bytes']==16
    assert value['expected_sha256']==value['received_sha256']
    assert 'not saved' not in json.dumps(value)


@pytest.mark.parametrize('payload',[b'\x06C'*3,b'\x06C'*5,b'\xaaC'+b'\x06C'*3,b'\x06C\r\n'+b'\x06C'*3])
def test_missing_extra_changed_and_newline_bytes_fail(payload):
    assert parse(frame(payload))['payload_matches'] is False


def test_console_log_classification_never_filters_data_or_grants_pass():
    value=parse(frame(b'\x06C'*2+b'OMEMAC poll synthetic private text\r\n'+b'\x06C'*2))
    assert value['payload_matches'] is False
    assert value['emac_log_markers']==1 and value['ack_bytes']==4
    assert value['other_bytes']>0 and value['printable_other_bytes']==value['other_bytes']
    assert 'private text' not in json.dumps(value)


@pytest.mark.parametrize('data',[
    b'',(RUN+'_BEGIN:').encode()+b'\x06C'*4,
    frame(b'\x06C'*4)+((':'+RUN+'_END').encode()),
    (RUN+'_BEGIN:').encode()+frame(b'\x06C'*4),
    (':'+RUN+'_END'+RUN+'_BEGIN:').encode(),
])
def test_incomplete_duplicate_and_reversed_markers_are_rejected(data):
    assert parse(data)=='REFUSED'


@pytest.mark.parametrize('size,run',[(0,RUN),(7,RUN),(32770,RUN),(8,"bad';command")])
def test_parser_bounds_are_checked(size,run):
    assert parse(frame(b'\x06C'*4),size,run)=='REFUSED'


@pytest.mark.parametrize('shell',['powershell.exe','pwsh.exe'])
def test_default_is_file_only_dry_run(shell):
    p=subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(SCRIPT)],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert p.returncode==0,p.stderr
    v=json.loads(p.stdout)
    assert v['mode']=='dry-run' and v['uart_host_tx'] is False and v['flash'] is False and v['reboot'] is False


def test_control_flow_has_no_host_uart_writes_and_drains_before_validation():
    text=SCRIPT.read_text()
    assert '$serial.Write(' not in text and '$serial.WriteLine(' not in text
    assert '$serial.BreakState=' not in text
    assert text.index('$serial.Open()')<text.index('$process.Start()')<text.index('$serial.Read($chunk')
    assert text.index("$stage='drain_tail'")<text.index('$result.frame=Test-HgwRxFrame')
    assert text.index('Exit-F319HardwareGuard -Guard $guard')<text.index("[IO.File]::WriteAllText((Join-Path $output 'result.json')")


@pytest.mark.parametrize('failure',['none','close','dispose','sender','post','release'])
def test_cleanup_never_publishes_false_pass_or_skips_sender_containment(tmp_path,failure):
    code=functions()+f"""
$failure={quote(failure)};$output={quote(tmp_path)};$script:F323SshContainmentFailed=$false
$serialCloseFailed=$false;$eventRegistered=$false;$started=$true;$QuietConsole=$false;$stdoutTask=$null;$guard=[pscustomobject]@{{fixture=1}}
$probeSshPath='fixture';$sshArgs=@();$version='fixture';$buffer=[IO.MemoryStream]::new()
$script:calls=[Collections.Generic.List[string]]::new()
$serial=[pscustomobject]@{{IsOpen=$true}}
$serial | Add-Member ScriptMethod Close {{ $script:calls.Add('close');if($failure -eq 'close'){{throw 'close'}};$this.IsOpen=$false }}
$serial | Add-Member ScriptMethod Dispose {{ $script:calls.Add('dispose');if($failure -eq 'dispose'){{throw 'dispose'}} }}
$process=[pscustomobject]@{{fixture=1}}
$process | Add-Member ScriptMethod Dispose {{ $script:calls.Add('process-dispose') }}
function Stop-F323SshProcess {{ $script:calls.Add('sender-stop');if($failure -eq 'sender'){{$script:F323SshContainmentFailed=$true;throw 'sender'}} }}
function Invoke-F319SshScript {{ $script:calls.Add('post');if($failure -eq 'post'){{throw 'post'}};return [pscustomobject]@{{ExitCode=0;Stdout='OMRX_F321_READY'}} }}
function Exit-F319HardwareGuard {{ $script:calls.Add('release');if($failure -eq 'release'){{throw 'release'}} }}
$result=[ordered]@{{status='PASS_LINUX_UART_RX_WINDOW'}}
$try=@($ast.EndBlock.Statements | Where-Object {{$_ -is [Management.Automation.Language.TryStatementAst]}})[-1]
$cleanup=($try.Finally.Statements | ForEach-Object {{$_.Extent.Text}}) -join "`n"
. ([scriptblock]::Create($cleanup))
[pscustomobject]@{{calls=@($script:calls);result=(Get-Content -Raw -LiteralPath (Join-Path $output 'result.json') | ConvertFrom-Json)}} | ConvertTo-Json -Depth 8 -Compress
"""
    value=json.loads(ps(code)); calls=value['calls']; result=value['result']
    assert 'sender-stop' in calls and 'process-dispose' in calls
    if failure=='none':
        assert result['status']=='PASS_LINUX_UART_RX_WINDOW' and result['lease_released'] is True
    else:
        assert result['status']=='FAIL'
    if failure in {'close','dispose','sender'}:
        assert 'release' not in calls and result['helper_containment_verified'] is False
    else:
        assert 'post' in calls


@pytest.mark.parametrize('initial,fail',[('7\t4\t1\t7\n',False),('1\t4\t1\t7\n',False),('7\t4\t1\t7\n',True)])
def test_quiet_producer_restores_exact_console_values_even_on_failure(tmp_path,initial,fail):
    encoded=ps(functions()+f"$s=Get-HgwRxProducerScript -RunId {quote(RUN)} -ExpectedVersion 'lyoko-foundation-6.8.5-f321-classic-ui-f314-device' -Quiet $true; [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($s))")
    script=base64.b64decode(encoded).decode().replace('\r\n','\n')
    printk=tmp_path/'printk';console=tmp_path/'console';release=tmp_path/'release'
    printk.write_bytes(initial.encode('ascii'));release.write_bytes(b'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.8.5-f321-classic-ui-f314-device\n')
    def shell_path(p):
        return '/mnt/'+p.drive[0].lower()+'/'+p.as_posix()[3:] if os.name=='nt' else str(p)
    script=script.replace('/proc/sys/kernel/printk',shlex.quote(shell_path(printk)))
    script=script.replace('/etc/openmitrastar/release',shlex.quote(shell_path(release)))
    script=script.replace('> /dev/console','>> '+shlex.quote(shell_path(console)))
    assert '/proc/sys/' not in script and '/dev/console' not in script and '/etc/openmitrastar/' not in script
    if fail: script='\n'.join('false' if line.startswith('awk ') else line for line in script.splitlines())
    command=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh','-s'] if os.name=='nt' else ['sh','-s']
    out=subprocess.run(command,input=script.encode(),capture_output=True,timeout=15)
    assert (out.returncode!=0)==fail,out.stderr
    assert printk.read_bytes()==initial.encode('ascii')
    if not fail:
        assert console.read_bytes()==frame(b'\x06C'*16384)
        assert b'OMRX_PRINTK_BEFORE=' in out.stdout and b'OMRX_PRINTK_AFTER=' in out.stdout
