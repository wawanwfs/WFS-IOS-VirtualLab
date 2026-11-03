import sys
sys.path.insert(0, '/workspace/hackios/qemu')
from touch import Qmp
q = Qmp(port=int(sys.argv[1]))
if sys.argv[2] == 'release':
    print(q.pointer(.5, .5, False))
else:
    print(q.command('human-monitor-command', **{'command-line': sys.argv[2]}))
