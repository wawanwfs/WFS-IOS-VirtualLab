"""Record QEMU lifecycle events without injecting guest input."""
import json
from pathlib import Path
import socket
import time

connection = socket.create_connection(('127.0.0.1', 4445), timeout=5)
connection.settimeout(None)
stream = connection.makefile('rwb')
with Path('/workspace/logs/qmp-minimal.jsonl').open('a') as output:
    def record(message):
        line = json.dumps({'time': time.time(), 'message': message})
        output.write(line + '\n')
        output.flush()
        print(line, flush=True)

    record(json.loads(stream.readline()))
    stream.write(b'{"execute":"qmp_capabilities"}\n')
    stream.flush()
    for line in stream:
        record(json.loads(line))
    record({'connection': 'closed'})
