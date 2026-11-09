"""Seal conditional host->MuC TQE->AuC management admission evidence, offline."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from seal_rbs_mailbox_fullmap_search import dossier, sha, ROOT, MUC_SHA, MAP_SHA

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    args.output.mkdir(parents=True)
    mapdir = ROOT/'outputs/rea/rbs-muc-loaded-segments-20261023T004700Z-r1'
    source = ROOT/'work/rc1-radio-drivers-20260824-extract/openmitrastar-linux510-radio-drivers-product-rc1-20260824/radio5g/firmware/qtn_driver.qtn_ruby.0.bin'
    elf = mapdir/'muc-LOADED-SEGMENTS-ANALYSIS_ONLY.elf'
    assert sha(source)==MUC_SHA and sha(elf)==MAP_SHA
    pins = {}
    def pin(path):
        pins[str(path)] = sha(path)
    for path in (source,elf,mapdir/'result.json',mapdir/'muc-all-payload-disassembly.txt',Path(__file__),ROOT/'tools/seal_rbs_mailbox_fullmap_search.py',ROOT/'outputs/rea/rbs-muc-mailbox-fullmap-bounded-audit-20261023T012000Z-r1/result.json'):
        pin(path)
    queries = {
        'actual_tasklet_registration': ('rbs-muc-actual-tasklet-registration-20261023T013000Z-r1','0xe83ec',160),
        'real_tqe_management_ingress': ('rbs-muc-real-tqe-mgmt-ingress-20261023T013300Z-r1','0x159eb8',164),
        'real_management_producer': ('rbs-muc-real-mgmt-producer-20261023T013600Z-r1','0x155ec8',1252),
        'tqe_tasklet5_registration': ('rbs-muc-tqe-ingress-registration-20261023T013900Z-r1','0x15696c',202),
        'management_fcs_constructor': ('rbs-muc-real-mgmt-fcs-builder-20261023T014200Z-r1','0x12d3c8',1530),
        'ocs_suspend_command21': ('rbs-muc-ocs-suspend-command21-20261023T014200Z-r1','0x156550',16),
    }
    functions = {}
    for key,(dirname,address,size) in queries.items():
        directory = ROOT/'outputs/rea'/dirname
        receipt = json.loads((directory/'result.json').read_text())
        assert receipt['exit_code']==0 and receipt['target_unchanged']
        assert receipt['target_sha256']==MAP_SHA and sha(directory/'rea.json')==receipt['rea_output_sha256']
        function = dossier(directory/'rea.json')
        assert function['procedure']['address']==address and function['procedure']['body']['total_bytes']==size
        pseudocode = args.output/(key+'.pseudocode.c')
        pseudocode.write_text(function['pseudocode'])
        summary = {
            'source_directory': str(directory.relative_to(ROOT)), 'procedure': function['procedure'],
            'callees': [{'address': item['address'],'name': item['name']} for item in function.get('callees',[])],
            'callers': [{'address': item['address'],'name': item['name']} for item in function.get('callers',[])],
            'limitations': function.get('limitations',[]),
            'pseudocode_sha256': sha(pseudocode), 'rea_sha256': receipt['rea_output_sha256'],
            'started_utc': receipt['started_utc'], 'finished_utc': receipt['finished_utc'],
        }
        (args.output/(key+'.dossier.json')).write_text(json.dumps(summary,indent=2)+'\n')
        functions[key]=summary
        pin(directory/'rea.json');pin(directory/'result.json')
    assert 'qtn_auc_tqe_mgmt_xmit' in (args.output/'real_management_producer.pseudocode.c').read_text()
    assert '0x15,param_1,0,0,1' in (args.output/'ocs_suspend_command21.pseudocode.c').read_text()
    r24=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver/src/linux-7.3-r24'
    r20=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver/src/linux-7.3-r20'
    hostpaths={'r24_tx':r24/'source/qdrv/qdrv_tx.c','r24_wlan':r24/'source/qdrv/qdrv_wlan.c','r24_wlan_h':r24/'source/qdrv/qdrv_wlan.h','r20_rbs':r20/'source/wlan/openmitrastar_rbsdfs_kernel.inc'}
    for path in hostpaths.values():pin(path)
    assert 's->provider=NULL;' in hostpaths['r20_rbs'].read_text()
    assert 'qdrv_hostlink_xmitctl' not in hostpaths['r20_rbs'].read_text()
    tx=hostpaths['r24_tx'].read_text();wlan=hostpaths['r24_wlan'].read_text()
    assert 'return qdrv_tx_to_auc(qv, skb);' in tx and 'port = TOPAZ_TQE_MUC_PORT;' in tx
    assert 'qw->flags_ext |= QDRV_WLAN_FLAG_AUC_TX;' in wlan
    headers=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver/vendor/port-context/include/qtn'
    params=headers/'topaz_shared_params.h';tqe=headers/'topaz_tqe_cpuif.h'
    pin(params);pin(tqe)
    text=params.read_text();block=text.split('enum shared_params_auc_ipc_cmd',1)[1].split('};',1)[0]
    command_records=[];value=-1
    for name,assigned in re.findall(r'\b(SHARED_PARAMS_IPC_[A-Z0-9_]+)\s*(?:=\s*(0x[0-9a-fA-F]+|[0-9]+))?\s*,',block):
        value=int(assigned,0) if assigned else value+1
        command_records.append({'name':name,'value':value,'conditional':name=='SHARED_PARAMS_IPC_A2M_PUSH_WMAC1_FCS'})
    assert next(item['value'] for item in command_records if item['name']=='SHARED_PARAMS_IPC_M2A_OCS_TX_SUSPEND_CMD')==21
    assert next(item['value'] for item in command_records if item['name']=='SHARED_PARAMS_IPC_M2A_FCS_GIVE_CMD')==19
    (args.output/'auc-ipc-enum-source.json').write_text(json.dumps({'source_sha256':sha(params),'authority':'GPL header definition; AuC firmware instruction consumer not qualified','commands':command_records},indent=2)+'\n')
    flags=[line.strip() for line in tqe.read_text().splitlines() if re.match(r'#define\s+TQE_MISCUSER_M2A_(?:MGMT|EVENT)',line)]
    (args.output/'m2a-management-flags-source.json').write_text(json.dumps(flags,indent=2)+'\n')
    disassembly=(mapdir/'muc-all-payload-disassembly.txt').read_text().splitlines()
    windows={'tasklet_registration':(0xe83ec,0xe848c),'tqe_registration':(0x15696c,0x156a38),'tqe_descriptor_dispatch':(0x159f5c,0x15a15c),'real_management_ingress':(0x159eb8,0x159f5c),'real_management_producer':(0x155ec8,0x1563ac),'fcs_builder':(0x12d3c8,0x12da00),'ocs_suspend_command':(0x156550,0x156560),'ocs_halt_resume_callers':(0x10cca4,0x10cd5c)}
    for key,(begin,end) in windows.items():
        lines=[]
        for line in disassembly:
            try:address=int(line.split(':',1)[0].strip(),16)
            except ValueError:continue
            if begin<=address<end:lines.append(line)
        assert lines
        (args.output/(key+'.gnu-assembly.txt')).write_text('\n'.join(lines)+'\n')
    aucs={}
    for name in ('auc_driver.default.0.bin','auc_driver.nomu.0.bin'):
        path=source.with_name(name);pin(path);aucs[name]=sha(path)
    assert aucs['auc_driver.default.0.bin']=='e1fd397ef56b061af7c91cbd422973dcfcf1382933afa226f8f428dd315f65af'
    assert aucs['auc_driver.nomu.0.bin']=='c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6'
    result={
        'status':'PASS_CONDITIONAL_REAL_TQE_MANAGEMENT_ADMISSION_CHAIN_CAC_PROVIDER_UNRESOLVED',
        'hardware_accessed':False,'firmware_eligible':False,'qualified_ops_added':0,'adapter_added':False,
        'muc_sha256':MUC_SHA,'analysis_map_sha256':MAP_SHA,'fresh_functions':functions,
        'host_selection':{'default_source':'R24 qdrv_wlan.c8914 sets flags_ext AUC_TX bit0x20','mutable_source':'PARAM_AUC_TX4792 enables/disables flag','observed_device_state':'UNRUN; source default is not current runtime proof','nomu_relationship':'fw_no_mu is a separate carrier/config selector; nomu hash alone does not establish AUC_TX'},
        'conditional_pipeline':[
            'AUC_TX enabled: qdrv_tx_sch_enqueue_80211 -> qdrv_tx_sch_enqueue_to_node -> qdrv_tx_to_auc; management portMUC, node misc_user, TID_MGMT/WLAN; HBM packet delivered viaTQE.',
            'Firmware15696c registers tasklet5 with bottom-half159f5c and top-half15972c using actual registratione83ec; scheduler80023900 invokes stored bottom-half.',
            '159f5c pops valid16-byte TQE descriptor; AuCport7/type0 is TXfeedback, LHOSTport4 calls159eb8. Previous interpretation as feedback-only was incomplete.',
            '159eb8 accepts an HBM pool packet pointer plus length and misc_user node and calls155ec8 with args5=1,args6/7/8/9=0.',
            '155ec8 resolves node, constructs108-byte FCS via12d3c8 and emits a6-word TQEPPCTL descriptor then triggers e1035038; own diagnostic identifies qtn_auc_tqe_mgmt_xmit.',
            'NormalLHOST call sets OCS/probe flags0; builder return can set skip-retry flag but no proof of CACgrant.',
            'AUC_TX disabled: hosthardstart uses HTXD/mailbox1; its exact firmware packet consumer remains unresolved and no runtime selection asserted.',
        ],
        'node_lifetime':'Host qdrv_tx_to_auc frees the ieee80211_node ref before TQEpublication; firmware resolves sharednode. Any RBS adapter must account for this ownership and cannot assume HTXDcallback lifetime in AUC path.',
        'fcs_contract':{'constructor':'12d3c8','bytes':108,'exact_code_bytes':1530,'code_span_bytes':1592,'non_contiguous':True,'missing_range':'12d5fa..12d637 is switch table/data, not independent executable body','inputs':'MAC context/node/FCSatroundup(pkt+len)/frame/length/flags/TIDout','qualified_effects':'Subtype/protection/retry/rate/node fields; returnfeedsSKIP_RATE_RETRY1; no exactCAC authorization contract established'},
        'AuC_IPC':{'transport':'1563ac synchronous20-byte cmd,arg1,arg2,arg3,ret via18c260/e0000178; commandcleared signifies IPCdone, notRFsuccess','ocs_wrapper':'156550(16bytes) invokescmd21 boolarg1, arg2/arg3zero, irq1','ocs_scope':'10cca4/10cd00 halt/resume callers also change netdevmask/state40b4; noframeidentity/deadline in wrapper','fcs_give':'sourceenumcmd19; firmware/AuC acceptance semantics unqualified','carrier_hashes':aucs,'instruction_analysis':'AuC default and nomu both UNRUN in this lane'},
        'remaining_required':['ExactselectedAuC instructionconsumer of M2AmanagementPPCTL/FCS and OCSsuspendcmd21','Frame-boundCACgrant identity/role/channel/deadline, revoke andcompletion','Actualmailbox1consumer for AUC_TXdisabled path','CurrentdeviceAUC_TX/capability observation requires separate authorization; not requested in this offline lane'],
        'limits':['GNUaddressedassembly establishes write ordering; Ghidrapseudocode reordersMMIOassignments and alone is not an operational model','Labels drift: actualqtn_auc_tqe_mgmt_xmit155ec8 contradicts oldsymboltable1563ac; oldreceipt retained with corrected interpretation','Segment3paddr46e004 preserved; no80020000overlay, virtualaliases declarednotruntimeproved','No completeops promotion and no R24source edits; no exactframeprovider created','AllsixREA handles collected beforeseal; no job active'],
    }
    assert all(sha(path)==digest for path,digest in pins.items())
    (args.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'result_sha256':sha(args.output/'result.json'),'input_pins_sha256':sha(args.output/'input-pins.json'),'fresh_queries':len(functions),'qualified_ops_added':0}))

if __name__=='__main__':main()
