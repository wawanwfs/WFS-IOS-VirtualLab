from pathlib import Path
import json
import re
import datetime
log=Path('/workspace/logs/session.log').read_bytes().rsplit(b'=== WFS iOS session starting ===',1)[-1].decode(errors='replace')
lines=log.replace('\r','').splitlines()
print(json.dumps({
    'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'cpus_registered': len(set(re.findall(r'GenericARMCPU: cpu (\d+)',log))),
    'init_passed': '=== 36 checks, 0 failed ===' in log,
    'service_results': re.findall(r'svc_test: \d+ failed',log),
    'surface_results': re.findall(r'surf_test: 80 checks, \d+ failed',log),
    'panics': re.findall(r'^panic\(cpu .*$',log,re.M),
    'recent': [s for s in lines if s.strip()][-4:],
},indent=2))
