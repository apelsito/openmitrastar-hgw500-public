"""Software reset admission without hardware writes or heap retirement."""
import argparse,hashlib,json,shutil
from pathlib import Path

RESET = r'''
int om73_sram_reset_begin(u32 mask, struct om73_sram_reset_token *token)
{
 unsigned long flags;
 u32 i;
 int error;
 if (!token || mask != 0x4180U)
  return -EINVAL;
 error = om73_writer_reentrant();
 if (error)
  return error;
 mutex_lock(&om73_sram_lifecycle);
 if (!try_module_get(THIS_MODULE)) {
  mutex_unlock(&om73_sram_lifecycle);
  return -ENODEV;
 }
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (om73_core.live_count) {
  error = -EBUSY;
  goto refuse;
 }
 for (i = 0; i < OM_SRAM_MAX_LIVE; i++) {
  if (om73_owned[i].owner) {
   error = -EBUSY;
   goto refuse;
  }
 }
 if (om73_reset_generation == U64_MAX) {
  error = -EOVERFLOW;
  goto refuse;
 }
 token->generation = ++om73_reset_generation;
 token->mask = mask;
 om73_reset_token = token;
 om73_reset_task = current;
 /* Pool mappings and core metadata are retained. This latch blocks software
  * allocation until end; it does not prove any hardware queue is quiescent. */
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 return 0;
refuse:
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 mutex_unlock(&om73_sram_lifecycle);
 module_put(THIS_MODULE);
 return error;
}
EXPORT_SYMBOL_GPL(om73_sram_reset_begin);

int om73_sram_reset_end(struct om73_sram_reset_token *token)
{
 unsigned long flags;
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (!token || token != om73_reset_token || om73_reset_task != current ||
     token->generation != om73_reset_generation || token->mask != 0x4180U) {
  spin_unlock_irqrestore(&om73_sram_lock, flags);
  return -EPERM;
 }
 om73_reset_token = NULL;
 om73_reset_task = NULL;
 memset(token, 0, sizeof(*token));
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 mutex_unlock(&om73_sram_lifecycle);
 module_put(THIS_MODULE);
 return 0;
}
EXPORT_SYMBOL_GPL(om73_sram_reset_end);
'''

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output)
 h=a.output/'om73_sram_backend.h';t=h.read_text();anchor='int om73_sram_acquire(';pos=t.index(anchor);t=t[:pos]+'''/* Software admission for the selected NETSS/MAC/BB reset mask only.
 * This proves no hardware DMA/queue quiescence and never clears/reinitializes
 * the heap. Reject before driver lifetime/core promotion or hardware writes.
 */
struct om73_sram_reset_token { u64 generation; u32 mask; };
int om73_sram_reset_begin(u32 mask, struct om73_sram_reset_token *token);
int om73_sram_reset_end(struct om73_sram_reset_token *token);
'''+t[pos:];h.write_text(t,newline='\n')
 f=a.output/'om73_sram_backend.c';t=f.read_text();anchor='static u32 om73_writer_cpu;';assert t.count(anchor)==1;t=t.replace(anchor,anchor+'''
static struct om73_sram_reset_token *om73_reset_token;
static struct task_struct *om73_reset_task;
static u64 om73_reset_generation;
''',1);old=' nested = om73_writer_task == current;';assert t.count(old)==1;t=t.replace(old,' nested = om73_writer_task == current || om73_reset_task == current;',1)
 old=' if (om73_state != OM73_ACTIVE) {\n  error = -ENODEV;\n  goto done;\n }';assert t.count(old)==1;t=t.replace(old,''' if (om73_reset_task) {
  error = -EBUSY;
  goto done;
 }
'''+old,1)
 old=' if (om73_state != OM73_ACTIVE)\n  error = -ENODEV;';assert t.count(old)==2;t=t.replace(old,' if (om73_reset_task)\n  error = -EBUSY;\n else if (om73_state != OM73_ACTIVE)\n  error = -ENODEV;')
 anchor='/* Built-in provider is preferred.';assert t.count(anchor)==1;t=t.replace(anchor,RESET+'\n'+anchor,1);f.write_text(t,newline='\n')
 r=json.loads((a.parent/'result.json').read_text());r.update(status='SOURCE_ONLY_SRAM73_EXACT_MASK_RESET_LEASE_PENDING_ARC_FIXTURE',parent=str(a.parent),hardware_accessed=False,firmware_eligible=False,reset_scope={'mask':'0x4180','hardware_quiescence_proved':False,'live_pool_owners':'REFUSE_EBUSY','heap_reinitialization':False,'alloc_free_query_during_reset':'REFUSE_EBUSY','admission_before_driver_phase_required':True},source_files={p.name:sha(p)for p in a.output.iterdir()if p.is_file()and p.name!='result.json'});(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'source_files':r['source_files']},indent=2))
if __name__=='__main__':main()
