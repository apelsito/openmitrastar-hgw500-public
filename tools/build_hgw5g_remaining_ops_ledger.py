"""Create evidence ledger for every missing OEM private entry, metadata only."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

# Symbolic field names below are forensic identifiers, not port offset claims.
DETAILS = {
246:dict(kind='source_alias',set='existingTXMAXMPDU setter withVHTsizevalidation',get='existingiv_tx_max_amsdu byte',dependency='Twoaliases completeWLANmodulequalified separately'),
275:dict(kind='existing_named_field',get='ic.auto_cca_enable u8',dependency='Seven-entrySOURCE/fixture recovered; fullpairqualification separate'),
331:dict(kind='existing_named_field',get='ic.cca_fix_disable u8',dependency='Seven-entrySOURCE/fixture recovered; fullpairqualification separate'),
450:dict(kind='constant_getter',get='constant70',dependency='ObservedOEMMIN_CAC_PERIOD baseline compatibility policy'),
449:dict(kind='local_bool',oem_field='ic+0x5dac:u8',set='!!value,return0',dependency='20/40coexistence consumers absent or not reconciled; requires append-only ABIstate and actual beacon/control integration'),
451:dict(kind='existing_named_field',oem_field='ic+0x5c28:u8 andic+0x9c:flags',get='role1/2 else repeaterbit0x40000=>3 else0',dependency='existingEXTENDER_ROLE283 and REPEATER38 anchor samefields; SOURCEcandidatePASSED'),
457:dict(kind='shared_prefix_and_wire',oem_field='soc_shared_params+388 pointer->{u16@0,u16@2,u8@4}',get='(value1<<16)|((value0*100/value1 &255)<<8)|enabledlow8',set='HOSTAPonly genericSET_PARAMS11 id457→MuCFUN16548c',dependency='Sharedpointeralreadyallocated/published; zero denominatorguard-EAGAIN prototypePASSED; setter needsMuCtimer/monitor lifecycle evidence'),
460:dict(kind='existing_named_field',oem_field='ic+0x4df1:u8',set='low8value,return0,noQDRVcommand',get='u8',dependency='OEMexportedget_max_system_bw reads samebyte; portfunctionnamesic_max_system_bw; SOURCEcandidatePASSED'),
461:dict(kind='local_u8',oem_field='ic+0x4df0:u8',set='low8value,return0',get='u8',dependency='Portretainedic_max_system_bw adjacentlayout differs; newfieldnotidentified; preserveconsumersbeforeextension'),
463:dict(kind='wire_forwarding',oem_field='noneinWLAN',set='genericSET_PARAMS11 id463→MuCFUN11f01c',dependency='76Bpayload exact; signed/range/changedMuChardwareeffectsneedfunctionanalysis'),
464:dict(kind='existing_named_field',oem_field='ic+0x4e2c:u32',set='value,return0',dependency='ExactOEMexportcleanup_before_reload clears4e2c andcurrentequivalentclearsic_chan_is_set; SOURCEcandidate andhostfixturePASS, ARCcompileblockedWSL'),
465:dict(kind='faithful_unsupported',set='-EOPNOTSUPP default',dependency='NoimplementationinexactOEM; SOURCEstubPASSED'),
466:dict(kind='local_bool',oem_field='ic+0x5d88:u8',set='!!value,return0',get='u8',dependency='RBSspecificstateabsent; mustnotmaptoSTAstrictfieldwithdifferentvalidation'),
467:dict(kind='indirect_callback',oem_field='ic+0x54a0:functionptr→QDRV.text+0x2740c',get='refresh_scan_module_chan_list(ic),pickchannel(ic,0x130000)→1 or-95',dependency='Portcallbackic_dfs_chans_available_for_cac hasdifferentbool/sideeffects; missingrefreshexport/source, noequivalence'),
468:dict(kind='local_u32_validated',oem_field='ic+0x5da8:u32',set='1..1000 inclusive else-EINVAL',get='u32',dependency='RBSclosingtimefieldabsent; OEMinit500, STAtimefielddifferentcontract'),
478:dict(kind='local_bool',oem_field='ic+0xbf4:u8',set='!!value,return0',get='u8',dependency='WeatherCACpolicyfieldabsent; consumerrecovery/regulatorygate required'),
481:dict(kind='local_u8_policy',oem_field='ic+0x4df4:u8 request,ic+0x4df5:u8 effective',set='ic_opmodeHOSTAP andvalue0..2 else-EOPNOTSUPP; storelow8',get='HOSTAP:(request&15)<<4|effective else0',dependency='Currentportlackstwofields; effectivevaluewriterneededbeforeclaimingbehavior'),
483:dict(kind='wire_and_local_bool',oem_field='ic+0x5d3d:u8',set='WLANgenericforward; QDRV!!value thenSET_PARAMS11 id483→MuCDAT18c030bool',get='WLANic_getparam→QDRVboolfield',dependency='SOURCEprivateqdrv_wlan appendbool keepsalloldoffsets; witnesses131072cases+ARCunitsPASS; fullmoduleheaderdep rebuildandMuCgatepending'),
484:dict(kind='vap_bool_and_wire',oem_field='vap+0xc55:u8',set='ifchanged:!!value,SET_PARAMS11 id484,reassoc(vap,0,1)',get='u8',dependency='Distinct11nAMSDUfieldabsent; retainediv_tx_amsdu (VAPTXAMSDU302) isdifferentfield; requiresMuCnode+0x80consumer'),
490:dict(kind='legacy_rate_algorithm',oem_field='ic+0x18 savedmode,ic+0x1c fixedflag,ic+0xbf5:rfic',set='value-1restoreor0..12 rateencoding0x7f000000|v|v<<8|v<<16; SET_PARAMS62;media/channelcallbacks',dependency='Fullspanningcontrolflow/validation andPHYmodeconsumers; avoidnaivealiasexistingfixedtxrate'),
491:dict(kind='local_u32',oem_field='ic+0x5e14:u32',set='value,return0',get='u32',dependency='CoCmovementstateabsent, behaviorconsumerunknown'),
492:dict(kind='local_bit_beacon',oem_field='ic+0x5e18:u32bit0',set='value==1setelseclear;beacon_update_all(ic)',get='bit0',dependency='11kneighborreport IEconsumersabsent ornotreconciled; appendhoststate + IEgenerationneeded'),
493:dict(kind='local_bit_beacon',oem_field='ic+0x5e1c:u32bit0',set='value==1setelseclear;beacon_update_all(ic)',get='bit0',dependency='BSSTMextendedcap/managementactionconsumerrecoveryneeded'),
494:dict(kind='vap_u16_callback',oem_field='vap+0xf8c:u16',set='HOSTAPonly else-EINVAL;storelow16 thenic+0x5444callback',get='u16',dependency='MDIE/FTauthsourceabsent; callbackmapsOEMbeaconupdate; cannotclaimFTsupportfromfieldsetter'),
495:dict(kind='vap_u8',oem_field='vap+0xf8e:u8',set='HOSTAPonlyelse-EINVAL;storelow8',get='-EOPNOTSUPP default',dependency='FTOverDShandlersabsent; getstubPASSED butsetterstillrequiresconsumers'),
496:dict(kind='constant_getter',get='QDRVreturn8',dependency='ExactOEMbaselinepolicyonly; seven-entrycandidatePASSEDoffline'),
497:dict(kind='constant_getter',get='QDRVreturn8',dependency='ExactOEMbaselinepolicyonly; seven-entrycandidatePASSEDoffline'),
498:dict(kind='local_u8_and_wire',oem_field='ic+0x535c:u8',set='low8+SET_PARAMS11 id498→MuCFUN11ee48',get='u8',dependency='DupRTSstate/consumerabsent, MuChandlerhardwarecontractneeded'),
}


def main():
 p=argparse.ArgumentParser();p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 mapping=json.loads(a.map.read_text());records=[]
 for row in mapping['records']:
  details=DETAILS.get(row['cmd'],dict(kind='previous_recovery',dependency='TXMAXMPDU246andCCA331/275alreadyrecoveredsource'))
  records.append({**row,'operation_evidence':details,'classification':'PROVEN_CASE_BODY_NOT_COMPLETE_FEATURE','scope':'OFFLINE_ONLY'})
 a.output.mkdir(parents=True,exist_ok=False)
 result=dict(status='EVIDENCE_LEDGER_ALL44_NOT_COMPLETE_DRIVER',hardware_accessed=False,firmware_eligible=False,records=records,source_map_sha256=sha(a.map),constraints=['Types/offsets are exactOEMartifacts only.','SOURCEPASSandmodulePASSandphysicalPASSremainseparate.','Unknownconsumers preventfullfeatureclaim despite setter/getter reconstruction.'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=['# Missing OEM operation ledger — 22 October 2026','','ExactOEMcase mappings and source constraints. No hardware actions.','','| ID | Name | Direction | OEM evidence | Remaining requirement |','| --- | --- | --- | --- | --- |']
 for row in records:
  detail=row['operation_evidence'];sem=detail.get(row['direction'],'Notextractedhere').replace('|','\\|');dep=detail['dependency'].replace('|','\\|');lines.append(f"|{row['cmd']}|{row['name']}|{row['direction']}|{sem}|{dep}|")
 (a.output/'LEDGER.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps(dict(status=result['status'],rows=len(records))))


if __name__=='__main__':main()
