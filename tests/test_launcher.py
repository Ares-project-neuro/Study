"""Exercise the actual launcher, isolated from the user's study database."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
import pytest
from start import lan_addresses

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != 'nt', reason='Richiede cmd.exe: eseguito dalla CI Windows')
def test_windows_wrapper_forwards_launcher_options():
    result = subprocess.run(['cmd.exe', '/d', '/c', 'Avvia NeuroStudy.cmd', '--help'], cwd=ROOT,
                            env={**os.environ, 'CI': 'true', 'PYTHONUTF8': '1'}, capture_output=True,
                            text=True, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stderr
    assert '--lan' in result.stdout and '--no-browser' in result.stdout


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def test_lan_launcher_refuses_first_run_without_password(tmp_path):
    port = free_port()
    environment = {**os.environ, 'STUDY_DATA_DIR': str(tmp_path), 'STUDY_PASSWORD': '',
                   'STUDY_AI_KEY': '', 'PYTHONUTF8': '1', 'PIP_NO_INDEX': '1'}
    result = subprocess.run([sys.executable, str(ROOT/'start.py'), '--lan', '--no-browser', '--port', str(port)],
                            cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=40)
    assert result.returncode == 1, result.stderr
    assert 'Prima scegli una password sul PC' in result.stdout
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', port)) != 0


def test_lan_launcher_two_clients_share_persistent_data(tmp_path):
    port = free_port()
    environment = {**os.environ, 'STUDY_DATA_DIR': str(tmp_path/'dati con spazi'),
                   'STUDY_PASSWORD': 'test-launcher-password-123', 'STUDY_AI_KEY': '',
                   'PYTHONUTF8': '1', 'PIP_NO_INDEX': '1'}
    with (tmp_path/'server.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, str(ROOT/'start.py'), '--lan', '--no-browser', '--port', str(port)],
                                   cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            base = f'http://127.0.0.1:{port}'
            # A second hostname also checks the app's same-origin validation with a LAN-style Host.
            phone_base = f'http://localhost:{port}'
            with httpx.Client(base_url=base, trust_env=False) as desktop, httpx.Client(base_url=phone_base, trust_env=False) as phone:
                for _ in range(100):
                    assert process.poll() is None, (tmp_path/'server.log').read_text(encoding='utf-8')
                    try:
                        if desktop.get('/api/status').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.1)
                else:
                    raise AssertionError('Il launcher non ha avviato il server')
                for client, origin in ((desktop, base), (phone, phone_base)):
                    assert client.post('/api/login', json={'password': 'test-launcher-password-123'}, headers={'Origin': origin}).status_code == 200
                card = desktop.post('/api/cards', json={'front': 'Concetto condiviso dal PC?', 'back': 'Visibile anche da Android'}, headers={'Origin': base}).json()
                assert phone.get('/api/cards').json()[0]['id'] == card['id']
                for address in lan_addresses():
                    with httpx.Client(base_url=f'http://{address}:{port}', trust_env=False) as lan:
                        assert lan.get('/api/status').status_code == 200
                    break
                # Stop cleanly through the launcher's own Ctrl+C handling on supported platforms.
                if os.name != 'nt':
                    import signal
                    process.send_signal(signal.SIGINT)
                    assert process.wait(timeout=10) == 0
                else:
                    # taskkill includes the child Uvicorn process on Windows.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                    process.wait(timeout=10)
        finally:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    import signal
                    process.send_signal(signal.SIGINT)
                process.wait(timeout=10)
    assert (tmp_path/'dati con spazi'/'study.sqlite3').exists()
