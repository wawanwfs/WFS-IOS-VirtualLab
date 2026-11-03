from pathlib import Path
import os
import signal
import subprocess
import time
targets=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try: args=(p/'cmdline').read_bytes().split(b'\0')
    except (FileNotFoundError,PermissionError): continue
    if b'/usr/bin/websockify' in args or (args and args[0] == b'x11vnc'):
        targets.append(int(p.name))
for pid in targets:
    try: os.kill(pid,signal.SIGTERM)
    except ProcessLookupError: pass
time.sleep(1)
commands=[['x11vnc','-display',':99','-forever','-shared','-nopw','-localhost','-rfbport','5900','-wait','100','-defer','20'],
          ['websockify','--web','/usr/share/novnc','0.0.0.0:6080','127.0.0.1:5900']]
for name,cmd in zip(('x11vnc','novnc'),commands):
    with open('/workspace/logs/'+name+'.log','ab') as out:
        p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        print(name,p.pid,flush=True)
