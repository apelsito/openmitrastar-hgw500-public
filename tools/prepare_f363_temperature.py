"""Create the F363 temperature-only derivative, keeping F339 math immutable."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'work/kernel-port/versions/f339-topaz-hwmon'
DEST=ROOT/'work/kernel-port/versions/f363-temperature-diagnostic'
QBASE=ROOT/'work/linux510-radio-port/quantenna-f334-f321-profile'
QDEST=ROOT/'work/linux510-radio-port/quantenna-f363-temperature'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if shutil.disk_usage(ROOT).free<=500*1024*1024:raise RuntimeError('C space guard')
 if DEST.exists() or QDEST.exists():raise ValueError('F363 sources already exist')
 proof=json.loads((ROOT/'outputs/kernel-port/f339-hwmon-qualified-20260921T134348Z/result.json').read_text())
 for n in ('temp_sens.c','topaz_temp_core.h','Makefile','qdrv-consumer-error.patch'):
  p=OLD/n
  if sha(p)!=proof['source_pins'][str(p)]:raise ValueError('F339 source changed '+n)
 DEST.mkdir(parents=True);shutil.copytree(QBASE,QDEST)
 for n in ('topaz_temp_core.h','Makefile'):(DEST/n).write_bytes((OLD/n).read_bytes())
 s=(OLD/'temp_sens.c').read_text()
 s=s.replace('#include <linux/delay.h>','#include <linux/delay.h>\n#include <linux/capability.h>')
 s=s.replace('struct topaz_sensor {void __iomem *regs;struct f339_temp_io io;};','struct topaz_sensor {void __iomem *regs;struct f339_temp_io io;bool activation_attempted;int activation_error;};')
 s=s.replace('static struct topaz_sensor *active_sensor;','static struct topaz_sensor *active_sensor;\nstatic struct topaz_sensor *registered_sensor;')
 anchor='static DEVICE_ATTR_RO(interval);'
 extra='''
/* F363 exposes experimental activation, not a claim of clock qualification.
 * Probe/reservation and all status attributes perform zero sensor MMIO. */
static ssize_t enabled_show(struct device *dev,struct device_attribute *attr,char *buf)
{
 struct topaz_sensor *sensor=dev_get_drvdata(dev);int n;(void)attr;
 mutex_lock(&sensor_lock);n=scnprintf(buf,PAGE_SIZE,"%u\\n",active_sensor==sensor);mutex_unlock(&sensor_lock);return n;
}
static ssize_t activation_attempted_show(struct device *dev,struct device_attribute *attr,char *buf)
{
 struct topaz_sensor *sensor=dev_get_drvdata(dev);int n;(void)attr;
 mutex_lock(&sensor_lock);n=scnprintf(buf,PAGE_SIZE,"%u\\n",sensor->activation_attempted);mutex_unlock(&sensor_lock);return n;
}
static ssize_t activation_error_show(struct device *dev,struct device_attribute *attr,char *buf)
{
 struct topaz_sensor *sensor=dev_get_drvdata(dev);int n;(void)attr;
 mutex_lock(&sensor_lock);n=scnprintf(buf,PAGE_SIZE,"%d\\n",sensor->activation_error);mutex_unlock(&sensor_lock);return n;
}
static ssize_t experimental_enable_store(struct device *dev,struct device_attribute *attr,const char *buf,size_t count)
{
 struct topaz_sensor *sensor=dev_get_drvdata(dev);unsigned value;int ret;(void)attr;
 if(!capable(CAP_SYS_RAWIO))return -EPERM;
 if(kstrtouint(buf,10,&value)||value!=1)return -EINVAL;
 mutex_lock(&sensor_lock);
 if(registered_sensor!=sensor){ret=-ENODEV;goto out;}
 if(sensor->activation_attempted){ret=-EALREADY;goto out;}
 sensor->activation_attempted=true;
 ret=f339_temp_start(&sensor->io);sensor->activation_error=ret;
 if(!ret)active_sensor=sensor;
out:
 mutex_unlock(&sensor_lock);return ret?ret:(ssize_t)count;
}
static DEVICE_ATTR_RO(enabled);
static DEVICE_ATTR_RO(activation_attempted);
static DEVICE_ATTR_RO(activation_error);
static DEVICE_ATTR_WO(experimental_enable);
'''
 s=s.replace(anchor,anchor+'\n'+extra)
 s=s.replace('static struct attribute *sensor_attrs[]={&dev_attr_interval.attr,NULL};','static struct attribute *sensor_attrs[]={&dev_attr_interval.attr,&dev_attr_enabled.attr,&dev_attr_activation_attempted.attr,&dev_attr_activation_error.attr,&dev_attr_experimental_enable.attr,NULL};')
 start=s.index(' /* Default DT is disabled.');end=s.index(' resource=platform_get_resource',start)
 s=s[:start]+''' /* The property identifies the source-reviewed experimental interface.
  * It deliberately does not claim a measured clock or sensor acceptance. */
 if(!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")||
    !of_property_read_bool(dev->of_node,"openmitrastar,experimental-temperature-control"))return -EPERM;
'''+s[end:]
 s=s.replace('if(active_sensor){mutex_unlock(&sensor_lock);return -EBUSY;}\n ret=f339_temp_start(&sensor->io);if(!ret)active_sensor=sensor;\n mutex_unlock(&sensor_lock);if(ret)return ret;','if(registered_sensor){mutex_unlock(&sensor_lock);return -EBUSY;}\n sensor->activation_error=-ENODEV;registered_sensor=sensor;\n mutex_unlock(&sensor_lock);')
 s=s.replace('struct device *hwmon;int ret;','struct device *hwmon;')
 s=s.replace('if(IS_ERR(hwmon)){mutex_lock(&sensor_lock);active_sensor=NULL;mutex_unlock(&sensor_lock);return PTR_ERR(hwmon);}','if(IS_ERR(hwmon)){mutex_lock(&sensor_lock);if(active_sensor==sensor)active_sensor=NULL;if(registered_sensor==sensor)registered_sensor=NULL;mutex_unlock(&sensor_lock);return PTR_ERR(hwmon);}')
 s=s.replace('if(active_sensor==platform_get_drvdata(pdev))active_sensor=NULL;','if(active_sensor==platform_get_drvdata(pdev))active_sensor=NULL;if(registered_sensor==platform_get_drvdata(pdev))registered_sensor=NULL;')
 s=s.replace('MODULE_DESCRIPTION("Topaz internal temperature sensor, OEM curve, qualified opt-in");','MODULE_DESCRIPTION("Topaz F363 temperature, OEM curve, explicit experimental activation");\nMODULE_VERSION("363");')
 (DEST/'temp_sens.c').write_bytes(s.encode())
 p=QDEST/'qdrv/qdrv_wlan.c';s=p.read_text();old='''	qw->tx_power_cal_data.temp_info.temp_index = topaz_read_internal_temp_sens(&temp);
	qw->tx_power_cal_data.temp_info.real_temp = temp;
	if (p_muc_temp_index) {
		memcpy(p_muc_temp_index, &qw->tx_power_cal_data.temp_info, sizeof(*p_muc_temp_index));
	}'''
 new='''	int index;

	index = topaz_read_internal_temp_sens(&temp);
	if (index >= 0 && index < 34) {
		qw->tx_power_cal_data.temp_info.temp_index = index;
		qw->tx_power_cal_data.temp_info.real_temp = temp;
		if (p_muc_temp_index)
			memcpy(p_muc_temp_index, &qw->tx_power_cal_data.temp_info,
			       sizeof(*p_muc_temp_index));
	} else {
		pr_warn_ratelimited("Topaz internal temperature unavailable: %d\\n", index);
	}'''
 if s.count(old)!=1:raise ValueError('temperature consumer anchor')
 p.write_bytes(s.replace(old,new,1).encode())
 (DEST/'source-binding.json').write_text(json.dumps({'schema':'openmitrastar.f363-source/v1','f339_qualification':str(ROOT/'outputs/kernel-port/f339-hwmon-qualified-20260921T134348Z/result.json'),'core_sha256':sha(DEST/'topaz_temp_core.h'),'qdrv_base':str(QBASE),'qdrv_source':str(QDEST),'default_sensor_mmio':False,'physical_clock_or_sensor_qualification':False,'hardware_actions':False,'sources':{str(p):sha(p) for p in DEST.iterdir() if p.is_file()}},indent=2)+'\n')
 print(json.dumps({'source':str(DEST),'qdrv':str(QDEST),'hardware':False}))
if __name__=='__main__':main()
