"""Local workstation inventory. Does not install, connect or inspect secrets."""
import importlib.util,json,platform,shutil,subprocess,sys
commands=['git','gh','python','node','npm','ssh','scp','wsl','make','gcc','bison','flex','bc','dtc','tar','xz']
modules=['paramiko','serial','ymodem','cryptography','bcrypt','nacl','psutil']
print(json.dumps({'host':platform.node(),'os':platform.platform(),'python':sys.version,'commands':{n:shutil.which(n)for n in commands},'python_modules':{n:importlib.util.find_spec(n)is not None for n in modules},'hardware_accessed':False},indent=2))
