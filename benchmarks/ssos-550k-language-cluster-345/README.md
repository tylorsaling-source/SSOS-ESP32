# SSOS ESP32 V4.0.1: cluster 3–4–5

V4.0.1 is a standalone second training lineage for the custom
549,984-parameter split-language architecture. `cluster-345-fresh` begins from
fresh weights and owns its own master/worker weights, AdamW state, RNG,
schedule, quality evidence and checkpoint history.

This package does not contain the V4.0.0 checkpoint. V4.0.0 remains its own
separate release and download.

## Model

| Component | Value |
| --- | ---: |
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
| --- | ---: |
| Step | 5,000 |
| Presented tokens | 5,120,000 |
| Tokens per parameter | 9.309362 |
| Training loss | 3.468667 |
| Held-out loss | 3.488711 |
| Checkpoint bytes | 6,652,561 |
| SHA-256 | `f397e0eb18b74a2acf88e65bcc797628a49ab7612ee833a8b60a326bb3e0f27a` |

The checkpoint records no parent checkpoint. It contains the two model stages,
optimizer, RNG state, cumulative presented-token count, corpus identity and
the complete 100-token-per-parameter schedule.

## Verify

```powershell
python .\tools\quality_gate.py .\checkpoints\step-00005000.pt
python .\tools\verify_split.py
```

`verify_split.py` compares one continuous-model update with the detached
master/worker boundary. The accepted gate has zero loss, gradient and
post-update weight difference.

## Resume

```powershell
python .\tools\prepare_curriculum.py --simple-wikipedia-rows 1500 `
  --chars-per-stream 4000000

python -u .\tools\train_reference.py `
  --resume .\checkpoints\step-00005000.pt `
  --target-tokens-per-parameter 100 `
  --batch-size 16 --sequence-length 64 `
  --learning-rate 3e-4 --min-learning-rate 3e-5 `
  --warmup-steps 2000 --schedule-origin global `
  --checkpoint-every 5000 --eval-every 5000 --eval-batches 32 `
  --seed 345984
```

Downloaded corpus text stays local. `data/manifest.json` pins the accepted
corpus and tokenizer identities.

## Evidence

- [`results/result.json`](results/result.json) — machine-readable checkpoint record
- [`results/quality.json`](results/quality.json) — deterministic generated samples
- [`CLUSTER_IDENTITY.json`](CLUSTER_IDENTITY.json) — independent lineage identity
- `SHA256SUMS` — integrity for every packaged file
