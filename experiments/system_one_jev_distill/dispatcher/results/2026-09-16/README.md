# Dispatcher experiment: partial physical result

**Overall gate: BLOCKED. Twelve physical runs passed; six sleep/wake runs could
not run. This is not merge acceptance.** The first Jev experiment remains FAIL.

## What ran

The existing V2.0.1 ESP32 scored a physical aarch64 Linux R1 worker and the
Windows RTX 3050 computer hosting the controller. New weights were learned from
512 independent Jev candidate states (`jev-1.13.0`, SDK 0.6.0, seed 2102), then
frozen before testing. The controller used only the returned logits for worker
selection through the fixed reducer; it did not override a selected worker.

The final recorded run verifies distinct hashed OS machine identities, every
installed coefficient, and every candidate's device outputs. The earlier run
also passed all twelve runnable cases; its private evidence is preserved. This
report uses the later run after strengthening identity and completion checks.

| Scenario | Physical result | Selected worker | Median end-to-end time |
|---|---|---|---:|
| 1. Small CPU work | 3/3 PASS | R1 | 1.860 s |
| 2. CUDA work | 3/3 PASS | RTX 3050 | 1.281 s |
| 3. Preferred worker busy | 3/3 PASS | RTX 3050 CPU fallback | 1.188 s |
| 4. Small work while powerful worker sleeps | 3 BLOCKED | No selection claimed | — |
| 5. Work justifies real wake | 3 BLOCKED | No wake claimed | — |
| 6. Selected worker becomes unavailable | 3/3 PASS | R1 fails, then RTX 3050 CPU | 4.922 s |

Each completed task ran an integer-transform kernel and returned the expected
SHA-256 digest. Scenario 2 launched an actual CUDA PTX kernel through the NVIDIA
driver; it did not substitute CPU execution. Scenario 3 occupied only the
dedicated experiment worker with a bounded reservation and CPU loop. Scenario 6
injected unavailability into that worker after selection, observed a failed
execution, rescored both candidates on the ESP32, and completed on the alternate
computer. No production service or machine network was disabled.

These timings include SSH/process launch, telemetry, scoring and execution.
They are not inference latency or evidence of acceleration. Power/performance
profiles are declared proxies, not measured watts or an energy-efficiency result.
This is a finite experiment harness, not a deployed always-on dispatch service.

## Numerical and training evidence

- 30 physical candidate evaluations / 240 head outputs; maximum absolute score
  error **0.0000007031253**, within 0.00002. Zero serial retries in the final run.
- Nine basis vectors validated all 72 installed coefficients before routing and
  validated the restored original head afterward. No SAVE, firmware flashing,
  or settings erase was performed. The first experiment's saved head remains.
- New model held-out Jev agreement: **95.2670%**; probability MAE **0.046427**;
  maximum Q10 probability delta **0.000446043**. 409 training / 103 held-out states.
- `use_candidate` agreement **91.2621%**, versus **60.1942%** majority baseline.
- `wake_candidate` agreement **95.1456%**, equal to its majority baseline. This
  does not establish useful wake behavior; the missing physical tests matter.
- Weakest head `reject_candidate`: **81.5534%** agreement. New training metrics
  are descriptive, not a replacement for the six-scenario physical gate.

## Why the gate is blocked

The available GPU worker is also the active ESP32 controller. Suspending it
would stop the controller and its USB scoring link. The configured second
Windows desktop was offline and its SSH connection timed out. The Pi was online,
but its Tailscale SSH policy rejected the attempted username. The R1 was reachable
and provided real independent execution.

Completion needs a separate GPU worker that is reachable, safe to suspend, and
has a verified wake path plus independent sleep-state evidence. Then rerun all
six cases against the frozen model.

The harness supplies power-adapter integration points, but their real behavior
has not been validated. Neither an SSH outage nor a mocked wake is counted as a
sleep/wake success. The PR must remain open until the owner's physical gate is met.

## Artifacts

- [summary.json](summary.json): counts, timings, hashes, source provenance.
- [physical-evidence.json](physical-evidence.json): candidate states, all eight
  outputs, every selection, dispatch receipt, injected fault, retry count and
  blocked reason, with private identifiers omitted.
- [rows.json](rows.json): frozen 8x9 Q10 model.
- [training-report.json](training-report.json): per-head held-out metrics/baselines.
- [teacher.metadata.json](teacher.metadata.json): exact questions/API/SDK identity.
- [Protocol and reproduction](../../README.md).

Private raw evidence: `_local/dispatcher-physical-20260916-b/`; earlier run:
`_local/dispatcher-physical-20260916-a/`; teacher dataset:
`_local/dispatcher-20260916-2102/`. No credentials, network addresses, OS machine
fingerprints, original packets or raw serial device identity are published here.

Local validation: 12 new dispatcher boundary/routing/gate tests, 10 parent
experiment tests, and 11 existing V2 fixture/parser tests pass. CI runs the new
dispatcher tests separately from physical acceptance.
