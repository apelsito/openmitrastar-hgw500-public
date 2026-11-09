"""Prepare immutable minimalweather delta atopMDIDr3; source37 neverqualclaim."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'tools/prepare_hgw5g_weather478_source.py').read_text()
s=s.replace("p.add_argument('--output',type=Path,required=True);a=","p.add_argument('--weather-qualification',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=",1)
s=s.replace("assert proof['source_original_records']==32","assert proof['source_original_records']==35 and proof['revision']=='r3';weather=json.loads(a.weather_qualification.read_text());assert weather['status']=='PASS_OFFLINE_WEATHER478_SOURCE34_BOOLEAN_AP_SELECTION_SEVEN_MODULE_CLOSURE'",1)
s=s.replace("'source_original_records':34","'source_original_records':37")
s=s.replace("'qualified_combined_records':None","'qualified_combined_records':None,'weather_qualification':str(a.weather_qualification),'weather_qualification_sha256':sha(a.weather_qualification),'mdid35_qualification_pending':True,'bounded467_included':False,'expected_private_table_records':603")
s=s.replace('SOURCE_ONLY_WEATHER478_BOOLEAN_AP_SELECTION_PENDING_MODULE_GATES','SOURCE_ONLY_MDID35_R3_PLUS_WEATHER478_37_RECORDS_PENDING_FULL_GATES')
t=ROOT/'tools/prepare_hgw5g_weather478_mdid37_source.py';assert not t.exists();t.write_text(s,newline='\n')
