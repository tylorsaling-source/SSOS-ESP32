import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from process_workers import ProcessWorkers
from run_workers import gate


class ProcessLifecycleTests(unittest.TestCase):
    def test_real_process_exits_and_restarts_without_host_power_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            nodes=[]
            for name in ('a','b'):
                nodes.append(dict(id=name, argv=['unused'],
                    serve_argv=[sys.executable,str(Path(__file__).with_name('worker.py')),
                                '--directory',str(Path(tmp)/name),'--serve'],
                    performance=1, energy_cost=1, wake_cost=.1, is_controller=True,
                    host_probe_argv=[sys.executable,'-c',
                        'import json; print(json.dumps({"ok": True, "boot_id": "fixture-boot"}))']))
            workers=ProcessWorkers(nodes)
            try:
                first=workers.wake('a')
                self.assertTrue(first['ok'])
                self.assertTrue(workers.rpc('a',{'action':'execute','kernel':'cpu','count':2})['ok'])
                idle=workers.idle('a')
                self.assertTrue(idle['ok'])
                self.assertEqual(idle['exit_code'],0)
                self.assertFalse(workers.rpc('a',{'action':'probe'})['ok'])
                second=workers.wake('a')
                self.assertTrue(second['ok'])
                self.assertNotEqual(first['ready']['instance'],second['ready']['instance'])
                with self.assertRaises(RuntimeError): workers.sleep('a')
                with self.assertRaises(RuntimeError): workers.power_command('a','sleep_argv')
            finally:
                workers.close()
            self.assertTrue(all(s['process'].poll() is not None for s in workers.sessions.values()))

    def test_boot_identity_change_refuses_activation(self):
        nodes=[dict(id=n,argv=['unused'],serve_argv=['must-not-start'],
                    host_probe_argv=['probe'],performance=1,energy_cost=1,wake_cost=1)
               for n in ('a','b')]
        workers=ProcessWorkers(nodes)
        workers.host_baselines['a']='old'
        with patch('process_workers.subprocess.run') as probe, patch('process_workers.subprocess.Popen') as start:
            probe.return_value.returncode=0
            probe.return_value.stdout=json.dumps({'ok':True,'boot_id':'different'})
            self.assertFalse(workers.wake('a')['ok'])
            start.assert_not_called()

    def test_worker_eof_exits_without_a_shutdown_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('worker.py')),
                                   '--directory',tmp,'--serve'],input='',capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0)
            self.assertEqual(json.loads(result.stdout)['event'],'ready')


class ProcessGateTests(unittest.TestCase):
    def evidence(self):
        cases=[]
        for s in range(1,7):
            for r in range(1,4):
                case=dict(scenario=s,repetition=r,status='PASS',dispatches=[{'correct':True}],
                          rounds=[{'candidates':[{'source':'physical_esp32_minfer'}]}],wakes=[])
                if s in (4,5):
                    case['idle']=dict(ok=True,kind='dedicated_worker_process_exit',exit_code=0,
                                      host_awake={'ok':True},exit_receipt={'instance':'old'})
                if s==5:
                    case['rounds']*=2
                    case['wakes']=[dict(ok=True,kind='worker_process_activation',host_awake={'ok':True},
                                       ready={'instance':'new'})]
                cases.append(case)
        return dict(scenarios=cases,original_head_restored=True,
                    worker_cleanup_complete=True,distinct_machine_fingerprints_verified=True)

    def test_missing_new_process_or_awake_host_cannot_pass(self):
        valid=self.evidence()
        self.assertEqual(gate(valid),'PASS')
        valid['scenarios'][12]['wakes'][0]['ready']['instance']='old'
        self.assertEqual(gate(valid),'FAIL')
        valid=self.evidence()
        valid['scenarios'][12]['idle']['host_awake']['ok']=False
        self.assertEqual(gate(valid),'FAIL')
        valid=self.evidence()
        valid['scenarios'][9]['wakes']=[{'ok':True}]
        self.assertEqual(gate(valid),'FAIL')

    def test_partial_or_mocked_run_cannot_pass(self):
        valid=self.evidence()
        valid['scenarios'][0]['rounds'][0]['candidates'][0]['source']='mock'
        self.assertEqual(gate(valid),'FAIL')
        valid=self.evidence()
        valid['scenarios'].pop()
        self.assertEqual(gate(valid),'BLOCKED')


if __name__=='__main__':
    unittest.main()
