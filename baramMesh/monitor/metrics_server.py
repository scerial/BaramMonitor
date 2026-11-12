#!/usr/bin/env python
# -*- coding: utf-8 -*-

import hmac
import ipaddress
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, List, Optional
from urllib.parse import parse_qs, quote, urlparse

import psutil

from baramMesh.monitor.alerts import AlertEngine, EventLog


API_VERSION = 1
TAILSCALE_NETWORK = ipaddress.ip_network('100.64.0.0/10')
MAX_WAIT_SECONDS = 30.0
HISTORY_POINTS = 150
PAIRING_SCHEME = 'baramonitor'
TAILSCALE_CLI_CANDIDATES = (r'C:\Program Files\Tailscale\tailscale.exe', '/usr/bin/tailscale',
                            '/Applications/Tailscale.app/Contents/MacOS/Tailscale')


def _addresses():
    for addresses in psutil.net_if_addrs().values():
        for address in addresses:
            if address.family == socket.AF_INET:
                yield address.address


def tailscaleAddress() -> Optional[str]:
    for address in _addresses():
        try:
            if ipaddress.ip_address(address) in TAILSCALE_NETWORK:
                return address
        except ValueError:
            continue

    return None


def lanAddresses() -> List[str]:
    result = []
    for address in _addresses():
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue

        if ip.is_private and not ip.is_loopback and not ip.is_link_local and ip not in TAILSCALE_NETWORK:
            result.append(address)

    return result


def tailscaleDnsName() -> Optional[str]:
    executable = shutil.which('tailscale') or next((p for p in TAILSCALE_CLI_CANDIDATES if os.path.isfile(p)), None)
    if not executable:
        return None

    try:
        output = subprocess.run(
            [executable, 'status', '--json'], capture_output=True, text=True, timeout=3,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        name = json.loads(output).get('Self', {}).get('DNSName', '')
    except Exception:
        return None

    return name.rstrip('.') or None


def resolveBindHost(mode: str) -> str:
    if mode == 'all':
        return '0.0.0.0'

    if mode == 'local':
        return '127.0.0.1'

    address = tailscaleAddress()
    if address is None:
        raise OSError('Tailscale address not found. Start Tailscale on this PC or choose another network option.')

    return address


def pairingHosts(mode: str) -> List[str]:
    hosts = []
    if mode != 'local':
        name = tailscaleDnsName()
        if name:
            hosts.append(name)

        address = tailscaleAddress()
        if address:
            hosts.append(address)

    if mode == 'all':
        hosts.extend(lanAddresses())

    return hosts or ['127.0.0.1']


def pairingLink(host: str, port: int, token: str, name: Optional[str] = None) -> str:
    name = name or platform.node()
    return f'{PAIRING_SCHEME}://pair?host={quote(host)}&port={port}&token={quote(token)}&name={quote(name)}'


def _sampleDict(sample, config) -> dict:
    data = asdict(sample)
    data['ageSeconds'] = round(time.monotonic() - data.pop('time'), 1)
    data['thresholds'] = {
        'tdpWatts': config.tdpWatts, 'pptWatts': config.pptWatts, 'tempWarn': config.tempWarn,
        'tempCritical': config.tempCritical, 'psuWatts': config.psuWatts, 'baselineWatts': config.baselineWatts
    }
    return data


def _historyDict(samples, seconds: float) -> dict:
    now = time.monotonic()
    samples = [s for s in samples if now - s.time <= seconds]
    step = max(1, len(samples) // HISTORY_POINTS)
    points = [{
        't': round(now - s.time, 1), 'memUsed': s.memUsed, 'memMeshing': s.memMeshing, 'cpu': s.cpuPercent,
        'cpuMeshing': s.cpuMeshingPercent, 'temp': s.cpuTemp, 'cpuPower': s.cpuPower, 'pcPower': s.pcPower
    } for s in samples[::step]]

    return {'seconds': seconds, 'points': points}


class MetricsServer:
    def __init__(self, sampler, progressProvider: Callable[[], Optional[dict]]):
        self._sampler = sampler
        self._progressProvider = progressProvider
        self._log = EventLog()
        self._engine = AlertEngine(self._log)
        self._httpd = None
        self._serverThread = None
        self._tickThread = None
        self._stopping = threading.Event()
        self._token = ''
        self._started = time.time()
        self._instance = secrets.token_hex(4)
        self.address = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    @property
    def log(self) -> EventLog:
        return self._log

    def start(self, host: str, port: int, token: str):
        if self.running:
            return

        if not token:
            raise ValueError('An access token is required')

        self._token = token
        self._stopping.clear()
        self._httpd = ThreadingHTTPServer((host, port), self._handlerClass())
        self._httpd.daemon_threads = True
        self.address = self._httpd.server_address
        self._started = time.time()
        self._instance = secrets.token_hex(4)

        self._serverThread = threading.Thread(target=self._httpd.serve_forever, name='MetricsServer', daemon=True)
        self._tickThread = threading.Thread(target=self._tick, name='MetricsAlerts', daemon=True)
        self._serverThread.start()
        self._tickThread.start()

    def stop(self):
        httpd, self._httpd = self._httpd, None
        if httpd is None:
            return

        self._stopping.set()
        httpd.shutdown()
        httpd.server_close()
        self.address = None

    def snapshot(self) -> dict:
        sample = self._sampler.latest()
        config = self._sampler.config
        return {
            'apiVersion': API_VERSION,
            'instance': self._instance,
            'host': platform.node(),
            'serverTime': time.time(),
            'uptime': round(time.time() - self._started, 1),
            'resources': _sampleDict(sample, config) if sample else None,
            'progress': self._progress(),
            'lastEventId': self._log.lastId()
        }

    def _progress(self) -> Optional[dict]:
        try:
            return self._progressProvider()
        except Exception:
            return None

    def _tick(self):
        while not self._stopping.wait(1.0):
            sample = self._sampler.latest()
            if sample is None:
                continue

            try:
                self._engine.evaluate(sample, self._sampler.config, self._progress())
            except Exception:
                continue

    def _authorized(self, headers, query) -> bool:
        header = headers.get('Authorization', '')
        supplied = header[7:] if header.startswith('Bearer ') else (query.get('token') or [''])[0]
        return hmac.compare_digest(supplied.encode('utf-8'), self._token.encode('utf-8'))

    def _handlerClass(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, format, *args):
                return

            def _send(self, status, payload):
                body = json.dumps(payload).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urlparse(self.path)
                query = parse_qs(url.query)

                if not server._authorized(self.headers, query):
                    time.sleep(0.3)
                    self._send(401, {'error': 'unauthorized'})
                    return

                try:
                    self._route(url.path, query)
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as e:
                    self._send(500, {'error': f'{type(e).__name__}: {e}'})

            def _route(self, path, query):
                if path == '/api/ping':
                    self._send(200, {'ok': True, 'apiVersion': API_VERSION, 'host': platform.node()})
                elif path == '/api/state':
                    self._send(200, server.snapshot())
                elif path == '/api/history':
                    seconds = min(max(float((query.get('seconds') or ['300'])[0]), 10.0), 600.0)
                    self._send(200, _historyDict(server._sampler.history(), seconds))
                elif path == '/api/events':
                    since = int((query.get('since') or ['0'])[0])
                    wait = min(max(float((query.get('wait') or ['0'])[0]), 0.0), MAX_WAIT_SECONDS)
                    events = server._log.wait(since, wait) if wait else server._log.since(since)
                    self._send(200, {
                        'instance': server._instance, 'lastEventId': server._log.lastId(),
                        'events': [e.asDict() for e in events]
                    })
                else:
                    self._send(404, {'error': 'not found'})

        return Handler
