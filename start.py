"""Start the complete local app, including its Python dependencies, on Windows/macOS/Linux."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def lan_addresses():
    """Candidate local IPv4 addresses; no external service or Internet probe."""
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)}
    except OSError:
        return []
    return sorted(address for address in addresses if ipaddress.ip_address(address).is_private
                  and not ipaddress.ip_address(address).is_loopback
                  and not ipaddress.ip_address(address).is_link_local)


def main():
    parser = argparse.ArgumentParser(description='Avvia NeuroStudy e apri il browser.')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--lan', action='store_true', help='Consenti accesso da Android sulla stessa rete Wi-Fi (richiede password gia configurata).')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        print('Serve Python 3.12 o successivo. Installalo da https://www.python.org/downloads/')
        return 1
    if not 1024 <= args.port <= 65535:
        print('Scegli una porta compresa fra 1024 e 65535.')
        return 1
    if not (ROOT / 'requirements.txt').is_file() or not (ROOT / 'app/main.py').is_file():
        print('Scarica ed estrai il progetto completo: il solo file HTML non basta.')
        return 1
    host = '0.0.0.0' if args.lan else '127.0.0.1'
    # Never open an unrelated service already listening on this port.
    try:
        with socket.socket() as probe:
            probe.bind((host, args.port))
    except OSError:
        print(f'La porta {args.port} e gia in uso. Se NeuroStudy e aperto, usa quella finestra.')
        print('Altrimenti avvia con: python start.py --port 8001')
        return 1
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Preparazione dell’ambiente Python…', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], cwd=ROOT, check=True)
    requirements = ROOT / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = ROOT / '.venv' / '.neurostudy-requirements.sha256'
    if not marker.exists() or marker.read_text().strip() != fingerprint:
        print('Installazione delle dipendenze (solo al primo avvio o dopo aggiornamenti)…', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                        '-r', str(requirements)], cwd=ROOT, check=True)
        marker.write_text(fingerprint)
    if args.lan:
        # First-run account creation is available only from the local launcher.
        configured = subprocess.run([str(python), '-c',
            'import sys; from app.main import auth_config; sys.exit(0 if "hash" in auth_config() else 2)'], cwd=ROOT)
        if configured.returncode:
            if configured.returncode == 2:
                print('Prima scegli una password sul PC: avvia Avvia NeuroStudy.cmd senza WiFi,')
                print('configura la password nel browser e chiudi il programma con Ctrl+C.')
                print('Poi avvia Avvia NeuroStudy WiFi.cmd per collegare Android.')
            else:
                print('Impossibile verificare la configurazione. Controlla i messaggi precedenti.')
            return 1
    url = f'http://127.0.0.1:{args.port}'
    process = subprocess.Popen([str(python), '-m', 'uvicorn', 'app.main:app', '--host', host,
                                '--port', str(args.port)], cwd=ROOT)

    def open_when_ready():
        # Bypass outbound proxies only for the local readiness request.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(200):
            if process.poll() is not None:
                return
            try:
                with opener.open(url + '/api/status', timeout=1) as response:
                    status = json.load(response)
                if 'setup_required' in status and 'authenticated' in status:
                    print(f'NeuroStudy pronto: {url}', flush=True)
                    if args.lan:
                        print('Android: connetti il telefono alla stessa rete Wi-Fi del PC.', flush=True)
                        addresses = lan_addresses()
                        if addresses:
                            print('Apri nel browser del telefono l’indirizzo del PC sulla rete Wi-Fi:', flush=True)
                            for address in addresses:
                                print(f'  http://{address}:{args.port}', flush=True)
                        else:
                            print(f'Leggi l’indirizzo IPv4 Wi-Fi con ipconfig e apri http://INDIRIZZO-IP:{args.port}', flush=True)
                        print('Se richiesto da Windows Firewall, consenti Python solo sulle reti private.', flush=True)
                        print('Usa una rete fidata: questo collegamento locale usa HTTP, non HTTPS.', flush=True)
                        print('Non aprire porte sul router. Il PC deve restare acceso con questo programma aperto.', flush=True)
                    if not args.no_browser:
                        webbrowser.open(url)
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.3)
        print('Avvio piu lento del previsto: controlla i messaggi del server.', flush=True)

    threading.Thread(target=open_when_ready, daemon=True).start()
    print('Mantieni questa finestra aperta durante lo studio. Ctrl+C per arrestare.', flush=True)
    try:
        return process.wait()
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print('Avvio non riuscito. Controlla Python, la connessione e i messaggi precedenti.')
        print(str(error))
        sys.exit(1)
