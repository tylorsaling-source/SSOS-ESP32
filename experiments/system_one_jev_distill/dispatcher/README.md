# Learned compute dispatcher: worker processes on awake computers

**Latest result: all 18 corrected physical repetitions completed, 15 PASS / 3 FAIL.**
Read the [worker-process report](results/2026-09-16-worker-process/README.md).
The activation mechanism works, but the frozen model failed to select the
inactive GPU worker in the three cases that required activation. This is an
experimental failure, not a completed working scheduler. The PR stays unmerged.

## Scope and decision authority

The owner's clarification is authoritative: activate worker processes, keep
computers awake. No suspend, shutdown, reboot, Wake-on-LAN, or scheduled power
tasks belong in this experiment. The earlier host-power interpretation was a
mistake; its adapters are now disabled. Gamer can remain both the always-awake
controller with the ESP32 attached and the GPU worker host.

The existing V2.0.1 ESP32 computes eight candidate scores with MINFER. A fixed
host reducer filters capability/busy/reliability/freshness/reject outputs and
selects the largest eligible use score. It cannot substitute a preferred worker.
An inactive selected worker starts only when its activation score is nonnegative.
After readiness, all candidates are rescored before actual work is dispatched.
Failures trigger another physical ESP32 decision, with verified result digests.
There is no host-model fallback, firmware change, SAVE, or arbitrary task shell.

## Current protocol and files

The [frozen worker-process protocol](WORKER_PROCESS_PROTOCOL.md) describes the
features, Jev questions, training split, declared profiles, six scenarios and
18-run acceptance gate. Readiness 0 means a stopped dedicated process on an
awake, reachable host. Starting that process must produce a new instance and
real ready receipt. Exiting it must leave its computer responsive.

- `worker_contract.py`: revised Jev questions; same 8 features / 8 outputs / 72 weights.
- `train_workers.py`: separately collected and frozen worker-process model.
- `worker.py --serve`: bounded CPU/CUDA worker over local pipes or authenticated SSH.
- `process_workers.py`: lifecycle and request/response handling for owned processes.
- `host_witness.py`: read-only host responsiveness and boot identity.
- `run_workers.py`: physical ESP32 routing and process-activation acceptance.
- `audit_model.py`: analytical check that the activation output can become nonnegative.
- `run.py`: shared serial scorer and dispatch reducer, plus historical harness;
  its operating-system power adapter always refuses execution.

Earlier models and reports remain historical evidence:
[original dispatcher run](results/2026-09-16/README.md),
[old model's impossible wake output](results/2026-09-16-wake-audit/README.md).
The parent Jev experiment and its original FAIL outcome are unchanged.

## Running

Install the parent numpy/typesafe-sdk/pyserial dependencies. Copy `worker.py`
and `host_witness.py` into a dedicated scratch folder on an authorized remote
host. The worker uses only standard Python plus the installed NVIDIA driver for
CUDA. It opens no listening port. Use an existing authenticated SSH connection;
never put credentials in a manifest or command argument.

A private manifest has `low_power`, `powerful` and exactly two `nodes`. Each node
contains `id`, `argv`, `serve_argv`, `host_probe_argv`, `performance`, `energy_cost`
and `wake_cost`. `serve_argv` runs `worker.py --directory PRIVATE_PATH --serve`;
`host_probe_argv` runs `host_witness.py` on the same host. Commands are fixed
trusted arrays, independent of model output. See [worker-process example](worker-manifest.example.json).
Private manifests, keys, identities and serial transcripts stay under `_local`.

With the existing API key supplied securely only to the collector process:

```powershell
python experiments/system_one_jev_distill/dispatcher/train_workers.py experiments/system_one_jev_distill/_local/NEW-TRAINING --collect
```

This performs 512 paid Jev requests and refuses to overwrite collected/frozen
artifacts. Prior results must remain unchanged. Freeze and review the model
before physical testing:

```powershell
python experiments/system_one_jev_distill/dispatcher/run_workers.py --manifest experiments/system_one_jev_distill/_local/machines.json --model experiments/system_one_jev_distill/_local/NEW-TRAINING/rows.json --port COM13 --output experiments/system_one_jev_distill/_local/NEW-PHYSICAL-RUN
```

The output directory must not exist. The harness backs up all eight existing
model rows using individual GET commands, temporarily installs the candidate,
checks every coefficient and score, then restores and verifies the previous
head. Dedicated worker processes and temporary busy/unavailable reservations
are cleaned up at exit. The controller process and computer power are untouched.

A PASS requires real routing, correct work, model-driven activation, physical
ESP32 scoring, distinct hosts and successful restoration. Process startup
preflight or offline tests cannot substitute for learned activation evidence.
