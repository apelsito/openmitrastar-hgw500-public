"""Actual7.3CONFIG_I2C absent: optionalbusdeclguards andGPIOexportmodernAPI."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
CODE=r'''
/* Preserve optionalexternalI2Csensorunavailability when kernelbusisabsent.
 * These guards do not emulate a sensor or report thermal acceptance. */
#if !IS_ENABLED(CONFIG_I2C)
static inline struct i2c_adapter *om73_i2c_get_adapter(int nr){(void)nr;return NULL;}
static inline void om73_i2c_put_adapter(struct i2c_adapter *a){(void)a;}
static inline struct i2c_client *om73_i2c_new_client_device(struct i2c_adapter *a,const struct i2c_board_info *i){(void)a;(void)i;return ERR_PTR(-EOPNOTSUPP);}
static inline void om73_i2c_unregister_device(struct i2c_client *c){(void)c;}
#define i2c_get_adapter om73_i2c_get_adapter
#define i2c_put_adapter om73_i2c_put_adapter
#define i2c_new_client_device om73_i2c_new_client_device
#define i2c_unregister_device om73_i2c_unregister_device
#endif
static inline int om73_gpio_export(unsigned gpio,bool direction_may_change)
{
    struct gpio_desc *desc=gpio_to_desc(gpio);
    if(!desc)return -ENODEV;
    return gpiod_export(desc,direction_may_change);
}
#define gpio_export om73_gpio_export
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();shutil.copytree(a.parent,a.output);f=a.output/'source/qdrv/compat/include/openmitrastar_qdrv_compat.h';t=f.read_text();t=t.replace('#include <linux/fs.h>','#include <linux/fs.h>\n#include <linux/i2c.h>\n#include <linux/gpio.h>\n#include <linux/gpio/consumer.h>',1);idx=t.rfind('#endif');t=t[:idx]+CODE+t[idx:];f.write_text(t,newline='\n');proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_LINUX73_FULL44_OPTIONAL_I2C_AND_GPIO_API_GUARDS',parent=str(a.parent),changed_sources={'source/qdrv/compat/include/openmitrastar_qdrv_compat.h':sha(f)});proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'changed_sources':proof['changed_sources']},indent=2))
if __name__=='__main__':main()
