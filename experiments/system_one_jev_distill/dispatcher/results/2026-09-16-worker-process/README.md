# Corrected worker-process experiment: completed, FAIL (15/18)

All 18 planned repetitions ran on the physical ESP32, Gamer and R1. **15 passed,
3 failed, none blocked.** The three failures are learned routing/activation
failures, not missing hardware or unrun tests. The PR remains unmerged.

The owner clarified that wake means activating dedicated worker processes on
awake computers. The earlier computer power interpretation was wrong. No host
power operations occurred in this corrected run. The laptop affected by the
earlier preflight was manually recovered, and both temporary power tasks were
removed and their absence independently verified.

## Results

| Scenario | Result, three repetitions |
|---|---|
| Small CPU task -> ready R1 worker | 3 PASS |
| CUDA task -> ready Gamer worker | 3 PASS |
| R1 worker busy -> Gamer worker | 3 PASS |
| Gamer worker stopped, small task -> R1 without activation | 3 PASS |
| Substantial task -> activate Gamer worker, rescore, dispatch | 3 FAIL |
| R1 unavailable after selection -> rescore and execute on Gamer | 3 PASS |

In all three scenario-5 runs the Gamer process was genuinely stopped, with its
host still responsive. The ESP32 returned approximately:

| Candidate | Use score | Activation score |
|---|---:|---:|
| Ready R1 worker | 0.993359 | -0.965234 |
| Inactive Gamer worker | -0.186963 | 0.526831 |

The deterministic reducer requires nonnegative suitability before selection.
It therefore selected R1. The positive activation score did not override the
negative suitability score, and no model-driven Gamer activation occurred.
The substantial CPU task completed correctly on R1, but that violates the
predeclared expected routing and activation behavior. This is a failure of the
candidate under this protocol; the code does not override the learned decision.
No post-result profile, threshold or weight tuning was used to convert it to PASS.

Independent transport preflight did successfully exit and restart actual worker
processes on both hosts, with distinct process instances and awake-host witnesses.
That proves the process lifecycle mechanism works; it does not substitute for
the missing model-driven activation in scenario 5.

## Evidence and validation

- 42 physical candidate evaluations / 336 ESP32 outputs; maximum absolute
  numerical error `8.75e-7`, zero serial retries in the complete run.
- All 18 completed task output digests verified. Scenario 6 also records the
  expected failed first dispatch before the alternate succeeds.
- Previous ESP32 head restored and all coefficients verified. No SAVE, firmware
  flashing or settings erase. Every owned resident worker exited at cleanup.
- Two earlier attempts stopped on incomplete bulk DUMP replies before model
  replacement. They remain recorded in [summary.json](summary.json). Reading
  each of the eight model rows with the existing GET command fixed backup
  collection; no firmware or serial control-line changes were needed.
- 21 local dispatcher tests pass, including actual child-process exit/restart,
  EOF cleanup, boot identity checks, and rejection of mocked/incomplete evidence.
- [Physical evidence](physical-evidence.json) includes all candidate inputs and
  outputs, selections, receipts, worker exits, host witnesses, retries and timings.
  [Lifecycle preflight](process-lifecycle-preflight.json) is separate from model
  routing evidence. Private identities/addresses/raw packets remain excluded.

## Training and limits

This is a separate 512-state live Jev dataset, `jev-1.13.0`, seed 2103; 409 training
and 103 held-out examples. The [protocol](../../WORKER_PROCESS_PROTOCOL.md) was
fixed before collection. The activation head was trained only on inactive-worker
training states because it is consumed only in that state; all target values
still came from Jev. Model rows were frozen before hardware testing.

Suitability held-out agreement: **89.32%**, majority baseline **80.58%**.
Activation agreement on 71 held-out inactive states: **78.87%**, baseline
**64.79%**, positive recall **56.0%**, negative recall **91.30%**. These metrics
show substantial remaining errors; they are not production reliability claims.
See [training-report.json](training-report.json), [rows.json](rows.json), and
[teacher metadata](teacher.metadata.json).

The two computers, bounded CPU/CUDA kernels, declared performance/energy proxies
and finite scenario set limit this evidence. This is not an always-on deployed
scheduler. Earlier models, their failures, and the mistaken power preflight are
preserved. The next research question is how to make suitability and activation
judgments consistent within the fixed 72-weight head; this run does not answer it.
