"""Start/idle dedicated Python worker processes. Never changes host power state."""
import json
import queue
import subprocess
import threading
import time
import uuid

from run import Workers


class ProcessWorkers(Workers):
    def __init__(self, nodes):
        super().__init__(nodes)
        self.sessions = {}
        self.instances = {}
        self.host_baselines = {}

    def power_command(self, *args):
        raise RuntimeError('Operating-system power operations are forbidden')

    def sleep(self, *args):
        raise RuntimeError('Use idle() for dedicated worker processes; never suspend a computer')

    def host_witness(self, ident):
        try:
            proc = subprocess.run(self.nodes[ident]['host_probe_argv'], capture_output=True,
                                  text=True, timeout=15)
            result = json.loads(proc.stdout)
            if proc.returncode or not result.get('ok') or not result.get('boot_id'):
                raise ValueError('Host witness failed')
            baseline = self.host_baselines.setdefault(ident, result['boot_id'])
            result['ok'] = result['boot_id'] == baseline
            return result
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return {'ok': False, 'error': 'host_awake_witness_failed'}

    @staticmethod
    def read_lines(stream, messages):
        try:
            for line in stream:
                messages.put(line)
        finally:
            messages.put(None)

    def receive(self, ident, timeout=30):
        line = self.sessions[ident]['messages'].get(timeout=timeout)
        if line is None:
            raise ValueError('Worker exited')
        reply = json.loads(line)
        if not isinstance(reply, dict) or type(reply.get('ok')) is not bool:
            raise ValueError('Invalid worker reply')
        return reply

    def wake(self, ident):
        started = time.monotonic()
        old = self.sessions.get(ident)
        if old and old['process'].poll() is None:
            return {'ok': False, 'error': 'worker_already_running'}
        witness = self.host_witness(ident)
        if not witness['ok']:
            return witness
        previous_instance = self.instances.get(ident)
        try:
            proc = subprocess.Popen(self.nodes[ident]['serve_argv'], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    bufsize=1, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            messages = queue.Queue()
            self.sessions[ident] = {'process': proc, 'messages': messages}
            threading.Thread(target=self.read_lines, args=(proc.stdout, messages), daemon=True).start()
            ready = self.receive(ident)
            if not ready['ok'] or ready.get('event') != 'ready' or not ready.get('instance'):
                raise ValueError('Missing real worker readiness')
            if ready['instance'] == previous_instance:
                raise ValueError('Worker instance did not change')
            self.instances[ident] = ready['instance']
            self.nodes[ident]['verified_capabilities'] = ready['capabilities']
            self.sleeping.discard(ident)
            return {'ok': True, 'kind': 'worker_process_activation', 'ready': ready,
                    'host_awake': witness, 'elapsed_ms': (time.monotonic()-started)*1000}
        except (OSError, ValueError, queue.Empty):
            self.force_close(ident)
            return {'ok': False, 'error': 'worker_start_failed'}

    def force_close(self, ident):
        session = self.sessions.get(ident)
        if not session:
            return
        proc = session['process']
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()  # Only the child launched by this harness.
            proc.wait(timeout=5)
        if proc.stdout:
            proc.stdout.close()

    def rpc(self, ident, request):
        started = time.monotonic()
        session = self.sessions.get(ident)
        if not session or session['process'].poll() is not None:
            return {'ok': False, 'error': 'dedicated_worker_not_running', 'rpc_ms': 0}
        token = str(uuid.uuid4())
        try:
            session['process'].stdin.write(json.dumps({**request, 'request_id': token})+'\n')
            session['process'].stdin.flush()
            result = self.receive(ident, 60)
            if result.get('request_id') != token or result.get('instance') != self.instances[ident]:
                raise ValueError('Response is not from requested worker instance')
        except (OSError, ValueError, queue.Empty):
            self.force_close(ident)
            result = {'ok': False, 'error': 'worker_transport_or_protocol_failure'}
        result['rpc_ms'] = (time.monotonic()-started)*1000
        return result

    def idle(self, ident):
        reply = self.rpc(ident, {'action': 'idle'})
        if not reply.get('ok') or reply.get('event') != 'exiting':
            return {'ok': False, 'error': 'worker_did_not_acknowledge_exit'}
        self.force_close(ident)
        exited = self.sessions[ident]['process'].returncode == 0
        witness = self.host_witness(ident)
        if exited and witness['ok']:
            self.sleeping.add(ident)
        return {'ok': exited and witness['ok'], 'kind': 'dedicated_worker_process_exit',
                'exit_receipt': reply, 'exit_code': self.sessions[ident]['process'].returncode,
                'host_awake': witness}

    def close(self):
        for ident in self.nodes:
            self.rpc(ident, {'action': 'clear'})
            if self.sessions.get(ident) and self.sessions[ident]['process'].poll() is None:
                self.rpc(ident, {'action': 'idle'})
            self.force_close(ident)
