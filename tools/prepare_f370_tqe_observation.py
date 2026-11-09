"""Prepare isolated F370 observation source from pinned F365 lineage; offline."""
import hashlib,json,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/linux510-radio-port/quantenna-f364-lifetime'
OUT=ROOT/'work/kernel-port/f370-tqe-observation'
PROOF=ROOT/'work/kernel-port/versions/f364-lifetime-integration/source-manifest.json'
MODULE=ROOT/'outputs/rea/arc700-20261021-r2/f365-ram-activation/r3/payload/modules/qdrv.ko'
SOURCE_SHA='2f93045dc3937074300c571e1b5f1d49c95e51de91d8e00b0742db1177438c1d'
MODULE_SHA='cfb1b5c49eba15a0b114bb695d68dce07629d9600387a26d3c65d7ae573a4b01'

DECLS='''/* F370: observation only, fixed saturating counters; no packet logs. */
static unsigned int omqdrvtx_auc_raw_ok;
static unsigned int omqdrvtx_auc_raw_other;
static unsigned int omqdrvtx_auc_busy_free;
static unsigned int omqdrvtx_auc_return_success;
module_param_named(openmitrastar_auc_raw_ok, omqdrvtx_auc_raw_ok, uint, 0444);
module_param_named(openmitrastar_auc_raw_other, omqdrvtx_auc_raw_other, uint, 0444);
module_param_named(openmitrastar_auc_busy_free, omqdrvtx_auc_busy_free, uint, 0444);
module_param_named(openmitrastar_auc_return_success, omqdrvtx_auc_return_success, uint, 0444);
static __always_inline void omqdrvtx_observe_sat(unsigned int *counter)
{
\tunsigned int value = READ_ONCE(*counter);
\tif (value != ~0U)
\t\tWRITE_ONCE(*counter, value + 1);
}
'''
OBSERVE='''#ifdef OPENMITRASTAR_QDRV_V89_PAIR
\tif (hgw_target) {
\t\tif (tqe_queued == NETDEV_TX_OK)
\t\t\tomqdrvtx_observe_sat(&omqdrvtx_auc_raw_ok);
\t\telse if (tqe_queued != NETDEV_TX_BUSY)
\t\t\tomqdrvtx_observe_sat(&omqdrvtx_auc_raw_other);
\t}
#endif
'''
BUSY='''#ifdef OPENMITRASTAR_QDRV_V89_PAIR
\t\tif (hgw_target)
\t\t\tomqdrvtx_observe_sat(&omqdrvtx_auc_busy_free);
#endif
'''
SUCCESS='''#ifdef OPENMITRASTAR_QDRV_V89_PAIR
\tif (hgw_target)
\t\tomqdrvtx_observe_sat(&omqdrvtx_auc_return_success);
#endif
'''

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def patch(old):
    anchors=['static unsigned int omqdrvtx_gso_drop_total;\n','\ttqe_queued = tqe_tx(&ctl, skb);\n','\tif (tqe_queued == NETDEV_TX_BUSY) {\n\t\tkfree_skb(skb);\n\t}\n\n\treturn NET_XMIT_SUCCESS;']
    for anchor in anchors:assert old.count(anchor)==1,'nonunique anchor'
    new=old.replace(anchors[0],anchors[0]+DECLS).replace(anchors[1],anchors[1]+OBSERVE)
    new=new.replace(anchors[2],'\tif (tqe_queued == NETDEV_TX_BUSY) {\n'+BUSY+'\t\tkfree_skb(skb);\n\t}\n\n'+SUCCESS+'\treturn NET_XMIT_SUCCESS;')
    assert strip(new)==old,'operational source changed'
    return new
def strip(new):
    for part in (DECLS,OBSERVE,BUSY,SUCCESS):
        assert new.count(part)==1,'nonunique observation delta'
        new=new.replace(part,'')
    return new
def main():
    assert not OUT.exists(),'immutable output exists'
    proof=json.loads(PROOF.read_text());assert proof['status']=='PASS_SOURCE_COMBINATION'
    assert sha(MODULE)==MODULE_SHA and sha(BASE/'qdrv/qdrv_tx.c')==SOURCE_SHA
    for name,digest in proof['source_hashes'].items():assert sha(BASE/name)==digest,name
    shutil.copytree(BASE,OUT/'source')
    path=OUT/'source/qdrv/qdrv_tx.c';old=path.read_text();new=patch(old);path.write_text(new,newline='\n')
    pins={str(p.relative_to(OUT/'source')).replace('\\','/'):sha(p) for p in (OUT/'source').rglob('*') if p.is_file()}
    result=dict(schema='openmitrastar.f370-source/v1',status='PASS_OFFLINE_OBSERVATION_SOURCE',parent='F365 exact F364 qdrv lineage',parent_module=dict(path=str(MODULE),sha256=MODULE_SHA,bytes=MODULE.stat().st_size),source_proof=dict(path=str(PROOF),sha256=sha(PROOF)),source_pins=pins,changed=['qdrv/qdrv_tx.c'],operational_source_restores_exactly=True,hardware_accessed=False,firmware_eligible=False,physical='NO_GO_PHYSICAL',limits='Counters approximate under concurrent callers; raw OK is consumption not RF delivery; no queue/backpressure fix.')
    (OUT/'source-manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_pins'}))
if __name__=='__main__':main()
