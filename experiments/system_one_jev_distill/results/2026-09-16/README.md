# First live Jev / SSOS V2 experiment

**Accuracy gate: FAIL. Physical numerical execution and persistence: PASS, with three serial retries.**

This run continues PR #21 without changing the eight questions, state projection,
model shape, 80/20 split, or acceptance thresholds. It uses 1,024 generated states,
seed 1337, 819 training examples and 205 held-out examples. All responses identified
the teacher as `jev-1.13.0` (requested alias `jev-latest`, typesafe-sdk 0.6.0).
No mock labels were used for these results.

## Original gate

| Metric | Observed | Required | Result |
|---|---:|---:|---|
| Mean threshold agreement | 95.3049% | >=90% | Pass |
| Mean probability MAE | 0.040701 | <=0.08 | Pass |
| Maximum probability delta from Q10 quantization | 0.000424745 | <=0.005 | Pass |
| Worst head: `wake_worker` agreement | 79.0244% | >=80% | **Fail** |

The weak head matches 162/205 decisions; the threshold requires at least 164/205.
This is a failed first experiment, despite narrowly missing that one threshold.
Agreement with Jev does not establish that the underlying decisions are correct
or that the distilled probabilities are calibrated in a real application.

## What the high overall agreement means

The majority decision for each question, learned from training data alone,
achieves **94.0854%** mean held-out agreement. The learned head adds **1.2195
percentage points**. `route_fast_path` has no positive held-out teacher labels,
and `state_anomalous` has no negative ones. Six of eight heads match their
constant majority baseline's threshold agreement, though their probability
errors improve. The headline 95.30% should not be treated as broad decision
competence.

The `wake_worker` misses concentrate at three ready workers: **36 of its 43
errors** occur there. In that group, Jev's mean held-out probability is 0.5395,
while the linear student's is 0.4476. Jev's probabilities fall sharply when
all four workers are ready; the linear model distributes that drop across
intermediate worker counts.

A five-entry worker-count probability lookup, fitted on training examples only,
achieves **95.6098%** held-out agreement for `wake_worker`. This is a post-run
diagnostic, not a replacement gate or independently confirmed new model result.
It supports testing a nonlinear mapping before collecting more API labels.

The richer teacher input also contains retry count, state age and unsaved
updates omitted from the student projection. That remains a possible source
of other disagreements. These results do not prove that capacity alone explains
every miss.

## Physical ESP32 check

- Device: detected ESP32-S3 revision 0.2, 16 MB flash, 8 MB embedded PSRAM.
- Existing application: SSOS V2.0.1. All four backed-up firmware image regions
  matched the release files byte for byte; no firmware was rewritten.
- Original full flash and original packet rows were backed up locally before
  replacement. Saved settings were not erased.
- Candidate: the exact 8x9 Q10 rows in [ssos_head_rows.json](ssos_head_rows.json).
- Inputs: nine basis vectors (exercise all 72 coefficients) plus all 205
  held-out vectors, each tested before and after a watchdog reset.
- **3,424/3,424 numerical outputs matched**, including argmax, within 0.00002.
  Maximum absolute score error: **0.000000555523**.
- `SAVE` succeeded; the boot count advanced 3 -> 4; the model was ready and
  returned matching outputs after reset without reinstalling weights.
- The candidate remains installed as an experimental scoring head.

Transport qualification: the ordinary RTS hard reset left the interface silent
in this session; a non-writing watchdog reset restored the application response.
Two earlier test attempts stopped on incomplete serial replies. Their traces
are preserved. The final run accumulated fragments until newline, paced requests
by 20 ms, and used **three bounded retries of read-only MINFER commands**. Mutating
commands are not retried. This is numerical/persistence evidence with a documented
transport limitation, not a claim of uninterrupted serial reliability.

## Evidence and reproduction

- [report.json](report.json): original accuracy metrics and failed gate.
- [diagnostics.json](diagnostics.json): per-head baselines and worker-count groups.
- [hardware-summary.json](hardware-summary.json): physical counts, tolerance,
  retry count, and raw evidence hashes, without board identifiers.
- [teacher-metadata.json](teacher-metadata.json): exact questions and SDK/API identity.
- [provenance.json](provenance.json): seed, source commits and dataset SHA-256 values.

Raw states, teacher responses, full hardware traces, both failed traces and
backups remain gitignored under `_local/20260916T132231705Z-05d83e57/` and the
earlier `_local/board-backup-20260916T121354Z/`. The real API key is encrypted
outside the repository. It is not included in any result artifact. Capture
confirmed `saved`; its Tailscale HTTPS endpoint closed afterward.

From the repository root, diagnostics can be regenerated without API calls:

```powershell
python experiments/system_one_jev_distill/analyze_jev_run.py experiments/system_one_jev_distill/_local/20260916T132231705Z-05d83e57 --seed 1337
```

`validate_jev_hardware.py RUN --port COM13` installs the candidate rows on existing
V2.0.1 firmware and performs the documented physical test. It backs up packet
rows, does not flash firmware or erase settings, and refuses COM3. Its result
does not alter the accuracy gate.

Next experiment: compare the worker-count lookup and a small nonlinear 9 -> 16
-> 8 head using this preserved dataset. Treat that as exploratory development;
freeze the selected approach and use fresh held-out data before claiming a new
acceptance pass. The first fixed-head result remains FAIL.

Validation of this continuation: 10 experiment tests and 11 existing V2
fixture/parser tests pass. Firmware and validated release artifacts are unchanged.
