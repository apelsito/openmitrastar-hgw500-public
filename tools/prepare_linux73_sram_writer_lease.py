"""New immutable SRAM provider with process-owned writer lease; no root source edits."""
import argparse,hashlib,json,shutil
from pathlib import Path

WRITER = r'''
static int om73_writer_reentrant(void)
{
 unsigned long flags;
 bool nested;
 spin_lock_irqsave(&om73_sram_lock, flags);
 nested = om73_writer_task == current;
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 return nested ? -EBUSY : 0;
}

int om73_sram_writer_begin(unsigned int cpu, struct om73_sram_writer_token *token)
{
 unsigned long flags;
 int error;
 if (!token || cpu > 2)
  return -EINVAL;
 error = om73_writer_reentrant();
 if (error)
  return error;
 /* All three processor writers share this mutex with pool acquire/close.
  * It is held by this task through hashes, preflight, map, copy and cleanup. */
 mutex_lock(&om73_sram_lifecycle);
 if (!try_module_get(THIS_MODULE)) {
  mutex_unlock(&om73_sram_lifecycle);
  return -ENODEV;
 }
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (om73_writer_generation == U64_MAX) {
  spin_unlock_irqrestore(&om73_sram_lock, flags);
  mutex_unlock(&om73_sram_lifecycle);
  module_put(THIS_MODULE);
  return -EOVERFLOW;
 }
 token->generation = ++om73_writer_generation;
 token->cpu = cpu;
 om73_writer_token = token;
 om73_writer_task = current;
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 return 0;
}
EXPORT_SYMBOL_GPL(om73_sram_writer_begin);

static bool om73_writer_matches(const struct om73_sram_writer_token *token)
{
 return token && token == om73_writer_token && om73_writer_task == current &&
        token->generation == om73_writer_generation && token->cpu <= 2 &&
        token->cpu == om73_writer_cpu;
}

int om73_sram_writer_check(const struct om73_sram_writer_token *token,
                          phys_addr_t physical, size_t size)
{
 unsigned long flags;
 phys_addr_t end, arena_start, arena_end;
 int error = 0;
 if (!size || physical > U32_MAX || size - 1 > U32_MAX - physical)
  return -ERANGE;
 end = physical + size - 1;
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (!om73_writer_matches(token))
  error = -EPERM;
 else if (om73_state == OM73_ACTIVE) {
  arena_start = (phys_addr_t)om73_arena.cpu_base + om73_arena.start;
  arena_end = (phys_addr_t)om73_arena.cpu_base + om73_arena.end - 1;
  /* The free list itself lives here even when live_count is zero. */
  if (physical <= arena_end && end >= arena_start)
   error = -EBUSY;
 }
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 return error;
}
EXPORT_SYMBOL_GPL(om73_sram_writer_check);

int om73_sram_writer_end(struct om73_sram_writer_token *token)
{
 unsigned long flags;
 spin_lock_irqsave(&om73_sram_lock, flags);
 if (!om73_writer_matches(token)) {
  spin_unlock_irqrestore(&om73_sram_lock, flags);
  return -EPERM;
 }
 om73_writer_task = NULL;
 om73_writer_token = NULL;
 memset(token, 0, sizeof(*token));
 spin_unlock_irqrestore(&om73_sram_lock, flags);
 mutex_unlock(&om73_sram_lifecycle);
 module_put(THIS_MODULE);
 return 0;
}
EXPORT_SYMBOL_GPL(om73_sram_writer_end);
'''

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output)
 header=a.output/'om73_sram_backend.h';text=header.read_text();anchor='int om73_sram_acquire(';pos=text.index(anchor);text=text[:pos]+'''/* Writer begin/end must run in one process task. A successful begin holds the
 * lifecycle mutex until the same task ends the exact token. Stack token identity
 * and a monotonic generation are verified; copied/stale/foreign tokens refuse.
 * check only fences the active pool span; loader bounds and carrier hashes are
 * separate mandatory checks. No active pool still requires writer serialization.
 */
struct om73_sram_writer_token { u64 generation; u32 cpu; };
int om73_sram_writer_begin(unsigned int cpu, struct om73_sram_writer_token *token);
int om73_sram_writer_check(const struct om73_sram_writer_token *token,
                          phys_addr_t physical, size_t size);
int om73_sram_writer_end(struct om73_sram_writer_token *token);
'''+text[pos:];header.write_text(text,newline='\n')
 source=a.output/'om73_sram_backend.c';text=source.read_text();text=text.replace('#include <linux/spinlock.h>','#include <linux/spinlock.h>\n#include <linux/sched.h>',1)
 anchor='static u32 om73_generation;';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'''
static struct om73_sram_writer_token *om73_writer_token;
static struct task_struct *om73_writer_task;
static u64 om73_writer_generation;
static u32 om73_writer_cpu;
static int om73_writer_reentrant(void);
''',1)
 old=' error = om73_validate_board(board);';assert text.count(old)==1;text=text.replace(old,''' error = om73_writer_reentrant();
 if (error)
  return error;
'''+old,1)
 old=' int error;\n mutex_lock(&om73_sram_lifecycle);';assert text.count(old)==1;text=text.replace(old,''' int error;
 error = om73_writer_reentrant();
 if (error)
  return error;
 mutex_lock(&om73_sram_lifecycle);''',1)
 writer=WRITER.replace(' token->cpu = cpu;', ' token->cpu = cpu;\n om73_writer_cpu = cpu;')
 anchor='/* Built-in provider is preferred.';assert text.count(anchor)==1;text=text.replace(anchor,writer+'\n'+anchor,1);source.write_text(text,newline='\n')
 proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_SRAM73_WRITER_LEASE_PENDING_ARC_FIXTURES',parent=str(a.parent),board_registration_present=False,hardware_accessed=False,firmware_eligible=False,writer_changes=['Shared lifecycle mutex held by one task/token through complete firmware operation','Token pointer plus u64 generation/cpu/current task checked before end unlock','Active pool entire span protected even with no allocations; allocation/free remain irqsave and nonblocking','Closed-pool writers pin provider lifetime; same-task lifecycle recursion refuses'],source_files={p.name:sha(p)for p in a.output.iterdir()if p.is_file()and p.name!='result.json'});(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'source_files':proof['source_files']},indent=2))
if __name__=='__main__':main()
