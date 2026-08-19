# SSOS ESP32 V4.0.0: reproducible 550k split-language training

V4.0.0 publishes the first reproducible training checkpoint for a custom
549,984-parameter causal-language model divided into master and worker stages.
The package includes the exact checkpoint, tokenizer, model and split-boundary
implementation, corpus builder, deterministic gradient-equivalence gate,
quality samples, continuation controls, and physical split-training protocol.

## What V4.0.0 adds

- A custom adult field-language model with 549,984 trainable parameters.
- Master ownership of 274,944 parameters: embeddings and layers 0–1.
- Worker ownership of 275,040 parameters: layers 2–3, final norm and language
  head.
- A detached 96-wide activation boundary with the worker returning its exact
  activation gradient to the master.
- Separate checkpoint state for master weights, worker weights, AdamW,
  deterministic RNG, tokenizer/corpus identity and schedule.
- A 9-D transaction address for corpus, sequence, token window, phase, split,
  checkpoint generation, accumulation slot, retry and curriculum identity.
- Cumulative tokens-per-parameter accounting that remains correct across
  resumed runs and changed batch shapes.
- A first checkpoint at 54,998,528 presented tokens, or 100.00023 tokens per
  parameter.

## Model

| Component | Value |
|---|---:|
| Vocabulary | 940 |
| Width | 96 |
| Layers | 4 |
| Attention heads | 4 |
| Feed-forward width | 192 |
| Maximum context | 256 tokens |
| Master parameters | 274,944 |
| Worker parameters | 275,040 |
| Total parameters | **549,984** |

## First checkpoint

| Measurement | Value |
|---|---:|
| Step | 107,419 |
| Presented tokens | 54,998,528 |
| Tokens per parameter | 100.00023 |
| Held-out evaluations | 22 |
| First held-out loss | 3.661252 |
| Best held-out loss | 2.991671 at step 105,000 |
| Final held-out loss | 2.995222 |
| Checkpoint bytes | 6,652,305 |
| SHA-256 | `0a328c6938af044d65ae26758f7a8fe0a6e8f50e3db71d1af0eaed11b9bcc03c` |

The complete record is
[`results/first-checkpoint/result.json`](results/first-checkpoint/result.json),
with deterministic generated samples in
[`results/first-checkpoint/quality.json`](results/first-checkpoint/quality.json).

## Reproduce the split math

Create an environment and install the pinned runtime:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python .\tools\verify_split.py
```

The gate performs one continuous-model update and one detached split-boundary
update from identical weights and data. It compares loss, every gradient and
every post-update weight.

## Inspect the checkpoint

```powershell
python .\tools\quality_gate.py .\checkpoints\step-00107419.pt
python .\tools\generate.py .\checkpoints\step-00107419.pt `
  "Before crossing the river, the team should"
```

PyTorch checkpoints use Python pickle internally. Load the bundled checkpoint
only after verifying `SHA256SUMS` or the hash above.

## Rebuild the curriculum

The package includes two deterministic builders:

```powershell
python .\tools\prepare_corpus.py --fineweb-rows 300 --wikipedia-rows 100
python .\tools\prepare_curriculum.py --simple-wikipedia-rows 1500 `
  --chars-per-stream 4000000
```

Downloaded corpus text stays local. The bundled manifest records the accepted
corpus, vocabulary and merge hashes; the exact accepted tokenizer files are
included.

## Resume with cumulative token accounting

The checkpoint predates cumulative-token metadata, so its known token count is
passed once when changing the batch shape:

```powershell
python -u .\tools\train_reference.py `
  --resume .\checkpoints\step-00107419.pt `
  --initial-presented-tokens 54998528 `
  --target-tokens-per-parameter 200 `
  --batch-size 16 --sequence-length 64 `
  --learning-rate 3e-5 --min-learning-rate 1e-5 `
  --schedule-origin run `
  --checkpoint-every 5000 --eval-every 5000 --eval-batches 32
```

New V2-format checkpoints store cumulative presented tokens directly and can
be resumed without repeating the initial count.

## Physical protocol

[`TRAINING_PROTOCOL.md`](TRAINING_PROTOCOL.md) defines the board-owned forward,
backward and update transaction: master stage, SPI boundary activation, worker
stage and loss, boundary gradient return, matched update acknowledgement and
two-part checkpoint commit. V4.0.0 provides the executable host reference and
first checkpoint that physical implementations compare against.

## Package contents

- `checkpoints/` — exact resumable first checkpoint
- `tools/model.py` — model and master/worker split
- `tools/train_reference.py` — resumable split training
- `tools/verify_split.py` — deterministic continuous-versus-split gate
- `tools/quality_gate.py` and `tools/generate.py` — language inspection
- `tools/prepare_*.py` — adult/general/domain corpus builders
- `data/` — accepted tokenizer and identity manifest
- `domain/` — authored field-language material
- `results/` — compact first-checkpoint evidence
