"""FreezeR3actualkernelbridgefixture withF355order andexplicitnodecompletion."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'tools/test_hgw5g_rbsdfs_kernel_bridge.py').read_text()
s=s.replace('static unsigned finds,equalities,statusreads;','static unsigned claims,node_frees;static int claim_result;\nstatic int om_qdrv_rbsdfs_claim_lifetime(const char*name){assert(locks==1);claims++;return claim_result;}\nstatic void ieee80211_free_node(struct ieee80211_node*ni){assert(!locks&&ni->refs);ni->refs--;node_frees++;}\nstatic unsigned finds,equalities,statusreads;')
s=s.replace('f->opened++;f->role','assert(claims);f->opened++;f->role')
s=s.replace('f->granted++;return','assert(claims>=2);f->granted++;return')
s=s.replace('static void setup(struct ieee80211com*ic){memset','static void setup(struct ieee80211com*ic){claims=node_frees=0;claim_result=0;memset')
s=s.replace('fake.grant=grant;fake.send=send;fake.revoke=revoke;int rc=','fake.grant=grant;fake.send=send;fake.revoke=revoke;ni.refs=1;int rc=')
s=s.replace('if(rc==2){unsigned n=fake.granted;', 'assert(node_frees==(rc==1)&&ni.refs==(rc==1?0U:1U));if(rc==2){unsigned n=fake.granted;')
s=s.replace('setup(&ic);ic.om_rbsdfs.core.measurement_in_cac=1;assert(om_ieee80211_rbsdfs_send', 'setup(&ic);ic.om_rbsdfs.provider=&provider;ic.om_rbsdfs.core.measurement_in_cac=1;claim_result=-16;jiffies=100;assert(om_ieee80211_rbsdfs_radar(&ic,1,52)==-16&&!fake.opened&&!arms&&!ic.om_rbsdfs.core.allow_rbs_report);cases++;\nsetup(&ic);ic.om_rbsdfs.core.measurement_in_cac=1;assert(om_ieee80211_rbsdfs_send',1)
s=s.replace('PASS_SOURCE_ONLY_RBSDFS_ACTUAL_KERNEL_BRIDGE_TIMER_STOP_RESUME_FIXTURE','PASS_SOURCE_ONLY_RBSDFS_R3_ACTUAL_BRIDGE_F355_NODE_TIMER_FIXTURE')
t=ROOT/'tools/test_hgw5g_rbsdfs_kernel_r3.py';assert not t.exists();t.write_text(s,newline='\n')
