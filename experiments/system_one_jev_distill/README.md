# SSOS System-One / Jev Distillation Experiment

Status: **experimental**. This does not modify or invalidate the V2.0.1 hardware proof.

## Second experiment — learned compute dispatcher

The [dispatcher experiment](dispatcher/README.md) follows the owner's PR #21
request to route work across physical computers using ESP32 candidate scores.
Its [first physical results](dispatcher/results/2026-09-16/README.md) passed
12 routing/busy/failover runs across the R1 and RTX 3050 computers, while six
real sleep/wake runs remain blocked. The overall dispatcher gate is **BLOCKED**,
not merge acceptance. The original first experiment and its FAIL result below
are preserved unchanged.

## First live result — 2026-09-16

The [first real Jev run](results/2026-09-16/README.md) collected all 1,024 states
from `jev-1.13.0`. The fixed head achieved 95.30% held-out agreement and 0.04070
probability MAE, but **failed the original gate** because `wake_worker` reached
79.02%, below 80%. A constant majority baseline already achieved 94.09% overall.
The actual distilled head passed 3,424 ESP32 numerical comparisons and reset
persistence, with three read-only serial retries. These are separate results:
successful execution does not turn the teacher-agreement failure into a pass.

## Goal

Test whether Jev-style atomic probabilistic judgments can be distilled into the existing SSOS V2 fixed **9-input / 8-output / 72-weight signed-Q10 head**.

The first mapping uses eight independent Noul-like questions rather than text generation:

1. `route_fast_path`
2. `persist_state`
3. `prefetch_context`
4. `wake_worker`
5. `retry_transport`
6. `request_more_state`
7. `state_anomalous`
8. `fallback_deterministic`

The ESP32 computes eight logits with the existing V2 `MINFER` path. A deterministic caller can interpret `logit >= 0` as probability >= 0.5, or apply `sigmoid(logit)` for an estimated teacher probability. Distillation agreement does not establish calibration or real-world decision correctness. Nothing requires autoregressive text generation.

## 9-D state contract

Inputs 0..7 are normalized to `[-1, +1]`; input 8 is fixed to `1.0` as the bias feature.

| i | feature | -1 | +1 |
|---|---|---|---|
| 0 | urgency | idle / no deadline | immediate / deadline-critical |
| 1 | queue_pressure | empty | saturated |
| 2 | memory_pressure | ample memory | memory critical |
| 3 | transport_health | failing / unstable | healthy |
| 4 | worker_capacity | unavailable | abundant capacity |
| 5 | state_novelty | familiar | highly novel / out-of-distribution |
| 6 | confidence_margin | uncertain | strong separation / confidence |
| 7 | persistence_risk | loss is cheap | state loss is costly |
| 8 | bias | `1.0` | `1.0` |

The contract is intentionally tiny. The host/controller may derive these eight values from richer state. The experiment asks whether the last-mile decision fabric can remain tiny.

## Phase 0 result: synthetic stress test

`distill_system_one.py` includes a reproducible mildly nonlinear synthetic teacher. It is **not Jev** and makes no claim about Jev's hidden architecture. It exists only to answer a narrower question: can the fixed 72-weight head approximate eight nonlinear probabilistic judgments well enough to justify a real teacher run?

Seed 42, 50,000 examples, 40,000 train / 10,000 test:

- mean threshold agreement: **92.126%**
- mean probability MAE: **0.05759**
- mean Brier error against teacher probabilities: **0.006396**
- maximum probability change caused by Q10 quantization: **0.0004701**

That is strong enough to continue to a real Jev-labelled dataset without changing the V2 model shape first.

## One-command real Jev run on Windows

From the repository root, with branch `experiment/system-one-distill` checked out:

```powershell
.\experiments\system_one_jev_distill\run_real_jev_windows.ps1
```

The runner uses `python` by default. Use `-Python 'C:\path with spaces\python.exe'` to select a virtual environment, or `-Python py -PythonArgs '-3'` for the Windows launcher. `-SkipDependencyInstall` uses an already prepared environment.

### Enter the API key locally

Open a masked password window with Windows PowerShell:

```powershell
powershell.exe -NoProfile -STA -File .\experiments\system_one_jev_distill\set_typesafe_key_windows.ps1 -Dialog
```

Paste the key there, not into chat, a command argument, or a source file. The helper stores it at `%LOCALAPPDATA%\SSOS-ESP32\typesafe-api-key.dpapi`, outside the repository, encrypted with Windows DPAPI for the current Windows account. The dedicated credential directory grants access only to that account. To remove it, delete that file. Re-run the helper to replace it.

The runner uses an existing `TYPESAFE_API_KEY` first, then this encrypted file, then hidden console input. A key loaded by the runner is temporarily available to the collector process and removed from the runner environment immediately after collection, or on failure. Dependency installation and state generation happen before loading a stored key. No key is passed on a command line or included in experiment artifacts.

Generated states, teacher labels, distilled weights, and reports are written under a unique `_local/<UTC-time>-<random-id>/` directory, which is gitignored. Earlier runs are preserved. Completed teacher rows are flushed after each response; API failures stop collection with a sanitized error instead of printing SDK exception contents.

The collector explicitly uses `https://api.typesafe.ai` and the `jev-latest` alias. It records the resolved teacher model on every row and writes a metadata sidecar containing the input file SHA-256, SDK version, and exact questions. It refuses to overwrite an existing teacher dataset. These artifacts support auditing which live teacher produced the labels; they contain no API key.

### Remote key entry over Tailscale

`capture_key_tailscale.py` provides a temporary password form for a remote user.
Use a dedicated, unused Tailscale Serve HTTPS port and leave existing Serve
routes intact. The backend binds only `127.0.0.1`; never expose it directly.
Example (replace the DNS name and login with the live Tailscale values):

```powershell
python experiments/system_one_jev_distill/capture_key_tailscale.py --origin https://YOUR-PC.YOUR-TAILNET.ts.net:8447 --allowed-user YOUR-TAILSCALE-LOGIN --status-file experiments/system_one_jev_distill/_local/tailscale-capture.json
# In a second terminal, after the backend starts:
tailscale serve --bg --https=8447 http://127.0.0.1:18761
```

The local status file contains the complete link with a random fragment token.
Open that link on a device connected to the authorized Tailscale account. The
server checks the Serve-injected identity, expected Host, exact POST Origin,
and token. The API key travels only in the HTTPS POST body, then through stdin
to the existing Windows DPAPI storage helper. No key is placed in URLs, process
arguments, HTTP access logs, or source files. The page uses no external assets,
disables caching, and clears the password field on submission.

Only one successful submission is accepted. The backend and dedicated Serve
port close after success or 30 minutes; other Serve routes remain intact. An
existing stored key is not overwritten. To cancel early, stop this backend and
run `tailscale serve --https=8447 off`. A successful local test is not proof that
the user's remote device can reach the form; confirm the remote submission.

The default run generates 1,024 deterministic SSOS-like states, asks Jev all eight Noul questions for each state, distills the returned probabilities into the fixed 72-weight Q10 head, and prints a final PASS/FAIL against the gate below. Use `-Count` or `-Seed` to change the experiment, for example:

```powershell
.\experiments\system_one_jev_distill\run_real_jev_windows.ps1 -Count 2048 -Seed 2026
```

## Manual real Jev path

TypeSafe's public API accepts one state plus multiple independent typed questions in one call. `collect_jev_teacher.py` sends the eight questions above as Noul questions and records the returned probabilities beside the eight normalized SSOS features.

Install:

```bash
python -m pip install typesafe-sdk numpy
```

Set early-access credentials:

```bash
export TYPESAFE_API_KEY=...
```

Prepare JSONL where each row contains both the richer state presented to Jev and the compact SSOS projection:

```json
{"state":{"queue_depth":7,"free_heap":90321,"worker_ready":true},"x8":[0.3,0.7,-0.2,0.8,0.4,0.1,0.2,0.6]}
```

Collect teacher labels:

```bash
python experiments/system_one_jev_distill/collect_jev_teacher.py states.jsonl jev_teacher.jsonl
```

Distill to the 72-weight head:

```bash
python experiments/system_one_jev_distill/distill_system_one.py \
  --teacher-jsonl jev_teacher.jsonl \
  --out system_one_distill_out
```

The output includes `ssos_head_rows.json`, which uses the same 8x9 float-row shape consumed by the existing V2 model installer, plus a report containing Q10 evaluation metrics.

## Pass/fail gate for the first real run

Do not move the goalposts after seeing results. Initial gate:

- >= 90% mean threshold agreement with Jev on a held-out set;
- <= 0.08 mean probability MAE;
- Q10 quantization changes predicted probabilities by <= 0.005 max;
- no single question below 80% threshold agreement without being explicitly investigated.

If the head misses this gate, preserve the result. The next comparison should be a small nonlinear head (for example 9 -> 16 -> 8), not an immediate jump back to a language model.

One additional limitation must be investigated before changing the head: Jev sees richer state, including retry count, state age, and unsaved updates, that the eight-feature student projection omits. A disagreement can therefore reflect missing input information as well as insufficient model capacity. The first run keeps the PR's questions, projection, split, and acceptance thresholds unchanged.

## Why this fits SSOS

V2 already gives us the useful deployment properties: packet-backed replaceable weights, persistence, a fixed compact input/output contract, and deterministic surrounding code. Jev-style System-One behavior gives that head a much better target than prose generation: **small, typed, probabilistic judgments** that software composes.
