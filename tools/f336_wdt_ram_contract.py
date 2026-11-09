"""File-only F336 contracts: exact F321 DT, WDT ownership and RAM envelope."""
from pathlib import Path
import copy,hashlib,struct
from dtb_find_nodes import parse as parse_dtb
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
F321=DEVICE/'firmware/f321-f314-device-bound'
F321_BASE='openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
F329=ROOT/'outputs/kernel-port/f329-watchdog-20260921T101516Z'
F329_SOURCE=ROOT/'work/kernel-port/versions/f329-watchdog'
MARKER=b'F336_WDT_RAM_ONLY\0'
STAGING=0x83000000
CRC_SCRATCH=0x84000000
LOAD=0x8493a000
ENTRY=0x8493e000
DDR_END=0x88000000
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)
def cells(*values):return struct.pack('>'+'I'*len(values),*values)
def node_map(path):return {n['path']:dict(n['props']) for n in parse_dtb(Path(path))}
def reservations(blob):
    pos=struct.unpack_from('>I',blob,16)[0];start=pos
    for _ in range(64):
        address,size=struct.unpack_from('>QQ',blob,pos);pos+=16
        if not address and not size:return blob[start:pos]
    raise ValueError('unterminated DT reservations')
def serialize(nodes,old_blob):
    strings=bytearray();offsets={};body=bytearray();by_path={n['path']:n for n in nodes}
    children={p:[] for p in by_path}
    for n in nodes:
        if n['path']=='/':continue
        parent=n['path'].rsplit('/',1)[0] or '/';children[parent].append(n['path'])
    def emit(path):
        n=by_path[path];body.extend(cells(1));body.extend(('' if path=='/' else n['name']).encode()+b'\0')
        while len(body)%4:body.append(0)
        for key,value in n['props']:
            if key not in offsets:offsets[key]=len(strings);strings.extend(key.encode()+b'\0')
            body.extend(cells(3,len(value),offsets[key]));body.extend(value)
            while len(body)%4:body.append(0)
        for child in children[path]:emit(child)
        body.extend(cells(2))
    emit('/');body.extend(cells(9));reserve=reservations(old_blob);offset=40+len(reserve)
    bootcpu=struct.unpack_from('>I',old_blob,28)[0]
    header=cells(0xd00dfeed,offset+len(body)+len(strings),offset,offset+len(body),40,17,16,bootcpu,len(strings),len(body))
    return header+reserve+body+strings
def make_dt(base,target):
    nodes=copy.deepcopy(parse_dtb(base));lookup={n['path']:n for n in nodes};base_map=node_map(base)
    recovery=lookup['/soc/recovery@e0000000'];props=dict(recovery['props'])
    require(props['reg']==cells(0xe0000000,0x200,0xf1000000,0x40,0xf4000000,0x20),'F321 recovery map changed')
    require(props['reg-names']==b'sysctl\0gpio\0watchdog\0','F321 recovery ownership changed')
    changes={'reg':cells(0xe0000000,0x200,0xf1000000,0x40),'reg-names':b'sysctl\0gpio\0'}
    removed={'mitrastar,product-watchdog-canary','qtn,product-watchdog-timeout-range','qtn,product-watchdog-pet-seconds'}
    recovery['props']=[(k,changes.get(k,v)) for k,v in recovery['props'] if k not in removed]
    recovery['props'].append(('quantenna,separate-watchdog',b''))
    lookup['/']['props'].append(('openmitrastar,f336-wdt-ram',MARKER))
    handles=[struct.unpack('>I',v)[0] for n in nodes for k,v in n['props'] if k=='phandle']
    handle=max(handles)+1
    nodes.append({'name':'f336-watchdog-clock','path':'/f336-watchdog-clock','props':[
        ('compatible',b'fixed-clock\0'),('#clock-cells',cells(0)),('clock-frequency',cells(125000000)),('phandle',cells(handle))]})
    nodes.append({'name':'watchdog@f4000000','path':'/soc/watchdog@f4000000','props':[
        ('compatible',b'quantenna,topaz-wdt-f329\0'),('reg',cells(0xf4000000,0x20)),('clocks',cells(handle)),
        ('clock-names',b'tclk\0'),('timeout-sec',cells(8)),('quantenna,watchdog-experiment',b''),('status',b'okay\0')]})
    target.write_bytes(serialize(nodes,base.read_bytes()));candidate=node_map(target)
    require(reservations(base.read_bytes())==reservations(target.read_bytes()),'DT reservation drift')
    for path,values in base_map.items():
        require(path in candidate,'DT removed a base node')
        for key,value in values.items():
            if path=='/soc/recovery@e0000000' and (key in changes or key in removed):continue
            require(candidate[path].get(key)==value,'unrelated DT property changed: '+path+'/'+key)
    require(candidate['/soc/flash@90960000']['reg']==cells(0x90960000,0x460000),'F321 rootfs window not exact')
    return {'base_sha256':sha(base),'candidate_sha256':sha(target),'watchdog_clock_phandle':handle,
            'unchanged_base_nodes':len(base_map),'allowed_existing_changes':['root F336 marker','recovery WDT resource separation','remove inactive canary properties'],
            'added_nodes':['/f336-watchdog-clock','/soc/watchdog@f4000000'],'rootfs_flash_read_only':True}

def driver_observation_overlay(source):
    text=source.read_text()
    require(sha(source)=='9f0498ccc2898137fd0ae09f9cccfc28b04e630abd01763429e3091eb743d6e7','F329 driver input changed')
    anchor='#define to_dw_wdt(wdd)\tcontainer_of(wdd, struct dw_wdt, wdd)\n'
    require(text.count(anchor)==1,'driver accessor anchor')
    add=r'''
/* F336 diagnostic reads use the registered owner's existing mapping. */
static unsigned int f336_probe_control = UINT_MAX;
static bool f336_probe_seen;
module_param_named(f336_probe_control, f336_probe_control, uint, 0444);
module_param_named(f336_probe_seen, f336_probe_seen, bool, 0444);
static ssize_t f336_control_show(struct device *dev,
 struct device_attribute *attr, char *buf)
{
 struct watchdog_device *wdd = dev_get_drvdata(dev);
 struct dw_wdt *wdt = watchdog_get_drvdata(wdd);
 (void)attr;
 if (!wdt->topaz) return -ENODEV;
 return scnprintf(buf, PAGE_SIZE, "%08x\n", readl(wdt->regs + WDOG_CONTROL_REG_OFFSET));
}
static DEVICE_ATTR_RO(f336_control);
static ssize_t f336_counter_show(struct device *dev,
 struct device_attribute *attr, char *buf)
{
 struct watchdog_device *wdd = dev_get_drvdata(dev);
 struct dw_wdt *wdt = watchdog_get_drvdata(wdd);
 (void)attr;
 if (!wdt->topaz) return -ENODEV;
 return scnprintf(buf, PAGE_SIZE, "%08x\n", readl(wdt->regs + WDOG_CURRENT_COUNT_REG_OFFSET));
}
static DEVICE_ATTR_RO(f336_counter);
static struct attribute *f336_attrs[] = {
 &dev_attr_f336_control.attr, &dev_attr_f336_counter.attr, NULL
};
ATTRIBUTE_GROUPS(f336);
'''
    text=text.replace(anchor,anchor+add,1)
    old='\treturn readl(dw_wdt->regs + WDOG_CONTROL_REG_OFFSET) &\n\t\tWDOG_CONTROL_REG_WDT_EN_MASK;'
    new='\tu32 control = readl(dw_wdt->regs + WDOG_CONTROL_REG_OFFSET);\n\tif (dw_wdt->topaz) {\n\t\tWRITE_ONCE(f336_probe_control, control);\n\t\tWRITE_ONCE(f336_probe_seen, true);\n\t}\n\treturn control & WDOG_CONTROL_REG_WDT_EN_MASK;'
    require(text.count(old)==1,'probe read anchor');text=text.replace(old,new,1)
    old='\twatchdog_set_drvdata(wdd, dw_wdt);'
    require(text.count(old)==1,'device groups anchor');text=text.replace(old,old+'\n\tif (topaz)\n\t\twdd->groups = f336_groups;',1)
    return text.encode()
