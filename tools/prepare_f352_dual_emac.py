"""Generate an opt-in two-port driver from the exact F340 direct-EMAC source."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c'
DEST=ROOT/'work/kernel-port/modules/f352_dual_emac'
BASE_SHA='ffa1535e9432ca06190bef23f3382650a271d74770d082b6654b76ea028fc860'
def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('F352 anchor cardinality: '+old[:70])
    return text.replace(old,new,1)
def render(text):
    text=replace(text,'#include <linux/module.h>','#include <linux/module.h>\n#include <linux/mutex.h>\n#include <linux/rtnetlink.h>\n#include "f352_contract.h"')
    text=replace(text,'struct qtn_topaz_emac {', '''struct f352_pair {
 struct device *dev;
 struct qtn_topaz_emac_port ports[2];
 struct net_device *ndev[2];
 void __iomem *sysctl_regs;
 struct mutex mdio_lock;
 spinlock_t clock_lock;
 u8 addresses[2][ETH_ALEN];
};
struct qtn_topaz_emac {''')
    text=replace(text,'\tstruct device *dev;\n\tstruct net_device *ndev;','\tstruct device *dev;\n\tstruct net_device *ndev;\n\tstruct f352_pair *pair;\n\tstruct delayed_work link_work;\n\tbool link_polling;')
    text=replace(text,'static ssize_t lyoko_emac_stats_show(struct device *dev,\n\t\t\t\t     struct device_attribute *attr, char *buf)\n{\n\tstruct net_device *ndev = dev_get_drvdata(dev);','static ssize_t qtn_emac_stats(struct net_device *ndev, char *buf)\n{')
    text=replace(text,'static DEVICE_ATTR_RO(lyoko_emac_stats);','''static ssize_t lyoko_emac_stats_show(struct device *dev,
 struct device_attribute *attr,char *buf)
{return qtn_emac_stats(dev_get_drvdata(dev),buf);}
static DEVICE_ATTR_RO(lyoko_emac_stats);
static void f352_link_work(struct work_struct *work);''')
    text=replace(text,'static int qtn_emac_mdio_read(','static int qtn_emac_mdio_read_unlocked(')
    text=replace(text,'static int qtn_emac_mdio_write(','static int qtn_emac_mdio_write_unlocked(')
    text=replace(text,'static int qtn_emac_phy_state(','''static int qtn_emac_mdio_read(struct qtn_topaz_emac *emac,u32 phy,u32 reg,u16 *value)
{
 int ret;mutex_lock(&emac->pair->mdio_lock);
 ret=qtn_emac_mdio_read_unlocked(emac,phy,reg,value);
 mutex_unlock(&emac->pair->mdio_lock);return ret;
}
static int qtn_emac_mdio_write(struct qtn_topaz_emac *emac,u32 phy,u32 reg,u16 value)
{
 int ret;mutex_lock(&emac->pair->mdio_lock);
 ret=qtn_emac_mdio_write_unlocked(emac,phy,reg,value);
 mutex_unlock(&emac->pair->mdio_lock);return ret;
}
static int qtn_emac_phy_state(''')
    start=text.index('static int qtn_emac_phy_decode(');end=text.index('static int qtn_emac_select_rescue_port(',start)
    text=text[:start]+'''static int qtn_emac_phy_decode(struct qtn_topaz_emac *emac,u32 phy,
 u32 *speed,bool *full_duplex)
{
 u16 bmcr,bmsr,adv=0,lpa=0,adv1000=0,lpa1000=0;unsigned full=0,next_speed=0;int ret;
 ret=qtn_emac_phy_state(emac,phy,&bmcr,&bmsr);if(ret)return ret;
 if((bmcr&BMCR_ANENABLE)&&(bmsr&BMSR_LSTATUS)&&(bmsr&BMSR_ANEGCOMPLETE)){
  ret=qtn_emac_mdio_read(emac,phy,MII_ADVERTISE,&adv);if(ret)return ret;
  ret=qtn_emac_mdio_read(emac,phy,MII_LPA,&lpa);if(ret)return ret;
  ret=qtn_emac_mdio_read(emac,phy,MII_CTRL1000,&adv1000);if(ret)return ret;
  ret=qtn_emac_mdio_read(emac,phy,MII_STAT1000,&lpa1000);if(ret)return ret;
 }
 ret=f352_link_decode(bmcr,bmsr,adv,lpa,adv1000,lpa1000,&next_speed,&full);
 if(!ret){*speed=next_speed;*full_duplex=!!full;}return ret;
}

'''+text[end:]
    text=replace(text,'\tu32 mask;\n\n\tif (!emac->sysctl_regs)','\tu32 mask;\n\tunsigned long flags;\n\n\tif (!emac->sysctl_regs)')
    text=replace(text,'\twritel(mask, emac->sysctl_regs + QTN_TOPAZ_SYSCTL_CTRL_MASK);','\tspin_lock_irqsave(&emac->pair->clock_lock, flags);\n\twritel(mask, emac->sysctl_regs + QTN_TOPAZ_SYSCTL_CTRL_MASK);')
    text=replace(text,'\treadl(emac->sysctl_regs + QTN_TOPAZ_SYSCTL_CTRL);','\treadl(emac->sysctl_regs + QTN_TOPAZ_SYSCTL_CTRL);\n\tspin_unlock_irqrestore(&emac->pair->clock_lock, flags);')
    text=replace(text,'\tnetif_start_queue(ndev);','\tnetif_start_queue(ndev);\n\tWRITE_ONCE(emac->link_polling, true);\n\tschedule_delayed_work(&emac->link_work, msecs_to_jiffies(500));')
    text=replace(text,'\tbool cancelled = false;\n\n\tnetif_stop_queue(ndev);','\tbool cancelled = false;\n\n\tWRITE_ONCE(emac->link_polling, false);\n\tcancel_delayed_work_sync(&emac->link_work);\n\tnetif_stop_queue(ndev);')
    start=text.index('static int qtn_emac_probe(');end=text.index('static const struct of_device_id qtn_emac_of_match[]',start)
    text=text[:start]+'#include "f352_pair.inc"\n\n'+text[end:]
    text=replace(text,'{ .compatible = "qtn,topaz-emac" }','{ .compatible = "openmitrastar,f352-dual-emac" }')
    text=replace(text,'.name = "qtn-topaz-emac"','.name = "qtn-topaz-emac-f352"')
    text=replace(text,'MODULE_DESCRIPTION("Quantenna Topaz direct EMAC RAM-rescue driver");','MODULE_DESCRIPTION("F352 HGW500 two independent direct EMAC ports, opt-in");')
    text=replace(text,' * Minimal direct-DMA driver for the Arasan EMAC in Quantenna Topaz SoCs.',' * F352 two-port derivative of the exact F340 direct-DMA driver.\n * Each port owns its own rings/IRQ/NAPI; shared MDIO is serialized.\n * This candidate is disabled until the versioned DT explicitly opts in.\n * Historical F340 behavior documented below applies to each fixed port:')
    return text
def main():
    data=SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest()!=BASE_SHA:raise ValueError('F340 source drift')
    output=DEST/'qtn-topaz-emac-f352.c';output.write_text(render(data.decode('utf-8')),encoding='utf-8',newline='\n')
    (DEST/'Makefile').write_text('obj-m += qtn-topaz-emac-f352.o\n',encoding='ascii')
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),hardware_actions=False)))
if __name__=='__main__':main()
