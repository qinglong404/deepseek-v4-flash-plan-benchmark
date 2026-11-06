"""Real loopback transport checks; never contacts Magpie or reads credentials."""
import hashlib
import importlib.util
import io
import json
import socketserver
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent / 'client.py'
spec = importlib.util.spec_from_file_location('local_audited_client', CLIENT)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            first = self.rfile.readline().decode()
            path = first.split()[1]
            length = 0
            while True:
                line = self.rfile.readline()
                if line in (b'\r\n', b'\n', b''):
                    break
                if line.lower().startswith(b'content-length:'):
                    length = int(line.split(b':', 1)[1])
            self.rfile.read(length)
            self.server.paths.append(path)
            if '/slowheaders/' in path:
                self.wfile.write(b'HTTP/1.1 200 OK\r\nX-Slow: ')
                self.wfile.flush()
                for _ in range(20):
                    self.wfile.write(b'x')
                    self.wfile.flush()
                    time.sleep(.05)
                self.wfile.write(b'\r\nContent-Type: text/event-stream\r\nX-Magpie-Provider: opencode-go\r\nConnection: close\r\n\r\n')
                self.wfile.flush()
            else:
                self.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nX-Magpie-Provider: opencode-go\r\nConnection: close\r\n\r\n')
                self.wfile.flush()
            if '/partial/' in path:
                for _ in range(20):
                    self.wfile.write(b'd')
                    self.wfile.flush()
                    time.sleep(.05)
            elif '/idle/' in path:
                time.sleep(1)
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

results = {}
with Server(('127.0.0.1', 0), Handler) as server:
    server.paths = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for mode in ['idle', 'partial', 'slowheaders']:
        records = []
        cfg = json.dumps({'provider': {'magpie': {'options': {'baseURL': f'http://127.0.0.1:{server.server_address[1]}/{mode}', 'apiKey': 'FAKE-LOCAL'}}}})
        start = time.perf_counter()
        with patch.object(client.Path, 'read_text', return_value=cfg), patch.object(client, 'append', side_effect=lambda p, r: records.append((p.name, r.copy()))), redirect_stdout(io.StringIO()):
            result = client.call('go', [{'role': 'user', 'content': 'local-only'}], trial_id='local-deadline-'+mode, phase='audit-only', deadline=.25)
        wall = time.perf_counter() - start
        results[mode] = {k: result.get(k) for k in ['complete', 'failure_class', 'deadline_hit', 'error', 'total_ms', 'headers_ms']}
        results[mode].update(measured_wall_s=wall, journal_events=[r.get('event', 'request') for p, r in records])
    paths = list(server.paths)
    server.shutdown()
summary = {'client_sha256': hashlib.sha256(CLIENT.read_bytes()).hexdigest(), 'no_upstream_calls': True, 'no_credential_reads': True, 'local_request_paths': paths, 'deadline_s': .25, 'cases': results}
(HERE / 'local-deadline-results.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
