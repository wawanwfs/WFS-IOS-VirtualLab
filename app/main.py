import os
import signal
import subprocess
import threading
import sys
import select
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

ROOT = Path(os.getenv('WFS_WORKSPACE', '/workspace')).resolve()
REPO = ROOT / 'hackios'
SYSTEM_IMAGE = Path(os.getenv('WFS_SYSTEM_IMAGE') or str(REPO / 'userland/system.apfs'))
LOG_DIR = ROOT / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG = LOG_DIR / 'session.log'
STATIC = Path(__file__).parent / 'static'
SESSION_SECONDS = max(60, min(int(os.getenv('WFS_SESSION_SECONDS', '1200')), 3600))
_lock = threading.Lock()
_process = None
_timer = None
_log_thread = None
_guest_error = None

def pump_output(process, output):
    """Batch serial output: one Windows bind-mount write per second, not per byte."""
    global _guest_error
    with process.stdout, output:
        last_flush = time.monotonic()
        pending = b''
        while True:
            readable, _, _ = select.select([process.stdout], [], [], 0.5)
            if readable:
                data = os.read(process.stdout.fileno(), 65536)
                if not data:
                    break
                output.write(data)
                pending += data
                lines = pending.split(b'\n')
                pending = lines.pop()[-8192:]
                for line in lines:
                    if line.startswith(b'panic(cpu ') and process is _process:
                        _guest_error = line.rstrip(b'\r').decode('utf-8', errors='replace')
            if time.monotonic() - last_flush >= 1:
                output.flush()
                last_flush = time.monotonic()

@asynccontextmanager
async def lifespan(app):
    yield
    stop()

app = FastAPI(title='WFS iOS Virtual Lab', version='0.2.0', lifespan=lifespan)

class Settings(BaseModel):
    seconds: int = Field(default=SESSION_SECONDS, ge=60, le=3600, strict=True)

def prerequisites():
    files = {
        'launcher': REPO / 'qemu/run-ios.sh',
        'qemu_runner': REPO / 'qemu/run.sh',
        'payload_builder': REPO / 'xnuloader/mkpayload.py',
        'root_image': REPO / 'userland/root.apfs',
        'system_image': SYSTEM_IMAGE,
        'kernel': REPO / 'prebuilt/mach.development.bcm2837',
        'loader': REPO / 'prebuilt/loader.efi',
        'efi': Path(os.getenv('QEMU_EFI', '/usr/share/AAVMF/AAVMF_CODE.fd')),
        'efi_vars': Path(os.getenv('QEMU_VARS', '/usr/share/AAVMF/AAVMF_VARS.fd')),
        'ramfb_rom': Path('/usr/share/seabios/vgabios-ramfb.bin'),
    }
    return [name for name, path in files.items() if not path.is_file() or path.stat().st_size == 0]

def get_status():
    global _process
    if _process is not None and _process.poll() is None:
        return 'running'
    return 'stopped'

@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html')

@app.get('/api/status')
def status():
    missing = prerequisites()
    return {
        'status': get_status(),
        'repository_present': (REPO / 'qemu' / 'run-ios.sh').is_file(),
        'userland_present': (REPO / 'userland').exists(),
        'images_present': (REPO / 'userland' / 'root.apfs').is_file() and SYSTEM_IMAGE.is_file(),
        'session_seconds_default': SESSION_SECONDS,
        'host_logical_cpus': os.cpu_count(),
        'guest_cpus': int(os.getenv('QEMU_SMP', '1')),
        'guest_ram_gb': int(os.getenv('QEMU_RAM_GB', '7')),
        'ready': not missing,
        'missing': missing,
        'last_exit_code': _process.poll() if _process is not None else None,
        'guest_status': 'failed' if _guest_error else 'unverified' if get_status() == 'running' else 'stopped',
        'guest_error': _guest_error,
    }

@app.post('/api/start')
def start(settings: Settings):
    global _process, _timer, _log_thread, _guest_error
    with _lock:
        if get_status() == 'running':
            raise HTTPException(409, 'Session already running')
        missing = prerequisites()
        if missing:
            raise HTTPException(409, 'Missing prerequisites: ' + ', '.join(missing))
        if _timer is not None:
            _timer.cancel()
        if _log_thread is not None:
            _log_thread.join(timeout=2)
        _guest_error = None
        # Never shell interpolate arbitrary user input. Run documented entry point.
        out = open(RUN_LOG, 'ab')
        out.write(b'\n=== WFS iOS session starting ===\n')
        out.flush()
        try:
            _process = subprocess.Popen(
                [sys.executable, '-m', 'app.launch', str(settings.seconds), '-display', 'gtk', '-nic', 'none'],
                cwd=str(STATIC.parent.parent),
                env={**os.environ, 'DISPLAY': ':99',
                     'QEMU_EFI': os.getenv('QEMU_EFI', '/usr/share/AAVMF/AAVMF_CODE.fd'),
                     'QEMU_VARS': os.getenv('QEMU_VARS', '/usr/share/AAVMF/AAVMF_VARS.fd')},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            out.close()
            raise HTTPException(503, f'Cannot launch session: {exc}') from exc
        _log_thread = threading.Thread(target=pump_output, args=(_process, out), daemon=True)
        _log_thread.start()
        # Bound wall-clock runtime, including image preparation. A timer belongs
        # to one process only, so an old callback cannot stop a later session.
        _timer = threading.Timer(settings.seconds + 40, stop, args=(_process,))
        _timer.daemon = True
        _timer.start()
        return {'status': 'starting', 'pid': _process.pid}

@app.post('/api/stop')
def stop_session():
    return stop()

def stop(expected=None):
    global _timer
    with _lock:
        if expected is not None and expected is not _process:
            return {'status': 'stopped'}
        if _timer is not None:
            _timer.cancel()
        if get_status() != 'running':
            return {'status': 'stopped'}
        pid = _process.pid
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            _process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _process.wait(timeout=3)
        # The shell can exit before QEMU finishes its SIGTERM handler. Clean
        # up descendants even when waiting for the shell succeeded immediately.
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if _log_thread is not None:
            _log_thread.join(timeout=2)
        return {'status': 'stopped'}

@app.get('/api/logs', response_class=PlainTextResponse)
def logs():
    if not RUN_LOG.exists():
        return 'No session logs yet.'
    with RUN_LOG.open('rb') as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 20000))
        return f.read().decode('utf-8', errors='replace')
