import hashlib
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contract import FEATURES, choose, project
from run import Workers, dispatch, gate
from worker import cpu_transform, handle

GOOD = [2., -1., -2., 2., 2., -2., -2., -2.]

class ContractTests(unittest.TestCase):
    def test_projection_rejects_nonfinite_and_out_of_range(self):
        state = dict.fromkeys(FEATURES, 1)
        self.assertEqual(project(state), [1]*9)
        for value in (math.nan, math.inf, -1, 2):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    project({**state, 'energy_cost': value})

    def test_ineligible_high_scorer_never_wins(self):
        for index, invalid in ((2,1),(3,-1),(4,-1),(5,1),(7,1),(0,-1)):
            y = GOOD.copy()
            y[0] = 100
            y[index] = invalid
            self.assertEqual(choose([{'id':'bad','y8':y},{'id':'good','y8':GOOD}])['id'],'good')

    def test_ranking_uses_scores_and_ties_are_order_independent(self):
        candidates = [{'id':'a','y8':GOOD}, {'id':'b','y8':[3]+GOOD[1:]}]
        self.assertEqual(choose(candidates)['id'],'b')
        self.assertEqual(choose(candidates[::-1])['id'],'b')
        candidates[1]['y8'] = GOOD
        self.assertEqual(choose(candidates[::-1])['id'],'a')

    def test_no_eligible_candidate_is_explicit(self):
        self.assertIsNone(choose([{'id':'bad','y8':[-1]*8}]))

class WorkerTests(unittest.TestCase):
    def test_cpu_receipt_matches_independent_known_vector(self):
        self.assertEqual(cpu_transform(2).hex(), '5ff36e3c6c59883c')
        with tempfile.TemporaryDirectory() as directory:
            reply = handle({'action':'execute','kernel':'cpu','count':2},Path(directory))
            self.assertEqual(reply['sha256'],hashlib.sha256(bytes.fromhex('5ff36e3c6c59883c')).hexdigest())

    def test_unavailable_fault_is_worker_local_and_reversible(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            self.assertTrue(handle({'action':'unavailable','seconds':30},directory)['ok'])
            self.assertFalse(handle({'action':'execute','kernel':'cpu','count':2},directory)['ok'])
            handle({'action':'clear'},directory)
            self.assertTrue(handle({'action':'execute','kernel':'cpu','count':2},directory)['ok'])

    def test_worker_rejects_unbounded_or_unknown_work(self):
        with tempfile.TemporaryDirectory() as directory:
            for request in ({'action':'execute','kernel':'shell','count':1},
                            {'action':'execute','kernel':'cpu','count':2**30},
                            {'action':'sleep'}):
                with self.assertRaises(ValueError):
                    handle(request,Path(directory))

    def test_active_controller_cannot_be_suspended(self):
        nodes = [dict(id=n, argv=['unused'], performance=1, energy_cost=1, wake_cost=1,
                      is_controller=True,safe_to_suspend=True,sleep_argv=['unused']) for n in ('a','b')]
        workers = Workers(nodes)
        with patch('run.subprocess.run') as execute:
            self.assertFalse(workers.power_command('a','sleep_argv')['ok'])
            execute.assert_not_called()

class RoutingTests(unittest.TestCase):
    def test_partial_or_mock_results_cannot_pass_physical_gate(self):
        self.assertEqual(gate({'scenarios':[]}), 'BLOCKED')
        cases = [dict(scenario=s,repetition=r,status='PASS',
                      dispatches=[{'correct':True}],rounds=[{'candidates':[{'source':'mock'}]}],
                      sleep={'ok':True},wakes=[{'ok':True}]) for s in range(1,7) for r in range(1,4)]
        evidence = dict(scenarios=cases,original_head_restored=True,distinct_machine_fingerprints_verified=True)
        self.assertEqual(gate(evidence),'FAIL')
        for case in cases:
            case['rounds'][0]['candidates'][0]['source'] = 'physical_esp32_minfer'
        cases[12]['status'] = 'BLOCKED'
        self.assertEqual(gate(evidence),'BLOCKED')

    def test_numerical_failure_during_physical_run_is_failure_not_blocker(self):
        self.assertEqual(gate(dict(scenarios=[],error='bad score',physical_scoring_started=True)), 'FAIL')

    def test_failed_selection_is_rescored_before_failover(self):
        class FakeWorkers:
            nodes = {'a':{}, 'b':{}}
            failed = False
            def states(self, task):
                return self.failed
            def rpc(self, ident, request):
                if request['action'] == 'unavailable':
                    self.failed = True
                    return {'ok':True}
                if ident == 'a' and self.failed:
                    return {'ok':False}
                return {'ok':True,'kernel':'cpu','count':2,'sha256':hashlib.sha256(cpu_transform(2)).hexdigest()}
        class FakeScorer:
            calls = 0
            def score(self, failed):
                self.calls += 1
                return [{'id':'b' if failed else 'a','y8':GOOD,'state':{'readiness':1}}]
        scorer = FakeScorer()
        result = dispatch(FakeWorkers(),scorer,{'kernel':'cpu','count':2},True)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['completed_on'],'b')
        self.assertEqual(scorer.calls,2)
        self.assertFalse(result['dispatches'][0]['correct'])

    def test_wrong_output_cannot_pass(self):
        class FakeWorkers:
            nodes = {'a':{}, 'b':{}}
            def states(self, task):
                return []
            def rpc(self, ident, request):
                return {'ok':True,'kernel':'cpu','count':2,'sha256':'wrong'}
        class FakeScorer:
            def score(self, candidates):
                return [{'id':'a','y8':GOOD,'state':{'readiness':1}}]
        result = dispatch(FakeWorkers(),FakeScorer(),{'kernel':'cpu','count':2})
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['reason'],'incorrect_worker_output')

if __name__ == '__main__':
    unittest.main()
