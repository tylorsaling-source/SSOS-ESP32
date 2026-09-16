# Corrected experiment: wake worker processes, keep computers awake

Owner clarification on 2026-09-16 supersedes the earlier computer sleep/wake
interpretation. No suspend, shutdown, reboot, Wake-on-LAN, power-plan changes,
or scheduled power tasks are part of this protocol. Historical attempts remain
evidence of the mistaken interpretation and are not acceptance for this run.

The controller and ESP32 remain on Gamer. Dedicated experiment Python workers
run on Gamer (CUDA/CPU) and R1 (CPU), over inherited local pipes or authenticated
SSH. A worker is inactive only after it acknowledges exit and its owned process
exits. Starting a worker must produce a new instance identifier and real ready
receipt. Host witnesses before and after activation must show the same boot
identity. No machine power operation is implemented in the process adapter.

## Frozen candidate, before collection and physical testing

- Contract `worker-process-v3`, same eight features, eight outputs, and 72 Q10
  weights. Readiness 0 means the dedicated process is stopped on a reachable
  awake host; -1 means unavailable, and +1 means worker process ready.
- The eight teacher questions are in `worker_contract.py`. All labels come from
  live Jev; no manually assigned labels or winner override is permitted.
- Collect 512 states with seed 2103. Half deliberately cover healthy inactive
  workers across benefit/cost combinations; the remaining half mix ready,
  inactive and unavailable states. Generation is independent of named workers.
- Use the fixed 80/20 split. Train seven heads as before. Since wake is consumed
  only for readiness 0, fit that head on the readiness-0 training subset only,
  using 2,400 gradient steps at learning rate 0.15. Evaluate it on the held-out
  inactive subset, reporting positive and negative recall as well as agreement
  and majority baseline. Do not tune against the physical outcomes.
- Freeze rows before physical testing, reject Q10 overflow and an impossible
  activation score, and preserve any failures. Old datasets/models are unchanged.
- Declared profiles: R1 performance 0.25, execution energy 0.1, process startup
  cost 0.05; Gamer performance 1.0, execution energy 0.9, process startup cost
  0.05. These are proxies, not measured energy or startup duration.

## Acceptance

Three physical repetitions of each: (1) small CPU work on ready R1, (2) CUDA
work on ready Gamer, (3) busy R1 fallback to Gamer, (4) Gamer worker inactive and
small work stays on R1 without activating Gamer's worker, (5) substantial work
activates Gamer's worker, observes readiness, rescores and executes there,
(6) selected R1 worker becomes unavailable, then ESP32 rescores and dispatches
to Gamer. Faults affect only dedicated experiment workers.

PASS requires 18/18 correct results, actual ESP32 candidate scoring, verified
output digests, real process exit/start evidence, awake host witnesses, two
distinct physical host identities, and restoration of the prior ESP32 head.
Synthetic input checks, mocked lifecycle tests, and a training report cannot
replace this gate. There is no firmware flash or SAVE. Original model rows are
backed up, restored and numerically verified. End-of-run cleanup exits only
worker processes owned by this run and clears their temporary reservations.
