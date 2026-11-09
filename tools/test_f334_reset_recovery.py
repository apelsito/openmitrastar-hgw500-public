"""Fresh-reset recovery tests: real wrapper/derivative with fully mocked hardware."""
from pathlib import Path
import json
import subprocess
import tempfile

import pytest
import test_f325_ethernet_runtime as old
import f325_existing_permission_contract as permission

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'tools/f334_reset_recovery_runtime.ps1'

def ps(code):
    with tempfile.TemporaryDirectory(prefix='f334-reset-test-') as directory:
        path=Path(directory)/'fixture.ps1'
        path.write_text("$ErrorActionPreference='Stop'\n"+code,encoding='utf-8')
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(path)],cwd=ROOT,capture_output=True,text=True,timeout=60)
        assert result.returncode==0,result.stderr or result.stdout
        return json.loads(result.stdout)

def setup():return f'. {old.quote(RUNTIME)}\n'

def clean(absent=False):
    state={'boot_id':'0206117b-ccea-4543-8437-7260972115c0','version':'lyoko-foundation-6.9.5-f334-radar-once-f321-device',
           'provider_state':'absent' if absent else 'present','sysmodule_present':not absent,'procmodule_present':not absent,'procstatus_present':not absent}
    if not absent:state.update(dict.fromkeys(('once_phase','hardware_dirty','configured','shadow_arm','polling','mmio_writes'),0))
    return state

def check_state(value):
    return ps(setup()+f'$state=ConvertFrom-Json {old.quote(json.dumps(value))}\n'+r'''
$accepted=$false
try{Assert-F334CleanBoot -State $state -PreviousBootId $script:F334Origin.prearm_boot_id;$accepted=$true}catch{}
@{accepted=$accepted}|ConvertTo-Json -Compress
''')['accepted']

def test_fresh_original_failure_is_verified_from_immutable_files():
    assert ps(setup()+"Get-F334OriginalFailure|ConvertTo-Json -Compress")['status']=='PASS_ORIGINAL_FAILURE_PREWRITE'

@pytest.mark.parametrize('patch',[
    "$d.main.writer_verified=$false", "$d.main.lease_released=$false", "$d.main.helper_containment_verified=$false",
    "$d.writer.full_slot_crc32_observed='00000000'", "$d.rollback.failed_stage='write'", "$d.rollback.writer_verified=$true",
    "$d.capture.status='CAPTURE_ACTIVITY_OBSERVED'",
])
def test_fresh_restore_rejects_unproven_original_or_possible_prior_write(patch):
    code=setup()+r'''
$d=@{}
foreach($row in $script:F334Origin.files){if($row.label -ne 'uart'){$d[$row.label]=[IO.File]::ReadAllText((Join-Path $script:F325EthernetRoot $row.path))|ConvertFrom-Json}}
$d=[pscustomobject]$d
'''+patch+r'''
$accepted=$false;try{Assert-F334OriginDocuments -Documents $d;$accepted=$true}catch{}
@{accepted=$accepted}|ConvertTo-Json -Compress
'''
    assert ps(code)['accepted'] is False

def test_fresh_pristine_provider_is_accepted():assert check_state(clean())
def test_fresh_absent_provider_is_accepted_without_invented_counters():assert check_state(clean(True))

@pytest.mark.parametrize('field',['once_phase','hardware_dirty','configured','shadow_arm','polling','mmio_writes'])
def test_fresh_dirty_provider_is_rejected(field):
    value=clean();value[field]=1;assert not check_state(value)

@pytest.mark.parametrize('field,value',[('sysmodule_present',True),('procmodule_present',True),('procstatus_present',True),('provider_state','unknown')])
def test_absence_must_be_complete(field,value):
    state=clean(True);state[field]=value;assert not check_state(state)

def test_old_boot_is_not_a_reset():
    state=clean();state['boot_id']='3e771eda-f034-437e-a9ef-169b737403fe';assert not check_state(state)

def flow_setup():
    p=permission.validate_permission(permission.PERMISSION,permission.PERMISSION_SHA,python_executable=permission.PROGRAM)
    return old.setup()+setup()+old.CYCLE_MOCKS+f'''
$script:plan.network.firewall_mode='existing-permission'
$script:plan.network.existing_permission=ConvertFrom-Json {old.quote(json.dumps(p))}
$script:rollback.network.firewall_mode='existing-permission'
$script:rollback.network.existing_permission=$script:plan.network.existing_permission
$script:fresh=ConvertFrom-Json {old.quote(json.dumps(clean()))}
$script:recovery=[pscustomobject]@{{source=$script:plan;restore=$script:rollback}}
$script:fail='';$script:freshFail=''
function Get-Process {{param($Id) return $null}}
function Assert-F325ExistingPermission {{param($Plan) Record 'permission';return [pscustomobject]@{{fingerprint_sha256=$script:F325ExistingFingerprint}}}}
function Get-F334CleanBootState {{
 param($SourcePlan,$PreviousBootId) Record 'fresh-state'
 if($script:freshFail -eq 'dirty'){{throw 'F334_PROVIDER_NOT_PRISTINE'}}
 return $script:fresh
}}
function Test-F325EthernetAdministrator {{throw 'ADMIN FORBIDDEN'}}
function New-F325EthernetFirewallRule {{throw 'NEW RULE FORBIDDEN'}}
function Remove-F325EthernetFirewallRule {{throw 'REMOVE RULE FORBIDDEN'}}
'''

def run_flow(tmp_path, *, failure='', fresh_failure='', claim=False):
    claim_path=tmp_path/'claim.json'
    if claim:claim_path.write_text('{}')
    code=flow_setup()+f"$script:fail={old.quote(failure)}\n$script:freshFail={old.quote(fresh_failure)}\n"
    code+=f'''$result=Invoke-F334ResetRecovery -Plan $script:recovery -RunDir {old.quote(tmp_path)} -ClaimPath {old.quote(claim_path)}
@{{result=$result;trace=@($script:trace);claim_exists=(Test-Path -LiteralPath {old.quote(claim_path)})}}|ConvertTo-Json -Depth 8 -Compress
'''
    return ps(code)

def test_fresh_recovery_uses_new_f334_nonce_own_lease_and_one_f321_writer(tmp_path):
    report=run_flow(tmp_path)
    assert report['result']['status']=='PASS_EXACT_F321_RESTORED_AFTER_FRESH_RESET',report
    trace=report['trace']
    assert trace.count('lease')==trace.count('release')==trace.count('writer-rollback')==1
    assert trace.count('fresh-state')==2 and 'writer-promote' not in trace and 'capture' not in trace
    assert trace.index('fresh-state')<trace.index('lease')<trace.index('binding')<trace.index('writer-rollback')
    assert report['claim_exists'] and report['result']['lease_released']

def test_failed_fresh_boot_does_not_create_claim_or_touch_uart(tmp_path):
    report=run_flow(tmp_path,fresh_failure='dirty')
    assert not report['claim_exists'] and 'lease' not in report['trace'] and 'writer-rollback' not in report['trace']
    assert report['result']['status']=='STOP_NO_AUTOMATIC_RETRY'

def test_used_claim_never_restarts_recovery(tmp_path):
    report=run_flow(tmp_path,claim=True)
    assert not report['trace'] and report['result']['refusal_code']=='F334_RECOVERY_CLAIM_ALREADY_USED'

def test_uncertain_child_retains_lease_and_never_retries(tmp_path):
    report=run_flow(tmp_path,failure='loader-job')
    assert report['result']['status']=='STOP_NO_AUTOMATIC_RETRY'
    assert report['result']['retain_lease_required'] and 'release' not in report['trace']
    assert report['trace'].count('loader-rollback')==1 and 'writer-rollback' not in report['trace']

def test_writer_failure_cannot_retry_or_capture(tmp_path):
    report=run_flow(tmp_path,failure='writer')
    assert report['result']['status']=='STOP_NO_AUTOMATIC_RETRY'
    assert report['trace'].count('writer-rollback')==1 and 'writer-promote' not in report['trace'] and 'capture' not in report['trace']

def test_fresh_cycle_is_exact_derivative_and_refuses_other_directions():
    source=(ROOT/'tools/f325_ethernet_runtime.ps1').read_text()
    body=source[source.index('function Invoke-F325EthernetPhysicalCycle {'):source.index('\nfunction Invoke-F325CaptureGate {')].strip()+'\n'
    expected=body.replace('function Invoke-F325EthernetPhysicalCycle {','function Invoke-F334FreshRollbackCycle {',1).replace('Assert-F325BorrowedRecoveryGuard','Assert-F334FreshBorrowedRecoveryGuard',1)
    expected=expected.replace('    $guard=$null; $firewall=$null;',"    if($Plan.direction -cne 'rollback' -or $CaptureAndRestore){throw 'F334_ONLY_FRESH_F321_RETURN_ALLOWED'}\n    $guard=$null; $firewall=$null;",1)
    assert RUNTIME.read_text().endswith(expected)
    report=ps(flow_setup()+r'''
$accepted=$false;try{[void](Invoke-F334FreshRollbackCycle -Plan $script:plan -RunDir 'C:\NO-EFFECTS');$accepted=$true}catch{}
@{accepted=$accepted;trace=@($script:trace)}|ConvertTo-Json -Compress
''')
    assert report=={'accepted':False,'trace':[]}
