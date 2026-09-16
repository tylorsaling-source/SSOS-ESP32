# Experiment 2: learned compute dispatcher (protocol frozen before collection)

This follows the owner's [PR #21 request](https://github.com/tylorsaling-source/SSOS-ESP32/pull/21#issuecomment-5698714088).
The first experiment and its FAIL gate remain unchanged. This experiment has a
different state contract and new Jev labels; its model is not the first model.
No validated firmware, model shape, or packet format is changed.

## Decision authority

The V2.0.1 ESP32 scores each candidate separately with MINFER. A deterministic
host reducer filters on the returned capability/busy/reliability/freshness/reject
outputs, then chooses the largest returned use_candidate logit. Ties use stable
candidate IDs. The host does not substitute a preferred machine or calculate a
replacement utility score. V2.0.1 has no cross-candidate scheduling command:
the reducer is host-side SSOS orchestration, not a new on-device capability.
All eight scores and every projection are logged. Transport errors stop scoring;
there is no host-model fallback in physical mode.

After a selected worker fails dispatch, mark its actual health unavailable,
rescore all candidates on the ESP32, and use the new winner. The executor accepts
only fixed bounded test kernels and verifies results; no model-produced shell
command is executed. A worker refusing execution is a failed dispatch, never a
successful scheduling result. Wake is issued only for a model-selected sleeping
worker whose wake_candidate score is nonnegative. Poll actual readiness and
rescore before dispatch; a magic packet alone does not prove wake.

## Candidate projection (eight features plus constant bias)

| Feature | Meaning before normalization |
|---|---|
| capable | 0/1: worker supports this task's CPU or CUDA kernel |
| readiness | -1: unavailable; 0: confirmed sleeping and wake configured; +1: ready |
| free_capacity | 0..1: experiment worker queue availability |
| reliability | 0..1: observed transport health |
| work_value | 0..1: task demand times configured worker performance profile |
| energy_cost | 0..1: configured relative energy cost, not measured watts |
| wake_cost | 0..1: configured startup penalty; zero for ready workers |
| freshness | 0..1: freshness of telemetry, decays to zero at 30 seconds |

All features except readiness map from [0,1] to [-1,1]. A ninth constant 1 is
the bias. No candidate name, expected winner, or other candidate's score enters
the model. Profiles are declared in the private machine manifest and logged
without network addresses. Do not mislabel configured power/performance proxies
as measurements. Unreachable alone does not mean sleeping.

## Training and acceptance

Collect 512 new generated candidate states from Jev, seed 2102. Fit the existing
8x9 logistic head, quantize to Q10, and retain the original deterministic 80/20
split. Publish per-head held-out agreement and majority baselines. This is
descriptive training evidence; it is not the physical acceptance gate.

Freeze the resulting rows before physical tests. Run each of these six scenarios
three times with actual worker execution and verified output:

1. Small CPU task chooses an awake low-power worker.
2. CUDA task selects the CUDA worker (awake or actually awakened).
3. Preferred worker occupied by an experiment reservation: choose the alternate.
4. Sleeping powerful worker, small task: remain on an awake low-power worker.
5. Large task justifies real wake, readiness wait, rescore, and dispatch.
6. Selected worker becomes unavailable: failed execution, rescore, and alternate
   physical execution. Inject failure only in the dedicated experiment worker.

PASS requires 18/18 correct selections and correct completed results, including
real computer sleep/wake in scenarios 4/5, at least two distinct physical worker
computers, and an actual ESP32 response for every scheduling decision. Record
candidate inputs, all outputs, chosen node, wake requests/readiness, task output,
failover/retries and timings. Any unavailable prerequisite is BLOCKED; any wrong
decision/result is FAIL. Simulated worker states and mocked wake tests cannot
make this gate pass. Keep partial evidence, including failures.

The active controller must never suspend itself. Remote sleep requires an
explicitly designated, safe-to-suspend test worker. No broad firewall changes,
public services, or production worker shutdowns are part of this experiment.

## Files

`contract.py` owns projections, Jev questions and score reduction. `train.py`
collects new teacher labels and freezes rows. `worker.py` runs a small standalone
JSON/stdin CPU/CUDA worker over existing authenticated SSH or locally.
`run.py` drives serial scoring and physical routing using a private manifest.
Generated/private files belong under the parent experiment's gitignored `_local`.

## Running the harness

Install the parent experiment's numpy/typesafe-sdk/pyserial dependencies. Copy
`worker.py` to a dedicated scratch folder on each authorized worker using existing
SSH access. Its standard-library CPU kernel has no dependencies. CUDA execution
uses the installed NVIDIA driver and an embedded PTX integer-transform kernel;
probe checks driver availability, and dispatch verifies actual device output.
The task returns a SHA-256 digest of the output buffer. Fault injection occupies
or disables only this temporary experiment worker for at most 300 seconds.

Copy `manifest.example.json` into `_local`, replace SSH aliases and worker paths,
and declare the controller accurately. The two roles must identify different
physical computers: preflight requires distinct hashed OS machine identities.
Those hashes remain private. The harness uses no inbound worker listener.

With `TYPESAFE_API_KEY` supplied securely in the process environment, collect a
new dataset into a new private directory (512 paid API requests):

```powershell
python experiments/system_one_jev_distill/dispatcher/train.py experiments/system_one_jev_distill/_local/NEW-RUN --collect
```

Omit `--collect` to refit an existing dataset without API calls. Keep its frozen
rows and report before changing any training choice. Then run:

```powershell
python experiments/system_one_jev_distill/dispatcher/run.py --manifest experiments/system_one_jev_distill/_local/machines.json --model experiments/system_one_jev_distill/_local/NEW-RUN/rows.json --port COM13 --output experiments/system_one_jev_distill/_local/NEW-PHYSICAL-RUN
```

The output directory must not exist. The harness backs up the current model,
installs the dispatcher temporarily, validates every coefficient on the ESP32,
checks each subsequent device output against the frozen rows, then restores and
revalidates the prior head in `finally`. It does not SAVE or flash firmware.
Keep original-packets.txt and serial.txt private; they can contain device data.

Real power tests additionally require a designated external test worker with
`safe_to_suspend: true` and three trusted command arrays: `sleep_argv`,
`sleep_witness_argv`, and `wake_argv`. Their exit code must indicate success.
The witness must independently confirm sleep (for example, an external management
controller's power-state check). Merely checking that SSH fails is insufficient.
No generic power adapters are supplied because capabilities and wake delivery
depend on the actual machine and network. Never put credentials in these arrays.
Without these prerequisites, cases 4 and 5 are recorded BLOCKED automatically.

Worker selection uses the ESP32 outputs; a CPU calculation only checks numerical
integrity and cannot replace them. Gate evaluation requires all 18 case/repeat
pairs, correct execution, real device score provenance, real sleep/wake evidence,
distinct machines, and confirmed restoration. A partial run cannot return PASS.
