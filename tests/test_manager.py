"""Lifecycle regression tests; isolated fixtures never start the real guest."""
import importlib
import os
from pathlib import Path
import tempfile
import time
import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'WFS_WORKSPACE': self.temp.name,
                                          'WFS_SYSTEM_IMAGE': str(Path(self.temp.name) / 'hackios/userland/system.apfs'),
                                          'WFS_RUNTIME': str(Path(self.temp.name) / 'runtime')})
        self.env.start()
        from app import main
        self.manager = importlib.reload(main)
        self.context = TestClient(self.manager.app)
        self.client = self.context.__enter__()

    def tearDown(self):
        if self.context is not None:
            self.context.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def prepare_launcher(self):
        script = self.manager.REPO / 'qemu/run-ios.sh'
        script.parent.mkdir(parents=True)
        script.write_text('printf "%s\\n" "$@"; exec bash qemu/run.sh\n')
        for name in ('qemu/run.sh', 'xnuloader/mkpayload.py', 'prebuilt/mach.development.bcm2837',
                     'prebuilt/loader.efi', 'userland/root.apfs', 'userland/system.apfs'):
            path = self.manager.REPO / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
        (self.manager.REPO / 'qemu/run.sh').write_text(
            'T=300; timeout "$T" bash -c \'trap "" TERM; echo WFS_CHILD_PID=$$; exec sleep 300\'\n')

    def test_missing_prerequisites(self):
        status = self.client.get('/api/status').json()
        self.assertFalse(status['ready'])
        self.assertIn('launcher', status['missing'])
        self.assertEqual(self.client.post('/api/start', json={'seconds': 60}).status_code, 409)

    def test_duration_validation(self):
        for value in (0, 59, 3601, '60', 60.5, True, None):
            with self.subTest(value=value):
                response = self.client.post('/api/start', json={'seconds': value})
                self.assertEqual(response.status_code, 422)

    def test_start_duplicate_stop_restart_and_old_timer(self):
        self.prepare_launcher()
        with patch.object(self.manager, 'prerequisites', return_value=[]):
            first = self.client.post('/api/start', json={'seconds': 60})
            self.assertEqual(first.status_code, 200)
            old_process = self.manager._process
            self.assertEqual(self.client.get('/api/status').json()['status'], 'running')
            self.assertEqual(self.client.post('/api/start', json={'seconds': 60}).status_code, 409)
            deadline = time.monotonic() + 3
            while '-display' not in self.client.get('/api/logs').text and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertIn('60\n-display\ngtk', self.client.get('/api/logs').text)
            deadline = time.monotonic() + 3
            while 'WFS_CHILD_PID=' not in self.client.get('/api/logs').text and time.monotonic() < deadline:
                time.sleep(.05)
            child_pid = int(re.search(r'WFS_CHILD_PID=(\d+)', self.client.get('/api/logs').text)[1])
            self.assertEqual(self.client.post('/api/stop').json()['status'], 'stopped')
            self.assertIsNotNone(old_process.poll())
            child_state = Path(f'/proc/{child_pid}/stat')
            deadline = time.monotonic() + 2
            while child_state.exists() and child_state.read_text().split()[2] != 'Z' and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(not child_state.exists() or child_state.read_text().split()[2] == 'Z')
            self.assertEqual(self.client.post('/api/stop').status_code, 200)
            self.assertEqual(self.client.post('/api/start', json={'seconds': 60}).status_code, 200)
            self.manager.stop(old_process)
            self.assertEqual(self.client.get('/api/status').json()['status'], 'running')
            self.manager.stop(self.manager._process)
            self.assertEqual(self.client.get('/api/status').json()['status'], 'stopped')

    def test_shutdown_stops_process(self):
        self.prepare_launcher()
        with patch.object(self.manager, 'prerequisites', return_value=[]):
            self.client.post('/api/start', json={'seconds': 60})
        process = self.manager._process
        self.context.__exit__(None, None, None)
        self.context = None
        self.assertIsNotNone(process.poll())

    def test_home_and_empty_logs(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertIn('No session logs', self.client.get('/api/logs').text)

    def test_launch_error_is_reported(self):
        with patch.object(self.manager, 'prerequisites', return_value=[]), \
             patch.object(self.manager.subprocess, 'Popen', side_effect=OSError('launcher unavailable')):
            response = self.client.post('/api/start', json={'seconds': 60})
        self.assertEqual(response.status_code, 503)
        self.assertIn('launcher unavailable', response.json()['detail'])
        self.assertEqual(self.client.get('/api/status').json()['status'], 'stopped')

    def test_failed_guest_is_reported_as_stopped(self):
        self.prepare_launcher()
        (self.manager.REPO / 'qemu/run-ios.sh').write_text('echo guest-start-failed; exit 7\n')
        with patch.object(self.manager, 'prerequisites', return_value=[]):
            self.assertEqual(self.client.post('/api/start', json={'seconds': 60}).status_code, 200)
        deadline = time.monotonic() + 3
        while self.manager.get_status() == 'running' and time.monotonic() < deadline:
            time.sleep(.05)
        status = self.client.get('/api/status').json()
        self.assertEqual(status['status'], 'stopped')
        self.assertEqual(status['last_exit_code'], 7)
        self.manager._log_thread.join(timeout=2)
        self.assertIn('guest-start-failed', self.client.get('/api/logs').text)

    def test_guest_panic_is_reported_while_emulator_still_runs(self):
        self.prepare_launcher()
        (self.manager.REPO / 'qemu/run-ios.sh').write_text(
            'printf "pan"; sleep .05; printf "ic(cpu 0 caller 0xffff): Ticket spinlock timeout\\n"; exec sleep 300\n')
        with patch.object(self.manager, 'prerequisites', return_value=[]):
            self.client.post('/api/start', json={'seconds': 60})
        deadline = time.monotonic() + 3
        while not self.manager._guest_error and time.monotonic() < deadline:
            time.sleep(.05)
        status = self.client.get('/api/status').json()
        self.assertEqual(status['status'], 'running')
        self.assertEqual(status['guest_status'], 'failed')
        self.assertIn('Ticket spinlock timeout', status['guest_error'])
        self.assertIsNone(self.manager._process.poll())
        self.client.post('/api/stop')
        (self.manager.REPO / 'qemu/run-ios.sh').write_text('exec sleep 300\n')
        with patch.object(self.manager, 'prerequisites', return_value=[]):
            self.client.post('/api/start', json={'seconds': 60})
            self.assertIsNone(self.manager._guest_error)

    def test_alternate_image_is_checked_and_staged_without_replacing_source(self):
        self.prepare_launcher()
        original = self.manager.REPO / 'userland/system.apfs'
        original.write_text('original-image')
        alternate = Path(self.temp.name) / 'alternate.apfs'
        (self.manager.REPO / 'qemu/run-ios.sh').write_text(
            'cat userland/system.apfs; exec sleep 300\n')
        with patch.object(self.manager, 'SYSTEM_IMAGE', alternate), \
             patch.dict(os.environ, {'WFS_SYSTEM_IMAGE': str(alternate)}):
            self.assertIn('system_image', self.manager.prerequisites())
            alternate.write_text('override-image')
            self.assertNotIn('system_image', self.manager.prerequisites())
            with patch.object(self.manager, 'prerequisites', return_value=[]):
                self.client.post('/api/start', json={'seconds': 60})
            deadline = time.monotonic() + 3
            while 'override-image' not in self.client.get('/api/logs').text and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertIn('override-image', self.client.get('/api/logs').text)
            self.client.post('/api/stop')
        self.assertEqual(original.read_text(), 'original-image')


if __name__ == '__main__':
    unittest.main()
