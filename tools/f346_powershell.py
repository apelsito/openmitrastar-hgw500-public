"""Use Windows PowerShell's own modules for child processes, not Core modules.
Only the child environment changes; no user/system settings are written.
"""
from pathlib import Path
import os
def executable():
    path=Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    if not path.is_file():raise RuntimeError('Windows PowerShell executable absent')
    return str(path)
def environment():
    result=dict(os.environ);modules=Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/Modules'
    if not modules.is_dir():raise RuntimeError('Windows PowerShell modules absent')
    result['PSModulePath']=str(modules)
    return result
