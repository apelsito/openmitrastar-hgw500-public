"""ActualGPIOinit/exit controller withfakechipregistry verifiesmoduleowner/error path."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);src=a.candidate/'source/platform/ruby/gpio.c';t=src.read_text();init=function(t,'static int __init arc_gpio_init(');exit=function(t,'static void __exit arc_gpio_exit(');assert '#ifdef MODULE\nmodule_init(arc_gpio_init);\n#else\narch_initcall(arc_gpio_init);\n#endif\nmodule_exit(arc_gpio_exit);'in t
 pre=r'''#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#define __iomem
#define __init
#define __exit
#define GPIO_MAX 32
#define RUBY_GPIO_REGS_ADDR 0xf2000000U
static int owner;
#define THIS_MODULE (&owner)
struct gpio_chip{const char*label;void*owner;int(*direction_input)(struct gpio_chip*,unsigned);int(*direction_output)(struct gpio_chip*,unsigned,int);int(*set)(struct gpio_chip*,unsigned,int);int(*get)(struct gpio_chip*,unsigned);int base;unsigned ngpio;};struct arc_gpio_controller{unsigned unused;};struct arc_7XX_gpio{struct gpio_chip chip;struct arc_gpio_controller*regs;};static struct arc_7XX_gpio arc_gpio;
static int arc_gpio_dir_in(struct gpio_chip*c,unsigned i){(void)c;(void)i;return 0;}static int arc_gpio_dir_out(struct gpio_chip*c,unsigned i,int v){(void)c;(void)i;(void)v;return 0;}static int arc_gpio_set(struct gpio_chip*c,unsigned i,int v){(void)c;(void)i;(void)v;return 0;}static int arc_gpio_get(struct gpio_chip*c,unsigned i){(void)c;(void)i;return 0;}
static int addrc,added,removed;static struct gpio_chip*registered;
static int gpiochip_add_data(struct gpio_chip*c,void*d){assert(c->owner==THIS_MODULE&&d==&arc_gpio&&c->ngpio==32&&c->base==0);assert(c->set==arc_gpio_set&&c->get==arc_gpio_get);added++;if(addrc)return addrc;registered=c;return 0;}
static void gpiochip_remove(struct gpio_chip*c){assert(registered==c);registered=NULL;removed++;}
'''
 test=r'''int main(void){int rc[]={-12,-22,-16,0};unsigned cases=0;for(unsigned i=0;i<4;i++){addrc=rc[i];added=removed=0;registered=NULL;assert(arc_gpio_init()==rc[i]&&added==1&&arc_gpio.chip.owner==THIS_MODULE);if(!rc[i]){arc_gpio_exit();assert(!registered&&removed==1);}else assert(!registered&&!removed);cases++;}printf("{\"actual_GPIO_init_exit_cases\":%u}\n",cases);return 0;}
''';f=a.output/'actual-gpio-init-exit.c';f.write_text(pre+init+exit+test);compiler=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/clang.exe';r=subprocess.run([str(compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);pins={str(p):sha(p)for p in[Path(__file__),src,compiler,f,a.output/'fixture.exe']};r={'status':'PASS_R20_ACTUAL_GPIO_MODULE_OWNER_REGISTRATION_REFUSAL_AND_EXIT_CONTROLLER','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':pins,'limits':'Actualinit/exit bodies; fakegpiolibregistry noMMIO. Ownerselection/errorpropagation/exit checked; kernelGPIOrequest/liveunloadnotexecuted.'};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
