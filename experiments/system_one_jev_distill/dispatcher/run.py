"""Physical dispatcher experiment; absent prerequisites cannot produce PASS."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_jev_hardware import Device, proof
from contract import NAMES, choose, project
from audit_model import audit_wake
from worker import cpu_transform

class Workers:
    def __init__(self, nodes):
        self.nodes = {n['id']: n for n in nodes}
        if len(self.nodes) != len(nodes) or len(nodes) < 2:
            raise ValueError('Need at least two uniquely named physical workers')
        for node in nodes:
            if not re.fullmatch('[a-z0-9-]+', node['id']) or not isinstance(node['argv'], list):
                raise ValueError('Invalid worker identity/command manifest')
            for feature in ('performance', 'energy_cost', 'wake_cost'):
                if not 0 <= node[feature] <= 1:
                    raise ValueError('Invalid profile value')
        self.sleeping = set()
        self.pending_sleep = set()

    def rpc(self, node_id, request):
        started = time.monotonic()
        try:
            proc = subprocess.run(self.nodes[node_id]['argv'], input=json.dumps(request)+'\n',
                                  text=True, capture_output=True, timeout=60)
            result = json.loads(proc.stdout) if proc.returncode == 0 else {'ok': False, 'error': 'transport_exit'}
            if not isinstance(result, dict) or type(result.get('ok')) is not bool:
                raise ValueError('Invalid worker response')
        except (OSError, subprocess.TimeoutExpired, ValueError):
            result = {'ok': False, 'error': 'transport_or_invalid_response'}
        result['rpc_ms'] = (time.monotonic()-started)*1000
        return result

    def states(self, task):
        result = []
        for ident, node in self.nodes.items():
            probe = self.rpc(ident, {'action': 'probe'})
            ready = probe['ok']
            sleeping = ident in self.sleeping and not ready
            capabilities = probe.get('capabilities', []) if ready else node.get('verified_capabilities', [])
            state = dict(capable=int(task['kernel'] in capabilities), readiness=1 if ready else 0 if sleeping else -1,
                         free_capacity=probe.get('free_capacity', 1 if sleeping else 0),
                         reliability=1 if ready or sleeping else 0,
                         work_value=task['demand']*node['performance'], energy_cost=node['energy_cost'],
                         wake_cost=node['wake_cost'] if sleeping else 0,
                         freshness=1 if ready or sleeping else 0)
            result.append({'id': ident, 'state': state, 'probe': probe})
            result[-1]['observed_at_monotonic'] = time.monotonic()
        return result

    def power_command(self, ident, field):
        # Owner clarification: wake worker processes, never suspend their hosts.
        return {'ok': False, 'error': 'operating_system_power_operations_disabled'}

    def sleep(self, ident):
        node = self.nodes[ident]
        if not all(node.get(k) for k in ('sleep_argv', 'wake_argv', 'sleep_witness_argv')):
            return {'ok': False, 'error': 'real_sleep_wake_adapter_missing'}
        result = self.power_command(ident, 'sleep_argv')
        if not result['ok']:
            return result
        self.pending_sleep.add(ident)
        # Independent power witness is required: SSH timeout alone is not sleep.
        witnessed = self.power_command(ident, 'sleep_witness_argv')
        probe = self.rpc(ident, {'action': 'probe'})
        if witnessed['ok'] and not probe['ok']:
            self.sleeping.add(ident)
            return {'ok': True, 'sleep_witness': witnessed, 'probe': probe}
        return {'ok': False, 'error': 'sleep_not_witnessed'}

    def wake(self, ident):
        started = time.monotonic()
        sent = self.power_command(ident, 'wake_argv')
        if not sent['ok']:
            return sent
        deadline = time.monotonic()+120
        attempts = []
        while time.monotonic() < deadline:
            probe = self.rpc(ident, {'action': 'probe'})
            attempts.append(probe)
            if probe['ok']:
                self.sleeping.discard(ident)
                self.pending_sleep.discard(ident)
                return {'ok': True, 'elapsed_ms': (time.monotonic()-started)*1000, 'probes': attempts}
            time.sleep(2)
        return {'ok': False, 'error': 'wake_readiness_timeout', 'probes': attempts}

class HardwareScorer:
    def __init__(self, port, model, directory):
        if not re.fullmatch(r'COM\d+', port.upper()) or port.upper() == 'COM3':
            raise ValueError('A non-protected Windows COM port is required')
        self.transcript = proof.Transcript(directory/'serial.txt')
        self.device = Device(port, self.transcript)
        rows = model['rows']
        if len(rows) != 8 or any(len(row) != 9 for row in rows):
            raise ValueError('Expected 8x9 model')
        q10 = [[round(float(v)*1024) for v in row] for row in rows]
        if any(abs(float(rows[r][c])-q10[r][c]/1024) > 1e-12 for r in range(8) for c in range(9)):
            raise ValueError('Model weights must already be frozen on the Q10 grid')
        if any(abs(v) > 8192 for row in q10 for v in row):
            raise ValueError('Q10 weights outside firmware range')
        self.q10 = q10
        self.original = None
        self.changed = False

    def open(self):
        self.device.open()
        identity = proof.identify(self.device)
        if 'release=2.0.1' not in identity:
            raise RuntimeError('Expected SSOS V2.0.1')
        # Only these eight rows are replaced. Read each separately: a bulk DUMP
        # can exceed the native USB transmit buffer and lose its final packet.
        packets = []
        for row in range(8):
            reply = self.device.command(f'GET id=model:w:{row}',
                                        proof.prefix(f'OK PKT id=model:w:{row} '))
            packets.append(reply.removeprefix('OK '))
        (self.transcript.path.parent/'original-packets.txt').write_text('\n'.join(packets)+'\n')
        originals = {}
        for packet in packets:
            match = re.search(r'\bid=model:w:(\d+)\b', packet)
            body = re.search(r'\bbody=([\d,-]+)', packet)
            if match and body:
                originals[int(match[1])] = [int(v) for v in body[1].split(',')]
        if set(originals) != set(range(8)) or any(len(v) != 9 for v in originals.values()):
            raise RuntimeError('Could not back up all original model rows; refusing replacement')
        self.original = {'rows_q10': [originals[i] for i in range(8)]}
        self.changed = True
        proof.install_rows(self.device, {'rows_q10': self.q10})
        # Basis validation proves every coefficient of the installed candidate.
        for axis in range(9):
            values = [float(i == axis) for i in range(9)]
            y = self.infer(values)
            if max(abs(y[r]-self.q10[r][axis]/1024) for r in range(8)) > .00002:
                raise RuntimeError('Installed dispatcher rows failed basis validation')

    def infer(self, values):
        text = ','.join(format(v, '.9g') for v in values)
        line = self.device.command('MINFER x='+text, proof.prefix('OK model y8='))
        y, _ = proof.parse_inference(line)
        return y

    def score(self, candidates):
        result = []
        for candidate in candidates:
            candidate = dict(candidate)
            observed = candidate.pop('observed_at_monotonic')
            candidate['state'] = dict(candidate['state'])
            candidate['state']['freshness'] *= max(0, 1-(time.monotonic()-observed)/30)
            x9 = project(candidate['state'])
            started = time.monotonic()
            y = self.infer(x9)
            expected = [sum(row[i]/1024*x9[i] for i in range(9)) for row in self.q10]
            error = max(abs(a-b) for a,b in zip(y,expected))
            if error > .00002:
                raise RuntimeError('Device output differs from frozen model; refusing dispatch')
            result.append({**candidate, 'x9': x9, 'y8': y, 'outputs': dict(zip(NAMES, y)),
                           'source': 'physical_esp32_minfer', 'max_abs_error': error,
                           'score_ms': (time.monotonic()-started)*1000})
        return result

    def close(self):
        try:
            if self.changed:
                proof.install_rows(self.device, self.original)
                for axis in range(9):
                    y = self.infer([float(i == axis) for i in range(9)])
                    if max(abs(y[r]-self.original['rows_q10'][r][axis]/1024) for r in range(8)) > .00002:
                        raise RuntimeError('Restored model failed basis validation')
        finally:
            self.device.close()
            self.transcript.close()

def dispatch(workers, scorer, task, fail_after_selection=False):
    record = {'task': task, 'rounds': [], 'dispatches': [], 'wakes': [], 'status': 'FAIL'}
    started = time.monotonic()
    for attempt in range(len(workers.nodes)+1):
        scored = scorer.score(workers.states(task))
        selected = choose(scored)
        record['rounds'].append({'candidates': scored, 'selected': selected['id'] if selected else None})
        if selected is None:
            record['reason'] = 'no_eligible_candidate'
            break
        ident = selected['id']
        if selected['state']['readiness'] == 0:
            if selected['y8'][1] < 0:
                record['reason'] = 'selected_sleeping_worker_but_no_wake_decision'
                break
            woke = workers.wake(ident)
            record['wakes'].append({'id': ident, **woke})
            if not woke['ok']:
                record['reason'] = 'wake_failed'
                break
            continue  # require new device scores on observed ready telemetry
        if fail_after_selection and attempt == 0:
            fault = workers.rpc(ident, {'action': 'unavailable', 'seconds': 300})
            record['fault_injection'] = {'id': ident, **fault}
            if not fault['ok']:
                record['reason'] = 'fault_injection_failed'
                break
        reply = workers.rpc(ident, {'action': 'execute', 'kernel': task['kernel'], 'count': task['count']})
        expected = hashlib.sha256(cpu_transform(task['count'])).hexdigest()
        correct = (reply.get('ok') and reply.get('kernel') == task['kernel'] and
                   reply.get('count') == task['count'] and reply.get('sha256') == expected)
        record['dispatches'].append({'id': ident, 'reply': reply, 'correct': bool(correct)})
        if correct:
            record.update(status='PASS', completed_on=ident)
            break
        if reply.get('ok'):
            record['reason'] = 'incorrect_worker_output'
            break
        # Failed worker's probe must reflect failure before the next device decision.
        # If it still claims health, stop instead of replaying a task with unknown outcome.
        if workers.rpc(ident, {'action': 'probe'}).get('ok'):
            record['reason'] = 'ambiguous_dispatch_failure_no_safe_replay'
            break
    record['elapsed_ms'] = (time.monotonic()-started)*1000
    return record

def gate(evidence):
    cases = evidence['scenarios']
    if evidence.get('model_wake_audit', {}).get('status') == 'FAIL':
        return 'FAIL'
    if evidence.get('restore_error') or any(s['status'] == 'FAIL' for s in cases):
        return 'FAIL'
    if evidence.get('error'):
        return 'FAIL' if evidence.get('physical_scoring_started') else 'BLOCKED'
    expected = {(s,r) for s in range(1,7) for r in range(1,4)}
    if len(cases) != 18 or {(s['scenario'],s['repetition']) for s in cases} != expected:
        return 'BLOCKED'
    if not evidence.get('original_head_restored') or any(s['status'] != 'PASS' for s in cases):
        return 'BLOCKED'
    if not evidence.get('distinct_machine_fingerprints_verified'):
        return 'BLOCKED'
    for case in cases:
        if not case.get('dispatches') or not case['dispatches'][-1].get('correct'):
            return 'FAIL'
        if not case.get('rounds') or any(c.get('source') != 'physical_esp32_minfer'
                                      for r in case['rounds'] for c in r['candidates']):
            return 'FAIL'
        if case['scenario'] in (4,5) and not case.get('sleep',{}).get('ok'):
            return 'BLOCKED'
        if case['scenario'] == 5 and not any(w.get('ok') for w in case.get('wakes',[])):
            return 'FAIL'
    return 'PASS'

def worker_roles(manifest, workers):
    """CUDA execution need not belong to the worker used for sleep tests."""
    low, powerful = manifest['low_power'], manifest['powerful']
    gpu = manifest.get('gpu', powerful)
    if low == powerful or any(ident not in workers.nodes for ident in (low, powerful, gpu)):
        raise ValueError('Low-power and powerful roles must be distinct configured workers')
    return low, powerful, gpu

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--port', required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(args.manifest.read_text())
    workers = Workers(manifest['nodes'])
    low, powerful, gpu = worker_roles(manifest, workers)
    model = json.loads(args.model.read_text())
    if model.get('skills') != NAMES:
        raise ValueError('Model is not the frozen dispatcher contract')
    evidence = {'status': 'BLOCKED', 'created': datetime.now(timezone.utc).isoformat(),
                'model_sha256': proof.sha256(args.model), 'firmware_written': False,
                'profiles': [{k: n[k] for k in ('id','performance','energy_cost','wake_cost')} for n in manifest['nodes']],
                'scenarios': [], 'gate': '18/18 physical correct decisions/executions including actual wake',
                'head_names': NAMES}
    evidence['roles'] = {'low_power': low, 'powerful': powerful, 'gpu': gpu}
    evidence['source_sha256'] = {path.name: proof.sha256(path) for path in Path(__file__).parent.glob('*.py')}
    evidence['model_wake_audit'] = audit_wake(model)
    if evidence['model_wake_audit']['status'] == 'FAIL':
        # Do not suspend a worker when this frozen head cannot ever request wake.
        evidence.update(status='FAIL', error='model_cannot_wake_any_sleeping_candidate',
                        physical_scoring_started=False, model_changed=False)
        (args.output/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
        print('Overall dispatcher gate: FAIL (wake head is negative for every sleeping state)', flush=True)
        return 2
    scorer = HardwareScorer(args.port, model, args.output)
    small = {'kernel': 'cpu', 'count': 4096, 'demand': .05}
    large = {'kernel': 'cpu', 'count': 262144, 'demand': 1.0}
    cuda = {'kernel': 'cuda', 'count': 262144, 'demand': 1.0}
    def save():
        evidence['serial_retries'] = getattr(scorer.device, 'retry_count', 0)
        (args.output/'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')
    try:
        probes = {ident: workers.rpc(ident, {'action': 'probe'}) for ident in workers.nodes}
        evidence['initial_probes'] = probes
        if not all(p.get('ok') for p in probes.values()):
            raise RuntimeError('At least two physical workers must respond before running')
        if len({p.get('worker_id') for p in probes.values()}) != len(probes):
            raise RuntimeError('Worker identity collision')
        fingerprints = {p.get('machine_fingerprint') for p in probes.values()}
        if None in fingerprints or len(fingerprints) != len(probes):
            raise RuntimeError('Need independently identified machines, not two worker instances on one host')
        evidence['distinct_machine_fingerprints_verified'] = True
        for ident, probe in probes.items():
            workers.nodes[ident]['verified_capabilities'] = probe['capabilities']
        if 'cuda' not in probes[gpu]['capabilities']:
            raise RuntimeError('Designated GPU worker lacks CUDA')
        scorer.open()
        evidence['physical_scoring_started'] = True
        for scenario in range(1, 7):
            for repetition in range(1, 4):
                for ident in workers.nodes:
                    workers.rpc(ident, {'action': 'clear'})
                item = {'scenario': scenario, 'repetition': repetition}
                if scenario in (4, 5):
                    asleep = workers.sleep(powerful)
                    item['sleep'] = asleep
                    if not asleep['ok']:
                        item.update(status='BLOCKED', reason=asleep['error'])
                        evidence['scenarios'].append(item)
                        save()
                        continue
                if scenario == 3:
                    item['busy'] = workers.rpc(low, {'action': 'busy', 'seconds': 300})
                    if not item['busy']['ok']:
                        raise RuntimeError('Could not reserve preferred worker')
                task = cuda if scenario == 2 else large if scenario == 5 else small
                expected = gpu if scenario == 2 else powerful if scenario in (3, 5, 6) else low
                result = dispatch(workers, scorer, task, fail_after_selection=scenario == 6)
                item.update(result)
                item['expected'] = expected
                if result.get('completed_on') != expected:
                    item.update(status='FAIL', reason='expected_worker_not_selected')
                if scenario == 6 and (len(result['dispatches']) < 2 or result['dispatches'][0]['id'] != low):
                    item.update(status='FAIL', reason='no_expected_failover_observed')
                if scenario == 5 and not any(w.get('ok') for w in result['wakes']):
                    item.update(status='FAIL', reason='no_actual_wake_observed')
                evidence['scenarios'].append(item)
                save()
                print(f"Scenario {scenario} repeat {repetition}: {item['status']}", flush=True)
                # Restore a test worker left asleep by scenario 4, distinct from a scheduler wake.
                if powerful in workers.sleeping:
                    item['cleanup_wake'] = workers.wake(powerful)
                    if not item['cleanup_wake']['ok']:
                        raise RuntimeError('Test worker recovery failed')
        statuses = [s['status'] for s in evidence['scenarios']]
        evidence['status'] = 'FAIL' if 'FAIL' in statuses else 'BLOCKED' if 'BLOCKED' in statuses else 'PASS'
    except Exception as exc:
        evidence['error'] = str(exc)
    finally:
        for ident in workers.nodes:
            workers.rpc(ident, {'action': 'clear'})
        for ident in list(workers.sleeping | workers.pending_sleep):
            evidence.setdefault('recovery_wakes', []).append({'id': ident, **workers.wake(ident)})
        try:
            scorer.close()
            evidence['original_head_restored'] = bool(scorer.original)
        except Exception as exc:
            evidence.update(status='FAIL', restore_error=str(exc))
        evidence['status'] = gate(evidence)
        save()
    print('Overall dispatcher gate: '+evidence['status'], flush=True)
    return 0 if evidence['status'] == 'PASS' else 2

if __name__ == '__main__':
    raise SystemExit(main())
