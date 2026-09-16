"""Physical ESP32 dispatch with process activation; computers stay awake."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from audit_model import audit_wake
from contract import NAMES
from process_workers import ProcessWorkers
from run import HardwareScorer, dispatch, proof


def gate(evidence):
    cases=evidence['scenarios']
    if evidence.get('error') or evidence.get('restore_error') or any(c['status']=='FAIL' for c in cases):
        return 'FAIL'
    expected={(s,r) for s in range(1,7) for r in range(1,4)}
    if len(cases)!=18 or {(c['scenario'],c['repetition']) for c in cases}!=expected:
        return 'BLOCKED'
    if not evidence.get('original_head_restored') or not evidence.get('distinct_machine_fingerprints_verified'):
        return 'BLOCKED'
    if not evidence.get('worker_cleanup_complete'):
        return 'FAIL'
    for c in cases:
        if c['status']!='PASS' or not c.get('dispatches') or not c['dispatches'][-1].get('correct'):
            return 'FAIL'
        if not c.get('rounds') or any(n.get('source')!='physical_esp32_minfer'
                                    for r in c['rounds'] for n in r['candidates']):
            return 'FAIL'
        if c['scenario'] in (4,5):
            idle=c.get('idle',{})
            if not (idle.get('ok') and idle.get('kind')=='dedicated_worker_process_exit'
                    and idle.get('exit_code')==0 and idle.get('host_awake',{}).get('ok')):
                return 'FAIL'
        if c['scenario']==4 and c['wakes']:
            return 'FAIL'
        if c['scenario']==5:
            activated=[w for w in c['wakes'] if w.get('ok') and w.get('kind')=='worker_process_activation'
                       and w.get('host_awake',{}).get('ok')]
            if not activated or len(c['rounds'])<2:
                return 'FAIL'
            if activated[0]['ready'].get('instance')==c['idle']['exit_receipt'].get('instance'):
                return 'FAIL'
    return 'PASS'


def main():
    p=argparse.ArgumentParser()
    for name in ('manifest','model','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--port',required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads(args.manifest.read_text())
    model=json.loads(args.model.read_text())
    if model.get('contract')!='worker-process-v3' or model.get('skills')!=NAMES:
        raise ValueError('Need separately frozen worker-process-v3 model')
    workers=ProcessWorkers(manifest['nodes'])
    low, high=manifest['low_power'],manifest['powerful']
    if low==high or {low,high}!=set(workers.nodes):
        raise ValueError('This frozen run requires exactly two worker roles')
    evidence=dict(status='BLOCKED',created=datetime.now(timezone.utc).isoformat(),
        contract='worker-process-v3',model_sha256=proof.sha256(args.model),
        firmware_written=False,operating_system_power_operations=False,scenarios=[],
        profiles=[{k:n[k] for k in ('id','performance','energy_cost','wake_cost')} for n in manifest['nodes']],
        source_sha256={path.name:proof.sha256(path) for path in Path(__file__).parent.glob('*.py')})
    scorer=HardwareScorer(args.port,model,args.output)
    def save():
        evidence['serial_retries']=getattr(scorer.device,'retry_count',0)
        (args.output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    try:
        evidence['wake_capability']=audit_wake(model)
        if evidence['wake_capability']['status']=='FAIL':
            raise RuntimeError('Model cannot request activation for an inactive worker')
        initial={ident:workers.wake(ident) for ident in workers.nodes}
        evidence['initial_workers']=initial
        if not all(r['ok'] for r in initial.values()):
            raise RuntimeError('Worker startup failed')
        identities={r['ready']['machine_fingerprint'] for r in initial.values()}
        if len(identities)!=2:
            raise RuntimeError('Workers must run on two distinct physical computers')
        evidence['distinct_machine_fingerprints_verified']=True
        if 'cuda' not in initial[high]['ready']['capabilities']:
            raise RuntimeError('GPU worker lacks CUDA')
        scorer.open()
        for scenario in range(1,7):
            for repetition in range(1,4):
                for ident in workers.nodes:
                    if ident in workers.sleeping:
                        if not workers.wake(ident)['ok']:
                            raise RuntimeError('Could not reset experiment worker process')
                    if not workers.rpc(ident,{'action':'clear'})['ok']:
                        raise RuntimeError('Could not clear dedicated-worker faults')
                item={'scenario':scenario,'repetition':repetition}
                if scenario in (4,5):
                    item['idle']=workers.idle(high)
                    if not item['idle']['ok']:
                        raise RuntimeError('Dedicated worker did not exit while its host remained reachable')
                if scenario==3:
                    item['busy']=workers.rpc(low,{'action':'busy','seconds':300})
                    if not item['busy']['ok']:
                        raise RuntimeError('Busy reservation failed')
                task=dict(kernel='cuda' if scenario==2 else 'cpu',
                          count=262144 if scenario in (2,5) else 4096,
                          demand=1. if scenario in (2,5) else .05)
                result=dispatch(workers,scorer,task,fail_after_selection=scenario==6)
                item.update(result)
                expected=high if scenario in (2,3,5,6) else low
                item['expected']=expected
                if result.get('completed_on')!=expected:
                    item.update(status='FAIL',reason='expected_worker_not_selected')
                if scenario==6 and (len(result['dispatches'])<2 or result['dispatches'][0]['id']!=low):
                    item.update(status='FAIL',reason='no_expected_failover_observed')
                if scenario==4 and result['wakes']:
                    item.update(status='FAIL',reason='unnecessary_worker_activation')
                if scenario==5 and not any(w.get('ok') for w in result['wakes']):
                    item.update(status='FAIL',reason='no_real_process_activation')
                evidence['scenarios'].append(item)
                save()
                print(f'Scenario {scenario} repeat {repetition}: {item["status"]}',flush=True)
    except Exception as exc:
        evidence['error']=str(exc)
    finally:
        try:
            workers.close()
            evidence['worker_cleanup_complete']=all(s['process'].poll() is not None for s in workers.sessions.values())
        except Exception as exc:
            evidence['cleanup_error']=str(exc)
        try:
            scorer.close()
            evidence['original_head_restored']=bool(scorer.original)
        except Exception as exc:
            evidence['restore_error']=str(exc)
        evidence['status']=gate(evidence)
        save()
    print('Worker-process gate: '+evidence['status'],flush=True)
    return 0 if evidence['status']=='PASS' else 2


if __name__=='__main__':
    raise SystemExit(main())
