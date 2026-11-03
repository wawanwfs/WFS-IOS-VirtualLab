"""Exercise the real 60 + 40 second deadline in an isolated API subprocess.

The fake guest deliberately ignores SIGTERM; no real images are modified.
"""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        repo = root / 'hackios'
        files = ('qemu/run-ios.sh', 'qemu/run.sh', 'xnuloader/mkpayload.py',
                 'prebuilt/mach.development.bcm2837', 'prebuilt/loader.efi',
                 'userland/root.apfs', 'userland/system.apfs')
        for name in files:
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
        (repo / 'qemu/run-ios.sh').write_text('exec bash qemu/run.sh\n')
        (repo / 'qemu/run.sh').write_text(
            'T=300; timeout "$T" bash -c \'trap "" TERM; echo WFS_CHILD_PID=$$; exec sleep 300\'\n')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        env = {**os.environ, 'WFS_WORKSPACE': directory,
               'WFS_RUNTIME': str(root / 'runtime'), 'WFS_SESSION_SECONDS': '60'}
        server = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
             '--port', str(port), '--no-access-log', '--log-level', 'warning'],
            env=env, stdin=subprocess.DEVNULL)

        def request(path, payload=None):
            data = None if payload is None else json.dumps(payload).encode()
            req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data,
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read().decode()

        try:
            for _ in range(100):
                try:
                    request('/api/status')
                    break
                except OSError:
                    time.sleep(.1)
            started = time.monotonic()
            request('/api/start', {'seconds': 60})
            child_pid = None
            while time.monotonic() - started < 112:
                match = re.search(r'WFS_CHILD_PID=(\d+)', request('/api/logs'))
                if match:
                    child_pid = int(match[1])
                status = json.loads(request('/api/status'))
                if status['status'] == 'stopped':
                    break
                time.sleep(1)
            elapsed = time.monotonic() - started
            assert 98 <= elapsed <= 110, elapsed
            assert status['status'] == 'stopped', status
            assert child_pid is not None
            child = Path(f'/proc/{child_pid}/stat')
            assert not child.exists() or child.read_text().split()[2] == 'Z'
            result = {'passed': True, 'requested_seconds': 60,
                      'wall_limit_seconds': 100, 'elapsed_seconds': round(elapsed, 2),
                      'status': status['status'], 'child_terminated': True}
            print(json.dumps(result), flush=True)
            if len(sys.argv) > 1:
                Path(sys.argv[1]).write_text(json.dumps(result, indent=2))
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)


if __name__ == '__main__':
    main()
